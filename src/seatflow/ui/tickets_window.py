"""Tickets list window matching real SeatFlow UI.

Matches Screenshot_2026-11-14-21-08-54-27 with token alert banner,
search filter, table with Open / Refresh / Edit / Duplicate / Delete,
and Launch All / Delete All footer.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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

from seatflow.ui.app_icon import apply_bingo_icon, bingo_logo_pixmap
from seatflow.ui.window_drag import enable_window_drag


class TicketsWindow(QWidget):
    """Tickets management window matching official SeatFlow screenshot."""

    open_ticket = Signal(str, int)  # ticket_id, pair_index
    launch_all = Signal()
    edit_ticket = Signal(str)       # ticket_id
    duplicate_ticket = Signal(str)  # ticket_id
    delete_ticket = Signal(str)     # ticket_id
    delete_all = Signal()
    history_clicked = Signal()
    generate_tokens_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("Tickets")
        self.resize(960, 620)
        self.setMinimumSize(800, 480)
        self.setObjectName("ticketsWindowRoot")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self._tickets: list[dict[str, Any]] = []
        self._filter_text: str = ""

        self._setup_ui()
        self._setup_styles()
        enable_window_drag(self, self.head_frame)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        main_card = QFrame()
        main_card.setObjectName("tktMainCard")
        lay = QVBoxLayout(main_card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 1. Header
        self.head_frame = QFrame()
        self.head_frame.setObjectName("tktHead")
        self.head_frame.setFixedHeight(54)
        hl = QHBoxLayout(self.head_frame)
        hl.setContentsMargins(18, 10, 14, 10)
        hl.setSpacing(12)

        logo_lbl = QLabel()
        logo_lbl.setPixmap(bingo_logo_pixmap(24))
        hl.addWidget(logo_lbl)

        title_lbl = QLabel("TICKETS")
        title_lbl.setObjectName("tktTitle")
        hl.addWidget(title_lbl)

        hl.addStretch(1)

        # Search Bar
        self.search_input = QLineEdit()
        self.search_input.setObjectName("tktSearch")
        self.search_input.setPlaceholderText("🔍  Search name, station, train...")
        self.search_input.setFixedWidth(260)
        self.search_input.setFixedHeight(34)
        self.search_input.textChanged.connect(self._on_search_changed)
        hl.addWidget(self.search_input)

        # History Button
        self.btn_history = QPushButton("⏱  History")
        self.btn_history.setObjectName("tktBtnHistory")
        self.btn_history.setFixedHeight(34)
        self.btn_history.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_history.clicked.connect(self.history_clicked.emit)
        hl.addWidget(self.btn_history)

        # Close
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("tktClose")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.clicked.connect(self.hide)
        hl.addWidget(self.btn_close)

        lay.addWidget(self.head_frame)

        # 2. Pink/Red Token Warning Banner
        self.token_banner = QFrame()
        self.token_banner.setObjectName("tktBanner")
        self.token_banner.setFixedHeight(36)
        tbl = QHBoxLayout(self.token_banner)
        tbl.setContentsMargins(16, 0, 16, 0)
        tbl.setSpacing(8)

        bell_icon = QLabel("🔔")
        bell_icon.setStyleSheet("font-size: 14px;")
        tbl.addWidget(bell_icon)

        banner_text = QLabel("APP - No tokens, bookings will fail at Tatkal time.")
        banner_text.setStyleSheet("color: #ffffff; font-weight: 700; font-size: 12px;")
        tbl.addWidget(banner_text)

        btn_gen = QPushButton("Generate tokens")
        btn_gen.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #ffffff;
                text-decoration: underline;
                border: none;
                font-weight: 800;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #fef08a;
            }
        """)
        btn_gen.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_gen.clicked.connect(self.generate_tokens_clicked.emit)
        tbl.addWidget(btn_gen)
        tbl.addStretch(1)

        lay.addWidget(self.token_banner)

        # 3. Table
        self.table = QTableWidget(0, 9)
        self.table.setObjectName("tktTable")
        self.table.setHorizontalHeaderLabels([
            "#", "TICKET", "FROM", "TO", "TRAIN NO", "DATE", "QUOTA", "CLASS", "ACTIONS"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)

        lay.addWidget(self.table)

        # 4. Footer
        footer = QFrame()
        footer.setObjectName("tktFooter")
        footer.setFixedHeight(50)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(18, 8, 18, 8)
        fl.setSpacing(14)

        self.count_lbl = QLabel("0 tickets")
        self.count_lbl.setStyleSheet("color: #64748b; font-weight: 600; font-size: 12px;")
        fl.addWidget(self.count_lbl)

        fl.addStretch(1)

        self.btn_launch_all = QPushButton("⚡  Launch all")
        self.btn_launch_all.setObjectName("btnLaunchAll")
        self.btn_launch_all.setFixedHeight(34)
        self.btn_launch_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_launch_all.clicked.connect(self.launch_all.emit)
        fl.addWidget(self.btn_launch_all)

        self.btn_delete_all = QPushButton("🗑  Delete all")
        self.btn_delete_all.setObjectName("btnDeleteAll")
        self.btn_delete_all.setFixedHeight(34)
        self.btn_delete_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_delete_all.clicked.connect(self._on_delete_all_clicked)
        fl.addWidget(self.btn_delete_all)

        lay.addWidget(footer)
        root.addWidget(main_card)

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#ticketsWindowRoot {
                background: transparent;
            }
            QFrame#tktMainCard {
                background: #091a2b;
                border: 1px solid #1e3a5f;
                border-radius: 12px;
            }
            QFrame#tktHead {
                background: #0c1e34;
                border-bottom: 1px solid #1e3a5f;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#tktTitle {
                color: #ffffff;
                font-size: 15px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QLineEdit#tktSearch {
                background: #081422;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                padding: 4px 10px;
                color: #ffffff;
                font-size: 12px;
            }
            QLineEdit#tktSearch:focus {
                border-color: #7c3aed;
                background: #081422;
            }
            QPushButton#tktBtnHistory {
                background: #0d2238;
                color: #38bdf8;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-weight: 700;
                font-size: 12px;
                padding: 0 12px;
            }
            QPushButton#tktBtnHistory:hover {
                background: #143048;
            }
            QPushButton#tktClose {
                background: #0d1a28;
                color: #e8f4fa;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#tktClose:hover {
                background: #dc2626;
                border-color: #ef4444;
                color: #ffffff;
            }
            QFrame#tktBanner {
                background: #881337;
            }
            QTableWidget#tktTable {
                background-color: #081422;
                alternate-background-color: #061222;
                gridline-color: #0e2d3e;
                border: none;
                color: #ffffff;
            }
            QTableWidget#tktTable::item {
                padding: 8px 6px;
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
                border-bottom: 2px solid #1e3a5f;
            }
            QFrame#tktFooter {
                background: #071524;
                border-top: 1px solid #1e3a5f;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QPushButton#btnLaunchAll {
                background: #7c3aed;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-weight: 800;
                font-size: 12px;
                padding: 0 16px;
            }
            QPushButton#btnLaunchAll:hover {
                background: #8b5cf6;
            }
            QPushButton#btnDeleteAll {
                background: transparent;
                color: #f87171;
                border: none;
                font-weight: 700;
                font-size: 12px;
                padding: 0 12px;
            }
            QPushButton#btnDeleteAll:hover {
                color: #ef4444;
            }
        """)

    def set_tickets(self, tickets: list[dict[str, Any]]) -> None:
        """Update tickets table."""
        self._tickets = tickets
        self._render_table()

    def _on_search_changed(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        self._render_table()

    def _render_table(self) -> None:
        filtered = self._tickets
        if self._filter_text:
            filtered = [
                t for t in self._tickets
                if self._filter_text in (t.get("ticket_name") or "").lower()
                or self._filter_text in (t.get("from_station") or "").lower()
                or self._filter_text in (t.get("to_station") or "").lower()
                or self._filter_text in (t.get("train_number") or "").lower()
            ]

        self.table.setRowCount(len(filtered))
        self.count_lbl.setText(f"{len(filtered)} ticket{'s' if len(filtered) != 1 else ''}")

        for row, t in enumerate(filtered):
            tkt_id = t.get("id", "")

            # 0. S.NO
            idx_item = QTableWidgetItem(str(row + 1))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, idx_item)

            # 1. TICKET NAME
            name = t.get("ticket_name") or f"{t.get('from_station')}_{t.get('to_station')}"
            name_item = QTableWidgetItem(name)
            name_font = QFont()
            name_font.setBold(True)
            name_item.setFont(name_font)
            self.table.setItem(row, 1, name_item)

            # 2. FROM
            f_item = QTableWidgetItem(t.get("from_station", ""))
            f_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, f_item)

            # 3. TO
            to_item = QTableWidgetItem(t.get("to_station", ""))
            to_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, to_item)

            # 4. TRAIN NO
            tr_item = QTableWidgetItem(t.get("train_number", ""))
            tr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, tr_item)

            # 5. DATE
            d_item = QTableWidgetItem(t.get("journey_date", ""))
            d_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, d_item)

            # 6. QUOTA
            q_item = QTableWidgetItem(t.get("quota", "TQ"))
            q_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 6, q_item)

            # 7. CLASS pill dropdown
            cls_combo = QComboBox()
            for c in ["2S", "SL", "3A", "2A", "1A", "CC", "3E"]:
                cls_combo.addItem(c)
            current_cls = t.get("class", "2S")
            idx = cls_combo.findText(current_cls)
            if idx >= 0:
                cls_combo.setCurrentIndex(idx)
            cls_combo.setStyleSheet("""
                QComboBox {
                    background: #0d2238;
                    color: #38bdf8;
                    border: 1px solid #1e3a5f;
                    border-radius: 12px;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: 700;
                }
            """)
            self.table.setCellWidget(row, 7, cls_combo)

            # 8. ACTIONS: [⚡ Open]  [↻]  [✏️]  [📑]  [🗑️]
            actions_widget = QWidget()
            al = QHBoxLayout(actions_widget)
            al.setContentsMargins(4, 2, 4, 2)
            al.setSpacing(6)

            btn_open = QPushButton("⚡  Open")
            btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_open.setStyleSheet("""
                QPushButton {
                    background: #7c3aed;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 800;
                    padding: 4px 10px;
                }
                QPushButton:hover {
                    background: #8b5cf6;
                }
            """)
            btn_open.clicked.connect(lambda _, tid=tkt_id: self.open_ticket.emit(tid, 0))
            al.addWidget(btn_open)

            btn_refresh = self._make_icon_btn("↻", "Refresh status", lambda _, tid=tkt_id: None)
            al.addWidget(btn_refresh)

            btn_edit = self._make_icon_btn("✏️", "Edit ticket", lambda _, tid=tkt_id: self.edit_ticket.emit(tid))
            al.addWidget(btn_edit)

            btn_dup = self._make_icon_btn("📑", "Duplicate ticket", lambda _, tid=tkt_id: self.duplicate_ticket.emit(tid))
            al.addWidget(btn_dup)

            btn_del = self._make_icon_btn("🗑", "Delete ticket", lambda _, tid=tkt_id: self._on_delete_ticket_clicked(tid), color="#f87171")
            al.addWidget(btn_del)

            al.addStretch(1)
            self.table.setCellWidget(row, 8, actions_widget)

        self.table.resizeRowsToContents()

    def _make_icon_btn(self, text: str, tip: str, callback, color: str = "#94a3b8") -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tip)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setFixedSize(26, 26)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: #0d2238;
                color: {color};
                border: 1px solid #1e3a5f;
                border-radius: 4px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: #143048;
                border-color: #38bdf8;
            }}
        """)
        btn.clicked.connect(callback)
        return btn

    def _on_delete_ticket_clicked(self, ticket_id: str) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Ticket",
            "Are you sure you want to delete this ticket profile?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_ticket.emit(ticket_id)

    def _on_delete_all_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "Delete All Tickets",
            "Are you sure you want to delete ALL tickets?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_all.emit()
