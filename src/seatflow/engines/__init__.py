"""SeatFlow Pluggable Multi-Engine Subsystem.

Provides abstractions, registry, event bridge, and runners for orchestrating
multiple distinct booking automation engines.
"""

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
    EngineEvent,
    EngineEventType,
    PaymentRequestedEvent,
    StatusChangedEvent,
    StepProgressEvent,
    TwoFactorRequestedEvent,
)
from seatflow.engines.registry import (
    EngineMetadata,
    EngineRegistry,
    register_engine,
)
from seatflow.engines.runner import EngineWorker

__all__ = [
    # Base Abstractions
    "BaseBookingEngine",
    "EngineCapability",
    "EngineConfig",
    "EngineState",
    "JourneyDetails",
    "Passenger",
    # Events
    "EngineEvent",
    "EngineEventType",
    "StatusChangedEvent",
    "StepProgressEvent",
    "CaptchaRequestedEvent",
    "TwoFactorRequestedEvent",
    "PaymentRequestedEvent",
    "BookingCompletedEvent",
    "EngineErrorEvent",
    # Registry & Worker
    "EngineMetadata",
    "EngineRegistry",
    "register_engine",
    "EngineWorker",
]
