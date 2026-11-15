"""Ticket booking form window matching real SeatFlow UI.

Matches Screenshot_2026-11-14-21-06-07-23 and Screenshot_2026-11-14-21-07-57-68
with station swap, live train search, max 6 passengers, contact/bank/options,
and auto-generated ticket names.
"""

from __future__ import annotations

import json
import random
import re
from datetime import date, timedelta
from typing import Any, Optional

from PySide6.QtCore import QDate, QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QCursor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seatflow.services.master_data_service import MasterDataService
from seatflow.services.train_service import resolve_station_code
from seatflow.ui.app_icon import apply_bingo_icon, bingo_logo_pixmap
from seatflow.ui.widgets.clickable_date import ClickableDateEdit
from seatflow.ui.widgets.toggle_switch import ToggleSwitch, YesNoToggle
from seatflow.ui.window_drag import enable_window_drag

GENDERS = ["Male", "Female", "Transgender"]
BERTHS = [
    "No Preference",
    "Lower",
    "Middle",
    "Upper",
    "Side Lower",
    "Side Upper",
    "Cabin",
    "Coupe",
]
FOODS = ["No Preference", "Veg", "Non-Veg"]
CLASSES = [
    ("- Select -", ""),
    ("Second Sitting (2S)", "2S"),
    ("Sleeper (SL)", "SL"),
    ("AC 3 Tier (3A)", "3A"),
    ("AC 2 Tier (2A)", "2A"),
    ("AC First Class (1A)", "1A"),
    ("AC Chair Car (CC)", "CC"),
    ("AC 3 Economy (3E)", "3E"),
]
QUOTAS = [
    ("TATKAL", "TQ"),
    ("GENERAL", "GN"),
    ("PREMIUM TATKAL", "PT"),
    ("LADIES", "LD"),
    ("SENIOR CITIZEN", "SS"),
    ("DIVYANGJAN", "HP"),
]
BACKUP_GATEWAYS = [
    ("- Select a Bank / Gateway first -", ""),
    ("PHONEPEQR · bingophonepay@ybl", "PHONEPEQR"),
    ("IPAYQR · bingots@ybl", "IPAYQR"),
    ("PAYTMQR · bingopaytm@paytm", "PAYTMQR"),
    ("IRCTC UPI ID · irctc@upi", "IRCUPIID"),
]


