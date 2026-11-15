"""Dialog for managing Freecharge payment accounts and QR payment pairing.

Implements the user-controlled payment workflows matching payment.html:
1. Linked Account Management (view sessions, check balance, unlink).
2. Step-by-step Mobile & Bank Linking flow.
3. QR Payment Pairing and Cancellation monitor.

Strict Compliance: No card numbers or CVVs are ever requested or stored.
All OTPs and PINs are entered manually by the user.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bingo_linux.services.payment_service import PaymentService


class LinkAccountWizardDialog(QDialog):
    """Step-by-step modal wizard for linking a mobile number and bank account."""

    account_linked = Signal()

    def __init__(self, payment_service: PaymentService, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._service = payment_service
        self._session_id: Optional[str] = None
        self._mobile: str = ""

        self.setWindowTitle("Link Freecharge & Bank Account")
        self.setFixedSize(480, 420)
        self.setModal(True)

        self._setup_ui()
        self._setup_styles()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title
        title = QLabel("Link Bank Account")
        t_font = QFont()
        t_font.setPointSize(14)
        t_font.setBold(True)
        title.setFont(t_font)
        title.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(title)

        # Wizard Stack
        self.stack = QStackedWidget()

        # Page 0: Mobile Entry
        self.page_mobile = QWidget()
        m_layout = QVBoxLayout(self.page_mobile)
        m_layout.setSpacing(12)
        lbl_m = QLabel("Enter your 10-digit registered mobile number:")
        lbl_m.setStyleSheet("color: #b0b0b0; font-size: 12px;")
        m_layout.addWidget(lbl_m)

        self.input_mobile = QLineEdit()
        self.input_mobile.setPlaceholderText("e.g. 9876543210")
        self.input_mobile.setMaxLength(10)
        self.input_mobile.setStyleSheet(
            "QLineEdit { background: #333; color: #fff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 8px; font-size: 14px; }"
        )
        m_layout.addWidget(self.input_mobile)
        m_layout.addStretch()

        btn_send_otp = QPushButton("Send Login OTP")
        btn_send_otp.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_send_otp.setStyleSheet(
            "QPushButton { background: #42a5f5; color: #fff; border: none; "
            "border-radius: 4px; padding: 10px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background: #54b3f6; }"
        )
        btn_send_otp.clicked.connect(self._on_send_otp)
        m_layout.addWidget(btn_send_otp)
        self.stack.addWidget(self.page_mobile)

        # Page 1: OTP Entry
        self.page_otp = QWidget()
        otp_layout = QVBoxLayout(self.page_otp)
        otp_layout.setSpacing(12)
        self.lbl_otp_prompt = QLabel("Enter the OTP sent to your mobile:")
        self.lbl_otp_prompt.setStyleSheet("color: #b0b0b0; font-size: 12px;")
        otp_layout.addWidget(self.lbl_otp_prompt)

        self.input_otp = QLineEdit()
        self.input_otp.setPlaceholderText("Enter 4-6 digit OTP")
        self.input_otp.setMaxLength(6)
        self.input_otp.setStyleSheet(
            "QLineEdit { background: #333; color: #fff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 8px; font-size: 14px; }"
        )
        otp_layout.addWidget(self.input_otp)
        otp_layout.addStretch()

        btn_verify_otp = QPushButton("Verify OTP")
        btn_verify_otp.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_verify_otp.setStyleSheet(
            "QPushButton { background: #4caf50; color: #fff; border: none; "
            "border-radius: 4px; padding: 10px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background: #66bb6a; }"
        )
        btn_verify_otp.clicked.connect(self._on_verify_otp)
        otp_layout.addWidget(btn_verify_otp)
        self.stack.addWidget(self.page_otp)

        # Page 2: Bank Selection
        self.page_bank = QWidget()
        b_layout = QVBoxLayout(self.page_bank)
        b_layout.setSpacing(12)
        lbl_b = QLabel("Select your bank to link UPI account:")
        lbl_b.setStyleSheet("color: #b0b0b0; font-size: 12px;")
        b_layout.addWidget(lbl_b)

        self.combo_banks = QComboBox()
        for b in self._service.get_banks():
            self.combo_banks.addItem(f"{b['name']} ({b['code']})", b["id"])
        self.combo_banks.setStyleSheet(
            "QComboBox { background: #333; color: #fff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 8px; font-size: 13px; }"
            "QComboBox QAbstractItemView { background: #222; color: #fff; }"
        )
        b_layout.addWidget(self.combo_banks)
        b_layout.addStretch()

        btn_link_bank = QPushButton("Link Selected Bank")
        btn_link_bank.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_link_bank.setStyleSheet(
            "QPushButton { background: #42a5f5; color: #fff; border: none; "
            "border-radius: 4px; padding: 10px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background: #54b3f6; }"
        )
        btn_link_bank.clicked.connect(self._on_link_bank)
        b_layout.addWidget(btn_link_bank)
        self.stack.addWidget(self.page_bank)

        # Page 3: PIN Verification & Completion
        self.page_pin = QWidget()
        p_layout = QVBoxLayout(self.page_pin)
        p_layout.setSpacing(12)
        lbl_pin = QLabel("Enter your UPI PIN to verify account balance:")
        lbl_pin.setStyleSheet("color: #b0b0b0; font-size: 12px;")
        p_layout.addWidget(lbl_pin)

        self.input_pin = QLineEdit()
        self.input_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pin.setPlaceholderText("4 or 6-digit PIN")
        self.input_pin.setMaxLength(6)
        self.input_pin.setStyleSheet(
            "QLineEdit { background: #333; color: #fff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 8px; font-size: 14px; }"
        )
        p_layout.addWidget(self.input_pin)
        p_layout.addStretch()

        btn_finish = QPushButton("Complete Setup & Check Balance")
        btn_finish.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_finish.setStyleSheet(
            "QPushButton { background: #4caf50; color: #fff; border: none; "
            "border-radius: 4px; padding: 10px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background: #66bb6a; }"
        )
        btn_finish.clicked.connect(self._on_finish_pin)
        p_layout.addWidget(btn_finish)
        self.stack.addWidget(self.page_pin)

        layout.addWidget(self.stack)

    def _setup_styles(self) -> None:
        self.setStyleSheet("QDialog { background-color: #1e1e1e; }")

    def _on_send_otp(self) -> None:
        mobile = self.input_mobile.text().strip()
        res = self._service.send_login_otp(mobile)
        if not res.get("ok"):
            QMessageBox.warning(self, "Invalid Mobile", res.get("error", "Error sending OTP"))
            return
        self._session_id = res.get("sessionId")
        self._mobile = mobile
        self.lbl_otp_prompt.setText(f"Enter the OTP sent to +91 {mobile}:")
        self.stack.setCurrentIndex(1)

    def _on_verify_otp(self) -> None:
        otp = self.input_otp.text().strip()
        if not self._session_id:
            return
        res = self._service.verify_login_otp(self._session_id, otp)
        if not res.get("ok"):
            QMessageBox.warning(self, "OTP Failed", res.get("error", "Invalid OTP"))
            return
        self.stack.setCurrentIndex(2)

    def _on_link_bank(self) -> None:
        bank_id = self.combo_banks.currentData()
        if not self._session_id:
            return
        res = self._service.link_bank(self._session_id, bank_id)
        if not res.get("ok"):
            QMessageBox.warning(self, "Link Failed", res.get("error", "Failed to link bank"))
            return
        self.stack.setCurrentIndex(3)

    def _on_finish_pin(self) -> None:
        pin = self.input_pin.text().strip()
        if not self._session_id:
            return
        res = self._service.check_balance(self._session_id, pin)
        if not res.get("ok"):
            QMessageBox.warning(self, "PIN Error", res.get("error", "Invalid PIN"))
            return
        balance = res.get("balance", 0.0)
        QMessageBox.information(
            self,
            "Bank Linked",
            f"Bank account successfully linked!\nVerified balance: ₹{balance:,.2f}",
        )
        self.account_linked.emit()
        self.accept()


class PaymentDialog(QDialog):
    """Main Payment Management dialog for Freecharge and QR workflows."""

    def __init__(self, payment_service: PaymentService, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._service = payment_service
        self._qr_timer = QTimer(self)
        self._qr_timer.setInterval(1000)
        self._qr_timer.timeout.connect(self._on_qr_tick)
        self._qr_remaining_sec: int = 180

        self.setWindowTitle("Payment Management")
        self.setMinimumSize(680, 480)
        self.setModal(True)

        self._setup_ui()
        self._setup_styles()
        self._refresh_sessions()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        top_row = QHBoxLayout()
        title_label = QLabel("Payment & Gateway Setup")
        t_font = QFont()
        t_font.setPointSize(16)
        t_font.setBold(True)
        title_label.setFont(t_font)
        title_label.setStyleSheet("color: #ffffff; background: transparent;")
        top_row.addWidget(title_label)
        top_row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #b0b0b0; border: none; font-size: 16px; }"
            "QPushButton:hover { color: #ffffff; background: #3d3d3d; border-radius: 15px; }"
        )
        close_btn.clicked.connect(self.accept)
        top_row.addWidget(close_btn)
        layout.addLayout(top_row)

        # Compliance Banner
        banner = QFrame()
        banner.setStyleSheet(
            "QFrame { background: #1a2f1c; border: 1px solid #4caf50; border-radius: 4px; padding: 6px; }"
        )
        b_layout = QHBoxLayout(banner)
        b_layout.setContentsMargins(10, 4, 10, 4)
        lbl_b = QLabel("🔒 Safe Client: Payment confirmation & OTPs remain 100% user-controlled.")
        lbl_b.setStyleSheet("color: #a5d6a7; font-size: 11px; font-weight: bold;")
        b_layout.addWidget(lbl_b)
        layout.addWidget(banner)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #3d3d3d; background: #252525; border-radius: 6px; }"
            "QTabBar::tab { background: #1f1f1f; color: #b0b0b0; padding: 8px 20px; font-weight: bold; border-top-left-radius: 4px; border-top-right-radius: 4px; }"
            "QTabBar::tab:selected { background: #252525; color: #42a5f5; border-bottom: 2px solid #42a5f5; }"
        )

        # Tab 1: Linked Sessions
        tab_sessions = QWidget()
        s_layout = QVBoxLayout(tab_sessions)
        s_layout.setContentsMargins(14, 14, 14, 14)
        s_layout.setSpacing(12)

        self.table_sessions = QTableWidget()
        self.table_sessions.setColumnCount(5)
        self.table_sessions.setHorizontalHeaderLabels(
            ["Mobile", "Status", "Bank Linked", "Cached Balance", "Last Checked"]
        )
        self.table_sessions.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_sessions.verticalHeader().setVisible(False)
        self.table_sessions.setStyleSheet(
            "QTableWidget { background-color: #1e1e1e; border: 1px solid #3d3d3d; border-radius: 4px; color: #ffffff; }"
            "QHeaderView::section { background-color: #2b2b2b; color: #b0b0b0; padding: 6px; border: none; font-size: 11px; font-weight: bold; }"
            "QTableWidget::item { padding: 6px; border-bottom: 1px solid #2a2a2a; font-size: 12px; }"
        )
        s_layout.addWidget(self.table_sessions)

        btn_row = QHBoxLayout()
        self.btn_link = QPushButton("Link New Bank Account")
        self.btn_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_link.setStyleSheet(
            "QPushButton { background: #4caf50; color: #ffffff; border: none; "
            "border-radius: 4px; padding: 8px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #66bb6a; }"
        )
        self.btn_link.clicked.connect(self._on_open_wizard)
        btn_row.addWidget(self.btn_link)

        self.btn_unlink = QPushButton("Unlink Selected")
        self.btn_unlink.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_unlink.setStyleSheet(
            "QPushButton { background: #d32f2f; color: #ffffff; border: none; "
            "border-radius: 4px; padding: 8px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #e57373; }"
        )
        self.btn_unlink.clicked.connect(self._on_unlink_selected)
        btn_row.addWidget(self.btn_unlink)

        btn_row.addStretch()
        s_layout.addLayout(btn_row)
        self.tabs.addTab(tab_sessions, "Linked Accounts")

        # Tab 2: QR Payment Pairing Monitor
        tab_qr = QWidget()
        qr_layout = QVBoxLayout(tab_qr)
        qr_layout.setContentsMargins(16, 16, 16, 16)
        qr_layout.setSpacing(14)

        qr_desc = QLabel(
            "Active QR Payment Session: Simulates UPI dynamic QR payment pairing "
            "with client-side expiry monitoring (booking:confirm-pair-qr / booking:cancel-qr)."
        )
        qr_desc.setWordWrap(True)
        qr_desc.setStyleSheet("color: #b0b0b0; font-size: 12px;")
        qr_layout.addWidget(qr_desc)

        # QR card
        qr_card = QFrame()
        qr_card.setStyleSheet("QFrame { background: #1a1a1a; border: 1px solid #3d3d3d; border-radius: 6px; padding: 14px; }")
        c_layout = QVBoxLayout(qr_card)
        c_layout.setSpacing(8)

        self.lbl_qr_status = QLabel("QR Status: Ready for Pairing")
        self.lbl_qr_status.setStyleSheet("color: #42a5f5; font-size: 14px; font-weight: bold;")
        c_layout.addWidget(self.lbl_qr_status)

        self.lbl_qr_timer = QLabel("Session Expiry: 180 seconds")
        self.lbl_qr_timer.setStyleSheet("color: #ffb74d; font-size: 12px;")
        c_layout.addWidget(self.lbl_qr_timer)

        qr_layout.addWidget(qr_card)
        qr_layout.addStretch()

        qr_btn_row = QHBoxLayout()
        self.btn_pair = QPushButton("Confirm QR Pairing")
        self.btn_pair.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pair.setStyleSheet(
            "QPushButton { background: #4caf50; color: #fff; border: none; "
            "border-radius: 4px; padding: 8px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #66bb6a; }"
        )
        self.btn_pair.clicked.connect(self._on_confirm_pair)
        qr_btn_row.addWidget(self.btn_pair)

        self.btn_cancel_qr = QPushButton("Cancel QR Session")
        self.btn_cancel_qr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel_qr.setStyleSheet(
            "QPushButton { background: #f44336; color: #fff; border: none; "
            "border-radius: 4px; padding: 8px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #ff5252; }"
        )
        self.btn_cancel_qr.clicked.connect(self._on_cancel_qr)
        qr_btn_row.addWidget(self.btn_cancel_qr)

        qr_btn_row.addStretch()
        qr_layout.addLayout(qr_btn_row)

        self.tabs.addTab(tab_qr, "QR Payment Monitor")
        layout.addWidget(self.tabs)

        self._qr_timer.start()

    def _setup_styles(self) -> None:
        self.setStyleSheet("QDialog { background-color: #1e1e1e; }")

    def _refresh_sessions(self) -> None:
        sessions = self._service.list_sessions()
        self.table_sessions.setRowCount(len(sessions))

        for row, s in enumerate(sessions):
            self.table_sessions.setItem(row, 0, QTableWidgetItem(s.get("mobile", "")))
            status = "Verified" if s.get("otp_verified") else "Unverified"
            self.table_sessions.setItem(row, 1, QTableWidgetItem(status))
            bank = "Linked" if s.get("bank_linked") else "Not Linked"
            self.table_sessions.setItem(row, 2, QTableWidgetItem(bank))
            bal = f"₹{s.get('balance', 0.0):,.2f}"
            self.table_sessions.setItem(row, 3, QTableWidgetItem(bal))
            last = s.get("last_checked") or "Never"
            self.table_sessions.setItem(row, 4, QTableWidgetItem(str(last)[:19]))

    def _on_open_wizard(self) -> None:
        wiz = LinkAccountWizardDialog(self._service, parent=self)
        wiz.account_linked.connect(self._refresh_sessions)
        wiz.exec()

    def _on_unlink_selected(self) -> None:
        row = self.table_sessions.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select Account", "Please select an account row to unlink.")
            return

        sessions = self._service.list_sessions()
        if row >= len(sessions):
            return

        session_id = sessions[row].get("sessionId")
        if not session_id:
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Unlink",
            "Are you sure you want to unlink this payment session?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._service.cancel_session(session_id)
            self._refresh_sessions()

    def _on_qr_tick(self) -> None:
        if self._qr_remaining_sec > 0:
            self._qr_remaining_sec -= 1
            self.lbl_qr_timer.setText(f"Session Expiry: {self._qr_remaining_sec} seconds")
        else:
            self._qr_timer.stop()
            self.lbl_qr_status.setText("QR Status: Expired")
            self.lbl_qr_timer.setText("Session Expiry: Timed out (Auto-cancelled)")
            self._service.cancel_qr("auto_ticket", 1)

    def _on_confirm_pair(self) -> None:
        res = self._service.confirm_pair_qr("demo_ticket", 1)
        self.lbl_qr_status.setText("QR Status: Paired & Confirmed ✔")
        QMessageBox.information(self, "QR Paired", "Payment QR successfully paired and confirmed.")

    def _on_cancel_qr(self) -> None:
        res = self._service.cancel_qr("demo_ticket", 1)
        self.lbl_qr_status.setText("QR Status: Cancelled ✖")
        self._qr_timer.stop()
        QMessageBox.information(self, "QR Cancelled", "Payment QR session has been cancelled.")
