"""Ticket service layer.

Coordinates between the UI, repository layer, and master vault
for ticket booking profile management.

All ticket data is non-sensitive (no credentials), so vault
encryption is not required for ticket fields. The service
validates input, enforces business rules, and coordinates with
the IrctcAccountService for account relationships.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bingo_linux.database.database import Database
from bingo_linux.repositories import IrctcAccountRepository, TicketRepository


class TicketServiceError(Exception):
    """Base exception for ticket service errors."""


class TicketNotFoundError(TicketServiceError):
    """Raised when a ticket is not found."""


class InvalidTicketDataError(TicketServiceError):
    """Raised when ticket data fails validation."""


class TicketAccountNotFoundError(TicketServiceError):
    """Raised when the referenced IRCTC account is not found."""


class TicketService:
    """Service for managing ticket booking profiles.

    Responsibilities:
    - List ticket profiles (non-sensitive fields)
    - Add ticket profile (validate fields, optional account link)
    - Edit ticket profile (update fields, preserve integrity)
    - Delete/soft-delete ticket profile
    - Search and filter tickets
    """

    def __init__(self, db: Database) -> None:
        """Initialize the ticket service.

        Args:
            db: An initialized Database instance.
        """
        self._db = db
        self._repo = TicketRepository(db)
        self._account_repo = IrctcAccountRepository(db)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_tickets(self) -> list[dict]:
        """Return all non-deleted ticket profiles.

        Returns:
            List of ticket dictionaries with all non-sensitive fields.
        """
        return self._repo.list_active()

    def get_ticket(self, ticket_id: str) -> dict:
        """Return a single ticket by ID.

        Args:
            ticket_id: The ticket UUID.

        Returns:
            Ticket dictionary.

        Raises:
            TicketNotFoundError: If ticket not found.
        """
        ticket = self._repo.get_by_id(ticket_id)
        if ticket is None or ticket.get("deleted_at") is not None:
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")
        return ticket

    def list_tickets_by_account(self, irctc_account_id: str) -> list[dict]:
        """Return tickets for a given IRCTC account.

        Args:
            irctc_account_id: The account UUID.

        Returns:
            List of ticket dictionaries.
        """
        return self._repo.list_by_account(irctc_account_id)

    def search_tickets(self, query: str) -> list[dict]:
        """Search tickets by train number, from station, or to station.

        Args:
            query: Search string.

        Returns:
            List of matching ticket dictionaries.
        """
        like = f"%{query}%"
        return self._repo.list_all(
            "(train_number LIKE ? OR from_station LIKE ? OR to_station LIKE ?)"
            " AND deleted_at IS NULL",
            (like, like, like),
        )

    def filter_tickets(
        self,
        status: Optional[str] = None,
        irctc_account_id: Optional[str] = None,
        from_station: Optional[str] = None,
        to_station: Optional[str] = None,
    ) -> list[dict]:
        """Filter tickets by various criteria.

        Args:
            status: Filter by booking status.
            irctc_account_id: Filter by associated account.
            from_station: Filter by source station.
            to_station: Filter by destination station.

        Returns:
            List of matching ticket dictionaries.
        """
        conditions = ["deleted_at IS NULL"]
        params: list = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if irctc_account_id:
            conditions.append("irctc_account_id = ?")
            params.append(irctc_account_id)
        if from_station:
            conditions.append("from_station = ?")
            params.append(from_station)
        if to_station:
            conditions.append("to_station = ?")
            params.append(to_station)

        where = " AND ".join(conditions)
        return self._repo.list_all(where, tuple(params))

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add_ticket(
        self,
        train_number: str,
        from_station: str,
        to_station: str,
        journey_date: str,
        class_type: str,
        quota: str,
        passenger_details: str,
        mobile: Optional[str] = None,
        email: Optional[str] = None,
        irctc_account_id: Optional[str] = None,
        status: str = "draft",
    ) -> str:
        """Add a new ticket booking profile.

        Validates required fields and account relationship before
        saving through the repository.

        Args:
            train_number: Train number.
            from_station: Source station code.
            to_station: Destination station code.
            journey_date: ISO 8601 date (YYYY-MM-DD).
            class_type: Travel class (e.g., 3A, 2A, SL).
            quota: Booking quota (e.g., Tatkal, General).
            passenger_details: JSON string of passenger objects.
            mobile: Optional mobile number.
            email: Optional email address.
            irctc_account_id: Optional associated IRCTC account ID.
            status: Ticket status (default: draft).

        Returns:
            The new ticket ID.

        Raises:
            InvalidTicketDataError: If validation fails.
            AccountNotFoundError: If referenced account doesn't exist.
            TicketServiceError: If creation fails.
        """
        # Validate required fields
        if not train_number or not train_number.strip():
            raise InvalidTicketDataError("Train number is required.")
        if not from_station or not from_station.strip():
            raise InvalidTicketDataError("From station is required.")
        if not to_station or not to_station.strip():
            raise InvalidTicketDataError("To station is required.")
        if not journey_date or not journey_date.strip():
            raise InvalidTicketDataError("Journey date is required.")
        if not class_type or not class_type.strip():
            raise InvalidTicketDataError("Travel class is required.")
        if not quota or not quota.strip():
            raise InvalidTicketDataError("Quota is required.")
        if not passenger_details or not passenger_details.strip():
            raise InvalidTicketDataError("Passenger details are required.")

        # Validate journey date format (basic)
        try:
            datetime.strptime(journey_date, "%Y-%m-%d")
        except ValueError:
            raise InvalidTicketDataError(
                "Journey date must be in YYYY-MM-DD format."
            )

        # Validate account relationship if provided
        if irctc_account_id:
            account = self._account_repo.get_by_id(irctc_account_id)
            if account is None or account.get("deleted_at") is not None:
                raise TicketAccountNotFoundError(
                    f"IRCTC account {irctc_account_id} not found."
                )

        import uuid

        ticket_id = str(uuid.uuid4())

        try:
            self._repo.create({
                "id": ticket_id,
                "train_number": train_number.strip(),
                "from_station": from_station.strip(),
                "to_station": to_station.strip(),
                "journey_date": journey_date.strip(),
                "class": class_type.strip(),
                "quota": quota.strip(),
                "passenger_details": passenger_details.strip(),
                "mobile": mobile.strip() if mobile else None,
                "email": email.strip() if email else None,
                "irctc_account_id": irctc_account_id,
                "status": status,
                "created_at": None,
                "updated_at": None,
                "deleted_at": None,
            })
        except Exception as exc:
            raise TicketServiceError(f"Failed to create ticket: {exc}") from exc

        return ticket_id

    def update_ticket(
        self,
        ticket_id: str,
        train_number: Optional[str] = None,
        from_station: Optional[str] = None,
        to_station: Optional[str] = None,
        journey_date: Optional[str] = None,
        class_type: Optional[str] = None,
        quota: Optional[str] = None,
        passenger_details: Optional[str] = None,
        mobile: Optional[str] = None,
        email: Optional[str] = None,
        irctc_account_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        """Update an existing ticket booking profile.

        Only provided fields are updated. Validates account
        relationship if changed.

        Args:
            ticket_id: The ticket UUID.
            train_number: New train number (optional).
            from_station: New source station (optional).
            to_station: New destination station (optional).
            journey_date: New journey date (optional).
            class_type: New travel class (optional).
            quota: New quota (optional).
            passenger_details: New passenger details JSON (optional).
            mobile: New mobile number (optional).
            email: New email address (optional).
            irctc_account_id: New associated account ID (optional).
            status: New status (optional).

        Raises:
            TicketNotFoundError: If ticket not found.
            AccountNotFoundError: If referenced account doesn't exist.
            InvalidTicketDataError: If validation fails.
            TicketServiceError: If update fails.
        """
        ticket = self._repo.get_by_id(ticket_id)
        if ticket is None or ticket.get("deleted_at") is not None:
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")

        update_data: dict = {}

        if train_number is not None:
            if not train_number.strip():
                raise InvalidTicketDataError("Train number cannot be empty.")
            update_data["train_number"] = train_number.strip()

        if from_station is not None:
            if not from_station.strip():
                raise InvalidTicketDataError("From station cannot be empty.")
            update_data["from_station"] = from_station.strip()

        if to_station is not None:
            if not to_station.strip():
                raise InvalidTicketDataError("To station cannot be empty.")
            update_data["to_station"] = to_station.strip()

        if journey_date is not None:
            if not journey_date.strip():
                raise InvalidTicketDataError("Journey date cannot be empty.")
            try:
                datetime.strptime(journey_date, "%Y-%m-%d")
            except ValueError:
                raise InvalidTicketDataError(
                    "Journey date must be in YYYY-MM-DD format."
                )
            update_data["journey_date"] = journey_date.strip()

        if class_type is not None:
            if not class_type.strip():
                raise InvalidTicketDataError("Travel class cannot be empty.")
            update_data["class"] = class_type.strip()

        if quota is not None:
            if not quota.strip():
                raise InvalidTicketDataError("Quota cannot be empty.")
            update_data["quota"] = quota.strip()

        if passenger_details is not None:
            if not passenger_details.strip():
                raise InvalidTicketDataError("Passenger details cannot be empty.")
            update_data["passenger_details"] = passenger_details.strip()

        if mobile is not None:
            update_data["mobile"] = mobile.strip() if mobile else None

        if email is not None:
            update_data["email"] = email.strip() if email else None

        if irctc_account_id is not None:
            if irctc_account_id:
                account = self._account_repo.get_by_id(irctc_account_id)
                if account is None or account.get("deleted_at") is not None:
                    raise TicketAccountNotFoundError(
                        f"IRCTC account {irctc_account_id} not found."
                    )
            update_data["irctc_account_id"] = irctc_account_id

        if status is not None:
            update_data["status"] = status

        if update_data:
            update_data["updated_at"] = None
            try:
                self._repo.update(ticket_id, update_data)
            except Exception as exc:
                raise TicketServiceError(f"Failed to update ticket: {exc}") from exc

    def delete_ticket(self, ticket_id: str) -> None:
        """Soft-delete a ticket profile.

        Sets deleted_at timestamp. Related booking_history records
        keep their ticket_id reference (ON DELETE SET NULL).

        Args:
            ticket_id: The ticket UUID.

        Raises:
            TicketNotFoundError: If ticket not found.
            TicketServiceError: If deletion fails.
        """
        ticket = self._repo.get_by_id(ticket_id)
        if ticket is None or ticket.get("deleted_at") is not None:
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")

        deleted_at = datetime.now(timezone.utc).isoformat()
        try:
            self._repo.soft_delete(ticket_id, deleted_at)
        except Exception as exc:
            raise TicketServiceError(f"Failed to delete ticket: {exc}") from exc
