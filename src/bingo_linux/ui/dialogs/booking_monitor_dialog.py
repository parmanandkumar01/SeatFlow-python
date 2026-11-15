"""Booking Monitor dialog.

Reproduces the original ``open-ticket.html`` / ``mini.html`` monitoring
interface as a user-controlled, manual booking workflow monitor. The
dialog is a pure presentation + orchestration layer over
:class:`BookingWorkflowService`; it performs no network I/O, no CAPTCHA
solving, and no credential handling.

Layout
------
- Header: train number, route, journey date, class, quota, IRCTC username.
- 6-stage visual stepper (Session Init -> Account Auth -> Availability
  Check -> Passenger Submission -> Verification -> Payment & PNR).
- Read-only passenger preview table (Name, Age, Gender, Berth).
- Timestamped status log console (``QTextEdit``).
- Controls: Start, Cancel/Stop, and contextual checkpoint buttons.
- Automatic dialog handoff for CAPTCHA, 2FA, and fare confirmation.

All checkpoint values entered by the user are passed straight to the
service and discarded there (never stored or transmitted).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bingo_linux.services import BookingState, BookingWorkflowService
from bingo_linux.ui.dialogs.captcha_dialog import CaptchaDialog
from bingo_linux.ui.dialogs.fare_confirm_dialog import FareConfirmDialog
from bingo_linux.ui.dialogs.two_factor_dialog import TwoFactorDialog

# Dark theme palette (consistent with existing UI).
_BG = "#1a1a1a"
_PANEL = "#2d2d2d"
_PANEL_BORDER = "#3d3d3d"
_ACCENT_CYAN = "#00bcd4"
_ACCENT_ORANGE = "#ff9800"
_TEXT = "#ffffff"
_MUTED = "#b0b0b0"
_GREEN = "#4caf50"
_RED = "#f44336"

# The six monitor stages mapped to booking states. Each stage is
# considered "complete" once the workflow has reached or passed it.
_STAGES = [
    ("Session Init", BookingState.IN_PROGRESS),
    ("Account Auth", BookingState.WAITING_FOR_2FA),
    ("Availability Check", BookingState.WAITING_FOR_2FA),
    ("Passenger Submission", BookingState.WAITING_FOR_CAPTCHA),
    ("Verification (CAPTCHA / 2FA)", BookingState.PAYMENT),
    ("Payment & PNR", BookingState.COMPLETED),
]

# Order used to determine which stages are complete.
_STATE_ORDER = [
    BookingState.IDLE,
    BookingState.IN_PROGRESS,
    BookingState.WAITING_FOR_2FA,
    BookingState.WAITING_FOR_CAPTCHA,
    BookingState.PAYMENT,
    BookingState.COMPLETED,
]


class BookingMonitorDialog(QDialog):
    """Modal booking monitor for a single ticket profile.

    Parameters
    ----------
    ticket : dict
        The ticket profile to book (from ``TicketService``).
    workflow : BookingWorkflowService
        The shared workflow service driving the state machine.
    account_username : str | None
        Resolved IRCTC account username for display (optional).
    parent : QWidget | None
        Parent widget.
    """

    #: Emitted when the workflow reaches a terminal state.
    workflow_finished = Signal(str)

    def __init__(
        self,
        ticket: dict,
        workflow: BookingWorkflowService,
        account_username: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ticket = ticket
        self._workflow = workflow
        self._account_username = account_username or "—"
        self._started = False
        self._suppress_auto_dialog = False

        self.setWindowTitle("Booking Monitor")
        self.setModal(True)
        self.setMinimumSize(820, 680)
        self._setup_ui()
        self._connect_workflow()
        self._refresh_controls()
        self._render_passengers()
        self._log("info", "Monitor ready. Press 'Start Workflow' to begin.")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the dialog layout."""
        self.setStyleSheet(f"QDialog {{ background-color: {_BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        root.addWidget(self._build_header())
        root.addWidget(self._build_stepper())
        root.addWidget(self._build_passenger_section(), stretch=1)
        root.addWidget(self._build_log_section(), stretch=1)
        root.addLayout(self._build_controls())

    def _build_header(self) -> QWidget:
        """Build the ticket summary header."""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: {_PANEL}; border: 1px solid "
            f"{_PANEL_BORDER}; border-radius: 8px; }}"
        )
        grid = QGridLayout(frame)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)

        title = QLabel("Booking Monitor")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(
            f"color: {_ACCENT_CYAN}; background-color: transparent; border: none;"
        )
        grid.addWidget(title, 0, 0, 1, 4)

        fields = [
            ("Train", self._ticket.get("train_number", "")),
            (
                "Route",
                f"{self._ticket.get('from_station', '')} → "
                f"{self._ticket.get('to_station', '')}",
            ),
            ("Journey Date", self._ticket.get("journey_date", "")),
            ("Class", self._ticket.get("class", "")),
            ("Quota", self._ticket.get("quota", "")),
            ("IRCTC User", self._account_username),
        ]
        for i, (label, value) in enumerate(fields):
            row = 1 + i // 3
            col = (i % 3) * 2
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet(
                f"color: {_MUTED}; background-color: transparent; border: none;"
            )
            val = QLabel(str(value))
            val.setStyleSheet(
                f"color: {_TEXT}; background-color: transparent; border: none; "
                f"font-weight: bold;"
            )
            grid.addWidget(lbl, row, col)
            grid.addWidget(val, row, col + 1)

        return frame

    def _build_stepper(self) -> QWidget:
        """Build the 6-stage visual stepper."""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: {_PANEL}; border: 1px solid "
            f"{_PANEL_BORDER}; border-radius: 8px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        header = QLabel("Progress")
        header.setStyleSheet(
            f"color: {_MUTED}; background-color: transparent; border: none; "
            f"font-weight: bold;"
        )
        layout.addWidget(header)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._stage_labels: list[QLabel] = []
        for i, (name, _state) in enumerate(_STAGES):
            pill = QLabel(f"{i + 1}. {name}")
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setStyleSheet(self._stage_style("pending"))
            pill.setMinimumHeight(40)
            row.addWidget(pill, stretch=1)
            self._stage_labels.append(pill)
        layout.addLayout(row)
        return frame

    def _build_passenger_section(self) -> QWidget:
        """Build the read-only passenger preview table."""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: {_PANEL}; border: 1px solid "
            f"{_PANEL_BORDER}; border-radius: 8px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        header = QLabel("Passengers")
        header.setStyleSheet(
            f"color: {_MUTED}; background-color: transparent; border: none; "
            f"font-weight: bold;"
        )
        layout.addWidget(header)

        self.passenger_table = QTableWidget(0, 4)
        self.passenger_table.setHorizontalHeaderLabels(
            ["Name", "Age", "Gender", "Berth"]
        )
        self.passenger_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.passenger_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.passenger_table.setSelectionMode(
            QTableWidget.SelectionMode.NoSelection
        )
        self.passenger_table.setStyleSheet(
            f"QTableWidget {{ background-color: {_BG}; border: 1px solid "
            f"{_PANEL_BORDER}; border-radius: 6px; gridline-color: {_PANEL_BORDER}; "
            f"color: {_TEXT}; }}"
            f"QHeaderView::section {{ background-color: #252525; color: {_MUTED}; "
            f"padding: 6px; border: none; font-weight: bold; }}"
        )
        layout.addWidget(self.passenger_table)
        return frame

    def _build_log_section(self) -> QWidget:
        """Build the timestamped status log console."""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: {_PANEL}; border: 1px solid "
            f"{_PANEL_BORDER}; border-radius: 8px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        header = QLabel("Status Log")
        header.setStyleSheet(
            f"color: {_MUTED}; background-color: transparent; border: none; "
            f"font-weight: bold;"
        )
        layout.addWidget(header)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet(
            f"QTextEdit {{ background-color: {_BG}; border: 1px solid "
            f"{_PANEL_BORDER}; border-radius: 6px; color: {_TEXT}; "
            f"font-family: monospace; font-size: 12px; }}"
        )
        layout.addWidget(self.log_console)
        return frame

    def _build_controls(self) -> QHBoxLayout:
        """Build the control button row."""
        layout = QHBoxLayout()
        layout.setSpacing(8)

        self.btn_start = QPushButton("Start Workflow")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setStyleSheet(self._button_style(_ACCENT_CYAN))
        self.btn_start.clicked.connect(self._on_start)
        layout.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("Cancel / Stop")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet(self._button_style(_RED))
        self.btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(self.btn_cancel)

        self.btn_captcha = QPushButton("Enter CAPTCHA")
        self.btn_captcha.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_captcha.setStyleSheet(self._button_style(_ACCENT_ORANGE))
        self.btn_captcha.clicked.connect(self._on_manual_captcha)
        layout.addWidget(self.btn_captcha)

        self.btn_otp = QPushButton("Enter OTP")
        self.btn_otp.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_otp.setStyleSheet(self._button_style(_ACCENT_ORANGE))
        self.btn_otp.clicked.connect(self._on_manual_otp)
        layout.addWidget(self.btn_otp)

        self.btn_fare = QPushButton("Confirm Fare")
        self.btn_fare.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fare.setStyleSheet(self._button_style(_ACCENT_ORANGE))
        self.btn_fare.clicked.connect(self._on_confirm_fare)
        layout.addWidget(self.btn_fare)

        self.btn_pnr = QPushButton("Record PNR")
        self.btn_pnr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pnr.setStyleSheet(self._button_style(_ACCENT_CYAN))
        self.btn_pnr.clicked.connect(self._on_record_pnr)
        layout.addWidget(self.btn_pnr)

        self.btn_close = QPushButton("Close")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet(self._button_style(_PANEL_BORDER))
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close)

        layout.addStretch()
        return layout

    # ------------------------------------------------------------------
    # Styling helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _button_style(accent: str) -> str:
        return (
            f"QPushButton {{ background-color: {accent}; color: #ffffff; "
            f"border: none; border-radius: 6px; padding: 8px 14px; "
            f"font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {accent}dd; }}"
            f"QPushButton:disabled {{ background-color: #555555; color: #888888; }}"
        )

    @staticmethod
    def _stage_style(status: str) -> str:
        base = (
            "QLabel { border-radius: 6px; padding: 6px; font-size: 12px; "
            "font-weight: bold; }"
        )
        if status == "complete":
            return (
                f"background-color: {_GREEN}; color: #ffffff; {base}"
            )
        if status == "active":
            return (
                f"background-color: {_ACCENT_ORANGE}; color: #ffffff; {base}"
            )
        return f"background-color: #3d3d3d; color: {_MUTED}; {base}"

    # ------------------------------------------------------------------
    # Passenger rendering
    # ------------------------------------------------------------------

    def _render_passengers(self) -> None:
        """Parse the ticket's passenger_details JSON into the table."""
        self.passenger_table.setRowCount(0)
        raw = self._ticket.get("passenger_details", "") or ""
        passengers: list[dict] = []
        if raw.strip():
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    passengers = [p for p in parsed if isinstance(p, dict)]
            except (json.JSONDecodeError, TypeError):
                passengers = []

        self.passenger_table.setRowCount(len(passengers))
        for row, pax in enumerate(passengers):
            values = [
                str(pax.get("name", "")),
                str(pax.get("age", "")),
                str(pax.get("gender", "")),
                str(pax.get("berth", "") or pax.get("berth_preference", "")),
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.passenger_table.setItem(row, col, item)
        self.passenger_table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # Workflow wiring
    # ------------------------------------------------------------------

    def _connect_workflow(self) -> None:
        """Connect workflow signals to monitor slots."""
        self._workflow.state_changed.connect(self._on_state_changed)
        self._workflow.event_emitted.connect(self._on_event_emitted)
        self._workflow.waiting_for_captcha.connect(self._on_waiting_for_captcha)
        self._workflow.waiting_for_2fa.connect(self._on_waiting_for_2fa)
        self._workflow.waiting_for_fare_confirmation.connect(
            self._on_waiting_for_fare
        )
        self._workflow.booking_completed.connect(self._on_booking_completed)
        self._workflow.booking_failed.connect(self._on_booking_failed)
        self._workflow.booking_cancelled.connect(self._on_booking_cancelled)

    def _on_state_changed(self, old: str, new: str) -> None:
        """Handle a state transition: update stepper and controls."""
        self._update_stepper(BookingState(new))
        self._refresh_controls()

    def _on_event_emitted(self, name: str, message: str) -> None:
        """Handle a lifecycle event: append to the log console."""
        self._log("event", f"[{name}] {message}")

    # ------------------------------------------------------------------
    # Automatic dialog handoff
    # ------------------------------------------------------------------

    def _on_waiting_for_2fa(self) -> None:
        """Auto-open the 2FA dialog unless suppressed."""
        if self._suppress_auto_dialog:
            return
        self._open_2fa_dialog()

    def _on_waiting_for_captcha(self) -> None:
        """Auto-open the CAPTCHA dialog unless suppressed."""
        if self._suppress_auto_dialog:
            return
        self._open_captcha_dialog()

    def _on_waiting_for_fare(self) -> None:
        """Auto-open the fare confirmation dialog unless suppressed."""
        if self._suppress_auto_dialog:
            return
        self._open_fare_dialog()

    def _open_2fa_dialog(self) -> None:
        """Prompt for manual 2FA and feed it to the workflow."""
        dlg = TwoFactorDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            code = dlg.get_otp_code()
            try:
                self._workflow.submit_manual_2fa(code)
            except Exception as exc:
                self._log("error", f"2FA rejected: {exc}")

    def _open_captcha_dialog(self) -> None:
        """Prompt for manual CAPTCHA and feed it to the workflow."""
        dlg = CaptchaDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            text = dlg.get_captcha_text()
            try:
                self._workflow.submit_manual_captcha(text)
            except Exception as exc:
                self._log("error", f"CAPTCHA rejected: {exc}")

    def _open_fare_dialog(self) -> None:
        """Prompt for fare confirmation and feed it to the workflow."""
        dlg = FareConfirmDialog(
            self,
            fare_amount=self._ticket.get("fare_amount"),
            train_number=self._ticket.get("train_number"),
            journey_date=self._ticket.get("journey_date"),
        )
        confirmed = dlg.exec() == QDialog.DialogCode.Accepted
        try:
            self._workflow.confirm_fare(confirmed)
        except Exception as exc:
            self._log("error", f"Fare confirmation failed: {exc}")

    # ------------------------------------------------------------------
    # Control actions
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        """Start the workflow for this ticket."""
        if self._started:
            return
        ticket_id = self._ticket.get("id")
        account_id = self._ticket.get("irctc_account_id")
        try:
            self._workflow.start_session(ticket_id, account_id)
            self._started = True
            self._log("info", "Workflow started.")
            # The IN_PROGRESS state has no auto-dialog; advance to the
            # login/2FA checkpoint so the user is prompted to log in.
            self._workflow.reach_login_checkpoint()
        except Exception as exc:
            self._log("error", f"Failed to start: {exc}")

    def _on_cancel(self) -> None:
        """Cancel the active workflow."""
        try:
            self._workflow.cancel()
        except Exception as exc:
            self._log("error", f"Cancel failed: {exc}")

    def _on_manual_otp(self) -> None:
        """Manually trigger the OTP dialog (button fallback)."""
        self._open_2fa_dialog()

    def _on_manual_captcha(self) -> None:
        """Manually trigger the CAPTCHA dialog (button fallback)."""
        self._open_captcha_dialog()

    def _on_confirm_fare(self) -> None:
        """Manually trigger the fare dialog (button fallback)."""
        self._open_fare_dialog()

    def _on_record_pnr(self) -> None:
        """Prompt for the PNR and confirm payment."""
        text, ok = self._prompt_text("Record PNR", "Enter the confirmed PNR:")
        if not ok or not text.strip():
            return
        try:
            self._workflow.confirm_payment(text.strip())
        except Exception as exc:
            self._log("error", f"Payment failed: {exc}")

    def _prompt_text(self, title: str, label: str) -> tuple[str, bool]:
        """Minimal inline text prompt (avoids an extra module).

        Returns (text, ok). Uses a tiny QDialog built on the fly.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setModal(True)
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet(f"QDialog {{ background-color: {_BG}; }}")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {_TEXT}; background-color: transparent;")
        lay.addWidget(lbl)
        edit = QLineEdit()
        edit.setStyleSheet(
            f"QLineEdit {{ background-color: {_PANEL}; color: {_TEXT}; "
            f"border: 1px solid {_PANEL_BORDER}; border-radius: 4px; padding: 6px; }}"
        )
        lay.addWidget(edit)
        from PySide6.QtWidgets import QDialogButtonBox

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        return edit.text(), ok

    # ------------------------------------------------------------------
    # Terminal state handling
    # ------------------------------------------------------------------

    def _on_booking_completed(self, pnr: str) -> None:
        """Handle successful completion."""
        self._update_stepper(BookingState.COMPLETED)
        self._refresh_controls()
        self._log("success", f"Booking completed. PNR: {pnr}")
        self.workflow_finished.emit(f"completed:{pnr}")

    def _on_booking_failed(self, reason: str) -> None:
        """Handle failure."""
        self._refresh_controls()
        self._log("error", f"Booking failed: {reason}")
        self.workflow_finished.emit(f"failed:{reason}")

    def _on_booking_cancelled(self) -> None:
        """Handle cancellation."""
        self._update_stepper(BookingState.CANCELLED)
        self._refresh_controls()
        self.workflow_finished.emit("cancelled")

    # ------------------------------------------------------------------
    # Stepper + control state
    # ------------------------------------------------------------------

    def _update_stepper(self, state: BookingState) -> None:
        """Update stepper pill styles based on the current state."""
        current_idx = (
            _STATE_ORDER.index(state) if state in _STATE_ORDER else 0
        )
        for i, pill in enumerate(self._stage_labels):
            stage_state = _STAGES[i][1]
            stage_idx = (
                _STATE_ORDER.index(stage_state)
                if stage_state in _STATE_ORDER
                else 0
            )
            if state in (
                BookingState.COMPLETED,
                BookingState.FAILED,
                BookingState.CANCELLED,
            ) and i == len(_STAGES) - 1 and state == BookingState.COMPLETED:
                pill.setStyleSheet(self._stage_style("complete"))
            elif stage_idx < current_idx:
                pill.setStyleSheet(self._stage_style("complete"))
            elif stage_idx == current_idx:
                pill.setStyleSheet(self._stage_style("active"))
            else:
                pill.setStyleSheet(self._stage_style("pending"))

    def _refresh_controls(self) -> None:
        """Enable/disable buttons according to the current state."""
        state = self._workflow.state
        active = self._workflow.is_active

        self.btn_start.setEnabled(state == BookingState.IDLE and not self._started)
        self.btn_cancel.setEnabled(active)
        self.btn_captcha.setEnabled(state == BookingState.WAITING_FOR_CAPTCHA)
        self.btn_otp.setEnabled(state == BookingState.WAITING_FOR_2FA)
        self.btn_fare.setEnabled(state == BookingState.PAYMENT)
        self.btn_pnr.setEnabled(state == BookingState.PAYMENT)
        self.btn_close.setEnabled(
            state
            in (
                BookingState.COMPLETED,
                BookingState.FAILED,
                BookingState.CANCELLED,
            )
        )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, level: str, message: str) -> None:
        """Append a timestamped line to the log console."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = {
            "info": _MUTED,
            "event": _ACCENT_CYAN,
            "success": _GREEN,
            "error": _RED,
        }.get(level, _TEXT)
        self.log_console.append(
            f'<span style="color:{color}">[{timestamp}] {message}</span>'
        )

    # ------------------------------------------------------------------
    # Public accessors (for tests / integration)
    # ------------------------------------------------------------------

    @property
    def workflow(self) -> BookingWorkflowService:
        """Return the bound workflow service."""
        return self._workflow

    @property
    def is_started(self) -> bool:
        """Return True once the workflow has been started from this dialog."""
        return self._started