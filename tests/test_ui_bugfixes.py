"""Tests covering all 6 TASK-006 UI bugfixes.

Covers:
1. Startup window visibility: floating/ticket/panel windows HIDDEN at startup;
   only MainToolbarWindow (or VaultWindow when locked) is shown.
2. Payment QR gateways (IPAYQR, PHONEPEQR, ...) do not require a UPI ID;
   upi_input disabled when QR selected; identifier defaults to "Dynamic QR".
3. show_toast works reliably on AccountsWindow/PaymentWindow without raising.
4. Tokens button opens TokensWindow and NOT AccountsWindow.
5. fetch_train_list offline fallback train data for common routes (NDLS-HWH etc.)
   so TrainResultsWindow displays trains with class chips and quota selection.
6. Shutdown cleanly closes database and windows (idempotent).

Uses an offscreen QApplication and temporary databases. No network I/O is
required for the fallback path (the live httpx client is forced to fail).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from PySide6.QtWidgets import QApplication

from bingo_linux.app.application import Application
from bingo_linux.database.database import Database
from bingo_linux.security.vault import VaultService
from bingo_linux.services.train_service import fetch_train_list
from bingo_linux.ui.accounts_window import AccountsWindow
from bingo_linux.ui.main_window import MainToolbarWindow
from bingo_linux.ui.payment_window import is_qr_gateway, PaymentWindow
from bingo_linux.ui.train_results_window import TrainResultsWindow

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class _BaseTestCase(unittest.TestCase):
    """Base case with a temporary database and an Application controller."""

    def setUp(self) -> None:
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.controller = Application()
        self.controller._db = self.db
        self.vault = None

    def tearDown(self) -> None:
        try:
            self.controller.shutdown()
        except Exception:
            pass
        if self.vault is not None:
            try:
                self.vault.lock()
            except Exception:
                pass
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def _configure_locked_vault(self) -> None:
        """Leave the temp database's vault configured but locked with a
        password that differs from the master key used by
        Application._initialize_services, so unlock fails and the vault
        stays locked at startup."""
        vault = VaultService(self.db)
        vault.initialize("some-other-master-password")
        vault.lock()
        self.vault = vault
        self.controller._vault = vault


# ---------------------------------------------------------------------------
# Fix 1: Startup window visibility
# ---------------------------------------------------------------------------

class TestStartupVisibility(_BaseTestCase):
    """Floating/ticket/panel windows must be hidden at startup."""

    def test_unlocked_startup_shows_only_main_toolbar(self) -> None:
        """Vault auto-unlocks with the master key: only the toolbar exists,
        and every secondary floating window is hidden."""
        main_win = self.controller.create_main_window()
        self.assertIsNotNone(main_win)
        self.assertIsNotNone(self.controller._main_window)
        self.assertIsNone(self.controller._vault_window)

        floating = [
            self.controller._book_window,
            self.controller._tickets_window,
            self.controller._train_results_window,
            self.controller._accounts_window,
            self.controller._payment_window,
            self.controller._settings_window,
            self.controller._proxies_window,
            self.controller._history_window,
            self.controller._backup_restore_window,
            self.controller._tokens_window,
        ]
        for w in floating:
            self.assertIsNotNone(w)
            self.assertFalse(w.isVisible(), f"{w!r} should be hidden at startup")

        # Simulate run() showing only the main toolbar.
        self.controller._main_window.show()
        self.assertTrue(self.controller._main_window.isVisible())
        for w in floating:
            self.assertFalse(w.isVisible())

    def test_locked_startup_shows_vault_window_only(self) -> None:
        """When the vault is locked, only VaultWindow is shown; no main
        toolbar or floating windows are created/shown."""
        self._configure_locked_vault()
        win = self.controller.create_main_window()
        self.assertIsNone(self.controller._main_window)
        self.assertIsNotNone(self.controller._vault_window)
        self.assertIs(win, self.controller._vault_window)
        self.assertTrue(self.controller._vault_window.isVisible())
        self.assertIsNone(self.controller._tickets_window)
        self.assertIsNone(self.controller._tokens_window)


# ---------------------------------------------------------------------------
# Fix 2: QR gateways do not require a UPI ID
# ---------------------------------------------------------------------------

class TestQRGatewayPayment(_BaseTestCase):
    """QR gateways must not require a UPI ID."""

    def test_is_qr_gateway_detects_qr_codes(self) -> None:
        self.assertTrue(is_qr_gateway("IPAYQR"))
        self.assertTrue(is_qr_gateway("PHONEPEQR"))
        self.assertTrue(is_qr_gateway("PAYTMQR"))
        self.assertTrue(is_qr_gateway("IRCQR"))
        self.assertTrue(is_qr_gateway("RAZORPAYQR"))
        self.assertTrue(is_qr_gateway("PAYUQR"))
        self.assertFalse(is_qr_gateway("IRCUPIID"))
        self.assertFalse(is_qr_gateway("PHONEPEUPIID"))
        self.assertFalse(is_qr_gateway("PAYTMUPIID"))
        self.assertFalse(is_qr_gateway("RAZORPAYUPI"))
        self.assertFalse(is_qr_gateway("PAYUUPIID"))
        self.assertFalse(is_qr_gateway(""))
        self.assertFalse(is_qr_gateway(None))  # type: ignore[arg-type]

    def test_qr_gateway_disables_upi_input_and_defaults_identifier(self) -> None:
        win = PaymentWindow()
        try:
            # IPAYQR is the first gateway entry.
            win.gateway_combo.setCurrentIndex(0)
            self.assertTrue(is_qr_gateway(win.gateway_combo.currentData()))
            self.assertFalse(win.upi_input.isEnabled())
            self.assertEqual(win.upi_input.placeholderText(),
                             "Dynamic QR code at checkout (No UPI ID required)")

            emitted = []
            win.add_payment.connect(lambda d: emitted.append(d))
            win.upi_input.setText("")
            win._on_add_upi()
            self.assertEqual(len(emitted), 1)
            self.assertEqual(emitted[0]["gateway"], "IPAYQR")
            self.assertEqual(emitted[0]["identifier"], "Dynamic QR")
            self.assertEqual(emitted[0]["type"], "QR")

            # A non-QR gateway keeps the input enabled and requires a UPI ID.
            win.gateway_combo.setCurrentIndex(7)  # IRCUPIID
            self.assertFalse(is_qr_gateway(win.gateway_combo.currentData()))
            self.assertTrue(win.upi_input.isEnabled())
        finally:
            win.hide()
            win.deleteLater()


# ---------------------------------------------------------------------------
# Fix 3: show_toast works reliably without raising
# ---------------------------------------------------------------------------

class TestShowToastReliable(_BaseTestCase):
    """show_toast must never raise, on AccountsWindow and PaymentWindow."""

    def test_accounts_window_show_toast_never_raises(self) -> None:
        win = AccountsWindow()
        try:
            for i in range(20):
                win.show_toast(f"Toast message {i}")
            win.show_toast("Added user1")
            win.show_toast("Imported 2 accounts")
        finally:
            win.hide()
            win.deleteLater()

    def test_payment_window_show_toast_never_raises(self) -> None:
        win = PaymentWindow()
        try:
            for i in range(20):
                win.show_toast(f"Toast message {i}")
        finally:
            win.hide()
            win.deleteLater()

    def test_application_add_account_invokes_show_toast(self) -> None:
        """Application._on_add_account calls show_toast without raising."""
        self.controller.create_main_window()
        self.controller._on_add_account({
            "username": "railway_user",
            "password": "railway_password",
            "mobile": "9876543210",
            "email": "user@example.com",
        })
        self.controller._accounts_window.hide()


# ---------------------------------------------------------------------------
# Fix 4: Tokens button opens TokensWindow, not AccountsWindow
# ---------------------------------------------------------------------------

class TestTokensButton(_BaseTestCase):
    """The Tokens toolbar action must open TokensWindow and not AccountsWindow."""

    def test_tokens_action_opens_tokens_window_only(self) -> None:
        self.controller.create_main_window()
        self.controller._on_action_clicked("tokens")
        self.assertTrue(self.controller._tokens_window.isVisible())
        self.assertFalse(self.controller._accounts_window.isVisible())
        self.controller._tokens_window.hide()


# ---------------------------------------------------------------------------
# Fix 5: Offline fallback train data
# ---------------------------------------------------------------------------

class TestTrainFallback(_BaseTestCase):
    """fetch_train_list must return fallback trains for common routes offline."""

    def test_offline_fallback_ndls_hwh(self) -> None:
        with mock.patch(
            "bingo_linux.services.train_service.httpx.Client",
            side_effect=Exception("network offline"),
        ):
            res = fetch_train_list("NDLS", "HWH", "2026-12-01")
        self.assertTrue(res["trains"], "fallback trains should be returned offline")
        self.assertTrue(
            any(t["from"] == "NDLS" and t["to"] == "HWH" for t in res["trains"])
        )
        # Every fallback train carries class chips for the UI.
        for t in res["trains"]:
            self.assertIn("classes", t)
            self.assertTrue(t["classes"])

    def test_offline_unknown_route_returns_empty(self) -> None:
        with mock.patch(
            "bingo_linux.services.train_service.httpx.Client",
            side_effect=Exception("network offline"),
        ):
            res = fetch_train_list("XYZ", "ABC", "2026-12-01")
        self.assertEqual(res["trains"], [])

    def test_train_results_window_displays_fallback_trains(self) -> None:
        with mock.patch(
            "bingo_linux.services.train_service.httpx.Client",
            side_effect=Exception("network offline"),
        ):
            res = fetch_train_list("NDLS", "HWH", "2026-12-01")

        win = TrainResultsWindow()
        try:
            win.set_trains(
                res["trains"],
                {"from": "NDLS", "to": "HWH", "date": "2026-12-01"},
            )
            self.assertEqual(win.table.rowCount(), len(res["trains"]))
            self.assertTrue(win._quota_group.checkedButton() is not None)
        finally:
            win.hide()
            win.deleteLater()


# ---------------------------------------------------------------------------
# Fix 6: Shutdown cleanly closes database and windows
# ---------------------------------------------------------------------------

class TestShutdown(_BaseTestCase):
    """Shutdown must close the database and all windows, idempotently."""

    def test_shutdown_closes_database_and_windows(self) -> None:
        self.controller.create_main_window()
        self.assertIsNotNone(self.controller._db)
        self.controller.shutdown()
        self.assertIsNone(self.controller._db)
        self.controller._main_window.hide()

    def test_shutdown_is_idempotent(self) -> None:
        self.controller.create_main_window()
        self.controller.shutdown()
        # A second shutdown must not raise.
        self.controller.shutdown()
        self.assertIsNone(self.controller._db)


if __name__ == "__main__":
    unittest.main()
