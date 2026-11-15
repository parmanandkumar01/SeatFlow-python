"""Proxies management window for SeatFlow."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seatflow.ui.app_icon import apply_bingo_icon
from seatflow.ui.widgets.toggle_switch import ToggleSwitch
from seatflow.ui.window_drag import enable_window_drag


class ProxiesWindow(QWidget):
    """Proxies management window."""

    add_proxy = Signal(dict)       # {"host": ..., "port": ..., "username": ..., "password": ...}
    delete_proxy = Signal(str)     # proxy_id
    test_proxy = Signal(str)       # proxy_id
    toggle_active = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("Proxies")
        self.resize(780, 560)
        self.setMinimumSize(680, 440)
        self.setObjectName("proxiesWindowRoot")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self._proxies: list[dict[str, Any]] = []

        self._setup_ui()
        self._setup_styles()
        enable_window_drag(self, self.head_frame)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        main_card = QFrame()
        main_card.setObjectName("prxMainCard")
        lay = QVBoxLayout(main_card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 1. Header
        self.head_frame = QFrame()
        self.head_frame.setObjectName("prxHead")
        self.head_frame.setFixedHeight(54)
        hl = QHBoxLayout(self.head_frame)
        hl.setContentsMargins(18, 10, 14, 10)
        hl.setSpacing(12)

        icon_lbl = QLabel("🌐")
        icon_lbl.setStyleSheet("font-size: 18px;")
        hl.addWidget(icon_lbl)

        title_lbl = QLabel("NETWORK PROXIES")
        title_lbl.setObjectName("prxTitle")
        hl.addWidget(title_lbl)

        hl.addStretch(1)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("prxClose")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.clicked.connect(self.hide)
        hl.addWidget(self.btn_close)

        lay.addWidget(self.head_frame)

        # 2. Input Box
        in_card = QFrame()
        in_card.setObjectName("prxInputCard")
        il = QVBoxLayout(in_card)
        il.setContentsMargins(20, 14, 20, 14)
        il.setSpacing(8)

        lbl_row = QHBoxLayout()
        lbl_cap = QLabel("PROXY STRING")
        lbl_cap.setObjectName("prxCap")
        lbl_fmt = QLabel("Format: host:port:username:password — or host:port")
        lbl_fmt.setStyleSheet("color: #94a3b8; font-size: 11px;")
        lbl_row.addWidget(lbl_cap)
        lbl_row.addWidget(lbl_fmt)
        lbl_row.addStretch(1)
        il.addLayout(lbl_row)

        in_row = QHBoxLayout()
        in_row.setSpacing(10)
        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("192.168.1.100:8080:user:pass")
        self.proxy_input.setFixedHeight(38)
        in_row.addWidget(self.proxy_input, stretch=1)

        self.btn_save = QPushButton("Save Proxy")
        self.btn_save.setObjectName("btnPurplePrimary")
        self.btn_save.setFixedHeight(38)
        self.btn_save.setMinimumWidth(120)
        self.btn_save.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_save.clicked.connect(self._on_save)
        in_row.addWidget(self.btn_save)

        il.addLayout(in_row)
        lay.addWidget(in_card)

        # 3. Table
        self.table = QTableWidget(0, 6)
        self.table.setObjectName("prxTable")
        self.table.setHorizontalHeaderLabels([
            "#", "HOST", "PORT", "TYPE", "ACTIVE", ""
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 50)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 90)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 90)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 80)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 60)

        lay.addWidget(self.table)
        root.addWidget(main_card)

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#proxiesWindowRoot {
                background: transparent;
            }
            QFrame#prxMainCard {
                background: #091a2b;
                border: 1px solid #1e3a5f;
                border-radius: 12px;
            }
            QFrame#prxHead {
                background: #0c1e34;
                border-bottom: 1px solid #1e3a5f;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#prxTitle {
                color: #ffffff;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QPushButton#prxClose {
                background: #0d1a28;
                color: #e8f4fa;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#prxClose:hover {
                background: #dc2626;
                border-color: #ef4444;
                color: #ffffff;
            }
            QFrame#prxInputCard {
                background: #071524;
                border-bottom: 1px solid #1e3a5f;
            }
            QLabel#prxCap {
                font-size: 11px;
                font-weight: 800;
                color: #94a3b8;
                letter-spacing: 0.5px;
            }
            QPushButton#btnPurplePrimary {
                background: #7c3aed;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton#btnPurplePrimary:hover {
                background: #8b5cf6;
            }
            QLineEdit {
                background: #081422;
                color: #ffffff;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QLineEdit:focus {
                border-color: #7c3aed;
            }
            QTableWidget#prxTable {
                background-color: #081422;
                alternate-background-color: #061222;
                gridline-color: #0e2d3e;
                border: none;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                color: #ffffff;
            }
            QTableWidget#prxTable::item {
                padding: 6px 8px;
                color: #ffffff;
                border: none;
            }
            QHeaderView::section {
                background-color: #0c1e34;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 800;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #1e3a5f;
            }
        """)

    def set_proxies(self, proxies: list[dict[str, Any]]) -> None:
        self._proxies = proxies
        self._render_table()

    def _render_table(self) -> None:
        self.table.setRowCount(len(self._proxies))
        for row, p in enumerate(self._proxies):
            pid = p.get("id", "")

            # 0. #
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

            # 1. HOST
            self.table.setItem(row, 1, QTableWidgetItem(p.get("host", "")))

            # 2. PORT
            self.table.setItem(row, 2, QTableWidgetItem(str(p.get("port", ""))))

            # 3. TYPE
            self.table.setItem(row, 3, QTableWidgetItem(p.get("type", "HTTP").upper()))

            # 4. ACTIVE Toggle
            sw = ToggleSwitch(checked=bool(p.get("is_active", False)))
            sw.toggled.connect(lambda val, proxy_id=pid: self.toggle_active.emit(proxy_id, val))
            sw_wrap = QWidget()
            sl = QHBoxLayout(sw_wrap)
            sl.setContentsMargins(0, 0, 0, 0)
            sl.addWidget(sw, alignment=Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 4, sw_wrap)

            # 5. Delete
            btn_del = QPushButton("🗑")
            btn_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_del.setFixedSize(26, 26)
            btn_del.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #ef4444;
                    border: none;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: #fee2e2;
                    border-radius: 4px;
                }
            """)
            btn_del.clicked.connect(lambda _, proxy_id=pid: self.delete_proxy.emit(proxy_id))
            del_wrap = QWidget()
            dl = QHBoxLayout(del_wrap)
            dl.setContentsMargins(0, 0, 0, 0)
            dl.addWidget(btn_del, alignment=Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 5, del_wrap)

        self.table.resizeRowsToContents()

    def _on_save(self) -> None:
        raw = self.proxy_input.text().strip()
        if not raw:
            return

        parts = raw.split(":")
        if len(parts) < 2:
            QMessageBox.warning(self, "Format Error", "Enter at least host:port")
            return

        host = parts[0].strip()
        port = int(parts[1].strip()) if parts[1].strip().isdigit() else 8080
        user = parts[2].strip() if len(parts) > 2 else None
        pwd = parts[3].strip() if len(parts) > 3 else None

        self.add_proxy.emit({
            "host": host,
            "port": port,
            "username": user,
            "password": pwd,
            "type": "HTTP",
        })
        self.proxy_input.clear()
