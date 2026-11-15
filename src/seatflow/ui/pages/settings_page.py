"""Settings page.

Application preferences for the SeatFlow train ticket booking
application. Integrates with the SettingsService for persistent
storage of user preferences.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seatflow.services import (
    InvalidSettingError,
    SETTING_AUTO_LOCK_MINUTES,
    SETTING_REMEMBER_PREFERENCES,
    SETTING_THEME,
    SettingsService,
    TransferService,
)
from seatflow.ui.dialogs.transfer_dialog import TransferDialog


class SettingsPage(QWidget):
    """Application settings page.

    Provides preference management for the railway booking
    application. Integrates with SettingsService for persistent
    storage of user preferences.

    Supported settings:
    - Theme (dark/light/system)
    - Auto-lock vault timeout (minutes)
    - Remember preferences (boolean)
    """

    #: Emitted when settings are changed.
    settings_changed = Signal()

    def __init__(
        self,
        settings_service: SettingsService,
        transfer_service: TransferService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = settings_service
        self._transfer_service = transfer_service
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        """Initialize the settings page layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Page header
        title = QLabel("Settings")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #ffffff; background-color: transparent; border: none;")
        layout.addWidget(title)

        # Appearance group
        appearance_group = QGroupBox("Appearance")
        appearance_group.setStyleSheet(
            "QGroupBox { color: #ffffff; font-size: 14px; font-weight: bold; "
            "border: 1px solid #3d3d3d; border-radius: 6px; margin-top: 12px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        appearance_layout = QFormLayout(appearance_group)
        appearance_layout.setSpacing(12)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light", "System"])
        self.theme_combo.setCurrentText("Dark")
        self.theme_combo.setStyleSheet(
            "QComboBox { background-color: #3d3d3d; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 6px 10px; min-width: 150px; }"
            "QComboBox::drop-down { border: none; }"
        )
        appearance_layout.addRow("Theme:", self.theme_combo)

        layout.addWidget(appearance_group)

        # Security group
        security_group = QGroupBox("Security")
        security_group.setStyleSheet(
            "QGroupBox { color: #ffffff; font-size: 14px; font-weight: bold; "
            "border: 1px solid #3d3d3d; border-radius: 6px; margin-top: 12px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        security_layout = QFormLayout(security_group)

        self.auto_lock_spin = QSpinBox()
        self.auto_lock_spin.setRange(0, 120)
        self.auto_lock_spin.setValue(0)
        self.auto_lock_spin.setSuffix(" minutes")
        self.auto_lock_spin.setStyleSheet(
            "QSpinBox { background-color: #3d3d3d; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 6px 10px; min-width: 150px; }"
        )
        security_layout.addRow("Auto-lock vault after:", self.auto_lock_spin)

        self.remember_checkbox = QCheckBox("Remember application preferences")
        self.remember_checkbox.setStyleSheet("QCheckBox { color: #ffffff; }")
        security_layout.addRow("", self.remember_checkbox)

        layout.addWidget(security_group)

        # Local storage group
        storage_group = QGroupBox("Local Storage")
        storage_group.setStyleSheet(
            "QGroupBox { color: #ffffff; font-size: 14px; font-weight: bold; "
            "border: 1px solid #3d3d3d; border-radius: 6px; margin-top: 12px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        storage_layout = QHBoxLayout(storage_group)

        self.storage_label = QLabel("~/.local/share/SeatFlow/")
        self.storage_label.setStyleSheet("color: #b0b0b0; font-size: 12px; background-color: transparent; border: none;")
        storage_layout.addWidget(self.storage_label)
        storage_layout.addStretch()

        self.btn_browse = QPushButton("Browse")
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.setStyleSheet(
            "QPushButton { background-color: #3d3d3d; color: #ffffff; border: none; "
            "border-radius: 4px; padding: 6px 14px; font-size: 12px; }"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        self.btn_browse.setEnabled(False)  # Read-only; relocation not implemented
        storage_layout.addWidget(self.btn_browse)

        layout.addWidget(storage_group)

        # Backup & Restore group
        if self._transfer_service is not None:
            backup_group = QGroupBox("Data Backup & Restore (.bingo)")
            backup_group.setStyleSheet(
                "QGroupBox { color: #ffffff; font-size: 14px; font-weight: bold; "
                "border: 1px solid #3d3d3d; border-radius: 6px; margin-top: 12px; padding-top: 8px; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
            )
            backup_layout = QHBoxLayout(backup_group)

            backup_desc = QLabel(
                "Export or import all accounts, tickets, proxies, and history via encrypted .bingo archives."
            )
            backup_desc.setStyleSheet("color: #b0b0b0; font-size: 12px; background-color: transparent; border: none;")
            backup_layout.addWidget(backup_desc)
            backup_layout.addStretch()

            self.btn_open_transfer = QPushButton("Export / Import...")
            self.btn_open_transfer.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_open_transfer.setStyleSheet(
                "QPushButton { background-color: #42a5f5; color: #ffffff; border: none; "
                "border-radius: 4px; padding: 6px 14px; font-size: 12px; font-weight: bold; }"
                "QPushButton:hover { background-color: #54b3f6; }"
            )
            self.btn_open_transfer.clicked.connect(self._on_open_transfer_dialog)
            backup_layout.addWidget(self.btn_open_transfer)

            layout.addWidget(backup_group)

        # Action buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)

        self.btn_reset = QPushButton("Reset to Defaults")
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.setStyleSheet(
            "QPushButton { background-color: #f44336; color: #ffffff; border: none; "
            "border-radius: 6px; padding: 10px 24px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #ff5252; }"
        )
        self.btn_reset.clicked.connect(self._on_reset)
        buttons_layout.addWidget(self.btn_reset)

        buttons_layout.addStretch()

        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #42a5f5; color: #ffffff; border: none; "
            "border-radius: 6px; padding: 10px 24px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #54b3f6; }"
        )
        self.btn_save.clicked.connect(self._on_save)
        buttons_layout.addWidget(self.btn_save)

        layout.addLayout(buttons_layout)
        layout.addStretch()

    def _load_settings(self) -> None:
        """Load settings from the service into UI controls."""
        # Theme
        theme = self._service.get_theme()
        index = self.theme_combo.findText(theme.capitalize())
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)

        # Auto-lock
        minutes = self._service.get_auto_lock_minutes()
        self.auto_lock_spin.setValue(minutes)

        # Remember preferences
        remember = self._service.get_remember_preferences()
        self.remember_checkbox.setChecked(remember)

    def _collect_settings(self) -> dict[str, str]:
        """Collect current UI control values into a settings dictionary.

        Returns:
            Dictionary mapping setting keys to string values.
        """
        theme_text = self.theme_combo.currentText().lower()
        minutes = str(self.auto_lock_spin.value())
        remember = "true" if self.remember_checkbox.isChecked() else "false"

        return {
            SETTING_THEME: theme_text,
            SETTING_AUTO_LOCK_MINUTES: minutes,
            SETTING_REMEMBER_PREFERENCES: remember,
        }

    def _on_save(self) -> None:
        """Handle save button click."""
        settings = self._collect_settings()
        errors: list[str] = []

        for key, value in settings.items():
            try:
                self._service.set_setting(key, value)
            except InvalidSettingError as exc:
                errors.append(str(exc))
            except Exception as exc:  # pylint: disable=broad-except
                errors.append(f"Failed to save {key}: {exc}")

        if errors:
            QMessageBox.warning(
                self,
                "Save Failed",
                "Some settings could not be saved:\n" + "\n".join(errors),
            )
            return

        self.settings_changed.emit()
        QMessageBox.information(
            self,
            "Settings Saved",
            "Your settings have been saved successfully.",
        )

    def _on_reset(self) -> None:
        """Handle reset button click with confirmation."""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Are you sure you want to reset all settings to defaults?\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service.reset_settings()
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(
                self,
                "Reset Failed",
                f"Failed to reset settings: {exc}",
            )
            return

        self._load_settings()
        self.settings_changed.emit()
        QMessageBox.information(
            self,
            "Settings Reset",
            "Settings have been reset to defaults.",
        )

    def _on_open_transfer_dialog(self) -> None:
        """Open the data export/import modal dialog."""
        if self._transfer_service is None:
            return
        dialog = TransferDialog(self._transfer_service, parent=self)
        dialog.exec()
