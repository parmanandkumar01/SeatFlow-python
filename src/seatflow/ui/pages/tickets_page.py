"""Ticket Records page.

Page for managing ticket booking profiles with journey information.
Integrates with the TicketService for persistent storage.

Features:
- List ticket profiles (all non-sensitive fields)
- Add new tickets with validation
- Edit existing tickets
- Delete tickets with confirmation
- Search by train number, from/to station
- Filter by status, account, source, destination
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seatflow.services import (
    BookingWorkflowService,
    IrctcAccountService,
    MasterDataService,
    ProxyService,
    TicketService,
)
from seatflow.ui.dialogs.booking_monitor_dialog import BookingMonitorDialog
from seatflow.ui.dialogs.ticket_dialog import TicketDialog

from PySide6.QtWidgets import QMessageBox, QFrame


class TicketsPage(QWidget):
    """Page for managing ticket booking records.

    Integrates with TicketService and IrctcAccountService for
    persistent ticket storage and account relationships.
    """

    #: Emitted when a ticket is added, updated, or deleted.
    tickets_changed = Signal()

    def __init__(
        self,
        ticket_service: TicketService,
        account_service: IrctcAccountService,
        booking_workflow_service: BookingWorkflowService | None = None,
        proxy_service: ProxyService | None = None,
        master_data_service: MasterDataService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ticket_service = ticket_service
        self._account_service = account_service
        self._booking_workflow_service = booking_workflow_service
        self._proxy_service = proxy_service
        self._master_data_service = master_data_service
        self._accounts: list[dict] = []
        self._proxies: list[dict] = []
        self._setup_ui()
        self._refresh_accounts()
        self._refresh_proxies()
        self._refresh_tickets()

    def _setup_ui(self) -> None:
        """Initialize the tickets page layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Page header
        header_layout = QHBoxLayout()
        title = QLabel("Ticket Records")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #ffffff; background-color: transparent; border: none;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        btn_add = QPushButton("Create Ticket")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet(
            "QPushButton { background-color: #4caf50; color: #ffffff; border: none; "
            "border-radius: 6px; padding: 8px 16px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #5fbf60; }"
            "QPushButton:disabled { background-color: #555555; color: #888888; }"
        )
        btn_add.clicked.connect(self._on_add_ticket)
        header_layout.addWidget(btn_add)

        self._btn_add = btn_add
        layout.addLayout(header_layout)

        # Search and filter bar
        search_frame = QFrame()
        search_frame.setStyleSheet(
            "QFrame { background-color: #2d2d2d; border: 1px solid #3d3d3d; border-radius: 6px; }"
        )
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(12, 8, 12, 8)
        search_layout.setSpacing(8)

        search_label = QLabel("Search:")
        search_label.setStyleSheet("color: #b0b0b0; font-size: 12px; border: none;")
        search_layout.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by train number, from, or to station...")
        self.search_input.setStyleSheet(
            "QLineEdit { background-color: #3d3d3d; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 6px 10px; font-size: 12px; }"
        )
        self.search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_input)

        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("color: #b0b0b0; font-size: 12px; border: none;")
        search_layout.addWidget(filter_label)

        self.filter_combo = QWidget()  # placeholder replaced below
        from PySide6.QtWidgets import QComboBox
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Draft", "Active", "Archived"])
        self.filter_combo.setStyleSheet(
            "QComboBox { background-color: #3d3d3d; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 6px 10px; font-size: 12px; min-width: 100px; }"
            "QComboBox::drop-down { border: none; }"
        )
        self.filter_combo.currentTextChanged.connect(self._on_filter_changed)
        search_layout.addWidget(self.filter_combo)

        search_layout.addStretch()
        layout.addWidget(search_frame)

        # Table - ticket records
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Train No.", "From", "To", "Date", "Class", "Quota", "Account", "Actions"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #2d2d2d; border: 1px solid #3d3d3d; "
            "border-radius: 6px; gridline-color: #3d3d3d; color: #ffffff; }"
            "QTableWidget::item { padding: 8px; border: none; }"
            "QTableWidget::item:selected { background-color: #4caf50; }"
            "QHeaderView::section { background-color: #252525; color: #b0b0b0; "
            "padding: 8px; border: none; font-weight: bold; }"
        )
        layout.addWidget(self.table)

        # Empty state
        self._show_empty_state()

    def _refresh_accounts(self) -> None:
        """Refresh the list of railway accounts for the dialog."""
        try:
            self._accounts = self._account_service.list_accounts()
        except Exception:
            self._accounts = []

    def _refresh_proxies(self) -> None:
        """Refresh the list of proxies for the dialog."""
        if self._proxy_service is not None:
            try:
                self._proxies = self._proxy_service.list_proxies()
            except Exception:
                self._proxies = []
        else:
            self._proxies = []

    def _refresh_tickets(self) -> None:
        """Refresh the ticket table from the service layer."""
        tickets = self._ticket_service.list_tickets()
        self._populate_table(tickets)

    def _populate_table(self, tickets: list[dict]) -> None:
        """Populate the table with ticket data."""
        if not tickets:
            self._show_empty_state()
            return

        self.table.setRowCount(len(tickets))
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["Train No.", "From", "To", "Date", "Class", "Quota", "Account", "Actions"]
        )

        # Build account lookup for display
        account_lookup = {a["id"]: a.get("username", "") for a in self._accounts}

        for row, ticket in enumerate(tickets):
            self.table.setItem(row, 0, QTableWidgetItem(ticket.get("train_number", "")))
            self.table.setItem(row, 1, QTableWidgetItem(ticket.get("from_station", "")))
            self.table.setItem(row, 2, QTableWidgetItem(ticket.get("to_station", "")))
            self.table.setItem(row, 3, QTableWidgetItem(ticket.get("journey_date", "")))
            self.table.setItem(row, 4, QTableWidgetItem(ticket.get("class", "")))
            self.table.setItem(row, 5, QTableWidgetItem(ticket.get("quota", "")))

            # Account column
            account_id = ticket.get("irctc_account_id")
            account_name = account_lookup.get(account_id, "—") if account_id else "—"
            self.table.setItem(row, 6, QTableWidgetItem(account_name))

            # Actions
            from PySide6.QtWidgets import QWidget as _QWidget
            from PySide6.QtWidgets import QHBoxLayout as _QHBoxLayout

            actions_widget = _QWidget()
            actions_layout = _QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            actions_layout.setSpacing(4)

            btn_edit = QPushButton("Edit")
            btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_edit.setProperty("ticket_id", ticket["id"])
            btn_edit.clicked.connect(self._on_edit_ticket)
            btn_edit.setStyleSheet(
                "QPushButton { background-color: #3d3d3d; color: #ffffff; border: none; "
                "border-radius: 4px; padding: 4px 12px; font-size: 12px; }"
                "QPushButton:hover { background-color: #4a4a4a; }"
            )

            btn_delete = QPushButton("Delete")
            btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_delete.setProperty("ticket_id", ticket["id"])
            btn_delete.clicked.connect(self._on_delete_ticket)
            btn_delete.setStyleSheet(
                "QPushButton { background-color: #f44336; color: #ffffff; border: none; "
                "border-radius: 4px; padding: 4px 12px; font-size: 12px; }"
                "QPushButton:hover { background-color: #ff5252; }"
            )

            btn_book = QPushButton("Book / Monitor")
            btn_book.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_book.setProperty("ticket_id", ticket["id"])
            btn_book.clicked.connect(self._on_book_ticket)
            btn_book.setStyleSheet(
                "QPushButton { background-color: #00bcd4; color: #ffffff; border: none; "
                "border-radius: 4px; padding: 4px 12px; font-size: 12px; font-weight: bold; }"
                "QPushButton:hover { background-color: #00bcd4dd; }"
                "QPushButton:disabled { background-color: #555555; color: #888888; }"
            )
            btn_book.setEnabled(self._booking_workflow_service is not None)

            actions_layout.addWidget(btn_book)
            actions_layout.addWidget(btn_edit)
            actions_layout.addWidget(btn_delete)
            actions_layout.addStretch()

            self.table.setCellWidget(row, 7, actions_widget)

        self.table.resizeColumnsToContents()

    def _show_empty_state(self) -> None:
        """Display empty state when no tickets exist."""
        self.table.setRowCount(0)
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels([""])
        item = QTableWidgetItem(
            "No ticket records configured. Click 'Create Ticket' to get started."
        )
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(Qt.GlobalColor.gray)
        self.table.setRowCount(1)
        self.table.setColumnCount(1)
        self.table.setItem(0, 0, item)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        text = text.strip()
        if text:
            tickets = self._ticket_service.search_tickets(text)
        else:
            tickets = self._ticket_service.list_tickets()
        self._populate_table(tickets)

    def _on_filter_changed(self, text: str) -> None:
        """Handle filter change."""
        status_map = {"All": None, "Draft": "draft", "Active": "active", "Archived": "archived"}
        status = status_map.get(text)
        tickets = self._ticket_service.filter_tickets(status=status)
        self._populate_table(tickets)

    def _on_add_ticket(self) -> None:
        """Handle add ticket button click."""
        self._refresh_accounts()
        self._refresh_proxies()
        dialog = TicketDialog(
            parent=self,
            accounts=self._accounts,
            master_data_service=self._master_data_service,
            proxies=self._proxies,
        )
        dialog.ticket_saved.connect(self._handle_ticket_saved)
        dialog.exec()

    def _on_edit_ticket(self) -> None:
        """Handle edit ticket button click."""
        button = self.sender()
        if not button:
            return
        ticket_id = button.property("ticket_id")
        if not ticket_id:
            return

        try:
            ticket = self._ticket_service.get_ticket(ticket_id)
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Failed to load ticket: {exc}"
            )
            return

        self._refresh_accounts()
        self._refresh_proxies()
        dialog = TicketDialog(
            parent=self,
            accounts=self._accounts,
            ticket=ticket,
            master_data_service=self._master_data_service,
            proxies=self._proxies,
        )
        dialog.ticket_saved.connect(
            lambda data: self._handle_ticket_saved(data, ticket_id=ticket_id)
        )
        dialog.exec()

    def _on_delete_ticket(self) -> None:
        """Handle delete ticket button click."""
        button = self.sender()
        if not button:
            return
        ticket_id = button.property("ticket_id")
        if not ticket_id:
            return

        try:
            ticket = self._ticket_service.get_ticket(ticket_id)
        except Exception:
            QMessageBox.critical(
                self, "Error", "Ticket not found."
            )
            return

        reply = QMessageBox.question(
            self,
            "Delete Ticket",
            f"Are you sure you want to delete ticket '{ticket.get('train_number', '')}' "
            f"from {ticket.get('from_station', '')} to {ticket.get('to_station', '')}?\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._ticket_service.delete_ticket(ticket_id)
            self._refresh_tickets()
            self.tickets_changed.emit()
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Failed to delete ticket: {exc}"
            )

    def _on_book_ticket(self) -> None:
        """Handle the Book / Monitor action button click."""
        if self._booking_workflow_service is None:
            QMessageBox.information(
                self,
                "Booking Unavailable",
                "The booking workflow service is not configured.",
            )
            return

        button = self.sender()
        if not button:
            return
        ticket_id = button.property("ticket_id")
        if not ticket_id:
            return

        try:
            ticket = self._ticket_service.get_ticket(ticket_id)
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Failed to load ticket: {exc}"
            )
            return

        account_username = "—"
        account_id = ticket.get("irctc_account_id")
        if account_id:
            try:
                account = self._account_service.get_account(account_id)
                account_username = account.get("username", "—")
            except Exception:
                account_username = "—"

        dialog = BookingMonitorDialog(
            ticket=ticket,
            workflow=self._booking_workflow_service,
            account_username=account_username,
            parent=self,
        )
        dialog.exec()
        self._refresh_tickets()

    def _handle_ticket_saved(
        self, data: dict, ticket_id: str | None = None
    ) -> None:
        """Handle ticket data saved from dialog.

        Args:
            data: Ticket form data from dialog.
            ticket_id: Existing ticket ID for edit mode, or None for add mode.
        """
        try:
            if ticket_id:
                self._ticket_service.update_ticket(
                    ticket_id=ticket_id,
                    train_number=data.get("train_number"),
                    from_station=data.get("from_station"),
                    to_station=data.get("to_station"),
                    journey_date=data.get("journey_date"),
                    class_type=data.get("class"),
                    quota=data.get("quota"),
                    passenger_details=data.get("passenger_details"),
                    mobile=data.get("mobile"),
                    email=data.get("email"),
                    irctc_account_id=data.get("irctc_account_id"),
                    status=data.get("status"),
                )
            else:
                self._ticket_service.add_ticket(
                    train_number=data.get("train_number", ""),
                    from_station=data.get("from_station", ""),
                    to_station=data.get("to_station", ""),
                    journey_date=data.get("journey_date", ""),
                    class_type=data.get("class", ""),
                    quota=data.get("quota", ""),
                    passenger_details=data.get("passenger_details", ""),
                    mobile=data.get("mobile"),
                    email=data.get("email"),
                    irctc_account_id=data.get("irctc_account_id"),
                    status=data.get("status", "draft"),
                )
            self._refresh_accounts()
            self._refresh_tickets()
            self.tickets_changed.emit()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to save ticket: {exc}")
