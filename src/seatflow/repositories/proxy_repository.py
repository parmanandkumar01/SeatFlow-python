"""Proxies repository."""

from __future__ import annotations

from typing import Any, Optional

from seatflow.database.database import Database
from seatflow.repositories.base_repository import BaseRepository


class ProxyRepository(BaseRepository):
    """Repository for the proxies table.

    Proxy passwords are stored encrypted via the vault layer.
    """

    table_name = "proxies"
    columns = [
        "id", "host", "port", "username", "password_encrypted",
        "type", "is_active", "last_tested", "test_result",
        "test_latency_ms", "created_at", "updated_at", "deleted_at",
    ]

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def list_active(self) -> list[dict[str, Any]]:
        """Return all active, non-deleted proxies."""
        return self.list_all("is_active = 1 AND deleted_at IS NULL")

    def get_active(self) -> Optional[dict[str, Any]]:
        """Return the currently active proxy."""
        conn = self.db.connect()
        row = conn.execute(
            "SELECT * FROM proxies WHERE is_active = 1 AND deleted_at IS NULL LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def soft_delete(self, row_id: str, deleted_at: str) -> bool:
        """Soft-delete a proxy.

        Args:
            row_id: The proxy id.
            deleted_at: ISO 8601 timestamp.

        Returns:
            True if soft-deleted, False if not found.
        """
        return super().soft_delete(row_id, deleted_at)
