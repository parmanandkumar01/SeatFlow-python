"""Schema version repository."""

from __future__ import annotations

from typing import Any, Optional

from bingo_linux.database.database import Database
from bingo_linux.repositories.base_repository import BaseRepository


class SchemaVersionRepository(BaseRepository):
    """Repository for the schema_version table."""

    table_name = "schema_version"
    columns = ["version", "applied_at", "description"]

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def get_latest_version(self) -> Optional[int]:
        """Return the highest schema version number."""
        conn = self.db.connect()
        row = conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return int(row["version"]) if row else None

    def record_version(self, version: int, description: str) -> None:
        """Record a new schema version.

        Args:
            version: The schema version number.
            description: Human-readable description of the migration.
        """
        self.create({
            "version": version,
            "applied_at": None,  # Uses DEFAULT (datetime('now'))
            "description": description,
        })

    def is_initialized(self) -> bool:
        """Return True if the schema_version table has any rows."""
        return self.count() > 0
