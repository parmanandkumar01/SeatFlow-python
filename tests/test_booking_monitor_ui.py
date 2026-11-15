"""Tests for the Booking Monitor UI.

Tests cover:
- Dialog initialization with a sample ticket and account.
- Passenger table rendering from passenger_details JSON.
- Visual stepper updates on BookingState transitions.
- Button enabled/disabled states across the lifecycle.
- Integration with BookingWorkflowService signals (event_emitted,
  state_changed, completion/failure/cancellation).
- Suppressed auto-dialog handoff so modal dialogs do not block tests.

Uses an offscreen QApplication and temporary database. No network I/O.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from PySide6.QtWidgets import QApplication

from seatflow.database.database import Database
from seatflow.security.vault import VaultService
from seatflow.services import (
    BookingState,
    BookingWorkflowService,
    IrctcAccountService,
    PnrService,
    TicketService,
    HistoryService,
)
from seatflow.ui.dialogs.booking_monitor_dialog import BookingMonitorDialog

_app = QApplication.instance() or QApplication([])


class BookingMonitorTestCase(unittest.TestCase):
    """Base test case with temp DB, services, and a monitor dialog."""

    def setUp(self) -> None:
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.vault = VaultService(self.db)
        self.account_service = IrctcAccountService(self.db, self.vault)
        self.ticket_service = TicketService(self.db)
        self.history_service = HistoryService(self.db)
        self.pnr_service = PnrService(self.db)
        self.workflow = BookingWorkflowService(
            self.db,
            history_service=self.history_service,
            pnr_service=self.pnr_service,
            ticket_service=self.ticket_service,
            account_service=self.account_service,
        )
        self.vault.initialize("master-password")
        self.account_id = self.account_service.add_account(
            username="railuser",
            password="pass123",
            mobile="9876543210",
            email="user@example.com",
        )
        self.ticket_id = self.ticket_service.add_ticket(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details=(
                '[{"name": "John Doe", "age": 30, "gender": "M", "berth": "LB"},'
                ' {"name": "Jane Doe", "age": 28, "gender": "F", "berth": "UB"}]'
            ),
            irctc_account_id=self.account_id,
        )
        self.ticket = self.ticket_service.get_ticket(self.ticket_id)
        self.dialog = BookingMonitorDialog(
            ticket=self.ticket,
            workflow=self.workflow,
            account_username="railuser",
        )
        # Suppress modal auto-dialogs so tests never block.
        self.dialog._suppress_auto_dialog = True

    def tearDown(self) -> None:
        self.dialog.close()
        self.vault.lock()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def _advance_to(self, state: BookingState) -> None:
        """Drive the workflow to a target state via its public API."""
        if state == BookingState.IN_PROGRESS:
            self.workflow.start_session(self.ticket_id, self.account_id)
        elif state == BookingState.WAITING_FOR_2FA:
            self.workflow.start_session(self.ticket_id, self.account_id)
            self.workflow.reach_login_checkpoint()
        elif state == BookingState.WAITING_FOR_CAPTCHA:
            self.workflow.start_session(self.ticket_id, self.account_id)
            self.workflow.reach_login_checkpoint()
            self.workflow.submit_manual_2fa("123456")
        elif state == BookingState.PAYMENT:
            self.workflow.start_session(self.ticket_id, self.account_id)
            self.workflow.reach_login_checkpoint()
            self.workflow.submit_manual_2fa("123456")
            self.workflow.submit_manual_captcha("AB12CD")
        elif state == BookingState.COMPLETED:
            self.workflow.start_session(self.ticket_id, self.account_id)
            self.workflow.reach_login_checkpoint()
            self.workflow.submit_manual_2fa("123456")
            self.workflow.submit_manual_captcha("AB12CD")
            self.workflow.confirm_fare(True)
            self.workflow.confirm_payment("1234567890", fare_amount=1800.0)
        elif state == BookingState.CANCELLED:
            self.workflow.start_session(self.ticket_id, self.account_id)
            self.workflow.cancel()
        elif state == BookingState.FAILED:
            self.workflow.start_session(self.ticket_id, self.account_id)
            self.workflow.fail("test failure")


class TestMonitorInitialization(BookingMonitorTestCase):
    """Tests for dialog initialization."""

    def test_dialog_initializes(self) -> None:
        self.assertIsNotNone(self.dialog)
        self.assertEqual(self.dialog.windowTitle(), "Booking Monitor")

    def test_six_stages_present(self) -> None:
        self.assertEqual(len(self.dialog._stage_labels), 6)

    def test_passenger_table_populated(self) -> None:
        self.assertEqual(self.dialog.passenger_table.rowCount(), 2)
        self.assertEqual(
            self.dialog.passenger_table.item(0, 0).text(), "John Doe"
        )
        self.assertEqual(
            self.dialog.passenger_table.item(1, 0).text(), "Jane Doe"
        )
        self.assertEqual(
            self.dialog.passenger_table.item(0, 3).text(), "LB"
        )

    def test_passenger_table_bad_json_empty(self) -> None:
        self.ticket["passenger_details"] = "not json"
        dlg = BookingMonitorDialog(
            ticket=self.ticket,
            workflow=self.workflow,
            account_username="railuser",
        )
        self.assertEqual(dlg.passenger_table.rowCount(), 0)
        dlg.close()

    def test_is_started_false_initially(self) -> None:
        self.assertFalse(self.dialog.is_started)

    def test_workflow_accessor(self) -> None:
        self.assertIs(self.dialog.workflow, self.workflow)


class TestInitialControlStates(BookingMonitorTestCase):
    """Tests for button enabled/disabled at IDLE."""

    def test_start_enabled_idle(self) -> None:
        self.assertTrue(self.dialog.btn_start.isEnabled())

    def test_cancel_disabled_idle(self) -> None:
        self.assertFalse(self.dialog.btn_cancel.isEnabled())

    def test_checkpoint_buttons_disabled_idle(self) -> None:
        self.assertFalse(self.dialog.btn_captcha.isEnabled())
        self.assertFalse(self.dialog.btn_otp.isEnabled())
        self.assertFalse(self.dialog.btn_fare.isEnabled())
        self.assertFalse(self.dialog.btn_pnr.isEnabled())

    def test_close_disabled_idle(self) -> None:
        self.assertFalse(self.dialog.btn_close.isEnabled())


class TestStepperUpdates(BookingMonitorTestCase):
    """Tests for stepper visual updates on state changes."""

    def test_stepper_updates_on_in_progress(self) -> None:
        self._advance_to(BookingState.IN_PROGRESS)
        # First stage should be active (orange) after IN_PROGRESS.
        # We assert the first pill's stylesheet references the orange accent.
        first_style = self.dialog._stage_labels[0].styleSheet()
        self.assertIn("#ff9800", first_style)

    def test_stepper_updates_on_waiting_captcha(self) -> None:
        self._advance_to(BookingState.WAITING_FOR_CAPTCHA)
        # Later stage becomes active.
        some_active = any(
            "#ff9800" in lbl.styleSheet()
            for lbl in self.dialog._stage_labels
        )
        self.assertTrue(some_active)

    def test_stepper_completed_marks_all(self) -> None:
        self._advance_to(BookingState.COMPLETED)
        # All stages should be complete (green) on completion.
        all_green = all(
            "#4caf50" in lbl.styleSheet()
            for lbl in self.dialog._stage_labels
        )
        self.assertTrue(all_green)


class TestControlStatesAcrossLifecycle(BookingMonitorTestCase):
    """Tests for button states at each lifecycle stage."""

    def test_in_progress_enables_cancel(self) -> None:
        self._advance_to(BookingState.IN_PROGRESS)
        self.assertTrue(self.dialog.btn_cancel.isEnabled())
        self.assertFalse(self.dialog.btn_start.isEnabled())

    def test_waiting_2fa_enables_otp(self) -> None:
        self._advance_to(BookingState.WAITING_FOR_2FA)
        self.assertTrue(self.dialog.btn_otp.isEnabled())
        self.assertFalse(self.dialog.btn_captcha.isEnabled())

    def test_waiting_captcha_enables_captcha(self) -> None:
        self._advance_to(BookingState.WAITING_FOR_CAPTCHA)
        self.assertTrue(self.dialog.btn_captcha.isEnabled())
        self.assertFalse(self.dialog.btn_otp.isEnabled())

    def test_payment_enables_fare_and_pnr(self) -> None:
        self._advance_to(BookingState.PAYMENT)
        self.assertTrue(self.dialog.btn_fare.isEnabled())
        self.assertTrue(self.dialog.btn_pnr.isEnabled())

    def test_completed_enables_close(self) -> None:
        self._advance_to(BookingState.COMPLETED)
        self.assertTrue(self.dialog.btn_close.isEnabled())
        self.assertFalse(self.dialog.btn_start.isEnabled())

    def test_cancelled_enables_close(self) -> None:
        self._advance_to(BookingState.CANCELLED)
        self.assertTrue(self.dialog.btn_close.isEnabled())


class TestWorkflowIntegration(BookingMonitorTestCase):
    """Tests for signal integration between workflow and monitor."""

    def test_event_emitted_logs_to_console(self) -> None:
        self._advance_to(BookingState.IN_PROGRESS)
        console_text = self.dialog.log_console.toPlainText()
        self.assertIn("session_started", console_text)

    def test_completion_emits_workflow_finished(self) -> None:
        received = []
        self.dialog.workflow_finished.connect(received.append)
        self._advance_to(BookingState.COMPLETED)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], "completed:1234567890")

    def test_cancellation_emits_workflow_finished(self) -> None:
        received = []
        self.dialog.workflow_finished.connect(received.append)
        self._advance_to(BookingState.CANCELLED)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], "cancelled")

    def test_failure_emits_workflow_finished(self) -> None:
        received = []
        self.dialog.workflow_finished.connect(received.append)
        self._advance_to(BookingState.FAILED)
        self.assertEqual(len(received), 1)
        self.assertTrue(received[0].startswith("failed:"))

    def test_completion_persists_history_and_pnr(self) -> None:
        self._advance_to(BookingState.COMPLETED)
        self.assertEqual(len(self.history_service.list_history()), 1)
        self.assertTrue(self.pnr_service.pnr_exists("1234567890"))

    def test_log_console_receives_state_changes(self) -> None:
        self._advance_to(BookingState.PAYMENT)
        console_text = self.dialog.log_console.toPlainText()
        self.assertIn("state_changed", console_text)


class TestMonitorStartAction(BookingMonitorTestCase):
    """Tests for the Start button action."""

    def test_start_button_starts_workflow(self) -> None:
        self.dialog._on_start()
        self.assertTrue(self.dialog.is_started)
        # After start + reach_login_checkpoint, state is WAITING_FOR_2FA.
        self.assertEqual(self.workflow.state, BookingState.WAITING_FOR_2FA)
        self.assertTrue(self.dialog.btn_otp.isEnabled())

    def test_start_twice_is_noop(self) -> None:
        self.dialog._on_start()
        self.dialog._on_start()
        self.assertTrue(self.dialog.is_started)


if __name__ == "__main__":
    unittest.main()