"""Main floating toolbar window for SeatFlow.

Matches Screenshot_2026-11-14-21-16-54-66:
A modern, floating top dock bar with SeatFlow branding,
+ Book, Tickets, Tokens, Settings ⌃, Profile, Payment, live clock,
and close confirmation.
"""

from __future__ import annotations

import datetime
from typing import Optional

from PySide6.QtCore import QByteArray, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seatflow.ui.app_icon import apply_bingo_icon, bingo_logo_pixmap
from seatflow.ui.window_drag import enable_window_drag, start_window_drag

TOOLBAR_W = 1140
TOOLBAR_H = 74
TOOLBAR_MIN_W = 960
TOOLBAR_MIN_H = 68

# SVG Icons
_SVG_ICONS = {
    "tickets": '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#0284c7" d="M4 6h16a1 1 0 0 1 1 1v3a2 2 0 0 0 0 4v3a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-3a2 2 0 0 0 0-4V7a1 1 0 0 1 1-1zm7 2v3H8v2h3v3h2v-3h3v-2h-3V8h-2z"/></svg>',
    "tokens": '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#0d9488" d="M12 2a7 7 0 0 0-4.9 12L4 20.1V22h3.2l1.5-1.5.9.9H14v-2.2l-1.4-1.4A7 7 0 0 0 12 2zm0 3a2 2 0 1 1 0 4 2 2 0 0 1 0-4z"/></svg>',
    "settings": '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#64748b" d="M19.1 12.9a7.5 7.5 0 0 0 .1-1.8l2-1.6-1.9-3.3-2.4 1a7.4 7.4 0 0 0-1.6-.9L14.9 3h-3.8l-.4 2.5c-.6.2-1.1.5-1.6.9l-2.4-1L5 9.5l2 1.6a7.5 7.5 0 0 0 0 1.8L5 14.5l1.9 3.3 2.4-1c.5.4 1 .7 1.6.9l.4 2.5h3.8l.4-2.5c.6-.2 1.1-.5 1.6-.9l2.4 1 1.9-3.3-2-1.6zM12 15.2A3.2 3.2 0 1 1 12 8.8a3.2 3.2 0 0 1 0 6.4z"/></svg>',
    "profile": '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#db2777" d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4zm0 2c-4.4 0-8 2.2-8 5v1h16v-1c0-2.8-3.6-5-8-5z"/></svg>',
    "payment": '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#0891b2" d="M3 6h18a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2zm0 3v2h18V9H3zm0 5v2h6v-2H3z"/></svg>',
    "power": '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="none" stroke="#ef4444" stroke-width="2.6" stroke-linecap="round" d="M12 3.2v7.4"/><path fill="none" stroke="#ef4444" stroke-width="2.6" stroke-linecap="round" d="M7.1 6.3a7.3 7.3 0 1 0 9.8 0"/></svg>',
}


def _svg_icon(key: str, size: int = 18) -> QIcon:
    svg = _SVG_ICONS.get(key, "")
    if not svg:
        return QIcon()
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return QIcon(pm)


