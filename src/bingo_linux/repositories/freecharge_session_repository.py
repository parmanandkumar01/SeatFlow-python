"""Freecharge sessions repository."""

from __future__ import annotations

from typing import Any, Optional

from bingo_linux.database.database import Database
from bingo_linux.repositories.base_repository import BaseRepository


class FreechargeSessionRepository(BaseRepository):
    """Repository for the freecharge_sessions table."""

    table_name = "freecharge_sessions"
    columns = [
        "id", "mobile", "session_id", "otp_verified", "bank_linked",
        "balance_cached", "last_checked", "created_at", "updated_at",
        "deleted_at",
    ]

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def get_by_mobile(self, mobile: str) -> Optional[dict[str, Any]]:
        """Return a session by mobile number.

        Args:
            mobile: The mobile number.

        Returns:
            Session row dictionary, or None.
        """
        conn = self.db.connect()
        row = conn.execute(
            "SELECT * FROM freecharge_sessions WHERE mobile = ? AND deleted_at IS NULL",
            (mobile,),
        ).fetchone()
        return dict(row) if row else None

    def get_by_session_id(self, session_id: str) -> Optional[dict[str, Any]]:
        """Return a session by session ID.

        Args:
            session_id: The session identifier.

        Returns:
            Session row dictionary, or None.
        """
        conn = self.db.connect()
        row = conn.execute(
            "SELECT * FROM freecharge_sessions WHERE session_id = ? AND deleted_at IS NULL",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_active(self) -> list[dict[str, Any]]:
        """Return all active (non-deleted) sessions.

        Returns:
            List of session dictionaries.
        """
        return self.list_all("deleted_at IS NULL ORDER BY created_at DESC")

    def soft_delete(self, row_id: str, deleted_at: str) -> bool:
        """Soft-delete a session.

        Args:
            row_id: The session id.
            deleted_at: ISO 8601 timestamp.

        Returns:
            True if soft-deleted, False if not found.
        """
        return super().soft_delete(row_id, deleted_at)
