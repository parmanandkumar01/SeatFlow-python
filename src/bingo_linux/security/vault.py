"""Master vault service.

Implements the master vault for protecting stored credentials using
Argon2id key derivation and AES-256-GCM authenticated encryption.

Security properties:
- Master password is never stored in plaintext
- Encryption key exists only in memory while vault is unlocked
- All encrypted fields are authenticated (AES-GCM tag verification)
- Password change re-encrypts all credentials with a new key
- Lock wipes the key from memory

Parameters (per Phase 4 security design §2.1):
  - Argon2id: time_cost=3, memory_cost=64 MiB, parallelism=4
  - Salt: 16 bytes
  - Hash: 32 bytes (used directly as AES-256-GCM key)
  - AES-256-GCM: 12-byte nonce, 16-byte tag
"""

from __future__ import annotations

import base64
import time
from datetime import datetime, timezone
from typing import Final

from bingo_linux.database.database import Database
from bingo_linux.security.encryption import Encryption, EncryptionError
from bingo_linux.security.password_hash import PasswordHasher, PasswordHashError
from bingo_linux.repositories import (
    IrctcAccountRepository,
    ProxyRepository,
    VaultRepository,
)

# Brute force protection (Phase 4 §6.4)
MAX_FAILED_ATTEMPTS: Final[int] = 5
FAILURE_DELAY_SECONDS: Final[float] = 5.0


class VaultError(Exception):
    """Base exception for vault operations."""


class VaultNotConfiguredError(VaultError):
    """Raised when the vault has not been initialized."""


class VaultAlreadyConfiguredError(VaultError):
    """Raised when trying to initialize an already-configured vault."""


class VaultLockedError(VaultError):
    """Raised when an operation requires an unlocked vault."""


class InvalidPasswordError(VaultError):
    """Raised when the master password is incorrect.

    Generic message that does not reveal whether the vault exists
    or whether the password is correct (Phase 4 §6.3).
    """


