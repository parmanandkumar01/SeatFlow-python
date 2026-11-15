"""Booking history & PNR status records window for SeatFlow."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seatflow.ui.app_icon import apply_bingo_icon
from seatflow.ui.window_drag import enable_window_drag


class HistoryWindow(QWidget):
    """Booking history records window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("Booking History")
        self.resize(860, 560)
        self.setMinimumSize(720, 440)
        self.setObjectName("historyWindowRoot")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self._records: list[dict[str, Any]] = []
        self._filter_text: str = ""

        self._setup_ui()
        self._setup_styles()
        enable_window_drag(self, self.head_frame)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        main_card = QFrame()
        main_card.setObjectName("histMainCard")
        lay = QVBoxLayout(main_card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        self.head_frame = QFrame()
        self.head_frame.setObjectName("histHead")
        self.head_frame.setFixedHeight(54)
        hl = QHBoxLayout(self.head_frame)
        hl.setContentsMargins(18, 10, 14, 10)
        hl.setSpacing(12)

        icon_lbl = QLabel("⏱")
        icon_lbl.setStyleSheet("font-size: 18px;")
        hl.addWidget(icon_lbl)

        title_lbl = QLabel("BOOKING HISTORY & PNR RECORDS")
        title_lbl.setObjectName("histTitle")
        hl.addWidget(title_lbl)

        hl.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search PNR, train...")
        self.search_input.setFixedWidth(220)
        self.search_input.setFixedHeight(32)
        self.search_input.textChanged.connect(self._on_search_changed)
        hl.addWidget(self.search_input)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("histClose")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.clicked.connect(self.hide)
        hl.addWidget(self.btn_close)

        lay.addWidget(self.head_frame)

        # Table
        self.table = QTableWidget(0, 7)
        self.table.setObjectName("histTable")
        self.table.setHorizontalHeaderLabels([
            "#", "PNR", "TRAIN", "FROM", "TO", "STATUS", "BOOKED AT"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 50)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 120)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 90)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 90)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 110)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 140)

        lay.addWidget(self.table)
        root.addWidget(main_card)

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#historyWindowRoot {
                background: transparent;
            }
            QFrame#histMainCard {
                background: #091a2b;
                border: 1px solid #1e3a5f;
                border-radius: 12px;
            }
            QFrame#histHead {
                background: #0c1e34;
                border-bottom: 1px solid #1e3a5f;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#histTitle {
                color: #ffffff;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QLineEdit {
                background: #081422;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                color: #ffffff;
                padding: 4px 8px;
            }
            QPushButton#histClose {
                background: #0d1a28;
                color: #e8f4fa;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#histClose:hover {
                background: #dc2626;
                border-color: #ef4444;
                color: #ffffff;
            }
            QTableWidget#histTable {
                background-color: #081422;
                alternate-background-color: #061222;
                gridline-color: #0e2d3e;
                border: none;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                color: #ffffff;
            }
            QTableWidget#histTable::item {
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

    def set_records(self, records: list[dict[str, Any]]) -> None:
        self._records = records
        self._render_table()

    def _on_search_changed(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        self._render_table()

    def _render_table(self) -> None:
        filtered = self._records
        if self._filter_text:
            filtered = [
                r for r in self._records
                if self._filter_text in (r.get("pnr") or "").lower()
                or self._filter_text in (r.get("train_number") or "").lower()
            ]

        self.table.setRowCount(len(filtered))
        for row, r in enumerate(filtered):
            # 0. #
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

            # 1. PNR
            pnr_item = QTableWidgetItem(r.get("pnr", "—"))
            pnr_font = QFont()
            pnr_font.setBold(True)
            pnr_item.setFont(pnr_font)
            self.table.setItem(row, 1, pnr_item)

            # 2. TRAIN
            self.table.setItem(row, 2, QTableWidgetItem(r.get("train_number", "")))

            # 3. FROM
            self.table.setItem(row, 3, QTableWidgetItem(r.get("from_station", "")))

            # 4. TO
            self.table.setItem(row, 4, QTableWidgetItem(r.get("to_station", "")))

            # 5. STATUS pill
            status = r.get("status", "SUCCESS").upper()
            st_lbl = QLabel(status)
            st_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bg = "#064e3b" if "SUCC" in status or "BOOK" in status else "#450a0a"
            fg = "#34d399" if "SUCC" in status or "BOOK" in status else "#f87171"
            st_lbl.setStyleSheet(f"""
                background: {bg};
                color: {fg};
                border-radius: 8px;
                font-size: 10px;
                font-weight: 800;
                padding: 2px 6px;
            """)
            st_wrap = QWidget()
            sl = QHBoxLayout(st_wrap)
            sl.setContentsMargins(0, 0, 0, 0)
            sl.addWidget(st_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 5, st_wrap)

            # 6. BOOKED AT
            self.table.setItem(row, 6, QTableWidgetItem(str(r.get("created_at", ""))))

        self.table.resizeRowsToContents()
