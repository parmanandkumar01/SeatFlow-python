"""Booking history repository."""

from __future__ import annotations

from typing import Any, Optional

from bingo_linux.database.database import Database
from bingo_linux.repositories.base_repository import BaseRepository


class BookingHistoryRepository(BaseRepository):
    """Repository for the booking_history table."""

    table_name = "booking_history"
    columns = [
        "id", "ticket_id", "irctc_account_id", "pnr_number", "train_number",
        "journey_date", "booking_status", "fare_amount", "booking_timestamp",
        "error_message", "deleted_at",
    ]

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def list_all(
        self,
        where: Optional[str] = None,
        params: Optional[tuple] = None,
    ) -> list[dict[str, Any]]:
        """Return all non-deleted booking history records.

        Args:
            where: Optional WHERE clause (without the WHERE keyword).
            params: Optional parameters for the WHERE clause.

        Returns:
            List of matching history dictionaries.
        """
        conditions = ["deleted_at IS NULL"]
        if where:
            conditions.append(where)
        where_clause = " AND ".join(conditions)
        return super().list_all(where_clause, params)

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        """Return history records filtered by booking status."""
        return super().list_all(
            "booking_status = ? AND deleted_at IS NULL",
            (status,),
        )

    def list_by_account(self, irctc_account_id: str) -> list[dict[str, Any]]:
        """Return history records for a given IRCTC account."""
        return super().list_all(
            "irctc_account_id = ? AND deleted_at IS NULL",
            (irctc_account_id,),
        )

    def soft_delete(self, row_id: str, deleted_at: str) -> bool:
        """Soft-delete a history record.

        Args:
            row_id: The history id.
            deleted_at: ISO 8601 timestamp.

        Returns:
            True if soft-deleted, False if not found.
        """
        return super().soft_delete(row_id, deleted_at)

    def list_by_date_range(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return history records within a date range.

        Args:
            start_date: ISO 8601 date string (inclusive), or None.
            end_date: ISO 8601 date string (inclusive), or None.

        Returns:
            List of matching history dictionaries.
        """
        conditions = ["deleted_at IS NULL"]
        params: list = []
        if start_date:
            conditions.append("journey_date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("journey_date <= ?")
            params.append(end_date)
        where = " AND ".join(conditions)
        return super().list_all(where, tuple(params))

    def list_by_pnr_or_train(self, query: str) -> list[dict[str, Any]]:
        """Return history records matching PNR or train number.

        Args:
            query: Search string.

        Returns:
            List of matching history dictionaries.
        """
        like = f"%{query}%"
        where = "(pnr_number LIKE ? OR train_number LIKE ?) AND deleted_at IS NULL"
        return super().list_all(where, (like, like))
