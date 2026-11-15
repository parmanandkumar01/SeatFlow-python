"""Application updater window matching update.html.

PyQt6 port of the original electron update.html:
- Frameless, stays-on-top window with SeatFlow branding
- Spinner -> status text -> progress bar -> sub-status lifecycle
- States: checking, downloading, installing, restarting
- Signals wired to Application for update flow control

PRIVACY (default-deny): This window is LOCAL-ONLY. It performs ZERO vendor
network calls. All update material must be a locally provided package
(selected and verified manually by the user). Remote update checks,
auto-download, vendor telemetry, and license pings are intentionally absent.
The signals below are UI state transitions only; they never trigger a network
request.
"""

from __future__ import annotations

import os
from typing import Literal, Optional

from PySide6.QtCore import QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from seatflow.ui.app_icon import apply_bingo_icon, bingo_logo_pixmap
from seatflow.ui.window_drag import enable_window_drag

UpdateState = Literal["checking", "downloading", "installing", "restarting", "completed", "failed"]

#: Default status text per state.
_STATE_STATUS_TEXT: dict[UpdateState, str] = {
    "checking": "Checking for updates…",
    "downloading": "Downloading update…",
    "installing": "Installing update…",
    "restarting": "Restarting…",
    "completed": "Up to date",
    "failed": "Update check failed",
}


