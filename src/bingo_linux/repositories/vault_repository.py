"""Vault repository."""

from __future__ import annotations

from typing import Any, Optional

from bingo_linux.database.database import Database
from bingo_linux.repositories.base_repository import BaseRepository


class VaultRepository(BaseRepository):
    """Repository for the vault table.

    The vault table stores master vault configuration. It is a
    single-row table (id = 1). Credential encryption/decryption
    is handled by the separate security layer.
    """

    table_name = "vault"
    columns = [
        "id", "salt", "hash", "created_at", "updated_at",
        "unlocked_at", "is_configured",
    ]

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def get_config(self) -> Optional[dict[str, Any]]:
        """Return the vault configuration row (id = 1)."""
        return self.get_by_id("1")

    def is_configured(self) -> bool:
        """Return True if the vault has been configured."""
        row = self.get_config()
        return bool(row and row.get("is_configured"))

    def create_config(
        self,
        salt: str,
        hash_value: str,
        is_configured: int = 1,
    ) -> str:
        """Create the initial vault configuration.

        Args:
            salt: Hex-encoded Argon2 salt.
            hash_value: Hex-encoded Argon2id hash of master password.
            is_configured: 1 if configured, 0 otherwise.

        Returns:
            The vault row id.
        """
        return self.create({
            "id": "1",
            "salt": salt,
            "hash": hash_value,
            "created_at": None,
            "updated_at": None,
            "unlocked_at": None,
            "is_configured": is_configured,
        })

    def update_unlock_time(self, unlocked_at: str) -> bool:
        """Update the last successful unlock timestamp.

        Args:
            unlocked_at: ISO 8601 timestamp string.

        Returns:
            True if updated, False if not found.
        """
        return self.update("1", {"unlocked_at": unlocked_at, "updated_at": None})

    def mark_unconfigured(self) -> bool:
        """Reset the vault to unconfigured state (purge credentials)."""
        return self.update("1", {"is_configured": 0, "updated_at": None})
