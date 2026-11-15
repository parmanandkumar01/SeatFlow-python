"""Ticket profiles repository."""

from __future__ import annotations

from typing import Any, Optional

from bingo_linux.database.database import Database
from bingo_linux.repositories.base_repository import BaseRepository


class TicketRepository(BaseRepository):
    """Repository for the tickets table."""

    table_name = "tickets"
    columns = [
        "id", "train_number", "from_station", "to_station", "journey_date",
        "class", "quota", "passenger_details", "mobile", "email",
        "irctc_account_id", "status", "created_at", "updated_at", "deleted_at",
    ]

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def list_active(self) -> list[dict[str, Any]]:
        """Return all non-deleted ticket profiles."""
        return self.list_all("deleted_at IS NULL")

    def list_by_account(self, irctc_account_id: str) -> list[dict[str, Any]]:
        """Return tickets for a given IRCTC account."""
        return self.list_all(
            "irctc_account_id = ? AND deleted_at IS NULL",
            (irctc_account_id,),
        )

    def soft_delete(self, row_id: str, deleted_at: str) -> bool:
        """Soft-delete a ticket profile.

        Args:
            row_id: The ticket id.
            deleted_at: ISO 8601 timestamp.

        Returns:
            True if soft-deleted, False if not found.
        """
        return super().soft_delete(row_id, deleted_at)
