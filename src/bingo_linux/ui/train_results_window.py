"""Train results and live availability window.

Matches Screenshot_2026-11-14-21-07-08-50 (TRAINS BETWEEN STATIONS)
with live timetables from erail API, quota selection, and class selection chips.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bingo_linux.services.train_service import check_availability
from bingo_linux.ui.app_icon import apply_bingo_icon
from bingo_linux.ui.window_drag import enable_window_drag


class ClassChip(QPushButton):
    """Clickable class badge/chip (e.g. 2S, 3A, SL, CC)."""

    def __init__(self, code: str, parent: QWidget | None = None) -> None:
        super().__init__(code, parent)
        self.class_code = code
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setCheckable(True)
        self.setObjectName("classChip")
        self.setMinimumHeight(26)
        self.setMinimumWidth(38)
        self.setStyleSheet("""
            QPushButton#classChip {
                background: #0d2238;
                color: #38bdf8;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 700;
                padding: 2px 6px;
            }
            QPushButton#classChip:hover {
                background: #143048;
                border-color: #38bdf8;
            }
            QPushButton#classChip:checked {
                background: #7c3aed;
                color: #ffffff;
                border-color: #8b5cf6;
            }
        """)


class TrainResultsWindow(QWidget):
    """Window displaying live trains between stations matching official UI."""

    #: Emitted when user selects a train and class: {trainNo, trainName, trainClass, quota}
    apply_selection = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("Trains Between Stations")
        self.resize(880, 580)
        self.setMinimumSize(720, 460)
        self.setObjectName("trainResultsRoot")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self._query: dict[str, Any] = {}
        self._trains: list[dict[str, Any]] = []
        self._selected: dict[str, Any] = {}

        self._setup_ui()
        self._setup_styles()
        enable_window_drag(self, self.head_frame)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        main_card = QFrame()
        main_card.setObjectName("trMainCard")
        lay = QVBoxLayout(main_card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 1. Header Frame
        self.head_frame = QFrame()
        self.head_frame.setObjectName("trHead")
        self.head_frame.setFixedHeight(54)
        hl = QHBoxLayout(self.head_frame)
        hl.setContentsMargins(18, 10, 14, 10)
        hl.setSpacing(12)

        icon_lbl = QLabel("🚆")
        icon_lbl.setStyleSheet("font-size: 18px;")
        hl.addWidget(icon_lbl)

        title_lbl = QLabel("TRAINS BETWEEN STATIONS")
        title_lbl.setObjectName("trTitle")
        hl.addWidget(title_lbl)

        hl.addStretch(1)

        self.route_lbl = QLabel("BWN → KAN  01-Sep-2026")
        self.route_lbl.setObjectName("trRoute")
        hl.addWidget(self.route_lbl)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("trClose")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.clicked.connect(self.hide)
        hl.addWidget(self.btn_close)
        lay.addWidget(self.head_frame)

        # 2. Sub-banner: Checking availability status
        self.banner = QFrame()
        self.banner.setObjectName("trBanner")
        self.banner.setFixedHeight(34)
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(16, 0, 16, 0)
        self.banner_text = QLabel("SELECT A TRAIN AND CLASS TO APPLY TO TICKET FORM")
        self.banner_text.setObjectName("trBannerText")
        bl.addWidget(self.banner_text)
        lay.addWidget(self.banner)

        # 3. Quota & Filter Bar
        bar_frame = QFrame()
        bar_frame.setObjectName("trFilterBar")
        bar_lay = QHBoxLayout(bar_frame)
        bar_lay.setContentsMargins(16, 8, 16, 8)
        bar_lay.setSpacing(10)

        quota_lbl = QLabel("QUOTA:")
        quota_lbl.setStyleSheet("font-weight: 700; color: #64748b; font-size: 11px;")
        bar_lay.addWidget(quota_lbl)

        self._quota_group = QButtonGroup(self)
        self.quota_buttons: dict[str, QPushButton] = {}
        for code in ["GN", "TQ", "PT", "LD", "SS", "DP", "HP"]:
            btn = QPushButton(code)
            btn.setCheckable(True)
            btn.setObjectName("trQuotaBtn")
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setFixedSize(36, 26)
            self._quota_group.addButton(btn)
            self.quota_buttons[code] = btn
            bar_lay.addWidget(btn)
        self.quota_buttons["TQ"].setChecked(True)

        bar_lay.addStretch(1)

        # Search filter input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search train number or name...")
        self.search_input.setFixedWidth(240)
        self.search_input.setFixedHeight(32)
        self.search_input.textChanged.connect(self._on_filter_changed)
        bar_lay.addWidget(self.search_input)

        lay.addWidget(bar_frame)

        # 4. Trains Table
        self.table = QTableWidget(0, 9)
        self.table.setObjectName("trTable")
        self.table.setHorizontalHeaderLabels([
            "#", "TRAIN NO", "NAME", "FROM", "TO", "DEP", "ARR", "DUR", "CLASSES"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)

        lay.addWidget(self.table)
        root.addWidget(main_card)

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#trainResultsRoot {
                background: transparent;
            }
            QFrame#trMainCard {
                background: #091a2b;
                border: 1px solid #1e3a5f;
                border-radius: 12px;
            }
            QFrame#trHead {
                background: #0c1e34;
                border-bottom: 1px solid #1e3a5f;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#trTitle {
                color: #ffffff;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QLabel#trRoute {
                color: #38bdf8;
                font-size: 13px;
                font-weight: 700;
                margin-right: 8px;
            }
            QPushButton#trClose {
                background: #0d1a28;
                color: #e8f4fa;
                border: 1px solid #1e3a5f;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#trClose:hover {
                background: #dc2626;
                border-color: #ef4444;
                color: #ffffff;
            }
            QFrame#trBanner {
                background: #0c4a6e;
            }
            QLabel#trBannerText {
                color: #38bdf8;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QFrame#trFilterBar {
                background: #071524;
                border-bottom: 1px solid #1e3a5f;
            }
            QPushButton#trQuotaBtn {
                background: #081422;
                color: #94a3b8;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#trQuotaBtn:hover {
                background: #0d2238;
                border-color: #38bdf8;
                color: #ffffff;
            }
            QPushButton#trQuotaBtn:checked {
                background: #7c3aed;
                color: #ffffff;
                border-color: #8b5cf6;
            }
            QTableWidget#trTable {
                background-color: #081422;
                alternate-background-color: #061222;
                gridline-color: #0e2d3e;
                border: none;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                color: #ffffff;
            }
            QTableWidget#trTable::item {
                padding: 6px 8px;
                color: #ffffff;
                border: none;
            }
            QHeaderView::section {
                background-color: #0c1e34;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 800;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #1e3a5f;
            }
        """)

    def set_loading(self, query: dict) -> None:
        """Display loading status while query is in-flight."""
        self._query = query
        fr = query.get("from", "")
        to = query.get("to", "")
        dt = query.get("date", "")
        self.route_lbl.setText(f"{fr} → {to}  {dt}")
        self.banner_text.setText(f"FETCHING LIVE TRAINS FOR {fr} → {to}...")
        self.table.setRowCount(0)

    def set_trains(self, trains: list[dict], query: dict) -> None:
        """Populate table with fetched live trains."""
        self._query = query
        self._trains = trains
        fr = query.get("from", "")
        to = query.get("to", "")
        dt = query.get("date", "")
        self.route_lbl.setText(f"{fr} → {to}  {dt}")
        self.banner_text.setText(f"FOUND {len(trains)} TRAIN(S) FOR {fr} → {to}. CLICK A CLASS CHIP TO SELECT.")
        self._populate_table(trains)

    def set_results(self, query: dict, trains: list[dict]) -> None:
        """Compatibility helper matching query, trains signature."""
        self.set_trains(trains, query)

    def set_error(self, message: str) -> None:
        """Display error banner."""
        self.banner_text.setText(f"ERROR: {message}")
        self.table.setRowCount(0)

    def _on_filter_changed(self, text: str) -> None:
        q = text.strip().upper()
        if not q:
            self._populate_table(self._trains)
            return
        filtered = [
            t for t in self._trains
            if q in t.get("train_no", "") or q in t.get("name", "").upper()
        ]
        self._populate_table(filtered)

    def _populate_table(self, trains: list[dict]) -> None:
        self.table.setRowCount(len(trains))
        for row, t in enumerate(trains):
            # 0. Index
            idx_item = QTableWidgetItem(str(row + 1))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, idx_item)

            # 1. Train No
            no_item = QTableWidgetItem(t.get("train_no", ""))
            no_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            no_font = QFont()
            no_font.setBold(True)
            no_item.setFont(no_font)
            self.table.setItem(row, 1, no_item)

            # 2. Name & Running days container
            name_widget = QWidget()
            name_lay = QVBoxLayout(name_widget)
            name_lay.setContentsMargins(4, 2, 4, 2)
            name_lay.setSpacing(2)

            name_lbl = QLabel(t.get("name", ""))
            name_lbl.setStyleSheet("font-weight: 700; color: #ffffff; font-size: 12px;")
            name_lay.addWidget(name_lbl)

            # Days run indicators: M T W T F S S
            days_row = QHBoxLayout()
            days_row.setSpacing(4)
            bits = t.get("days_bits", "1111111")
            day_letters = ["M", "T", "W", "T", "F", "S", "S"]
            for i, letter in enumerate(day_letters):
                dl = QLabel(letter)
                active = len(bits) > i and bits[i] == "1"
                color = "#10b981" if active else "#475569"
                dl.setStyleSheet(f"font-size: 9px; font-weight: 800; color: {color};")
                days_row.addWidget(dl)
            days_row.addStretch(1)
            name_lay.addLayout(days_row)
            self.table.setCellWidget(row, 2, name_widget)

            # 3. From
            self.table.setItem(row, 3, QTableWidgetItem(t.get("from", "")))

            # 4. To
            self.table.setItem(row, 4, QTableWidgetItem(t.get("to", "")))

            # 5. Dep
            self.table.setItem(row, 5, QTableWidgetItem(t.get("depart", "")))

            # 6. Arr
            self.table.setItem(row, 6, QTableWidgetItem(t.get("arrive", "")))

            # 7. Dur
            self.table.setItem(row, 7, QTableWidgetItem(t.get("duration", "")))

            # 8. Classes Chips
            chips_widget = QWidget()
            chips_lay = QHBoxLayout(chips_widget)
            chips_lay.setContentsMargins(2, 2, 2, 2)
            chips_lay.setSpacing(4)

            classes = t.get("classes", [])
            if not classes:
                classes = ["2S", "SL", "3A", "2A"]
            for c in classes:
                chip = ClassChip(c)
                chip.clicked.connect(lambda checked, tr=t, cls_code=c: self._on_chip_clicked(tr, cls_code))
                chips_lay.addWidget(chip)
            chips_lay.addStretch(1)
            self.table.setCellWidget(row, 8, chips_widget)

        self.table.resizeRowsToContents()

    def _get_active_quota(self) -> str:
        for code, btn in self.quota_buttons.items():
            if btn.isChecked():
                return code
        return "TQ"

    def _on_chip_clicked(self, train: dict, class_code: str) -> None:
        quota = self._get_active_quota()
        train_no = train.get("train_no", "")
        from_code = train.get("from", "")
        to_code = train.get("to", "")
        journey_date = self._query.get("date", "")

        avail = check_availability(
            train_no,
            from_code,
            to_code,
            journey_date,
            travel_class=class_code,
            quota=quota,
        )
        status = avail.get("status", "")
        fare = avail.get("fare")
        is_available = bool(avail.get("is_available", False))
        dot = "🟢" if is_available else "🟡"
        self.banner_text.setText(
            f"{dot} {status} | ₹{fare:,} | {quota} | "
            f"SELECTED: {train_no} - {train.get('name')} | CLASS: {class_code} | QUOTA: {quota}"
        )
        selection = {
            "trainNo": train_no,
            "trainName": train.get("name", ""),
            "trainClass": class_code,
            "quota": quota,
            "from": from_code,
            "to": to_code,
            "date": journey_date,
            "availability": status,
            "fare": fare,
            "is_available": is_available,
        }
        self.apply_selection.emit(selection)
        self.hide()
