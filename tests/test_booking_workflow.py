"""Tests for the booking workflow state machine and service layer.

Tests cover:
- Initial state and allowed-transition table.
- start_session validation and IN_PROGRESS transition.
- Valid and invalid state transitions for every checkpoint.
- Manual 2FA and CAPTCHA submission triggers (presence validation,
  never stored/transmitted).
- Fare confirmation (confirm and cancel paths).
- Payment completion with automatic HistoryService + PnrService
  persistence.
- Cancellation and failure handling.
- Qt signal emission for state changes and checkpoints.
- Persistence failure surfaces as a FAILED transition + error.

Uses temporary databases and dummy data only. No network I/O.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal

from seatflow.database.database import Database
from seatflow.security.vault import VaultService
from seatflow.services import (
    BookingSessionError,
    BookingState,
    BookingWorkflowError,
    BookingWorkflowService,
    HistoryService,
    InvalidCheckpointError,
    InvalidTransitionError,
    IrctcAccountService,
    PnrService,
    TicketService,
)


class _SignalCollector(QObject):
    """Helper to collect signal emissions for assertions."""

    state_changed = Signal(str, str)
    waiting_for_2fa = Signal()
    waiting_for_captcha = Signal()
    waiting_for_fare_confirmation = Signal()
    booking_completed = Signal(str)
    booking_failed = Signal(str)
    booking_cancelled = Signal()


class BookingWorkflowTestCase(unittest.TestCase):
    """Base test case with temporary DB, vault, and all services."""

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
        self.service = BookingWorkflowService(
            self.db,
            history_service=self.history_service,
            pnr_service=self.pnr_service,
            ticket_service=self.ticket_service,
            account_service=self.account_service,
        )
        # Wire a signal collector to capture emissions.
        self.collector = _SignalCollector()
        self.service.state_changed.connect(self.collector.state_changed)
        self.service.waiting_for_2fa.connect(self.collector.waiting_for_2fa)
        self.service.waiting_for_captcha.connect(self.collector.waiting_for_captcha)
        self.service.waiting_for_fare_confirmation.connect(
            self.collector.waiting_for_fare_confirmation
        )
        self.service.booking_completed.connect(self.collector.booking_completed)
        self.service.booking_failed.connect(self.collector.booking_failed)
        self.service.booking_cancelled.connect(self.collector.booking_cancelled)
        self._signals: dict[str, list] = {
            "state_changed": [],
            "waiting_for_2fa": [],
            "waiting_for_captcha": [],
            "waiting_for_fare_confirmation": [],
            "booking_completed": [],
            "booking_failed": [],
            "booking_cancelled": [],
        }
        self.collector.state_changed.connect(
            lambda o, n: self._signals["state_changed"].append((o, n))
        )
        self.collector.waiting_for_2fa.connect(
            lambda: self._signals["waiting_for_2fa"].append(True)
        )
        self.collector.waiting_for_captcha.connect(
            lambda: self._signals["waiting_for_captcha"].append(True)
        )
        self.collector.waiting_for_fare_confirmation.connect(
            lambda: self._signals["waiting_for_fare_confirmation"].append(True)
        )
        self.collector.booking_completed.connect(
            lambda p: self._signals["booking_completed"].append(p)
        )
        self.collector.booking_failed.connect(
            lambda r: self._signals["booking_failed"].append(r)
        )
        self.collector.booking_cancelled.connect(
            lambda: self._signals["booking_cancelled"].append(True)
        )

    def tearDown(self) -> None:
        self.vault.lock()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def _create_account(self, username="railway_user", password="pass123") -> str:
        self.vault.initialize("master-password")
        return self.account_service.add_account(
            username=username,
            password=password,
            mobile="9876543210",
            email="user@example.com",
            is_active=True,
        )

    def _create_ticket(self, account_id=None, **overrides) -> str:
        data = dict(
            train_number="12345",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="General",
            passenger_details='[{"name": "John Doe", "age": 30, "gender": "M"}]',
            irctc_account_id=account_id,
        )
        data.update(overrides)
        return self.ticket_service.add_ticket(**data)


class TestInitialStateAndTransitions(BookingWorkflowTestCase):
    """Tests for the initial state and the transition table."""

    def test_initial_state_is_idle(self) -> None:
        self.assertEqual(self.service.state, BookingState.IDLE)

    def test_is_active_false_when_idle(self) -> None:
        self.assertFalse(self.service.is_active)

    def test_session_none_when_idle(self) -> None:
        self.assertIsNone(self.service.session)

    def test_allowed_transitions_table(self) -> None:
        table = BookingWorkflowService.allowed_transitions()
        self.assertEqual(
            table[BookingState.IDLE], {BookingState.IN_PROGRESS}
        )
        self.assertEqual(
            table[BookingState.COMPLETED], set()
        )

    def test_can_transition_static(self) -> None:
        self.assertTrue(
            BookingWorkflowService.can_transition(
                BookingState.IDLE, BookingState.IN_PROGRESS
            )
        )
        self.assertFalse(
            BookingWorkflowService.can_transition(
                BookingState.IDLE, BookingState.PAYMENT
            )
        )

    def test_cannot_start_when_not_idle(self) -> None:
        ticket_id = self._create_ticket()
        self.service.start_session(ticket_id)
        with self.assertRaises(InvalidTransitionError):
            self.service.start_session(ticket_id)


class TestStartSession(BookingWorkflowTestCase):
    """Tests for starting a booking session."""

    def test_start_session_transitions_to_in_progress(self) -> None:
        ticket_id = self._create_ticket()
        session = self.service.start_session(ticket_id)
        self.assertEqual(self.service.state, BookingState.IN_PROGRESS)
        self.assertTrue(self.service.is_active)
        self.assertEqual(session["ticket_id"], ticket_id)
        self.assertIn(
            ("idle", "in-progress"), self._signals["state_changed"]
        )

    def test_start_session_missing_ticket_raises(self) -> None:
        with self.assertRaises(Exception):
            self.service.start_session("nonexistent-ticket-id")

    def test_start_session_with_account(self) -> None:
        account_id = self._create_account()
        ticket_id = self._create_ticket(account_id=account_id)
        session = self.service.start_session(ticket_id)
        self.assertEqual(session["irctc_account_id"], account_id)

    def test_start_session_invalid_account_raises(self) -> None:
        ticket_id = self._create_ticket()
        with self.assertRaises(Exception):
            self.service.start_session(ticket_id, irctc_account_id="bad-account")


class TestManualCheckpoints(BookingWorkflowTestCase):
    """Tests for the user-driven checkpoints."""

    def setUp(self) -> None:
        super().setUp()
        self.ticket_id = self._create_ticket()
        self.service.start_session(self.ticket_id)

    def test_reach_login_checkpoint(self) -> None:
        self.service.reach_login_checkpoint()
        self.assertEqual(self.service.state, BookingState.WAITING_FOR_2FA)
        self.assertEqual(len(self._signals["waiting_for_2fa"]), 1)

    def test_submit_2fa_advances_to_captcha(self) -> None:
        self.service.reach_login_checkpoint()
        self.service.submit_manual_2fa("123456")
        self.assertEqual(self.service.state, BookingState.WAITING_FOR_CAPTCHA)
        self.assertEqual(len(self._signals["waiting_for_captcha"]), 1)

    def test_submit_2fa_empty_raises(self) -> None:
        self.service.reach_login_checkpoint()
        with self.assertRaises(InvalidCheckpointError):
            self.service.submit_manual_2fa("   ")

    def test_submit_2fa_wrong_state_raises(self) -> None:
        # Still IN_PROGRESS, not at 2FA checkpoint.
        with self.assertRaises(InvalidTransitionError):
            self.service.submit_manual_2fa("123456")

    def test_submit_captcha_advances_to_payment(self) -> None:
        self.service.reach_login_checkpoint()
        self.service.submit_manual_2fa("123456")
        self.service.submit_manual_captcha("AB12CD")
        self.assertEqual(self.service.state, BookingState.PAYMENT)
        self.assertEqual(
            len(self._signals["waiting_for_fare_confirmation"]), 1
        )

    def test_submit_captcha_empty_raises(self) -> None:
        self.service.reach_login_checkpoint()
        self.service.submit_manual_2fa("123456")
        with self.assertRaises(InvalidCheckpointError):
            self.service.submit_manual_captcha("")

    def test_submit_captcha_wrong_state_raises(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            self.service.submit_manual_captcha("AB12CD")


class TestFareConfirmation(BookingWorkflowTestCase):
    """Tests for the fare confirmation checkpoint."""

    def setUp(self) -> None:
        super().setUp()
        self.ticket_id = self._create_ticket()
        self.service.start_session(self.ticket_id)
        self.service.reach_login_checkpoint()
        self.service.submit_manual_2fa("123456")
        self.service.submit_manual_captcha("AB12CD")

    def test_confirm_fare_true_sets_flag(self) -> None:
        self.service.confirm_fare(True)
        self.assertEqual(self.service.state, BookingState.PAYMENT)
        self.assertTrue(self.service.session["confirmed_fare"])

    def test_confirm_fare_false_cancels(self) -> None:
        self.service.confirm_fare(False)
        self.assertEqual(self.service.state, BookingState.CANCELLED)
        self.assertEqual(len(self._signals["booking_cancelled"]), 1)
        self.assertIsNone(self.service.session)

    def test_confirm_fare_wrong_state_raises(self) -> None:
        # Cancel first, then trying to confirm fare should fail.
        self.service.confirm_fare(False)
        with self.assertRaises(InvalidTransitionError):
            self.service.confirm_fare(True)


class TestPaymentCompletion(BookingWorkflowTestCase):
    """Tests for payment confirmation and persistence."""

    def setUp(self) -> None:
        super().setUp()
        self.account_id = self._create_account()
        self.ticket_id = self._create_ticket(account_id=self.account_id)
        self.service.start_session(self.ticket_id)
        self.service.reach_login_checkpoint()
        self.service.submit_manual_2fa("123456")
        self.service.submit_manual_captcha("AB12CD")
        self.service.confirm_fare(True)

    def test_confirm_payment_completes_and_persists(self) -> None:
        result = self.service.confirm_payment("1234567890", fare_amount=2500.0)
        self.assertEqual(self.service.state, BookingState.COMPLETED)
        self.assertIn("history_id", result)
        self.assertIn("pnr_id", result)
        self.assertEqual(result["pnr"], "1234567890")

        # History persisted.
        history = self.history_service.list_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["pnr_number"], "1234567890")
        self.assertEqual(history[0]["booking_status"], "success")
        self.assertEqual(history[0]["fare_amount"], 2500.0)
        self.assertEqual(history[0]["irctc_account_id"], self.account_id)

        # PNR persisted.
        self.assertTrue(self.pnr_service.pnr_exists("1234567890"))
        pnr = self.pnr_service.get_pnr("1234567890")
        self.assertEqual(pnr["booking_status"], "booked")

        # Signal emitted.
        self.assertEqual(self._signals["booking_completed"], ["1234567890"])
        self.assertIsNone(self.service.session)

    def test_confirm_payment_empty_pnr_raises(self) -> None:
        with self.assertRaises(InvalidCheckpointError):
            self.service.confirm_payment("")

    def test_confirm_payment_wrong_state_raises(self) -> None:
        # Cancel out of PAYMENT first.
        self.service.confirm_fare(False)
        with self.assertRaises(InvalidTransitionError):
            self.service.confirm_payment("1234567890")

    def test_confirm_payment_duplicate_pnr(self) -> None:
        # First completion.
        self.service.confirm_payment("1234567890")
        # Reset and start a second booking with the same PNR.
        self.service.reset()
        ticket_id = self._create_ticket(
            train_number="99999", journey_date="2026-12-02"
        )
        self.service.start_session(ticket_id)
        self.service.reach_login_checkpoint()
        self.service.submit_manual_2fa("654321")
        self.service.submit_manual_captcha("ZZ99YY")
        self.service.confirm_fare(True)
        # PNR already exists -> add_pnr raises; but history still records.
        result = self.service.confirm_payment("1234567890")
        self.assertEqual(self.service.state, BookingState.COMPLETED)
        self.assertIsNone(result["pnr_id"])  # not re-created
        self.assertEqual(len(self.history_service.list_history()), 2)

    def test_confirm_payment_persistence_failure_marks_failed(self) -> None:
        with patch.object(
            self.history_service,
            "add_history",
            side_effect=RuntimeError("db write error"),
        ):
            with self.assertRaises(BookingWorkflowError):
                self.service.confirm_payment("1234567890")
        self.assertEqual(self.service.state, BookingState.FAILED)
        self.assertEqual(len(self._signals["booking_failed"]), 1)
        self.assertIsNone(self.service.session)


class TestCaseellationAndFailure(BookingWorkflowTestCase):
    """Tests for cancellation and failure handling."""

    def setUp(self) -> None:
        super().setUp()
        self.ticket_id = self._create_ticket()
        self.service.start_session(self.ticket_id)

    def test_cancel_from_in_progress(self) -> None:
        self.service.cancel()
        self.assertEqual(self.service.state, BookingState.CANCELLED)
        self.assertEqual(len(self._signals["booking_cancelled"]), 1)
        self.assertIsNone(self.service.session)

    def test_cancel_from_idle_raises(self) -> None:
        self.service.reset()
        with self.assertRaises(InvalidTransitionError):
            self.service.cancel()

    def test_cancel_twice_raises(self) -> None:
        self.service.cancel()
        with self.assertRaises(InvalidTransitionError):
            self.service.cancel()

    def test_fail_from_in_progress(self) -> None:
        self.service.fail("boom")
        self.assertEqual(self.service.state, BookingState.FAILED)
        self.assertEqual(len(self._signals["booking_failed"]), 1)
        self.assertIsNone(self.service.session)

    def test_fail_from_idle_raises(self) -> None:
        self.service.reset()
        with self.assertRaises(InvalidTransitionError):
            self.service.fail("boom")

    def test_terminal_state_has_no_outgoing_transitions(self) -> None:
        self.service.fail("boom")
        with self.assertRaises(InvalidTransitionError):
            self.service.reach_login_checkpoint()

    def test_reset_returns_to_idle(self) -> None:
        self.service.reset()
        self.assertEqual(self.service.state, BookingState.IDLE)
        self.assertIsNone(self.service.session)


class TestFullLifecyclePath(BookingWorkflowTestCase):
    """End-to-end happy-path lifecycle through every checkpoint."""

    def test_full_happy_path(self) -> None:
        account_id = self._create_account()
        ticket_id = self._create_ticket(account_id=account_id)

        self.assertEqual(self.service.state, BookingState.IDLE)
        self.service.start_session(ticket_id)
        self.assertEqual(self.service.state, BookingState.IN_PROGRESS)

        self.service.reach_login_checkpoint()
        self.assertEqual(self.service.state, BookingState.WAITING_FOR_2FA)

        self.service.submit_manual_2fa("123456")
        self.assertEqual(self.service.state, BookingState.WAITING_FOR_CAPTCHA)

        self.service.submit_manual_captcha("AB12CD")
        self.assertEqual(self.service.state, BookingState.PAYMENT)

        self.service.confirm_fare(True)

        result = self.service.confirm_payment("1234567890", fare_amount=1800.0)
        self.assertEqual(self.service.state, BookingState.COMPLETED)

        # Full expected state sequence.
        expected = [
            ("idle", "in-progress"),
            ("in-progress", "waiting-for-2fa"),
            ("waiting-for-2fa", "waiting-for-captcha"),
            ("waiting-for-captcha", "payment"),
            ("payment", "completed"),
        ]
        self.assertEqual(self._signals["state_changed"], expected)

        # All checkpoint signals fired exactly once.
        self.assertEqual(len(self._signals["waiting_for_2fa"]), 1)
        self.assertEqual(len(self._signals["waiting_for_captcha"]), 1)
        self.assertEqual(
            len(self._signals["waiting_for_fare_confirmation"]), 1
        )
        self.assertEqual(self._signals["booking_completed"], ["1234567890"])
        self.assertEqual(self._signals["booking_failed"], [])
        self.assertEqual(self._signals["booking_cancelled"], [])

        # Persistence side effects.
        self.assertEqual(len(self.history_service.list_history()), 1)
        self.assertTrue(self.pnr_service.pnr_exists("1234567890"))
        self.assertEqual(result["pnr"], "1234567890")


if __name__ == "__main__":
    unittest.main()