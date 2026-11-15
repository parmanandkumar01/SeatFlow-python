"""PNR Records page.

Page for viewing PNR booking records stored locally.
Integrates with the PnrService for persistent storage.

Features:
- List PNR records
- Search by PNR number or train number
- Display PNR record details
- Remove PNR record with confirmation
- Remove all PNR records with confirmation
- Refresh behavior
"""

from __future__ import annotations

from typing import Optional

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

from seatflow.services import PnrService
from seatflow.services.pnr_service import (
    PNR_STATUS_BOOKED,
    PNR_STATUS_CANCELLED,
    PNR_STATUS_FAILED,
    PNR_STATUS_PENDING,
)

try:
    from seatflow.services.pnr_sync_service import PnrSyncService
except Exception:  # pragma: no cover - defensive import guard
    PnrSyncService = None  # type: ignore[assignment]

from PySide6.QtWidgets import QFrame, QMessageBox


class PnrPage(QWidget):
    """Page for viewing PNR records.

    Integrates with PnrService for persistent storage of
    PNR booking records.
    """

    #: Emitted when a PNR record is removed.
    pnr_changed = Signal()

    def __init__(
        self,
        pnr_service: PnrService,
        pnr_sync_service: Optional[PnrSyncService] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = pnr_service
        self._sync_service = pnr_sync_service
        self._setup_ui()
        self._refresh_pnrs()

    def _setup_ui(self) -> None:
        """Initialize the PNR page layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Page header
        header_layout = QHBoxLayout()
        title = QLabel("PNR Records")
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
        btn_refresh.clicked.connect(self._refresh_pnrs)
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

        # Search bar
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

        search_layout.addStretch()
        layout.addWidget(search_frame)

        # Table - PNR records
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["PNR Number", "PNR (Last 6)", "Train No.", "Journey Date", "Status", "Amount", "Looked Up At", "Actions"]
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

    def _refresh_pnrs(self) -> None:
        """Refresh the PNR table from the service layer."""
        pnrs = self._service.list_pnrs()
        self._populate_table(pnrs)

    def _populate_table(self, records: list[dict]) -> None:
        """Populate the table with PNR data."""
        if not records:
            self._show_empty_state()
            return

        self.table.setRowCount(len(records))
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["PNR Number", "PNR (Last 6)", "Train No.", "Journey Date", "Status", "Amount", "Looked Up At", "Actions"]
        )

        for row, record in enumerate(records):
            # PNR Number (full)
            pnr_number = record.get("pnr_number", "—")
            self.table.setItem(row, 0, QTableWidgetItem(pnr_number))

            # PNR (Last 6 digits)
            pnr_short = self._service.get_pnr_short(pnr_number)
            self.table.setItem(row, 1, QTableWidgetItem(pnr_short))

            # Train No.
            self.table.setItem(
                row, 2, QTableWidgetItem(record.get("train_number", "—"))
            )
            # Journey Date
            self.table.setItem(
                row, 3, QTableWidgetItem(record.get("journey_date", "—"))
            )
            # Status
            status = record.get("booking_status", "—")
            status_item = QTableWidgetItem(status.capitalize() if status else "—")
            status_color = {
                "booked": Qt.GlobalColor.green,
                "pending": Qt.GlobalColor.yellow,
                "failed": Qt.GlobalColor.red,
                "cancelled": Qt.GlobalColor.gray,
            }.get(status, Qt.GlobalColor.white)
            status_item.setForeground(status_color)
            self.table.setItem(row, 4, status_item)
            # Amount
            amount = record.get("fare_amount")
            amount_text = self._service.format_fare_amount(amount)
            self.table.setItem(row, 5, QTableWidgetItem(amount_text))
            # Looked Up At
            self.table.setItem(
                row, 6, QTableWidgetItem(record.get("looked_up_at", "—"))
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
            btn_delete.setProperty("pnr_number", record.get("pnr_number", ""))
            btn_delete.clicked.connect(self._on_delete_pnr)
            btn_delete.setStyleSheet(
                "QPushButton { background-color: #f44336; color: #ffffff; border: none; "
                "border-radius: 4px; padding: 4px 12px; font-size: 12px; }"
                "QPushButton:hover { background-color: #ff5252; }"
            )

            btn_refresh_status = QPushButton("Refresh Status")
            btn_refresh_status.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_refresh_status.setProperty(
                "pnr_number", record.get("pnr_number", "")
            )
            btn_refresh_status.setEnabled(self._sync_service is not None)
            btn_refresh_status.clicked.connect(self._on_refresh_status)
            btn_refresh_status.setStyleSheet(
                "QPushButton { background-color: #3d3d3d; color: #ffffff; border: none; "
                "border-radius: 4px; padding: 4px 12px; font-size: 12px; }"
                "QPushButton:hover { background-color: #4a4a4a; }"
                "QPushButton:disabled { background-color: #555555; color: #888888; }"
            )

            actions_layout.addWidget(btn_refresh_status)
            actions_layout.addWidget(btn_delete)
            actions_layout.addStretch()

            self.table.setCellWidget(row, 7, actions_widget)

        self.table.resizeColumnsToContents()

        # Update clear all button state
        self._btn_clear.setEnabled(len(records) > 0)

    def _show_empty_state(self) -> None:
        """Display empty state when no PNR records exist."""
        self.table.setRowCount(0)
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels([""])
        item = QTableWidgetItem(
            "No PNR records yet."
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
            records = self._service.search_pnrs(text)
        else:
            records = self._service.list_pnrs()
        self._populate_table(records)

    def _on_delete_pnr(self) -> None:
        """Handle delete PNR button click."""
        button = self.sender()
        if not button:
            return
        pnr_number = button.property("pnr_number")
        if not pnr_number:
            return

        try:
            record = self._service.get_pnr(pnr_number)
        except Exception:
            QMessageBox.critical(
                self, "Error", "PNR record not found."
            )
            return

        pnr = record.get("pnr_number", "unknown")
        reply = QMessageBox.question(
            self,
            "Delete PNR Record",
            f"Are you sure you want to delete the PNR record '{pnr}'?\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service.remove_pnr(pnr_number)
            self._refresh_pnrs()
            self.pnr_changed.emit()
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Failed to remove PNR record: {exc}"
            )

    def _on_refresh_status(self) -> None:
        """Handle live PNR status refresh for a single record (RT-06).

        Calls PnrSyncService.refresh_pnr (user-initiated, single PNR).
        Since the PNR endpoint contract is not recovered, the endpoint is
        not configured by default, so this reports "endpoint not configured"
        rather than inventing a live URL.
        """
        button = self.sender()
        if not button:
            return
        pnr_number = button.property("pnr_number")
        if not pnr_number:
            return

        if self._sync_service is None:
            QMessageBox.information(
                self,
                "Refresh Status",
                "PNR sync service is not available.",
            )
            return

        result = self._sync_service.refresh_pnr(pnr_number)
        if result.get("ok"):
            msg = (
                f"PNR {pnr_number} refreshed.\n"
                f"Status: {result.get('status')}\n"
                f"Train: {result.get('train_number') or '—'}\n"
                f"Date: {result.get('journey_date') or '—'}"
            )
            if result.get("status_changed"):
                msg += (
                    f"\n\nStatus changed from "
                    f"{result.get('previous_status') or '—'} to "
                    f"{result.get('status')}."
                )
            QMessageBox.information(self, "Refresh Status", msg)
            self._refresh_pnrs()
            self.pnr_changed.emit()
        elif result.get("endpoint_not_configured"):
            QMessageBox.information(
                self,
                "Refresh Status",
                "Live PNR refresh is not available: the PNR status endpoint "
                "contract has not been recovered. Configure the endpoint URL "
                "in Settings once the contract is authenticated.",
            )
        elif result.get("cooldown_remaining"):
            QMessageBox.information(
                self,
                "Refresh Status",
                f"Rate-limit cooldown active. Try again in "
                f"{result.get('cooldown_remaining')} second(s).",
            )
        elif result.get("manual_verification_required"):
            QMessageBox.information(
                self,
                "Refresh Status",
                "The endpoint returned a CAPTCHA or bot-verification challenge. "
                "Automatic PNR refresh is not supported; please verify manually "
                "in the browser.",
            )
        else:
            QMessageBox.critical(
                self,
                "Refresh Status",
                f"Failed to refresh PNR {pnr_number}: "
                f"{result.get('message', 'unknown error')}",
            )

    def _on_clear_all(self) -> None:
        """Handle clear all button click."""
        records = self._service.list_pnrs()
        if not records:
            return

        reply = QMessageBox.question(
            self,
            "Clear All PNR Records",
            f"Are you sure you want to clear all {len(records)} PNR record(s)?\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            removed_count = self._service.remove_all_pnrs()
            self._refresh_pnrs()
            self.pnr_changed.emit()
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Failed to clear PNR records: {exc}"
            )
