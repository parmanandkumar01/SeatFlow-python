"""Railway account service layer.

Coordinates between the UI, repository layer, and master vault
for railway account (IRCTC account) management.

All sensitive credential operations go through the vault. The
service never handles plaintext passwords directly — it delegates
encryption/decryption to the vault service.
"""

from __future__ import annotations

from typing import Optional

from bingo_linux.database.database import Database
from bingo_linux.repositories import IrctcAccountRepository
from bingo_linux.security.vault import (
    InvalidPasswordError,
    VaultLockedError,
    VaultNotConfiguredError,
    VaultService,
)


class AccountServiceError(Exception):
    """Base exception for account service errors."""


class AccountNotFoundError(AccountServiceError):
    """Raised when an account is not found."""


class DuplicateUsernameError(AccountServiceError):
    """Raised when a username already exists."""


class VaultRequiredError(AccountServiceError):
    """Raised when vault operations are required but vault is locked/not configured."""


class IrctcAccountService:
    """Service for managing railway account profiles.

    Responsibilities:
    - List accounts (non-sensitive fields only)
    - Add account (encrypt password via vault)
    - Edit account (update fields, optionally re-encrypt password)
    - Delete/soft-delete account
    - Check for duplicate usernames
    """

    def __init__(self, db: Database, vault: VaultService) -> None:
        """Initialize the account service.

        Args:
            db: An initialized Database instance.
            vault: An initialized VaultService instance.
        """
        self._db = db
        self._vault = vault
        self._repo = IrctcAccountRepository(db)

    # ------------------------------------------------------------------
    # Read operations (no vault required)
    # ------------------------------------------------------------------

    def list_accounts(self) -> list[dict]:
        """Return all active, non-deleted accounts.

        Returns non-sensitive fields only. Passwords are never
        returned by this method.

        Returns:
            List of account dictionaries with id, username, mobile,
            email, is_active, created_at, updated_at.
        """
        accounts = self._repo.list_active()
        # Remove sensitive fields from each account
        for acct in accounts:
            acct.pop("password_encrypted", None)
        return accounts

    def get_account(self, account_id: str) -> dict:
        """Return a single account by ID.

        Returns non-sensitive fields only. Passwords are never
        returned by this method.

        Args:
            account_id: The account UUID.

        Returns:
            Account dictionary.

        Raises:
            AccountNotFoundError: If account not found.
        """
        account = self._repo.get_by_id(account_id)
        if account is None or account.get("deleted_at") is not None:
            raise AccountNotFoundError(f"Account {account_id} not found")
        # Remove sensitive fields before returning
        account.pop("password_encrypted", None)
        return account

    def username_exists(self, username: str, exclude_id: Optional[str] = None) -> bool:
        """Check if a username already exists.

        Args:
            username: The username to check.
            exclude_id: Optional account ID to exclude (for edit mode).

        Returns:
            True if username exists.
        """
        existing = self._repo.get_by_username(username)
        if existing is None:
            return False
        if exclude_id and existing["id"] == exclude_id:
            return False
        return True

    # ------------------------------------------------------------------
    # Write operations (vault required)
    # ------------------------------------------------------------------

    def add_account(
        self,
        username: str,
        password: str,
        mobile: Optional[str] = None,
        email: Optional[str] = None,
        is_active: bool = True,
    ) -> str:
        """Add a new railway account.

        The password is encrypted via the vault before storage.
        The vault must be unlocked.

        Args:
            username: The railway account username.
            password: The account password (plaintext, will be encrypted).
            mobile: Optional mobile number.
            email: Optional email address.
            is_active: Whether the account is active.

        Returns:
            The new account ID.

        Raises:
            VaultRequiredError: If vault is not configured or locked.
            DuplicateUsernameError: If username already exists.
            AccountServiceError: If creation fails.
        """
        if not self._vault.is_configured():
            raise VaultRequiredError("Vault is not configured")
        if not self._vault.is_unlocked():
            raise VaultRequiredError("Vault is locked")

        if self.username_exists(username):
            raise DuplicateUsernameError(f"Username '{username}' already exists")

        # Encrypt password via vault
        encrypted_password = self._vault.encrypt(password)

        import uuid

        account_id = str(uuid.uuid4())

        try:
            self._repo.create({
                "id": account_id,
                "username": username,
                "password_encrypted": encrypted_password,
                "mobile": mobile,
                "email": email,
                "is_active": 1 if is_active else 0,
                "created_at": None,  # Uses DEFAULT
                "updated_at": None,  # Uses DEFAULT
                "deleted_at": None,
            })
        except Exception as exc:
            raise AccountServiceError(f"Failed to create account: {exc}") from exc

        return account_id

    def update_account(
        self,
        account_id: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        mobile: Optional[str] = None,
        email: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> None:
        """Update an existing railway account.

        If a new password is provided, it is encrypted via the vault.
        The vault must be unlocked for password changes.

        Args:
            account_id: The account UUID.
            username: New username (optional).
            password: New password (optional, plaintext).
            mobile: New mobile number (optional).
            email: New email address (optional).
            is_active: New active status (optional).

        Raises:
            AccountNotFoundError: If account not found.
            VaultRequiredError: If vault is locked and password change requested.
            DuplicateUsernameError: If new username already exists.
            AccountServiceError: If update fails.
        """
        account = self._repo.get_by_id(account_id)
        if account is None or account.get("deleted_at") is not None:
            raise AccountNotFoundError(f"Account {account_id} not found")

        update_data: dict = {}

        if username is not None and username != account["username"]:
            if self.username_exists(username, exclude_id=account_id):
                raise DuplicateUsernameError(f"Username '{username}' already exists")
            update_data["username"] = username

        if mobile is not None:
            update_data["mobile"] = mobile

        if email is not None:
            update_data["email"] = email

        if is_active is not None:
            update_data["is_active"] = 1 if is_active else 0

        if password is not None:
            if not self._vault.is_unlocked():
                raise VaultRequiredError("Vault is locked to update password")
            update_data["password_encrypted"] = self._vault.encrypt(password)

        if update_data:
            update_data["updated_at"] = None  # Uses DEFAULT
            try:
                self._repo.update(account_id, update_data)
            except Exception as exc:
                raise AccountServiceError(f"Failed to update account: {exc}") from exc

    def delete_account(self, account_id: str) -> None:
        """Soft-delete a railway account.

        Sets deleted_at timestamp rather than hard-deleting,
        respecting foreign-key constraints (related ticket/history
        records keep their references via ON DELETE SET NULL).

        Args:
            account_id: The account UUID.

        Raises:
            AccountNotFoundError: If account not found.
            AccountServiceError: If deletion fails.
        """
        account = self._repo.get_by_id(account_id)
        if account is None or account.get("deleted_at") is not None:
            raise AccountNotFoundError(f"Account {account_id} not found")

        from datetime import datetime, timezone

        deleted_at = datetime.now(timezone.utc).isoformat()
        try:
            self._repo.soft_delete(account_id, deleted_at)
        except Exception as exc:
            raise AccountServiceError(f"Failed to delete account: {exc}") from exc

    # ------------------------------------------------------------------
    # Vault state
    # ------------------------------------------------------------------

    def is_vault_unlocked(self) -> bool:
        """Return whether the vault is currently unlocked."""
        return self._vault.is_unlocked()

    def is_vault_configured(self) -> bool:
        """Return whether the vault has been configured."""
        return self._vault.is_configured()
