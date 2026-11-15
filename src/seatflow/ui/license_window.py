"""License / about window for SeatFlow.

Corresponds to the original application's `dist-renderer/license.html`
(window title "SeatFlow · License"). The original renderer bundle
(`license-BCJsqfw2.js`) is obfuscated and its exact license text is not
recoverable, so this window shows the application identity and version
without fabricating specific license terms. The full license text, if
any, is expected in the repository `LICENSE` file.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seatflow.ui.app_icon import apply_bingo_icon
from seatflow.ui.window_drag import enable_window_drag


class LicenseWindow(QWidget):
    """License / about popup window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("SeatFlow · License")
        self.setFixedSize(420, 300)
        self.setObjectName("licenseRoot")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        self._setup_ui()
        self._setup_styles()
        enable_window_drag(self, self.head_frame)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("licenseCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(10)

        # Header
        self.head_frame = QFrame()
        hl = QHBoxLayout(self.head_frame)
        hl.setContentsMargins(4, 2, 4, 2)

        title_lbl = QLabel("LICENSE")
        title_lbl.setObjectName("licenseTitle")
        hl.addWidget(title_lbl)

        hl.addStretch(1)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("licenseClose")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.clicked.connect(self.hide)
        hl.addWidget(self.btn_close)

        lay.addWidget(self.head_frame)

        # App identity
        app_lbl = QLabel("SeatFlow")
        app_lbl.setObjectName("licenseApp")
        lay.addWidget(app_lbl)

        version_lbl = QLabel("Version 0.1.0")
        version_lbl.setObjectName("licenseVersion")
        lay.addWidget(version_lbl)

        desc_lbl = QLabel(
            "Toolbar-style railway booking assistant for IRCTC ticket "
            "management. Local-first application: all account credentials, "
            "ticket profiles, proxies, and journey history are stored "
            "locally in an encrypted SQLite database."
        )
        desc_lbl.setObjectName("licenseDesc")
        desc_lbl.setWordWrap(True)
        lay.addWidget(desc_lbl)

        lay.addSpacing(6)

        # License notice
        notice_lbl = QLabel(
            "This software is provided as-is. Account credentials are "
            "encrypted using the Master Security Vault (Argon2id + "
            "AES-256-GCM) and are never transmitted by the application. "
            "See the repository LICENSE file for full terms."
        )
        notice_lbl.setObjectName("licenseNotice")
        notice_lbl.setWordWrap(True)
        lay.addWidget(notice_lbl)

        lay.addStretch(1)

        outer.addWidget(card)

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#licenseRoot {
                background: transparent;
            }
            QFrame#licenseCard {
                background: #091a2b;
                border: 1px solid #1e3a5f;
                border-radius: 10px;
            }
            QLabel#licenseTitle {
                color: #ffffff;
                font-weight: 800;
                font-size: 13px;
                letter-spacing: 0.5px;
            }
            QPushButton#licenseClose {
                background: transparent;
                color: #94a3b8;
                border: none;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton#licenseClose:hover {
                color: #ef4444;
            }
            QLabel#licenseApp {
                color: #38bdf8;
                font-weight: 800;
                font-size: 20px;
                margin-top: 6px;
            }
            QLabel#licenseVersion {
                color: #94a3b8;
                font-size: 12px;
            }
            QLabel#licenseDesc {
                color: #e2e8f0;
                font-size: 12px;
                line-height: 1.45;
            }
            QLabel#licenseNotice {
                color: #94a3b8;
                font-size: 11px;
                line-height: 1.4;
                font-style: italic;
            }
        """)
