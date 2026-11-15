"""Tests for Browser Extension Bridge integration with Application and SettingsService.

Covers:
- bridge_enabled setting get/set/persistence
- Application bridge toggle (enable/disable)
- NativeHost creation when enabled, None when disabled
- Extension message routing into booking workflow
- Graceful fallback when bridge disabled

Uses temporary databases and mock objects only. No network I/O.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from seatflow.database.database import Database
from seatflow.security.vault import VaultService
from seatflow.services import (
    SettingsService,
    SETTING_BRIDGE_ENABLED,
    SUPPORTED_KEYS,
)
from seatflow.integrations.native_host import NativeHost

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class BridgeSettingsTestCase(unittest.TestCase):
    """Tests for the bridge_enabled setting."""

    def setUp(self) -> None:
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.vault = VaultService(self.db)
        self.vault.initialize("master-password")
        self.settings = SettingsService(self.db, self.vault)

    def tearDown(self) -> None:
        self.vault.lock()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def test_default_bridge_disabled(self) -> None:
        self.assertFalse(self.settings.get_bridge_enabled())

    def test_set_and_get_bridge_enabled(self) -> None:
        self.settings.set_bridge_enabled(True)
        self.assertTrue(self.settings.get_bridge_enabled())
        self.settings.set_bridge_enabled(False)
        self.assertFalse(self.settings.get_bridge_enabled())

    def test_bridge_enabled_in_supported_keys(self) -> None:
        self.assertIn(SETTING_BRIDGE_ENABLED, SUPPORTED_KEYS)

    def test_bridge_enabled_persists(self) -> None:
        self.settings.set_bridge_enabled(True)
        new_service = SettingsService(self.db, self.vault)
        self.assertTrue(new_service.get_bridge_enabled())

    def test_invalid_bridge_value_raises(self) -> None:
        from seatflow.services.settings_service import InvalidSettingError
        with self.assertRaises(InvalidSettingError):
            self.settings.set_setting(SETTING_BRIDGE_ENABLED, "maybe")


class BridgeApplicationTestCase(unittest.TestCase):
    """Tests for bridge wiring in Application."""

    def setUp(self) -> None:
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()

        # Minimal mock application-like object
        from seatflow.app.application import Application
        self.app = Application()
        self.app._db = self.db
        self.app._bridge_enabled = False
        self.app._native_host = None

    def tearDown(self) -> None:
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def test_bridge_defaults_disabled(self) -> None:
        self.assertFalse(self.app._bridge_enabled)
        self.assertIsNone(self.app._native_host)

    def test_on_bridge_toggled_creates_host(self) -> None:
        self.app._settings_service = MagicMock()
        self.app._settings_service.get_bridge_enabled.return_value = True
        self.app._on_bridge_toggled(True)
        self.assertTrue(self.app._bridge_enabled)
        self.assertIsInstance(self.app._native_host, NativeHost)
        self.app._settings_service.set_bridge_enabled.assert_called_with(True)

    def test_on_bridge_toggled_disabled_clears_host(self) -> None:
        self.app._settings_service = MagicMock()
        self.app._settings_service.get_bridge_enabled.return_value = False
        # First enable
        self.app._native_host = NativeHost()
        self.app._bridge_enabled = True
        self.app._on_bridge_toggled(False)
        self.assertFalse(self.app._bridge_enabled)
        self.assertIsNone(self.app._native_host)

    def test_route_extension_message_captcha(self) -> None:
        self.app._booking_service = MagicMock()
        self.app._native_host = NativeHost(router=self.app._route_extension_message)
        # Avoid modal dialogs: stub the dialog-handling methods.
        self.app._on_booking_waiting_for_captcha = MagicMock()
        response = self.app._route_extension_message({
            "type": "captcha_detected",
            "payload": {"stage": "captcha", "page": "booking"},
            "session_id": "sess_1",
        })
        self.assertEqual(response["status"], "ok")
        self.app._on_booking_waiting_for_captcha.assert_called_once()

    def test_route_extension_message_otp(self) -> None:
        self.app._booking_service = MagicMock()
        self.app._native_host = NativeHost(router=self.app._route_extension_message)
        self.app._on_booking_waiting_for_2fa = MagicMock()
        response = self.app._route_extension_message({
            "type": "otp_prompt",
            "payload": {"stage": "login", "channel": "sms"},
            "session_id": "sess_1",
        })
        self.assertEqual(response["status"], "ok")
        self.app._on_booking_waiting_for_2fa.assert_called_once()

    def test_route_extension_message_payment_page(self) -> None:
        self.app._booking_service = MagicMock()
        self.app._native_host = NativeHost(router=self.app._route_extension_message)
        self.app._on_booking_waiting_for_fare = MagicMock()
        response = self.app._route_extension_message({
            "type": "payment_page",
            "payload": {"stage": "payment", "gateway": "UPI"},
            "session_id": "sess_1",
        })
        self.assertEqual(response["status"], "ok")
        self.app._on_booking_waiting_for_fare.assert_called_once()

    def test_route_extension_message_pnr_received(self) -> None:
        self.app._booking_service = MagicMock()
        self.app._native_host = NativeHost(router=self.app._route_extension_message)
        response = self.app._route_extension_message({
            "type": "pnr_received",
            "payload": {"pnr": "ABCD1234", "fare_amount": 500.0},
            "session_id": "sess_1",
        })
        self.assertEqual(response["status"], "ok")
        self.app._booking_service.confirm_payment.assert_called_with("ABCD1234", fare_amount=500.0)

    def test_route_extension_message_unknown_type(self) -> None:
        self.app._native_host = NativeHost(router=self.app._route_extension_message)
        response = self.app._route_extension_message({
            "type": "unknown_type",
            "payload": {},
            "session_id": "sess_1",
        })
        self.assertEqual(response["status"], "error")

    def test_send_open_booking_when_disabled_falls_back(self) -> None:
        self.app._ticket_service = MagicMock()
        self.app._ticket_service.get_ticket.return_value = {
            "train_number": "12345",
            "from_station": "BWC",
            "to_station": "NDLS",
            "journey_date": "2026-12-01",
            "class": "3A",
            "quota": "GN",
        }
        self.app._booking_service = MagicMock()
        self.app._booking_service.session = {"session_id": "sess_1"}
        self.app._bridge_enabled = False
        self.app._native_host = None
        # Should not raise; no open_booking sent when disabled.
        self.app._send_open_booking("ticket_1")

    def test_send_open_booking_when_enabled(self) -> None:
        self.app._ticket_service = MagicMock()
        self.app._ticket_service.get_ticket.return_value = {
            "train_number": "12345",
            "from_station": "BWC",
            "to_station": "NDLS",
            "journey_date": "2026-12-01",
            "class": "3A",
            "quota": "GN",
        }
        self.app._booking_service = MagicMock()
        self.app._booking_service.session = {"session_id": "sess_1"}
        self.app._bridge_enabled = True
        mock_host = MagicMock(spec=NativeHost)
        self.app._native_host = mock_host
        self.app._send_open_booking("ticket_1")
        mock_host.make_outbound.assert_called_once()
        mock_host.write_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
