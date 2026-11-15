"""Tests for the UpdateWindow (update.html parity).

Covers:
- State transitions: checking, downloading, installing, restarting, completed, failed
- Status text and sub-status updates
- Progress bar show/hide and value updates
- Spinner show/hide per state
- Signal emission per state
- UI elements present (logo, brand, title, status, spinner, progress bar)

Uses an offscreen QApplication. No network I/O.
"""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication

from bingo_linux.ui.update_window import UpdateWindow, UpdateState

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class UpdateWindowTestCase(unittest.TestCase):
    """Test case for UpdateWindow state machine and UI."""

    def setUp(self) -> None:
        self.window = UpdateWindow()
        self.signals = {
            "checking": 0,
            "downloading": 0,
            "installing": 0,
            "restarting": 0,
            "completed": 0,
            "failed": 0,
        }
        self.window.checking.connect(lambda: self.signals.__setitem__("checking", self.signals["checking"] + 1))
        self.window.downloading.connect(lambda: self.signals.__setitem__("downloading", self.signals["downloading"] + 1))
        self.window.installing.connect(lambda: self.signals.__setitem__("installing", self.signals["installing"] + 1))
        self.window.restarting.connect(lambda: self.signals.__setitem__("restarting", self.signals["restarting"] + 1))
        self.window.completed.connect(lambda: self.signals.__setitem__("completed", self.signals["completed"] + 1))
        self.window.failed.connect(lambda _: self.signals.__setitem__("failed", self.signals["failed"] + 1))

    def tearDown(self) -> None:
        self.window.hide()
        self.window.deleteLater()
        self.window = None

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def test_initial_state_is_checking(self) -> None:
        """Window starts in checking state."""
        self.assertEqual(self.window.state(), "checking")
        self.assertEqual(self.window.status_lbl.text(), "Checking for updates…")

    def test_set_state_downloading(self) -> None:
        """Transition to downloading shows progress bar and spinner."""
        self.window.set_state("downloading", progress=0)
        self.assertEqual(self.window.state(), "downloading")
        self.assertFalse(self.window.bar_wrap.isHidden())
        self.assertFalse(self.window.spinner.isHidden())
        self.assertEqual(self.window.progress(), 0)

    def test_set_state_installing(self) -> None:
        """Transition to installing shows progress bar and spinner."""
        self.window.set_state("installing", progress=50)
        self.assertEqual(self.window.state(), "installing")
        self.assertFalse(self.window.bar_wrap.isHidden())
        self.assertFalse(self.window.spinner.isHidden())
        self.assertEqual(self.window.progress(), 50)

    def test_set_state_restarting(self) -> None:
        """Transition to restarting hides progress bar and spinner."""
        self.window.set_state("restarting")
        self.assertEqual(self.window.state(), "restarting")
        self.assertTrue(self.window.bar_wrap.isHidden())
        self.assertTrue(self.window.spinner.isHidden())

    def test_set_state_completed(self) -> None:
        """Transition to completed hides progress bar, shows at 100%."""
        self.window.set_state("completed", progress=100)
        self.assertEqual(self.window.state(), "completed")
        self.assertTrue(self.window.bar_wrap.isHidden())
        self.assertTrue(self.window.spinner.isHidden())
        self.assertEqual(self.window.progress(), 100)

    def test_set_state_failed(self) -> None:
        """Transition to failed shows error status."""
        self.window.set_state("failed", status="Network error")
        self.assertEqual(self.window.state(), "failed")
        self.assertEqual(self.window.status_lbl.text(), "Network error")

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def test_set_progress(self) -> None:
        """set_progress updates the progress bar value."""
        self.window.set_state("downloading")
        self.window.set_progress(42)
        self.assertEqual(self.window.progress(), 42)

    def test_set_progress_clamps(self) -> None:
        """set_progress clamps values outside 0-100."""
        self.window.set_state("downloading")
        self.window.set_progress(-10)
        self.assertEqual(self.window.progress(), 0)
        self.window.set_progress(150)
        self.assertEqual(self.window.progress(), 100)

    # ------------------------------------------------------------------
    # Sub-status
    # ------------------------------------------------------------------

    def test_set_sub_status(self) -> None:
        """set_sub_status updates the sub-status label."""
        self.window.set_sub_status("2.4 MB/s · ETA 0:45")
        self.assertEqual(self.window.sub_lbl.text(), "2.4 MB/s · ETA 0:45")

    # ------------------------------------------------------------------
    # Convenience lifecycle methods
    # ------------------------------------------------------------------

    def test_start_checking(self) -> None:
        """start_checking sets state and emits checking signal."""
        self.window.set_state("installing")
        self.window.start_checking()
        self.assertEqual(self.window.state(), "checking")
        self.assertEqual(self.signals["checking"], 1)

    def test_start_downloading(self) -> None:
        """start_downloading sets state and emits downloading signal."""
        self.window.start_downloading()
        self.assertEqual(self.window.state(), "downloading")
        self.assertEqual(self.signals["downloading"], 1)

    def test_start_installing(self) -> None:
        """start_installing sets state and emits installing signal."""
        self.window.start_installing()
        self.assertEqual(self.window.state(), "installing")
        self.assertEqual(self.signals["installing"], 1)

    def test_start_restarting(self) -> None:
        """start_restarting sets state and emits restarting signal."""
        self.window.start_restarting()
        self.assertEqual(self.window.state(), "restarting")
        self.assertEqual(self.signals["restarting"], 1)

    def test_mark_completed(self) -> None:
        """mark_completed sets state to completed and emits signal."""
        self.window.mark_completed()
        self.assertEqual(self.window.state(), "completed")
        self.assertEqual(self.signals["completed"], 1)

    def test_mark_failed(self) -> None:
        """mark_failed sets state to failed and emits signal with reason."""
        self.window.mark_failed("Server unreachable")
        self.assertEqual(self.window.state(), "failed")
        self.assertEqual(self.signals["failed"], 1)
        self.assertEqual(self.window.status_lbl.text(), "Server unreachable")

    # ------------------------------------------------------------------
    # Signal emission
    # ------------------------------------------------------------------

    def test_state_signals_emitted(self) -> None:
        """Each state transition emits the corresponding signal."""
        self.window.start_checking()
        self.window.start_downloading()
        self.window.start_installing()
        self.window.start_restarting()
        self.window.mark_completed()
        self.assertEqual(self.signals["checking"], 1)
        self.assertEqual(self.signals["downloading"], 1)
        self.assertEqual(self.signals["installing"], 1)
        self.assertEqual(self.signals["restarting"], 1)
        self.assertEqual(self.signals["completed"], 1)
        self.assertEqual(self.signals["failed"], 0)

    # ------------------------------------------------------------------
    # UI elements present
    # ------------------------------------------------------------------

    def test_ui_elements_present(self) -> None:
        """UpdateWindow contains all expected UI elements from update.html."""
        # Logo
        self.assertIsNotNone(self.window.logo_lbl.pixmap())
        # Brand
        self.assertEqual(self.window.brand_lbl.text(), "BINGO")
        self.assertIn("Smart Software", self.window.tagline_lbl.text())
        # Title
        self.assertEqual(self.window.title_lbl.text(), "Updater")
        # Status
        self.assertEqual(self.window.status_lbl.text(), "Checking for updates…")
        # Spinner present
        self.assertIsNotNone(self.window.spinner)
        # Progress bar present and hidden initially
        self.assertIsNotNone(self.window.progress_bar)
        self.assertTrue(self.window.bar_wrap.isHidden())


if __name__ == "__main__":
    unittest.main()
