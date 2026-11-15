"""IRCTC credentials manager window matching real Bingo UI.

Matches Screenshot_2026-11-14-21-05-35-97 and Screenshot_2026-11-14-21-17-47-62
with Single / Bulk import tabs, password show/hide eye, active toggle switch,
and green toast notification.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bingo_linux.ui.app_icon import apply_bingo_icon, bingo_logo_pixmap
from bingo_linux.ui.widgets.toggle_switch import ToggleSwitch
from bingo_linux.ui.window_drag import enable_window_drag


class ToastNotification(QLabel):
    """Floating pill toast notification (e.g. '✓ Added <username>')."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            background: #10b981;
            color: #ffffff;
            border-radius: 16px;
            padding: 8px 20px;
            font-size: 13px;
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
        w = self.width() + 24
        h = self.height()
        self.setGeometry((pw - w) // 2, ph - 60, w, h)
        self.show()
        self.raise_()
        self._timer.start(duration_ms)


class AccountsWindow(QWidget):
    """IRCTC accounts window matching official Bingo screenshot UI."""

    add_account = Signal(dict)       # {"username": ..., "password": ...}
    bulk_import = Signal(list)       # [{"username": ..., "password": ...}]
    delete_account = Signal(str)     # account_id
    toggle_active = Signal(str, bool)# account_id, active

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("IRCTC Accounts")
        self.resize(720, 640)
        self.setMinimumSize(640, 520)
        self.setObjectName("accountsWindowRoot")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self._accounts: list[dict[str, Any]] = []
        self._filter_text: str = ""

        self._setup_ui()
        self._setup_styles()
        self.toast = ToastNotification(self)
        enable_window_drag(self, self.head_frame)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        main_card = QFrame()
        main_card.setObjectName("acctMainCard")
        lay = QVBoxLayout(main_card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 1. Header Frame
        self.head_frame = QFrame()
        self.head_frame.setObjectName("acctHead")
        self.head_frame.setFixedHeight(54)
        hl = QHBoxLayout(self.head_frame)
        hl.setContentsMargins(18, 10, 14, 10)
        hl.setSpacing(12)

        logo_lbl = QLabel()
        logo_lbl.setPixmap(bingo_logo_pixmap(24))
        hl.addWidget(logo_lbl)

        title_lbl = QLabel("🪪  IRCTC ACCOUNTS")
        title_lbl.setObjectName("acctTitle")
        hl.addWidget(title_lbl)

        hl.addStretch(1)

        # Tabs: Single | Bulk import
        tabs_box = QHBoxLayout()
        tabs_box.setSpacing(4)
        self.btn_tab_single = QPushButton("Single")
        self.btn_tab_single.setObjectName("tabBtnActive")
        self.btn_tab_single.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_tab_single.clicked.connect(lambda: self._switch_tab(0))
        tabs_box.addWidget(self.btn_tab_single)

        self.btn_tab_bulk = QPushButton("Bulk import")
        self.btn_tab_bulk.setObjectName("tabBtnInactive")
        self.btn_tab_bulk.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_tab_bulk.clicked.connect(lambda: self._switch_tab(1))
        tabs_box.addWidget(self.btn_tab_bulk)
        hl.addLayout(tabs_box)

        # Close
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("acctClose")
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

        # Single Form Widget
        self.single_widget = QWidget()
        sl = QHBoxLayout(self.single_widget)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(12)

        # Username
        u_box = QVBoxLayout()
        u_box.setSpacing(4)
        u_lbl = QLabel("IRCTC USERNAME")
        u_lbl.setObjectName("fieldLabel")
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("myaccount99")
        self.user_input.setFixedHeight(38)
        u_box.addWidget(u_lbl)
        u_box.addWidget(self.user_input)
        sl.addLayout(u_box, stretch=3)

        # Password + Eye show/hide
        p_box = QVBoxLayout()
        p_box.setSpacing(4)
        p_lbl = QLabel("PASSWORD")
        p_lbl.setObjectName("fieldLabel")

        p_row = QHBoxLayout()
        p_row.setSpacing(4)
        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("••••••••")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setFixedHeight(38)
        p_row.addWidget(self.pass_input)

        self.btn_eye = QPushButton("👁")
        self.btn_eye.setObjectName("btnEye")
        self.btn_eye.setFixedSize(36, 38)
        self.btn_eye.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_eye.clicked.connect(self._toggle_pass_visibility)
        p_row.addWidget(self.btn_eye)

        p_box.addWidget(p_lbl)
        p_box.addLayout(p_row)
        sl.addLayout(p_box, stretch=3)

        # + Add account button
        add_box = QVBoxLayout()
        add_box.setSpacing(4)
        add_box.addWidget(QLabel(""))  # spacer
        self.btn_add = QPushButton("+ Add account")
        self.btn_add.setObjectName("btnPurplePrimary")
        self.btn_add.setFixedHeight(38)
        self.btn_add.setMinimumWidth(130)
        self.btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add.clicked.connect(self._on_add_account)
        add_box.addWidget(self.btn_add)
        sl.addLayout(add_box, stretch=2)

        self.form_layout.addWidget(self.single_widget)

        # Bulk Form Widget
        self.bulk_widget = QWidget()
        bl = QVBoxLayout(self.bulk_widget)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)

        bulk_hint = QLabel("Enter username:password per line, or one username per line with password on top:")
        bulk_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        bl.addWidget(bulk_hint)

        self.bulk_input = QTextEdit()
        self.bulk_input.setPlaceholderText("user1:pass1\nuser2:pass2")
        self.bulk_input.setFixedHeight(80)
        bl.addWidget(self.bulk_input)

        self.btn_bulk_add = QPushButton("+ Bulk Import Accounts")
        self.btn_bulk_add.setObjectName("btnPurplePrimary")
        self.btn_bulk_add.setFixedHeight(36)
        self.btn_bulk_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_bulk_add.clicked.connect(self._on_bulk_import)
        bl.addWidget(self.btn_bulk_add, alignment=Qt.AlignmentFlag.AlignRight)

        self.bulk_widget.hide()
        self.form_layout.addWidget(self.bulk_widget)

        lay.addWidget(self.form_container)

        # 3. List Header: ALL ACCOUNTS  X  |  Search username...
        list_head = QFrame()
        list_head.setObjectName("acctListHead")
        list_head.setFixedHeight(44)
        lhl = QHBoxLayout(list_head)
        lhl.setContentsMargins(20, 4, 20, 4)
        lhl.setSpacing(12)

        self.accounts_count_lbl = QLabel("ALL ACCOUNTS  0")
        self.accounts_count_lbl.setObjectName("countLabel")
        lhl.addWidget(self.accounts_count_lbl)

        lhl.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("acctSearch")
        self.search_input.setPlaceholderText("Search username...")
        self.search_input.setFixedWidth(200)
        self.search_input.setFixedHeight(30)
        self.search_input.textChanged.connect(self._on_search_changed)
        lhl.addWidget(self.search_input)

        lay.addWidget(list_head)

        # 4. Table: #, USERNAME, BOOKINGS, ACTIVE, ACTIONS
        self.table = QTableWidget(0, 5)
        self.table.setObjectName("acctTable")
        self.table.setHorizontalHeaderLabels([
            "#", "USERNAME", "BOOKINGS", "ACTIVE", ""
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
        self.table.setColumnWidth(2, 100)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 90)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 80)

        lay.addWidget(self.table)
        root.addWidget(main_card)

        # Floating Toast Notification
        self.toast = ToastNotification(self)

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#accountsWindowRoot {
                background: transparent;
            }
            QFrame#acctMainCard {
                background: #091a2b;
                border: 1px solid #1e3a5f;
                border-radius: 12px;
            }
            QFrame#acctHead {
                background: #0c1e34;
                border-bottom: 1px solid #1e3a5f;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#acctTitle {
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
                padding: 4px 12px;
            }
            QPushButton#tabBtnInactive {
                background: transparent;
                color: #94a3b8;
                border: none;
                font-weight: 600;
                font-size: 12px;
                padding: 4px 12px;
            }
            QPushButton#tabBtnInactive:hover {
                color: #ffffff;
            }
            QPushButton#acctClose {
                background: #0d1a28;
                color: #e8f4fa;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#acctClose:hover {
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
            QPushButton#btnEye {
                background: #081422;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-size: 14px;
                color: #ffffff;
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
            QFrame#acctListHead {
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
            QLineEdit#acctSearch {
                background: #081422;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 11px;
                color: #ffffff;
            }
            QLineEdit, QTextEdit {
                background: #081422;
                color: #ffffff;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border-color: #7c3aed;
            }
            QTableWidget#acctTable {
                background-color: #081422;
                alternate-background-color: #061222;
                gridline-color: #0e2d3e;
                border: none;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                color: #ffffff;
            }
            QTableWidget#acctTable::item {
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

    def _switch_tab(self, index: int) -> None:
        if index == 0:
            self.btn_tab_single.setObjectName("tabBtnActive")
            self.btn_tab_bulk.setObjectName("tabBtnInactive")
            self.single_widget.show()
            self.bulk_widget.hide()
        else:
            self.btn_tab_single.setObjectName("tabBtnInactive")
            self.btn_tab_bulk.setObjectName("tabBtnActive")
            self.single_widget.hide()
            self.bulk_widget.show()
        self._setup_styles()

    def _toggle_pass_visibility(self) -> None:
        if self.pass_input.echoMode() == QLineEdit.EchoMode.Password:
            self.pass_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)

    def set_accounts(self, accounts: list[dict[str, Any]]) -> None:
        """Update accounts list."""
        self._accounts = accounts
        self._render_table()

    def _on_search_changed(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        self._render_table()

    def _render_table(self) -> None:
        filtered = self._accounts
        if self._filter_text:
            filtered = [
                a for a in self._accounts
                if self._filter_text in (a.get("username") or "").lower()
            ]

        self.table.setRowCount(len(filtered))
        self.accounts_count_lbl.setText(f"ALL ACCOUNTS  {len(filtered)}")

        for row, a in enumerate(filtered):
            acct_id = a.get("id", "")

            # 0. #
            idx_item = QTableWidgetItem(str(row + 1))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, idx_item)

            # 1. USERNAME
            u_item = QTableWidgetItem(a.get("username", ""))
            u_font = QFont()
            u_font.setBold(True)
            u_item.setFont(u_font)
            self.table.setItem(row, 1, u_item)

            # 2. BOOKINGS
            bk_item = QTableWidgetItem(str(a.get("bookings_count", 0)))
            bk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, bk_item)

            # 3. ACTIVE toggle
            sw = ToggleSwitch(checked=bool(a.get("is_active", True)))
            sw.toggled.connect(lambda val, aid=acct_id: self.toggle_active.emit(aid, val))
            sw_wrap = QWidget()
            sw_lay = QHBoxLayout(sw_wrap)
            sw_lay.setContentsMargins(0, 0, 0, 0)
            sw_lay.addWidget(sw, alignment=Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 3, sw_wrap)

            # 4. Actions: ✏️  🗑️
            act_wrap = QWidget()
            al = QHBoxLayout(act_wrap)
            al.setContentsMargins(0, 0, 0, 0)
            al.setSpacing(6)

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
            btn_del.clicked.connect(lambda _, aid=acct_id: self._on_delete(aid))
            al.addWidget(btn_del)
            al.addStretch(1)
            self.table.setCellWidget(row, 4, act_wrap)

        self.table.resizeRowsToContents()

    def _on_add_account(self) -> None:
        user = self.user_input.text().strip()
        pwd = self.pass_input.text().strip()
        if not user or not pwd:
            QMessageBox.warning(self, "Validation Error", "Username and password are required.")
            return

        self.add_account.emit({"username": user, "password": pwd})
        self.user_input.clear()
        self.pass_input.clear()
        self.toast.show_message(f"Added {user}")

    def _on_bulk_import(self) -> None:
        text = self.bulk_input.toPlainText().strip()
        if not text:
            return

        lines = [l.strip() for l in text.splitlines() if l.strip()]
        creds = []
        for line in lines:
            if ":" in line:
                u, p = line.split(":", 1)
                creds.append({"username": u.strip(), "password": p.strip()})
            else:
                creds.append({"username": line.strip(), "password": "password123"})

        if creds:
            self.bulk_import.emit(creds)
            self.bulk_input.clear()
            self.toast.show_message(f"Imported {len(creds)} accounts")

    def _on_delete(self, acct_id: str) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Account",
            "Are you sure you want to remove this account?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_account.emit(acct_id)

    def show_toast(self, message: str) -> None:
        """Display non-blocking floating status toast.

        Never raises: the toast is lazily created and any underlying
        Qt failure is swallowed so callers (e.g. Application handlers)
        cannot crash on a toast.
        """
        try:
            toast = getattr(self, "toast", None)
            if toast is None:
                toast = ToastNotification(self)
                self.toast = toast
            toast.show_message(message)
        except Exception:
            pass

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "toast") and self.toast.isVisible():
            pw = self.width()
            ph = self.height()
            w = self.toast.width()
            h = self.toast.height()
            self.toast.setGeometry((pw - w) // 2, ph - 60, w, h)
