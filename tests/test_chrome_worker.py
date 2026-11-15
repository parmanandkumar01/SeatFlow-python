"""Tests for the Chrome worker service (RT-05 / MW-01..MW-09).

Uses a temporary settings database and a non-existent Chrome binary so no
browser is actually launched. Covers:
- Worker state machine transitions
- Max concurrent worker enforcement
- Start / stop / restart / stop-all
- Profile directory creation and cleanup on reset
- State sync from the booking workflow
- Settings (worker count 1-4, chrome binary path)
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
    SETTING_CHROME_BINARY,
    SETTING_WORKER_COUNT,
    WORKER_COUNT_MAX,
    WORKER_COUNT_MIN,
    SettingsService,
)
from seatflow.services.chrome_worker import (
    WorkerState,
    booking_state_to_worker_state,
)
from seatflow.services.chrome_worker_service import ChromeWorkerService

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class ChromeWorkerStateTestCase(unittest.TestCase):
    """Tests for the worker state machine and helpers."""

    def test_state_enum_values(self) -> None:
        self.assertEqual(WorkerState.IDLE.value, "idle")
        self.assertEqual(WorkerState.READY.value, "ready")
        self.assertEqual(WorkerState.COMPLETED.value, "completed")

    def test_booking_to_worker_mapping(self) -> None:
        self.assertEqual(
            booking_state_to_worker_state("IN_PROGRESS"), WorkerState.READY
        )
        self.assertEqual(
            booking_state_to_worker_state("WAITING_FOR_2FA"),
            WorkerState.AWAITING_2FA,
        )
        self.assertEqual(
            booking_state_to_worker_state("WAITING_FOR_CAPTCHA"),
            WorkerState.AWAITING_CAPTCHA,
        )
        self.assertEqual(
            booking_state_to_worker_state("PAYMENT"), WorkerState.PAYMENT
        )
        self.assertEqual(
            booking_state_to_worker_state("COMPLETED"), WorkerState.COMPLETED
        )
        self.assertEqual(
            booking_state_to_worker_state("FAILED"), WorkerState.FAILED
        )
        self.assertEqual(
            booking_state_to_worker_state("CANCELLED"), WorkerState.CANCELLED
        )
        self.assertEqual(
            booking_state_to_worker_state("IDLE"), WorkerState.IDLE
        )
        self.assertIsNone(booking_state_to_worker_state("UNKNOWN_STATE"))


class ChromeWorkerServiceTestCase(unittest.TestCase):
    """Tests for ChromeWorkerService lifecycle without launching Chrome."""

    def setUp(self) -> None:
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.profiles_root = tempfile.mkdtemp(prefix="bingo_profiles_")
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.vault = VaultService(self.db)
        self.vault.initialize("master-password")
        self.settings = SettingsService(self.db, self.vault)
        # Force a non-existent Chrome binary so no browser is launched.
        self.settings.set_chrome_binary("/nonexistent/chrome-binary")
        self._popen_patch = patch(
            "seatflow.services.chrome_worker.subprocess.Popen",
            side_effect=FileNotFoundError("no such binary"),
        )
        self._popen_patch.start()
        self.service = ChromeWorkerService(
            settings_service=self.settings,
            profiles_root=self.profiles_root,
        )

    def tearDown(self) -> None:
        self._popen_patch.stop()
        try:
            self.service.cleanup()
        except Exception:
            pass
        self.vault.lock()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def test_defaults(self) -> None:
        self.assertEqual(self.service.max_workers, WORKER_COUNT_MIN)
        self.assertEqual(self.settings.get_worker_count(), WORKER_COUNT_MIN)
        self.assertEqual(self.settings.get_chrome_binary(), "/nonexistent/chrome-binary")
        self.assertEqual(len(self.service.list_workers()), 0)

    def test_set_max_workers_range(self) -> None:
        self.service.set_max_workers(3)
        self.assertEqual(self.service.max_workers, 3)
        self.assertEqual(self.settings.get_worker_count(), 3)

    def test_max_workers_enforced(self) -> None:
        self.service.set_max_workers(1)

        class _RunningProc:
            pid = 1234

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

            def terminate(self):
                pass

            def kill(self):
                pass

        # Patch Popen to return a running process so the worker enters READY.
        with patch(
            "seatflow.services.chrome_worker.subprocess.Popen",
            return_value=_RunningProc(),
        ):
            self.assertTrue(self.service.start_worker("ticket_a"))
            # Second worker exceeds the limit.
            self.assertFalse(self.service.start_worker("ticket_b"))
            workers = self.service.list_workers()
            self.assertEqual(len(workers), 1)
            self.assertEqual(workers[0]["ticket_id"], "ticket_a")
            self.assertTrue(workers[0]["is_running"])

            # Stopping the first frees a slot; the second can now start.
            self.assertTrue(self.service.stop_worker("ticket_a"))
            self.assertTrue(self.service.start_worker("ticket_b"))
            self.assertEqual(
                self.service.get_worker("ticket_b").state, WorkerState.READY
            )

    def test_start_worker_fails_without_chrome(self) -> None:
        # Chrome binary does not exist -> worker enters FAILED state.
        result = self.service.start_worker("ticket_x")
        self.assertFalse(result)
        worker = self.service.get_worker("ticket_x")
        self.assertIsNotNone(worker)
        self.assertEqual(worker.state, WorkerState.FAILED)
        self.assertFalse(worker.is_running)

    def test_stop_unknown_worker(self) -> None:
        self.assertFalse(self.service.stop_worker("no_such_ticket"))

    def test_restart_unknown_creates_worker(self) -> None:
        # Restart with no Chrome -> start fails, but a worker object exists.
        self.assertFalse(self.service.restart_worker("ticket_r"))
        worker = self.service.get_worker("ticket_r")
        self.assertIsNotNone(worker)
        self.assertEqual(worker.state, WorkerState.FAILED)

    def test_state_sync_from_booking(self) -> None:
        # Create a worker (will fail to launch chrome but object exists).
        self.service.start_worker("ticket_sync")
        worker = self.service.get_worker("ticket_sync")
        self.assertIsNotNone(worker)

        # Sync a booking state -> worker state transition.
        new_state = self.service.sync_worker_state(
            "ticket_sync", "WAITING_FOR_CAPTCHA"
        )
        self.assertEqual(new_state, WorkerState.AWAITING_CAPTCHA)
        self.assertEqual(worker.state, WorkerState.AWAITING_CAPTCHA)

        # Sync to terminal completed.
        new_state = self.service.sync_worker_state("ticket_sync", "COMPLETED")
        self.assertEqual(new_state, WorkerState.COMPLETED)
        self.assertEqual(worker.state, WorkerState.COMPLETED)

    def test_cleanup_removes_profiles(self) -> None:
        self.service.start_worker("ticket_cleanup")
        worker = self.service.get_worker("ticket_cleanup")
        self.assertIsNotNone(worker)
        profile_dir = worker.profile_dir
        self.assertIsNotNone(profile_dir)
        self.assertTrue(os.path.isdir(profile_dir))

        self.service.cleanup()
        self.assertFalse(os.path.isdir(profile_dir))
        self.assertEqual(len(self.service.list_workers()), 0)

    def test_profile_dir_isolation(self) -> None:
        self.service.set_max_workers(2)
        self.service.start_worker("ticket_a")
        self.service.start_worker("ticket_b")
        wa = self.service.get_worker("ticket_a")
        wb = self.service.get_worker("ticket_b")
        self.assertIsNotNone(wa)
        self.assertIsNotNone(wb)
        self.assertNotEqual(wa.profile_dir, wb.profile_dir)
        # Both dirs exist (even though Chrome failed to launch, profile dir was made).
        self.assertTrue(os.path.isdir(wa.profile_dir))
        self.assertTrue(os.path.isdir(wb.profile_dir))

    def test_worker_count_settings_validation(self) -> None:
        from seatflow.services.settings_service import InvalidSettingError

        with self.assertRaises(InvalidSettingError):
            self.settings.set_worker_count(0)
        with self.assertRaises(InvalidSettingError):
            self.settings.set_worker_count(WORKER_COUNT_MAX + 1)
        self.settings.set_worker_count(WORKER_COUNT_MAX)
        self.assertEqual(self.settings.get_worker_count(), WORKER_COUNT_MAX)


class ChromeWorkerServiceSignalsTestCase(unittest.TestCase):
    """Tests that ChromeWorkerService emits the expected Qt signals."""

    def setUp(self) -> None:
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.profiles_root = tempfile.mkdtemp(prefix="bingo_profiles_")
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.vault = VaultService(self.db)
        self.vault.initialize("master-password")
        self.settings = SettingsService(self.db, self.vault)
        self.settings.set_chrome_binary("/nonexistent/chrome-binary")
        self._popen_patch = patch(
            "seatflow.services.chrome_worker.subprocess.Popen",
            side_effect=FileNotFoundError("no such binary"),
        )
        self._popen_patch.start()
        self.service = ChromeWorkerService(
            settings_service=self.settings,
            profiles_root=self.profiles_root,
        )
        self.states = []
        self.logs = []
        self.started = []
        self.stopped = []
        self.service.worker_state_changed.connect(
            lambda t, o, n: self.states.append((t, o, n))
        )
        self.service.worker_logged.connect(
            lambda t, l, m: self.logs.append((t, l, m))
        )
        self.service.worker_started.connect(lambda t: self.started.append(t))
        self.service.worker_stopped.connect(lambda t: self.stopped.append(t))

    def tearDown(self) -> None:
        self._popen_patch.stop()
        try:
            self.service.cleanup()
        except Exception:
            pass
        self.vault.lock()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def test_signals_emitted(self) -> None:
        self.service.start_worker("ticket_sig")
        # Start fails (no Chrome), so worker_started is not emitted, but the
        # state change to FAILED is.
        self.assertTrue(any(s[0] == "ticket_sig" for s in self.states))
        self.assertTrue(any(l[0] == "ticket_sig" for l in self.logs))
        self.assertEqual(len(self.started), 0)
        self.service.stop_worker("ticket_sig")
        self.assertIn("ticket_sig", self.stopped)
        self.service.cleanup()


if __name__ == "__main__":
    unittest.main()
