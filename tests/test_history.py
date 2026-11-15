"""Tests for the journey history service layer.

Tests history creation, listing, date filtering, search, removal,
remove-all behavior, invalid input validation, and foreign-key
integrity. Uses temporary databases and dummy data only.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import os
import tempfile
import unittest

from seatflow.database.database import Database
from seatflow.security.vault import VaultService
from seatflow.services import (
    HistoryNotFoundError,
    HistoryService,
    HistoryServiceError,
    InvalidHistoryDataError,
    IrctcAccountService,
    VaultRequiredError,
)


class HistoryServiceTestCase(unittest.TestCase):
    """Base test case with a temporary database and history service."""

    def setUp(self) -> None:
        """Create a temporary database, vault, account service, and history service."""
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.vault = VaultService(self.db)
        self.account_service = IrctcAccountService(self.db, self.vault)
        self.history_service = HistoryService(self.db)

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


class TestHistoryCreation(HistoryServiceTestCase):
    """Tests for history creation."""

    def test_add_history_success(self) -> None:
        """History record can be created with all required fields."""
        history_id = self.history_service.add_history(
            pnr_number="ABC12345",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=1200.0,
        )
        self.assertIsNotNone(history_id)

        record = self.history_service.get_history(history_id)
        self.assertEqual(record["pnr_number"], "ABC12345")
        self.assertEqual(record["train_number"], "12345")
        self.assertEqual(record["journey_date"], "2026-12-01")
        self.assertEqual(record["booking_status"], "success")
        self.assertEqual(record["fare_amount"], 1200.0)

    def test_add_history_with_account(self) -> None:
        """History record can be linked to an IRCTC account."""
        account_id = self._create_account()
        history_id = self.history_service.add_history(
            pnr_number="XYZ78901",
            train_number="67890",
            journey_date="2026-12-05",
            booking_status="pending",
            fare_amount=850.0,
            irctc_account_id=account_id,
        )
        record = self.history_service.get_history(history_id)
        self.assertEqual(record["irctc_account_id"], account_id)

    def test_add_history_missing_pnr_raises(self) -> None:
        """Missing PNR number raises InvalidHistoryDataError."""
        with self.assertRaises(InvalidHistoryDataError):
            self.history_service.add_history(
                pnr_number="",
                train_number="12345",
                journey_date="2026-12-01",
                booking_status="success",
                fare_amount=100.0,
            )

    def test_add_history_invalid_date_raises(self) -> None:
        """Invalid journey date format raises InvalidHistoryDataError."""
        with self.assertRaises(InvalidHistoryDataError):
            self.history_service.add_history(
                pnr_number="PNR123",
                train_number="12345",
                journey_date="01-12-2026",
                booking_status="success",
                fare_amount=100.0,
            )

    def test_add_history_invalid_status_raises(self) -> None:
        """Invalid booking status raises InvalidHistoryDataError."""
        with self.assertRaises(InvalidHistoryDataError):
            self.history_service.add_history(
                pnr_number="PNR123",
                train_number="12345",
                journey_date="2026-12-01",
                booking_status="unknown",
                fare_amount=100.0,
            )

    def test_add_history_invalid_account_raises(self) -> None:
        """Non-existent IRCTC account raises IrctcAccountNotFoundError."""
        from seatflow.services import IrctcAccountNotFoundError

        with self.assertRaises(IrctcAccountNotFoundError):
            self.history_service.add_history(
                pnr_number="PNR123",
                train_number="12345",
                journey_date="2026-12-01",
                booking_status="success",
                fare_amount=100.0,
                irctc_account_id="nonexistent-account",
            )


class TestHistoryListing(HistoryServiceTestCase):
    """Tests for history listing."""

    def test_list_history_returns_all(self) -> None:
        """List history returns all non-deleted records."""
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=100.0,
        )
        self.history_service.add_history(
            pnr_number="PNR002",
            train_number="67890",
            journey_date="2026-12-05",
            booking_status="failed",
            fare_amount=200.0,
        )

        records = self.history_service.list_history()
        self.assertEqual(len(records), 2)

    def test_list_history_excludes_deleted(self) -> None:
        """Soft-deleted records are not returned."""
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=100.0,
        )
        self.history_service.add_history(
            pnr_number="PNR002",
            train_number="67890",
            journey_date="2026-12-05",
            booking_status="failed",
            fare_amount=200.0,
        )

        records = self.history_service.list_history()
        self.assertEqual(len(records), 2)

        self.history_service.remove_history(records[0]["id"])
        records = self.history_service.list_history()
        self.assertEqual(len(records), 1)


class TestHistoryDateFilters(HistoryServiceTestCase):
    """Tests for date-based filtering."""

    def test_filter_all(self) -> None:
        """Filter 'all' returns all non-deleted records."""
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=100.0,
        )
        self.history_service.add_history(
            pnr_number="PNR002",
            train_number="67890",
            journey_date="2026-12-05",
            booking_status="failed",
            fare_amount=200.0,
        )

        records = self.history_service.filter_history(filter_key="all")
        self.assertEqual(len(records), 2)

    def test_filter_upcoming(self) -> None:
        """Filter 'upcoming' returns records with journey_date >= today."""
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=100.0,
        )
        self.history_service.add_history(
            pnr_number="PNR002",
            train_number="67890",
            journey_date="2020-01-01",
            booking_status="success",
            fare_amount=200.0,
        )

        records = self.history_service.filter_history(filter_key="upcoming")
        # All records with journey_date >= today
        self.assertTrue(len(records) >= 1)
        for record in records:
            self.assertGreaterEqual(record["journey_date"], date.today().isoformat())

    def test_filter_past(self) -> None:
        """Filter 'past' returns records with journey_date < today."""
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2020-01-01",
            booking_status="success",
            fare_amount=100.0,
        )
        self.history_service.add_history(
            pnr_number="PNR002",
            train_number="67890",
            journey_date="2030-12-01",
            booking_status="success",
            fare_amount=200.0,
        )

        records = self.history_service.filter_history(filter_key="past")
        self.assertTrue(len(records) >= 1)
        for record in records:
            self.assertLess(record["journey_date"], date.today().isoformat())

    def test_filter_today(self) -> None:
        """Filter 'today' returns records with journey_date == today."""
        today = date.today().isoformat()
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date=today,
            booking_status="success",
            fare_amount=100.0,
        )
        self.history_service.add_history(
            pnr_number="PNR002",
            train_number="67890",
            journey_date="2026-12-05",
            booking_status="failed",
            fare_amount=200.0,
        )

        records = self.history_service.filter_history(filter_key="today")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["journey_date"], today)

    def test_filter_7d(self) -> None:
        """Filter '7d' returns records within the next 7 days."""
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date=date.today().isoformat(),
            booking_status="success",
            fare_amount=100.0,
        )
        self.history_service.add_history(
            pnr_number="PNR002",
            train_number="67890",
            journey_date=(date.today() + timedelta(days=3)).isoformat(),
            booking_status="success",
            fare_amount=200.0,
        )
        self.history_service.add_history(
            pnr_number="PNR003",
            train_number="11111",
            journey_date=(date.today() + timedelta(days=10)).isoformat(),
            booking_status="success",
            fare_amount=300.0,
        )

        records = self.history_service.filter_history(filter_key="7d")
        self.assertEqual(len(records), 2)

    def test_filter_30d(self) -> None:
        """Filter '30d' returns records within the next 30 days."""
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date=date.today().isoformat(),
            booking_status="success",
            fare_amount=100.0,
        )
        self.history_service.add_history(
            pnr_number="PNR002",
            train_number="67890",
            journey_date=(date.today() + timedelta(days=15)).isoformat(),
            booking_status="success",
            fare_amount=200.0,
        )
        self.history_service.add_history(
            pnr_number="PNR003",
            train_number="11111",
            journey_date=(date.today() + timedelta(days=45)).isoformat(),
            booking_status="success",
            fare_amount=300.0,
        )

        records = self.history_service.filter_history(filter_key="30d")
        self.assertEqual(len(records), 2)

    def test_filter_month(self) -> None:
        """Filter 'month' returns records in the current month."""
        today = date.today()
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date=today.isoformat(),
            booking_status="success",
            fare_amount=100.0,
        )
        # Record in a different month
        if today.month == 12:
            other_month = today.replace(year=today.year + 1, month=1, day=15)
        else:
            other_month = today.replace(month=today.month + 1, day=15)
        self.history_service.add_history(
            pnr_number="PNR002",
            train_number="67890",
            journey_date=other_month.isoformat(),
            booking_status="success",
            fare_amount=200.0,
        )

        records = self.history_service.filter_history(filter_key="month")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["journey_date"], today.isoformat())


class TestHistorySearch(HistoryServiceTestCase):
    """Tests for history search."""

    def test_search_by_pnr(self) -> None:
        """Search by PNR number returns matching records."""
        self.history_service.add_history(
            pnr_number="ABC12345",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=100.0,
        )
        self.history_service.add_history(
            pnr_number="XYZ78901",
            train_number="67890",
            journey_date="2026-12-05",
            booking_status="failed",
            fare_amount=200.0,
        )

        results = self.history_service.search_history("ABC12345")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["pnr_number"], "ABC12345")

    def test_search_by_train_number(self) -> None:
        """Search by train number returns matching records."""
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=100.0,
        )

        results = self.history_service.search_history("12345")
        self.assertEqual(len(results), 1)

    def test_search_no_results(self) -> None:
        """Search with no matches returns empty list."""
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=100.0,
        )

        results = self.history_service.search_history("ZZZZZ")
        self.assertEqual(len(results), 0)


class TestHistoryFilterByStatus(HistoryServiceTestCase):
    """Tests for status filtering."""

    def test_filter_by_status(self) -> None:
        """Filter by status returns matching records."""
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=100.0,
        )
        self.history_service.add_history(
            pnr_number="PNR002",
            train_number="67890",
            journey_date="2026-12-05",
            booking_status="failed",
            fare_amount=200.0,
        )

        success = self.history_service.filter_by_status("success")
        self.assertEqual(len(success), 1)
        self.assertEqual(success[0]["booking_status"], "success")

        failed = self.history_service.filter_by_status("failed")
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["booking_status"], "failed")


class TestHistoryRemoval(HistoryServiceTestCase):
    """Tests for history removal."""

    def test_remove_history_success(self) -> None:
        """History record can be soft-deleted."""
        history_id = self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=100.0,
        )

        self.history_service.remove_history(history_id)
        records = self.history_service.list_history()
        self.assertEqual(len(records), 0)

    def test_remove_history_not_found_raises(self) -> None:
        """Removing non-existent record raises HistoryNotFoundError."""
        with self.assertRaises(HistoryNotFoundError):
            self.history_service.remove_history("nonexistent")

    def test_remove_all_history(self) -> None:
        """All history records can be soft-deleted."""
        self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=100.0,
        )
        self.history_service.add_history(
            pnr_number="PNR002",
            train_number="67890",
            journey_date="2026-12-05",
            booking_status="failed",
            fare_amount=200.0,
        )

        removed_count = self.history_service.remove_all_history()
        self.assertEqual(removed_count, 2)

        records = self.history_service.list_history()
        self.assertEqual(len(records), 0)

    def test_remove_all_history_empty(self) -> None:
        """Remove all on empty history returns 0."""
        removed_count = self.history_service.remove_all_history()
        self.assertEqual(removed_count, 0)


class TestHistoryGet(HistoryServiceTestCase):
    """Tests for get_history."""

    def test_get_history_success(self) -> None:
        """get_history returns record data."""
        history_id = self.history_service.add_history(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=100.0,
        )

        record = self.history_service.get_history(history_id)
        self.assertEqual(record["pnr_number"], "PNR001")
        self.assertEqual(record["id"], history_id)

    def test_get_history_not_found(self) -> None:
        """get_history raises for non-existent ID."""
        with self.assertRaises(HistoryNotFoundError):
            self.history_service.get_history("nonexistent")


class TestHistoryPendingFilter(HistoryServiceTestCase):
    """Tests for pending filter state."""

    def test_pending_filter_default_none(self) -> None:
        """Pending filter is None by default."""
        result = self.history_service.get_pending_filter()
        self.assertIsNone(result)

    def test_set_and_get_pending_filter(self) -> None:
        """Pending filter can be set and retrieved."""
        self.history_service.set_pending_filter("7d")
        result = self.history_service.get_pending_filter()
        self.assertEqual(result, "7d")

    def test_clear_pending_filter(self) -> None:
        """Pending filter can be cleared."""
        self.history_service.set_pending_filter("30d")
        self.history_service.clear_pending_filter()
        result = self.history_service.get_pending_filter()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
