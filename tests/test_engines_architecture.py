"""Tests for the SeatFlow Multi-Engine Subsystem (Base, Registry, Events, Runner, and Mock)."""

import time
import pytest
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])

from seatflow.engines import (
    BaseBookingEngine,
    EngineCapability,
    EngineConfig,
    EngineRegistry,
    EngineState,
    EngineWorker,
    JourneyDetails,
    Passenger,
    StatusChangedEvent,
    StepProgressEvent,
    BookingCompletedEvent,
    register_engine,
)
from seatflow.engines.implementations.mock.engine import MockBookingEngine


def test_engine_worker_qt_bridge():
    """Test EngineWorker background execution and Qt signal dispatch."""
    app = _app

    """Verify that MockBookingEngine is automatically registered in EngineRegistry."""
    engines = EngineRegistry.list_engines()
    engine_ids = [e.engine_id for e in engines]
    assert "mock_engine" in engine_ids

    meta = next(e for e in engines if e.engine_id == "mock_engine")
    assert meta.display_name == "SeatFlow Simulated Mock Engine"
    assert EngineCapability.OFFLINE_MOCK in meta.capabilities
    assert meta.is_default is True


def test_create_engine_factory():
    """Test creating an engine instance via EngineRegistry factory."""
    engine = EngineRegistry.create_engine("mock_engine")
    assert isinstance(engine, BaseBookingEngine)
    assert isinstance(engine, MockBookingEngine)
    assert engine.engine_id == "mock_engine"
    assert engine.state == EngineState.IDLE


def test_custom_engine_registration():
    """Test registering a dynamic custom engine via decorator."""
    @register_engine(
        engine_id="test_custom_engine",
        display_name="Test Custom Engine",
        version="2.0.0",
        capabilities=[EngineCapability.DIRECT_API],
    )
    class CustomTestEngine(BaseBookingEngine):
        def prepare(self, journey, passengers, account, config=None):
            return True

        def start(self):
            pass

        def pause(self):
            pass

        def resume(self):
            pass

        def stop(self, reason=""):
            pass

        def cleanup(self):
            pass

    engine_class = EngineRegistry.get_engine_class("test_custom_engine")
    assert engine_class is CustomTestEngine
    created = EngineRegistry.create_engine("test_custom_engine")
    assert isinstance(created, CustomTestEngine)


def test_mock_engine_lifecycle():
    """Test MockBookingEngine execution and event emission."""
    engine = MockBookingEngine()
    events_received = []

    def on_event(ev):
        events_received.append(ev)

    engine.add_event_listener(on_event)

    journey = JourneyDetails(
        train_number="12301",
        train_name="Rajdhani Express",
        from_station="NDLS",
        to_station="HWH",
        journey_date="2026-11-20",
        travel_class="3A",
    )
    passengers = [Passenger(name="Rahul Kumar", age=30, gender="M")]
    account = {"username": "user123"}

    # Prepare
    ok = engine.prepare(journey=journey, passengers=passengers, account=account)
    assert ok is True
    assert engine.state == EngineState.READY

    # Run
    engine.step_delay = 0.001  # ultra fast for unit test
    engine.start()

    assert engine.state == EngineState.COMPLETED

    step_events = [e for e in events_received if isinstance(e, StepProgressEvent)]
    assert len(step_events) >= 7

    completion_events = [e for e in events_received if isinstance(e, BookingCompletedEvent)]
    assert len(completion_events) == 1
    assert completion_events[0].pnr == "2847593021"


def test_engine_worker_qt_bridge():
    """Test EngineWorker background execution and Qt signal dispatch."""
    engine = MockBookingEngine()
    engine.step_delay = 0.001
    worker = EngineWorker(engine)

    emitted_steps = []
    emitted_statuses = []
    completion_data = []

    worker.step_progress.connect(lambda eid, cur, tot, desc: emitted_steps.append((cur, tot, desc)))
    worker.status_changed.connect(lambda eid, st: emitted_statuses.append(st))
    worker.booking_completed.connect(lambda eid, pnr, train, fare: completion_data.append((pnr, fare)))

    journey = JourneyDetails(
        train_number="12801",
        train_name="Purushottam Express",
        from_station="PURI",
        to_station="NDLS",
        journey_date="2026-11-25",
    )
    worker.prepare(journey=journey, passengers=[], account={})
    worker.start_in_background()

    # Wait for thread completion
    for _ in range(50):
        _app.processEvents()
        if not worker.is_running:
            break
        time.sleep(0.02)

    _app.processEvents()

    assert len(emitted_statuses) > 0
    assert len(emitted_steps) >= 7
    assert len(completion_data) == 1
    assert completion_data[0][0] == "2847593021"
    worker.cleanup()