class UpdateWindow(QWidget):
    """Updater window matching update.html layout and lifecycle."""

    checking = Signal()
    downloading = Signal()
    installing = Signal()
    restarting = Signal()
    completed = Signal()
    failed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("SeatFlow — Update")
        self.resize(420, 360)
        self.setMinimumWidth(340)
        self.setObjectName("updRoot")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._state: UpdateState = "checking"
        self._progress_value = 0
        self._progress_animation: Optional[QPropertyAnimation] = None
        #: Locally provided package path (manual selection only; zero network).
        self._local_package_path: Optional[str] = None

        self._setup_ui()
        self._setup_styles()
        enable_window_drag(self, self.header)

        # Apply initial state without emitting signals (window not yet shown).
        self.status_lbl.setText(_STATE_STATUS_TEXT["checking"])
        self.bar_wrap.setVisible(False)
        self.spinner.setVisible(True)
        self._spin_timer.start(50)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        self.card.setObjectName("updCard")
        self.card.setStyleSheet("""
            QFrame#updCard {
                background: #0c1e34;
                border: 1px solid #1e3a5f;
                border-radius: 0;
            }
        """)
        outer.addWidget(self.card)

        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        # ---- Header ----
        self.header = QFrame()
        self.header.setObjectName("updHeader")
        self.header.setFixedHeight(64)
        self.header.setStyleSheet("""
            QFrame#updHeader {
                background: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(124, 58, 237, 0.04), stop:1 transparent);
                border-bottom: 1px solid #1e3a5f;
            }
        """)
        header_lay = QHBoxLayout(self.header)
        header_lay.setContentsMargins(18, 14, 24, 14)
        header_lay.setSpacing(14)

        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedSize(40, 40)
        self.logo_lbl.setPixmap(bingo_logo_pixmap(40))
        self.logo_lbl.setScaledContents(True)
        header_lay.addWidget(self.logo_lbl)

        brand_col = QVBoxLayout()
        brand_col.setContentsMargins(0, 0, 0, 0)
        brand_col.setSpacing(2)

        self.brand_lbl = QLabel("BINGO")
        self.brand_lbl.setStyleSheet(
            "font-family: 'Rajdhani', 'Segoe UI', sans-serif; "
            "font-size: 20px; font-weight: 700; letter-spacing: 3px; "
            "color: #ffffff; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #0891b2, stop:0.5 #7c3aed, stop:1 #db2777); "
            "-webkit-background-clip: text; -webkit-text-fill-color: transparent; "
            "line-height: 1;"
        )
        brand_col.addWidget(self.brand_lbl)

        self.tagline_lbl = QLabel("Smart Software for Smart Users")
        self.tagline_lbl.setStyleSheet(
            "font-size: 10px; letter-spacing: 1.2px; text-transform: uppercase; "
            "color: #7c3aed; margin-top: 4px;"
        )
        brand_col.addWidget(self.tagline_lbl)

        header_lay.addLayout(brand_col, stretch=1)
        card_lay.addWidget(self.header)

        # ---- Body ----
        self.body = QFrame()
        self.body.setObjectName("updBody")
        self.body.setStyleSheet("background: transparent;")
        body_lay = QVBoxLayout(self.body)
        body_lay.setContentsMargins(24, 28, 24, 28)
        body_lay.setSpacing(16)
        body_lay.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        # Spinner
        self.spinner = QFrame()
        self.spinner.setObjectName("updSpinner")
        self.spinner.setFixedSize(30, 30)
        self.spinner.setStyleSheet("""
            QFrame#updSpinner {
                border: 3px solid #ede9fe;
                border-top-color: #7c3aed;
                border-radius: 15px;
            }
        """)
        body_lay.addWidget(self.spinner, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Spinner animation timer
        self._spin_angle = 0
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._tick_spin)
        self._spin_timer.start(50)

        # Title
        self.title_lbl = QLabel("Updater")
        self.title_lbl.setObjectName("updTitle")
        self.title_lbl.setStyleSheet(
            "font-family: 'Rajdhani', 'Segoe UI', sans-serif; font-size: 18px; "
            "font-weight: 700; letter-spacing: 0.5px; color: #e2e8f0;"
        )
        body_lay.addWidget(self.title_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Status
        self.status_lbl = QLabel("Checking for updates…")
        self.status_lbl.setObjectName("updStatus")
        self.status_lbl.setStyleSheet(
            "color: #94a3b8; font-size: 13px; line-height: 1.45; min-height: 18px;"
        )
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        body_lay.addWidget(self.status_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Progress bar (hidden by default)
        self.bar_wrap = QFrame()
        self.bar_wrap.setObjectName("updBarWrap")
        self.bar_wrap.setStyleSheet("background: transparent;")
        bar_lay = QVBoxLayout(self.bar_wrap)
        bar_lay.setContentsMargins(0, 0, 0, 0)
        bar_lay.setSpacing(4)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("updBar")
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar#updBar {
                background: #ede9fe;
                border: none;
                border-radius: 6px;
                text-align: center;
            }
            QProgressBar#updBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8b5cf6, stop:1 #5b21b6);
                border-radius: 6px;
            }
        """)
        bar_lay.addWidget(self.progress_bar)

        body_lay.addWidget(self.bar_wrap, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Sub-status
        self.sub_lbl = QLabel("")
        self.sub_lbl.setObjectName("updSub")
        self.sub_lbl.setStyleSheet(
            "color: #64748b; font-size: 11px; min-height: 14px; "
            "font-variant-numeric: tabular-nums; letter-spacing: 0.2px;"
        )
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        body_lay.addWidget(self.sub_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        card_lay.addWidget(self.body, stretch=1)

    def _setup_styles(self) -> None:
        self.setStyleSheet("QWidget#updRoot { background: transparent; }")

    # ------------------------------------------------------------------
    # Spinner animation
    # ------------------------------------------------------------------

    def _tick_spin(self) -> None:
        self._spin_angle = (self._spin_angle + 45) % 360
        self.spinner.update()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_state(
        self,
        state: UpdateState,
        status: Optional[str] = None,
        sub: Optional[str] = None,
        progress: Optional[int] = None,
    ) -> None:
        """Transition to a new update state.

        Args:
            state: New update state.
            status: Optional override for status text.
            sub: Optional sub-status text.
            progress: Optional progress value (0-100).
        """
        self._state = state

        # Emit state signal
        if state == "checking":
            self.checking.emit()
        elif state == "downloading":
            self.downloading.emit()
        elif state == "installing":
            self.installing.emit()
        elif state == "restarting":
            self.restarting.emit()
        elif state == "completed":
            self.completed.emit()
        elif state == "failed":
            self.failed.emit(status or "")

        # Update status text
        if status is not None:
            self.status_lbl.setText(status)
        else:
            self.status_lbl.setText(_STATE_STATUS_TEXT[state])

        # Update sub-status
        if sub is not None:
            self.sub_lbl.setText(sub)
        elif state == "checking":
            self.sub_lbl.setText("")
        elif state == "downloading":
            self.sub_lbl.setText("")
        elif state == "installing":
            self.sub_lbl.setText("")
        elif state == "restarting":
            self.sub_lbl.setText("")

        # Show/hide progress bar
        show_bar = state in ("downloading", "installing")
        self.bar_wrap.setVisible(show_bar)

        # Update progress
        if progress is not None:
            self.set_progress(progress)

        # Spinner: show for checking/downloading/installing, hide for others
        show_spinner = state in ("checking", "downloading", "installing")
        self.spinner.setVisible(show_spinner)
        if show_spinner and not self._spin_timer.isActive():
            self._spin_timer.start(50)
        elif not show_spinner:
            self._spin_timer.stop()

    def set_progress(self, value: int) -> None:
        """Set the progress bar value (0-100)."""
        self._progress_value = max(0, min(100, value))
        self.progress_bar.setValue(self._progress_value)

    def set_sub_status(self, text: str) -> None:
        """Set the sub-status text (e.g. download speed/ETA)."""
        self.sub_lbl.setText(text)

    def state(self) -> UpdateState:
        """Return the current update state."""
        return self._state

    def progress(self) -> int:
        """Return the current progress value."""
        return self._progress_value

    # ------------------------------------------------------------------
    # Local-only package handling (default-deny, zero vendor network)
    # ------------------------------------------------------------------

    def set_local_package(self, file_path: Optional[str]) -> None:
        """Record a locally provided update package for manual verification.

        Args:
            file_path: Absolute path to a locally provided package file, or
                None to clear the current selection. No network access is
                performed; only the path is stored.
        """
        self._local_package_path = file_path

    def local_package_path(self) -> Optional[str]:
        """Return the currently selected local package path, if any."""
        return self._local_package_path

    def verify_local_package(self) -> bool:
        """Verify the selected local package using local file I/O only.

        Performs zero network access. Verification is limited to existence,
        readability, and non-zero size of the locally provided package.

        Returns:
            True if a package is selected and passes local verification;
            False otherwise (transitions to failed state).
        """
        path = self._local_package_path
        if not path:
            self.mark_failed("No local package selected")
            return False
        try:
            if not os.path.exists(path):
                raise FileNotFoundError(path)
            if not os.path.isfile(path):
                raise IsADirectoryError(path)
            if os.path.getsize(path) <= 0:
                raise ValueError("empty package")
        except Exception as exc:  # noqa: BLE001 - surface verification failure
            self.mark_failed(f"Local verification failed: {exc}")
            return False
        self.mark_completed()
        return True

    # ------------------------------------------------------------------
    # Convenience lifecycle methods
    # ------------------------------------------------------------------

    def start_checking(self) -> None:
        """Begin checking for updates."""
        self.set_state("checking")

    def start_downloading(self) -> None:
        """Begin downloading the update."""
        self.set_state("downloading", progress=0)

    def update_download_progress(self, value: int, sub: Optional[str] = None) -> None:
        """Update download progress (0-100) and optional sub-status."""
        self.set_state("downloading", progress=value)
        if sub is not None:
            self.set_sub_status(sub)

    def start_installing(self) -> None:
        """Begin installing the update."""
        self.set_state("installing", progress=0)

    def start_restarting(self) -> None:
        """Begin restarting the application."""
        self.set_state("restarting")

    def mark_completed(self) -> None:
        """Mark the update cycle as completed."""
        self.set_state("completed", progress=100)

    def mark_failed(self, reason: str) -> None:
        """Mark the update cycle as failed with a reason."""
        self.set_state("failed", status=reason)