# SeatFlow Engine Implementations Directory

This directory is the home for all pluggable booking engines in SeatFlow.

## Architecture Overview

SeatFlow uses a pluggable multi-engine architecture. Each engine is an autonomous module that implements `BaseBookingEngine` and registers itself with `EngineRegistry`.

```
src/seatflow/engines/implementations/
├── __init__.py
├── mock/                     # Built-in offline testing engine
│   ├── __init__.py
│   └── engine.py
├── ocean_hybrid/             # (Example) Ocean Hybrid Browser + Direct API engine
│   ├── __init__.py
│   ├── engine.py
│   ├── api_client.py
│   ├── browser_bridge.py
│   └── autofill.py
├── playwright_direct/        # (Example) Pure Playwright automation engine
│   ├── __init__.py
│   └── engine.py
└── api_express/              # (Example) Pure REST API microsecond execution engine
    ├── __init__.py
    └── engine.py
```

---

## How to Add a New Engine in 3 Steps

### 1. Create a Folder for your Engine
Create a directory under `src/seatflow/engines/implementations/<your_engine_name>/`:
```bash
mkdir -p src/seatflow/engines/implementations/my_new_engine
touch src/seatflow/engines/implementations/my_new_engine/__init__.py
touch src/seatflow/engines/implementations/my_new_engine/engine.py
```

### 2. Implement `BaseBookingEngine` and Decorate with `@register_engine`
In `engine.py`:

```python
from seatflow.engines.base import BaseBookingEngine, EngineCapability, EngineConfig, EngineState, JourneyDetails, Passenger
from seatflow.engines.registry import register_engine
from seatflow.engines.events import StepProgressEvent, BookingCompletedEvent

@register_engine(
    engine_id="my_new_engine",
    display_name="My Ultra Fast Engine",
    description="High-speed booking automation using XYZ technology",
    version="1.0.0",
    capabilities=[
        EngineCapability.BROWSER_AUTOMATION,
        EngineCapability.CAPTCHA_SOLVER_LOCAL,
        EngineCapability.AUTOFILL_FAST,
    ],
    is_default=False,
)
class MyNewEngine(BaseBookingEngine):
    def prepare(self, journey: JourneyDetails, passengers: list[Passenger], account: dict, config: EngineConfig = None) -> bool:
        self._journey = journey
        self._passengers = passengers
        self._account = account
        self.set_state(EngineState.READY)
        return True

    def start(self) -> None:
        self.set_state(EngineState.RUNNING)
        # Execute your steps here...
        self.emit_event(StepProgressEvent(self.engine_id, "LOGIN", 1, 5, "Logging in..."))
        # When done:
        self.set_state(EngineState.COMPLETED)
        self.emit_event(BookingCompletedEvent(self.engine_id, pnr="1234567890", train_number=self._journey.train_number))

    def pause(self) -> None:
        self.set_state(EngineState.PAUSED)

    def resume(self) -> None:
        self.set_state(EngineState.RUNNING)

    def stop(self, reason: str = "") -> None:
        self.set_state(EngineState.STOPPED)

    def cleanup(self) -> None:
        pass
```

### 3. Expose in `implementations/__init__.py`
Import your engine class in `src/seatflow/engines/implementations/__init__.py`:
```python
from seatflow.engines.implementations.my_new_engine.engine import MyNewEngine

__all__ = [..., "MyNewEngine"]
```

That's it! SeatFlow will automatically discover your engine, list it in the UI engine selector, and route bookings through it.
