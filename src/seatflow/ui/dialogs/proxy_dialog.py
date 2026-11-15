"""Proxy dialog for adding and editing proxy configurations.

Collects proxy fields:
- host (required)
- port (required, 1-65535)
- type ('http', 'https', 'socks5')
- username (optional)
- password (optional, encrypted in vault)
- is_active (boolean)
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ProxyDialog(QDialog):
    """Dialog for creating or editing a proxy profile."""

    #: Emitted when proxy data is validated and accepted.
    proxy_saved = Signal(dict)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        vault_unlocked: bool = False,
        proxy: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialize the proxy dialog.

        Args:
            parent: Parent widget.
            vault_unlocked: Whether the master vault is unlocked.
            proxy: Existing proxy dict for edit mode, or None for add mode.
        """
        super().__init__(parent)
        self._vault_unlocked = vault_unlocked
        self._is_edit = proxy is not None
        self._proxy_id = proxy.get("id") if proxy else None
        self._setup_ui()
        if self._is_edit and proxy:
            self._load_proxy(proxy)

    def _setup_ui(self) -> None:
        """Initialize widgets and layout."""
        self.setWindowTitle("Edit Proxy" if self._is_edit else "Add Proxy")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet("""
            QDialog {
                background-color: #222222;
                color: #e0e0e0;
            }
            QLabel {
                color: #cccccc;
                font-size: 13px;
            }
            QLineEdit, QSpinBox, QComboBox {
                background-color: #2e2e2e;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border: 1px solid #42a5f5;
            }
            QCheckBox {
                color: #cccccc;
                font-size: 13px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("e.g. 192.168.1.100 or proxy.company.com")
        form.addRow("Host*:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8080)
        form.addRow("Port*:", self.port_spin)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["HTTP", "HTTPS", "SOCKS5"])
        form.addRow("Protocol*:", self.type_combo)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Optional proxy username")
        form.addRow("Username:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Optional proxy password")
        form.addRow("Password:", self.password_edit)

        self.active_check = QCheckBox("Set as active proxy")
        form.addRow("", self.active_check)

        layout.addLayout(form)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Save Proxy")
        layout.addWidget(button_box)

    def _load_proxy(self, proxy: dict[str, Any]) -> None:
        """Populate fields with existing proxy data."""
        self.host_edit.setText(proxy.get("host", ""))
        self.port_spin.setValue(int(proxy.get("port", 8080)))

        proto = proxy.get("type", "http").upper()
        idx = self.type_combo.findText(proto)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)

        self.username_edit.setText(proxy.get("username", "") or "")
        self.active_check.setChecked(bool(proxy.get("is_active", 0)))
        if self._is_edit:
            self.password_edit.setPlaceholderText("Leave empty to keep existing password")

    def _on_accept(self) -> None:
        """Validate input and emit proxy_saved."""
        host = self.host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, "Validation Error", "Host is required.")
            self.host_edit.setFocus()
            return

        port = self.port_spin.value()
        proxy_type = self.type_combo.currentText().lower()
        username = self.username_edit.text().strip() or None
        password_raw = self.password_edit.text()

        # If user entered a new password but vault is locked, warn them
        if password_raw and not self._vault_unlocked:
            QMessageBox.warning(
                self,
                "Vault Locked",
                "The master security vault must be unlocked to encrypt proxy credentials.\n"
                "Please unlock the vault first, or save without a password."
            )
            return

        data: dict[str, Any] = {
            "host": host,
            "port": port,
            "type": proxy_type,
            "username": username,
            "is_active": self.active_check.isChecked(),
        }

        if self._is_edit:
            data["id"] = self._proxy_id
            if password_raw:
                data["password"] = password_raw
        else:
            data["password"] = password_raw if password_raw else None

        self.proxy_saved.emit(data)
        self.accept()
