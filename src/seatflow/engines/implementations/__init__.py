"""SeatFlow engine implementations package.

Engines placed in this directory are discovered and registered with EngineRegistry.
"""

from seatflow.engines.implementations.mock.engine import MockBookingEngine

__all__ = [
    "MockBookingEngine",
]
