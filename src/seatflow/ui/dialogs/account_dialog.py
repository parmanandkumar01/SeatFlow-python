"""Account dialog for adding and editing railway account profiles.

Collects only fields supported by the approved database schema:
- username (required)
- password (required, encrypted via vault)
- mobile (optional)
- email (optional)
- is_active (boolean)

Never displays stored passwords in plaintext.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)


class AccountDialog(QDialog):
    """Dialog for adding or editing a railway account profile.

    Parameters
    ----------
    parent : QWidget | None
        Parent widget.
    vault_unlocked : bool
        Whether the master vault is currently unlocked.
    account : dict | None
        Existing account data for edit mode. If None, dialog is in add mode.
    """

    #: Emitted when account data is saved successfully with the account dict.
    account_saved = Signal(dict)

    def __init__(
        self,
        parent: QWidget | None = None,
        vault_unlocked: bool = False,
        account: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self._vault_unlocked = vault_unlocked
        self._is_edit = account is not None
        self._account_id = account.get("id") if account else None
        self._setup_ui()
        if self._is_edit and account:
            self._load_account(account)

    def _setup_ui(self) -> None:
        """Initialize the dialog layout and widgets."""
        title = "Edit Railway Account" if self._is_edit else "Add Railway Account"
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Form
        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Enter railway account username")
        self.username_edit.setMaxLength(100)
        form.addRow("Username*:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Enter account password")
        self.password_edit.setMaxLength(100)
        form.addRow("Password*:", self.password_edit)

        self.mobile_edit = QLineEdit()
        self.mobile_edit.setPlaceholderText("Optional mobile number")
        self.mobile_edit.setMaxLength(20)
        form.addRow("Mobile:", self.mobile_edit)

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Optional email address")
        self.email_edit.setMaxLength(100)
        form.addRow("Email:", self.email_edit)

        self.active_check = QCheckBox("Account is active")
        self.active_check.setChecked(True)
        form.addRow("", self.active_check)

        layout.addLayout(form)

        # Vault status notice
        if not self._vault_unlocked:
            notice = QLabel(
                "Vault is locked. Password will be encrypted once vault is unlocked."
            )
            notice.setStyleSheet("color: #ff9800; font-size: 12px;")
            notice.setWordWrap(True)
            layout.addWidget(notice)

        # Buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.save_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Save
        )
        self.save_button.setText("Save" if not self._is_edit else "Update")
        self.save_button.setEnabled(self._vault_unlocked)
        self.button_box.accepted.connect(self._on_save)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        # Set vault unlocked state on fields
        self._update_field_states()

    def _load_account(self, account: dict) -> None:
        """Load existing account data into the form.

        Args:
            account: Account dictionary from repository.
        """
        self.username_edit.setText(account.get("username", ""))
        self.mobile_edit.setText(account.get("mobile") or "")
        self.email_edit.setText(account.get("email") or "")
        self.active_check.setChecked(bool(account.get("is_active", 1)))
        # Password field is intentionally left empty for security

    def _update_field_states(self) -> None:
        """Enable/disable fields based on vault state."""
        self.password_edit.setEnabled(self._vault_unlocked)
        if not self._vault_unlocked:
            self.password_edit.setPlaceholderText(
                "Unlock vault to set password"
            )

    def set_vault_unlocked(self, unlocked: bool) -> None:
        """Update the vault unlocked state.

        Args:
            unlocked: Whether the vault is currently unlocked.
        """
        self._vault_unlocked = unlocked
        self.save_button.setEnabled(unlocked)
        self._update_field_states()

    def _validate(self) -> str | None:
        """Validate form input.

        Returns:
            Error message string if validation fails, None if valid.
        """
        username = self.username_edit.text().strip()
        if not username:
            return "Username is required."

        password = self.password_edit.text()
        if self._vault_unlocked and not password:
            return "Password is required."

        if not self._is_edit and not self._vault_unlocked:
            return "Vault must be unlocked to add an account."

        return None

    def _on_save(self) -> None:
        """Handle save button click."""
        error = self._validate()
        if error:
            QMessageBox.warning(self, "Validation Error", error)
            return

        data = {
            "username": self.username_edit.text().strip(),
            "mobile": self.mobile_edit.text().strip() or None,
            "email": self.email_edit.text().strip() or None,
            "is_active": 1 if self.active_check.isChecked() else 0,
        }

        # Only include password if vault is unlocked and a password was provided
        if self._vault_unlocked:
            password = self.password_edit.text()
            if password:
                data["password"] = password

        self.account_saved.emit(data)
        self.accept()

    def get_account_data(self) -> dict:
        """Return the form data as a dictionary.

        Returns:
            Dictionary with account field values.
        """
        return {
            "username": self.username_edit.text().strip(),
            "password": self.password_edit.text(),
            "mobile": self.mobile_edit.text().strip() or None,
            "email": self.email_edit.text().strip() or None,
            "is_active": 1 if self.active_check.isChecked() else 0,
        }
