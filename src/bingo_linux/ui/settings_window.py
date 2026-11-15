"""Settings popup window for Bingo Linux."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bingo_linux.ui.app_icon import apply_bingo_icon
from bingo_linux.ui.window_drag import enable_window_drag


class SettingsWindow(QWidget):
    """Settings popup menu window."""

    proxy_clicked = Signal()
    freecharge_clicked = Signal()
    backup_restore_clicked = Signal()
    cleanup_clicked = Signal()
    manual_login_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("Settings")
        self.setFixedWidth(280)
        self.setObjectName("settingsRoot")
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self._setup_ui()
        self._setup_styles()
        enable_window_drag(self, self.head_frame)

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("settingsCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        # Header
        self.head_frame = QFrame()
        hl = QHBoxLayout(self.head_frame)
        hl.setContentsMargins(4, 2, 4, 2)

        title_lbl = QLabel("SETTINGS")
        title_lbl.setObjectName("settingsTitle")
        hl.addWidget(title_lbl)

        hl.addStretch(1)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("settingsClose")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.clicked.connect(self.hide)
        hl.addWidget(self.btn_close)

        lay.addWidget(self.head_frame)

        # Automation
        sub1 = QLabel("AUTOMATION")
        sub1.setObjectName("settingsSub")
        lay.addWidget(sub1)

        self.chk_manual = QCheckBox("Manual Login")
        self.chk_manual.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.chk_manual.toggled.connect(self.manual_login_changed.emit)
        lay.addWidget(self.chk_manual)

        # Network
        sub2 = QLabel("NETWORK")
        sub2.setObjectName("settingsSub")
        lay.addWidget(sub2)

        btn_proxy = self._make_menu_btn("🌐  Proxy Settings", self.proxy_clicked.emit)
        lay.addWidget(btn_proxy)

        btn_fc = self._make_menu_btn("⚡  FreeCharge Gateway", self.freecharge_clicked.emit)
        lay.addWidget(btn_fc)

        # Data & Security
        sub3 = QLabel("DATA & BACKUP")
        sub3.setObjectName("settingsSub")
        lay.addWidget(sub3)

        btn_backup = self._make_menu_btn("💾  Backup & Restore (.bingo)", self.backup_restore_clicked.emit)
        lay.addWidget(btn_backup)

        btn_clean = self._make_menu_btn("🧹  Clear Application Cache", self.cleanup_clicked.emit)
        lay.addWidget(btn_clean)

        outer.addWidget(card)

    def _make_menu_btn(self, label: str, callback) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("settingsItem")
        btn.setFixedHeight(34)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.clicked.connect(lambda: (self.hide(), callback()))
        return btn

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#settingsRoot {
                background: transparent;
            }
            QFrame#settingsCard {
                background: #091a2b;
                border: 1px solid #1e3a5f;
                border-radius: 10px;
            }
            QLabel#settingsTitle {
                color: #ffffff;
                font-weight: 800;
                font-size: 13px;
                letter-spacing: 0.5px;
            }
            QPushButton#settingsClose {
                background: transparent;
                color: #94a3b8;
                border: none;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton#settingsClose:hover {
                color: #ef4444;
            }
            QLabel#settingsSub {
                color: #38bdf8;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.5px;
                margin-top: 4px;
            }
            QCheckBox {
                color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                padding: 4px 6px;
            }
            QPushButton#settingsItem {
                background: #0d2238;
                color: #e2e8f0;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                text-align: left;
                padding-left: 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#settingsItem:hover {
                background: #143048;
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)


def place_settings_near_button(win: QWidget, btn: QPushButton) -> None:
    """Position settings popup right below or above the button."""
    pos = btn.mapToGlobal(btn.rect().bottomLeft())
    win.move(pos.x(), pos.y() + 6)
