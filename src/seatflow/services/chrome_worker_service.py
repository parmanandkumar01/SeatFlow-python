"""Multi-worker Chrome profile manager (RT-05 / MW-01..MW-09).

Owns a pool of :class:`ChromeWorker` instances, each bound to a single
ticket and launched only on explicit user action. Provides Start, Stop,
Restart and Stop All, enforces the configured maximum concurrent workers,
and terminates every Chrome process on cleanup / app exit.

Emits Qt signals so the UI can surface per-worker state (MW-06).
"""

from __future__ import annotations

import os
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal

from seatflow.services.chrome_worker import (
    TERMINAL_STATES,
    ChromeWorker,
    ChromeWorkerError,
    WorkerState,
    booking_state_to_worker_state,
)
from seatflow.services.settings_service import (
    SETTING_CHROME_BINARY,
    SETTING_WORKER_COUNT,
    WORKER_COUNT_MAX,
    WORKER_COUNT_MIN,
)

# Default profile root: ~/.local/share/SeatFlow/chrome_profiles/ (MW-07).
DEFAULT_PROFILES_ROOT = os.path.join(
    os.path.expanduser("~"),
    ".local",
    "share",
    "SeatFlow",
    "chrome_profiles",
)

IRCTC_BOOKING_URL = "https://www.irctc.co.in/ntrain/train"


class ChromeWorkerServiceError(Exception):
    """Raised for Chrome worker service errors."""


