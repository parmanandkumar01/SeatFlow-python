"""Argon2id password hashing for vault master password verification.

Implements the key derivation chain:
  Master password -> Argon2id(password, salt, params) -> derived_key (32 bytes)

The derived key is used directly as the AES-256-GCM encryption key.
No additional key stretching is applied (Argon2id is sufficient).

Parameters (per Phase 4 security design §2.1):
  - Algorithm: Argon2id
  - Time cost: 3 iterations
  - Memory cost: 64 MiB
  - Parallelism: 4 lanes
  - Salt length: 16 bytes
  - Hash length: 32 bytes
"""

from __future__ import annotations

import base64
import os
from typing import Final

import argon2

# Argon2id parameters (Phase 4 security design §2.1)
ARGON2_TIME_COST: Final[int] = 3
ARGON2_MEMORY_COST: Final[int] = 65536  # 64 MiB in KiB
ARGON2_PARALLELISM: Final[int] = 4
ARGON2_SALT_LEN: Final[int] = 16
ARGON2_HASH_LEN: Final[int] = 32


class PasswordHashError(Exception):
    """Raised for password hashing or verification failures."""


class PasswordHasher:
    """Argon2id password hashing and verification.

    Uses the argon2-cffi library with low-level Argon2id parameters
    matching the Phase 4 security design.
    """

    def __init__(
        self,
        time_cost: int = ARGON2_TIME_COST,
        memory_cost: int = ARGON2_MEMORY_COST,
        parallelism: int = ARGON2_PARALLELISM,
        hash_len: int = ARGON2_HASH_LEN,
        salt_len: int = ARGON2_SALT_LEN,
    ) -> None:
        """Initialize the password hasher with Argon2id parameters.

        Args:
            time_cost: Number of iterations.
            memory_cost: Memory cost in KiB.
            parallelism: Number of parallel lanes.
            hash_len: Length of derived hash in bytes.
            salt_len: Length of random salt in bytes.
        """
        self._hasher = argon2.PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=hash_len,
            salt_len=salt_len,
            type=argon2.Type.ID,
        )
        self._salt_len = salt_len

    def hash_password(self, password: str) -> str:
        """Hash a password using Argon2id.

        Returns a standard argon2-encoded hash string that includes
        the salt, parameters, and hash. This string is stored in
        the vault table's `hash` column.

        Args:
            password: The plaintext master password.

        Returns:
            Argon2-encoded hash string.

        Raises:
            PasswordHashError: If hashing fails.
        """
        try:
            return self._hasher.hash(password)
        except Exception as exc:
            raise PasswordHashError(f"Password hashing failed: {exc}") from exc

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against an Argon2-encoded hash.

        Args:
            password: The plaintext password to verify.
            hashed: The argon2-encoded hash string.

        Returns:
            True if the password matches, False otherwise.

        Raises:
            PasswordHashError: If the hash format is invalid.
        """
        try:
            self._hasher.verify(hashed, password)
            return True
        except argon2.exceptions.VerifyMismatchError:
            return False
        except Exception as exc:
            raise PasswordHashError(f"Password verification failed: {exc}") from exc

    def generate_salt(self) -> str:
        """Generate a cryptographically random salt and return it hex-encoded.

        Returns:
            Hex-encoded random salt string.
        """
        return base64.b16encode(os.urandom(ARGON2_SALT_LEN)).decode("ascii").lower()

    def derive_key(self, password: str, salt: str) -> bytes:
        """Derive a 32-byte encryption key from a password and salt using Argon2id.

        Uses raw Argon2id (not the PHC string format) to derive a
        32-byte key suitable for AES-256-GCM.

        Args:
            password: The plaintext master password.
            salt: Hex-encoded salt string.

        Returns:
            32-byte derived key.

        Raises:
            PasswordHashError: If key derivation fails.
        """
        try:
            salt_bytes = bytes.fromhex(salt)
            raw = argon2.low_level.hash_secret_raw(
                secret=password.encode("utf-8"),
                salt=salt_bytes,
                time_cost=ARGON2_TIME_COST,
                memory_cost=ARGON2_MEMORY_COST,
                parallelism=ARGON2_PARALLELISM,
                hash_len=ARGON2_HASH_LEN,
                type=argon2.low_level.Type.ID,
            )
            return raw
        except Exception as exc:
            raise PasswordHashError(f"Key derivation failed: {exc}") from exc

    def wipe_password(self, password: str) -> None:
        """Best-effort overwrite of a password string in memory.

        Python strings are immutable, so this cannot truly zero the
        original memory. The caller should avoid retaining password
        strings longer than necessary.

        Args:
            password: The password string to "wipe" (no-op for safety).
        """
        # Strings are immutable in Python; the caller must ensure
        # the password is not retained. This is a no-op placeholder
        # to document the intent.
        del password
