"""Tests for Application controller and new UI window architecture."""

from __future__ import annotations

import os
import tempfile
import unittest

from PySide6.QtWidgets import QApplication

from seatflow.app.application import Application
from seatflow.database.database import Database

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class ApplicationUITestCase(unittest.TestCase):
    """Test case for Application controller and floating window architecture."""

    def setUp(self) -> None:
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)

        self.controller = Application()
        # Point to temporary database
        self.controller._db = Database(db_path=self.tmp_path)
        self.controller._db.initialize_schema()

    def tearDown(self) -> None:
        self.controller.shutdown()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def test_window_creation_and_lifecycle(self) -> None:
        """Verify all floating windows are initialized and wired."""
        main_win = self.controller.create_main_window()
        self.assertIsNotNone(main_win)
        self.assertIsNotNone(self.controller._tickets_window)
        self.assertIsNotNone(self.controller._book_window)
        self.assertIsNotNone(self.controller._accounts_window)
        self.assertIsNotNone(self.controller._payment_window)
        self.assertIsNotNone(self.controller._settings_window)
        self.assertIsNotNone(self.controller._proxies_window)
        self.assertIsNotNone(self.controller._history_window)
        self.assertIsNotNone(self.controller._backup_restore_window)

    def test_toolbar_action_routing(self) -> None:
        """Verify toolbar actions display appropriate windows."""
        self.controller.create_main_window()

        # Action: book
        self.controller._on_action_clicked("book")
        self.assertTrue(self.controller._book_window.isVisible())
        self.controller._book_window.hide()

        # Action: accounts (Profile)
        self.controller._on_action_clicked("accounts")
        self.assertTrue(self.controller._accounts_window.isVisible())
        self.controller._accounts_window.hide()

        # Action: payment
        self.controller._on_action_clicked("payment")
        self.assertTrue(self.controller._payment_window.isVisible())
        self.controller._payment_window.hide()

        # Action: tickets
        self.controller._on_action_clicked("tickets")
        self.assertTrue(self.controller._tickets_window.isVisible())
        self.controller._tickets_window.hide()

    def test_ticket_save_and_open_pair(self) -> None:
        """Verify ticket saving and opening floating pair panel."""
        self.controller.create_main_window()

        sample_ticket = {
            "from_station": "HWH",
            "to_station": "SC",
            "train_number": "12704",
            "journey_date": "2026-12-05",
            "class": "3A",
            "quota": "TQ",
            "passenger_details": '[{"name": "S. Singh", "age": 32, "gender": "Male"}]',
        }
        self.controller._on_save_ticket(sample_ticket)

        tickets = self.controller._ticket_service.list_tickets()
        self.assertEqual(len(tickets), 1)
        ticket_id = tickets[0]["id"]

        # Open floating pair card
        self.controller._on_open_ticket(ticket_id, 0)
        pair_key = f"{ticket_id}_0"
        self.assertIn(pair_key, self.controller._pair_windows)
        pair_win = self.controller._pair_windows[pair_key]
        self.assertTrue(pair_win.isVisible())
        pair_win.hide()


if __name__ == "__main__":
    unittest.main()
