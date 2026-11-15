"""Master Vault Unlock & Setup window matching vault.html layout.

Dual modes:
- setup: first-time launch, create a master password with confirmation.
- unlock: routine launch, enter the existing master password.

UI mirrors the original electron vault.html:
Header (logo + BINGO brand + tagline), body (title, subtitle, password
input with reveal toggle, optional confirm input, error text, primary
action, Quit ghost button, "Forgot password? Reset data" link) and an
in-page modal overlay ("Wipe data?") with Cancel / Wipe data buttons.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seatflow.security.vault import (
    VaultAlreadyConfiguredError,
    InvalidPasswordError,
    VaultLockedError,
    VaultNotConfiguredError,
    VaultService,
)
from seatflow.ui.app_icon import bingo_logo_pixmap
from seatflow.ui.window_drag import enable_window_drag


class _WipeDialog(QFrame):
    """In-page 'Wipe data?' confirmation modal overlay."""

    wipe_confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("vaultWipeDialog")
        self.setStyleSheet("""
            QFrame#vaultWipeDialog {
                background: #0c1e34;
                border: 1px solid #134150;
                border-radius: 10px;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 22, 22, 18)
        lay.setSpacing(12)

        title = QLabel("Wipe data?")
        title.setStyleSheet(
            "font-family: 'Rajdhani', 'Segoe UI', sans-serif; "
            "font-size: 17px; font-weight: 700; color: #ffffff;"
        )
        lay.addWidget(title)

        msg = QLabel(
            "This will permanently delete all your saved IRCTC IDs, "
            "proxies and banks. This cannot be undone."
        )
        msg.setWordWrap(True)
        msg.setStyleSheet(
            "font-size: 13px; color: #94a3b8; line-height: 1.45;"
        )
        lay.addWidget(msg)

        btns = QHBoxLayout()
        btns.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #e2e8f0;
                border: 1px solid transparent;
                border-radius: 6px;
                font-size: 13px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background: #081422;
            }
        """)
        self.btn_cancel.clicked.connect(self.cancelled.emit)

        self.btn_wipe = QPushButton("Wipe data")
        self.btn_wipe.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_wipe.setStyleSheet("""
            QPushButton {
                background: #ef4444;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background: #dc2626;
            }
        """)
        self.btn_wipe.clicked.connect(self.wipe_confirmed.emit)

        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_wipe)
        lay.addLayout(btns)

    def show_overlay(self, parent_rect) -> None:
        self.move(
            parent_rect.center().x() - self.width() // 2,
            parent_rect.center().y() - self.height() // 2,
        )
        self.show()
        self.raise_()

    def hide_overlay(self) -> None:
        self.hide()


class VaultWindow(QWidget):
    """Master vault gate window matching vault.html.

    Signals:
        unlocked: emitted when the vault is initialized or unlocked successfully.
        quit_requested: emitted when the user chooses to quit.
    """

    unlocked = Signal()
    quit_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vault: Optional[VaultService] = None
        self._mode: str = "unlock"

        self.setWindowTitle("SeatFlow — Unlock")
        self.setFixedSize(400, 560)
        self.setObjectName("vaultRoot")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        self._setup_ui()
        self._setup_styles()
        enable_window_drag(self, self.header)

        self._wipe_dialog = _WipeDialog(self)
        self._wipe_dialog.wipe_confirmed.connect(self._on_wipe_confirmed)
        self._wipe_dialog.cancelled.connect(self._wipe_dialog.hide_overlay)
        self._wipe_dialog.hide_overlay()

    # ------------------------------------------------------------------ UI

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.card = QFrame()
        self.card.setObjectName("vaultCard")
        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        # ---- Header ----
        self.header = QFrame()
        self.header.setObjectName("vaultHeader")
        header_lay = QHBoxLayout(self.header)
        header_lay.setContentsMargins(20, 20, 24, 20)
        header_lay.setSpacing(14)

        self.logo = QLabel()
        self.logo.setPixmap(bingo_logo_pixmap(44))
        self.logo.setFixedSize(44, 44)
        header_lay.addWidget(self.logo)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        self.brand = QLabel("BINGO")
        self.brand.setObjectName("vaultBrand")
        self.tagline = QLabel("Smart Software for Smart Users")
        self.tagline.setObjectName("vaultTagline")
        brand_col.addWidget(self.brand)
        brand_col.addWidget(self.tagline)
        header_lay.addLayout(brand_col)
        header_lay.addStretch(1)

        card_lay.addWidget(self.header)

        # ---- Body ----
        self.body = QFrame()
        self.body.setObjectName("vaultBody")
        body_lay = QVBoxLayout(self.body)
        body_lay.setContentsMargins(28, 24, 24, 24)
        body_lay.setSpacing(0)
        body_lay.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )

        self.title = QLabel("Unlock")
        self.title.setObjectName("vaultTitle")
        self.subtitle = QLabel("Enter your password to continue.")
        self.subtitle.setObjectName("vaultSubtitle")
        body_lay.addWidget(self.title)
        body_lay.addWidget(self.subtitle)
        body_lay.addSpacing(10)

        # Password input + reveal toggle
        self.pw_wrap = QFrame()
        self.pw_wrap.setObjectName("pwWrap")
        pw_lay = QVBoxLayout(self.pw_wrap)
        pw_lay.setContentsMargins(0, 0, 0, 0)
        pw_lay.setSpacing(0)

        self.pw_edit = QLineEdit()
        self.pw_edit.setObjectName("bingoInput")
        self.pw_edit.setPlaceholderText("Password")
        self.pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_edit.setFixedHeight(44)
        pw_lay.addWidget(self.pw_edit)

        self.eye_btn = QPushButton()
        self.eye_btn.setObjectName("pwEye")
        self.eye_btn.setFixedSize(44, 44)
        self.eye_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.eye_btn.setText("👁")
        self.eye_btn.setStyleSheet(
            "background: transparent; border: none; font-size: 18px; color: #64748b;"
        )
        self.eye_btn.clicked.connect(self._toggle_eye)
        pw_lay.addWidget(self.eye_btn, alignment=Qt.AlignmentFlag.AlignRight)

        body_lay.addWidget(self.pw_wrap)

        # Confirm password input (setup mode only)
        self.pw2_wrap = QFrame()
        self.pw2_wrap.setObjectName("pw2Wrap")
        pw2_lay = QVBoxLayout(self.pw2_wrap)
        pw2_lay.setContentsMargins(0, 0, 0, 0)
        pw2_lay.setSpacing(0)

        self.pw2_edit = QLineEdit()
        self.pw2_edit.setObjectName("bingoInput")
        self.pw2_edit.setPlaceholderText("Confirm password")
        self.pw2_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw2_edit.setFixedHeight(44)
        pw2_lay.addWidget(self.pw2_edit)

        self.eye2_btn = QPushButton()
        self.eye2_btn.setObjectName("pwEye")
        self.eye2_btn.setFixedSize(44, 44)
        self.eye2_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.eye2_btn.setText("👁")
        self.eye2_btn.setStyleSheet(
            "background: transparent; border: none; font-size: 18px; color: #64748b;"
        )
        self.eye2_btn.clicked.connect(self._toggle_eye2)
        pw2_lay.addWidget(self.eye2_btn, alignment=Qt.AlignmentFlag.AlignRight)

        body_lay.addWidget(self.pw2_wrap)

        # Error text
        self.error_lbl = QLabel("")
        self.error_lbl.setObjectName("vaultError")
        self.error_lbl.hide()
        body_lay.addWidget(self.error_lbl)

        body_lay.addSpacing(6)

        # Primary action button
        self.go_btn = QPushButton("Unlock")
        self.go_btn.setObjectName("goBtn")
        self.go_btn.setFixedHeight(44)
        self.go_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.go_btn.clicked.connect(self._on_go)
        body_lay.addWidget(self.go_btn)

        # Quit ghost button
        self.quit_btn = QPushButton("Quit")
        self.quit_btn.setObjectName("quitBtn")
        self.quit_btn.setFixedHeight(36)
        self.quit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.quit_btn.clicked.connect(self.quit_requested.emit)
        body_lay.addWidget(self.quit_btn)

        body_lay.addSpacing(4)

        # Reset link (unlock mode only)
        self.reset_btn = QPushButton("Forgot password? Reset data")
        self.reset_btn.setObjectName("resetBtn")
        self.reset_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.reset_btn.clicked.connect(self._show_wipe_overlay)
        body_lay.addWidget(self.reset_btn)

        body_lay.addStretch(1)
        card_lay.addWidget(self.body)
        root.addWidget(self.card)

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#vaultRoot {
                background: #091a2b;
            }
            QFrame#vaultCard {
                background: #091a2b;
            }
            QFrame#vaultHeader {
                background: #091a2b;
                border-bottom: 1px solid #134150;
            }
            QLabel#vaultBrand {
                font-family: 'Rajdhani', 'Segoe UI', sans-serif;
                font-size: 22px;
                font-weight: 700;
                letter-spacing: 3px;
                color: #ffffff;
            }
            QLabel#vaultTagline {
                font-size: 10px;
                letter-spacing: 1.2px;
                color: #7c3aed;
                text-transform: uppercase;
                margin-top: 4px;
            }
            QFrame#vaultBody {
                background: #091a2b;
            }
            QLabel#vaultTitle {
                font-family: 'Rajdhani', 'Segoe UI', sans-serif;
                font-size: 20px;
                font-weight: 700;
                color: #e2e8f0;
                letter-spacing: 0.5px;
            }
            QLabel#vaultSubtitle {
                font-size: 13px;
                color: #94a3b8;
                line-height: 1.4;
            }
            QFrame#pwWrap, QFrame#pw2Wrap {
                background: transparent;
            }
            QLineEdit#bingoInput {
                background: #081422;
                color: #ffffff;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                padding: 0 44px 0 12px;
                font-size: 14px;
                selection-background-color: #7c3aed;
            }
            QLineEdit#bingoInput:focus {
                border: 1px solid #7c3aed;
            }
            QLineEdit#bingoInput::placeholder {
                color: #64748b;
            }
            QPushButton#pwEye {
                background: transparent;
                border: none;
                color: #64748b;
                font-size: 18px;
            }
            QPushButton#pwEye:hover {
                color: #7c3aed;
            }
            QLabel#vaultError {
                color: #ef4444;
                font-size: 12px;
            }
            QPushButton#goBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #8b5cf6, stop:1 #5b21b6);
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
                letter-spacing: 1px;
                text-transform: uppercase;
            }
            QPushButton#goBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #a78bfa, stop:1 #6d28d9);
            }
            QPushButton#goBtn:disabled {
                opacity: 0.45;
            }
            QPushButton#quitBtn {
                background: transparent;
                color: #94a3b8;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                text-transform: none;
            }
            QPushButton#quitBtn:hover {
                color: #ffffff;
                background: #081422;
            }
            QPushButton#resetBtn {
                background: transparent;
                color: #94a3b8;
                border: none;
                font-size: 12px;
            }
            QPushButton#resetBtn:hover {
                color: #ef4444;
            }
        """)

    # ------------------------------------------------------------------ mode

    def set_mode(self, mode: str) -> None:
        """Set gate mode: 'setup' or 'unlock'."""
        if mode not in ("setup", "unlock"):
            raise ValueError(f"Invalid vault mode: {mode}")
        self._mode = mode
        if mode == "setup":
            self.setWindowTitle("SeatFlow — Set up")
            self.title.setText("Set up your vault")
            self.subtitle.setText(
                "Create a master password to protect your data."
            )
            self.go_btn.setText("Set up vault")
            self.pw2_wrap.show()
            self.reset_btn.hide()
        else:
            self.setWindowTitle("SeatFlow — Unlock")
            self.title.setText("Unlock")
            self.subtitle.setText("Enter your password to continue.")
            self.go_btn.setText("Unlock")
            self.pw2_wrap.hide()
            self.reset_btn.show()
        self._clear_error()
        self.pw_edit.clear()
        self.pw2_edit.clear()

    # ------------------------------------------------------------------ vault wiring

    def set_vault(self, vault: Optional[VaultService]) -> None:
        """Attach the VaultService to this gate."""
        self._vault = vault

    # ------------------------------------------------------------------ actions

    def _toggle_eye(self) -> None:
        if self.pw_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.pw_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.eye_btn.setText("🙈")
        else:
            self.pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.eye_btn.setText("👁")

    def _toggle_eye2(self) -> None:
        if self.pw2_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.pw2_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.eye2_btn.setText("🙈")
        else:
            self.pw2_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.eye2_btn.setText("👁")

    def _show_error(self, message: str) -> None:
        self.error_lbl.setText(message)
        self.error_lbl.show()

    def _clear_error(self) -> None:
        self.error_lbl.hide()
        self.error_lbl.setText("")

    def _show_wipe_overlay(self) -> None:
        self._wipe_dialog.show_overlay(self.card.rect())

    def _on_wipe_confirmed(self) -> None:
        self._wipe_dialog.hide_overlay()
        vault = self._vault
        if vault is None:
            return
        password = self.pw_edit.text().strip()
        if not password:
            self._show_error("Enter your current password to wipe data.")
            return
        try:
            vault.reset(password)
        except (VaultNotConfiguredError, VaultLockedError, InvalidPasswordError):
            self._show_error("Invalid master password")
            return
        except Exception:
            self._show_error("Reset failed")
            return
        self._clear_error()
        self.pw_edit.clear()
        # After wipe, vault is unconfigured: return to setup mode
        self.set_mode("setup")
        self.unlocked.emit()

    def _on_go(self) -> None:
        vault = self._vault
        if vault is None:
            self._show_error("Vault service unavailable")
            return

        password = self.pw_edit.text().strip()
        if not password:
            self._show_error("Password must not be empty")
            return

        self._clear_error()

        try:
            if self._mode == "setup":
                confirm = self.pw2_edit.text().strip()
                if not confirm:
                    self._show_error("Please confirm your password")
                    return
                if password != confirm:
                    self._show_error("Passwords do not match")
                    return
                vault.initialize(password)
            else:
                vault.unlock(password)
        except VaultAlreadyConfiguredError:
            self._show_error("Vault is already set up")
            return
        except (InvalidPasswordError, VaultNotConfiguredError, VaultLockedError) as exc:
            self._show_error(str(exc) or "Invalid master password")
            return
        except Exception:
            self._show_error("Operation failed")
            return

        self.pw_edit.clear()
        self.pw2_edit.clear()
        self.unlocked.emit()
