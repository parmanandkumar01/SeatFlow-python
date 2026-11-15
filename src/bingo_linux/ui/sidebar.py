"""Left sidebar navigation component."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Navigation items: (key, display text, icon hint)
NAV_ITEMS: list[tuple[str, str]] = [
    ("dashboard", "Dashboard"),
    ("accounts", "Railway Accounts"),
    ("tickets", "Ticket Records"),
    ("history", "Journey History"),
    ("pnr", "PNR Status"),
    ("proxies", "Proxy Config"),
    ("settings", "Settings"),
]

# Default inactive button style
INACTIVE_STYLE = """
    QPushButton {
        background-color: transparent;
        color: #b0b0b0;
        border: none;
        text-align: left;
        padding: 12px 16px;
        font-size: 13px;
        border-radius: 0;
    }
    QPushButton:hover {
        background-color: #3d3d3d;
        color: #ffffff;
    }
"""

# Active button style
ACTIVE_STYLE = """
    QPushButton {
        background-color: #3d3d3d;
        color: #ffffff;
        border: none;
        text-align: left;
        padding: 12px 16px;
        font-size: 13px;
        border-radius: 0;
        border-left: 4px solid #42a5f5;
    }
    QPushButton:hover {
        background-color: #4a4a4a;
        color: #ffffff;
    }
"""

# Logo / header style
HEADER_STYLE = """
    QFrame {
        background-color: #2d2d2d;
        border-bottom: 1px solid #3d3d3d;
    }
    QLabel {
        color: #ffffff;
        background-color: transparent;
    }
"""


class Sidebar(QFrame):
    """Fixed left sidebar with application navigation.

    Emits page_requested when a navigation button is clicked.
    """

    #: Emitted when a navigation button is clicked with the page key.
    page_requested = Signal(str)
    bulletins_requested = Signal()
    transfer_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(220)
        self.setStyleSheet("QFrame { background-color: #252525; }")

        self._buttons: dict[str, QPushButton] = {}
        self._active_page: str = "dashboard"

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the sidebar layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # App header
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet(HEADER_STYLE)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)

        logo_label = QLabel("Bingo")
        logo_font = QFont()
        logo_font.setPointSize(16)
        logo_font.setBold(True)
        logo_label.setFont(logo_font)
        header_layout.addWidget(logo_label)
        header_layout.addStretch()

        layout.addWidget(header)

        # Navigation buttons
        nav_frame = QFrame()
        nav_layout = QVBoxLayout(nav_frame)
        nav_layout.setContentsMargins(0, 16, 0, 0)
        nav_layout.setSpacing(0)

        for key, label in NAV_ITEMS:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(ACTIVE_STYLE if key == self._active_page else INACTIVE_STYLE)
            btn.clicked.connect(lambda checked, k=key: self._on_nav_clicked(k))
            self._buttons[key] = btn
            nav_layout.addWidget(btn)

        nav_layout.addStretch()

        # Utility actions
        btn_bulletins = QPushButton("📢  Bulletins")
        btn_bulletins.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_bulletins.setStyleSheet(INACTIVE_STYLE)
        btn_bulletins.clicked.connect(self.bulletins_requested.emit)
        nav_layout.addWidget(btn_bulletins)

        btn_transfer = QPushButton("🔄  Export / Import")
        btn_transfer.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_transfer.setStyleSheet(INACTIVE_STYLE)
        btn_transfer.clicked.connect(self.transfer_requested.emit)
        nav_layout.addWidget(btn_transfer)

        layout.addWidget(nav_frame)

        # Version footer
        footer = QLabel("v0.1.0")
        footer.setStyleSheet("color: #6b6b6b; font-size: 11px; padding: 16px;")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)

    def _on_nav_clicked(self, key: str) -> None:
        """Handle navigation button click.

        Args:
            key: The page key associated with the clicked button.
        """
        self.set_active(key)
        self.page_requested.emit(key)

    def set_active(self, page_name: str) -> None:
        """Set the active navigation item.

        Args:
            page_name: The key of the page to mark as active.
        """
        self._active_page = page_name
        for key, btn in self._buttons.items():
            btn.setStyleSheet(ACTIVE_STYLE if key == page_name else INACTIVE_STYLE)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        """Return the preferred size for the sidebar."""
        return QSize(220, 600)
