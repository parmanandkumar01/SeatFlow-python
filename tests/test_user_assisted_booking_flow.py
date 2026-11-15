"""End-to-end tests for the legitimate user-assisted booking flow & handoff pipeline.

Covers:
- TicketPanelWindow state-driven status banner / availability pill updates.
- Tatkal countdown timer (10:00 AC / 11:00 Non-AC) with live clock ticks.
- Worker-button launch -> IRCTC browser handoff + clipboard form assistance.
- Manual 2FA -> CAPTCHA -> fare -> payment state transitions via dialogs.
- PNR completion: BookingHistory + PnrService persistence, ERS HTML render,
  and panel status flipping to "BOOKED".
- Cancellation and failure transitions.

All checkpoints are user-driven: no CAPTCHA solving, no credential storage,
no browser automation, and no network I/O. webbrowser.open and the modal
dialogs are patched so the flow runs headless.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QGuiApplication

from bingo_linux.app.application import Application
from bingo_linux.database.database import Database
from bingo_linux.services import (
    BookingState,
    BookingWorkflowService,
    HistoryService,
    IrctcAccountService,
    PnrService,
    TicketService,
)
from bingo_linux.ui.ticket_panel_window import TicketPanelWindow

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class _FlowHarness:
    """Wires an Application controller for one ticket pair."""

    def __init__(self) -> None:
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()

        self.controller = Application()
        self.controller._db = self.db
        self.controller.create_main_window()

        self.account_id = self.controller._account_service.add_account(
            username="rail_user",
            password="pass123",
            mobile="9876543210",
            email="u@example.com",
            is_active=True,
        )
        self.ticket_id = self.controller._ticket_service.add_ticket(
            train_number="12704",
            from_station="HWH",
            to_station="SC",
            journey_date="2026-12-05",
            class_type="3A",
            quota="TQ",
            passenger_details=json.dumps(
                [{"name": "S. Singh", "age": 32, "gender": "Male", "berth": "Lower"}]
            ),
            irctc_account_id=self.account_id,
        )
        self.controller._on_open_ticket(self.ticket_id, 0)
        pair_key = f"{self.ticket_id}_0"
        self.pair_win = self.controller._pair_windows[pair_key]

        self.ers_dir = tempfile.mkdtemp()
        self.controller._ers_output_dir = self.ers_dir

        self.browser_urls: list[str] = []

    def close(self) -> None:
        self.controller.shutdown()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)


class TestTicketPanelStateUpdates(unittest.TestCase):
    """Unit tests for TicketPanelWindow booking-state reflection."""

    def setUp(self) -> None:
        self.win = TicketPanelWindow(
            ticket={
                "id": "ticket-1",
                "train_number": "12704",
                "from_station": "HWH",
                "to_station": "SC",
                "journey_date": "2026-12-05",
                "class": "3A",
                "quota": "TQ",
                "passenger_details": '[]',
            },
            pair_index=0,
        )

    def tearDown(self) -> None:
        self.win.close()

    def test_set_status_no_longer_crashes(self) -> None:
        # Regression: set_status previously referenced non-existent widgets.
        self.win.set_status("READY · STANDBY", "#0284c7")
        self.win.set_status("BOOKED", "#16a34a")
        self.assertEqual(self.win.banner_text.text(), "BOOKED")

    def test_set_booking_state_transitions(self) -> None:
        self.win.set_booking_state(BookingState.IDLE)
        self.assertEqual(self.win.banner_text.text(), "READY · STANDBY")
        self.assertIn("AVAILABLE", self.win.avail_pill.text())

        self.win.set_booking_state(BookingState.WAITING_FOR_2FA)
        self.assertEqual(self.win.banner_text.text(), "WAITING · 2FA / OTP")

        self.win.set_booking_state(BookingState.WAITING_FOR_CAPTCHA)
        self.assertEqual(self.win.banner_text.text(), "WAITING · CAPTCHA")

        self.win.set_booking_state(BookingState.PAYMENT)
        self.assertEqual(self.win.banner_text.text(), "PAYMENT · PENDING")

        self.win.set_booking_state(BookingState.COMPLETED)
        self.assertEqual(self.win.banner_text.text(), "BOOKED")
        self.assertIn("BOOKED", self.win.avail_pill.text())

        self.win.set_booking_state(BookingState.FAILED)
        self.assertEqual(self.win.banner_text.text(), "FAILED")

    def test_worker_buttons_emit_launch_worker(self) -> None:
        emitted: list[tuple[str, int, str]] = []
        self.win.launch_worker.connect(
            lambda tid, idx, tag: emitted.append((tid, idx, tag))
        )
        self.win.btn_w2.click()
        self.win.btn_app.click()
        self.assertEqual(len(emitted), 2)
        self.assertEqual(emitted[0], ("ticket-1", 0, "@ W2"))
        self.assertEqual(emitted[1], ("ticket-1", 0, "🌀 APP"))

    def test_tatkal_countdown_updates_clock(self) -> None:
        self.win.set_tatkal_countdown("3A")
        self.win._tick_clock()
        text = self.win.clock_lbl.text()
        self.assertTrue(text.startswith("TATKAL"), f"unexpected clock text: {text!r}")

        self.win.set_tatkal_countdown("SL")
        self.win._tick_clock()
        self.assertTrue(self.win.clock_lbl.text().startswith("TATKAL"))


class TestUserAssistedBookingFlow(unittest.TestCase):
    """End-to-end user-assisted booking flow through the Application controller."""

    def setUp(self) -> None:
        self.harness = _FlowHarness()
        self.controller = self.harness.controller
        self.pair_win = self.harness.pair_win

        # Headless: no real browser, no modal dialogs, no blocking message boxes.
        self._info_patch = patch.object(QMessageBox, "information", return_value=None)
        self._warn_patch = patch.object(QMessageBox, "warning", return_value=None)
        self._info_patch.start()
        self._warn_patch.start()

        # Auto-accept every manual checkpoint dialog so the flow runs headless.
        self.controller._show_two_factor_dialog = lambda win: "123456"
        self.controller._show_captcha_dialog = lambda win: "AB12CD"
        self.controller._show_payment_details = lambda win: None
        self.controller._show_fare_confirm_dialog = lambda win: True

    def tearDown(self) -> None:
        self._warn_patch.stop()
        self._info_patch.stop()
        self.harness.close()

    def _click_worker(self, button) -> None:
        with patch("webbrowser.open") as mock_open:
            button.click()
            self.harness.browser_urls.extend(
                str(args[0][0]) for args in mock_open.call_args_list
            )
            return mock_open

    def test_worker_launch_opens_irctc_and_advances_to_payment(self) -> None:
        mock_open = self._click_worker(self.pair_win.btn_w2)

        # 2. Browser launch handoff to the official IRCTC page.
        self.assertTrue(mock_open.called, "webbrowser.open was not called")
        url = mock_open.call_args[0][0]
        self.assertIn("irctc.co.in", url)

        # 3. Form assistance: passenger/train details copied to clipboard.
        clipboard = QGuiApplication.clipboard()
        clip_text = clipboard.text() if clipboard is not None else ""
        self.assertIn("12704", clip_text)
        self.assertIn("S. Singh", clip_text)
        self.assertIn("Lower", clip_text)

        # 4. Manual checkpoints ran synchronously: 2FA -> CAPTCHA -> PAYMENT.
        service: BookingWorkflowService = self.controller._booking_service  # type: ignore[assignment]
        self.assertEqual(service.state, BookingState.PAYMENT)
        self.assertEqual(self.pair_win.banner_text.text(), "PAYMENT · PENDING")

    def test_completion_persists_history_pnr_ers_and_books_panel(self) -> None:
        self._click_worker(self.pair_win.btn_w2)

        service: BookingWorkflowService = self.controller._booking_service  # type: ignore[assignment]
        history: HistoryService = self.controller._history_service  # type: ignore[assignment]
        pnr_service: PnrService = self.controller._pnr_service  # type: ignore[assignment]

        # 6. Payment handoff: PNR entered upon payment approval.
        result = service.confirm_payment("1234567890", fare_amount=1800.0)

        # 7. Post-booking completion.
        self.assertEqual(service.state, BookingState.COMPLETED)
        self.assertEqual(result["pnr"], "1234567890")
        self.assertIn("history_id", result)
        self.assertIsNone(service.session)

        # History persisted.
        records = history.list_history()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["pnr_number"], "1234567890")
        self.assertEqual(records[0]["booking_status"], "success")
        self.assertEqual(records[0]["fare_amount"], 1800.0)

        # PNR stored.
        self.assertTrue(pnr_service.pnr_exists("1234567890"))
        pnr_record = pnr_service.get_pnr("1234567890")
        self.assertEqual(pnr_record["booking_status"], "booked")

        # ERS HTML generated on disk.
        ers_path = os.path.join(self.harness.ers_dir, "ERS_1234567890.html")
        self.assertTrue(os.path.exists(ers_path), f"ERS file not created: {ers_path}")
        with open(ers_path, "r", encoding="utf-8") as fh:
            ers_html = fh.read()
        self.assertIn("1234567890", ers_html)
        self.assertIn("12704", ers_html)
        self.assertIn("S. Singh", ers_html)
        self.assertNotIn("{pnr_number}", ers_html)

        # Panel status flipped to BOOKED.
        self.assertEqual(self.pair_win.banner_text.text(), "BOOKED")
        self.assertIn("BOOKED", self.pair_win.avail_pill.text())

    def test_cancel_flow(self) -> None:
        self._click_worker(self.pair_win.btn_w2)
        service: BookingWorkflowService = self.controller._booking_service  # type: ignore[assignment]
        service.cancel()
        self.assertEqual(service.state, BookingState.CANCELLED)
        self.assertEqual(self.pair_win.banner_text.text(), "CANCELLED")

    def test_cannot_start_second_session_without_reset(self) -> None:
        self._click_worker(self.pair_win.btn_w2)
        service: BookingWorkflowService = self.controller._booking_service  # type: ignore[assignment]
        with self.assertRaises(Exception):
            service.start_session("some-other-ticket-id")


if __name__ == "__main__":
    unittest.main()
