"""Chrome worker process and isolated user profile management.

Each :class:`ChromeWorker` binds one visible Chrome/Chromium instance to a
single booking ticket. Workers are user-controlled: Chrome is launched only on
explicit ``Start`` (never at startup), navigates to the official IRCTC booking
URL, and is terminated on ``Stop`` / app exit.

A dedicated, randomly-named Chrome user-data directory is created per worker
under ``~/.local/share/SeatFlow/chrome_profiles/`` (mode 0700). Profile
directories persist for the worker's lifetime so the user does not re-login on
every stop/start, and are cleaned up by an explicit reset/uninstall.

No credentials, cookies, or session data are stored or transmitted by this
module. Chrome automation (form filling, headless driving, CAPTCHA solving) is
not performed.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import uuid
from enum import Enum
from typing import Optional

IRCTC_BOOKING_URL = "https://www.irctc.co.in/ntrain/train"

# Chrome flags that keep the window visible and user-controlled while
# minimising background network chatter. No headless, no automation, no
# credential handling flags are added.
_CHROME_FLAGS = [
    "--new-window",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-sync",
]


class WorkerState(str, Enum):
    """Per-worker state machine (MW-04).

    idle        - worker created, not running
    launching   - Chrome process being started
    ready       - Chrome window open on IRCTC booking page
    awaiting_2fa - user-assisted 2FA checkpoint in progress
    awaiting_captcha - user-assisted CAPTCHA checkpoint in progress
    payment      - user-assisted payment/PNR checkpoint in progress
    completed   - booking completed (terminal)
    failed      - worker failed to launch or run (terminal)
    cancelled   - user cancelled the worker (terminal)
    """

    IDLE = "idle"
    LAUNCHING = "launching"
    READY = "ready"
    AWAITING_2FA = "awaiting_2fa"
    AWAITING_CAPTCHA = "awaiting_captcha"
    PAYMENT = "payment"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATES = frozenset(
    {
        WorkerState.COMPLETED,
        WorkerState.FAILED,
        WorkerState.CANCELLED,
    }
)

# Common Chrome/Chromium binary locations on Linux.
_CHROME_CANDIDATES = [
    "google-chrome-stable",
    "google-chrome",
    "chromium",
    "chromium-browser",
    "chrome",
]


class ChromeWorkerError(Exception):
    """Raised for Chrome worker lifecycle errors."""


class ChromeWorker:
    """One visible Chrome instance bound to a single ticket."""

    def __init__(
        self,
        ticket_id: str,
        chrome_binary: str,
        profiles_dir: str,
    ) -> None:
        self.ticket_id = ticket_id
        self.chrome_binary = chrome_binary
        self.profiles_dir = profiles_dir
        self.profile_dir: Optional[str] = None
        self.process: Optional[subprocess.Popen] = None
        self._state = WorkerState.IDLE
        self._log: list[str] = []
        self._lock = threading.Lock()
        self._pid: Optional[int] = None
        self._started_at: Optional[float] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> WorkerState:
        with self._lock:
            return self._state

    @property
    def pid(self) -> Optional[int]:
        return self._pid

    @property
    def log(self) -> list[str]:
        return list(self._log)

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_event(self, message: str) -> None:
        with self._lock:
            self._log.append(message)
        if len(self._log) > 500:
            with self._lock:
                self._log = self._log[-500:]

    # ------------------------------------------------------------------
    # Profile directory
    # ------------------------------------------------------------------

    def _profile_dir_path(self) -> str:
        if self.profile_dir is None:
            self.profile_dir = os.path.join(
                self.profiles_dir, f"worker_{uuid.uuid4().hex[:12]}"
            )
            os.makedirs(self.profile_dir, mode=0o700, exist_ok=True)
        return self.profile_dir

    def remove_profile(self) -> None:
        """Remove this worker's profile directory (cleanup/reset)."""
        if self.profile_dir is None:
            return
        try:
            if os.path.isdir(self.profile_dir):
                shutil.rmtree(self.profile_dir, ignore_errors=True)
        except OSError:
            pass
        self.profile_dir = None

    # ------------------------------------------------------------------
    # Chrome binary resolution
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_chrome_binary(configured: str = "") -> str:
        """Resolve a Chrome/Chromium binary path.

        Order: configured path -> standard Linux names -> PATH lookup.
        Returns the first executable found, or the configured value if none.
        """
        if configured and os.path.isfile(configured) and os.access(configured, os.X_OK):
            return configured
        for name in _CHROME_CANDIDATES:
            found = shutil.which(name)
            if found:
                return found
        return configured or ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch Chrome on the IRCTC booking page (user-controlled, visible)."""
        if self.is_running:
            self._log_event("worker already running")
            return
        if self.state in TERMINAL_STATES:
            # Allow restarting from a terminal state by resetting.
            self._state = WorkerState.IDLE

        self._set_state(WorkerState.LAUNCHING)
        binary = self.resolve_chrome_binary(self.chrome_binary)
        if not binary:
            self._set_state(WorkerState.FAILED)
            self._log_event("failed to start: no Chrome/Chromium binary found")
            raise ChromeWorkerError("No Chrome/Chromium binary found")

        profile_dir = self._profile_dir_path()
        args = [
            binary,
            f"--user-data-dir={profile_dir}",
            *_CHROME_FLAGS,
            IRCTC_BOOKING_URL,
        ]

        self._log_event(f"launching Chrome (profile={profile_dir})")
        try:
            self.process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._pid = self.process.pid
            self._started_at = __import__("time").time()
            # Brief settle: confirm the process did not immediately exit.
            import time as _time

            _time.sleep(0.25)
            if self.process.poll() is not None:
                rc = self.process.returncode
                self._set_state(WorkerState.FAILED)
                self._log_event(f"Chrome exited immediately with code {rc}")
                raise ChromeWorkerError(f"Chrome exited immediately (code {rc})")
            self._set_state(WorkerState.READY)
            self._log_event("Chrome ready on IRCTC booking page")
        except FileNotFoundError as exc:
            self._set_state(WorkerState.FAILED)
            self._log_event(f"failed to start: {exc}")
            raise ChromeWorkerError(f"Chrome binary not executable: {binary}") from exc
        except ChromeWorkerError:
            raise
        except OSError as exc:
            self._set_state(WorkerState.FAILED)
            self._log_event(f"failed to start: {exc}")
            raise ChromeWorkerError(str(exc)) from exc

    def stop(self, terminate_children: bool = True) -> None:
        """Terminate the Chrome process for this worker.

        The profile directory is kept (bound to the worker/ticket) so the
        session persists across stops.
        """
        if self.process is None:
            self._set_state(WorkerState.IDLE)
            return
        if self.process.poll() is not None:
            self.process = None
            self._pid = None
            if self.state not in TERMINAL_STATES:
                self._set_state(WorkerState.IDLE)
            return

        self._log_event("stopping Chrome worker")
        try:
            if terminate_children and hasattr(os, "killpg") and self._pid is not None:
                try:
                    os.killpg(self._pid, signal.SIGTERM)
                except OSError:
                    self.process.terminate()
            else:
                self.process.terminate()
        except OSError:
            pass

        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                if terminate_children and hasattr(os, "killpg") and self._pid is not None:
                    os.killpg(self._pid, signal.SIGKILL)
                else:
                    self.process.kill()
                self.process.wait(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                self._log_event("Chrome did not terminate; process may remain")

        self.process = None
        self._pid = None
        if self.state not in TERMINAL_STATES:
            self._set_state(WorkerState.IDLE)
        self._log_event("Chrome worker stopped")

    # ------------------------------------------------------------------
    # State transitions driven by the booking workflow (user-assisted)
    # ------------------------------------------------------------------

    def set_state(self, state: WorkerState) -> None:
        """Externally set the worker state (e.g. synced from booking flow)."""
        self._set_state(state)

    def _set_state(self, state: WorkerState) -> None:
        if self._state == state:
            return
        old = self._state
        with self._lock:
            self._state = state
        self._log_event(f"state {old.value} -> {state.value}")


def booking_state_to_worker_state(state_str: str) -> Optional[WorkerState]:
    """Map a BookingWorkflowService state string to a WorkerState.

    Returns None when there is no meaningful mapping (worker keeps its
    current state).
    """
    mapping = {
        "IN_PROGRESS": WorkerState.READY,
        "WAITING_FOR_2FA": WorkerState.AWAITING_2FA,
        "WAITING_FOR_CAPTCHA": WorkerState.AWAITING_CAPTCHA,
        "PAYMENT": WorkerState.PAYMENT,
        "COMPLETED": WorkerState.COMPLETED,
        "FAILED": WorkerState.FAILED,
        "CANCELLED": WorkerState.CANCELLED,
        "IDLE": WorkerState.IDLE,
    }
    return mapping.get(state_str)
