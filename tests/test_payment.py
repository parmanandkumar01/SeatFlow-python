"""Unit tests for the Payment & Freecharge service layer.

Tests mobile validation, OTP verification, bank account linking,
UPI balance check, QR pairing/cancellation, and database persistence.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from PySide6.QtCore import QCoreApplication

from seatflow.database.database import Database
from seatflow.services.payment_service import (
    PaymentService,
    SUPPORTED_BANKS,
)


class PaymentServiceTestCase(unittest.TestCase):
    """Base test case for PaymentService with temporary database."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure a QCoreApplication exists for Qt signals."""
        if QCoreApplication.instance() is None:
            cls.app = QCoreApplication([])

    def setUp(self) -> None:
        """Create a temporary database and PaymentService for each test."""
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.payment_service = PaymentService(self.db)

    def tearDown(self) -> None:
        """Clean up database."""
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)


class TestLoginOtp(PaymentServiceTestCase):
    """Tests for send_login_otp and verify_login_otp."""

    def test_send_login_otp_valid_mobile(self) -> None:
        """Valid 10-digit mobile number creates session and returns sessionId."""
        signals: list[str] = []
        self.payment_service.session_updated.connect(signals.append)

        res = self.payment_service.send_login_otp("9876543210")
        self.assertTrue(res["ok"])
        self.assertIn("sessionId", res)
        session_id = res["sessionId"]
        self.assertTrue(session_id.startswith("fc_"))
        self.assertEqual(len(signals), 1)

        # Check DB persistence
        session = self.payment_service.get_session_by_id(session_id)
        self.assertIsNotNone(session)
        self.assertEqual(session["mobile"], "9876543210")
        self.assertEqual(session["otp_verified"], 0)

    def test_send_login_otp_invalid_mobiles(self) -> None:
        """Invalid mobile numbers (length != 10 or non-digits) are rejected."""
        for invalid in ["123", "98765432101", "abcdefghij", ""]:
            res = self.payment_service.send_login_otp(invalid)
            self.assertFalse(res["ok"])
            self.assertIn("error", res)

    def test_verify_login_otp_success(self) -> None:
        """Valid OTP marks session as verified in database."""
        send_res = self.payment_service.send_login_otp("9876543210")
        session_id = send_res["sessionId"]

        verify_res = self.payment_service.verify_login_otp(session_id, "123456")
        self.assertTrue(verify_res["ok"])
        self.assertFalse(verify_res["needDeviceOtp"])
        self.assertEqual(verify_res["sms"]["mobile"], "9876543210")

        session = self.payment_service.get_session_by_id(session_id)
        self.assertEqual(session["otp_verified"], 1)

    def test_verify_login_otp_short_or_empty(self) -> None:
        """Short OTP (< 4 chars) is rejected."""
        send_res = self.payment_service.send_login_otp("9876543210")
        session_id = send_res["sessionId"]

        res = self.payment_service.verify_login_otp(session_id, "12")
        self.assertFalse(res["ok"])
        self.assertIn("error", res)

    def test_verify_login_otp_unknown_session(self) -> None:
        """Non-existent session ID fails cleanly."""
        res = self.payment_service.verify_login_otp("fc_invalid_id", "1234")
        self.assertFalse(res["ok"])


class TestBankLinkingAndBalance(PaymentServiceTestCase):
    """Tests for bank linking and balance queries."""

    def setUp(self) -> None:
        super().setUp()
        res = self.payment_service.send_login_otp("9876543210")
        self.session_id = res["sessionId"]
        self.payment_service.verify_login_otp(self.session_id, "1234")

    def test_get_available_banks(self) -> None:
        """Returns pre-configured list of supported banks."""
        banks = self.payment_service.get_banks()
        self.assertEqual(len(banks), len(SUPPORTED_BANKS))
        bank_ids = [b["id"] for b in banks]
        self.assertIn("sbi", bank_ids)
        self.assertIn("hdfc", bank_ids)

    def test_link_bank_success(self) -> None:
        """Linking a bank sets bank_linked=1 and returns masked account info."""
        link_res = self.payment_service.link_bank(self.session_id, "sbi")
        self.assertTrue(link_res["ok"])
        self.assertIn("account", link_res)
        acct = link_res["account"]
        self.assertEqual(acct["bankId"], "sbi")
        self.assertEqual(acct["last4"], "3210")
        self.assertIn("3210", acct["accountNumber"])

        session = self.payment_service.get_session_by_id(self.session_id)
        self.assertEqual(session["bank_linked"], 1)

    def test_check_balance_with_valid_pin(self) -> None:
        """check_balance returns balance and updates last_checked timestamp."""
        self.payment_service.link_bank(self.session_id, "hdfc")

        bal_res = self.payment_service.check_balance(self.session_id, "1234")
        self.assertTrue(bal_res["ok"])
        self.assertGreater(bal_res["balance"], 0)

        session = self.payment_service.get_session_by_id(self.session_id)
        self.assertIsNotNone(session["last_checked"])

    def test_check_balance_invalid_pin(self) -> None:
        """Short or empty PIN is rejected."""
        self.payment_service.link_bank(self.session_id, "hdfc")
        res = self.payment_service.check_balance(self.session_id, "1")
        self.assertFalse(res["ok"])

    def test_saved_balance_query(self) -> None:
        """saved_balance returns balance from cached session."""
        self.payment_service.link_bank(self.session_id, "icici")
        self.payment_service.check_balance(self.session_id, "1234")

        saved = self.payment_service.saved_balance("9876543210", "1234")
        self.assertTrue(saved["ok"])
        self.assertGreater(saved["balance"], 0)


class TestSessionManagement(PaymentServiceTestCase):
    """Tests for listing and cancelling sessions."""

    def test_list_sessions_returns_formatted_data(self) -> None:
        """list_sessions returns formatted session cards."""
        self.payment_service.send_login_otp("9876543210")
        sessions = self.payment_service.list_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["mobile"], "9876543210")
        self.assertEqual(sessions[0]["last4"], "3210")

    def test_cancel_session_soft_deletes(self) -> None:
        """cancel_session soft-deletes the record from active list."""
        res = self.payment_service.send_login_otp("9876543210")
        session_id = res["sessionId"]

        deleted = self.payment_service.cancel_session(session_id)
        self.assertTrue(deleted)

        sessions = self.payment_service.list_sessions()
        self.assertEqual(len(sessions), 0)


class TestQRPairing(PaymentServiceTestCase):
    """Tests for booking QR confirmation and cancellation."""

    def test_confirm_pair_qr(self) -> None:
        """confirm_pair_qr emits signal and returns confirmation."""
        paired: list[tuple[str, int]] = []
        self.payment_service.qr_pair_confirmed.connect(lambda t, s: paired.append((t, s)))

        res = self.payment_service.confirm_pair_qr("ticket_123", slot=2)
        self.assertTrue(res["ok"])
        self.assertEqual(res["ticketId"], "ticket_123")
        self.assertEqual(res["slot"], 2)
        self.assertEqual(len(paired), 1)
        self.assertEqual(paired[0], ("ticket_123", 2))

    def test_cancel_qr(self) -> None:
        """cancel_qr emits signal and returns session key."""
        cancelled: list[str] = []
        self.payment_service.qr_cancelled.connect(cancelled.append)

        res = self.payment_service.cancel_qr("ticket_123", slot=1)
        self.assertTrue(res["ok"])
        self.assertEqual(res["sessionKey"], "ticket_123_1")
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0], "ticket_123_1")


if __name__ == "__main__":
    unittest.main()
