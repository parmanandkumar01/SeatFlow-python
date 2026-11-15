"""Security package."""

from seatflow.security.encryption import Encryption, EncryptionError
from seatflow.security.password_hash import PasswordHasher, PasswordHashError
from seatflow.security.vault import (
    VaultService,
    VaultError,
    VaultNotConfiguredError,
    VaultAlreadyConfiguredError,
    VaultLockedError,
    InvalidPasswordError,
)

__all__ = [
    "Encryption",
    "EncryptionError",
    "PasswordHasher",
    "PasswordHashError",
    "VaultService",
    "VaultError",
    "VaultNotConfiguredError",
    "VaultAlreadyConfiguredError",
    "VaultLockedError",
    "InvalidPasswordError",
]
