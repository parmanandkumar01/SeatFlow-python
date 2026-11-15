"""Tests for PnrSyncService (RT-06).

All network calls are mocked; no live endpoint is contacted. The erail.in
PNR endpoint contract is not recovered, so these tests verify the
documented integration interface (configurable endpoint, rate limiting,
single-PNR lookup, offline handling, bot-challenge stop) without fabricating
live PNR data.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from seatflow.database.database import Database
from seatflow.security.vault import VaultService
from seatflow.services import (
    InvalidSettingError,
    PNR_STATUS_BOOKED,
    PNR_STATUS_CANCELLED,
    PNR_STATUS_FAILED,
    PNR_STATUS_PENDING,
    PnrService,
    SettingsService,
)
from seatflow.services.pnr_sync_service import PnrSyncService

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])


def _make_service():
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)
    db = Database(db_path=tmp_path)
    db.initialize_schema()
    vault = VaultService(db)
    vault.initialize("master-password")
    settings = SettingsService(db, vault)
    pnr_service = PnrService(db)
    sync_service = PnrSyncService(settings_service=settings, pnr_service=pnr_service)
    return tmp_path, db, vault, settings, pnr_service, sync_service


def _cleanup(tmp_path, db, vault):
    try:
        vault.lock()
    except Exception:
        pass
    db.close()
    if tmp_path and os.path.exists(tmp_path):
        os.unlink(tmp_path)


class PnrSyncSettingsTestCase(unittest.TestCase):
    """Tests for PNR sync settings validation."""

    def test_endpoint_url_default_empty(self) -> None:
        tmp_path, db, vault, settings, _, _ = _make_service()
        try:
            self.assertEqual(settings.get_pnr_endpoint_url(), "")
            self.assertFalse(settings.get_pnr_endpoint_url().strip())
        finally:
            _cleanup(tmp_path, db, vault)

    def test_endpoint_url_valid_https(self) -> None:
        tmp_path, db, vault, settings, _, _ = _make_service()
        try:
            settings.set_pnr_endpoint_url("https://example.com/pnr")
            self.assertEqual(
                settings.get_pnr_endpoint_url(), "https://example.com/pnr"
            )
        finally:
            _cleanup(tmp_path, db, vault)

    def test_endpoint_url_invalid_rejected(self) -> None:
        tmp_path, db, vault, settings, _, _ = _make_service()
        try:
            with self.assertRaises(InvalidSettingError):
                settings.set_pnr_endpoint_url("not-a-url")
            with self.assertRaises(InvalidSettingError):
                settings.set_pnr_endpoint_url("ftp://example.com/x")
        finally:
            _cleanup(tmp_path, db, vault)

    def test_cooldown_default_and_range(self) -> None:
        tmp_path, db, vault, settings, _, _ = _make_service()
        try:
            self.assertEqual(settings.get_pnr_cooldown_seconds(), 60)
            settings.set_pnr_cooldown_seconds(120)
            self.assertEqual(settings.get_pnr_cooldown_seconds(), 120)
            with self.assertRaises(InvalidSettingError):
                settings.set_pnr_cooldown_seconds(-1)
            with self.assertRaises(InvalidSettingError):
                settings.set_pnr_cooldown_seconds(9999)
        finally:
            _cleanup(tmp_path, db, vault)


class PnrSyncServiceTestCase(unittest.TestCase):
    """Tests for PnrSyncService behavior with mocked lookups."""

    def setUp(self) -> None:
        (self.tmp_path, self.db, self.vault, self.settings,
         self.pnr_service, self.sync_service) = _make_service()

    def tearDown(self) -> None:
        _cleanup(self.tmp_path, self.db, self.vault)

    def _mock_lookup(self, response: dict) -> None:
        self.sync_service._perform_lookup = lambda pnr: response  # type: ignore

    def test_endpoint_not_configured(self) -> None:
        self.assertFalse(self.sync_service.is_endpoint_configured())
        result = self.sync_service.refresh_pnr("123456")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "endpoint_not_configured")
        self.assertTrue(result["endpoint_not_configured"])
        self.assertIn("not configured", result["message"])

    def test_invalid_pnr_rejected(self) -> None:
        self.settings.set_pnr_endpoint_url("https://example.com/pnr")
        result = self.sync_service.refresh_pnr("abc")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_pnr")

    def test_cooldown_enforced(self) -> None:
        self.settings.set_pnr_endpoint_url("https://example.com/pnr")
        self._mock_lookup({
            "text": json_ok("123456", "CNF", "12345"),
            "status_code": 200,
        })
        r1 = self.sync_service.refresh_pnr("123456")
        self.assertTrue(r1["ok"])
        # Immediate repeat -> cooldown.
        r2 = self.sync_service.refresh_pnr("123456")
        self.assertFalse(r2["ok"])
        self.assertEqual(r2["error"], "cooldown")
        self.assertGreater(r2["cooldown_remaining"], 0)

    def test_successful_refresh_persists_and_detects_change(self) -> None:
        self.settings.set_pnr_endpoint_url("https://example.com/pnr")
        self._mock_lookup({
            "text": json_ok("123456", "CNF", "12345", "2026-12-01", "3A", "1200"),
            "status_code": 200,
        })
        r1 = self.sync_service.refresh_pnr("123456")
        self.assertTrue(r1["ok"])
        self.assertEqual(r1["status"], PNR_STATUS_BOOKED)
        self.assertEqual(r1["train_number"], "12345")
        self.assertEqual(r1["fare_amount"], 1200)
        self.assertFalse(r1["status_changed"])  # first time, no previous

        # Second refresh with a different status -> status_changed True.
        self._mock_lookup({
            "text": json_ok("123456", "WL", "12345", "2026-12-01", "3A", "1200"),
            "status_code": 200,
        })
        # Bump the clock past cooldown by patching time via cooldown=0.
        self.settings.set_pnr_cooldown_seconds(0)
        r2 = self.sync_service.refresh_pnr("123456")
        self.assertTrue(r2["ok"])
        self.assertEqual(r2["status"], PNR_STATUS_PENDING)  # WL -> pending
        self.assertTrue(r2["status_changed"])
        self.assertEqual(r2["previous_status"], PNR_STATUS_BOOKED)

    def test_bot_challenge_stops(self) -> None:
        self.settings.set_pnr_endpoint_url("https://example.com/pnr")
        self._mock_lookup({
            "text": '{"captcha": true}',
            "status_code": 200,
            "bot_challenge": True,
        })
        result = self.sync_service.refresh_pnr("123456")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "bot_challenge")
        self.assertTrue(result["manual_verification_required"])
        self.assertIn("CAPTCHA", result["message"])

    def test_rate_limited_backs_off(self) -> None:
        self.settings.set_pnr_endpoint_url("https://example.com/pnr")
        self._mock_lookup({
            "text": "",
            "status_code": 429,
            "rate_limited": True,
            "retry_after": 30,
        })
        result = self.sync_service.refresh_pnr("123456")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "rate_limited")
        self.assertEqual(result["cooldown_remaining"], 30)

    def test_non_json_response_unparseable(self) -> None:
        self.settings.set_pnr_endpoint_url("https://example.com/pnr")
        self._mock_lookup({
            "text": "<html><body>CAPTCHA verification required</body></html>",
            "status_code": 200,
        })
        result = self.sync_service.refresh_pnr("123456")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "unparseable")

    def test_normalize_status_mapping(self) -> None:
        svc = self.sync_service
        self.assertEqual(svc._normalize_status("CNF"), PNR_STATUS_BOOKED)
        self.assertEqual(svc._normalize_status("confirmed"), PNR_STATUS_BOOKED)
        self.assertEqual(svc._normalize_status("chart prepared"), PNR_STATUS_BOOKED)
        self.assertEqual(svc._normalize_status("RAC"), PNR_STATUS_PENDING)
        self.assertEqual(svc._normalize_status("WL"), PNR_STATUS_PENDING)
        self.assertEqual(svc._normalize_status("Cancelled"), PNR_STATUS_CANCELLED)
        self.assertEqual(svc._normalize_status("failed"), PNR_STATUS_FAILED)
        self.assertEqual(svc._normalize_status(""), PNR_STATUS_PENDING)


def json_ok(pnr, status, train, date="2026-12-01", cls="3A", fare="1200"):
    import json

    return json.dumps({
        "pnr": pnr,
        "status": status,
        "train_number": train,
        "date": date,
        "class": cls,
        "fare_amount": fare,
        "chart_status": "Prepared",
    })


if __name__ == "__main__":
    unittest.main()
