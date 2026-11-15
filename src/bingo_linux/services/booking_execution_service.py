"""Booking execution pipeline service (mapps1 API contract).

Provides a clean-room, manual/user-controlled 6-step booking flow
service wired to the TicketPanelWindow worker buttons (W2/W3/W5/W6/APP).
Each worker tag maps to a distinct execution method (browser/app variant):

    "@ W2"  -> edge        (Microsoft Edge)
    "🛡️ W3" -> brave      (Brave Browser)
    "0 W5"  -> opera       (Opera Browser)
    "🚀 W6" -> comet       (Perplexity Comet)
    "🌀 APP" -> app        (IRCTC mobile app variant)

The service wraps :class:`BookingWorkflowService` to add worker-specific
execution contexts. All verification checkpoints (CAPTCHA, 2FA, fare,
payment/PNR) are user-driven. No network I/O, CAPTCHA solving, or
automated login is performed.

State machine per worker session:

    IDLE
      -> IN_PROGRESS            (start_session)
      -> WAITING_FOR_2FA        (reached login checkpoint)
      -> WAITING_FOR_CAPTCHA    (2FA accepted)
      -> PAYMENT                (captcha + fare accepted)
      -> COMPLETED              (payment confirmed with PNR)
      -> FAILED                 (error during any stage)
      -> CANCELLED              (user cancels)

Only allowed transitions are permitted; any other transition raises
InvalidTransitionError.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal

from bingo_linux.database.database import Database
from bingo_linux.services import (
    BookingSessionError,
    BookingState,
    BookingWorkflowError,
    BookingWorkflowService,
    HistoryService,
    InvalidCheckpointError,
    InvalidTransitionError,
    IrctcAccountService,
    PnrService,
    TicketService,
)


#: Mapping of TicketPanelWindow worker button labels to execution methods.
WORKER_METHODS: dict[str, str] = {
    "@ W2": "edge",
    "🛡️ W3": "brave",
    "0 W5": "opera",
    "🚀 W6": "comet",
    "🌀 APP": "app",
}

#: Reverse mapping from method to worker label.
METHOD_TO_WORKER: dict[str, str] = {v: k for k, v in WORKER_METHODS.items()}

#: All supported worker tags.
SUPPORTED_WORKERS: frozenset[str] = frozenset(WORKER_METHODS.keys())


class BookingExecutionError(Exception):
    """Base exception for booking execution errors."""


class WorkerNotSupportedError(BookingExecutionError):
    """Raised when an unsupported worker tag is used."""


class ExecutionSessionNotFoundError(BookingExecutionError):
    """Raised when no active execution session exists for a ticket."""


class BookingExecutionService(QObject):
    """Coordinates manual booking execution sessions per worker.

    Wraps :class:`BookingWorkflowService` to provide worker-aware
    execution contexts. Each TicketPanelWindow worker button (W2/W3/W5/
    W6/APP) maps to a distinct execution method. All checkpoints are
    user-driven; the service only tracks state and emits signals.

    Signals
    -------
    execution_started(str, str)
        Emitted with (ticket_id, worker_tag) when a session starts.
    execution_completed(str, str, str)
        Emitted with (ticket_id, worker_tag, pnr) on completion.
    execution_failed(str, str, str)
        Emitted with (ticket_id, worker_tag, reason) on failure.
    execution_cancelled(str, str)
        Emitted with (ticket_id, worker_tag) on cancellation.
    worker_state_changed(str, str, str)
        Emitted with (ticket_id, worker_tag, new_state) on transition.
    event_emitted(str, str)
        Emitted with (event_name, message) for each lifecycle event.
    """

    execution_started = Signal(str, str)
    execution_completed = Signal(str, str, str)
    execution_failed = Signal(str, str, str)
    execution_cancelled = Signal(str, str)
    worker_state_changed = Signal(str, str, str)
    event_emitted = Signal(str, str)

    def __init__(
        self,
        db: Database,
        booking_workflow: Optional[BookingWorkflowService] = None,
        history_service: Optional[HistoryService] = None,
        pnr_service: Optional[PnrService] = None,
        ticket_service: Optional[TicketService] = None,
        account_service: Optional[IrctcAccountService] = None,
    ) -> None:
        """Initialize the booking execution service.

        Args:
            db: An initialized Database instance.
            booking_workflow: Optional existing BookingWorkflowService;
                one is created from ``db`` if not provided.
            history_service: Optional HistoryService; created from
                ``db`` if not provided.
            pnr_service: Optional PnrService; created from ``db`` if
                not provided.
            ticket_service: Optional TicketService; created from
                ``db`` if not provided.
            account_service: Optional IrctcAccountService.
        """
        super().__init__()
        self._db = db
        self._workflow = booking_workflow or BookingWorkflowService(
            db=db,
            history_service=history_service,
            pnr_service=pnr_service,
            ticket_service=ticket_service,
            account_service=account_service,
        )

        # Per-ticket worker execution contexts:
        # ticket_id -> {worker_tag: {method, state, session, ...}}
        self._executions: dict[str, dict[str, dict]] = {}

        # Wire workflow signals to execution-level signals.
        self._workflow.state_changed.connect(self._on_workflow_state_changed)
        self._workflow.booking_completed.connect(self._on_workflow_completed)
        self._workflow.booking_failed.connect(self._on_workflow_failed)
        self._workflow.booking_cancelled.connect(self._on_workflow_cancelled)

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------

    @property
    def workflow(self) -> BookingWorkflowService:
        """Return the underlying BookingWorkflowService."""
        return self._workflow

    @property
    def state(self) -> BookingState:
        """Return the current workflow state."""
        return self._workflow.state

    @property
    def is_active(self) -> bool:
        """Return True if a session is in a non-terminal state."""
        return self._workflow.is_active

    def supported_workers(self) -> frozenset[str]:
        """Return the set of supported worker tags."""
        return SUPPORTED_WORKERS

    def method_for_worker(self, worker_tag: str) -> str:
        """Return the execution method for a worker tag.

        Args:
            worker_tag: The TicketPanelWindow worker button label
                (e.g. "@ W2", "🛡️ W3", "0 W5", "🚀 W6", "🌀 APP").

        Returns:
            The execution method string (edge, brave, opera, comet, app).

        Raises:
            WorkerNotSupportedError: If the worker tag is unknown.
        """
        if worker_tag not in WORKER_METHODS:
            raise WorkerNotSupportedError(
                f"Unsupported worker tag: {worker_tag!r}. "
                f"Supported: {sorted(WORKER_METHODS)}"
            )
        return WORKER_METHODS[worker_tag]

    def worker_for_method(self, method: str) -> str:
        """Return the worker tag for an execution method."""
        if method not in METHOD_TO_WORKER:
            raise WorkerNotSupportedError(
                f"Unsupported execution method: {method!r}. "
                f"Supported: {sorted(METHOD_TO_WORKER)}"
            )
        return METHOD_TO_WORKER[method]

    def get_execution_context(
        self, ticket_id: str, worker_tag: str
    ) -> Optional[dict]:
        """Return the execution context for a ticket+worker, or None."""
        return self._executions.get(ticket_id, {}).get(worker_tag)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_execution(
        self,
        ticket_id: str,
        worker_tag: str,
        irctc_account_id: Optional[str] = None,
    ) -> dict:
        """Begin a booking execution for a ticket with a specific worker.

        Validates the worker tag, then delegates to the underlying
        BookingWorkflowService.start_session(). Each ticket+worker
        combination gets its own execution context.

        Args:
            ticket_id: The ticket UUID to book.
            worker_tag: The worker button label
                (e.g. "@ W2", "🛡️ W3", "0 W5", "🚀 W6", "🌀 APP").
            irctc_account_id: Optional IRCTC account UUID override.

        Returns:
            The session context dictionary.

        Raises:
            WorkerNotSupportedError: If the worker tag is unknown.
            InvalidTransitionError: If a session is already active.
            BookingSessionError: If the ticket/account cannot be resolved.
        """
        method = self.method_for_worker(worker_tag)

        # Delegate to the workflow service (enforces single active session).
        session = self._workflow.start_session(
            ticket_id=ticket_id,
            irctc_account_id=irctc_account_id,
        )

        # Record per-worker execution context.
        if ticket_id not in self._executions:
            self._executions[ticket_id] = {}
        self._executions[ticket_id][worker_tag] = {
            "method": method,
            "worker_tag": worker_tag,
            "ticket_id": ticket_id,
            "state": self._workflow.state,
            "session": session,
            "pnr": None,
        }

        self.event_emitted.emit(
            "execution_started",
            f"Execution started: ticket={ticket_id}, worker={worker_tag} "
            f"({method})",
        )
        self.execution_started.emit(ticket_id, worker_tag)
        self.worker_state_changed.emit(
            ticket_id, worker_tag, self._workflow.state.value
        )
        return session

    # ------------------------------------------------------------------
    # Checkpoints (user-driven, delegated to workflow)
    # ------------------------------------------------------------------

    def reach_login_checkpoint(self) -> None:
        """Advance to the 2FA checkpoint."""
        self._workflow.reach_login_checkpoint()
        self._emit_worker_state()

    def submit_manual_2fa(self, otp_code: str) -> None:
        """Submit a manually-entered 2FA/OTP code."""
        self._workflow.submit_manual_2fa(otp_code)
        self._emit_worker_state()

    def submit_manual_captcha(self, captcha_text: str) -> None:
        """Submit a manually-entered CAPTCHA answer."""
        self._workflow.submit_manual_captcha(captcha_text)
        self._emit_worker_state()

    def confirm_fare(self, confirmed: bool) -> None:
        """Confirm or reject the fare shown to the user."""
        self._workflow.confirm_fare(confirmed)
        self._emit_worker_state()

    def confirm_payment(
        self, pnr: str, fare_amount: Optional[float] = None
    ) -> dict:
        """Confirm payment completion and persist the booking."""
        # Capture ticket/worker context before workflow clears its session.
        ticket_id = self._current_ticket_id()
        worker_tag = self._current_worker_tag(ticket_id)

        result = self._workflow.confirm_payment(pnr, fare_amount)
        self._emit_worker_state()

        # Update per-worker execution contexts with the PNR.
        pnr_clean = pnr.strip()
        for contexts in self._executions.values():
            for ctx in contexts.values():
                ctx["pnr"] = pnr_clean

        if ticket_id and worker_tag:
            self.execution_completed.emit(ticket_id, worker_tag, pnr_clean)

        return result

    def cancel(self) -> None:
        """Cancel the active booking execution."""
        ticket_id = self._current_ticket_id()
        worker_tag = self._current_worker_tag(ticket_id)
        self._workflow.cancel()
        self._emit_worker_state()
        if ticket_id and worker_tag:
            self.execution_cancelled.emit(ticket_id, worker_tag)

    def fail(self, reason: str) -> None:
        """Mark the active booking as failed with a reason."""
        ticket_id = self._current_ticket_id()
        worker_tag = self._current_worker_tag(ticket_id)
        self._workflow.fail(reason)
        self._emit_worker_state()
        if ticket_id and worker_tag:
            self.execution_failed.emit(ticket_id, worker_tag, reason)

    def reset(self) -> None:
        """Force the workflow back to IDLE and clear all sessions."""
        self._workflow.reset()
        self._executions.clear()
        self.event_emitted.emit("execution_reset", "All execution contexts cleared.")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _current_ticket_id(self) -> Optional[str]:
        """Return the ticket ID from the current workflow session."""
        session = self._workflow.session
        return session.get("ticket_id") if session else None

    def _current_worker_tag(self, ticket_id: Optional[str] = None) -> Optional[str]:
        """Return the worker tag for the current execution, if any."""
        if ticket_id is None:
            ticket_id = self._current_ticket_id()
        if ticket_id and ticket_id in self._executions:
            contexts = self._executions[ticket_id]
            if contexts:
                # Return the first (most recent) worker tag.
                return next(iter(contexts))
        return None

    def _emit_worker_state(self) -> None:
        """Emit worker_state_changed for all active execution contexts."""
        ticket_id = self._current_ticket_id()
        if not ticket_id:
            return
        contexts = self._executions.get(ticket_id, {})
        new_state = self._workflow.state.value
        for worker_tag, ctx in contexts.items():
            ctx["state"] = new_state
            self.worker_state_changed.emit(ticket_id, worker_tag, new_state)

    def _on_workflow_state_changed(self, old_state: str, new_state: str) -> None:
        """Forward workflow state changes to execution-level signal."""
        self.event_emitted.emit(
            "state_changed", f"{old_state} -> {new_state}"
        )
        self._emit_worker_state()

    def _on_workflow_completed(self, pnr: str) -> None:
        """Handle workflow completion."""
        ticket_id = self._current_ticket_id()
        worker_tag = self._current_worker_tag(ticket_id)
        self.event_emitted.emit(
            "payment_confirmed", f"Payment confirmed. PNR {pnr} persisted."
        )
        if ticket_id and worker_tag:
            self.execution_completed.emit(ticket_id, worker_tag, pnr)

    def _on_workflow_failed(self, reason: str) -> None:
        """Handle workflow failure."""
        ticket_id = self._current_ticket_id()
        worker_tag = self._current_worker_tag(ticket_id)
        self.event_emitted.emit("failed", f"Booking failed: {reason}")
        if ticket_id and worker_tag:
            self.execution_failed.emit(ticket_id, worker_tag, reason)

    def _on_workflow_cancelled(self) -> None:
        """Handle workflow cancellation."""
        ticket_id = self._current_ticket_id()
        worker_tag = self._current_worker_tag(ticket_id)
        self.event_emitted.emit("cancelled", "Booking cancelled by user.")
        if ticket_id and worker_tag:
            self.execution_cancelled.emit(ticket_id, worker_tag)
