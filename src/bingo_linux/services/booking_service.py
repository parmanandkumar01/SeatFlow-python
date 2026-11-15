"""Booking workflow state machine and service layer.

Implements the legitimate, user-controlled subset of the original
6-stage booking lifecycle recovered during Task 9B-2. This service
coordinates state transitions for a manual, user-driven booking flow.

Strictly excluded (never implemented here):
- Automated CAPTCHA solving / ML CAPTCHA recognition.
- Anti-bot circumvention, cookie or ``sensor_data`` replay.
- Token harvesting or automated login.
- Anti-detect browser automation.

All verification checkpoints (CAPTCHA, 2FA, fare, payment/PNR) are
user-driven. The service exposes Qt signals so the UI can react to
state changes and prompt the user at each checkpoint.

State machine (see :class:`BookingState`):

    IDLE
      -> IN_PROGRESS            (start_session)
      -> WAITING_FOR_2FA        (reached login checkpoint)
      -> WAITING_FOR_CAPTCHA    (2FA accepted)
      -> PAYMENT                (captcha + fare accepted)
      -> COMPLETED              (payment confirmed with PNR)
      -> FAILED                 (error during any stage)
      -> CANCELLED              (user cancels)

Only :data:`_ALLOWED_TRANSITIONS` are permitted; any other transition
raises :class:`InvalidTransitionError`.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from PySide6.QtCore import QObject, Signal

from bingo_linux.database.database import Database
from bingo_linux.services.history_service import HistoryService
from bingo_linux.services.irctc_account_service import IrctcAccountService
from bingo_linux.services.pnr_service import PnrService
from bingo_linux.services.ticket_service import TicketService


class BookingState(str, Enum):
    """Lifecycle states for a manual booking workflow.

    Values are lowercase strings to match the original renderer's
    ``booking:status`` state names where applicable (idle,
    in-progress, waiting-for-2fa, waiting-for-captcha, payment,
    completed, failed, cancelled).
    """

    IDLE = "idle"
    IN_PROGRESS = "in-progress"
    WAITING_FOR_2FA = "waiting-for-2fa"
    WAITING_FOR_CAPTCHA = "waiting-for-captcha"
    PAYMENT = "payment"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: Allowed state transitions. Keys are source states; values are the
#: set of states reachable directly from that source.
_ALLOWED_TRANSITIONS: dict[BookingState, set[BookingState]] = {
    BookingState.IDLE: {BookingState.IN_PROGRESS},
    BookingState.IN_PROGRESS: {
        BookingState.WAITING_FOR_2FA,
        BookingState.FAILED,
        BookingState.CANCELLED,
    },
    BookingState.WAITING_FOR_2FA: {
        BookingState.WAITING_FOR_CAPTCHA,
        BookingState.FAILED,
        BookingState.CANCELLED,
    },
    BookingState.WAITING_FOR_CAPTCHA: {
        BookingState.PAYMENT,
        BookingState.FAILED,
        BookingState.CANCELLED,
    },
    BookingState.PAYMENT: {
        BookingState.COMPLETED,
        BookingState.FAILED,
        BookingState.CANCELLED,
    },
    # Terminal states have no outgoing transitions.
    BookingState.COMPLETED: set(),
    BookingState.FAILED: set(),
    BookingState.CANCELLED: set(),
}


class BookingWorkflowError(Exception):
    """Base exception for booking workflow errors."""


class InvalidTransitionError(BookingWorkflowError):
    """Raised when a state transition is not permitted."""


class BookingSessionError(BookingWorkflowError):
    """Raised when there is no active session for an operation."""


class InvalidCheckpointError(BookingWorkflowError):
    """Raised when a checkpoint value fails validation."""


class BookingWorkflowService(QObject):
    """Coordinates a manual, user-driven booking workflow.

    The service owns the current :class:`BookingState` and enforces
    the transition rules. It never performs any network I/O, CAPTCHA
    solving, or credential handling; it only records state and, on
    completion, persists the booking via :class:`HistoryService` and
    :class:`PnrService`.

    Signals
    -------
    state_changed(str, str)
        Emitted with ``(old_state, new_state)`` on every valid
        transition.
    waiting_for_2fa()
        Emitted when the flow reaches the 2FA checkpoint.
    waiting_for_captcha()
        Emitted when the flow reaches the CAPTCHA checkpoint.
    waiting_for_fare_confirmation()
        Emitted when the flow reaches the fare confirmation checkpoint.
    booking_completed(str)
        Emitted with the PNR number when a booking completes.
    booking_failed(str)
        Emitted with an error message when a booking fails.
    booking_cancelled()
        Emitted when a booking is cancelled.
    event_emitted(str, str)
        Emitted with ``(event_name, message)`` for each lifecycle
        event. Used by the booking monitor UI to render a timestamped
        status log.
    """

    state_changed = Signal(str, str)
    waiting_for_2fa = Signal()
    waiting_for_captcha = Signal()
    waiting_for_fare_confirmation = Signal()
    booking_completed = Signal(str)
    booking_failed = Signal(str)
    booking_cancelled = Signal()
    event_emitted = Signal(str, str)

    def __init__(
        self,
        db: Database,
        history_service: Optional[HistoryService] = None,
        pnr_service: Optional[PnrService] = None,
        ticket_service: Optional[TicketService] = None,
        account_service: Optional[IrctcAccountService] = None,
    ) -> None:
        """Initialize the booking workflow service.

        Args:
            db: An initialized Database instance.
            history_service: Optional HistoryService; one is created
                from ``db`` if not provided.
            pnr_service: Optional PnrService; one is created from
                ``db`` if not provided.
            ticket_service: Optional TicketService; one is created
                from ``db`` if not provided.
            account_service: Optional IrctcAccountService. Account
                existence is only validated when this is supplied; if
                it is None, account references are recorded without a
                lookup (the caller is responsible for account validity).
        """
        super().__init__()
        self._db = db
        self._history_service = history_service or HistoryService(db)
        self._pnr_service = pnr_service or PnrService(db)
        self._ticket_service = ticket_service or TicketService(db)
        self._account_service = account_service

        self._state: BookingState = BookingState.IDLE
        self._session: Optional[dict] = None

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------

    @property
    def state(self) -> BookingState:
        """Return the current booking state."""
        return self._state

    @property
    def session(self) -> Optional[dict]:
        """Return the active session context, or None if idle."""
        return self._session

    @property
    def is_active(self) -> bool:
        """Return True if a session is in a non-terminal, non-idle state."""
        return self._state not in (
            BookingState.IDLE,
            BookingState.COMPLETED,
            BookingState.FAILED,
            BookingState.CANCELLED,
        )

    @staticmethod
    def allowed_transitions() -> dict[BookingState, set[BookingState]]:
        """Return a copy of the allowed transition table."""
        return {k: set(v) for k, v in _ALLOWED_TRANSITIONS.items()}

    @staticmethod
    def can_transition(source: BookingState, target: BookingState) -> bool:
        """Return True if ``source -> target`` is permitted."""
        return target in _ALLOWED_TRANSITIONS.get(source, set())

    # ------------------------------------------------------------------
    # Transition primitives
    # ------------------------------------------------------------------

    def _transition(self, target: BookingState) -> None:
        """Perform a validated state transition and emit signals.

        Args:
            target: The desired new state.

        Raises:
            InvalidTransitionError: If the transition is not allowed.
        """
        if target not in _ALLOWED_TRANSITIONS.get(self._state, set()):
            raise InvalidTransitionError(
                f"Cannot transition from {self._state.value!r} to {target.value!r}."
            )
        old = self._state
        self._state = target
        self.state_changed.emit(old.value, target.value)
        self.event_emitted.emit(
            "state_changed", f"{old.value} -> {target.value}"
        )

        if target == BookingState.WAITING_FOR_2FA:
            self.event_emitted.emit("awaiting_2fa", "Waiting for manual OTP/2FA entry.")
            self.waiting_for_2fa.emit()
        elif target == BookingState.WAITING_FOR_CAPTCHA:
            self.event_emitted.emit(
                "awaiting_captcha", "Waiting for manual CAPTCHA entry."
            )
            self.waiting_for_captcha.emit()
        elif target == BookingState.PAYMENT:
            self.event_emitted.emit(
                "awaiting_fare", "Awaiting fare confirmation before payment."
            )
            self.waiting_for_fare_confirmation.emit()

    def reset(self) -> None:
        """Force the workflow back to IDLE and clear the session.

        This is an administrative reset used by the UI; it does not
        emit a transition (it bypasses the transition table) and does
        not persist anything.
        """
        self._state = BookingState.IDLE
        self._session = None

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(
        self,
        ticket_id: str,
        irctc_account_id: Optional[str] = None,
    ) -> dict:
        """Begin a manual booking session for an existing ticket.

        Validates the ticket (and optional account) exist, then moves
        the workflow from IDLE to IN_PROGRESS.

        Args:
            ticket_id: The ticket UUID to book.
            irctc_account_id: Optional IRCTC account UUID override. If
                omitted, the ticket's own ``irctc_account_id`` is used.

        Returns:
            The session context dictionary.

        Raises:
            InvalidTransitionError: If not currently IDLE.
            BookingSessionError: If the ticket/account cannot be resolved.
        """
        if self._state != BookingState.IDLE:
            raise InvalidTransitionError(
                "Cannot start a new session while one is active or finished; "
                "reset first."
            )

        ticket = self._ticket_service.get_ticket(ticket_id)

        account_id = irctc_account_id or ticket.get("irctc_account_id")
        if account_id and self._account_service is not None:
            # Validate the account exists (raises IrctcAccountNotFoundError).
            self._account_service.get_account(account_id)

        self._session = {
            "ticket_id": ticket_id,
            "irctc_account_id": account_id,
            "train_number": ticket.get("train_number"),
            "journey_date": ticket.get("journey_date"),
            "fare_amount": None,
            "pnr": None,
            "confirmed_fare": False,
        }
        self.event_emitted.emit(
            "session_started",
            f"Session started for train {ticket.get('train_number', '')} "
            f"on {ticket.get('journey_date', '')}.",
        )
        self._transition(BookingState.IN_PROGRESS)
        return self._session

    # ------------------------------------------------------------------
    # Checkpoints (user-driven)
    # ------------------------------------------------------------------

    def reach_login_checkpoint(self) -> None:
        """Advance to the 2FA checkpoint (user has begun login).

        Raises:
            InvalidTransitionError: If not currently IN_PROGRESS.
        """
        self._transition(BookingState.WAITING_FOR_2FA)

    def submit_manual_2fa(self, otp_code: str) -> None:
        """Submit a manually-entered 2FA/OTP code.

        The code is validated for presence only; it is never stored,
        logged, or transmitted by this service. On success the flow
        advances to the CAPTCHA checkpoint.

        Args:
            otp_code: The OTP/2FA code entered by the user.

        Raises:
            InvalidTransitionError: If not at the 2FA checkpoint.
            InvalidCheckpointError: If ``otp_code`` is empty.
        """
        if self._state != BookingState.WAITING_FOR_2FA:
            raise InvalidTransitionError(
                f"Cannot submit 2FA while in state {self._state.value!r}."
            )
        if not otp_code or not otp_code.strip():
            raise InvalidCheckpointError("OTP/2FA code must not be empty.")
        # Code intentionally discarded — no storage, no transmission.
        self.event_emitted.emit("2fa_submitted", "Manual 2FA/OTP accepted.")
        self._transition(BookingState.WAITING_FOR_CAPTCHA)

    def submit_manual_captcha(self, captcha_text: str) -> None:
        """Submit a manually-entered CAPTCHA answer.

        The text is validated for presence only; it is never stored,
        logged, or used for automated solving. On success the flow
        advances to the payment/fare-confirmation checkpoint.

        Args:
            captcha_text: The CAPTCHA text entered by the user.

        Raises:
            InvalidTransitionError: If not at the CAPTCHA checkpoint.
            InvalidCheckpointError: If ``captcha_text`` is empty.
        """
        if self._state != BookingState.WAITING_FOR_CAPTCHA:
            raise InvalidTransitionError(
                f"Cannot submit CAPTCHA while in state {self._state.value!r}."
            )
        if not captcha_text or not captcha_text.strip():
            raise InvalidCheckpointError("CAPTCHA text must not be empty.")
        # Text intentionally discarded — no storage, no automated solving.
        self.event_emitted.emit("captcha_submitted", "Manual CAPTCHA accepted.")
        self._transition(BookingState.PAYMENT)

    def confirm_fare(self, confirmed: bool) -> None:
        """Confirm (or reject) the fare shown to the user.

        Args:
            confirmed: True if the user accepts the fare, False to
                cancel the booking.

        Raises:
            InvalidTransitionError: If not at the fare/payment checkpoint.
        """
        if self._state != BookingState.PAYMENT:
            raise InvalidTransitionError(
                f"Cannot confirm fare while in state {self._state.value!r}."
            )
        if not confirmed:
            self.event_emitted.emit("fare_rejected", "Fare rejected; booking cancelled.")
            self._transition(BookingState.CANCELLED)
            self._session = None
            self.booking_cancelled.emit()
            return
        if self._session is not None:
            self._session["confirmed_fare"] = True
        self.event_emitted.emit("fare_confirmed", "Fare confirmed by user.")

    def confirm_payment(self, pnr: str, fare_amount: Optional[float] = None) -> dict:
        """Confirm payment completion and persist the booking.

        Moves the workflow from PAYMENT to COMPLETED, then persists a
        booking-history record (via :class:`HistoryService`) and a PNR
        record (via :class:`PnrService`).

        Args:
            pnr: The PNR number returned by IRCTC (user-entered).
            fare_amount: Optional fare amount; defaults to the amount
                recorded on the session if available.

        Returns:
            A dict with ``history_id`` and ``pnr_id`` of the persisted
            records.

        Raises:
            InvalidTransitionError: If not at the payment checkpoint.
            InvalidCheckpointError: If ``pnr`` is empty.
            BookingWorkflowError: If persistence fails.
        """
        if self._state != BookingState.PAYMENT:
            raise InvalidTransitionError(
                f"Cannot confirm payment while in state {self._state.value!r}."
            )
        if not pnr or not pnr.strip():
            raise InvalidCheckpointError("PNR number must not be empty.")

        pnr_clean = pnr.strip()
        session = self._session or {}
        ticket_id = session.get("ticket_id")
        account_id = session.get("irctc_account_id")
        train_number = session.get("train_number")
        journey_date = session.get("journey_date")
        resolved_fare = fare_amount if fare_amount is not None else session.get("fare_amount")

        history_id: Optional[str] = None
        pnr_id: Optional[str] = None

        try:
            # Persist PNR record first (must be unique).
            if not self._pnr_service.pnr_exists(pnr_clean):
                pnr_id = self._pnr_service.add_pnr(
                    pnr_number=pnr_clean,
                    train_number=train_number,
                    journey_date=journey_date,
                    booking_status="booked",
                    fare_amount=resolved_fare,
                )

            # Persist booking history.
            history_id = self._history_service.add_history(
                pnr_number=pnr_clean,
                train_number=train_number or "UNKNOWN",
                journey_date=journey_date or "",
                booking_status="success",
                fare_amount=resolved_fare if resolved_fare is not None else 0.0,
                ticket_id=ticket_id,
                irctc_account_id=account_id,
            )
        except Exception as exc:
            # Persistence failure is a workflow failure.
            self._transition(BookingState.FAILED)
            self._session = None
            self.event_emitted.emit("failed", f"Persistence error: {exc}")
            self.booking_failed.emit(str(exc))
            raise BookingWorkflowError(f"Failed to persist booking: {exc}") from exc

        self._transition(BookingState.COMPLETED)
        if self._session is not None:
            self._session["pnr"] = pnr_clean
        result = {"history_id": history_id, "pnr_id": pnr_id, "pnr": pnr_clean}
        self._session = None
        self.event_emitted.emit(
            "payment_confirmed", f"Payment confirmed. PNR {pnr_clean} persisted."
        )
        self.booking_completed.emit(pnr_clean)
        return result

    def cancel(self) -> None:
        """Cancel the active booking session.

        Raises:
            InvalidTransitionError: If the current state is terminal or
                idle (nothing to cancel).
        """
        if self._state in (
            BookingState.IDLE,
            BookingState.COMPLETED,
            BookingState.FAILED,
            BookingState.CANCELLED,
        ):
            raise InvalidTransitionError(
                f"Cannot cancel from state {self._state.value!r}."
            )
        self._transition(BookingState.CANCELLED)
        self._session = None
        self.event_emitted.emit("cancelled", "Booking cancelled by user.")
        self.booking_cancelled.emit()

    def fail(self, reason: str) -> None:
        """Mark the active booking as failed with a reason.

        Args:
            reason: Human-readable failure reason.

        Raises:
            InvalidTransitionError: If the current state is terminal or
                idle.
        """
        if self._state in (
            BookingState.IDLE,
            BookingState.COMPLETED,
            BookingState.FAILED,
            BookingState.CANCELLED,
        ):
            raise InvalidTransitionError(
                f"Cannot fail from state {self._state.value!r}."
            )
        self._transition(BookingState.FAILED)
        self._session = None
        self.event_emitted.emit("failed", f"Booking failed: {reason}")
        self.booking_failed.emit(reason)