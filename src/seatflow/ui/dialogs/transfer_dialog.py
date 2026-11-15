"""Dialog for data backup export and restore (.bingo files).

Provides a two-tab interface matching the original desktop application:
1. Export: Password-protected export of tickets, accounts, proxies, and history.
2. Import: Preview and restore from .bingo archive with Merge or Replace mode.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from seatflow.services.transfer_service import (
    BackupDecryptionError,
    InvalidBackupFormatError,
    InvalidExportPasswordError,
    MIN_EXPORT_PASSWORD_LEN,
    TransferService,
    TransferServiceError,
)


class TransferDialog(QDialog):
    """Modal dialog for exporting and importing application data backups."""

    backup_exported = Signal(str)
    backup_imported = Signal(str)

    def __init__(
        self,
        transfer_service: TransferService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._service = transfer_service
        self._preview_data: Optional[dict[str, Any]] = None

        self.setWindowTitle("Export / Import Data")
        self.setMinimumSize(560, 520)
        self.setModal(True)

        self._setup_ui()
        self._setup_styles()
        self._refresh_export_counts()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("Data Backup & Restore")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #ffffff; background: transparent;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #b0b0b0; border: none; font-size: 16px; }"
            "QPushButton:hover { color: #ffffff; background: #3d3d3d; border-radius: 15px; }"
        )
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)
        main_layout.addLayout(header_layout)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #3d3d3d; background: #252525; border-radius: 6px; }"
            "QTabBar::tab { background: #1f1f1f; color: #b0b0b0; padding: 8px 24px; font-weight: bold; border-top-left-radius: 4px; border-top-right-radius: 4px; }"
            "QTabBar::tab:selected { background: #252525; color: #42a5f5; border-bottom: 2px solid #42a5f5; }"
        )

        # Tab 1: Export
        self.export_tab = QWidget()
        self._setup_export_tab(self.export_tab)
        self.tabs.addTab(self.export_tab, "Export Backup")

        # Tab 2: Import
        self.import_tab = QWidget()
        self._setup_import_tab(self.import_tab)
        self.tabs.addTab(self.import_tab, "Import Backup")

        main_layout.addWidget(self.tabs)

    def _setup_export_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        desc = QLabel(
            "Export all tickets, IRCTC accounts, proxies, and booking history "
            "into an encrypted .bingo archive file."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #cccccc; font-size: 12px;")
        layout.addWidget(desc)

        # Counts group
        counts_group = QGroupBox("Available Records")
        counts_group.setStyleSheet(
            "QGroupBox { color: #ffffff; font-weight: bold; border: 1px solid #3d3d3d; "
            "border-radius: 6px; margin-top: 8px; padding-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; }"
        )
        counts_layout = QHBoxLayout(counts_group)
        self.lbl_tickets_count = QLabel("Tickets: 0")
        self.lbl_accounts_count = QLabel("Accounts: 0")
        self.lbl_proxies_count = QLabel("Proxies: 0")
        self.lbl_history_count = QLabel("History: 0")
        for lbl in (self.lbl_tickets_count, self.lbl_accounts_count, self.lbl_proxies_count, self.lbl_history_count):
            lbl.setStyleSheet("color: #42a5f5; font-size: 13px; font-weight: bold;")
            counts_layout.addWidget(lbl)
        layout.addWidget(counts_group)

        # Password inputs
        pw_label = QLabel(f"Encryption Password (min {MIN_EXPORT_PASSWORD_LEN} characters):")
        pw_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        layout.addWidget(pw_label)

        self.export_password_input = QLineEdit()
        self.export_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.export_password_input.setPlaceholderText("Enter a strong backup password")
        self.export_password_input.setStyleSheet(
            "QLineEdit { background: #333333; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 8px; font-size: 13px; }"
        )
        layout.addWidget(self.export_password_input)

        confirm_label = QLabel("Confirm Password:")
        confirm_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        layout.addWidget(confirm_label)

        self.export_confirm_input = QLineEdit()
        self.export_confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.export_confirm_input.setPlaceholderText("Re-type password")
        self.export_confirm_input.setStyleSheet(
            "QLineEdit { background: #333333; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 8px; font-size: 13px; }"
        )
        layout.addWidget(self.export_confirm_input)

        layout.addStretch()

        # Action button
        self.btn_export = QPushButton("Export Backup (.bingo)")
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.setStyleSheet(
            "QPushButton { background: #42a5f5; color: #ffffff; border: none; "
            "border-radius: 4px; padding: 10px 18px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background: #54b3f6; }"
        )
        self.btn_export.clicked.connect(self._on_export_clicked)
        layout.addWidget(self.btn_export)

    def _setup_import_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # File picker row
        file_label = QLabel("Select Backup File (.bingo):")
        file_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        layout.addWidget(file_label)

        file_row = QHBoxLayout()
        self.import_file_input = QLineEdit()
        self.import_file_input.setPlaceholderText("Path to .bingo file...")
        self.import_file_input.setStyleSheet(
            "QLineEdit { background: #333333; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 8px; font-size: 12px; }"
        )
        file_row.addWidget(self.import_file_input)

        btn_browse = QPushButton("Browse")
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.setStyleSheet(
            "QPushButton { background: #3d3d3d; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 8px 14px; font-size: 12px; }"
            "QPushButton:hover { background: #4a4a4a; }"
        )
        btn_browse.clicked.connect(self._on_browse_file)
        file_row.addWidget(btn_browse)
        layout.addLayout(file_row)

        # Password row
        pw_label = QLabel("Backup Password:")
        pw_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        layout.addWidget(pw_label)

        self.import_password_input = QLineEdit()
        self.import_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.import_password_input.setPlaceholderText("Enter the password used to create the backup")
        self.import_password_input.setStyleSheet(
            "QLineEdit { background: #333333; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 8px; font-size: 13px; }"
        )
        layout.addWidget(self.import_password_input)

        # Mode dropdown
        mode_label = QLabel("Import Mode:")
        mode_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Merge - add new, keep existing", "merge")
        self.mode_combo.addItem("Replace all - wipe, then import", "replace")
        self.mode_combo.setStyleSheet(
            "QComboBox { background: #333333; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 6px; font-size: 12px; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView { background: #2b2b2b; color: #ffffff; selection-background-color: #42a5f5; }"
        )
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        # Warning banner for replace mode
        self.warning_banner = QFrame()
        self.warning_banner.setStyleSheet(
            "QFrame { background: #4a2800; border: 1px solid #ff9800; border-radius: 4px; padding: 8px; }"
        )
        warning_layout = QHBoxLayout(self.warning_banner)
        warning_layout.setContentsMargins(8, 4, 8, 4)
        warn_lbl = QLabel(
            "⚠️ Replace all deletes existing tickets, accounts, and proxies before importing. "
            "This cannot be undone."
        )
        warn_lbl.setStyleSheet("color: #ffb74d; font-size: 11px;")
        warn_lbl.setWordWrap(True)
        warning_layout.addWidget(warn_lbl)
        self.warning_banner.setVisible(False)
        layout.addWidget(self.warning_banner)

        # Preview box
        self.preview_frame = QFrame()
        self.preview_frame.setStyleSheet(
            "QFrame { background: #1e3320; border: 1px solid #4caf50; border-radius: 4px; padding: 8px; }"
        )
        preview_layout = QVBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(8, 6, 8, 6)
        preview_layout.setSpacing(4)
        self.lbl_preview_status = QLabel("✔ File unlocked")
        self.lbl_preview_status.setStyleSheet("color: #81c784; font-weight: bold; font-size: 12px;")
        self.lbl_preview_details = QLabel("")
        self.lbl_preview_details.setStyleSheet("color: #ffffff; font-size: 11px;")
        preview_layout.addWidget(self.lbl_preview_status)
        preview_layout.addWidget(self.lbl_preview_details)
        self.preview_frame.setVisible(False)
        layout.addWidget(self.preview_frame)

        layout.addStretch()

        # Action buttons
        btn_row = QHBoxLayout()
        self.btn_unlock = QPushButton("Unlock & Preview")
        self.btn_unlock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_unlock.setStyleSheet(
            "QPushButton { background: #3d3d3d; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 8px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #4a4a4a; }"
        )
        self.btn_unlock.clicked.connect(self._on_unlock_clicked)
        btn_row.addWidget(self.btn_unlock)

        self.btn_import = QPushButton("Import Data")
        self.btn_import.setEnabled(False)
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.setStyleSheet(
            "QPushButton { background: #4caf50; color: #ffffff; border: none; "
            "border-radius: 4px; padding: 8px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #66bb6a; }"
            "QPushButton:disabled { background: #2e4730; color: #888888; }"
        )
        self.btn_import.clicked.connect(self._on_import_clicked)
        btn_row.addWidget(self.btn_import)
        layout.addLayout(btn_row)

    def _setup_styles(self) -> None:
        self.setStyleSheet(
            "QDialog { background-color: #1e1e1e; }"
            "QLabel { background: transparent; }"
        )

    def _refresh_export_counts(self) -> None:
        try:
            counts = self._service.export_counts()
            self.lbl_tickets_count.setText(f"Tickets: {counts.get('tickets', 0)}")
            self.lbl_accounts_count.setText(f"Accounts: {counts.get('irctc_accounts', 0)}")
            self.lbl_proxies_count.setText(f"Proxies: {counts.get('proxies', 0)}")
            self.lbl_history_count.setText(f"History: {counts.get('history', 0)}")
        except Exception:
            pass

    def _on_export_clicked(self) -> None:
        password = self.export_password_input.text()
        confirm = self.export_confirm_input.text()

        if len(password) < MIN_EXPORT_PASSWORD_LEN:
            QMessageBox.warning(
                self,
                "Password Too Short",
                f"Password must be at least {MIN_EXPORT_PASSWORD_LEN} characters.",
            )
            return

        if password != confirm:
            QMessageBox.warning(
                self,
                "Password Mismatch",
                "Passwords do not match. Please re-enter.",
            )
            return

        default_filename = f"bingo_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bingo"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Backup Archive",
            default_filename,
            "SeatFlow Backup Files (*.bingo)",
        )
        if not file_path:
            return

        if not file_path.endswith(".bingo"):
            file_path += ".bingo"

        try:
            res = self._service.export_data(file_path, password)
            self.backup_exported.emit(file_path)
            counts = res.get("counts", {})
            QMessageBox.information(
                self,
                "Export Complete",
                f"Backup successfully saved to:\n{file_path}\n\n"
                f"Exported:\n"
                f"• Tickets: {counts.get('tickets', 0)}\n"
                f"• Accounts: {counts.get('irctc_accounts', 0)}\n"
                f"• Proxies: {counts.get('proxies', 0)}\n"
                f"• History: {counts.get('history', 0)}",
            )
            self.export_password_input.clear()
            self.export_confirm_input.clear()
        except InvalidExportPasswordError as exc:
            QMessageBox.warning(self, "Invalid Password", str(exc))
        except TransferServiceError as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    def _on_browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Backup File",
            "",
            "SeatFlow Backup Files (*.bingo);;All Files (*)",
        )
        if file_path:
            self.import_file_input.setText(file_path)
            self.preview_frame.setVisible(False)
            self.btn_import.setEnabled(False)
            self._preview_data = None

    def _on_mode_changed(self) -> None:
        mode = self.mode_combo.currentData()
        self.warning_banner.setVisible(mode == "replace")

    def _on_unlock_clicked(self) -> None:
        file_path = self.import_file_input.text().strip()
        password = self.import_password_input.text()

        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "File Not Found", "Please choose a valid .bingo file.")
            return

        if not password:
            QMessageBox.warning(self, "Password Required", "Please enter the backup decryption password.")
            return

        try:
            preview = self._service.import_preview(file_path, password)
            self._preview_data = preview
            counts = preview.get("counts", {})
            exported_at = preview.get("exported_at", "Unknown")

            details_text = (
                f"Created: {exported_at}\n"
                f"Contains: {counts.get('tickets', 0)} tickets, "
                f"{counts.get('irctc_accounts', 0)} accounts, "
                f"{counts.get('proxies', 0)} proxies, "
                f"{counts.get('history', 0)} history records."
            )
            self.lbl_preview_details.setText(details_text)
            self.preview_frame.setVisible(True)
            self.btn_import.setEnabled(True)
        except BackupDecryptionError:
            self.preview_frame.setVisible(False)
            self.btn_import.setEnabled(False)
            QMessageBox.warning(
                self,
                "Decryption Failed",
                "Incorrect password or corrupted backup file.",
            )
        except InvalidBackupFormatError as exc:
            self.preview_frame.setVisible(False)
            self.btn_import.setEnabled(False)
            QMessageBox.warning(self, "Invalid Backup", str(exc))
        except Exception as exc:
            self.preview_frame.setVisible(False)
            self.btn_import.setEnabled(False)
            QMessageBox.critical(self, "Error", f"Failed to preview backup: {exc}")

    def _on_import_clicked(self) -> None:
        file_path = self.import_file_input.text().strip()
        password = self.import_password_input.text()
        mode = self.mode_combo.currentData() or "merge"

        if mode == "replace":
            confirm = QMessageBox.question(
                self,
                "Confirm Replace",
                "Are you sure you want to REPLACE ALL current records?\n"
                "Existing tickets, accounts, and proxies will be deleted.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        try:
            res = self._service.import_data(file_path, password, mode=mode)
            counts = res.get("imported_counts", {})
            self.backup_imported.emit(mode)
            QMessageBox.information(
                self,
                "Import Complete",
                f"Successfully restored data in '{mode}' mode:\n\n"
                f"• Tickets imported: {counts.get('tickets', 0)}\n"
                f"• Accounts imported: {counts.get('irctc_accounts', 0)}\n"
                f"• Proxies imported: {counts.get('proxies', 0)}\n"
                f"• History records: {counts.get('history', 0)}",
            )
            self._refresh_export_counts()
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", f"Failed to restore data: {exc}")
