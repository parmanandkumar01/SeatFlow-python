"""Tests for the VaultWindow UI (vault.html parity).

Covers:
- Setup mode: password + confirm, "Set up vault" button initializes vault.
- Unlock mode: correct password unlocks, wrong password shows error.
- Wipe data flow: unlock, show wipe confirm, confirm wipe resets vault.
- Quit signal emission.
- UI fields map to vault.html elements (logo, brand, inputs, buttons).

Uses an offscreen QApplication and temporary database. No network I/O.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from PySide6.QtWidgets import QApplication, QLineEdit

from seatflow.database.database import Database
from seatflow.security.vault import VaultService
from seatflow.ui.vault_window import VaultWindow

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class VaultWindowTestCase(unittest.TestCase):
    """Test case for VaultWindow setup / unlock / wipe flows."""

    def setUp(self) -> None:
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.vault = VaultService(self.db)
        self.window: VaultWindow | None = None
        self.unlocked_calls = 0
        self.quit_calls = 0

    def tearDown(self) -> None:
        if self.window is not None:
            self.window.hide()
            self.window.deleteLater()
            self.window = None
        self.vault.lock()
        if self.db is not None:
            self.db.close()
            self.db = None
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_window(self, mode: str = "unlock") -> VaultWindow:
        win = VaultWindow()
        win.set_mode(mode)  # type: ignore[arg-type]
        win.set_vault(self.vault)
        win.unlocked.connect(lambda: setattr(self, "unlocked_calls", self.unlocked_calls + 1))
        win.quit_requested.connect(lambda: setattr(self, "quit_calls", self.quit_calls + 1))
        self.window = win
        return win

    def _enter_password(self, win: VaultWindow, pw: str, confirm: str | None = None) -> None:
        win.pw_edit.setText(pw)
        if confirm is not None:
            win.pw2_edit.setText(confirm)

    # ------------------------------------------------------------------
    # Setup mode
    # ------------------------------------------------------------------

    def test_setup_mode_initializes_vault(self) -> None:
        """Setup mode with matching passwords initializes the vault."""
        win = self._make_window(mode="setup")
        self.assertEqual(win._mode, "setup")
        self.assertEqual(win.title.text(), "Set up your vault")
        self.assertEqual(win.go_btn.text(), "Set up vault")

        self._enter_password(win, "test-master-key", confirm="test-master-key")
        win.go_btn.click()

        self.assertTrue(self.vault.is_configured())
        self.assertTrue(self.vault.is_unlocked())
        self.assertEqual(self.unlocked_calls, 1)

    # ------------------------------------------------------------------
    # Unlock mode
    # ------------------------------------------------------------------

    def test_unlock_mode_correct_password(self) -> None:
        """Unlock mode with correct password unlocks the vault."""
        self.vault.initialize("secret-pw")
        self.assertTrue(self.vault.is_configured())
        self.assertTrue(self.vault.is_unlocked())  # initialize() unlocks

        # Lock it again to test unlock flow
        self.vault.lock()
        self.assertFalse(self.vault.is_unlocked())

        win = self._make_window(mode="unlock")
        self.assertEqual(win._mode, "unlock")
        self.assertEqual(win.title.text(), "Unlock")
        self.assertEqual(win.go_btn.text(), "Unlock")

        self._enter_password(win, "secret-pw")
        win.go_btn.click()

        self.assertTrue(self.vault.is_unlocked())

    def test_unlock_mode_wrong_password(self) -> None:
        """Unlock mode with wrong password does not unlock."""
        self.vault.initialize("secret-pw")
        self.vault.lock()

        win = self._make_window(mode="unlock")
        self._enter_password(win, "wrong-pw")
        win.go_btn.click()

        self.assertFalse(self.vault.is_unlocked())
        self.assertEqual(win.error_lbl.text(), "Invalid master password")

    # ------------------------------------------------------------------
    # Wipe data flow
    # ------------------------------------------------------------------

    def test_wipe_confirm_resets_vault(self) -> None:
        """Confirming wipe resets the vault to unconfigured state."""
        self.vault.initialize("secret-pw")
        self.vault.lock()
        self.assertTrue(self.vault.is_configured())
        self.assertFalse(self.vault.is_unlocked())

        win = self._make_window(mode="unlock")
        self._enter_password(win, "secret-pw")
        win.go_btn.click()
        self.assertTrue(self.vault.is_unlocked())

        # Re-enter password (go_btn clears fields after unlock), then wipe
        self._enter_password(win, "secret-pw")
        win._show_wipe_overlay()  # type: ignore[attr-defined]
        self.assertFalse(win._wipe_dialog.isHidden())  # type: ignore[attr-defined]
        win._wipe_dialog.btn_wipe.click()  # type: ignore[attr-defined]

        self.assertFalse(self.vault.is_configured())
        self.assertFalse(self.vault.is_unlocked())

    def test_wipe_cancel_does_not_reset(self) -> None:
        """Cancelling wipe keeps the vault configured and unlocked."""
        self.vault.initialize("secret-pw")
        self.vault.lock()

        win = self._make_window(mode="unlock")
        self._enter_password(win, "secret-pw")
        win.go_btn.click()
        self.assertTrue(self.vault.is_unlocked())

        win._show_wipe_overlay()  # type: ignore[attr-defined]
        win._wipe_dialog.btn_cancel.click()  # type: ignore[attr-defined]

        self.assertTrue(self.vault.is_configured())
        self.assertTrue(self.vault.is_unlocked())
        self.assertTrue(win._wipe_dialog.isHidden())  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Quit signal
    # ------------------------------------------------------------------

    def test_quit_button_emits_signal(self) -> None:
        """Clicking Quit emits quit_requested."""
        win = self._make_window(mode="unlock")
        win.quit_btn.click()
        self.assertEqual(self.quit_calls, 1)

    # ------------------------------------------------------------------
    # Signals wired
    # ------------------------------------------------------------------

    def test_unlock_signal_emitted_on_success(self) -> None:
        """A successful unlock emits the unlocked signal."""
        self.vault.initialize("secret-pw")
        self.vault.lock()

        win = self._make_window(mode="unlock")
        self._enter_password(win, "secret-pw")
        win.go_btn.click()

        self.assertEqual(self.unlocked_calls, 1)

    # ------------------------------------------------------------------
    # UI elements present
    # ------------------------------------------------------------------

    def test_ui_elements_present(self) -> None:
        """VaultWindow contains all expected UI elements from vault.html."""
        win = self._make_window(mode="unlock")

        # Logo
        self.assertIsNotNone(win.logo.pixmap())
        # Brand
        self.assertEqual(win.brand.text(), "BINGO")
        self.assertIn("Smart Software", win.tagline.text())
        # Inputs
        self.assertEqual(win.pw_edit.placeholderText(), "Password")
        self.assertEqual(win.pw_edit.echoMode(), QLineEdit.EchoMode.Password)
        # Buttons
        self.assertEqual(win.go_btn.text(), "Unlock")
        self.assertEqual(win.quit_btn.text(), "Quit")
        # Error hidden by default
        self.assertEqual(win.error_lbl.text(), "")
        # Reset visible in unlock mode
        self.assertFalse(win.reset_btn.isHidden())


if __name__ == "__main__":
    unittest.main()
