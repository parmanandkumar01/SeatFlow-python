"""News acknowledgments repository."""

from __future__ import annotations

from seatflow.database.database import Database
from seatflow.repositories.base_repository import BaseRepository


class NewsAcknowledgmentRepository(BaseRepository):
    """Repository for the news_acknowledgments table."""

    table_name = "news_acknowledgments"
    columns = ["news_id", "acknowledged_at"]

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def is_acknowledged(self, news_id: str) -> bool:
        """Return True if a news item has been acknowledged.

        Args:
            news_id: The news item identifier.

        Returns:
            True if acknowledged, False otherwise.
        """
        conn = self.db.connect()
        row = conn.execute(
            "SELECT 1 FROM news_acknowledgments WHERE news_id = ?",
            (news_id,),
        ).fetchone()
        return row is not None

    def acknowledge(self, news_id: str) -> None:
        """Mark a news item as acknowledged.

        Args:
            news_id: The news item identifier.
        """
        if self.is_acknowledged(news_id):
            return
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO news_acknowledgments (news_id) VALUES (?)",
                (news_id,),
            )

    def get_all_acknowledged_ids(self) -> set[str]:
        """Return the set of all acknowledged news identifiers.

        Returns:
            Set of news_id strings.
        """
        conn = self.db.connect()
        rows = conn.execute("SELECT news_id FROM news_acknowledgments").fetchall()
        return {r["news_id"] for r in rows}

    def unacknowledge(self, news_id: str) -> None:
        """Remove acknowledgment for a news item.

        Args:
            news_id: The news item identifier.
        """
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM news_acknowledgments WHERE news_id = ?",
                (news_id,),
            )
