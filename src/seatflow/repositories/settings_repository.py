"""Settings repository."""

from __future__ import annotations

from typing import Any, Optional

from seatflow.database.database import Database
from seatflow.repositories.base_repository import BaseRepository


class SettingsRepository(BaseRepository):
    """Repository for the settings table (key-value application settings)."""

    table_name = "settings"
    columns = ["key", "value", "updated_at"]

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def get(self, key: str) -> Optional[str]:
        """Return the value for a setting key.

        Args:
            key: The setting key.

        Returns:
            The setting value, or None if not found.
        """
        conn = self.db.connect()
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        """Insert or update a setting value.

        Args:
            key: The setting key.
            value: The setting value.
        """
        conn = self.db.connect()
        with self.db.transaction() as c:
            c.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
                (key, value),
            )

    def delete(self, key: str) -> bool:
        """Delete a setting by key.

        Args:
            key: The setting key.

        Returns:
            True if deleted, False if not found.
        """
        conn = self.db.connect()
        with self.db.transaction() as c:
            cursor = c.execute("DELETE FROM settings WHERE key = ?", (key,))
        return cursor.rowcount > 0

    def get_all(self) -> dict[str, str]:
        """Return all settings as a dictionary."""
        conn = self.db.connect()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}
