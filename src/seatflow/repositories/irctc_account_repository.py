"""IRCTC accounts repository."""

from __future__ import annotations

from typing import Any, Optional

from seatflow.database.database import Database
from seatflow.repositories.base_repository import BaseRepository


class IrctcAccountRepository(BaseRepository):
    """Repository for the irctc_accounts table.

    Passwords are stored encrypted via the vault layer. This
    repository only handles storage and retrieval.
    """

    table_name = "irctc_accounts"
    columns = [
        "id", "username", "password_encrypted", "mobile", "email",
        "is_active", "created_at", "updated_at", "deleted_at",
    ]

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def get_by_username(self, username: str) -> Optional[dict[str, Any]]:
        """Return an account by username.

        Args:
            username: The IRCTC username.

        Returns:
            Account row dictionary, or None.
        """
        conn = self.db.connect()
        row = conn.execute(
            "SELECT * FROM irctc_accounts WHERE username = ? AND deleted_at IS NULL",
            (username,),
        ).fetchone()
        return dict(row) if row else None

    def list_active(self) -> list[dict[str, Any]]:
        """Return all active, non-deleted accounts."""
        return self.list_all(
            "is_active = 1 AND deleted_at IS NULL"
        )

    def soft_delete(self, row_id: str, deleted_at: str) -> bool:
        """Soft-delete an account by setting deleted_at.

        Args:
            row_id: The account id.
            deleted_at: ISO 8601 timestamp.

        Returns:
            True if soft-deleted, False if not found.
        """
        return super().soft_delete(row_id, deleted_at)
