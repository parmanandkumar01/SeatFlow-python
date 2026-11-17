"""Base abstractions, contracts, and data models for SeatFlow booking engines."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class EngineState(str, Enum):
    """Lifecycle states of an execution engine."""
    IDLE = "idle"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_INPUT = "awaiting_input"
    AWAITING_CAPTCHA = "awaiting_captcha"
    AWAITING_2FA = "awaiting_2fa"
    AWAITING_PAYMENT = "awaiting_payment"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ERROR = "error"


class EngineCapability(str, Enum):
    """Capabilities supported by a specific engine implementation."""
    BROWSER_AUTOMATION = "browser_automation"
    DIRECT_API = "direct_api"
    HYBRID = "hybrid"
    CAPTCHA_SOLVER_LOCAL = "captcha_solver_local"
    CAPTCHA_SOLVER_MANUAL = "captcha_solver_manual"
    AUTOFILL_FAST = "autofill_fast"
    PAYMENT_AUTOMATION = "payment_automation"
    MULTI_SESSION = "multi_session"
    OFFLINE_MOCK = "offline_mock"


@dataclass
class Passenger:
    """Passenger details for ticket booking."""
    name: str
    age: int
    gender: str = "M"  # M, F, T
    berth_preference: str = "NONE"  # LB, MB, UB, SL, SU, WS, NONE
    senior_citizen: bool = False
    food_choice: str = "D"  # D (Default), V (Veg), N (Non-Veg)
    id_card_type: str = ""
    id_card_no: str = ""


@dataclass
class JourneyDetails:
    """Journey and train travel parameters."""
    train_number: str
    train_name: str
    from_station: str
    to_station: str
    journey_date: str  # YYYY-MM-DD or DD-MM-YYYY
    travel_class: str = "SL"  # 1A, 2A, 3A, 3E, CC, SL, 2S
    quota: str = "GN"  # GN, TQ (Tatkal), PT (Premium Tatkal), LD (Ladies)
    mobile_number: str = ""
    auto_upgrade: bool = False
    only_confirm: bool = False
    reservation_choice: str = "99"  # None / default
    gst_details: Dict[str, str] = field(default_factory=dict)


@dataclass
class EngineConfig:
    """Runtime configuration for an engine run."""
    headless: bool = False
    proxy_url: Optional[str] = None
    timeout_seconds: int = 120
    solve_captcha_automatically: bool = True
    manual_fallback_on_captcha: bool = True
    extra_options: Dict[str, Any] = field(default_factory=dict)


class BaseBookingEngine(abc.ABC):
    """Abstract base class that all SeatFlow booking engines must implement."""

    def __init__(self, engine_id: str, name: str, capabilities: List[EngineCapability] | None = None):
        self.engine_id = engine_id
        self.name = name
        self.capabilities: List[EngineCapability] = capabilities or []
        self._state: EngineState = EngineState.IDLE
        self._event_listeners: List[Callable[[Any], None]] = []
        self._journey: Optional[JourneyDetails] = None
        self._passengers: List[Passenger] = []
        self._account: Dict[str, Any] = {}
        self._config: EngineConfig = EngineConfig()

    @property
    def state(self) -> EngineState:
        """Current operational state."""
        return self._state

    def set_state(self, new_state: EngineState) -> None:
        """Update state and notify listeners."""
        old_state = self._state
        self._state = new_state
        from seatflow.engines.events import StatusChangedEvent
        self.emit_event(StatusChangedEvent(engine_id=self.engine_id, old_status=old_state.value, new_status=new_state.value))

    def add_event_listener(self, listener: Callable[[Any], None]) -> None:
        """Register a callback for engine events."""
        if listener not in self._event_listeners:
            self._event_listeners.append(listener)

    def remove_event_listener(self, listener: Callable[[Any], None]) -> None:
        """Remove a previously registered callback."""
        if listener in self._event_listeners:
            self._event_listeners.remove(listener)

    def emit_event(self, event: Any) -> None:
        """Dispatch event to all registered listeners."""
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception as e:
                pass

    @abc.abstractmethod
    def prepare(
        self,
        journey: JourneyDetails,
        passengers: List[Passenger],
        account: Dict[str, Any],
        config: Optional[EngineConfig] = None,
    ) -> bool:
        """Prepare engine with booking parameters and credentials before launch."""
        pass

    @abc.abstractmethod
    def start(self) -> None:
        """Start booking execution."""
        pass

    @abc.abstractmethod
    def pause(self) -> None:
        """Pause execution when waiting for user interaction."""
        pass

    @abc.abstractmethod
    def resume(self) -> None:
        """Resume execution after user interaction completes."""
        pass

    @abc.abstractmethod
    def stop(self, reason: str = "") -> None:
        """Gracefully stop or cancel execution."""
        pass

    @abc.abstractmethod
    def cleanup(self) -> None:
        """Release browser instances, network sessions, and temporary resources."""
        pass
