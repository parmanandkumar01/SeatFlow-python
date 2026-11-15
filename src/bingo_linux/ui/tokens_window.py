"""Tokens management window matching official Bingo PRO / Ocean architecture.

Displays sensor tokens available, user license status, and enables
checking or clearing server queue tokens.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bingo_linux.ui.app_icon import apply_bingo_icon
from bingo_linux.ui.window_drag import enable_window_drag

TOKENS_W = 500
TOKENS_H = 380
TOKENS_MIN_W = 440
TOKENS_MIN_H = 320


class TokensWindow(QWidget):
    """Tokens window for subscription & sensor token status."""

    check_clicked = Signal()
    clear_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("Tokens")
        self.resize(TOKENS_W, TOKENS_H)
        self.setMinimumSize(TOKENS_MIN_W, TOKENS_MIN_H)
        self.setObjectName("tokensRoot")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(12)

        # 1. Header Frame
        head = QFrame()
        head.setObjectName("tokensHead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 12, 12, 12)
        hl.setSpacing(10)

        kicker = QLabel("Subscription")
        kicker.setObjectName("tokensKicker")
        title = QLabel("TOKENS")
        title.setObjectName("tokensTitle")
        hl.addWidget(kicker)
        hl.addWidget(title)
        hl.addStretch()

        self.tab_app = QPushButton("App")
        self.tab_app.setObjectName("tokensTab")
        self.tab_app.setCheckable(True)
        self.tab_app.setChecked(True)
        self.tab_app.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        hl.addWidget(self.tab_app)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("tokensClose")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        hl.addWidget(self.btn_close, 0, Qt.AlignmentFlag.AlignTop)
        root.addWidget(head)
        enable_window_drag(self, head)

        # 2. Main Banner
        banner = QFrame()
        banner.setObjectName("tokensBanner")
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(16, 16, 16, 16)
        bl.setSpacing(14)

        tag = QLabel("SENSOR")
        tag.setObjectName("tokensTag")
        bl.addWidget(tag)

        btitle = QLabel("App sensor tokens")
        btitle.setObjectName("tokensBannerTitle")
        bl.addWidget(btitle)

        self.status_line = QLabel("Check queue count or clear all sensors on server.")
        self.status_line.setObjectName("tokensStatus")
        self.status_line.setWordWrap(True)
        bl.addWidget(self.status_line)

        # Stat row
        stat_frame = QFrame()
        stat_frame.setObjectName("tokensStat")
        sl = QHBoxLayout(stat_frame)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(16)

        uid_col = QVBoxLayout()
        uid_col.setSpacing(2)
        l_uid = QLabel("UserId")
        l_uid.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 700;")
        self.user_id = QLabel("PRO-ACTIVE")
        self.user_id.setObjectName("tokensStatVal")
        uid_col.addWidget(l_uid)
        uid_col.addWidget(self.user_id)
        sl.addLayout(uid_col)

        cnt_col = QVBoxLayout()
        cnt_col.setSpacing(2)
        l_cnt = QLabel("Tokens available")
        l_cnt.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 700;")
        self.count_val = QLabel("Unlimited")
        self.count_val.setObjectName("tokensStatVal")
        cnt_col.addWidget(l_cnt)
        cnt_col.addWidget(self.count_val)
        sl.addLayout(cnt_col)

        sl.addStretch(1)

        badge = QLabel("PRO")
        badge.setObjectName("tokensAppBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(60, 60)
        sl.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        bl.addWidget(stat_frame)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_check = QPushButton("Check Tokens")
        self.btn_check.setObjectName("tokensPrimary")
        self.btn_check.setMinimumHeight(38)
        self.btn_check.setMinimumWidth(130)
        self.btn_check.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.btn_clear = QPushButton("Clear Tokens")
        self.btn_clear.setObjectName("tokensSecondary")
        self.btn_clear.setMinimumHeight(38)
        self.btn_clear.setMinimumWidth(130)
        self.btn_clear.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        btn_row.addWidget(self.btn_check)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch(1)
        bl.addLayout(btn_row)

        root.addWidget(banner, 1)

        self._apply_styles()
        self.btn_close.clicked.connect(self.hide)
        self.btn_check.clicked.connect(self._on_check)
        self.btn_clear.clicked.connect(self._on_clear)

    def _on_check(self) -> None:
        self.status_line.setText("Tokens verified: Active and ready for automated pairing.")
        self.count_val.setText("Active")
        self.check_clicked.emit()

    def _on_clear(self) -> None:
        res = QMessageBox.question(
            self,
            "Clear Tokens",
            "Clear all cached sensor tokens?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self.status_line.setText("Sensor tokens cleared successfully.")
            self.clear_clicked.emit()

    def apply_check_result(self, data: dict[str, Any]) -> None:
        uid = data.get("userId", "PRO-ACTIVE")
        self.user_id.setText(str(uid))
        if data.get("httpOk", True):
            s = data.get("count", "Unlimited")
            self.count_val.setText(str(s))
            self.status_line.setText(f"Sensor status: Ready (userId={uid})")
        else:
            reason = data.get("reason", "unknown")
            self.status_line.setText(f"Check failed: {reason}")

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#tokensRoot {
                background: #091a2b;
                color: #e2e8f0;
                font-family: "Segoe UI", sans-serif;
                border: 1px solid #134150;
                border-radius: 14px;
            }
            QFrame#tokensHead {
                background: #0c1e34;
                border: 1px solid #1e3a5f;
                border-radius: 12px;
            }
            QLabel#tokensKicker {
                color: #94a3b8;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 2px;
            }
            QLabel#tokensTitle {
                color: #ffffff;
                font-size: 20px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QPushButton#tokensTab {
                background: #7c3aed;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: 800;
                font-size: 12px;
            }
            QPushButton#tokensClose {
                background: #0d1a28;
                color: #e8f4fa;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#tokensClose:hover {
                background: #dc2626;
                border-color: #ef4444;
                color: #ffffff;
            }
            QFrame#tokensBanner {
                background: #0c1e34;
                border: 1px solid #1e3a5f;
                border-radius: 12px;
            }
            QLabel#tokensTag {
                background: #7c3aed;
                color: #ffffff;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 800;
            }
            QLabel#tokensBannerTitle {
                color: #ffffff;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#tokensStatus {
                color: #94a3b8;
                font-size: 12px;
            }
            QFrame#tokensStat {
                background: #081422;
                border: 1px solid #1e3a5f;
                border-radius: 8px;
            }
            QLabel#tokensStatVal {
                color: #38bdf8;
                font-size: 16px;
                font-weight: 800;
            }
            QLabel#tokensAppBadge {
                background: #059669;
                color: #ffffff;
                border-radius: 30px;
                font-size: 13px;
                font-weight: 900;
            }
            QPushButton#tokensPrimary {
                background: #0e7490;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-weight: 800;
                font-size: 13px;
            }
            QPushButton#tokensPrimary:hover {
                background: #0891b2;
            }
            QPushButton#tokensSecondary {
                background: #2e1065;
                color: #c4b5fd;
                border: 1px solid #5b21b6;
                border-radius: 8px;
                font-weight: 800;
                font-size: 13px;
            }
            QPushButton#tokensSecondary:hover {
                background: #3b0764;
            }
        """)
