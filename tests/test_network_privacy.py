"""Automated network privacy tests (TASK-008).

Asserts that application startup and window creation generate ZERO
socket/HTTP requests, enforcing the strict default-deny network policy:

- No automatic vendor communications on startup or in the background.
- NewsService is purely local (no remote news fetch).
- UpdateWindow is local-only (no vendor network calls).
- The only remaining network paths (erail.in train search, proxy socket
  test) are user-initiated and are NOT exercised during startup.

These tests monkeypatch the low-level network entry points so that any
attempted socket/HTTP call raises immediately, making a silent network
call a test failure rather than a silent leak.
"""

from __future__ import annotations

import os
import socket
import tempfile
import urllib.request
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])

from bingo_linux.app.application import Application  # noqa: E402
from bingo_linux.database.database import Database  # noqa: E402
from bingo_linux.services.news_service import NewsService  # noqa: E402
from bingo_linux.ui.update_window import UpdateWindow  # noqa: E402

try:  # httpx is an optional dependency used by train_service
    import httpx  # noqa: E402

    _HAVE_HTTPX = True
except ImportError:  # pragma: no cover - environment dependent
    httpx = None
    _HAVE_HTTPX = False

# Network entry points that must remain unused during startup / window creation.
_NETWORK_TARGETS = [
    "socket.socket.connect",
    "socket.create_connection",
    "urllib.request.urlopen",
]


class _NetworkBlocker:
    """Context manager that records and blocks every network call attempt."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def _make_blocker(self, name: str):
        def blocker(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            raise AssertionError(
                f"NETWORK POLICY VIOLATION: {name}{args} attempted; "
                "zero external network calls are allowed on startup/window creation."
            )

        return blocker

    def __enter__(self):
        self._patches = [
            patch("socket.socket.connect", self._make_blocker("socket.socket.connect")),
            patch(
                "socket.create_connection", self._make_blocker("socket.create_connection")
            ),
            patch(
                "urllib.request.urlopen",
                self._make_blocker("urllib.request.urlopen"),
            ),
        ]
        if _HAVE_HTTPX:
            self._patches.append(
                patch(
                    "httpx.Client.get",
                    self._make_blocker("httpx.Client.get"),
                )
            )
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        for p in reversed(self._patches):
            p.stop()
        return False


class TestNetworkPrivacyStartup(unittest.TestCase):
    """Application startup and window creation must perform no network I/O."""

    def setUp(self) -> None:
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)

    def tearDown(self) -> None:
        if self.tmp_path and os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def test_application_startup_zero_network(self) -> None:
        """Constructing Application() and creating the main window makes no network calls."""
        db = Database(db_path=self.tmp_path)
        db.initialize_schema()
        db.close()

        with _NetworkBlocker() as blocker:
            controller = Application()
            controller._db = Database(db_path=self.tmp_path)
            controller._db.initialize_schema()
            main_win = controller.create_main_window()
            controller.shutdown()

        self.assertIsNotNone(main_win)
        self.assertEqual(blocker.calls, [], f"Unexpected network calls: {blocker.calls}")

    def test_news_service_zero_network(self) -> None:
        """NewsService instantiation and queries perform no network calls (purely local)."""
        db = Database(db_path=self.tmp_path)
        db.initialize_schema()

        with _NetworkBlocker() as blocker:
            service = NewsService(db)
            service.get_all_news()
            service.get_unread_news()
            service.unread_count()
            service.has_unread_news()

        db.close()
        self.assertEqual(blocker.calls, [], f"Unexpected network calls: {blocker.calls}")

    def test_update_window_zero_network(self) -> None:
        """UpdateWindow creation performs no network calls (local-only interface)."""
        with _NetworkBlocker() as blocker:
            window = UpdateWindow()
            window.set_state("checking")
            window.set_state("completed", progress=100)
            window.set_local_package("/tmp/kilo/nonexistent-package.bingo")
            self.assertEqual(window.local_package_path(), "/tmp/kilo/nonexistent-package.bingo")
            self.assertFalse(window.verify_local_package())  # local file I/O only, no network
            window.hide()
            window.deleteLater()

        self.assertEqual(blocker.calls, [], f"Unexpected network calls: {blocker.calls}")

    def test_network_blocker_detects_calls(self) -> None:
        """Sanity check: the blocker actually raises on a real socket.connect attempt."""
        with _NetworkBlocker() as blocker:
            with self.assertRaises(AssertionError):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.connect(("example.com", 443))
                finally:
                    s.close()
        self.assertGreaterEqual(len(blocker.calls), 1)


if __name__ == "__main__":
    unittest.main()