class VaultService:
    """Master vault service managing encryption state and key lifecycle.

    Coordinates between the database (vault table), password hashing
    (Argon2id), and encryption (AES-256-GCM) layers.
    """

    def __init__(self, db: Database) -> None:
        """Initialize the vault service.

        Args:
            db: An initialized Database instance.
        """
        self._db = db
        self._vault_repo = VaultRepository(db)
        self._irctc_repo = IrctcAccountRepository(db)
        self._proxy_repo = ProxyRepository(db)
        self._hasher = PasswordHasher()
        self._encryption: Encryption | None = None
        self._unlocked = False
        self._configured = False
        self._failed_attempts = 0
        self._lockout_until: float = 0.0

        # Load configured state from database
        self._load_configured_state()

    def _load_configured_state(self) -> None:
        """Load the configured state from the vault table."""
        config = self._vault_repo.get_config()
        self._configured = bool(config and config.get("is_configured"))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        """Return whether the vault has been initialized."""
        return self._configured

    def is_unlocked(self) -> bool:
        """Return whether the vault is currently unlocked."""
        return self._unlocked

    def initialize(self, password: str) -> None:
        """Create the vault with a master password.

        Generates a random salt, derives an encryption key using
        Argon2id, stores the salt and hash in the vault table, and
        unlocks the vault (key held in memory).

        Args:
            password: The master password.

        Raises:
            VaultAlreadyConfiguredError: If the vault is already configured.
            VaultError: If initialization fails.
        """
        if self._configured:
            raise VaultAlreadyConfiguredError("Vault is already configured")

        salt = self._hasher.generate_salt()
        password_hash = self._hasher.hash_password(password)
        encryption_key = self._hasher.derive_key(password, salt)

        try:
            self._vault_repo.create_config(
                salt=salt,
                hash_value=password_hash,
                is_configured=1,
            )
        except Exception as exc:
            raise VaultError(f"Failed to store vault configuration: {exc}") from exc

        self._encryption = Encryption(encryption_key)
        self._configured = True
        self._unlocked = True
        self._failed_attempts = 0

        # Record unlock time
        now = datetime.now(timezone.utc).isoformat()
        self._vault_repo.update_unlock_time(now)

    def unlock(self, password: str) -> bool:
        """Verify the master password and unlock the vault.

        Retrieves the salt and hash from the vault table, verifies
        the password using Argon2id, and if correct derives the
        encryption key and holds it in memory.

        Implements brute force protection: after MAX_FAILED_ATTEMPTS
        consecutive failures, enforces a delay before allowing another
        attempt.

        Args:
            password: The master password to verify.

        Returns:
            True if the password is correct and the vault is unlocked.

        Raises:
            VaultNotConfiguredError: If the vault has not been initialized.
            InvalidPasswordError: If the password is incorrect.
            VaultError: If unlock fails for another reason.
        """
        if not self._configured:
            raise VaultNotConfiguredError("Vault is not configured")

        # Brute force lockout check
        now = time.monotonic()
        if now < self._lockout_until:
            remaining = self._lockout_until - now
            raise InvalidPasswordError(
                f"Too many failed attempts. Try again in {remaining:.0f} seconds."
            )

        config = self._vault_repo.get_config()
        if config is None:
            raise VaultNotConfiguredError("Vault configuration not found")

        stored_hash = config["hash"]
        salt = config["salt"]

        try:
            if not self._hasher.verify_password(password, stored_hash):
                self._record_failed_attempt()
                raise InvalidPasswordError("Invalid master password")
        except PasswordHashError:
            self._record_failed_attempt()
            raise InvalidPasswordError("Invalid master password")

        # Password correct - derive key and unlock
        try:
            encryption_key = self._hasher.derive_key(password, salt)
        except PasswordHashError as exc:
            raise VaultError(f"Key derivation failed: {exc}") from exc

        self._encryption = Encryption(encryption_key)
        self._unlocked = True
        self._failed_attempts = 0
        self._lockout_until = 0.0

        # Record unlock time
        now_iso = datetime.now(timezone.utc).isoformat()
        self._vault_repo.update_unlock_time(now_iso)

        return True

    def lock(self) -> None:
        """Lock the vault and wipe the encryption key from memory.

        After locking, no credential operations are possible until
        the vault is unlocked again.
        """
        if self._encryption is not None:
            self._encryption.wipe_key()
            self._encryption = None
        self._unlocked = False

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string using the vault encryption key.

        The vault must be unlocked. The ciphertext is authenticated
        with an AES-GCM tag, so any tampering will be detected on
        decryption.

        Args:
            plaintext: The string to encrypt.

        Returns:
            Base64-encoded ciphertext (nonce || ciphertext || tag).

        Raises:
            VaultLockedError: If the vault is locked.
            VaultNotConfiguredError: If the vault is not configured.
        """
        if not self._configured:
            raise VaultNotConfiguredError("Vault is not configured")
        if not self._unlocked or self._encryption is None:
            raise VaultLockedError("Vault is locked")
        return self._encryption.encrypt(plaintext)

    def decrypt(self, ciphertext_b64: str) -> str:
        """Decrypt a base64-encoded ciphertext using the vault encryption key.

        The vault must be unlocked. If the ciphertext has been tampered
        with or the key is incorrect, an InvalidPasswordError is raised
        (generic message, does not reveal the cause).

        Args:
            ciphertext_b64: Base64-encoded encrypted string.

        Returns:
            The decrypted plaintext string.

        Raises:
            VaultLockedError: If the vault is locked.
            VaultNotConfiguredError: If the vault is not configured.
            InvalidPasswordError: If decryption or authentication fails.
        """
        if not self._configured:
            raise VaultNotConfiguredError("Vault is not configured")
        if not self._unlocked or self._encryption is None:
            raise VaultLockedError("Vault is locked")
        try:
            return self._encryption.decrypt(ciphertext_b64)
        except EncryptionError as exc:
            raise InvalidPasswordError(str(exc)) from exc

    def change_password(self, old_password: str, new_password: str) -> None:
        """Change the master password and re-encrypt all credentials.

        1. Verifies the old password (must be unlocked first).
        2. Generates a new random salt.
        3. Derives a new encryption key from the new password.
        4. Re-encrypts all encrypted credentials (IRCTC accounts,
           proxies) with the new key.
        5. Updates the vault table with the new salt and hash.
        6. Wipes the old key from memory.

        All credential re-encryption happens within a single database
        transaction for atomicity.

        Args:
            old_password: The current master password.
            new_password: The new master password.

        Raises:
            VaultLockedError: If the vault is locked.
            InvalidPasswordError: If the old password is incorrect.
            VaultError: If the password change fails.
        """
        if not self._unlocked or self._encryption is None:
            raise VaultLockedError("Vault is locked")

        # Verify old password by re-deriving and comparing hash
        config = self._vault_repo.get_config()
        if config is None:
            raise VaultError("Vault configuration not found")

        if not self._hasher.verify_password(old_password, config["hash"]):
            raise InvalidPasswordError("Invalid master password")

        # Generate new salt and derive new key
        new_salt = self._hasher.generate_salt()
        new_password_hash = self._hasher.hash_password(new_password)
        new_encryption_key = self._hasher.derive_key(new_password, new_salt)

        # Collect all encrypted credentials that need re-encryption
        records_to_reencrypt: list[tuple[str, str, str]] = []  # (table, id, encrypted_field)

        # IRCTC accounts
        accounts = self._irctc_repo.list_all()
        for acct in accounts:
            enc_pw = acct.get("password_encrypted")
            if enc_pw:
                records_to_reencrypt.append(("irctc_accounts", acct["id"], enc_pw))

        # Proxies
        proxies = self._proxy_repo.list_all()
        for proxy in proxies:
            enc_pw = proxy.get("password_encrypted")
            if enc_pw:
                records_to_reencrypt.append(("proxies", proxy["id"], enc_pw))

        # Decrypt all credentials with old key, then re-encrypt with new key
        reencrypted: list[tuple[str, str, str]] = []  # (table, id, new_encrypted)
        for table, row_id, old_encrypted in records_to_reencrypt:
            try:
                plaintext = self._encryption.decrypt(old_encrypted)
            except EncryptionError as exc:
                raise VaultError(
                    f"Failed to decrypt {table} id={row_id}: {exc}"
                ) from exc
            new_encrypted = self._encrypt_with_key(new_encryption_key, plaintext)
            reencrypted.append((table, row_id, new_encrypted))

        # Update all records within a single transaction
        try:
            with self._db.transaction() as conn:
                for table, row_id, new_encrypted in reencrypted:
                    if table == "irctc_accounts":
                        conn.execute(
                            "UPDATE irctc_accounts SET password_encrypted = ?, updated_at = datetime('now') WHERE id = ?",
                            (new_encrypted, row_id),
                        )
                    elif table == "proxies":
                        conn.execute(
                            "UPDATE proxies SET password_encrypted = ?, updated_at = datetime('now') WHERE id = ?",
                            (new_encrypted, row_id),
                        )

                # Update vault table with new salt and hash
                conn.execute(
                    "UPDATE vault SET salt = ?, hash = ?, updated_at = datetime('now') WHERE id = 1",
                    (new_salt, new_password_hash),
                )
        except Exception as exc:
            raise VaultError(f"Failed to update credentials: {exc}") from exc

        # Wipe old key and install new key
        self._encryption.wipe_key()
        self._encryption = Encryption(new_encryption_key)

    def reset(self, password: str) -> None:
        """Purge the vault and all credentials.

        Requires the current master password. After reset:
        - Vault salt/hash cleared
        - is_configured = 0
        - All encrypted credentials deleted from database
        - Key wiped from memory

        Args:
            password: The current master password.

        Raises:
            VaultLockedError: If the vault is locked.
            InvalidPasswordError: If the password is incorrect.
            VaultError: If reset fails.
        """
        if not self._unlocked or self._encryption is None:
            raise VaultLockedError("Vault is locked")

        # Verify password
        config = self._vault_repo.get_config()
        if config is None or not self._hasher.verify_password(password, config["hash"]):
            raise InvalidPasswordError("Invalid master password")

        # Delete all encrypted credentials within a transaction
        try:
            with self._db.transaction() as conn:
                conn.execute("UPDATE irctc_accounts SET password_encrypted = '', deleted_at = datetime('now') WHERE deleted_at IS NULL")
                conn.execute("UPDATE proxies SET password_encrypted = '', deleted_at = datetime('now') WHERE deleted_at IS NULL")
                conn.execute(
                    "UPDATE vault SET salt = '', hash = '', is_configured = 0, updated_at = datetime('now') WHERE id = 1"
                )
        except Exception as exc:
            raise VaultError(f"Failed to reset vault: {exc}") from exc

        # Wipe key and mark locked/unconfigured
        self._encryption.wipe_key()
        self._encryption = None
        self._unlocked = False
        self._configured = False

    def get_encryption_key(self) -> bytes:
        """Return the current encryption key (internal use only).

        The key exists only in memory while the vault is unlocked.
        Callers must not log or persist the key.

        Returns:
            The 32-byte AES-256-GCM key.

        Raises:
            VaultLockedError: If the vault is locked.
            VaultNotConfiguredError: If the vault is not configured.
        """
        if not self._configured:
            raise VaultNotConfiguredError("Vault is not configured")
        if not self._unlocked or self._encryption is None:
            raise VaultLockedError("Vault is locked")
        return self._encryption._key  # access internal key for service-level use

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _encrypt_with_key(self, key: bytes, plaintext: str) -> str:
        """Encrypt using a specific key (used during password change).

        Args:
            key: 32-byte AES-256 key.
            plaintext: The string to encrypt.

        Returns:
            Base64-encoded ciphertext.
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import os

        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        combined = nonce + ciphertext_with_tag
        return base64.b64encode(combined).decode("ascii")

    def _record_failed_attempt(self) -> None:
        """Record a failed unlock attempt and potentially enforce lockout."""
        self._failed_attempts += 1
        if self._failed_attempts >= MAX_FAILED_ATTEMPTS:
            self._lockout_until = time.monotonic() + FAILURE_DELAY_SECONDS