class BookWindow(QWidget):
    """Book a ticket form window matching official SeatFlow screenshot UI."""

    #: Signals
    search_clicked = Signal()
    availability_clicked = Signal()
    save_clicked = Signal(dict)
    cancel_clicked = Signal()

    def __init__(
        self,
        master_data_service: Optional[MasterDataService] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("Book a Ticket")
        self.resize(780, 840)
        self.setMinimumSize(700, 680)
        self.setObjectName("bookTicketRoot")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self._master_data_service = master_data_service or MasterDataService()
        self._accounts: list[dict] = []
        self._proxies: list[dict] = []
        self._payments: list[dict] = []
        self._ticket_id: Optional[str] = None

        self._setup_ui()
        self._setup_styles()
        self._setup_completers()
        enable_window_drag(self, self.head_frame)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        main_card = QFrame()
        main_card.setObjectName("bookMainCard")
        lay = QVBoxLayout(main_card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 1. Header Frame
        self.head_frame = QFrame()
        self.head_frame.setObjectName("bookHead")
        self.head_frame.setFixedHeight(54)
        hl = QHBoxLayout(self.head_frame)
        hl.setContentsMargins(18, 10, 14, 10)
        hl.setSpacing(12)

        logo_lbl = QLabel()
        logo_lbl.setPixmap(bingo_logo_pixmap(24))
        hl.addWidget(logo_lbl)

        title_lbl = QLabel("+  BOOK A TICKET")
        title_lbl.setObjectName("bookTitle")
        hl.addWidget(title_lbl)

        hl.addStretch(1)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("bookClose")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.clicked.connect(self.hide)
        hl.addWidget(self.btn_close)
        lay.addWidget(self.head_frame)

        # Scrollable form body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("bookScroll")

        body = QWidget()
        body.setObjectName("bookBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16)
        bl.setSpacing(16)

        # -------------------------------------------------------------
        # Journey Details
        # -------------------------------------------------------------
        # Row 1: FROM, ⇄, TO, DATE, Search
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        # FROM
        from_col = QVBoxLayout()
        from_col.setSpacing(4)
        l_from = QLabel("FROM")
        l_from.setObjectName("fieldLabel")
        self.from_edit = QLineEdit()
        self.from_edit.setPlaceholderText("Code or station name")
        self.from_edit.setFixedHeight(38)
        self.from_edit.textChanged.connect(self._auto_generate_ticket_name)
        from_col.addWidget(l_from)
        from_col.addWidget(self.from_edit)
        row1.addLayout(from_col, stretch=3)

        # Swap button ⇄
        swap_col = QVBoxLayout()
        swap_col.setSpacing(4)
        swap_col.addWidget(QLabel(""))  # spacer
        self.btn_swap = QPushButton("⇄")
        self.btn_swap.setObjectName("btnSwap")
        self.btn_swap.setFixedSize(34, 38)
        self.btn_swap.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_swap.clicked.connect(self._swap_stations)
        swap_col.addWidget(self.btn_swap)
        row1.addLayout(swap_col)

        # TO
        to_col = QVBoxLayout()
        to_col.setSpacing(4)
        l_to = QLabel("TO")
        l_to.setObjectName("fieldLabel")
        self.to_edit = QLineEdit()
        self.to_edit.setPlaceholderText("Code or station name")
        self.to_edit.setFixedHeight(38)
        self.to_edit.textChanged.connect(self._auto_generate_ticket_name)
        to_col.addWidget(l_to)
        to_col.addWidget(self.to_edit)
        row1.addLayout(to_col, stretch=3)

        # DATE
        date_col = QVBoxLayout()
        date_col.setSpacing(4)
        l_date = QLabel("DATE")
        l_date.setObjectName("fieldLabel")
        self.date_edit = ClickableDateEdit()
        self.date_edit.setFixedHeight(38)
        self.date_edit.setDate(QDate.currentDate().addDays(1))
        date_col.addWidget(l_date)
        date_col.addWidget(self.date_edit)
        row1.addLayout(date_col, stretch=2)

        # Q Search button
        search_col = QVBoxLayout()
        search_col.setSpacing(4)
        search_col.addWidget(QLabel(""))  # spacer
        self.btn_search = QPushButton("🔍  Search")
        self.btn_search.setObjectName("btnPurplePrimary")
        self.btn_search.setFixedHeight(38)
        self.btn_search.setMinimumWidth(100)
        self.btn_search.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_search.clicked.connect(self.search_clicked.emit)
        search_col.addWidget(self.btn_search)
        row1.addLayout(search_col)

        bl.addLayout(row1)

        # Row 2: TRAIN, CLASS, QUOTA, Availability
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        # TRAIN
        train_col = QVBoxLayout()
        train_col.setSpacing(4)
        l_tr = QLabel("TRAIN")
        l_tr.setObjectName("fieldLabel")
        self.train_edit = QLineEdit()
        self.train_edit.setPlaceholderText("Type a train number or name")
        self.train_edit.setFixedHeight(38)
        train_col.addWidget(l_tr)
        train_col.addWidget(self.train_edit)
        row2.addLayout(train_col, stretch=4)

        # CLASS
        class_col = QVBoxLayout()
        class_col.setSpacing(4)
        l_cls = QLabel("CLASS")
        l_cls.setObjectName("fieldLabel")
        self.class_combo = QComboBox()
        for label, val in CLASSES:
            self.class_combo.addItem(label, val)
        self.class_combo.setFixedHeight(38)
        class_col.addWidget(l_cls)
        class_col.addWidget(self.class_combo)
        row2.addLayout(class_col, stretch=2)

        # QUOTA
        quota_col = QVBoxLayout()
        quota_col.setSpacing(4)
        l_q = QLabel("QUOTA")
        l_q.setObjectName("fieldLabel")
        self.quota_combo = QComboBox()
        for label, val in QUOTAS:
            self.quota_combo.addItem(label, val)
        self.quota_combo.setFixedHeight(38)
        quota_col.addWidget(l_q)
        quota_col.addWidget(self.quota_combo)
        row2.addLayout(quota_col, stretch=2)

        # Availability button
        avail_col = QVBoxLayout()
        avail_col.setSpacing(4)
        avail_col.addWidget(QLabel(""))  # spacer
        self.btn_avail = QPushButton("💺 Availability")
        self.btn_avail.setObjectName("btnPurplePrimary")
        self.btn_avail.setFixedHeight(38)
        self.btn_avail.setMinimumWidth(110)
        self.btn_avail.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_avail.clicked.connect(self.availability_clicked.emit)
        avail_col.addWidget(self.btn_avail)
        row2.addLayout(avail_col)

        bl.addLayout(row2)

        # Availability pill (green = available, amber = RAC/WL)
        self.avail_pill = QLabel("")
        self.avail_pill.setObjectName("bookAvailPill")
        self.avail_pill.setFixedHeight(30)
        self.avail_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(self.avail_pill)

        # -------------------------------------------------------------
        # Section 2: PASSENGER INFORMATION (Max 6)
        # -------------------------------------------------------------
        sec1_lbl = QLabel("👥  PASSENGER INFORMATION  (Max 6)")
        sec1_lbl.setObjectName("sectionHeader")
        bl.addWidget(sec1_lbl)

        # Table of passengers
        self.pax_table = QTableWidget(0, 7)
        self.pax_table.setObjectName("paxTable")
        self.pax_table.setHorizontalHeaderLabels([
            "S.NO", "FULL NAME", "AGE", "GENDER", "BERTH PREF", "FOOD", ""
        ])
        self.pax_table.verticalHeader().setVisible(False)
        self.pax_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.pax_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        pHdr = self.pax_table.horizontalHeader()
        pHdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.pax_table.setColumnWidth(0, 50)
        pHdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        pHdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.pax_table.setColumnWidth(2, 60)
        pHdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.pax_table.setColumnWidth(3, 110)
        pHdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.pax_table.setColumnWidth(4, 130)
        pHdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.pax_table.setColumnWidth(5, 120)
        pHdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.pax_table.setColumnWidth(6, 40)

        bl.addWidget(self.pax_table)

        # + Add passenger button
        self.btn_add_pax = QPushButton("+ Add passenger")
        self.btn_add_pax.setObjectName("btnAddPax")
        self.btn_add_pax.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add_pax.clicked.connect(self._add_empty_passenger_row)
        bl.addWidget(self.btn_add_pax, alignment=Qt.AlignmentFlag.AlignLeft)

        # -------------------------------------------------------------
        # Section 3: CONTACT · BANK · OPTIONS
        # -------------------------------------------------------------
        sec2_lbl = QLabel("⚙️  CONTACT · BANK · OPTIONS")
        sec2_lbl.setObjectName("sectionHeader")
        bl.addWidget(sec2_lbl)

        # Row: IRCTC ID, MOBILE (+91) with 🎲, MAX PT FARE, BANK/GATEWAY
        opt_row1 = QHBoxLayout()
        opt_row1.setSpacing(12)

        # IRCTC ID
        acct_col = QVBoxLayout()
        acct_col.setSpacing(4)
        l_aid = QLabel("IRCTC ID")
        l_aid.setObjectName("fieldLabel")
        self.account_combo = QComboBox()
        self.account_combo.addItem("- Select -", None)
        self.account_combo.setFixedHeight(38)
        acct_col.addWidget(l_aid)
        acct_col.addWidget(self.account_combo)
        opt_row1.addLayout(acct_col, stretch=2)

        # MOBILE (+91) + 🎲
        mob_col = QVBoxLayout()
        mob_col.setSpacing(4)
        l_mob = QLabel("MOBILE (+91)")
        l_mob.setObjectName("fieldLabel")
        mob_input_lay = QHBoxLayout()
        mob_input_lay.setSpacing(4)
        self.mobile_edit = QLineEdit()
        self.mobile_edit.setPlaceholderText("9876543210")
        self.mobile_edit.setMaxLength(10)
        self.mobile_edit.setFixedHeight(38)
        mob_input_lay.addWidget(self.mobile_edit)

        self.btn_dice = QPushButton("🎲")
        self.btn_dice.setObjectName("btnDice")
        self.btn_dice.setFixedSize(36, 38)
        self.btn_dice.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_dice.clicked.connect(self._randomize_mobile)
        mob_input_lay.addWidget(self.btn_dice)

        mob_col.addWidget(l_mob)
        mob_col.addLayout(mob_input_lay)
        opt_row1.addLayout(mob_col, stretch=2)

        # MAX PT FARE
        fare_col = QVBoxLayout()
        fare_col.setSpacing(4)
        l_fare = QLabel("MAX PT FARE")
        l_fare.setObjectName("fieldLabel")
        self.max_fare_edit = QLineEdit()
        self.max_fare_edit.setPlaceholderText("Max PT Fare")
        self.max_fare_edit.setFixedHeight(38)
        fare_col.addWidget(l_fare)
        fare_col.addWidget(self.max_fare_edit)
        opt_row1.addLayout(fare_col, stretch=2)

        # BANK / GATEWAY
        bank_col = QVBoxLayout()
        bank_col.setSpacing(4)
        l_bank = QLabel("BANK / GATEWAY")
        l_bank.setObjectName("fieldLabel")
        self.bank_combo = QComboBox()
        self.bank_combo.addItem("- Select -", None)
        for label, val in BACKUP_GATEWAYS[1:]:
            self.bank_combo.addItem(label, val)
        self.bank_combo.setFixedHeight(38)
        bank_col.addWidget(l_bank)
        bank_col.addWidget(self.bank_combo)
        opt_row1.addLayout(bank_col, stretch=3)

        bl.addLayout(opt_row1)

        # Row: ALTERNATE BANK / GATEWAY *
        alt_bank_col = QVBoxLayout()
        alt_bank_col.setSpacing(4)
        l_alt = QLabel("ALTERNATE BANK / GATEWAY *")
        l_alt.setObjectName("fieldLabel")
        self.alt_bank_combo = QComboBox()
        for label, val in BACKUP_GATEWAYS:
            self.alt_bank_combo.addItem(label, val)
        self.alt_bank_combo.setFixedHeight(38)
        alt_bank_col.addWidget(l_alt)
        alt_bank_col.addWidget(self.alt_bank_combo)
        bl.addLayout(alt_bank_col)

        # Toggles Row 1: Auto Upgradation & Fill captcha manually
        toggles_lay1 = QHBoxLayout()
        toggles_lay1.setSpacing(24)

        t1_box = QHBoxLayout()
        t1_box.setSpacing(8)
        t1_lbl = QLabel("Auto Upgradation")
        t1_lbl.setStyleSheet("font-size: 13px; color: #334155; font-weight: 500;")
        self.sw_auto_upgrade = ToggleSwitch(checked=False)
        t1_box.addWidget(t1_lbl)
        t1_box.addWidget(self.sw_auto_upgrade)
        toggles_lay1.addLayout(t1_box)

        t2_box = QHBoxLayout()
        t2_box.setSpacing(8)
        t2_lbl = QLabel("Fill captcha manually")
        t2_lbl.setStyleSheet("font-size: 13px; color: #334155; font-weight: 500;")
        self.sw_manual_captcha = ToggleSwitch(checked=False)
        t2_box.addWidget(t2_lbl)
        t2_box.addWidget(self.sw_manual_captcha)
        toggles_lay1.addLayout(t2_box)
        toggles_lay1.addStretch(1)

        bl.addLayout(toggles_lay1)

        # Toggles Row 2: Travel Insurance (YES/NO), Food (YES/NO), Book only if confirmed
        toggles_lay2 = QHBoxLayout()
        toggles_lay2.setSpacing(24)

        # Travel Insurance
        ins_box = QHBoxLayout()
        ins_box.setSpacing(8)
        ins_lbl = QLabel("Travel Insurance")
        ins_lbl.setStyleSheet("font-size: 13px; color: #334155; font-weight: 500;")
        self.pill_insurance = YesNoToggle(initial_yes=False)
        ins_box.addWidget(ins_lbl)
        ins_box.addWidget(self.pill_insurance)
        toggles_lay2.addLayout(ins_box)

        # Food
        food_box = QHBoxLayout()
        food_box.setSpacing(8)
        food_lbl = QLabel("Food")
        food_lbl.setStyleSheet("font-size: 13px; color: #334155; font-weight: 500;")
        self.pill_food = YesNoToggle(initial_yes=False)
        food_box.addWidget(food_lbl)
        food_box.addWidget(self.pill_food)
        toggles_lay2.addLayout(food_box)

        # Book only if confirmed berths available
        cnf_box = QHBoxLayout()
        cnf_box.setSpacing(8)
        cnf_lbl = QLabel("Book only if confirmed berths available")
        cnf_lbl.setStyleSheet("font-size: 13px; color: #334155; font-weight: 500;")
        self.sw_book_cnf = ToggleSwitch(checked=True)
        cnf_box.addWidget(cnf_lbl)
        cnf_box.addWidget(self.sw_book_cnf)
        toggles_lay2.addLayout(cnf_box)
        toggles_lay2.addStretch(1)

        bl.addLayout(toggles_lay2)

        # -------------------------------------------------------------
        # Bottom row: TICKET_NAME, IP, Cancel, SAVE
        # -------------------------------------------------------------
        bottom_box = QHBoxLayout()
        bottom_box.setSpacing(14)

        # TICKET_NAME
        tn_col = QVBoxLayout()
        tn_col.setSpacing(4)
        l_tn = QLabel("TICKET_NAME")
        l_tn.setObjectName("fieldLabel")
        self.ticket_name_edit = QLineEdit()
        self.ticket_name_edit.setPlaceholderText("e.g. bwn_kan_ssingh")
        self.ticket_name_edit.setFixedHeight(38)
        tn_col.addWidget(l_tn)
        tn_col.addWidget(self.ticket_name_edit)
        bottom_box.addLayout(tn_col, stretch=3)

        # IP
        ip_col = QVBoxLayout()
        ip_col.setSpacing(4)
        l_ip = QLabel("IP")
        l_ip.setObjectName("fieldLabel")
        self.proxy_combo = QComboBox()
        self.proxy_combo.addItem("Home IP", None)
        self.proxy_combo.setFixedHeight(38)
        ip_col.addWidget(l_ip)
        ip_col.addWidget(self.proxy_combo)
        bottom_box.addLayout(ip_col, stretch=2)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        btn_box_spacer = QVBoxLayout()
        btn_box_spacer.setSpacing(4)
        btn_box_spacer.addWidget(QLabel(""))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.setFixedHeight(38)
        self.btn_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_cancel.clicked.connect(self.hide)
        btn_row.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("💾  SAVE")
        self.btn_save.setObjectName("btnSave")
        self.btn_save.setFixedHeight(38)
        self.btn_save.setMinimumWidth(120)
        self.btn_save.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_save.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(self.btn_save)

        btn_box_spacer.addLayout(btn_row)
        bottom_box.addLayout(btn_box_spacer, stretch=2)

        bl.addLayout(bottom_box)

        scroll.setWidget(body)
        lay.addWidget(scroll)
        root.addWidget(main_card)

        # Default: 1 empty passenger row
        self._add_empty_passenger_row()

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#bookTicketRoot {
                background: transparent;
            }
            QFrame#bookMainCard {
                background: #091a2b;
                border: 1px solid #1e3a5f;
                border-radius: 12px;
            }
            QFrame#bookHead {
                background: #0c1e34;
                border-bottom: 1px solid #1e3a5f;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#bookTitle {
                color: #ffffff;
                font-size: 15px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QPushButton#bookClose {
                background: #0d1a28;
                color: #e8f4fa;
                border: 1px solid #1e3a5f;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#bookClose:hover {
                background: #dc2626;
                border-color: #ef4444;
                color: #ffffff;
            }
            QLabel#fieldLabel {
                font-size: 11px;
                font-weight: 800;
                color: #94a3b8;
                letter-spacing: 0.5px;
            }
            QLabel#sectionHeader {
                font-size: 13px;
                font-weight: 800;
                color: #38bdf8;
                letter-spacing: 0.5px;
                margin-top: 10px;
                margin-bottom: 4px;
            }
            QLabel#bookAvailPill {
                background: #064e3b;
                color: #bbf7d0;
                border: 1px solid #10b981;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.5px;
                padding: 2px 10px;
            }
            QPushButton#btnSwap {
                background: #081422;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                color: #38bdf8;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#btnSwap:hover {
                background: #0d2238;
                border-color: #38bdf8;
            }
            QPushButton#btnPurplePrimary {
                background: #7c3aed;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-weight: 700;
                font-size: 13px;
                padding: 0 14px;
            }
            QPushButton#btnPurplePrimary:hover {
                background: #8b5cf6;
            }
            QPushButton#btnAddPax {
                background: transparent;
                color: #38bdf8;
                border: none;
                font-weight: 700;
                font-size: 13px;
                padding: 4px 8px;
            }
            QPushButton#btnAddPax:hover {
                color: #7dd3fc;
            }
            QPushButton#btnDice {
                background: #081422;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-size: 16px;
                color: #ffffff;
            }
            QPushButton#btnDice:hover {
                background: #0d2238;
            }
            QPushButton#btnCancel {
                background: #141f2e;
                color: #f87171;
                border: 1px solid #7f1d1d;
                border-radius: 6px;
                font-weight: 700;
                padding: 0 16px;
            }
            QPushButton#btnCancel:hover {
                background: #450a0a;
            }
            QPushButton#btnSave {
                background: #7c3aed;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-weight: 800;
                font-size: 13px;
                letter-spacing: 0.5px;
            }
            QPushButton#btnSave:hover {
                background: #8b5cf6;
            }
            QLineEdit, QComboBox, QDateEdit {
                background: #081422;
                color: #ffffff;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                padding: 5px 8px;
                selection-background-color: #7c3aed;
                selection-color: #ffffff;
            }
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
                border-color: #7c3aed;
            }
            QComboBox QAbstractItemView {
                background: #081422;
                color: #ffffff;
                border: 1px solid #1e3a5f;
                selection-background-color: #7c3aed;
                selection-color: #ffffff;
            }
            QScrollArea#bookScroll {
                background: transparent;
                border: none;
            }
            QWidget#bookBody {
                background: #091a2b;
            }
            QTableWidget#paxTable {
                background-color: #081422;
                gridline-color: #0e2d3e;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                min-height: 160px;
                color: #ffffff;
            }
            QTableWidget#paxTable::item {
                padding: 2px 4px;
                border: none;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #0c1e34;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 800;
                padding: 6px 4px;
                border: none;
                border-bottom: 1px solid #1e3a5f;
            }
        """)

    def _setup_completers(self) -> None:
        """Attach autocomplete to Station and Train fields."""
        station_completions = self._master_data_service.get_station_completions()
        if station_completions:
            c_from = QCompleter(station_completions, self)
            c_from.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            c_from.setFilterMode(Qt.MatchFlag.MatchContains)
            self.from_edit.setCompleter(c_from)

            c_to = QCompleter(station_completions, self)
            c_to.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            c_to.setFilterMode(Qt.MatchFlag.MatchContains)
            self.to_edit.setCompleter(c_to)

        train_completions = self._master_data_service.get_train_completions()
        if train_completions:
            c_tr = QCompleter(train_completions, self)
            c_tr.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            c_tr.setFilterMode(Qt.MatchFlag.MatchContains)
            self.train_edit.setCompleter(c_tr)

    def _swap_stations(self) -> None:
        """Swap FROM and TO station fields."""
        f = self.from_edit.text()
        t = self.to_edit.text()
        self.from_edit.setText(t)
        self.to_edit.setText(f)

    def _randomize_mobile(self) -> None:
        """Generate realistic Indian 10-digit mobile number."""
        prefix = random.choice(["6", "7", "8", "9"])
        rest = "".join(str(random.randint(0, 9)) for _ in range(9))
        self.mobile_edit.setText(prefix + rest)

    def _add_empty_passenger_row(self) -> None:
        """Add new passenger row up to max 6."""
        row = self.pax_table.rowCount()
        if row >= 6:
            return

        self.pax_table.insertRow(row)

        # 0. S.NO
        sno = QLabel(str(row + 1))
        sno.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sno.setStyleSheet("font-weight: 700; color: #94a3b8;")
        self.pax_table.setCellWidget(row, 0, sno)

        # 1. FULL NAME
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Enter full name")
        name_edit.textChanged.connect(self._auto_generate_ticket_name)
        self.pax_table.setCellWidget(row, 1, name_edit)

        # 2. AGE
        age_edit = QLineEdit()
        age_edit.setPlaceholderText("Age")
        age_edit.setMaxLength(3)
        self.pax_table.setCellWidget(row, 2, age_edit)

        # 3. GENDER
        gender_combo = QComboBox()
        gender_combo.addItems(GENDERS)
        self.pax_table.setCellWidget(row, 3, gender_combo)

        # 4. BERTH PREF
        berth_combo = QComboBox()
        berth_combo.addItems(BERTHS)
        self.pax_table.setCellWidget(row, 4, berth_combo)

        # 5. FOOD
        food_combo = QComboBox()
        food_combo.addItems(FOODS)
        self.pax_table.setCellWidget(row, 5, food_combo)

        # 6. Remove button ✕
        btn_del = QPushButton("✕")
        btn_del.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                color: #ef4444;
            }
        """)
        btn_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_del.clicked.connect(lambda _, r=row: self._remove_passenger_row(r))
        self.pax_table.setCellWidget(row, 6, btn_del)

        self.pax_table.setRowHeight(row, 36)

    def _remove_passenger_row(self, row_idx: int) -> None:
        """Remove specified passenger row and re-number S.NO."""
        if self.pax_table.rowCount() <= 1:
            return  # keep at least one
        self.pax_table.removeRow(row_idx)
        # Re-number S.NO and rebind delete buttons
        for r in range(self.pax_table.rowCount()):
            lbl = self.pax_table.cellWidget(r, 0)
            if isinstance(lbl, QLabel):
                lbl.setText(str(r + 1))
            btn = self.pax_table.cellWidget(r, 6)
            if isinstance(btn, QPushButton):
                btn.clicked.disconnect()
                btn.clicked.connect(lambda _, row_num=r: self._remove_passenger_row(row_num))
        self._auto_generate_ticket_name()

    def _auto_generate_ticket_name(self) -> None:
        """Auto-populate ticket name in format: <from>_<to>_<first_pax_surname>."""
        f = self._clean_station(self.from_edit.text()).lower()
        t = self._clean_station(self.to_edit.text()).lower()

        pax_name = ""
        if self.pax_table.rowCount() > 0:
            w = self.pax_table.cellWidget(0, 1)
            if isinstance(w, QLineEdit):
                full = w.text().strip().lower()
                parts = full.split()
                if parts:
                    pax_name = parts[-1]  # last name or single name

        if f and t:
            sugg = f"{f}_{t}"
            if pax_name:
                sugg += f"_{pax_name}"
            self.ticket_name_edit.setText(sugg)

    @staticmethod
    def _clean_station(text: str) -> str:
        return resolve_station_code(text)

    @staticmethod
    def _clean_train_no(text: str) -> str:
        s = text.strip()
        if " - " in s:
            s = s.split(" - ", 1)[0].strip()
        m = re.search(r"(\d{4,5})", s)
        return m.group(1) if m else s

    def apply_train_selection(self, selection: dict) -> None:
        """Fill journey fields from TrainResultsWindow selection."""
        train_no = selection.get("trainNo", "")
        train_name = selection.get("trainName", "")
        if train_no and train_name:
            self.train_edit.setText(f"{train_name} ({train_no})")
        elif train_no:
            self.train_edit.setText(train_no)

        cls = selection.get("trainClass", "")
        if cls:
            idx = self.class_combo.findData(cls)
            if idx < 0:
                idx = self.class_combo.findText(cls, Qt.MatchFlag.MatchContains)
            if idx >= 0:
                self.class_combo.setCurrentIndex(idx)

        quota = selection.get("quota", "TQ")
        if quota:
            idx = self.quota_combo.findData(quota)
            if idx < 0:
                idx = self.quota_combo.findText(quota, Qt.MatchFlag.MatchContains)
            if idx >= 0:
                self.quota_combo.setCurrentIndex(idx)

        if selection.get("from"):
            self.from_edit.setText(selection["from"])
        if selection.get("to"):
            self.to_edit.setText(selection["to"])

        if selection.get("availability") or selection.get("fare") is not None:
            self.set_availability_status(
                selection.get("availability", ""),
                is_available=bool(selection.get("is_available", True)),
                fare=selection.get("fare"),
            )

        self._auto_generate_ticket_name()

    def set_availability_status(self, text: str, is_available: bool = True, fare: int | None = None) -> None:
        """Show/update the availability pill below the Class/Quota row."""
        display = (text or "").strip()
        if fare is not None and "₹" not in display:
            display = f"{display} | ₹{fare:,}" if display else f"₹{fare:,}"
        self.avail_pill.setText(display)
        if is_available:
            self.avail_pill.setStyleSheet("""
                QLabel {
                    background: #064e3b;
                    color: #bbf7d0;
                    border: 1px solid #10b981;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 800;
                    letter-spacing: 0.5px;
                    padding: 2px 10px;
                }
            """)
        else:
            self.avail_pill.setStyleSheet("""
                QLabel {
                    background: #7c2d12;
                    color: #fdba74;
                    border: 1px solid #f97316;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 800;
                    letter-spacing: 0.5px;
                    padding: 2px 10px;
                }
            """)

    def set_accounts(self, accounts: list[dict]) -> None:
        """Populate IRCTC accounts combo."""
        self._accounts = accounts
        self.account_combo.clear()
        self.account_combo.addItem("- Select -", None)
        for a in accounts:
            self.account_combo.addItem(a.get("username", ""), a.get("id"))

    def set_proxies(self, proxies: list[dict]) -> None:
        """Populate Network Proxies combo."""
        self._proxies = proxies
        self.proxy_combo.clear()
        self.proxy_combo.addItem("Home IP", None)
        for p in proxies:
            name = p.get("name") or f"{p.get('host')}:{p.get('port')}"
            self.proxy_combo.addItem(name, p.get("id"))

    def set_payments(self, payments: list[dict]) -> None:
        """Populate Bank / Gateway combos."""
        self._payments = payments
        self.bank_combo.clear()
        self.bank_combo.addItem("- Select -", None)
        for p in payments:
            label = f"{p.get('gateway', '')} · {p.get('identifier', '')}"
            self.bank_combo.addItem(label, p.get("id"))

    def get_form_data(self) -> dict[str, Any]:
        """Collect all form inputs into a structured ticket dictionary."""
        passengers = []
        for r in range(self.pax_table.rowCount()):
            name_w = self.pax_table.cellWidget(r, 1)
            age_w = self.pax_table.cellWidget(r, 2)
            gen_w = self.pax_table.cellWidget(r, 3)
            berth_w = self.pax_table.cellWidget(r, 4)
            food_w = self.pax_table.cellWidget(r, 5)

            name = name_w.text().strip() if isinstance(name_w, QLineEdit) else ""
            age = age_w.text().strip() if isinstance(age_w, QLineEdit) else ""
            gender = gen_w.currentText() if isinstance(gen_w, QComboBox) else "Male"
            berth = berth_w.currentText() if isinstance(berth_w, QComboBox) else "No Preference"
            food = food_w.currentText() if isinstance(food_w, QComboBox) else "No Preference"

            if name:
                passengers.append({
                    "name": name,
                    "age": int(age) if age.isdigit() else 30,
                    "gender": gender,
                    "berth_preference": berth,
                    "food_preference": food,
                })

        train_raw = self.train_edit.text()
        train_no = self._clean_train_no(train_raw)

        return {
            "id": self._ticket_id,
            "train_number": train_no,
            "train_name": train_raw,
            "from_station": self._clean_station(self.from_edit.text()),
            "to_station": self._clean_station(self.to_edit.text()),
            "journey_date": self.date_edit.date().toString("yyyy-MM-dd"),
            "class": self.class_combo.currentData() or self.class_combo.currentText(),
            "quota": self.quota_combo.currentData() or self.quota_combo.currentText(),
            "passenger_details": json.dumps(passengers),
            "passengers": passengers,
            "mobile": self.mobile_edit.text().strip() or None,
            "max_pt_fare": self.max_fare_edit.text().strip() or None,
            "irctc_account_id": self.account_combo.currentData(),
            "bank_gateway": self.bank_combo.currentText(),
            "alternate_bank_gateway": self.alt_bank_combo.currentText(),
            "auto_upgrade": self.sw_auto_upgrade.isChecked(),
            "manual_captcha": self.sw_manual_captcha.isChecked(),
            "insurance": self.pill_insurance.is_yes(),
            "food": self.pill_food.is_yes(),
            "book_only_if_cnf": self.sw_book_cnf.isChecked(),
            "ticket_name": self.ticket_name_edit.text().strip() or f"{self.from_edit.text()}_{self.to_edit.text()}",
            "proxy_id": self.proxy_combo.currentData(),
            "status": "draft",
        }

    def load_ticket(self, ticket: dict) -> None:
        """Load an existing ticket profile into the form."""
        self._ticket_id = ticket.get("id")
        self.from_edit.setText(ticket.get("from_station", ""))
        self.to_edit.setText(ticket.get("to_station", ""))

        jd = ticket.get("journey_date", "")
        if jd:
            d = QDate.fromString(jd, "yyyy-MM-dd")
            if d.isValid():
                self.date_edit.setDate(d)

        tr_no = ticket.get("train_number", "")
        tr_name = ticket.get("train_name", "")
        self.train_edit.setText(f"{tr_name} ({tr_no})" if tr_name and tr_no else tr_no)

        cls = ticket.get("class", "")
        idx = self.class_combo.findData(cls)
        if idx >= 0:
            self.class_combo.setCurrentIndex(idx)

        quota = ticket.get("quota", "")
        idx = self.quota_combo.findData(quota)
        if idx >= 0:
            self.quota_combo.setCurrentIndex(idx)

        self.mobile_edit.setText(ticket.get("mobile", "") or "")
        self.max_fare_edit.setText(str(ticket.get("max_pt_fare", "") or ""))

        acct_id = ticket.get("irctc_account_id")
        if acct_id:
            idx = self.account_combo.findData(acct_id)
            if idx >= 0:
                self.account_combo.setCurrentIndex(idx)

        proxy_id = ticket.get("proxy_id")
        if proxy_id:
            idx = self.proxy_combo.findData(proxy_id)
            if idx >= 0:
                self.proxy_combo.setCurrentIndex(idx)

        self.sw_auto_upgrade.setChecked(bool(ticket.get("auto_upgrade", False)))
        self.sw_manual_captcha.setChecked(bool(ticket.get("manual_captcha", False)))
        self.pill_insurance.set_yes(bool(ticket.get("insurance", False)))
        self.pill_food.set_yes(bool(ticket.get("food", False)))
        self.sw_book_cnf.setChecked(bool(ticket.get("book_only_if_cnf", True)))

        self.ticket_name_edit.setText(ticket.get("ticket_name", ""))

        # Passengers
        raw_pax = ticket.get("passenger_details", "")
        passengers = []
        if isinstance(raw_pax, str) and raw_pax.strip():
            try:
                passengers = json.loads(raw_pax)
            except Exception:
                passengers = []
        elif isinstance(raw_pax, list):
            passengers = raw_pax

        self.pax_table.setRowCount(0)
        for p in passengers:
            self._add_empty_passenger_row()
            r = self.pax_table.rowCount() - 1
            nw = self.pax_table.cellWidget(r, 1)
            aw = self.pax_table.cellWidget(r, 2)
            gw = self.pax_table.cellWidget(r, 3)
            bw = self.pax_table.cellWidget(r, 4)
            fw = self.pax_table.cellWidget(r, 5)
            if isinstance(nw, QLineEdit):
                nw.setText(str(p.get("name", "")))
            if isinstance(aw, QLineEdit):
                aw.setText(str(p.get("age", "")))
            if isinstance(gw, QComboBox):
                gw.setCurrentText(str(p.get("gender", "Male")))
            if isinstance(bw, QComboBox):
                bw.setCurrentText(str(p.get("berth_preference", "No Preference")))
            if isinstance(fw, QComboBox):
                fw.setCurrentText(str(p.get("food_preference", "No Preference")))

        if self.pax_table.rowCount() == 0:
            self._add_empty_passenger_row()

    def reset_form(self) -> None:
        """Clear form to default state for new ticket creation."""
        self._ticket_id = None
        self.from_edit.clear()
        self.to_edit.clear()
        self.date_edit.setDate(QDate.currentDate().addDays(1))
        self.train_edit.clear()
        self.class_combo.setCurrentIndex(0)
        self.quota_combo.setCurrentIndex(0)
        self.mobile_edit.clear()
        self.max_fare_edit.clear()
        self.account_combo.setCurrentIndex(0)
        self.proxy_combo.setCurrentIndex(0)
        self.sw_auto_upgrade.setChecked(False)
        self.sw_manual_captcha.setChecked(False)
        self.pill_insurance.set_yes(False)
        self.pill_food.set_yes(False)
        self.sw_book_cnf.setChecked(True)
        self.ticket_name_edit.clear()
        self.pax_table.setRowCount(0)
        self._add_empty_passenger_row()

    def _on_save_clicked(self) -> None:
        """Validate and emit save signal."""
        data = self.get_form_data()
        if not data["from_station"]:
            QMessageBox.warning(self, "Validation Error", "From station is required.")
            return
        if not data["to_station"]:
            QMessageBox.warning(self, "Validation Error", "To station is required.")
            return
        if data["from_station"] == data["to_station"]:
            QMessageBox.warning(self, "Validation Error", "From and To stations cannot be the same.")
            return
        if not data["train_number"]:
            QMessageBox.warning(self, "Validation Error", "Train number is required.")
            return
        if not data["passengers"]:
            QMessageBox.warning(self, "Validation Error", "At least one passenger is required.")
            return

        self.save_clicked.emit(data)
        self.hide()
