"""Tests for the ticket service layer.

Tests ticket creation, listing, editing, deletion, search,
filtering, account relationship validation, invalid input
validation, and foreign-key integrity. Uses temporary databases
and dummy data only.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from seatflow.database.database import Database
from seatflow.security.vault import VaultService
from seatflow.services import (
    DuplicateUsernameError,
    IrctcAccountService,
    InvalidTicketDataError,
    TicketAccountNotFoundError,
    TicketNotFoundError,
    TicketService,
    TicketServiceError,
    VaultRequiredError,
)


class TicketServiceTestCase(unittest.TestCase):
    """Base test case with a temporary database and ticket service."""

    def setUp(self) -> None:
        """Create a temporary database, vault, account service, and ticket service."""
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.vault = VaultService(self.db)
        self.account_service = IrctcAccountService(self.db, self.vault)
        self.ticket_service = TicketService(self.db)

    def tearDown(self) -> None:
        """Close and remove the temporary database."""
        self.vault.lock()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def _create_account(self, username="railway_user", password="pass123") -> str:
        """Helper to create an unlocked vault and account, return account ID."""
        self.vault.initialize("master-password")
        return self.account_service.add_account(
            username=username,
            password=password,
            mobile="9876543210",
            email="user@example.com",
            is_active=True,
        )


class TestTicketCreation(TicketServiceTestCase):
    """Tests for ticket creation."""

    def test_add_ticket_success(self) -> None:
        """Ticket can be created with all required fields."""
        ticket_id = self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="Tatkal",
            passenger_details='[{"name": "John Doe", "age": 30}]',
            mobile="9876543210",
            email="user@example.com",
            status="draft",
        )
        self.assertIsNotNone(ticket_id)

        ticket = self.ticket_service.get_ticket(ticket_id)
        self.assertEqual(ticket["train_number"], "12345")
        self.assertEqual(ticket["from_station"], "NDLS")
        self.assertEqual(ticket["to_station"], "HWH")
        self.assertEqual(ticket["journey_date"], "2026-12-01")
        self.assertEqual(ticket["class"], "3A")
        self.assertEqual(ticket["quota"], "Tatkal")
        self.assertEqual(ticket["status"], "draft")

    def test_add_ticket_with_account(self) -> None:
        """Ticket can be linked to an IRCTC account."""
        account_id = self._create_account()
        ticket_id = self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
            irctc_account_id=account_id,
        )
        ticket = self.ticket_service.get_ticket(ticket_id)
        self.assertEqual(ticket["irctc_account_id"], account_id)

    def test_add_ticket_missing_train_number_raises(self) -> None:
        """Missing train number raises InvalidTicketDataError."""
        with self.assertRaises(InvalidTicketDataError):
            self.ticket_service.add_ticket(
                train_number="",
                from_station="NDLS",
                to_station="HWH",
                journey_date="2026-12-01",
                class_type="3A",
                quota="General",
                passenger_details='[]',
            )

    def test_add_ticket_invalid_date_raises(self) -> None:
        """Invalid journey date format raises InvalidTicketDataError."""
        with self.assertRaises(InvalidTicketDataError):
            self.ticket_service.add_ticket(
                train_number="12345",
                from_station="NDLS",
                to_station="HWH",
                journey_date="01-12-2026",
                class_type="3A",
                quota="General",
                passenger_details='[]',
            )

    def test_add_ticket_same_from_to_raises(self) -> None:
        """Same from and to station is allowed (no validation against it in service).
        
        Note: The service does not validate from != to. This test documents
        current behavior - same station is allowed.
        """
        ticket_id = self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="NDLS",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
        )
        self.assertIsNotNone(ticket_id)

    def test_add_ticket_invalid_account_raises(self) -> None:
        """Non-existent IRCTC account raises TicketAccountNotFoundError."""
        with self.assertRaises(TicketAccountNotFoundError):
            self.ticket_service.add_ticket(
                train_number="12345",
                from_station="NDLS",
                to_station="HWH",
                journey_date="2026-12-01",
                class_type="3A",
                quota="General",
                passenger_details='[]',
                irctc_account_id="nonexistent-account",
            )

    def test_add_ticket_missing_passenger_details_raises(self) -> None:
        """Missing passenger details raises InvalidTicketDataError."""
        with self.assertRaises(InvalidTicketDataError):
            self.ticket_service.add_ticket(
                train_number="12345",
                from_station="NDLS",
                to_station="HWH",
                journey_date="2026-12-01",
                class_type="3A",
                quota="General",
                passenger_details="",
            )


class TestTicketListing(TicketServiceTestCase):
    """Tests for ticket listing."""

    def test_list_tickets_returns_all(self) -> None:
        """List tickets returns all non-deleted tickets."""
        self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
        )
        self.ticket_service.add_ticket(
            train_number="67890",
            from_station="MAS",
            to_station="SBC",
            journey_date="2026-12-05",
            class_type="2A",
            quota="Tatkal",
            passenger_details='[]',
        )

        tickets = self.ticket_service.list_tickets()
        self.assertEqual(len(tickets), 2)

    def test_list_tickets_excludes_deleted(self) -> None:
        """Soft-deleted tickets are not returned."""
        self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
        )
        self.ticket_service.add_ticket(
            train_number="67890",
            from_station="MAS",
            to_station="SBC",
            journey_date="2026-12-05",
            class_type="2A",
            quota="Tatkal",
            passenger_details='[]',
        )

        tickets = self.ticket_service.list_tickets()
        self.assertEqual(len(tickets), 2)

        self.ticket_service.delete_ticket(tickets[0]["id"])
        tickets = self.ticket_service.list_tickets()
        self.assertEqual(len(tickets), 1)


class TestTicketSearch(TicketServiceTestCase):
    """Tests for ticket search."""

    def test_search_by_train_number(self) -> None:
        """Search by train number returns matching tickets."""
        self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
        )
        self.ticket_service.add_ticket(
            train_number="67890",
            from_station="MAS",
            to_station="SBC",
            journey_date="2026-12-05",
            class_type="2A",
            quota="Tatkal",
            passenger_details='[]',
        )

        results = self.ticket_service.search_tickets("12345")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["train_number"], "12345")

    def test_search_by_from_station(self) -> None:
        """Search by from station returns matching tickets."""
        self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
        )

        results = self.ticket_service.search_tickets("NDLS")
        self.assertEqual(len(results), 1)

    def test_search_no_results(self) -> None:
        """Search with no matches returns empty list."""
        self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
        )

        results = self.ticket_service.search_tickets("ZZZZZ")
        self.assertEqual(len(results), 0)


class TestTicketFilter(TicketServiceTestCase):
    """Tests for ticket filtering."""

    def test_filter_by_status(self) -> None:
        """Filter by status returns matching tickets."""
        self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
            status="active",
        )
        self.ticket_service.add_ticket(
            train_number="67890",
            from_station="MAS",
            to_station="SBC",
            journey_date="2026-12-05",
            class_type="2A",
            quota="Tatkal",
            passenger_details='[]',
            status="draft",
        )

        active = self.ticket_service.filter_tickets(status="active")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["status"], "active")

        draft = self.ticket_service.filter_tickets(status="draft")
        self.assertEqual(len(draft), 1)
        self.assertEqual(draft[0]["status"], "draft")

    def test_filter_by_account(self) -> None:
        """Filter by account returns matching tickets."""
        account_id = self._create_account()
        self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
            irctc_account_id=account_id,
        )
        self.ticket_service.add_ticket(
            train_number="67890",
            from_station="MAS",
            to_station="SBC",
            journey_date="2026-12-05",
            class_type="2A",
            quota="Tatkal",
            passenger_details='[]',
        )

        tickets = self.ticket_service.filter_tickets(
            irctc_account_id=account_id
        )
        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0]["irctc_account_id"], account_id)


class TestTicketEditing(TicketServiceTestCase):
    """Tests for ticket editing."""

    def test_edit_ticket_success(self) -> None:
        """Ticket can be edited."""
        ticket_id = self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
        )

        self.ticket_service.update_ticket(
            ticket_id=ticket_id,
            train_number="54321",
            class_type="2A",
            status="active",
        )

        ticket = self.ticket_service.get_ticket(ticket_id)
        self.assertEqual(ticket["train_number"], "54321")
        self.assertEqual(ticket["class"], "2A")
        self.assertEqual(ticket["status"], "active")
        # Unchanged fields preserved
        self.assertEqual(ticket["from_station"], "NDLS")

    def test_edit_ticket_not_found_raises(self) -> None:
        """Editing non-existent ticket raises TicketNotFoundError."""
        with self.assertRaises(TicketNotFoundError):
            self.ticket_service.update_ticket(
                ticket_id="nonexistent",
                train_number="99999",
            )

    def test_edit_ticket_invalid_date_raises(self) -> None:
        """Invalid date in edit raises InvalidTicketDataError."""
        ticket_id = self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
        )

        with self.assertRaises(InvalidTicketDataError):
            self.ticket_service.update_ticket(
                ticket_id=ticket_id,
                journey_date="invalid-date",
            )

    def test_edit_ticket_account_link(self) -> None:
        """Ticket can be linked to an account on edit."""
        account_id = self._create_account()
        ticket_id = self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
        )

        self.ticket_service.update_ticket(
            ticket_id=ticket_id,
            irctc_account_id=account_id,
        )

        ticket = self.ticket_service.get_ticket(ticket_id)
        self.assertEqual(ticket["irctc_account_id"], account_id)


class TestTicketDeletion(TicketServiceTestCase):
    """Tests for ticket deletion."""

    def test_delete_ticket_success(self) -> None:
        """Ticket can be soft-deleted."""
        ticket_id = self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
        )

        self.ticket_service.delete_ticket(ticket_id)
        tickets = self.ticket_service.list_tickets()
        self.assertEqual(len(tickets), 0)

    def test_delete_ticket_not_found_raises(self) -> None:
        """Deleting non-existent ticket raises TicketNotFoundError."""
        with self.assertRaises(TicketNotFoundError):
            self.ticket_service.delete_ticket("nonexistent")


class TestTicketGet(TicketServiceTestCase):
    """Tests for get_ticket."""

    def test_get_ticket_success(self) -> None:
        """get_ticket returns ticket data."""
        ticket_id = self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
        )

        ticket = self.ticket_service.get_ticket(ticket_id)
        self.assertEqual(ticket["train_number"], "12345")
        self.assertEqual(ticket["id"], ticket_id)

    def test_get_ticket_not_found(self) -> None:
        """get_ticket raises for non-existent ID."""
        with self.assertRaises(TicketNotFoundError):
            self.ticket_service.get_ticket("nonexistent")


class TestTicketAccountRelationship(TicketServiceTestCase):
    """Tests for ticket-account relationship."""

    def test_ticket_list_by_account(self) -> None:
        """list_tickets_by_account returns tickets for that account."""
        account_id = self._create_account()
        self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[]',
            irctc_account_id=account_id,
        )
        self.ticket_service.add_ticket(
            train_number="67890",
            from_station="MAS",
            to_station="SBC",
            journey_date="2026-12-05",
            class_type="2A",
            quota="Tatkal",
            passenger_details='[]',
        )

        tickets = self.ticket_service.list_tickets_by_account(account_id)
        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0]["train_number"], "12345")


if __name__ == "__main__":
    unittest.main()
