"""Unit tests for MasterDataService and TicketDialog autocomplete integration.

Verifies:
- Offline station dataset loading (8,464 stations)
- Offline train dataset loading (4,204 trains)
- Station lookup by code (case-insensitive)
- Station search by name/code
- Station autocomplete formatting
- Train lookup by number
- Train search by name/number
- Train autocomplete formatting
- TicketDialog autocompletion and input cleaning (train numbers and station codes)
- TicketDialog proxy selector and travel options
- TicketDialog form validation and data extraction
"""

from __future__ import annotations

import unittest

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from bingo_linux.services.master_data_service import MasterDataService
from bingo_linux.ui.dialogs.ticket_dialog import TicketDialog


class TestMasterDataService(unittest.TestCase):
    """Tests for MasterDataService loading and query methods."""

    @classmethod
    def setUpClass(cls) -> None:
        """Initialize the master data service once for all test cases."""
        cls.service = MasterDataService()

    def test_datasets_loaded(self) -> None:
        """Verify stations and trains datasets are successfully loaded."""
        self.assertGreaterEqual(self.service.total_stations, 8000)
        self.assertGreaterEqual(self.service.total_trains, 4000)

    def test_station_lookup_by_code(self) -> None:
        """Lookup station by uppercase and lowercase code."""
        stn = self.service.get_station_by_code("NDLS")
        self.assertIsNotNone(stn)
        self.assertEqual(stn["code"], "NDLS")
        self.assertIn("DELHI", stn["name"].upper())

        # Case-insensitivity
        stn_lower = self.service.get_station_by_code("ndls")
        self.assertIsNotNone(stn_lower)
        self.assertEqual(stn_lower["code"], "NDLS")

    def test_station_lookup_invalid_code(self) -> None:
        """Invalid station code returns None."""
        stn = self.service.get_station_by_code("NONEXISTENT_XYZ")
        self.assertIsNone(stn)

    def test_station_search(self) -> None:
        """Station search returns matching results."""
        results = self.service.search_stations("HOWRAH", limit=10)
        self.assertTrue(len(results) > 0)
        codes = [s["code"] for s in results]
        self.assertIn("HWH", codes)

    def test_station_search_empty_query(self) -> None:
        """Empty query returns empty list."""
        self.assertEqual(self.service.search_stations(""), [])
        self.assertEqual(self.service.search_stations("   "), [])

    def test_station_completions(self) -> None:
        """Station completions formatted as 'CODE - NAME'."""
        completions = self.service.get_station_completions()
        self.assertGreaterEqual(len(completions), 8000)
        has_ndls = any("NDLS - " in c for c in completions)
        self.assertTrue(has_ndls)

    def test_train_lookup_by_number(self) -> None:
        """Lookup train info by train number."""
        train = self.service.get_train_by_number("12438")
        self.assertIsNotNone(train)
        self.assertEqual(train["number"], "12438")
        self.assertIn("RAJDHANI", train["name"].upper())

    def test_train_lookup_invalid_number(self) -> None:
        """Invalid train number returns None."""
        train = self.service.get_train_by_number("00000000")
        self.assertIsNone(train)

    def test_train_search(self) -> None:
        """Train search returns matching results by name or number."""
        results = self.service.search_trains("RAJDHANI", limit=10)
        self.assertTrue(len(results) > 0)
        for t in results:
            self.assertTrue("RAJDHANI" in t["name"].upper() or "RAJDHANI" in t["number"])

    def test_train_search_empty_query(self) -> None:
        """Empty train search query returns empty list."""
        self.assertEqual(self.service.search_trains(""), [])

    def test_train_completions(self) -> None:
        """Train completions formatted as 'NUMBER - NAME'."""
        completions = self.service.get_train_completions()
        self.assertGreaterEqual(len(completions), 4000)
        has_train = any("12438 - " in c for c in completions)
        self.assertTrue(has_train)


