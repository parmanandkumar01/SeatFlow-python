"""Tests for the PNR records service layer.

Tests PNR creation, listing, lookup by PNR number, search,
filtering by status, removal, remove-all behavior, invalid input
validation, and foreign-key integrity. Uses temporary databases
and dummy data only.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from bingo_linux.database.database import Database
from bingo_linux.security.vault import VaultService
from bingo_linux.services import (
    InvalidPnrDataError,
    PnrNotFoundError,
    PnrService,
    PnrServiceError,
    PNR_STATUS_BOOKED,
    PNR_STATUS_CANCELLED,
    PNR_STATUS_FAILED,
    PNR_STATUS_PENDING,
)


class PnrServiceTestCase(unittest.TestCase):
    """Base test case with a temporary database and PNR service."""

    def setUp(self) -> None:
        """Create a temporary database, vault, and PNR service for each test."""
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.vault = VaultService(self.db)
        self.vault.initialize("master-password")
        self.pnr_service = PnrService(self.db)

    def tearDown(self) -> None:
        """Close and remove the temporary database."""
        self.vault.lock()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)


class TestPnrCreation(PnrServiceTestCase):
    """Tests for PNR creation."""

    def test_add_pnr_success(self) -> None:
        """PNR record can be created with all required fields."""
        pnr_id = self.pnr_service.add_pnr(
            pnr_number="ABC1234567",
            train_number="12345",
            journey_date="2026-12-01",
            passenger_names='["John Doe", "Jane Doe"]',
            booking_status="booked",
            fare_amount=1200.0,
        )
        self.assertIsNotNone(pnr_id)

        record = self.pnr_service.get_pnr("ABC1234567")
        self.assertEqual(record["pnr_number"], "ABC1234567")
        self.assertEqual(record["train_number"], "12345")
        self.assertEqual(record["journey_date"], "2026-12-01")
        self.assertEqual(record["booking_status"], "booked")
        self.assertEqual(record["fare_amount"], 1200.0)

    def test_add_pnr_minimal_fields(self) -> None:
        """PNR record can be created with only required fields."""
        pnr_id = self.pnr_service.add_pnr(pnr_number="XYZ7890123")
        self.assertIsNotNone(pnr_id)

        record = self.pnr_service.get_pnr("XYZ7890123")
        self.assertEqual(record["pnr_number"], "XYZ7890123")
        self.assertIsNone(record["train_number"])
        self.assertIsNone(record["journey_date"])
        self.assertEqual(record["booking_status"], "booked")

    def test_add_pnr_missing_pnr_raises(self) -> None:
        """Missing PNR number raises InvalidPnrDataError."""
        with self.assertRaises(InvalidPnrDataError):
            self.pnr_service.add_pnr(pnr_number="")

    def test_add_pnr_non_alphanumeric_raises(self) -> None:
        """Non-alphanumeric PNR raises InvalidPnrDataError."""
        with self.assertRaises(InvalidPnrDataError):
            self.pnr_service.add_pnr(pnr_number="ABC-1234")

    def test_add_pnr_too_short_raises(self) -> None:
        """Too short PNR raises InvalidPnrDataError."""
        with self.assertRaises(InvalidPnrDataError):
            self.pnr_service.add_pnr(pnr_number="ABC12")

    def test_add_pnr_too_long_raises(self) -> None:
        """Too long PNR raises InvalidPnrDataError."""
        with self.assertRaises(InvalidPnrDataError):
            self.pnr_service.add_pnr(pnr_number="A" * 21)

    def test_add_pnr_invalid_date_raises(self) -> None:
        """Invalid journey date format raises InvalidPnrDataError."""
        with self.assertRaises(InvalidPnrDataError):
            self.pnr_service.add_pnr(
                pnr_number="PNR123456",
                journey_date="01-12-2026",
            )

    def test_add_pnr_invalid_status_raises(self) -> None:
        """Invalid booking status raises InvalidPnrDataError."""
        with self.assertRaises(InvalidPnrDataError):
            self.pnr_service.add_pnr(
                pnr_number="PNR123456",
                booking_status="unknown",
            )

    def test_add_pnr_duplicate_raises(self) -> None:
        """Duplicate PNR number raises InvalidPnrDataError."""
        self.pnr_service.add_pnr(pnr_number="DUP1234567")
        with self.assertRaises(InvalidPnrDataError):
            self.pnr_service.add_pnr(pnr_number="DUP1234567")


class TestPnrListing(PnrServiceTestCase):
    """Tests for PNR listing."""

    def test_list_pnrs_returns_all(self) -> None:
        """List PNRs returns all non-deleted records."""
        self.pnr_service.add_pnr(pnr_number="PNR001", train_number="12345")
        self.pnr_service.add_pnr(pnr_number="PNR002", train_number="67890")

        records = self.pnr_service.list_pnrs()
        self.assertEqual(len(records), 2)

    def test_list_pnrs_excludes_deleted(self) -> None:
        """Soft-deleted PNRs are not returned."""
        self.pnr_service.add_pnr(pnr_number="PNR001", train_number="12345")
        self.pnr_service.add_pnr(pnr_number="PNR002", train_number="67890")

        records = self.pnr_service.list_pnrs()
        self.assertEqual(len(records), 2)

        self.pnr_service.remove_pnr("PNR001")
        records = self.pnr_service.list_pnrs()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["pnr_number"], "PNR002")


class TestPnrLookup(PnrServiceTestCase):
    """Tests for PNR lookup by number."""

    def test_get_pnr_success(self) -> None:
        """get_pnr returns record data."""
        self.pnr_service.add_pnr(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="booked",
            fare_amount=100.0,
        )

        record = self.pnr_service.get_pnr("PNR001")
        self.assertEqual(record["pnr_number"], "PNR001")
        self.assertEqual(record["train_number"], "12345")
        self.assertEqual(record["booking_status"], "booked")

    def test_get_pnr_not_found(self) -> None:
        """get_pnr raises for non-existent PNR."""
        with self.assertRaises(PnrNotFoundError):
            self.pnr_service.get_pnr("NONEXISTENT")


class TestPnrExists(PnrServiceTestCase):
    """Tests for PNR existence check."""

    def test_pnr_exists_true(self) -> None:
        """pnr_exists returns True for existing PNR."""
        self.pnr_service.add_pnr(pnr_number="PNR001", train_number="12345")
        self.assertTrue(self.pnr_service.pnr_exists("PNR001"))

    def test_pnr_exists_false(self) -> None:
        """pnr_exists returns False for non-existent PNR."""
        self.assertFalse(self.pnr_service.pnr_exists("NONEXISTENT"))

    def test_pnr_exists_false_after_delete(self) -> None:
        """pnr_exists returns False after soft delete."""
        self.pnr_service.add_pnr(pnr_number="PNR001", train_number="12345")
        self.pnr_service.remove_pnr("PNR001")
        self.assertFalse(self.pnr_service.pnr_exists("PNR001"))


class TestPnrSearch(PnrServiceTestCase):
    """Tests for PNR search."""

    def test_search_by_pnr(self) -> None:
        """Search by PNR number returns matching records."""
        self.pnr_service.add_pnr(pnr_number="ABC12345", train_number="12345")
        self.pnr_service.add_pnr(pnr_number="XYZ78901", train_number="67890")

        results = self.pnr_service.search_pnrs("ABC12345")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["pnr_number"], "ABC12345")

    def test_search_by_train_number(self) -> None:
        """Search by train number returns matching records."""
        self.pnr_service.add_pnr(pnr_number="PNR001", train_number="12345")

        results = self.pnr_service.search_pnrs("12345")
        self.assertEqual(len(results), 1)

    def test_search_no_results(self) -> None:
        """Search with no matches returns empty list."""
        self.pnr_service.add_pnr(pnr_number="PNR001", train_number="12345")

        results = self.pnr_service.search_pnrs("ZZZZZ")
        self.assertEqual(len(results), 0)


class TestPnrFilterByStatus(PnrServiceTestCase):
    """Tests for status filtering."""

    def test_filter_by_status(self) -> None:
        """Filter by status returns matching records."""
        self.pnr_service.add_pnr(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="booked",
            fare_amount=100.0,
        )
        self.pnr_service.add_pnr(
            pnr_number="PNR002",
            train_number="67890",
            journey_date="2026-12-05",
            booking_status="failed",
            fare_amount=200.0,
        )

        booked = self.pnr_service.filter_by_status("booked")
        self.assertEqual(len(booked), 1)
        self.assertEqual(booked[0]["booking_status"], "booked")

        failed = self.pnr_service.filter_by_status("failed")
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["booking_status"], "failed")


class TestPnrRemoval(PnrServiceTestCase):
    """Tests for PNR removal."""

    def test_remove_pnr_success(self) -> None:
        """PNR record can be soft-deleted."""
        self.pnr_service.add_pnr(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="booked",
            fare_amount=100.0,
        )

        self.pnr_service.remove_pnr("PNR001")
        records = self.pnr_service.list_pnrs()
        self.assertEqual(len(records), 0)

    def test_remove_pnr_not_found_raises(self) -> None:
        """Removing non-existent PNR raises PnrNotFoundError."""
        with self.assertRaises(PnrNotFoundError):
            self.pnr_service.remove_pnr("nonexistent")

    def test_remove_all_pnrs(self) -> None:
        """All PNR records can be soft-deleted."""
        self.pnr_service.add_pnr(
            pnr_number="PNR001",
            train_number="12345",
            journey_date="2026-12-01",
            booking_status="booked",
            fare_amount=100.0,
        )
        self.pnr_service.add_pnr(
            pnr_number="PNR002",
            train_number="67890",
            journey_date="2026-12-05",
            booking_status="failed",
            fare_amount=200.0,
        )

        removed_count = self.pnr_service.remove_all_pnrs()
        self.assertEqual(removed_count, 2)

        records = self.pnr_service.list_pnrs()
        self.assertEqual(len(records), 0)

    def test_remove_all_pnrs_empty(self) -> None:
        """Remove all on empty PNRs returns 0."""
        removed_count = self.pnr_service.remove_all_pnrs()
        self.assertEqual(removed_count, 0)


class TestPnrDisplayHelpers(PnrServiceTestCase):
    """Tests for PNR display helper methods."""

    def test_get_pnr_short(self) -> None:
        """get_pnr_short returns last 6 digits."""
        self.assertEqual(self.pnr_service.get_pnr_short("ABC1234567"), "234567")
        self.assertEqual(self.pnr_service.get_pnr_short("PNR123"), "PNR123")
        self.assertEqual(self.pnr_service.get_pnr_short("AB12"), "AB12")
        self.assertEqual(self.pnr_service.get_pnr_short(""), "—")

    def test_format_fare_amount(self) -> None:
        """format_fare_amount formats fare correctly."""
        self.assertEqual(self.pnr_service.format_fare_amount(1200.0), "₹1200.0")
        self.assertEqual(self.pnr_service.format_fare_amount(None), "—")

    def test_decode_passenger_names(self) -> None:
        """decode_passenger_names parses JSON array."""
        self.assertEqual(
            self.pnr_service.decode_passenger_names('["John Doe", "Jane Doe"]'),
            ["John Doe", "Jane Doe"],
        )
        self.assertEqual(self.pnr_service.decode_passenger_names("[]"), [])
        self.assertEqual(self.pnr_service.decode_passenger_names(None), [])
        self.assertEqual(self.pnr_service.decode_passenger_names(""), [])
        self.assertEqual(self.pnr_service.decode_passenger_names("not json"), [])


if __name__ == "__main__":
    unittest.main()
