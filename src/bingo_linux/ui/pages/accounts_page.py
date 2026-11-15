"""Railway Accounts page.

Page for managing railway account profiles (e.g. IRCTC accounts).
Integrates with the SQLite repository layer and master security vault.

Features:
- List account profiles (non-sensitive fields only)
- Add new accounts (password encrypted via vault)
- Edit existing accounts
- Delete accounts with confirmation
- Vault lock integration
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bingo_linux.services import (
    DuplicateUsernameError,
    IrctcAccountService,
    VaultRequiredError,
)
from bingo_linux.ui.dialogs.account_dialog import AccountDialog
from bingo_linux.security.vault import (
    InvalidPasswordError,
    VaultLockedError,
    VaultNotConfiguredError,
    VaultService,
)

from PySide6.QtWidgets import QMessageBox


class AccountsPage(QWidget):
    """Page for managing railway account profiles.

    Integrates with IrctcAccountService and VaultService for
    persistent, encrypted account storage.
    """

    #: Emitted when an account is added, updated, or deleted.
    accounts_changed = Signal()

    def __init__(
        self,
        service: IrctcAccountService,
        vault: VaultService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._vault = vault
        self._setup_ui()
        self._refresh_accounts()

    def _setup_ui(self) -> None:
        """Initialize the accounts page layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Page header
        header_layout = QHBoxLayout()
        title = QLabel("Railway Accounts")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #ffffff; background-color: transparent; border: none;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        # Vault status indicator
        self._vault_status = QLabel()
        self._vault_status.setStyleSheet("font-size: 12px; font-weight: bold;")
        self._update_vault_status_label()
        header_layout.addWidget(self._vault_status)

        btn_add = QPushButton("Add Profile")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet(
            "QPushButton { background-color: #42a5f5; color: #ffffff; border: none; "
            "border-radius: 6px; padding: 8px 16px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #54b3f6; }"
            "QPushButton:disabled { background-color: #555555; color: #888888; }"
        )
        btn_add.clicked.connect(self._on_add_account)
        header_layout.addWidget(btn_add)

        self._btn_add = btn_add
        self._update_add_button_state()

        layout.addLayout(header_layout)

        # Table - railway account profiles
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Username", "Mobile", "Email", "Status", "Actions"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #2d2d2d; border: 1px solid #3d3d3d; "
            "border-radius: 6px; gridline-color: #3d3d3d; color: #ffffff; }"
            "QTableWidget::item { padding: 8px; border: none; }"
            "QTableWidget::item:selected { background-color: #42a5f5; }"
            "QHeaderView::section { background-color: #252525; color: #b0b0b0; "
            "padding: 8px; border: none; font-weight: bold; }"
        )
        layout.addWidget(self.table)

        # Empty state
        self._show_empty_state()

    def _update_vault_status_label(self) -> None:
        """Update the vault status indicator text."""
        if not self._vault.is_configured():
            self._vault_status.setText("Vault: Not configured")
            self._vault_status.setStyleSheet(
                "color: #ff9800; font-size: 12px; font-weight: bold;"
            )
        elif not self._vault.is_unlocked():
            self._vault_status.setText("Vault: Locked")
            self._vault_status.setStyleSheet(
                "color: #f44336; font-size: 12px; font-weight: bold;"
            )
        else:
            self._vault_status.setText("Vault: Unlocked")
            self._vault_status.setStyleSheet(
                "color: #4caf50; font-size: 12px; font-weight: bold;"
            )

    def _update_add_button_state(self) -> None:
        """Enable/disable the add button based on vault state."""
        can_add = self._vault.is_configured() and self._vault.is_unlocked()
        self._btn_add.setEnabled(can_add)

    def _refresh_accounts(self) -> None:
        """Refresh the account table from the service layer."""
        accounts = self._service.list_accounts()
        self._populate_table(accounts)

    def _populate_table(self, accounts: list[dict]) -> None:
        """Populate the table with account data.

        Non-sensitive fields only. Passwords are never displayed.
        """
        if not accounts:
            self._show_empty_state()
            return

        self.table.setRowCount(len(accounts))
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Username", "Mobile", "Email", "Status", "Actions"]
        )

        for row, acct in enumerate(accounts):
            # Username
            self.table.setItem(
                row, 0, QTableWidgetItem(acct.get("username", ""))
            )
            # Mobile
            mobile = acct.get("mobile") or ""
            self.table.setItem(row, 1, QTableWidgetItem(mobile))
            # Email
            email = acct.get("email") or ""
            self.table.setItem(row, 2, QTableWidgetItem(email))
            # Status
            status = "Active" if acct.get("is_active") else "Inactive"
            status_item = QTableWidgetItem(status)
            status_item.setForeground(
                Qt.GlobalColor.green if acct.get("is_active") else Qt.GlobalColor.gray
            )
            self.table.setItem(row, 3, status_item)

            # Actions
            from PySide6.QtWidgets import QHBoxLayout as _QHBoxLayout
            from PySide6.QtWidgets import QWidget as _QWidget

            actions_widget = _QWidget()
            actions_layout = _QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            actions_layout.setSpacing(4)

            btn_edit = QPushButton("Edit")
            btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_edit.setProperty("account_id", acct["id"])
            btn_edit.clicked.connect(self._on_edit_account)
            btn_edit.setStyleSheet(
                "QPushButton { background-color: #3d3d3d; color: #ffffff; border: none; "
                "border-radius: 4px; padding: 4px 12px; font-size: 12px; }"
                "QPushButton:hover { background-color: #4a4a4a; }"
            )

            btn_delete = QPushButton("Delete")
            btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_delete.setProperty("account_id", acct["id"])
            btn_delete.clicked.connect(self._on_delete_account)
            btn_delete.setStyleSheet(
                "QPushButton { background-color: #f44336; color: #ffffff; border: none; "
                "border-radius: 4px; padding: 4px 12px; font-size: 12px; }"
                "QPushButton:hover { background-color: #ff5252; }"
            )

            actions_layout.addWidget(btn_edit)
            actions_layout.addWidget(btn_delete)
            actions_layout.addStretch()

            self.table.setCellWidget(row, 4, actions_widget)

        self.table.resizeColumnsToContents()

    def _show_empty_state(self) -> None:
        """Display empty state when no accounts exist."""
        self.table.setRowCount(0)
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels([""])
        item = QTableWidgetItem(
            "No railway accounts configured. Click 'Add Profile' to get started."
        )
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(Qt.GlobalColor.gray)
        self.table.setRowCount(1)
        self.table.setColumnCount(1)
        self.table.setItem(0, 0, item)

    def _on_add_account(self) -> None:
        """Handle add account button click."""
        if not self._vault.is_configured() or not self._vault.is_unlocked():
            QMessageBox.warning(
                self,
                "Vault Required",
                "The master vault must be unlocked before adding accounts.\n"
                "Please unlock the vault in Settings.",
            )
            return

        dialog = AccountDialog(
            parent=self,
            vault_unlocked=True,
        )
        dialog.account_saved.connect(self._handle_account_saved)
        dialog.exec()

    def _on_edit_account(self) -> None:
        """Handle edit account button click."""
        button = self.sender()
        if not button:
            return
        account_id = button.property("account_id")
        if not account_id:
            return

        try:
            account = self._service.get_account(account_id)
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Failed to load account: {exc}"
            )
            return

        dialog = AccountDialog(
            parent=self,
            vault_unlocked=self._vault.is_unlocked(),
            account=account,
        )
        dialog.account_saved.connect(
            lambda data: self._handle_account_saved(data, account_id=account_id)
        )
        dialog.exec()

    def _on_delete_account(self) -> None:
        """Handle delete account button click."""
        button = self.sender()
        if not button:
            return
        account_id = button.property("account_id")
        if not account_id:
            return

        try:
            account = self._service.get_account(account_id)
        except Exception:
            QMessageBox.critical(
                self, "Error", "Account not found."
            )
            return

        reply = QMessageBox.question(
            self,
            "Delete Account",
            f"Are you sure you want to delete the account '{account['username']}'?\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service.delete_account(account_id)
            self._refresh_accounts()
            self.accounts_changed.emit()
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Failed to delete account: {exc}"
            )

    def _handle_account_saved(
        self, data: dict, account_id: Optional[str] = None
    ) -> None:
        """Handle account data saved from dialog.

        Args:
            data: Account form data from dialog.
            account_id: Existing account ID for edit mode, or None for add mode.
        """
        try:
            if account_id:
                # Edit mode
                self._service.update_account(
                    account_id=account_id,
                    username=data.get("username"),
                    password=data.get("password") or None,
                    mobile=data.get("mobile"),
                    email=data.get("email"),
                    is_active=bool(data.get("is_active")),
                )
            else:
                # Add mode
                self._service.add_account(
                    username=data.get("username", ""),
                    password=data.get("password", ""),
                    mobile=data.get("mobile"),
                    email=data.get("email"),
                    is_active=bool(data.get("is_active")),
                )
            self._refresh_accounts()
            self.accounts_changed.emit()
        except DuplicateUsernameError as exc:
            QMessageBox.warning(self, "Duplicate Username", str(exc))
        except VaultRequiredError as exc:
            QMessageBox.warning(self, "Vault Required", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to save account: {exc}")

    def _update_vault_state(self) -> None:
        """Update UI based on current vault state."""
        self._update_vault_status_label()
        self._update_add_button_state()
        self._refresh_accounts()
