"""Background runner and worker bridge connecting any engine to the PySide6 UI."""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from seatflow.engines.base import (
    BaseBookingEngine,
    EngineConfig,
    EngineState,
    JourneyDetails,
    Passenger,
)
from seatflow.engines.events import (
    BookingCompletedEvent,
    CaptchaRequestedEvent,
    EngineErrorEvent,
    EngineEvent,
    PaymentRequestedEvent,
    StatusChangedEvent,
    StepProgressEvent,
    TwoFactorRequestedEvent,
)

logger = logging.getLogger(__name__)


class EngineWorker(QObject):
    """Background execution runner for booking engines.
    
    Bridges asynchronous engine callbacks into thread-safe PySide6 Qt Signals
    so that the UI windows stay responsive, smooth, and easily decoupled.
    """

    # Qt Signals for UI bindings
    status_changed = Signal(str, str)  # (engine_id, new_status)
    step_progress = Signal(str, int, int, str)  # (engine_id, current_step, total_steps, description)
    captcha_requested = Signal(str, str, str, str)  # (engine_id, captcha_id, image_b64, prompt)
    two_factor_requested = Signal(str, str, str)  # (engine_id, transaction_id, mobile_mask)
    payment_requested = Signal(str, float, list, str)  # (engine_id, amount, options_list, instructions)
    booking_completed = Signal(str, str, str, float)  # (engine_id, pnr, train_number, fare)
    error_occurred = Signal(str, str, str)  # (engine_id, error_code, message)
    finished = Signal(str)  # (engine_id)

    def __init__(self, engine: BaseBookingEngine, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.engine = engine
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

        # Attach event listener to engine
        self.engine.add_event_listener(self._on_engine_event)

    @property
    def is_running(self) -> bool:
        """Whether the worker thread is active."""
        return self._is_running and (self._thread.is_alive() if self._thread else False)

    def prepare(
        self,
        journey: JourneyDetails,
        passengers: List[Passenger],
        account: Dict[str, Any],
        config: Optional[EngineConfig] = None,
    ) -> bool:
        """Prepare the engine for execution."""
        return self.engine.prepare(journey=journey, passengers=passengers, account=account, config=config)

    def start_in_background(self) -> None:
        """Spawn engine execution in a background worker thread."""
        if self.is_running:
            logger.warning("Engine '%s' is already running in background.", self.engine.engine_id)
            return

        self._is_running = True
        self._thread = threading.Thread(
            target=self._run_wrapper,
            name=f"EngineWorker-{self.engine.engine_id}",
            daemon=True,
        )
        self._thread.start()

    def _run_wrapper(self) -> None:
        """Internal worker thread target."""
        try:
            logger.info("EngineWorker started for engine '%s'", self.engine.engine_id)
            self.engine.start()
        except Exception as e:
            logger.exception("Uncaught exception in engine '%s': %s", self.engine.engine_id, e)
            self.error_occurred.emit(self.engine.engine_id, "UNCAUGHT_ENGINE_EXCEPTION", str(e))
        finally:
            self._is_running = False
            self.finished.emit(self.engine.engine_id)
            logger.info("EngineWorker finished for engine '%s'", self.engine.engine_id)

    def pause(self) -> None:
        """Pause engine execution."""
        self.engine.pause()

    def resume(self) -> None:
        """Resume engine execution."""
        self.engine.resume()

    def stop(self, reason: str = "Stopped by user") -> None:
        """Stop engine and clean up."""
        self.engine.stop(reason=reason)
        self._is_running = False

    def cleanup(self) -> None:
        """Clean up engine and detach listeners."""
        self.engine.remove_event_listener(self._on_engine_event)
        self.engine.cleanup()

    def _on_engine_event(self, event: EngineEvent) -> None:
        """Translate raw engine event dataclass to Qt Signal."""
        try:
            if isinstance(event, StatusChangedEvent):
                self.status_changed.emit(event.engine_id, event.new_status)
            elif isinstance(event, StepProgressEvent):
                self.step_progress.emit(event.engine_id, event.current_step, event.total_steps, event.description)
            elif isinstance(event, CaptchaRequestedEvent):
                self.captcha_requested.emit(event.engine_id, event.captcha_id, event.image_base64, event.prompt_text)
            elif isinstance(event, TwoFactorRequestedEvent):
                self.two_factor_requested.emit(event.engine_id, event.transaction_id, event.mobile_mask)
            elif isinstance(event, PaymentRequestedEvent):
                self.payment_requested.emit(event.engine_id, event.amount, event.payment_options, event.instructions)
            elif isinstance(event, BookingCompletedEvent):
                self.booking_completed.emit(event.engine_id, event.pnr, event.train_number, event.fare_paid)
            elif isinstance(event, EngineErrorEvent):
                self.error_occurred.emit(event.engine_id, event.error_code, event.message)
        except Exception as e:
            logger.error("Error dispatching engine event %s: %s", type(event).__name__, e)
