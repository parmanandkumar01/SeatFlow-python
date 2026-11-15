"""Proxy Management Page.

Provides table-based management of HTTP, HTTPS, and SOCKS5 proxies:
- List proxies with active status, protocol, and test results
- Add new proxies with vault-backed credential encryption
- Edit existing proxies
- Toggle active proxy (single active proxy constraint)
- Connectivity and latency testing
- Delete proxies with confirmation
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seatflow.security.vault import VaultService
from seatflow.services.proxy_service import ProxyService, ProxyServiceError
from seatflow.ui.dialogs.proxy_dialog import ProxyDialog


class ProxiesPage(QWidget):
    """Page for configuring and monitoring network proxies."""

    def __init__(
        self,
        service: ProxyService,
        vault: VaultService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._vault = vault
        self._proxies: list[dict[str, Any]] = []

        self._setup_ui()
        self._service.proxies_changed.connect(self._refresh_proxies)
        self._refresh_proxies()

    def _setup_ui(self) -> None:
        """Initialize the page layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header bar
        header_layout = QHBoxLayout()
        title = QLabel("Proxy Configuration")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #ffffff; background-color: transparent;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self._vault_status_label = QLabel()
        self._vault_status_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        self._update_vault_status()
        header_layout.addWidget(self._vault_status_label)

        btn_add = QPushButton("Add Proxy")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #42a5f5;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #54b3f6; }
        """)
        btn_add.clicked.connect(self._on_add_proxy)
        header_layout.addWidget(btn_add)

        layout.addLayout(header_layout)

        # Proxy table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Host", "Port", "Protocol", "Username", "Status", "Latency", "Last Tested"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                color: #dcdcdc;
                gridline-color: #333333;
                border: 1px solid #333333;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: #b0b0b0;
                padding: 8px;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid #444444;
            }
            QTableWidget::item:selected {
                background-color: #2c4a6b;
                color: #ffffff;
            }
        """)
        self.table.itemSelectionChanged.connect(self._update_button_states)
        layout.addWidget(self.table)

        # Bottom action bar
        actions_layout = QHBoxLayout()

        self.btn_set_active = QPushButton("Toggle Active")
        self.btn_set_active.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #388e3c; }
            QPushButton:disabled { background-color: #333333; color: #666666; }
        """)
        self.btn_set_active.clicked.connect(self._on_toggle_active)
        actions_layout.addWidget(self.btn_set_active)

        self.btn_test = QPushButton("Test Connection")
        self.btn_test.setStyleSheet("""
            QPushButton {
                background-color: #f57c00;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #fb8c00; }
            QPushButton:disabled { background-color: #333333; color: #666666; }
        """)
        self.btn_test.clicked.connect(self._on_test_connection)
        actions_layout.addWidget(self.btn_test)

        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setStyleSheet("""
            QPushButton {
                background-color: #424242;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #505050; }
            QPushButton:disabled { background-color: #333333; color: #666666; }
        """)
        self.btn_edit.clicked.connect(self._on_edit_proxy)
        actions_layout.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #c62828;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #d32f2f; }
            QPushButton:disabled { background-color: #333333; color: #666666; }
        """)
        self.btn_delete.clicked.connect(self._on_delete_proxy)
        actions_layout.addWidget(self.btn_delete)

        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        self._update_button_states()

    def _update_vault_status(self) -> None:
        """Update vault status indicator text and color."""
        if not self._vault.is_configured():
            self._vault_status_label.setText("Vault: Not Configured")
            self._vault_status_label.setStyleSheet("color: #ffa726; font-size: 12px; font-weight: bold;")
        elif self._vault.is_unlocked():
            self._vault_status_label.setText("Vault: Unlocked")
            self._vault_status_label.setStyleSheet("color: #66bb6a; font-size: 12px; font-weight: bold;")
        else:
            self._vault_status_label.setText("Vault: Locked")
            self._vault_status_label.setStyleSheet("color: #ef5350; font-size: 12px; font-weight: bold;")

    def _refresh_proxies(self) -> None:
        """Reload proxy list from service and repopulate table."""
        self._update_vault_status()
        self._proxies = self._service.list_proxies()
        self.table.setRowCount(len(self._proxies))

        for row, p in enumerate(self._proxies):
            # Host
            item_host = QTableWidgetItem(p.get("host", ""))
            self.table.setItem(row, 0, item_host)

            # Port
            item_port = QTableWidgetItem(str(p.get("port", "")))
            item_port.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, item_port)

            # Protocol
            item_proto = QTableWidgetItem(str(p.get("type", "http")).upper())
            item_proto.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, item_proto)

            # Username
            user_text = p.get("username") or "—"
            item_user = QTableWidgetItem(user_text)
            self.table.setItem(row, 3, item_user)

            # Status
            is_active = bool(p.get("is_active", 0))
            status_text = "ACTIVE" if is_active else "Inactive"
            item_status = QTableWidgetItem(status_text)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_active:
                item_status.setForeground(QColor("#66bb6a"))
                font = item_status.font()
                font.setBold(True)
                item_status.setFont(font)
            else:
                item_status.setForeground(QColor("#888888"))
            self.table.setItem(row, 4, item_status)

            # Latency
            lat = p.get("test_latency_ms")
            lat_text = f"{lat} ms" if lat is not None else "—"
            item_lat = QTableWidgetItem(lat_text)
            item_lat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if lat is not None:
                item_lat.setForeground(QColor("#42a5f5") if lat < 300 else QColor("#ffa726"))
            self.table.setItem(row, 5, item_lat)

            # Last Tested
            tested_text = p.get("last_tested")
            if tested_text and "T" in tested_text:
                tested_text = tested_text.split("T")[0] + " " + tested_text.split("T")[1][:5]
            item_tested = QTableWidgetItem(tested_text or "Never")
            item_tested.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 6, item_tested)

        self._update_button_states()

    def _selected_proxy(self) -> Optional[dict[str, Any]]:
        """Return the dict of the currently selected proxy row, or None."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        if 0 <= row < len(self._proxies):
            return self._proxies[row]
        return None

    def _update_button_states(self) -> None:
        """Enable or disable contextual buttons based on selection."""
        has_sel = self._selected_proxy() is not None
        self.btn_set_active.setEnabled(has_sel)
        self.btn_test.setEnabled(has_sel)
        self.btn_edit.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)

    def _on_add_proxy(self) -> None:
        """Open dialog to add a new proxy."""
        dialog = ProxyDialog(
            parent=self,
            vault_unlocked=self._vault.is_unlocked(),
        )

        def handle_save(data: dict[str, Any]) -> None:
            try:
                self._service.add_proxy(
                    host=data["host"],
                    port=data["port"],
                    proxy_type=data["type"],
                    username=data.get("username"),
                    password=data.get("password"),
                    is_active=data.get("is_active", False),
                )
            except ProxyServiceError as exc:
                QMessageBox.critical(self, "Error", f"Failed to add proxy: {exc}")

        dialog.proxy_saved.connect(handle_save)
        dialog.exec()

    def _on_edit_proxy(self) -> None:
        """Open dialog to edit the selected proxy."""
        selected = self._selected_proxy()
        if not selected:
            return

        dialog = ProxyDialog(
            parent=self,
            vault_unlocked=self._vault.is_unlocked(),
            proxy=selected,
        )

        def handle_save(data: dict[str, Any]) -> None:
            try:
                self._service.update_proxy(
                    proxy_id=data["id"],
                    host=data["host"],
                    port=data["port"],
                    proxy_type=data["type"],
                    username=data.get("username"),
                    password=data.get("password"),
                    is_active=data.get("is_active"),
                )
            except ProxyServiceError as exc:
                QMessageBox.critical(self, "Error", f"Failed to update proxy: {exc}")

        dialog.proxy_saved.connect(handle_save)
        dialog.exec()

    def _on_toggle_active(self) -> None:
        """Toggle active status of the selected proxy."""
        selected = self._selected_proxy()
        if not selected:
            return

        is_currently_active = bool(selected.get("is_active", 0))
        target_id = None if is_currently_active else selected["id"]
        try:
            self._service.set_active(target_id)
        except ProxyServiceError as exc:
            QMessageBox.critical(self, "Error", f"Failed to toggle proxy: {exc}")

    def _on_test_connection(self) -> None:
        """Test reachability of the selected proxy."""
        selected = self._selected_proxy()
        if not selected:
            return

        proxy_id = selected["id"]
        result = self._service.test_proxy(proxy_id, timeout=3.0)
        if result["success"]:
            QMessageBox.information(
                self,
                "Connection Successful",
                f"Successfully connected to {selected['host']}:{selected['port']}.\nLatency: {result['latency_ms']} ms",
            )
        else:
            QMessageBox.warning(
                self,
                "Connection Failed",
                f"Could not connect to {selected['host']}:{selected['port']}.\nDetails: {result['message']}",
            )

    def _on_delete_proxy(self) -> None:
        """Delete selected proxy after user confirmation."""
        selected = self._selected_proxy()
        if not selected:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to remove proxy {selected['host']}:{selected['port']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._service.delete_proxy(selected["id"])
            except ProxyServiceError as exc:
                QMessageBox.critical(self, "Error", f"Failed to delete proxy: {exc}")
