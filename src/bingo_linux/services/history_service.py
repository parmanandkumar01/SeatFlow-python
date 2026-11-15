"""Journey history service layer.

Coordinates between the UI, repository layer, and master vault
for journey history record management.

All history data is non-sensitive (no credentials), so vault
encryption is not required for history fields. The service
validates input, enforces business rules, and coordinates with
the IrctcAccountRepository for account name lookups.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from bingo_linux.database.database import Database
from bingo_linux.repositories import BookingHistoryRepository, IrctcAccountRepository


class HistoryServiceError(Exception):
    """Base exception for history service errors."""


class HistoryNotFoundError(HistoryServiceError):
    """Raised when a history record is not found."""


class InvalidHistoryDataError(HistoryServiceError):
    """Raised when history data fails validation."""


# Confirmed filter identifiers from the original application renderer bundle.
FILTER_ALL = "all"
FILTER_UPCOMING = "upcoming"
FILTER_PAST = "past"
FILTER_TODAY = "today"
FILTER_7D = "7d"
FILTER_30D = "30d"
FILTER_MONTH = "month"

_FILTER_LABELS = {
    FILTER_ALL: "All",
    FILTER_UPCOMING: "Upcoming Journey",
    FILTER_PAST: "Past Journey",
    FILTER_TODAY: "Today",
    FILTER_7D: "Last 7 days",
    FILTER_30D: "Last 30 days",
    FILTER_MONTH: "Month",
}


class HistoryService:
    """Service for managing journey history records.

    Responsibilities:
    - List history records (non-sensitive fields)
    - Get pending filter state
    - Filter history by date range and status
    - Remove/delete history records (soft delete)
    - Remove all history records
    """

    def __init__(self, db: Database) -> None:
        """Initialize the history service.

        Args:
            db: An initialized Database instance.
        """
        self._db = db
        self._repo = BookingHistoryRepository(db)
        self._account_repo = IrctcAccountRepository(db)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_history(self) -> list[dict]:
        """Return all non-deleted journey history records.

        Returns:
            List of history dictionaries with all schema-supported fields.
            The ``gateway`` field from the original renderer is NOT stored
            because it is not part of the approved Phase 4 schema.
        """
        return self._repo.list_all()

    def get_history(self, history_id: str) -> dict:
        """Return a single history record by ID.

        Args:
            history_id: The history record UUID.

        Returns:
            History record dictionary.

        Raises:
            HistoryNotFoundError: If record not found.
        """
        record = self._repo.get_by_id(history_id)
        if record is None or record.get("deleted_at") is not None:
            raise HistoryNotFoundError(f"History record {history_id} not found")
        return record

    def get_pending_filter(self) -> Optional[str]:
        """Return the pending filter state from application settings.

        Returns:
            The pending filter key, or None if no pending filter.
        """
        from bingo_linux.database.database import get_db_path
        from bingo_linux.repositories import SettingsRepository

        settings_repo = SettingsRepository(self._db)
        # The pending filter is stored as a setting; return its value if present.
        value = settings_repo.get("history_pending_filter")
        return value

    def set_pending_filter(self, filter_key: str) -> None:
        """Store the pending filter state in application settings.

        Args:
            filter_key: The filter key to store.
        """
        from bingo_linux.repositories import SettingsRepository

        settings_repo = SettingsRepository(self._db)
        settings_repo.set("history_pending_filter", filter_key)

    def clear_pending_filter(self) -> None:
        """Clear the pending filter state from application settings."""
        from bingo_linux.repositories import SettingsRepository

        settings_repo = SettingsRepository(self._db)
        settings_repo.delete("history_pending_filter")

    def filter_history(
        self,
        filter_key: str = FILTER_ALL,
        irctc_account_id: Optional[str] = None,
    ) -> list[dict]:
        """Filter history records by date range and optional account.

        Date filter semantics (local dates, ISO 8601 journey_date):
        - all: all non-deleted records
        - upcoming: journey_date >= today
        - past: journey_date < today
        - today: journey_date == today
        - 7d: today <= journey_date <= today + 6 days
        - 30d: today <= journey_date <= today + 29 days
        - month: journey_date in current month

        Args:
            filter_key: One of the FILTER_* constants.
            irctc_account_id: Optional account ID to filter by.

        Returns:
            List of matching history dictionaries.
        """
        today = date.today()
        conditions = ["deleted_at IS NULL"]
        params: list = []

        if filter_key == FILTER_ALL:
            pass  # no additional date condition
        elif filter_key == FILTER_UPCOMING:
            conditions.append("journey_date >= ?")
            params.append(today.isoformat())
        elif filter_key == FILTER_PAST:
            conditions.append("journey_date < ?")
            params.append(today.isoformat())
        elif filter_key == FILTER_TODAY:
            conditions.append("journey_date = ?")
            params.append(today.isoformat())
        elif filter_key == FILTER_7D:
            start = today.isoformat()
            end = (today + timedelta(days=6)).isoformat()
            conditions.append("journey_date BETWEEN ? AND ?")
            params.extend([start, end])
        elif filter_key == FILTER_30D:
            start = today.isoformat()
            end = (today + timedelta(days=29)).isoformat()
            conditions.append("journey_date BETWEEN ? AND ?")
            params.extend([start, end])
        elif filter_key == FILTER_MONTH:
            start = today.replace(day=1).isoformat()
            # Last day of current month
            if today.month == 12:
                end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
            end = end_date.isoformat()
            conditions.append("journey_date BETWEEN ? AND ?")
            params.extend([start, end])
        else:
            # Unknown filter key defaults to all
            pass

        if irctc_account_id:
            conditions.append("irctc_account_id = ?")
            params.append(irctc_account_id)

        where = " AND ".join(conditions)
        return self._repo.list_all(where, tuple(params))

    def search_history(self, query: str) -> list[dict]:
        """Search history records by PNR, train number, or from/to station.

        Args:
            query: Search string.

        Returns:
            List of matching history dictionaries.
        """
        like = f"%{query}%"
        return self._repo.list_all(
            "(pnr_number LIKE ? OR train_number LIKE ?)"
            " AND deleted_at IS NULL",
            (like, like),
        )

    def filter_by_status(self, status: str) -> list[dict]:
        """Filter history records by booking status.

        Args:
            status: One of pending, success, failed, cancelled.

        Returns:
            List of matching history dictionaries.
        """
        return self._repo.list_by_status(status)

    def filter_by_account(self, irctc_account_id: str) -> list[dict]:
        """Filter history records by IRCTC account.

        Args:
            irctc_account_id: The account UUID.

        Returns:
            List of matching history dictionaries.
        """
        return self._repo.list_by_account(irctc_account_id)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add_history(
        self,
        pnr_number: str,
        train_number: str,
        journey_date: str,
        booking_status: str,
        fare_amount: float,
        ticket_id: Optional[str] = None,
        irctc_account_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> str:
        """Add a new journey history record.

        Validates required fields and account relationship before
        saving through the repository.

        Args:
            pnr_number: PNR number.
            train_number: Train number.
            journey_date: ISO 8601 date (YYYY-MM-DD).
            booking_status: One of pending, success, failed, cancelled.
            fare_amount: Fare amount.
            ticket_id: Optional associated ticket ID.
            irctc_account_id: Optional associated IRCTC account ID.
            error_message: Optional error message.

        Returns:
            The new history record ID.

        Raises:
            InvalidHistoryDataError: If validation fails.
            HistoryServiceError: If creation fails.
        """
        # Validate required fields
        if not pnr_number or not pnr_number.strip():
            raise InvalidHistoryDataError("PNR number is required.")
        if not train_number or not train_number.strip():
            raise InvalidHistoryDataError("Train number is required.")
        if not journey_date or not journey_date.strip():
            raise InvalidHistoryDataError("Journey date is required.")
        if not booking_status or not booking_status.strip():
            raise InvalidHistoryDataError("Booking status is required.")

        # Validate journey date format
        try:
            datetime.strptime(journey_date, "%Y-%m-%d")
        except ValueError:
            raise InvalidHistoryDataError(
                "Journey date must be in YYYY-MM-DD format."
            )

        # Validate booking status
        valid_statuses = {"pending", "success", "failed", "cancelled"}
        if booking_status.strip().lower() not in valid_statuses:
            raise InvalidHistoryDataError(
                f"Booking status must be one of: {', '.join(sorted(valid_statuses))}."
            )

        # Validate account relationship if provided
        if irctc_account_id:
            account = self._account_repo.get_by_id(irctc_account_id)
            if account is None or account.get("deleted_at") is not None:
                from bingo_linux.services import IrctcAccountNotFoundError

                raise IrctcAccountNotFoundError(
                    f"IRCTC account {irctc_account_id} not found."
                )

        import uuid

        history_id = str(uuid.uuid4())

        try:
            self._repo.create({
                "id": history_id,
                "ticket_id": ticket_id,
                "irctc_account_id": irctc_account_id,
                "pnr_number": pnr_number.strip(),
                "train_number": train_number.strip(),
                "journey_date": journey_date.strip(),
                "booking_status": booking_status.strip().lower(),
                "fare_amount": fare_amount,
                "booking_timestamp": None,  # Uses DEFAULT
                "error_message": error_message,
                "deleted_at": None,
            })
        except Exception as exc:
            raise HistoryServiceError(f"Failed to create history record: {exc}") from exc

        return history_id

    def remove_history(self, history_id: str) -> None:
        """Soft-delete a journey history record.

        Sets deleted_at timestamp. Related records keep their
        references (ON DELETE SET NULL for ticket_id).

        Args:
            history_id: The history record UUID.

        Raises:
            HistoryNotFoundError: If record not found.
            HistoryServiceError: If deletion fails.
        """
        record = self._repo.get_by_id(history_id)
        if record is None or record.get("deleted_at") is not None:
            raise HistoryNotFoundError(f"History record {history_id} not found")

        deleted_at = datetime.now(timezone.utc).isoformat()
        try:
            self._repo.soft_delete(history_id, deleted_at)
        except Exception as exc:
            raise HistoryServiceError(f"Failed to remove history record: {exc}") from exc

    def remove_all_history(self) -> int:
        """Soft-delete all non-deleted history records.

        Returns:
            The number of records removed.

        Raises:
            HistoryServiceError: If removal fails.
        """
        records = self._repo.list_all()
        if not records:
            return 0

        deleted_at = datetime.now(timezone.utc).isoformat()
        removed_count = 0
        try:
            with self._db.transaction() as conn:
                for record in records:
                    conn.execute(
                        "UPDATE booking_history SET deleted_at = ? WHERE id = ?",
                        (deleted_at, record["id"]),
                    )
                    removed_count += 1
        except Exception as exc:
            raise HistoryServiceError(f"Failed to remove all history records: {exc}") from exc

        return removed_count

    # ------------------------------------------------------------------
    # Account name lookup (for display)
    # ------------------------------------------------------------------

    def get_account_name(self, irctc_account_id: Optional[str]) -> str:
        """Return the username for an IRCTC account ID, or em dash.

        Args:
            irctc_account_id: The account UUID, or None.

        Returns:
            The account username, or "—" if not found or None.
        """
        if not irctc_account_id:
            return "—"
        account = self._account_repo.get_by_id(irctc_account_id)
        if account is None or account.get("deleted_at") is not None:
            return "—"
        return account.get("username", "—")

    # ------------------------------------------------------------------
    # Filter labels
    # ------------------------------------------------------------------

    @staticmethod
    def filter_labels() -> dict[str, str]:
        """Return the mapping of filter keys to display labels.

        Returns:
            Dictionary mapping filter key to human-readable label.
        """
        return dict(_FILTER_LABELS)