class CloseConfirmDialog(QDialog):
    """Confirmation dialog when clicking close button."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Close SeatFlow")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(380, 180)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("closeConfirmCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        msg = QLabel("Are you sure you want to close SeatFlow?")
        msg.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(msg)

        btns = QHBoxLayout()
        btns.setSpacing(12)

        btn_yes = QPushButton("Yes, Close")
        btn_yes.setStyleSheet("""
            background: #ef4444;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-weight: 700;
            padding: 8px 16px;
        """)
        btn_yes.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_yes.clicked.connect(self.accept)

        btn_no = QPushButton("No, Keep Running")
        btn_no.setStyleSheet("""
            background: #143048;
            color: #e2e8f0;
            border: 1px solid #1e3a5f;
            border-radius: 8px;
            font-weight: 700;
            padding: 8px 16px;
        """)
        btn_no.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_no.clicked.connect(self.reject)

        btns.addWidget(btn_no, 1)
        btns.addWidget(btn_yes, 1)
        lay.addLayout(btns)

        card.setStyleSheet("""
            QFrame#closeConfirmCard {
                background: #0d2238;
                border: 1px solid #134150;
                border-radius: 12px;
            }
        """)
        root.addWidget(card)
        enable_window_drag(self, card)


class MainToolbarWindow(QWidget):
    """Floating top toolbar window matching official SeatFlow screenshot UI."""

    close_requested = Signal()
    exit_requested = Signal()
    action_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None, *args, **kwargs) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("SeatFlow Pro")
        self.resize(TOOLBAR_W, TOOLBAR_H)
        self.setMinimumWidth(TOOLBAR_MIN_W)
        self.setFixedHeight(TOOLBAR_H)
        self.setObjectName("mainToolbarRoot")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._setup_ui()
        self._setup_styles()
        enable_window_drag(self, self.toolbar_frame)

        # Clock timer
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_clock)
        self._timer.start()
        self._tick_clock()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(0)

        self.toolbar_frame = QFrame()
        self.toolbar_frame.setObjectName("bingoToolbar")
        row = QHBoxLayout(self.toolbar_frame)
        row.setContentsMargins(12, 6, 12, 6)
        row.setSpacing(10)

        # 1. Brand Widget: [Logo]  BINGO  [PRO]  ▾
        self.btn_brand = QPushButton()
        self.btn_brand.setObjectName("btnBrand")
        self.btn_brand.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        brand_lay = QHBoxLayout(self.btn_brand)
        brand_lay.setContentsMargins(8, 4, 10, 4)
        brand_lay.setSpacing(6)

        logo_lbl = QLabel()
        logo_lbl.setPixmap(bingo_logo_pixmap(24))
        brand_lay.addWidget(logo_lbl)

        brand_text = QLabel("BINGO")
        brand_text.setStyleSheet("font-size: 14px; font-weight: 900; color: #ffffff; letter-spacing: 0.5px;")
        brand_lay.addWidget(brand_text)

        pro_badge = QLabel("PRO")
        pro_badge.setStyleSheet("""
            background: #22c55e;
            color: #ffffff;
            font-size: 9px;
            font-weight: 800;
            padding: 2px 6px;
            border-radius: 4px;
        """)
        brand_lay.addWidget(pro_badge)

        arrow_lbl = QLabel("▾")
        arrow_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: bold;")
        brand_lay.addWidget(arrow_lbl)

        self.btn_brand.clicked.connect(lambda: self.action_clicked.emit("brand"))
        row.addWidget(self.btn_brand)

        # 2. Action buttons: + Book, Tickets, Tokens, Settings ⌃, Profile, Payment
        actions_lay = QHBoxLayout()
        actions_lay.setSpacing(8)

        # + Book (Purple Solid Button)
        self.btn_book = QPushButton("+  Book")
        self.btn_book.setObjectName("btnPurpleBook")
        self.btn_book.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_book.setFixedHeight(40)
        self.btn_book.clicked.connect(lambda: self.action_clicked.emit("book"))
        actions_lay.addWidget(self.btn_book)

        # 🎫 Tickets
        self.btn_tickets = self._make_action_btn("Tickets", "tickets", lambda: self.action_clicked.emit("tickets"))
        actions_lay.addWidget(self.btn_tickets)

        # 🔑 Tokens
        self.btn_tokens = self._make_action_btn("Tokens", "tokens", lambda: self.action_clicked.emit("tokens"))
        actions_lay.addWidget(self.btn_tokens)

        # ⚙️ Settings ⌃
        self.btn_settings = self._make_action_btn("Settings  ⌃", "settings", lambda: self.action_clicked.emit("settings"))
        actions_lay.addWidget(self.btn_settings)

        # 🪪 Profile
        self.btn_profile = self._make_action_btn("Profile", "profile", lambda: self.action_clicked.emit("accounts"))
        actions_lay.addWidget(self.btn_profile)

        # 💳 Payment
        self.btn_payment = self._make_action_btn("Payment", "payment", lambda: self.action_clicked.emit("payment"))
        actions_lay.addWidget(self.btn_payment)

        row.addLayout(actions_lay, stretch=1)

        # 3. Live Clock Pill: [●]  19:42:24
        clock_box = QFrame()
        clock_box.setObjectName("clockBox")
        c_lay = QHBoxLayout(clock_box)
        c_lay.setContentsMargins(10, 4, 12, 4)
        c_lay.setSpacing(6)

        dot = QFrame()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet("background: #22c55e; border-radius: 4px;")
        c_lay.addWidget(dot)

        self.clock_lbl = QLabel("00:00:00")
        self.clock_lbl.setObjectName("toolbarClock")
        c_lay.addWidget(self.clock_lbl)
        row.addWidget(clock_box)

        # 4. Close Button ✕
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("toolbarClose")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.clicked.connect(self._on_close_clicked)
        row.addWidget(self.btn_close)

        outer.addWidget(self.toolbar_frame)

    def _make_action_btn(self, text: str, icon_key: str, callback) -> QPushButton:
        btn = QPushButton(f"  {text}")
        btn.setObjectName("btnWhiteAction")
        btn.setFixedHeight(40)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setIcon(_svg_icon(icon_key, 16))
        btn.setIconSize(QSize(16, 16))
        btn.clicked.connect(callback)
        return btn

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#mainToolbarRoot {
                background: transparent;
            }
            QFrame#bingoToolbar {
                background: #0a1e30;
                border: 1px solid #134150;
                border-radius: 20px;
            }
            QPushButton#btnBrand {
                background: #071829;
                border: 1px solid #134150;
                border-radius: 12px;
                height: 40px;
                padding: 0 6px;
            }
            QPushButton#btnBrand:hover {
                background: #0d2238;
                border-color: #22d3ee;
            }
            QPushButton#btnPurpleBook {
                background: #7c3aed;
                color: #ffffff;
                border: none;
                border-radius: 12px;
                font-size: 13px;
                font-weight: 800;
                padding: 0 20px;
            }
            QPushButton#btnPurpleBook:hover {
                background: #8b5cf6;
            }
            QPushButton#btnWhiteAction {
                background: #0d2238;
                color: #e2e8f0;
                border: 1px solid #134150;
                border-radius: 12px;
                font-size: 13px;
                font-weight: 700;
                padding: 0 14px;
            }
            QPushButton#btnWhiteAction:hover {
                background: #143048;
                border-color: #22d3ee;
                color: #ffffff;
            }
            QFrame#clockBox {
                background: #071829;
                border: 1px solid #134150;
                border-radius: 12px;
                height: 38px;
            }
            QLabel#toolbarClock {
                color: #38bdf8;
                font-family: "Consolas", monospace;
                font-size: 14px;
                font-weight: 800;
            }
            QPushButton#toolbarClose {
                background: #071829;
                color: #94a3b8;
                border: 1px solid #134150;
                border-radius: 8px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton#toolbarClose:hover {
                background: #7f1d1d;
                border-color: #ef4444;
                color: #ffffff;
            }
        """)

    def _tick_clock(self) -> None:
        self.clock_lbl.setText(datetime.datetime.now().strftime("%H:%M:%S"))

    def _on_close_clicked(self) -> None:
        dlg = CloseConfirmDialog(self)
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            dlg.move(
                geo.center().x() - dlg.width() // 2,
                geo.center().y() - dlg.height() // 2,
            )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.close_requested.emit()
            self.exit_requested.emit()
            self.close()

    def closeEvent(self, event) -> None:
        self.close_requested.emit()
        self.exit_requested.emit()
        super().closeEvent(event)


def place_toolbar_top(win: QWidget, top_margin: int = 24) -> None:
    """Place toolbar at top center of primary display."""
    screen = QGuiApplication.primaryScreen()
    if not screen:
        return
    geo = screen.availableGeometry()
    w = win.width()
    x = geo.x() + (geo.width() - w) // 2
    y = geo.y() + top_margin
    win.move(x, y)


# Alias for backward compatibility with previous imports
MainWindow = MainToolbarWindow