class ChromeWorkerService(QObject):
    """Service managing isolated Chrome workers bound to tickets."""

    #: Emitted when a worker's state changes: (ticket_id, old_state, new_state).
    worker_state_changed = Signal(str, str, str)
    #: Emitted when a worker logs a message: (ticket_id, level, message).
    worker_logged = Signal(str, str, str)
    #: Emitted when a worker is started: (ticket_id,).
    worker_started = Signal(str)
    #: Emitted when a worker is stopped: (ticket_id,).
    worker_stopped = Signal(str)

    def __init__(
        self,
        settings_service,
        profiles_root: str = DEFAULT_PROFILES_ROOT,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings_service
        self._profiles_root = profiles_root
        self._workers: dict[str, ChromeWorker] = {}
        self._lock = __import__("threading").Lock()
        os.makedirs(self._profiles_root, mode=0o700, exist_ok=True)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @property
    def max_workers(self) -> int:
        return self._settings.get_worker_count()

    @property
    def chrome_binary(self) -> str:
        return self._settings.get_chrome_binary()

    @property
    def profiles_root(self) -> str:
        return self._profiles_root

    def set_max_workers(self, count: int) -> None:
        self._settings.set_worker_count(count)

    # ------------------------------------------------------------------
    # Worker accessors
    # ------------------------------------------------------------------

    def get_worker(self, ticket_id: str) -> Optional[ChromeWorker]:
        with self._lock:
            return self._workers.get(ticket_id)

    def list_workers(self) -> list[dict]:
        """Return a snapshot of all workers for UI display (MW-06)."""
        with self._lock:
            workers = list(self._workers.values())
        return [
            {
                "ticket_id": w.ticket_id,
                "state": w.state.value,
                "pid": w.pid,
                "is_running": w.is_running,
                "profile_dir": w.profile_dir,
                "log": w.log[-5:],
            }
            for w in workers
        ]

    def _active_count(self) -> int:
        return sum(1 for w in self._workers.values() if w.is_running)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_worker(self, ticket_id: str) -> bool:
        """Start (or resume) a Chrome worker for the given ticket.

        Returns True if the worker is running or was started; False if the
        maximum concurrent worker limit is reached.
        """
        with self._lock:
            existing = self._workers.get(ticket_id)
        if existing is not None:
            if existing.is_running:
                return True
            # Reuse the existing worker (keeps its profile).
            worker = existing
        else:
            if self._active_count() >= self.max_workers:
                self._log(ticket_id, "warning", "max concurrent workers reached")
                return False
            worker = ChromeWorker(
                ticket_id=ticket_id,
                chrome_binary=self.chrome_binary,
                profiles_dir=self._profiles_root,
            )
            with self._lock:
                self._workers[ticket_id] = worker

        old = worker.state
        try:
            worker.start()
        except ChromeWorkerError as exc:
            self._log(ticket_id, "error", str(exc))
            self._emit_state(ticket_id, old, WorkerState.FAILED.value)
            return False

        self._emit_state(ticket_id, old, WorkerState.READY.value)
        self._log(ticket_id, "info", "worker started")
        self.worker_started.emit(ticket_id)
        return True

    def stop_worker(self, ticket_id: str) -> bool:
        """Stop the Chrome worker for the given ticket."""
        worker = self._get_or_none(ticket_id)
        if worker is None:
            return False
        old = worker.state
        worker.stop()
        self._emit_state(ticket_id, old, WorkerState.IDLE.value)
        self._log(ticket_id, "info", "worker stopped")
        self.worker_stopped.emit(ticket_id)
        return True

    def restart_worker(self, ticket_id: str) -> bool:
        """Restart the Chrome worker for the given ticket."""
        worker = self._get_or_none(ticket_id)
        if worker is None:
            return self.start_worker(ticket_id)
        old = worker.state
        worker.stop()
        try:
            worker.start()
        except ChromeWorkerError as exc:
            self._log(ticket_id, "error", str(exc))
            self._emit_state(ticket_id, old, WorkerState.FAILED.value)
            return False
        self._emit_state(ticket_id, old, WorkerState.READY.value)
        self._log(ticket_id, "info", "worker restarted")
        self.worker_started.emit(ticket_id)
        return True

    def stop_all(self) -> None:
        """Stop every running Chrome worker (MW-05 global Stop All)."""
        with self._lock:
            workers = list(self._workers.values())
        for worker in workers:
            old = worker.state
            worker.stop()
            self._emit_state(worker.ticket_id, old, WorkerState.IDLE.value)
            self._log(worker.ticket_id, "info", "worker stopped (stop all)")
            self.worker_stopped.emit(worker.ticket_id)

    # ------------------------------------------------------------------
    # State sync from the booking workflow (user-assisted checkpoints)
    # ------------------------------------------------------------------

    def sync_worker_state(
        self, ticket_id: str, booking_state_str: str
    ) -> Optional[WorkerState]:
        """Map a booking workflow state to the worker state (MW-04).

        Without the Browser Extension Bridge, state advances via manual user
        confirmation in the desktop dialogs; this is called from the booking
        state-change handler.
        """
        target = booking_state_to_worker_state(booking_state_str)
        if target is None:
            return None
        worker = self._get_or_none(ticket_id)
        if worker is None:
            return None
        old = worker.state
        worker.set_state(target)
        self._emit_state(ticket_id, old, target.value)
        if target in TERMINAL_STATES:
            self._log(ticket_id, "info", f"worker reached terminal state: {target.value}")
        return target

    def cancel_worker(self, ticket_id: str) -> bool:
        """Cancel the worker for the given ticket (terminal)."""
        worker = self._get_or_none(ticket_id)
        if worker is None:
            return False
        old = worker.state
        worker.stop()
        worker.set_state(WorkerState.CANCELLED)
        self._emit_state(ticket_id, old, WorkerState.CANCELLED.value)
        self._log(ticket_id, "info", "worker cancelled")
        self.worker_stopped.emit(ticket_id)
        return True

    # ------------------------------------------------------------------
    # Cleanup (app exit / reset / uninstall)
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Terminate all workers and remove all profile directories (MW-07)."""
        self.stop_all()
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            worker.remove_profile()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_or_none(self, ticket_id: str) -> Optional[ChromeWorker]:
        with self._lock:
            return self._workers.get(ticket_id)

    def _emit_state(self, ticket_id: str, old: WorkerState, new: str) -> None:
        self.worker_state_changed.emit(ticket_id, old.value, new)

    def _log(self, ticket_id: str, level: str, message: str) -> None:
        worker = self._get_or_none(ticket_id)
        if worker is not None:
            worker._log_event(message)
        self.worker_logged.emit(ticket_id, level, message)

    def cleanup_profiles(self) -> None:
        """Alias for :meth:`cleanup` (kept for explicit reset/uninstall calls)."""
        self.cleanup()


# Backwards-compatible alias expected by some callers / docs.
ChromeWorkerManager = ChromeWorkerService
