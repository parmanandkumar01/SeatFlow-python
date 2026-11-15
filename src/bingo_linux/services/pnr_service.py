"""PNR records service layer.

Coordinates between the UI, repository layer, and master vault
for PNR record management.

All PNR data is non-sensitive (no credentials), so vault
encryption is not required for PNR fields. The service
validates input, enforces business rules, and coordinates with
the PnrRepository for persistent storage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bingo_linux.database.database import Database
from bingo_linux.repositories import PnrRepository


class PnrServiceError(Exception):
    """Base exception for PNR service errors."""


class PnrNotFoundError(PnrServiceError):
    """Raised when a PNR record is not found."""


class InvalidPnrDataError(PnrServiceError):
    """Raised when PNR data fails validation."""


# Confirmed PNR status values from the original application renderer bundle.
PNR_STATUS_BOOKED = "booked"
PNR_STATUS_PENDING = "pending"
PNR_STATUS_FAILED = "failed"
PNR_STATUS_CANCELLED = "cancelled"

_VALID_PNR_STATUSES = {
    PNR_STATUS_BOOKED,
    PNR_STATUS_PENDING,
    PNR_STATUS_FAILED,
    PNR_STATUS_CANCELLED,
}


class PnrService:
    """Service for managing PNR records.

    Responsibilities:
    - List PNR records (non-sensitive fields)
    - Get PNR record by PNR number
    - Create PNR record
    - Remove/delete PNR records (soft delete)
    - Remove all PNR records
    - Search PNR records by PNR number or train number
    """

    def __init__(self, db: Database) -> None:
        """Initialize the PNR service.

        Args:
            db: An initialized Database instance.
        """
        self._db = db
        self._repo = PnrRepository(db)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_pnrs(self) -> list[dict]:
        """Return all non-deleted PNR records.

        Returns:
            List of PNR record dictionaries with all schema-supported fields.
        """
        return self._repo.list_all()

    def get_pnr(self, pnr_number: str) -> dict:
        """Return a single PNR record by PNR number.

        Args:
            pnr_number: The PNR number.

        Returns:
            PNR record dictionary.

        Raises:
            PnrNotFoundError: If record not found.
        """
        record = self._repo.get_by_pnr(pnr_number)
        if record is None:
            raise PnrNotFoundError(f"PNR record {pnr_number} not found")
        return record

    def pnr_exists(self, pnr_number: str) -> bool:
        """Return True if a PNR record exists for the given number.

        Args:
            pnr_number: The PNR number.

        Returns:
            True if the PNR record exists and is not deleted.
        """
        record = self._repo.get_by_pnr(pnr_number)
        return record is not None and record.get("deleted_at") is None

    def search_pnrs(self, query: str) -> list[dict]:
        """Search PNR records by PNR number or train number.

        Args:
            query: Search string.

        Returns:
            List of matching PNR record dictionaries.
        """
        like = f"%{query}%"
        return self._repo.list_all(
            "(pnr_number LIKE ? OR train_number LIKE ?)",
            (like, like),
        )

    def filter_by_status(self, status: str) -> list[dict]:
        """Filter PNR records by booking status.

        Args:
            status: One of booked, pending, failed, cancelled.

        Returns:
            List of matching PNR record dictionaries.
        """
        return self._repo.list_all(
            "booking_status = ?",
            (status,),
        )

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add_pnr(
        self,
        pnr_number: str,
        train_number: Optional[str] = None,
        journey_date: Optional[str] = None,
        passenger_names: Optional[str] = None,
        booking_status: str = PNR_STATUS_BOOKED,
        fare_amount: Optional[float] = None,
    ) -> str:
        """Add a new PNR record.

        Validates required fields before saving through the
        repository. The PNR number must be unique.

        Args:
            pnr_number: PNR number.
            train_number: Train number (optional).
            journey_date: ISO 8601 date (YYYY-MM-DD) (optional).
            passenger_names: JSON array of passenger names (optional).
            booking_status: Booking status (default: booked).
            fare_amount: Fare amount (optional).

        Returns:
            The new PNR record ID.

        Raises:
            InvalidPnrDataError: If validation fails.
            PnrServiceError: If creation fails.
        """
        # Validate required fields
        if not pnr_number or not pnr_number.strip():
            raise InvalidPnrDataError("PNR number is required.")

        # Validate PNR format: alphanumeric, reasonable length
        pnr_clean = pnr_number.strip()
        if not pnr_clean.isalnum():
            raise InvalidPnrDataError("PNR number must be alphanumeric.")
        if len(pnr_clean) < 6 or len(pnr_number) > 20:
            raise InvalidPnrDataError("PNR number must be between 6 and 20 characters.")

        # Validate journey date format if provided
        if journey_date is not None and journey_date.strip():
            try:
                datetime.strptime(journey_date.strip(), "%Y-%m-%d")
            except ValueError:
                raise InvalidPnrDataError(
                    "Journey date must be in YYYY-MM-DD format."
                )

        # Validate booking status
        booking_status_clean = (booking_status or PNR_STATUS_BOOKED).strip().lower()
        if booking_status_clean not in _VALID_PNR_STATUSES:
            raise InvalidPnrDataError(
                f"Booking status must be one of: "
                f"{', '.join(sorted(_VALID_PNR_STATUSES))}."
            )

        # Check for duplicate PNR number
        if self._repo.get_by_pnr(pnr_clean) is not None:
            raise InvalidPnrDataError(
                f"PNR number {pnr_clean} already exists."
            )

        import uuid

        pnr_id = str(uuid.uuid4())

        try:
            self._repo.create({
                "id": pnr_id,
                "pnr_number": pnr_clean,
                "train_number": train_number.strip() if train_number else None,
                "journey_date": journey_date.strip() if journey_date else None,
                "passenger_names": passenger_names.strip() if passenger_names else None,
                "booking_status": booking_status_clean,
                "fare_amount": fare_amount,
                "looked_up_at": None,  # Uses DEFAULT
                "created_at": None,    # Uses DEFAULT
                "updated_at": None,    # Uses DEFAULT
                "deleted_at": None,
            })
        except Exception as exc:
            raise PnrServiceError(f"Failed to create PNR record: {exc}") from exc

        return pnr_id

    def remove_pnr(self, pnr_number: str) -> None:
        """Hard-delete a PNR record.

        The pnr_records table does not have a deleted_at column
        (per the Phase 4 schema), so records are hard-deleted.

        Args:
            pnr_number: The PNR number.

        Raises:
            PnrNotFoundError: If record not found.
            PnrServiceError: If deletion fails.
        """
        record = self._repo.get_by_pnr(pnr_number)
        if record is None:
            raise PnrNotFoundError(f"PNR record {pnr_number} not found")

        try:
            self._repo.delete(record["id"])
        except Exception as exc:
            raise PnrServiceError(f"Failed to remove PNR record: {exc}") from exc

    def remove_all_pnrs(self) -> int:
        """Hard-delete all PNR records.

        The pnr_records table does not have a deleted_at column
        (per the Phase 4 schema), so records are hard-deleted.

        Returns:
            The number of records removed.

        Raises:
            PnrServiceError: If removal fails.
        """
        records = self._repo.list_all()
        if not records:
            return 0

        removed_count = 0
        try:
            with self._db.transaction() as conn:
                for record in records:
                    conn.execute(
                        "DELETE FROM pnr_records WHERE id = ?",
                        (record["id"],),
                    )
                    removed_count += 1
        except Exception as exc:
            raise PnrServiceError(f"Failed to remove all PNR records: {exc}") from exc

        return removed_count

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def get_pnr_short(self, pnr_number: str) -> str:
        """Return the last six characters of a PNR number for display.

        Args:
            pnr_number: The full PNR number.

        Returns:
            The last six characters, or the original if shorter.
        """
        if not pnr_number:
            return "—"
        return pnr_number[-6:] if len(pnr_number) >= 6 else pnr_number

    def format_fare_amount(self, amount: Optional[float]) -> str:
        """Format a fare amount for display.

        Args:
            amount: The fare amount, or None.

        Returns:
            The formatted amount string, or "—" if None.
        """
        if amount is None:
            return "—"
        return f"₹{amount}"

    def decode_passenger_names(self, passenger_names: Optional[str]) -> list[str]:
        """Decode passenger names from JSON array string.

        Args:
            passenger_names: JSON-encoded array of passenger names.

        Returns:
            List of passenger name strings, or empty list if None/invalid.
        """
        if not passenger_names:
            return []
        try:
            import json
            data = json.loads(passenger_names)
            if isinstance(data, list):
                return [str(name) for name in data if name]
        except (ValueError, TypeError):
            pass
        return []
