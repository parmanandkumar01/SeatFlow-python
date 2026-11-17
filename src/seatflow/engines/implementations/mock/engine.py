"""Mock booking engine implementation for offline testing, UI verification, and rapid development."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from seatflow.engines.base import (
    BaseBookingEngine,
    EngineCapability,
    EngineConfig,
    EngineState,
    JourneyDetails,
    Passenger,
)
from seatflow.engines.events import (
    BookingCompletedEvent,
    CaptchaRequestedEvent,
    EngineErrorEvent,
    PaymentRequestedEvent,
    StatusChangedEvent,
    StepProgressEvent,
)
from seatflow.engines.registry import register_engine

logger = logging.getLogger(__name__)


@register_engine(
    engine_id="mock_engine",
    display_name="SeatFlow Simulated Mock Engine",
    description="Offline simulation engine for UI development and unit testing without network",
    version="1.0.0",
    capabilities=[
        EngineCapability.OFFLINE_MOCK,
        EngineCapability.AUTOFILL_FAST,
        EngineCapability.CAPTCHA_SOLVER_LOCAL,
    ],
    is_default=True,
)
class MockBookingEngine(BaseBookingEngine):
    """Simulated booking engine that walks through booking stages deterministically."""

    def __init__(self, engine_id: str = "mock_engine", name: str = "Mock Engine", capabilities: Optional[List[EngineCapability]] = None):
        super().__init__(
            engine_id=engine_id,
            name=name,
            capabilities=capabilities or [EngineCapability.OFFLINE_MOCK],
        )
        self._stopped = False
        self._paused = False
        self.step_delay: float = 0.05  # fast for tests, adjustable

    def prepare(
        self,
        journey: JourneyDetails,
        passengers: List[Passenger],
        account: Dict[str, Any],
        config: Optional[EngineConfig] = None,
    ) -> bool:
        self._journey = journey
        self._passengers = passengers
        self._account = account
        self._config = config or EngineConfig()
        self._stopped = False
        self._paused = False
        self.set_state(EngineState.READY)
        return True

    def start(self) -> None:
        if self._state not in (EngineState.READY, EngineState.IDLE):
            logger.warning("Mock engine started from state %s", self._state)

        self.set_state(EngineState.RUNNING)
        self._stopped = False

        steps = [
            ("INITIALIZE_SESSION", "Initializing browser and stealth session"),
            ("LOGIN_AUTHENTICATE", "Logging into IRCTC with credentials"),
            ("SEARCH_TRAIN", f"Searching train {self._journey.train_number if self._journey else '12301'}"),
            ("FILL_PASSENGERS", f"Filling {len(self._passengers)} passenger details"),
            ("REVIEW_BOOKING", "Reviewing booking summary and berth options"),
            ("PAYMENT_GATEWAY", "Initiating payment gateway handoff"),
            ("CONFIRM_PNR", "Verifying ticket confirmation and PNR generation"),
        ]

        total = len(steps)
        for idx, (step_name, desc) in enumerate(steps, start=1):
            if self._stopped:
                self.set_state(EngineState.STOPPED)
                return

            while self._paused and not self._stopped:
                time.sleep(0.05)

            if self._stopped:
                self.set_state(EngineState.STOPPED)
                return

            self.emit_event(
                StepProgressEvent(
                    engine_id=self.engine_id,
                    step_name=step_name,
                    current_step=idx,
                    total_steps=total,
                    description=desc,
                )
            )
            time.sleep(self.step_delay)

        # Complete booking
        pnr = "2847593021"
        train_no = self._journey.train_number if self._journey else "12301"
        fare = 1250.00
        self.set_state(EngineState.COMPLETED)
        self.emit_event(
            BookingCompletedEvent(
                engine_id=self.engine_id,
                pnr=pnr,
                train_number=train_no,
                booking_status="CONFIRMED",
                fare_paid=fare,
                ers_html=f"<html><body><h1>Ticket Confirmed</h1><p>PNR: {pnr}</p></body></html>",
            )
        )

    def pause(self) -> None:
        self._paused = True
        self.set_state(EngineState.PAUSED)

    def resume(self) -> None:
        self._paused = False
        self.set_state(EngineState.RUNNING)

    def stop(self, reason: str = "") -> None:
        self._stopped = True
        self.set_state(EngineState.STOPPED)

    def cleanup(self) -> None:
        self._stopped = True
        self.set_state(EngineState.IDLE)
