"""Payment methods window matching real Bingo UI.

Matches Screenshot_2026-11-14-21-03-32-01 and Screenshot_2026-11-14-21-17-18-73
with UPI / Card / Freecharge tabs, gateway dropdown, cyan TYPE pills,
and payment methods table.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer, Signal
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

from bingo_linux.ui.app_icon import apply_bingo_icon, bingo_logo_pixmap
from bingo_linux.ui.window_drag import enable_window_drag

UPI_GATEWAYS = [
    ("IPAYQR", "IPAYQR (IRCTC iPay QR)"),
    ("PHONEPEQR", "PHONEPEQR (PhonePe QR)"),
    ("PAYTMQR", "PAYTMQR (Paytm QR)"),
    ("IRCQR", "IRCQR (IRCTC QR)"),
    ("RAZORPAYQR", "RAZORPAYQR (RazorPay QR)"),
    ("PAYUQR", "PAYUQR (PayU QR)"),
    ("IRCUPIID", "IRCUPIID (IRCTC UPI ID)"),
    ("PHONEPEUPIID", "PHONEPEUPIID (PhonePe UPI ID)"),
    ("PAYTMUPIID", "PAYTMUPIID (Paytm UPI ID)"),
    ("RAZORPAYUPI", "RAZORPAYUPI (RazorPay UPI ID)"),
    ("PAYUUPIID", "PAYUUPIID (PayU UPI ID)"),
]


def is_qr_gateway(gw: str) -> bool:
    """Check if the payment method uses dynamic QR codes instead of static VPA."""
    return "QR" in (gw or "").upper()


class ToastNotification(QLabel):
    """Floating pill toast notification."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            background: #059669;
            color: #ffffff;
            border-radius: 14px;
            padding: 6px 16px;
            font-size: 12px;
            font-weight: 700;
        """)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, message: str, duration_ms: int = 3000) -> None:
        self.setText(f"✓  {message}")
        self.adjustSize()
        pw = self.parentWidget().width()
        ph = self.parentWidget().height()
        w = max(self.width() + 24, 180)
        h = max(self.height() + 8, 36)
        self.setGeometry((pw - w) // 2, ph - 60, w, h)
        self.show()
        self.raise_()
        self._timer.start(duration_ms)


class PaymentWindow(QWidget):
    """Payment methods window matching official Bingo screenshot UI."""

    add_payment = Signal(dict)       # {"type": ..., "gateway": ..., "identifier": ...}
    delete_payment = Signal(str)    # payment_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("Payment Methods")
        self.resize(720, 560)
        self.setMinimumSize(640, 480)
        self.setObjectName("paymentWindowRoot")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self._payments: list[dict[str, Any]] = []
        self._current_tab = 0  # 0=UPI, 1=Card, 2=Freecharge

        self._setup_ui()
        self._setup_styles()
        self.toast = ToastNotification(self)
        enable_window_drag(self, self.head_frame)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        main_card = QFrame()
        main_card.setObjectName("payMainCard")
        lay = QVBoxLayout(main_card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 1. Header Frame
        self.head_frame = QFrame()
        self.head_frame.setObjectName("payHead")
        self.head_frame.setFixedHeight(54)
        hl = QHBoxLayout(self.head_frame)
        hl.setContentsMargins(18, 10, 14, 10)
        hl.setSpacing(12)

        logo_lbl = QLabel()
        logo_lbl.setPixmap(bingo_logo_pixmap(24))
        hl.addWidget(logo_lbl)

        title_lbl = QLabel("💳  PAYMENT METHODS")
        title_lbl.setObjectName("payTitle")
        hl.addWidget(title_lbl)

        hl.addStretch(1)

        # Tabs: UPI | Card | Freecharge
        tabs_box = QHBoxLayout()
        tabs_box.setSpacing(4)
        self.btn_tab_upi = QPushButton("UPI")
        self.btn_tab_upi.setObjectName("tabBtnActive")
        self.btn_tab_upi.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_tab_upi.clicked.connect(lambda: self._switch_tab(0))
        tabs_box.addWidget(self.btn_tab_upi)

        self.btn_tab_card = QPushButton("Card")
        self.btn_tab_card.setObjectName("tabBtnInactive")
        self.btn_tab_card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_tab_card.clicked.connect(lambda: self._switch_tab(1))
        tabs_box.addWidget(self.btn_tab_card)

        self.btn_tab_fc = QPushButton("Freecharge")
        self.btn_tab_fc.setObjectName("tabBtnInactive")
        self.btn_tab_fc.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_tab_fc.clicked.connect(lambda: self._switch_tab(2))
        tabs_box.addWidget(self.btn_tab_fc)
        hl.addLayout(tabs_box)

        # Close
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("payClose")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.clicked.connect(self.hide)
        hl.addWidget(self.btn_close)

        lay.addWidget(self.head_frame)

        # 2. Form Container
        self.form_container = QWidget()
        self.form_layout = QVBoxLayout(self.form_container)
        self.form_layout.setContentsMargins(20, 14, 20, 14)
        self.form_layout.setSpacing(10)

        # UPI Form
        self.upi_widget = QWidget()
        ul = QHBoxLayout(self.upi_widget)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.setSpacing(14)

        # Gateway
        gw_box = QVBoxLayout()
        gw_box.setSpacing(4)
        l_gw = QLabel("GATEWAY")
        l_gw.setObjectName("fieldLabel")
        self.gateway_combo = QComboBox()
        for code, label in UPI_GATEWAYS:
            self.gateway_combo.addItem(label, code)
        self.gateway_combo.setFixedHeight(38)
        self.gateway_combo.currentIndexChanged.connect(self._on_gateway_changed)
        gw_box.addWidget(l_gw)
        gw_box.addWidget(self.gateway_combo)
        ul.addLayout(gw_box, stretch=3)

        # UPI ID
        upi_box = QVBoxLayout()
        upi_box.setSpacing(4)
        l_upi = QLabel("UPI ID")
        l_upi.setObjectName("fieldLabel")
        self.upi_input = QLineEdit()
        self.upi_input.setPlaceholderText("yourname@bank")
        self.upi_input.setFixedHeight(38)
        upi_box.addWidget(l_upi)
        upi_box.addWidget(self.upi_input)
        ul.addLayout(upi_box, stretch=4)
        self._on_gateway_changed()

        # + Add UPI button
        add_box = QVBoxLayout()
        add_box.setSpacing(4)
        add_box.addWidget(QLabel(""))  # spacer
        self.btn_add_upi = QPushButton("+ Add UPI")
        self.btn_add_upi.setObjectName("btnPurplePrimary")
        self.btn_add_upi.setFixedHeight(38)
        self.btn_add_upi.setMinimumWidth(110)
        self.btn_add_upi.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add_upi.clicked.connect(self._on_add_upi)
        add_box.addWidget(self.btn_add_upi)
        ul.addLayout(add_box, stretch=2)

        self.form_layout.addWidget(self.upi_widget)

        # Card Form
        self.card_widget = QWidget()
        cl = QHBoxLayout(self.card_widget)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(12)

        c_nick_box = QVBoxLayout()
        c_nick_box.setSpacing(4)
        l_cn = QLabel("CARD NICKNAME")
        l_cn.setObjectName("fieldLabel")
        self.card_nick_input = QLineEdit()
        self.card_nick_input.setPlaceholderText("e.g. HDFC Credit Card")
        self.card_nick_input.setFixedHeight(38)
        c_nick_box.addWidget(l_cn)
        c_nick_box.addWidget(self.card_nick_input)
        cl.addLayout(c_nick_box, stretch=3)

        c_bank_box = QVBoxLayout()
        c_bank_box.setSpacing(4)
        l_cb = QLabel("BANK / TYPE")
        l_cb.setObjectName("fieldLabel")
        self.card_bank_combo = QComboBox()
        self.card_bank_combo.addItems(["HDFC Bank", "ICICI Bank", "SBI Card", "Axis Bank", "Kotak Bank", "Other"])
        self.card_bank_combo.setFixedHeight(38)
        c_bank_box.addWidget(l_cb)
        c_bank_box.addWidget(self.card_bank_combo)
        cl.addLayout(c_bank_box, stretch=3)

        c_btn_box = QVBoxLayout()
        c_btn_box.setSpacing(4)
        c_btn_box.addWidget(QLabel(""))
        self.btn_add_card = QPushButton("+ Add Card")
        self.btn_add_card.setObjectName("btnPurplePrimary")
        self.btn_add_card.setFixedHeight(38)
        self.btn_add_card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add_card.clicked.connect(self._on_add_card)
        c_btn_box.addWidget(self.btn_add_card)
        cl.addLayout(c_btn_box, stretch=2)

        self.card_widget.hide()
        self.form_layout.addWidget(self.card_widget)

        # Freecharge Form
        self.fc_widget = QWidget()
        fl = QHBoxLayout(self.fc_widget)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(12)

        fc_box = QVBoxLayout()
        fc_box.setSpacing(4)
        l_fcm = QLabel("FREECHARGE MOBILE")
        l_fcm.setObjectName("fieldLabel")
        self.fc_mobile_input = QLineEdit()
        self.fc_mobile_input.setPlaceholderText("10-digit registered mobile")
        self.fc_mobile_input.setFixedHeight(38)
        fc_box.addWidget(l_fcm)
        fc_box.addWidget(self.fc_mobile_input)
        fl.addLayout(fc_box, stretch=4)

        fc_btn_box = QVBoxLayout()
        fc_btn_box.setSpacing(4)
        fc_btn_box.addWidget(QLabel(""))
        self.btn_link_fc = QPushButton("+ Link Freecharge")
        self.btn_link_fc.setObjectName("btnPurplePrimary")
        self.btn_link_fc.setFixedHeight(38)
        self.btn_link_fc.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_link_fc.clicked.connect(self._on_link_fc)
        fc_btn_box.addWidget(self.btn_link_fc)
        fl.addLayout(fc_btn_box, stretch=2)

        self.fc_widget.hide()
        self.form_layout.addWidget(self.fc_widget)

        lay.addWidget(self.form_container)

        # 3. List Header: ALL METHODS  X
        list_head = QFrame()
        list_head.setObjectName("payListHead")
        list_head.setFixedHeight(44)
        lhl = QHBoxLayout(list_head)
        lhl.setContentsMargins(20, 4, 20, 4)

        self.methods_count_lbl = QLabel("ALL METHODS  0")
        self.methods_count_lbl.setObjectName("countLabel")
        lhl.addWidget(self.methods_count_lbl)
        lhl.addStretch(1)

        lay.addWidget(list_head)

        # 4. Table: #, TYPE, GATEWAY, IDENTIFIER, delete
        self.table = QTableWidget(0, 5)
        self.table.setObjectName("payTable")
        self.table.setHorizontalHeaderLabels([
            "#", "TYPE", "GATEWAY", "IDENTIFIER", ""
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 50)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 80)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 50)

        lay.addWidget(self.table)
        root.addWidget(main_card)

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#paymentWindowRoot {
                background: transparent;
            }
            QFrame#payMainCard {
                background: #091a2b;
                border: 1px solid #1e3a5f;
                border-radius: 12px;
            }
            QFrame#payHead {
                background: #0c1e34;
                border-bottom: 1px solid #1e3a5f;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#payTitle {
                color: #ffffff;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QPushButton#tabBtnActive {
                background: #7c3aed;
                color: #ffffff;
                border: 1px solid #8b5cf6;
                border-radius: 6px;
                font-weight: 700;
                font-size: 12px;
                padding: 4px 14px;
            }
            QPushButton#tabBtnInactive {
                background: transparent;
                color: #94a3b8;
                border: none;
                font-weight: 600;
                font-size: 12px;
                padding: 4px 14px;
            }
            QPushButton#tabBtnInactive:hover {
                color: #ffffff;
            }
            QPushButton#payClose {
                background: #0d1a28;
                color: #e8f4fa;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#payClose:hover {
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
            QPushButton#btnPurplePrimary {
                background: #7c3aed;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-weight: 700;
                font-size: 13px;
                padding: 0 16px;
            }
            QPushButton#btnPurplePrimary:hover {
                background: #8b5cf6;
            }
            QFrame#payListHead {
                background: #071524;
                border-top: 1px solid #1e3a5f;
                border-bottom: 1px solid #1e3a5f;
            }
            QLabel#countLabel {
                font-size: 12px;
                font-weight: 800;
                color: #38bdf8;
                letter-spacing: 0.5px;
            }
            QLineEdit, QComboBox {
                background: #081422;
                color: #ffffff;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #7c3aed;
            }
            QComboBox QAbstractItemView {
                background: #081422;
                color: #ffffff;
                border: 1px solid #1e3a5f;
                selection-background-color: #7c3aed;
                selection-color: #ffffff;
            }
            QTableWidget#payTable {
                background-color: #081422;
                alternate-background-color: #061222;
                gridline-color: #0e2d3e;
                border: none;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                color: #ffffff;
            }
            QTableWidget#payTable::item {
                padding: 8px 6px;
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

    def _switch_tab(self, index: int) -> None:
        self._current_tab = index
        self.btn_tab_upi.setObjectName("tabBtnActive" if index == 0 else "tabBtnInactive")
        self.btn_tab_card.setObjectName("tabBtnActive" if index == 1 else "tabBtnInactive")
        self.btn_tab_fc.setObjectName("tabBtnActive" if index == 2 else "tabBtnInactive")

        self.upi_widget.setVisible(index == 0)
        self.card_widget.setVisible(index == 1)
        self.fc_widget.setVisible(index == 2)
        self._setup_styles()

    def set_payments(self, payments: list[dict[str, Any]]) -> None:
        """Update payment methods list."""
        self._payments = payments
        self._render_table()

    def _render_table(self) -> None:
        self.table.setRowCount(len(self._payments))
        self.methods_count_lbl.setText(f"ALL METHODS  {len(self._payments)}")

        for row, p in enumerate(self._payments):
            pid = p.get("id", "")

            # 0. #
            idx_item = QTableWidgetItem(str(row + 1))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, idx_item)

            # 1. TYPE (cyan pill)
            type_lbl = QLabel(p.get("type", "UPI").upper())
            type_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            type_lbl.setStyleSheet("""
                background: #0c4a6e;
                color: #38bdf8;
                font-size: 10px;
                font-weight: 800;
                border-radius: 8px;
                padding: 2px 8px;
            """)
            type_wrap = QWidget()
            tl = QHBoxLayout(type_wrap)
            tl.setContentsMargins(0, 0, 0, 0)
            tl.addWidget(type_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 1, type_wrap)

            # 2. GATEWAY
            gw_item = QTableWidgetItem(p.get("gateway", ""))
            gw_font = QFont()
            gw_font.setBold(True)
            gw_item.setFont(gw_font)
            self.table.setItem(row, 2, gw_item)

            # 3. IDENTIFIER
            id_item = QTableWidgetItem(p.get("identifier", ""))
            self.table.setItem(row, 3, id_item)

            # 4. Actions: delete
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
            btn_del.clicked.connect(lambda _, payment_id=pid: self._on_delete(payment_id))
            del_wrap = QWidget()
            dl = QHBoxLayout(del_wrap)
            dl.setContentsMargins(0, 0, 0, 0)
            dl.addWidget(btn_del, alignment=Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 4, del_wrap)

        self.table.resizeRowsToContents()

    def _on_gateway_changed(self) -> None:
        gw = self.gateway_combo.currentData() or self.gateway_combo.currentText()
        if is_qr_gateway(gw):
            self.upi_input.setPlaceholderText("Dynamic QR code at checkout (No UPI ID required)")
        else:
            self.upi_input.setPlaceholderText("yourname@bank")

    def _on_add_upi(self) -> None:
        gw = self.gateway_combo.currentData() or self.gateway_combo.currentText()
        upi_id = self.upi_input.text().strip()
        is_qr = is_qr_gateway(gw)

        if not is_qr and not upi_id:
            QMessageBox.warning(self, "Validation Error", "UPI ID is required for UPI ID payments.")
            return

        identifier = upi_id if upi_id else "Dynamic QR"
        self.add_payment.emit({
            "type": "QR" if is_qr else "UPI",
            "gateway": gw,
            "identifier": identifier,
        })
        self.upi_input.clear()
        self.toast.show_message(f"Added {gw}")

    def show_toast(self, message: str) -> None:
        self.toast.show_message(message)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "toast") and self.toast.isVisible():
            pw = self.width()
            ph = self.height()
            w = self.toast.width()
            h = self.toast.height()
            self.toast.setGeometry((pw - w) // 2, ph - 60, w, h)

    def _on_add_card(self) -> None:
        nick = self.card_nick_input.text().strip()
        bank = self.card_bank_combo.currentText()
        if not nick:
            QMessageBox.warning(self, "Validation Error", "Card nickname is required.")
            return

        self.add_payment.emit({
            "type": "Card",
            "gateway": bank,
            "identifier": nick,
        })
        self.card_nick_input.clear()

    def _on_link_fc(self) -> None:
        mob = self.fc_mobile_input.text().strip()
        if not mob or len(mob) != 10:
            QMessageBox.warning(self, "Validation Error", "Enter valid 10-digit mobile number.")
            return

        self.add_payment.emit({
            "type": "Freecharge",
            "gateway": "FREECHARGE",
            "identifier": f"Mobile: {mob}",
        })
        self.fc_mobile_input.clear()

    def _on_delete(self, payment_id: str) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Payment Method",
            "Are you sure you want to remove this payment method?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_payment.emit(payment_id)
