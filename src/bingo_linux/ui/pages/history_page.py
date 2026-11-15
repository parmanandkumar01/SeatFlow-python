"""Journey History page.

Page for viewing previous journey and booking records.
Integrates with the HistoryService for persistent storage.

Features:
- List journey history records
- Date-based filtering (All, Upcoming, Past, Today, Last 7 days, Last 30 days, This Month)
- Search by PNR or train number
- Remove history record with confirmation
- Remove all history records with confirmation
- Refresh behavior
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

from bingo_linux.services import HistoryService
from bingo_linux.services.history_service import (
    FILTER_30D,
    FILTER_7D,
    FILTER_ALL,
    FILTER_MONTH,
    FILTER_PAST,
    FILTER_TODAY,
    FILTER_UPCOMING,
)

from PySide6.QtWidgets import QFrame, QMessageBox


class HistoryPage(QWidget):
    """Page for viewing journey history records.

    Integrates with HistoryService for persistent storage of
    booking history records.
    """

    #: Emitted when a history record is removed.
    history_changed = Signal()

    def __init__(
        self,
        history_service: HistoryService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = history_service
        self._current_filter = FILTER_ALL
        self._setup_ui()
        self._refresh_history()

    def _setup_ui(self) -> None:
        """Initialize the history page layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Page header
        header_layout = QHBoxLayout()
        title = QLabel("Journey History")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #ffffff; background-color: transparent; border: none;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #3d3d3d; color: #ffffff; border: none; "
            "border-radius: 6px; padding: 8px 16px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        btn_refresh.clicked.connect(self._refresh_history)
        header_layout.addWidget(btn_refresh)

        btn_clear = QPushButton("Clear All")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setStyleSheet(
            "QPushButton { background-color: #f44336; color: #ffffff; border: none; "
            "border-radius: 6px; padding: 8px 16px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #ff5252; }"
            "QPushButton:disabled { background-color: #555555; color: #888888; }"
        )
        btn_clear.clicked.connect(self._on_clear_all)
        self._btn_clear = btn_clear
        header_layout.addWidget(btn_clear)

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
        self.search_input.setPlaceholderText("Search by PNR or train number...")
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
        filter_labels = self._service.filter_labels()
        for key in [FILTER_ALL, FILTER_UPCOMING, FILTER_PAST, FILTER_TODAY, FILTER_7D, FILTER_30D, FILTER_MONTH]:
            self.filter_combo.addItem(filter_labels[key], key)
        self.filter_combo.setStyleSheet(
            "QComboBox { background-color: #3d3d3d; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 6px 10px; font-size: 12px; min-width: 120px; }"
            "QComboBox::drop-down { border: none; }"
        )
        self.filter_combo.currentTextChanged.connect(self._on_filter_changed)
        search_layout.addWidget(self.filter_combo)

        search_layout.addStretch()
        layout.addWidget(search_frame)

        # Table - journey history records
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["PNR", "Train No.", "Journey Date", "Account", "Status", "Amount", "Booked At", "Actions"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #2d2d2d; border: 1px solid #3d3d3d; "
            "border-radius: 6px; gridline-color: #3d3d3d; color: #ffffff; }"
            "QTableWidget::item { padding: 8px; border: none; }"
            "QTableWidget::item:selected { background-color: #ff9800; }"
            "QHeaderView::section { background-color: #252525; color: #b0b0b0; "
            "padding: 8px; border: none; font-weight: bold; }"
        )
        layout.addWidget(self.table)

        # Empty state
        self._show_empty_state()

    def _refresh_history(self) -> None:
        """Refresh the history table from the service layer."""
        history = self._service.filter_history(filter_key=self._current_filter)
        self._populate_table(history)

    def _populate_table(self, records: list[dict]) -> None:
        """Populate the table with history data."""
        if not records:
            self._show_empty_state()
            return

        self.table.setRowCount(len(records))
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["PNR", "Train No.", "Journey Date", "Account", "Status", "Amount", "Booked At", "Actions"]
        )

        for row, record in enumerate(records):
            # PNR
            self.table.setItem(
                row, 0, QTableWidgetItem(record.get("pnr_number", "—"))
            )
            # Train No.
            self.table.setItem(
                row, 1, QTableWidgetItem(record.get("train_number", "—"))
            )
            # Journey Date
            self.table.setItem(
                row, 2, QTableWidgetItem(record.get("journey_date", "—"))
            )
            # Account
            account_id = record.get("irctc_account_id")
            account_name = self._service.get_account_name(account_id)
            self.table.setItem(row, 3, QTableWidgetItem(account_name))
            # Status
            status = record.get("booking_status", "—")
            status_item = QTableWidgetItem(status.capitalize())
            status_color = {
                "success": Qt.GlobalColor.green,
                "pending": Qt.GlobalColor.yellow,
                "failed": Qt.GlobalColor.red,
                "cancelled": Qt.GlobalColor.gray,
            }.get(status, Qt.GlobalColor.white)
            status_item.setForeground(status_color)
            self.table.setItem(row, 4, status_item)
            # Amount
            amount = record.get("fare_amount")
            amount_text = f"₹{amount}" if amount is not None else "—"
            self.table.setItem(row, 5, QTableWidgetItem(amount_text))
            # Booked At
            self.table.setItem(
                row, 6, QTableWidgetItem(record.get("booking_timestamp", "—"))
            )

            # Actions
            from PySide6.QtWidgets import QWidget as _QWidget
            from PySide6.QtWidgets import QHBoxLayout as _QHBoxLayout

            actions_widget = _QWidget()
            actions_layout = _QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            actions_layout.setSpacing(4)

            btn_delete = QPushButton("Delete")
            btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_delete.setProperty("history_id", record["id"])
            btn_delete.clicked.connect(self._on_delete_history)
            btn_delete.setStyleSheet(
                "QPushButton { background-color: #f44336; color: #ffffff; border: none; "
                "border-radius: 4px; padding: 4px 12px; font-size: 12px; }"
                "QPushButton:hover { background-color: #ff5252; }"
            )

            actions_layout.addWidget(btn_delete)
            actions_layout.addStretch()

            self.table.setCellWidget(row, 7, actions_widget)

        self.table.resizeColumnsToContents()

        # Update clear all button state
        self._btn_clear.setEnabled(len(records) > 0)

    def _show_empty_state(self) -> None:
        """Display empty state when no history exists."""
        self.table.setRowCount(0)
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels([""])
        item = QTableWidgetItem(
            "No journey history records yet."
        )
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(Qt.GlobalColor.gray)
        self.table.setRowCount(1)
        self.table.setColumnCount(1)
        self.table.setItem(0, 0, item)
        self._btn_clear.setEnabled(False)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        text = text.strip()
        if text:
            records = self._service.search_history(text)
        else:
            records = self._service.filter_history(filter_key=self._current_filter)
        self._populate_table(records)

    def _on_filter_changed(self, text: str) -> None:
        """Handle filter change."""
        # Find the filter key for the selected label
        filter_labels = self._service.filter_labels()
        filter_key = FILTER_ALL
        for key, label in filter_labels.items():
            if label == text:
                filter_key = key
                break
        self._current_filter = filter_key
        records = self._service.filter_history(filter_key=filter_key)
        self._populate_table(records)

    def _on_delete_history(self) -> None:
        """Handle delete history button click."""
        button = self.sender()
        if not button:
            return
        history_id = button.property("history_id")
        if not history_id:
            return

        try:
            record = self._service.get_history(history_id)
        except Exception:
            QMessageBox.critical(
                self, "Error", "History record not found."
            )
            return

        pnr = record.get("pnr_number", "unknown")
        reply = QMessageBox.question(
            self,
            "Delete History Record",
            f"Are you sure you want to delete the history record for PNR '{pnr}'?\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service.remove_history(history_id)
            self._refresh_history()
            self.history_changed.emit()
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Failed to remove history record: {exc}"
            )

    def _on_clear_all(self) -> None:
        """Handle clear all button click."""
        # Count non-deleted records
        records = self._service.filter_history(filter_key=FILTER_ALL)
        if not records:
            return

        reply = QMessageBox.question(
            self,
            "Clear All History",
            f"Are you sure you want to clear all {len(records)} history record(s)?\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            removed_count = self._service.remove_all_history()
            self._refresh_history()
            self.history_changed.emit()
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Failed to clear history: {exc}"
            )
