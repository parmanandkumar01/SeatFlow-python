"""Base repository class with common CRUD operations.

Provides reusable database access patterns for all entity
repositories. Uses parameterized SQL queries and transaction
management through the shared Database connection.
"""

from __future__ import annotations

from typing import Any, Optional

from seatflow.database.database import Database


class BaseRepository:
    """Base class for all entity repositories.

    Provides common CRUD operations using parameterized SQL.
    Subclasses must define ``table_name`` and ``columns``.
    """

    table_name: str = ""
    columns: list[str] = []

    def __init__(self, db: Database) -> None:
        """Initialize the repository with a database connection.

        Args:
            db: An initialized Database instance.
        """
        self.db = db

    def _placeholders(self, count: int) -> str:
        """Generate a comma-separated list of SQLite placeholders.

        Args:
            count: Number of placeholders.

        Returns:
            A string like "?, ?, ?".
        """
        return ", ".join(["?"] * count)

    def create(self, data: dict[str, Any]) -> str:
        """Insert a new row and return its primary key.

        Assumes the primary key column is named ``id`` and is
        provided in ``data``. Columns with ``None`` values are
        omitted so SQLite can apply its DEFAULT constraints.

        Args:
            data: Dictionary of column names to values.

        Returns:
            The primary key value of the inserted row.
        """
        # Filter out None values so SQLite applies DEFAULT constraints
        filtered = {k: v for k, v in data.items() if v is not None}
        if not filtered:
            raise ValueError("No non-None values to insert")
        cols = list(filtered.keys())
        vals = [filtered[c] for c in cols]
        sql = (
            f"INSERT INTO {self.table_name} ({', '.join(cols)}) "
            f"VALUES ({self._placeholders(len(cols))})"
        )
        with self.db.transaction() as conn:
            conn.execute(sql, vals)
        return str(filtered.get("id", ""))

    def get_by_id(self, row_id: str) -> Optional[dict[str, Any]]:
        """Fetch a row by its primary key.

        Args:
            row_id: The primary key value.

        Returns:
            A dictionary of column values, or None if not found.
        """
        conn = self.db.connect()
        row = conn.execute(
            f"SELECT * FROM {self.table_name} WHERE id = ?",
            (row_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_all(self, where: Optional[str] = None, params: Optional[tuple] = None) -> list[dict[str, Any]]:
        """Fetch all rows, optionally filtered.

        Args:
            where: Optional WHERE clause (without the WHERE keyword).
            params: Optional parameters for the WHERE clause.

        Returns:
            A list of row dictionaries.
        """
        conn = self.db.connect()
        sql = f"SELECT * FROM {self.table_name}"
        if where:
            sql += f" WHERE {where}"
        rows = conn.execute(sql, params or ()).fetchall()
        return [dict(r) for r in rows]

    def update(self, row_id: str, data: dict[str, Any]) -> bool:
        """Update a row by its primary key.

        Args:
            row_id: The primary key value.
            data: Dictionary of column names to new values.

        Returns:
            True if a row was updated, False if not found.
        """
        # Filter out None values so SQLite applies DEFAULT constraints
        filtered = {k: v for k, v in data.items() if v is not None}
        if not filtered:
            return False
        set_clause = ", ".join(f"{c} = ?" for c in filtered.keys())
        vals = list(filtered.values()) + [row_id]
        sql = f"UPDATE {self.table_name} SET {set_clause} WHERE id = ?"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql, vals)
        return cursor.rowcount > 0

    def delete(self, row_id: str) -> bool:
        """Delete a row by its primary key (hard delete).

        Args:
            row_id: The primary key value.

        Returns:
            True if a row was deleted, False if not found.
        """
        sql = f"DELETE FROM {self.table_name} WHERE id = ?"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql, (row_id,))
        return cursor.rowcount > 0

    def soft_delete(self, row_id: str, deleted_at: str) -> bool:
        """Soft-delete a row by setting its ``deleted_at`` timestamp.

        Args:
            row_id: The primary key value.
            deleted_at: ISO 8601 timestamp string.

        Returns:
            True if a row was soft-deleted, False if not found.
        """
        sql = f"UPDATE {self.table_name} SET deleted_at = ? WHERE id = ?"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql, (deleted_at, row_id))
        return cursor.rowcount > 0

    def count(self, where: Optional[str] = None, params: Optional[tuple] = None) -> int:
        """Count rows, optionally filtered.

        Args:
            where: Optional WHERE clause.
            params: Optional parameters.

        Returns:
            The number of matching rows.
        """
        conn = self.db.connect()
        sql = f"SELECT COUNT(*) as cnt FROM {self.table_name}"
        if where:
            sql += f" WHERE {where}"
        row = conn.execute(sql, params or ()).fetchone()
        return int(row["cnt"]) if row else 0
