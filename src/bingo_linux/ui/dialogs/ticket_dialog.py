"""Ticket dialog for adding and editing ticket booking profiles.

Collects fields supported by the tickets table schema and UI enhancements:
- train_number (required, with autocomplete and train name lookup)
- train_name (auto-populated display)
- from_station (required, with station autocomplete and code extraction)
- to_station (required, with station autocomplete and code extraction)
- journey_date (required, YYYY-MM-DD)
- class (required)
- quota (required)
- passenger_details (required, JSON)
- mobile (optional)
- email (optional)
- irctc_account_id (optional, FK to railway account)
- proxy_id (optional, network proxy selection)
- travel options (auto_upgrade, book_only_if_cnf, insurance)
- status (optional, default: draft)

Never stores or displays real booking data or credentials.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from bingo_linux.services.master_data_service import MasterDataService


class TicketDialog(QDialog):
    """Dialog for adding or editing a ticket booking profile.

    Parameters
    ----------
    parent : QWidget | None
        Parent widget.
    accounts : list[dict] | None
        List of available railway accounts for account selection.
        Each dict must have 'id' and 'username' keys.
    ticket : dict | None
        Existing ticket data for edit mode. If None, dialog is in add mode.
    master_data_service : MasterDataService | None
        Service providing offline station and train autocomplete datasets.
    proxies : list[dict] | None
        List of configured network proxies.
    """

    #: Emitted when ticket data is saved successfully with the ticket dict.
    ticket_saved = Signal(dict)

    # Default values for dropdowns
    TRAIN_CLASSES = ["1A", "2A", "3A", "SL", "CC", "EC", "2S", "3E"]
    QUOTAS = ["General", "Tatkal", "Premium Tatkal", "Ladies", "Senior Citizen", "Divyangjan"]

    def __init__(
        self,
        parent: QWidget | None = None,
        accounts: list[dict] | None = None,
        ticket: dict | None = None,
        master_data_service: Optional[MasterDataService] = None,
        proxies: list[dict] | None = None,
    ) -> None:
        super().__init__(parent)
        self._accounts = accounts or []
        self._proxies = proxies or []
        self._master_data_service = master_data_service
        self._is_edit = ticket is not None
        self._ticket_id = ticket.get("id") if ticket else None
        self._setup_ui()
        if self._is_edit and ticket:
            self._load_ticket(ticket)

    def _setup_ui(self) -> None:
        """Initialize the dialog layout and widgets."""
        title = "Edit Ticket Profile" if self._is_edit else "Add Ticket Profile"
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(580)
        self.setStyleSheet("""
            QDialog {
                background-color: #222222;
                color: #e0e0e0;
            }
            QLabel {
                color: #cccccc;
                font-size: 13px;
            }
            QLineEdit, QDateEdit, QComboBox, QTextEdit {
                background-color: #2e2e2e;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QTextEdit:focus {
                border: 1px solid #42a5f5;
            }
            QCheckBox {
                color: #cccccc;
                font-size: 13px;
            }
            QGroupBox {
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 14px;
                color: #b0b0b0;
                font-size: 12px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Form layout
        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # 1. Train Number & Name
        train_hlayout = QHBoxLayout()
        train_hlayout.setSpacing(8)
        self.train_number_edit = QLineEdit()
        self.train_number_edit.setPlaceholderText("e.g., 12345 or search name...")
        self.train_number_edit.setMaxLength(60)
        self.train_number_edit.textChanged.connect(self._on_train_number_changed)
        train_hlayout.addWidget(self.train_number_edit, stretch=1)

        self.train_name_edit = QLineEdit()
        self.train_name_edit.setPlaceholderText("Train name auto-detected...")
        self.train_name_edit.setReadOnly(True)
        self.train_name_edit.setStyleSheet(
            "QLineEdit { background-color: #262626; color: #64b5f6; font-style: italic; border: 1px solid #383838; }"
        )
        train_hlayout.addWidget(self.train_name_edit, stretch=2)
        form.addRow("Train Number*:", train_hlayout)

        # 2. From Station + Hint
        from_container = QVBoxLayout()
        from_container.setSpacing(2)
        self.from_station_edit = QLineEdit()
        self.from_station_edit.setPlaceholderText("e.g., NDLS or search city...")
        self.from_station_edit.setMaxLength(60)
        self.from_station_edit.textChanged.connect(self._on_from_station_changed)
        self.from_station_hint = QLabel("")
        self.from_station_hint.setStyleSheet("color: #888888; font-size: 11px; font-style: italic;")
        from_container.addWidget(self.from_station_edit)
        from_container.addWidget(self.from_station_hint)
        form.addRow("From Station*:", from_container)

        # 3. To Station + Hint
        to_container = QVBoxLayout()
        to_container.setSpacing(2)
        self.to_station_edit = QLineEdit()
        self.to_station_edit.setPlaceholderText("e.g., HWH or search city...")
        self.to_station_edit.setMaxLength(60)
        self.to_station_edit.textChanged.connect(self._on_to_station_changed)
        self.to_station_hint = QLabel("")
        self.to_station_hint.setStyleSheet("color: #888888; font-size: 11px; font-style: italic;")
        to_container.addWidget(self.to_station_edit)
        to_container.addWidget(self.to_station_hint)
        form.addRow("To Station*:", to_container)

        # Setup QCompleters if master_data_service is provided
        self._setup_completers()

        # 4. Journey Date
        self.journey_date_edit = QDateEdit()
        self.journey_date_edit.setCalendarPopup(True)
        self.journey_date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Journey Date*:", self.journey_date_edit)

        # 5. Class & Quota in single row
        class_quota_layout = QHBoxLayout()
        class_quota_layout.setSpacing(8)
        self.class_combo = QComboBox()
        self.class_combo.addItems(self.TRAIN_CLASSES)
        self.class_combo.setEditable(True)
        class_quota_layout.addWidget(self.class_combo, stretch=1)

        quota_label = QLabel("Quota*:")
        quota_label.setStyleSheet("color: #cccccc; font-size: 13px; margin-left: 10px;")
        class_quota_layout.addWidget(quota_label)

        self.quota_combo = QComboBox()
        self.quota_combo.addItems(self.QUOTAS)
        self.quota_combo.setEditable(True)
        class_quota_layout.addWidget(self.quota_combo, stretch=1)
        form.addRow("Class*:", class_quota_layout)

        # 6. Passenger Details
        self.passenger_details_edit = QTextEdit()
        self.passenger_details_edit.setPlaceholderText(
            'e.g., [{"name": "John Doe", "age": 30, "gender": "M", "berth": "LB"}]'
        )
        self.passenger_details_edit.setMaximumHeight(70)
        form.addRow("Passenger Details*:", self.passenger_details_edit)

        # 7. Mobile & Email
        contact_layout = QHBoxLayout()
        contact_layout.setSpacing(8)
        self.mobile_edit = QLineEdit()
        self.mobile_edit.setPlaceholderText("Optional 10-digit mobile")
        self.mobile_edit.setMaxLength(20)
        contact_layout.addWidget(self.mobile_edit, stretch=1)

        email_label = QLabel("Email:")
        email_label.setStyleSheet("color: #cccccc; font-size: 13px; margin-left: 10px;")
        contact_layout.addWidget(email_label)

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Optional email address")
        self.email_edit.setMaxLength(100)
        contact_layout.addWidget(self.email_edit, stretch=1)
        form.addRow("Mobile:", contact_layout)

        # 8. Railway Account selection
        self.account_combo = QComboBox()
        self.account_combo.addItem("No account linked", None)
        for acct in self._accounts:
            self.account_combo.addItem(acct.get("username", ""), acct.get("id"))
        form.addRow("Railway Account:", self.account_combo)

        # 9. Proxy Selector
        self.proxy_combo = QComboBox()
        self.proxy_combo.addItem("Direct Connection (No Proxy)", None)
        for p in self._proxies:
            p_name = p.get("name") or f"{p.get('host')}:{p.get('port')}"
            p_proto = p.get("type", "HTTP").upper()
            display_str = f"{p_name} ({p_proto} - {p.get('host')}:{p.get('port')})"
            self.proxy_combo.addItem(display_str, p.get("id"))
        form.addRow("Network Proxy:", self.proxy_combo)

        # 10. Status
        self.status_combo = QComboBox()
        self.status_combo.addItems(["draft", "active", "archived"])
        form.addRow("Status:", self.status_combo)

        layout.addLayout(form)

        # Travel & Booking Preferences (from recovered desktop spec)
        options_group = QGroupBox("Travel & Booking Preferences")
        options_layout = QHBoxLayout(options_group)
        options_layout.setSpacing(16)

        self.auto_upgrade_cb = QCheckBox("Auto Upgradation")
        self.book_cnf_cb = QCheckBox("Book only if confirmed")
        self.insurance_cb = QCheckBox("Travel Insurance")
        self.insurance_cb.setChecked(True)

        options_layout.addWidget(self.auto_upgrade_cb)
        options_layout.addWidget(self.book_cnf_cb)
        options_layout.addWidget(self.insurance_cb)
        options_layout.addStretch()
        layout.addWidget(options_group)

        # Buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.save_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Save
        )
        self.save_button.setText("Save" if not self._is_edit else "Update")
        self.button_box.accepted.connect(self._on_save)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _setup_completers(self) -> None:
        """Configure autocompleters using MasterDataService."""
        if not self._master_data_service:
            return

        # Station completer
        station_items = self._master_data_service.get_station_completions()
        if station_items:
            station_completer = QCompleter(station_items, self)
            station_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            station_completer.setFilterMode(Qt.MatchFlag.MatchContains)
            station_completer.setMaxVisibleItems(12)
            self.from_station_edit.setCompleter(station_completer)

            to_station_completer = QCompleter(station_items, self)
            to_station_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            to_station_completer.setFilterMode(Qt.MatchFlag.MatchContains)
            to_station_completer.setMaxVisibleItems(12)
            self.to_station_edit.setCompleter(to_station_completer)

        # Train completer
        train_items = self._master_data_service.get_train_completions()
        if train_items:
            train_completer = QCompleter(train_items, self)
            train_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            train_completer.setFilterMode(Qt.MatchFlag.MatchContains)
            train_completer.setMaxVisibleItems(12)
            self.train_number_edit.setCompleter(train_completer)

    # ------------------------------------------------------------------
    # Autocomplete & Input Handlers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_station_code(text: str) -> str:
        """Extract clean station code from potential 'CODE - NAME' string."""
        s = text.strip()
        if " - " in s:
            s = s.split(" - ", 1)[0].strip()
        return s.upper()

    @staticmethod
    def _clean_train_number(text: str) -> str:
        """Extract train number from potential 'NUMBER - NAME' string."""
        s = text.strip()
        if " - " in s:
            s = s.split(" - ", 1)[0].strip()
        return s

    def _on_train_number_changed(self) -> None:
        """Handle train number input change and auto-fill train name."""
        text = self.train_number_edit.text()
        if " - " in text:
            parts = text.split(" - ", 1)
            number = parts[0].strip()
            name = parts[1].strip()
            self.train_number_edit.blockSignals(True)
            self.train_number_edit.setText(number)
            self.train_number_edit.blockSignals(False)
            self.train_name_edit.setText(name)
            return

        clean_num = text.strip()
        if self._master_data_service and clean_num:
            train_info = self._master_data_service.get_train_by_number(clean_num)
            if train_info:
                self.train_name_edit.setText(train_info.get("name", ""))
            else:
                self.train_name_edit.clear()
        elif not clean_num:
            self.train_name_edit.clear()

    def _on_from_station_changed(self) -> None:
        """Handle source station input and update preview hint."""
        text = self.from_station_edit.text()
        if " - " in text:
            parts = text.split(" - ", 1)
            code = parts[0].strip().upper()
            name = parts[1].strip()
            self.from_station_edit.blockSignals(True)
            self.from_station_edit.setText(code)
            self.from_station_edit.blockSignals(False)
            self.from_station_hint.setText(f"✓ {name}")
            return

        code = text.strip().upper()
        if self._master_data_service and code:
            stn = self._master_data_service.get_station_by_code(code)
            if stn:
                state = f" ({stn.get('state')})" if stn.get("state") else ""
                self.from_station_hint.setText(f"✓ {stn.get('name')}{state}")
            else:
                self.from_station_hint.clear()
        else:
            self.from_station_hint.clear()

    def _on_to_station_changed(self) -> None:
        """Handle destination station input and update preview hint."""
        text = self.to_station_edit.text()
        if " - " in text:
            parts = text.split(" - ", 1)
            code = parts[0].strip().upper()
            name = parts[1].strip()
            self.to_station_edit.blockSignals(True)
            self.to_station_edit.setText(code)
            self.to_station_edit.blockSignals(False)
            self.to_station_hint.setText(f"✓ {name}")
            return

        code = text.strip().upper()
        if self._master_data_service and code:
            stn = self._master_data_service.get_station_by_code(code)
            if stn:
                state = f" ({stn.get('state')})" if stn.get("state") else ""
                self.to_station_hint.setText(f"✓ {stn.get('name')}{state}")
            else:
                self.to_station_hint.clear()
        else:
            self.to_station_hint.clear()

    # ------------------------------------------------------------------
    # Data Loading & Validation
    # ------------------------------------------------------------------

    def _load_ticket(self, ticket: dict) -> None:
        """Load existing ticket data into the form.

        Args:
            ticket: Ticket dictionary from repository.
        """
        train_num = ticket.get("train_number", "")
        self.train_number_edit.setText(train_num)
        if ticket.get("train_name"):
            self.train_name_edit.setText(ticket.get("train_name", ""))
        else:
            self._on_train_number_changed()

        self.from_station_edit.setText(ticket.get("from_station", ""))
        self._on_from_station_changed()

        self.to_station_edit.setText(ticket.get("to_station", ""))
        self._on_to_station_changed()

        journey_date = ticket.get("journey_date", "")
        if journey_date:
            from PySide6.QtCore import QDate
            date = QDate.fromString(journey_date, "yyyy-MM-dd")
            if date.isValid():
                self.journey_date_edit.setDate(date)

        class_type = ticket.get("class", "")
        idx = self.class_combo.findText(class_type)
        if idx >= 0:
            self.class_combo.setCurrentIndex(idx)
        else:
            self.class_combo.setEditText(class_type)

        quota = ticket.get("quota", "")
        idx = self.quota_combo.findText(quota)
        if idx >= 0:
            self.quota_combo.setCurrentIndex(idx)
        else:
            self.quota_combo.setEditText(quota)

        self.passenger_details_edit.setPlainText(ticket.get("passenger_details", ""))
        self.mobile_edit.setText(ticket.get("mobile") or "")
        self.email_edit.setText(ticket.get("email") or "")

        # Select the associated account
        account_id = ticket.get("irctc_account_id")
        if account_id:
            idx = self.account_combo.findData(account_id)
            if idx >= 0:
                self.account_combo.setCurrentIndex(idx)

        # Select proxy
        proxy_id = ticket.get("proxy_id")
        if proxy_id:
            idx = self.proxy_combo.findData(proxy_id)
            if idx >= 0:
                self.proxy_combo.setCurrentIndex(idx)

        # Options
        self.auto_upgrade_cb.setChecked(bool(ticket.get("auto_upgrade", False)))
        self.book_cnf_cb.setChecked(bool(ticket.get("book_only_if_cnf", False)))
        self.insurance_cb.setChecked(bool(ticket.get("insurance", True)))

        status = ticket.get("status", "draft")
        idx = self.status_combo.findText(status)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)

    def _validate(self) -> str | None:
        """Validate form input.

        Returns:
            Error message string if validation fails, None if valid.
        """
        train_number = self._clean_train_number(self.train_number_edit.text())
        if not train_number:
            return "Train number is required."

        from_station = self._clean_station_code(self.from_station_edit.text())
        if not from_station:
            return "From station is required."

        to_station = self._clean_station_code(self.to_station_edit.text())
        if not to_station:
            return "To station is required."

        if from_station == to_station:
            return "From station and To station cannot be the same."

        journey_date = self.journey_date_edit.date().toString("yyyy-MM-dd")
        if not journey_date:
            return "Journey date is required."

        class_type = self.class_combo.currentText().strip()
        if not class_type:
            return "Travel class is required."

        quota = self.quota_combo.currentText().strip()
        if not quota:
            return "Quota is required."

        passenger_details = self.passenger_details_edit.toPlainText().strip()
        if not passenger_details:
            return "Passenger details are required."

        # Validate passenger_details is valid JSON
        try:
            json.loads(passenger_details)
        except json.JSONDecodeError:
            return "Passenger details must be valid JSON."

        email = self.email_edit.text().strip()
        if email and "@" not in email:
            return "Invalid email address."

        return None

    def _on_save(self) -> None:
        """Handle save button click."""
        error = self._validate()
        if error:
            QMessageBox.warning(self, "Validation Error", error)
            return

        data = self.get_ticket_data()
        self.ticket_saved.emit(data)
        self.accept()

    def get_ticket_data(self) -> dict[str, Any]:
        """Return the form data as a dictionary.

        Returns:
            Dictionary with ticket field values.
        """
        account_id = self.account_combo.currentData()
        if account_id is None:
            account_id = None

        proxy_id = self.proxy_combo.currentData()
        if proxy_id is None:
            proxy_id = None

        return {
            "train_number": self._clean_train_number(self.train_number_edit.text()),
            "train_name": self.train_name_edit.text().strip(),
            "from_station": self._clean_station_code(self.from_station_edit.text()),
            "to_station": self._clean_station_code(self.to_station_edit.text()),
            "journey_date": self.journey_date_edit.date().toString("yyyy-MM-dd"),
            "class": self.class_combo.currentText().strip(),
            "quota": self.quota_combo.currentText().strip(),
            "passenger_details": self.passenger_details_edit.toPlainText().strip(),
            "mobile": self.mobile_edit.text().strip() or None,
            "email": self.email_edit.text().strip() or None,
            "irctc_account_id": account_id,
            "proxy_id": proxy_id,
            "auto_upgrade": self.auto_upgrade_cb.isChecked(),
            "book_only_if_cnf": self.book_cnf_cb.isChecked(),
            "insurance": self.insurance_cb.isChecked(),
            "status": self.status_combo.currentText(),
        }
