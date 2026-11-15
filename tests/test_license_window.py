"""Tests for the License / about window (M-01, traceable to original license.html).

The original renderer bundle (`license-BCJsqfw2.js`) is obfuscated and its
exact license text is not recoverable, so this test verifies the window
identity, title, and that it shows/hides without error rather than any
specific license wording (which is deliberately not fabricated).
"""

from __future__ import annotations

import unittest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from seatflow.ui.license_window import LicenseWindow

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class LicenseWindowTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.win = LicenseWindow()

    def tearDown(self) -> None:
        self.win.hide()
        self.win.deleteLater()

    def test_title_matches_original(self) -> None:
        self.assertEqual(self.win.windowTitle(), "SeatFlow · License")

    def test_window_is_frameless_tool(self) -> None:
        flags = self.win.windowFlags()
        self.assertTrue(flags & Qt.WindowType.Tool)
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)

    def test_contains_app_identity_and_version(self) -> None:
        labels = self.win.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        self.assertIn("SeatFlow", texts)
        self.assertIn("Version 0.1.0", texts)

    def test_show_and_hide(self) -> None:
        self.win.show()
        self.assertTrue(self.win.isVisible())
        self.win.hide()
        self.assertFalse(self.win.isVisible())

    def test_close_button_hides(self) -> None:
        self.win.show()
        close_btn = self.win.findChild(QPushButton, "licenseClose")
        self.assertIsNotNone(close_btn)
        close_btn.click()
        self.assertFalse(self.win.isVisible())


if __name__ == "__main__":
    unittest.main()