class TestTicketDialogIntegration(unittest.TestCase):
    """Tests for TicketDialog with autocomplete, proxies, and travel options."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create QApplication instance if not present."""
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])
        cls.master_data = MasterDataService()

    def setUp(self) -> None:
        """Setup sample accounts and proxies for dialog."""
        self.accounts = [
            {"id": "acct-1", "username": "user_alpha"},
            {"id": "acct-2", "username": "user_beta"},
        ]
        self.proxies = [
            {"id": "proxy-1", "name": "Proxy 1", "host": "10.0.0.1", "port": 8080, "type": "http"},
            {"id": "proxy-2", "name": "Proxy 2", "host": "10.0.0.2", "port": 1080, "type": "socks5"},
        ]
        self.dialog = TicketDialog(
            accounts=self.accounts,
            proxies=self.proxies,
            master_data_service=self.master_data,
        )

    def tearDown(self) -> None:
        """Close dialog."""
        self.dialog.close()

    def test_dialog_init(self) -> None:
        """Dialog initializes with all input widgets, combos, and checkboxes."""
        self.assertEqual(self.dialog.account_combo.count(), 3)  # None + 2 accounts
        self.assertEqual(self.dialog.proxy_combo.count(), 3)    # None + 2 proxies
        self.assertTrue(self.dialog.insurance_cb.isChecked())
        self.assertFalse(self.dialog.auto_upgrade_cb.isChecked())
        self.assertFalse(self.dialog.book_cnf_cb.isChecked())

    def test_autocomplete_train_number_cleaning(self) -> None:
        """Selecting or typing 'NUMBER - NAME' splits into number and fills name."""
        self.dialog.train_number_edit.setText("12438 - SECUNDERABAD RAJDHANI")
        self.assertEqual(self.dialog.train_number_edit.text(), "12438")
        self.assertIn("RAJDHANI", self.dialog.train_name_edit.text().upper())

    def test_autocomplete_train_lookup_from_number(self) -> None:
        """Typing valid train number auto-populates train name."""
        self.dialog.train_number_edit.setText("12438")
        self.assertEqual(self.dialog.train_number_edit.text(), "12438")
        self.assertIn("RAJDHANI", self.dialog.train_name_edit.text().upper())

    def test_autocomplete_station_cleaning(self) -> None:
        """Selecting or typing 'CODE - NAME' cleans station code to uppercase."""
        self.dialog.from_station_edit.setText("NDLS - NEW DELHI")
        self.assertEqual(self.dialog.from_station_edit.text(), "NDLS")
        self.assertIn("NEW DELHI", self.dialog.from_station_hint.text())

        self.dialog.to_station_edit.setText("HWH - HOWRAH JN")
        self.assertEqual(self.dialog.to_station_edit.text(), "HWH")
        self.assertIn("HOWRAH", self.dialog.to_station_hint.text())

    def test_dialog_validation_same_station(self) -> None:
        """Validation fails if from and to stations are the same."""
        self.dialog.train_number_edit.setText("12345")
        self.dialog.from_station_edit.setText("NDLS")
        self.dialog.to_station_edit.setText("NDLS")
        self.dialog.passenger_details_edit.setPlainText('[{"name": "Passenger"}]')

        error = self.dialog._validate()
        self.assertIsNotNone(error)
        self.assertIn("cannot be the same", error)

    def test_dialog_validation_invalid_json(self) -> None:
        """Validation fails if passenger details is not valid JSON."""
        self.dialog.train_number_edit.setText("12345")
        self.dialog.from_station_edit.setText("NDLS")
        self.dialog.to_station_edit.setText("HWH")
        self.dialog.passenger_details_edit.setPlainText('invalid json string')

        error = self.dialog._validate()
        self.assertIsNotNone(error)
        self.assertIn("valid JSON", error)

    def test_dialog_get_ticket_data(self) -> None:
        """Valid form values are correctly packaged in ticket data dict."""
        self.dialog.train_number_edit.setText("12438")
        self.dialog.from_station_edit.setText("NZM - HAZRAT NIZAMUDDIN")
        self.dialog.to_station_edit.setText("SC - SECUNDERABAD")
        self.dialog.journey_date_edit.setDate(QDate(2026, 12, 15))
        self.dialog.class_combo.setCurrentText("3A")
        self.dialog.quota_combo.setCurrentText("Tatkal")
        self.dialog.passenger_details_edit.setPlainText('[{"name": "Test Passenger", "age": 32, "gender": "M"}]')
        self.dialog.mobile_edit.setText("9876543210")
        self.dialog.email_edit.setText("test@example.com")
        self.dialog.account_combo.setCurrentIndex(1)  # acct-1
        self.dialog.proxy_combo.setCurrentIndex(1)    # proxy-1
        self.dialog.auto_upgrade_cb.setChecked(True)
        self.dialog.book_cnf_cb.setChecked(True)
        self.dialog.insurance_cb.setChecked(True)

        data = self.dialog.get_ticket_data()
        self.assertEqual(data["train_number"], "12438")
        self.assertIn("RAJDHANI", data["train_name"].upper())
        self.assertEqual(data["from_station"], "NZM")
        self.assertEqual(data["to_station"], "SC")
        self.assertEqual(data["journey_date"], "2026-12-15")
        self.assertEqual(data["class"], "3A")
        self.assertEqual(data["quota"], "Tatkal")
        self.assertEqual(data["irctc_account_id"], "acct-1")
        self.assertEqual(data["proxy_id"], "proxy-1")
        self.assertTrue(data["auto_upgrade"])
        self.assertTrue(data["book_only_if_cnf"])
        self.assertTrue(data["insurance"])
        self.assertEqual(data["status"], "draft")

    def test_load_existing_ticket(self) -> None:
        """Edit mode loads ticket, options, and populates train name and hints."""
        existing = {
            "id": "tkt-123",
            "train_number": "12438",
            "from_station": "NDLS",
            "to_station": "HWH",
            "journey_date": "2026-12-20",
            "class": "2A",
            "quota": "General",
            "passenger_details": '[{"name": "Existing Pax", "age": 45}]',
            "irctc_account_id": "acct-2",
            "proxy_id": "proxy-2",
            "auto_upgrade": True,
            "book_only_if_cnf": False,
            "insurance": False,
            "status": "active",
        }
        edit_dialog = TicketDialog(
            accounts=self.accounts,
            proxies=self.proxies,
            ticket=existing,
            master_data_service=self.master_data,
        )
        self.assertEqual(edit_dialog.train_number_edit.text(), "12438")
        self.assertIn("RAJDHANI", edit_dialog.train_name_edit.text().upper())
        self.assertEqual(edit_dialog.from_station_edit.text(), "NDLS")
        self.assertIn("NEW DELHI", edit_dialog.from_station_hint.text().upper())
        self.assertEqual(edit_dialog.to_station_edit.text(), "HWH")
        self.assertIn("HOWRAH", edit_dialog.to_station_hint.text().upper())
        self.assertEqual(edit_dialog.class_combo.currentText(), "2A")
        self.assertEqual(edit_dialog.quota_combo.currentText(), "General")
        self.assertEqual(edit_dialog.account_combo.currentData(), "acct-2")
        self.assertEqual(edit_dialog.proxy_combo.currentData(), "proxy-2")
        self.assertTrue(edit_dialog.auto_upgrade_cb.isChecked())
        self.assertFalse(edit_dialog.book_cnf_cb.isChecked())
        self.assertFalse(edit_dialog.insurance_cb.isChecked())
        self.assertEqual(edit_dialog.status_combo.currentText(), "active")
        edit_dialog.close()


if __name__ == "__main__":
    unittest.main()
