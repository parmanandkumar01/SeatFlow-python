"""Ticket pair / monitor card window matching real SeatFlow UI.

Matches Screenshot_2026-11-14-21-10-16-61 with pair number badge,
READY · STANDBY status banner, journey route, class/quota pills,
worker buttons (W2, W3, W5, W6, APP), availability pill, and live clock.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seatflow.services import BookingState
from seatflow.ui.app_icon import apply_bingo_icon
from seatflow.ui.window_drag import enable_window_drag


class TicketPanelWindow(QWidget):
    """Floating ticket pair / monitor card window matching official SeatFlow screenshot."""

    close_clicked = Signal(str, int)  # ticket_id, pair_index
    launch_worker = Signal(str, int, str)  # ticket_id, pair_index, worker_tag

    # Tatkal opening window: AC classes open at 10:00, Non-AC at 11:00.
    _TATKAL_HOUR_AC = 10
    _TATKAL_HOUR_NON_AC = 11
    _AC_CLASSES = frozenset({"1A", "2A", "3A", "CC", "EC"})

    def __init__(
        self,
        ticket: dict[str, Any],
        pair_index: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.ticket = ticket
        self.ticket_id = ticket.get("id", "")
        self.pair_index = pair_index

        self.setWindowTitle(f"Monitor - {ticket.get('train_number', '')}")
        self.resize(440, 460)
        self.setMinimumSize(420, 440)
        self.setObjectName("pairCardRoot")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self._setup_ui()
        self._setup_styles()
        self._load_ticket_data()
        enable_window_drag(self, self.head_frame)

        # Countdown to Tatkal opening (10:00 AC / 11:00 Non-AC).
        self._countdown_target = None
        self._countdown_active = False
        self.set_tatkal_countdown(self.ticket.get("class"))

        # Clock timer
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_clock)
        self._timer.start()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        main_card = QFrame()
        main_card.setObjectName("pairMainCard")
        lay = QVBoxLayout(main_card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 1. Header Frame
        self.head_frame = QFrame()
        self.head_frame.setObjectName("pairHead")
        self.head_frame.setFixedHeight(48)
        hl = QHBoxLayout(self.head_frame)
        hl.setContentsMargins(16, 8, 12, 8)
        hl.setSpacing(10)

        self.title_lbl = QLabel("hwh_sc_ssingh - 2")
        self.title_lbl.setObjectName("pairTitle")
        hl.addWidget(self.title_lbl)

        self.pair_pill = QLabel(f"PAIR {self.pair_index + 1}")
        self.pair_pill.setObjectName("pairPill")
        hl.addWidget(self.pair_pill)

        hl.addStretch(1)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("pairClose")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.clicked.connect(self._on_close)
        hl.addWidget(self.btn_close)

        lay.addWidget(self.head_frame)

        # 2. Status Banner (Cyan READY · STANDBY)
        self.banner = QFrame()
        self.banner.setObjectName("pairBanner")
        self.banner.setFixedHeight(34)
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(16, 0, 16, 0)
        self.banner_text = QLabel("READY · STANDBY")
        self.banner_text.setObjectName("pairBannerText")
        bl.addWidget(self.banner_text)
        lay.addWidget(self.banner)

        # 3. Card Body
        body = QWidget()
        body.setObjectName("pairBody")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(20, 16, 20, 16)
        body_lay.setSpacing(14)

        # Route Row: TRAIN NO   FROM → TO   DATE
        route_lay = QHBoxLayout()
        route_lay.setSpacing(14)

        self.train_no_lbl = QLabel("12703")
        self.train_no_lbl.setObjectName("routeTrainNo")
        route_lay.addWidget(self.train_no_lbl)

        self.from_lbl = QLabel("HWH")
        self.from_lbl.setObjectName("routeStation")
        route_lay.addWidget(self.from_lbl)

        arrow_lbl = QLabel("→")
        arrow_lbl.setStyleSheet("color: #7c3aed; font-size: 16px; font-weight: bold;")
        route_lay.addWidget(arrow_lbl)

        self.to_lbl = QLabel("SC")
        self.to_lbl.setObjectName("routeStation")
        route_lay.addWidget(self.to_lbl)

        route_lay.addStretch(1)

        self.date_lbl = QLabel("02-09-2026")
        self.date_lbl.setObjectName("routeDate")
        route_lay.addWidget(self.date_lbl)

        body_lay.addLayout(route_lay)

        # Badges & Account Row: [CLASS]  [QUOTA]  IRCTC ID
        badges_lay = QHBoxLayout()
        badges_lay.setSpacing(10)

        self.class_badge = QLabel("2A")
        self.class_badge.setObjectName("badgeClass")
        badges_lay.addWidget(self.class_badge)

        self.quota_badge = QLabel("TQ")
        self.quota_badge.setObjectName("badgeQuota")
        badges_lay.addWidget(self.quota_badge)

        badges_lay.addStretch(1)

        self.account_combo = QComboBox()
        self.account_combo.setObjectName("comboAccount")
        self.account_combo.setFixedWidth(140)
        badges_lay.addWidget(self.account_combo)

        body_lay.addLayout(badges_lay)

        # Settings Row: BANK, IP, QUOTA
        settings_lay = QHBoxLayout()
        settings_lay.setSpacing(8)

        # Bank
        bank_box = QVBoxLayout()
        bank_box.setSpacing(2)
        l_b = QLabel("BANK")
        l_b.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b;")
        self.bank_combo = QComboBox()
        self.bank_combo.addItems(["IPPAYUPI · ipay@upi", "PHONEPEQR · phonepe@ybl", "PAYTMQR"])
        bank_box.addWidget(l_b)
        bank_box.addWidget(self.bank_combo)
        settings_lay.addLayout(bank_box, stretch=2)

        # IP
        ip_box = QVBoxLayout()
        ip_box.setSpacing(2)
        l_i = QLabel("IP")
        l_i.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b;")
        self.ip_combo = QComboBox()
        self.ip_combo.addItems(["Home IP", "Proxy 1", "Proxy 2"])
        ip_box.addWidget(l_i)
        ip_box.addWidget(self.ip_combo)
        settings_lay.addLayout(ip_box, stretch=2)

        # Quota
        q_box = QVBoxLayout()
        q_box.setSpacing(2)
        l_q = QLabel("QUOTA")
        l_q.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b;")
        self.quota_combo = QComboBox()
        self.quota_combo.addItems(["TQ", "GN", "PT", "LD"])
        q_box.addWidget(l_q)
        q_box.addWidget(self.quota_combo)
        settings_lay.addLayout(q_box, stretch=1)

        body_lay.addLayout(settings_lay)

        # Workers Button Row: [@ W2]  [🛡️ W3]  [0 W5]  [🚀 W6]  [🌀 APP]
        worker_lay = QHBoxLayout()
        worker_lay.setSpacing(8)

        self.btn_w2 = self._make_worker_btn("@ W2", "#0284c7")
        self.btn_w3 = self._make_worker_btn("🛡️ W3", "#ea580c")
        self.btn_w5 = self._make_worker_btn("0 W5", "#dc2626")
        self.btn_w6 = self._make_worker_btn("🚀 W6", "#06b6d4")
        self.btn_app = self._make_worker_btn("🌀 APP", "#7c3aed")

        worker_lay.addWidget(self.btn_w2)
        worker_lay.addWidget(self.btn_w3)
        worker_lay.addWidget(self.btn_w5)
        worker_lay.addWidget(self.btn_w6)
        worker_lay.addWidget(self.btn_app)
        body_lay.addLayout(worker_lay)

        # BETA Checkbox
        beta_lay = QHBoxLayout()
        self.chk_beta = QCheckBox("BETA")
        self.chk_beta.setStyleSheet("color: #475569; font-weight: 700; font-size: 11px;")
        beta_lay.addStretch(1)
        beta_lay.addWidget(self.chk_beta)
        beta_lay.addStretch(1)
        body_lay.addLayout(beta_lay)

        lay.addWidget(body)

        # 4. Bottom Footer: [🟢 AVAILABLE-0016]  [09:42:40]
        footer = QFrame()
        footer.setObjectName("pairFooter")
        footer.setFixedHeight(50)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(18, 8, 18, 8)
        fl.setSpacing(14)

        self.avail_pill = QLabel("🟢  AVAILABLE-0016")
        self.avail_pill.setObjectName("pillAvail")
        fl.addWidget(self.avail_pill)

        fl.addStretch(1)

        self.clock_lbl = QLabel("00:00:00")
        self.clock_lbl.setObjectName("pairClock")
        fl.addWidget(self.clock_lbl)

        lay.addWidget(footer)
        root.addWidget(main_card)

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#pairCardRoot {
                background: transparent;
            }
            QFrame#pairMainCard {
                background: #091a2b;
                border: 1px solid #1e3a5f;
                border-radius: 12px;
            }
            QFrame#pairHead {
                background: #0c1e34;
                border-bottom: 1px solid #1e3a5f;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#pairTitle {
                color: #ffffff;
                font-size: 14px;
                font-weight: 800;
            }
            QLabel#pairPill {
                background: #f97316;
                color: #ffffff;
                font-size: 11px;
                font-weight: 800;
                padding: 2px 10px;
                border-radius: 10px;
            }
            QPushButton#pairClose {
                background: #0d1a28;
                color: #e8f4fa;
                border: 1px solid #1e3a5f;
                border-radius: 4px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton#pairClose:hover {
                background: #dc2626;
                border-color: #ef4444;
                color: #ffffff;
            }
            QFrame#pairBanner {
                background: #0284c7;
            }
            QLabel#pairBannerText {
                color: #ffffff;
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QLabel#routeTrainNo {
                color: #a78bfa;
                font-size: 16px;
                font-weight: 800;
            }
            QLabel#routeStation {
                color: #ffffff;
                font-size: 16px;
                font-weight: 800;
            }
            QLabel#routeDate {
                color: #38bdf8;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#badgeClass {
                background: #0284c7;
                color: #ffffff;
                font-size: 13px;
                font-weight: 800;
                padding: 4px 14px;
                border-radius: 6px;
            }
            QLabel#badgeQuota {
                background: #ec4899;
                color: #ffffff;
                font-size: 13px;
                font-weight: 800;
                padding: 4px 14px;
                border-radius: 6px;
            }
            QComboBox {
                background: #081422;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                padding: 4px 8px;
                color: #ffffff;
                font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background: #081422;
                color: #ffffff;
                border: 1px solid #1e3a5f;
                selection-background-color: #7c3aed;
                selection-color: #ffffff;
            }
            QFrame#pairFooter {
                background: #071524;
                border-top: 1px solid #1e3a5f;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QLabel#pillAvail {
                background: #064e3b;
                color: #34d399;
                border: 1px solid #059669;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 800;
                padding: 4px 12px;
            }
            QLabel#pairClock {
                color: #38bdf8;
                font-family: "Consolas", monospace;
                font-size: 15px;
                font-weight: 800;
            }
        """)

    def _make_worker_btn(self, label: str, color: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(34)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-weight: 800;
                font-size: 11px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)
        btn.clicked.connect(lambda _, l=label: self.launch_worker.emit(self.ticket_id, self.pair_index, l))
        return btn

    def _load_ticket_data(self) -> None:
        t = self.ticket
        name = t.get("ticket_name") or f"{t.get('from_station')}_{t.get('to_station')}"
        self.title_lbl.setText(f"{name} - {self.pair_index + 1}")
        self.train_no_lbl.setText(t.get("train_number", ""))
        self.from_lbl.setText(t.get("from_station", ""))
        self.to_lbl.setText(t.get("to_station", ""))
        self.date_lbl.setText(t.get("journey_date", ""))
        self.class_badge.setText(t.get("class", "2A"))
        self.quota_badge.setText(t.get("quota", "TQ"))

        acct_name = t.get("account_username") or "user****"
        self.account_combo.addItem(acct_name)

    def set_accounts(self, accounts: list[dict[str, Any]]) -> None:
        """Populate accounts dropdown."""
        self.account_combo.clear()
        for a in accounts:
            self.account_combo.addItem(a.get("username", ""), a.get("id"))
        if self.account_combo.count() == 0:
            self.account_combo.addItem(self.ticket.get("account_username") or "user****")

    def set_proxies(self, proxies: list[dict[str, Any]]) -> None:
        """Populate IP / proxy dropdown."""
        self.ip_combo.clear()
        self.ip_combo.addItem("Home IP", None)
        for p in proxies:
            name = p.get("name") or f"{p.get('host')}:{p.get('port')}"
            self.ip_combo.addItem(name, p.get("id"))

    def set_payments(self, payments: list[dict[str, Any]]) -> None:
        """Populate Bank dropdown."""
        self.bank_combo.clear()
        for p in payments:
            label = f"{p.get('gateway', '')} · {p.get('identifier', '')}"
            self.bank_combo.addItem(label, p.get("id"))

    def set_status(self, text: str, color_bg: str = "#0284c7") -> None:
        """Set banner status text and background color."""
        self.banner_text.setText(text)
        self.banner.setStyleSheet(f"background: {color_bg};")

    def set_booking_state(self, state: BookingState) -> None:
        """Update the status banner and availability pill from a booking state.

        Mirrors BookingWorkflowService states so the panel reflects the
        live, user-driven booking flow (READY · STANDBY -> ... -> BOOKED).
        """
        configs = {
            BookingState.IDLE: ("READY · STANDBY", "#0284c7", "AVAILABLE", True),
            BookingState.IN_PROGRESS: ("ACTIVE · IN PROGRESS", "#0284c7", "VERIFYING", False),
            BookingState.WAITING_FOR_2FA: ("WAITING · 2FA / OTP", "#ea580c", "AUTHENTICATING", False),
            BookingState.WAITING_FOR_CAPTCHA: ("WAITING · CAPTCHA", "#f59e0b", "VERIFYING", False),
            BookingState.PAYMENT: ("PAYMENT · PENDING", "#7c3aed", "PAYMENT DUE", False),
            BookingState.COMPLETED: ("BOOKED", "#16a34a", "BOOKED", False),
            BookingState.FAILED: ("FAILED", "#dc2626", "FAILED", False),
            BookingState.CANCELLED: ("CANCELLED", "#dc2626", "CANCELLED", False),
        }
        text, color, pill, available = configs[state]
        self.set_status(text, color)
        self.set_availability(pill, is_available=available)

    def set_tatkal_countdown(self, class_type: str | None = None) -> None:
        """Arm the countdown to the next Tatkal opening for this ticket's class.

        AC classes (1A/2A/3A/CC/EC) open at 10:00; all other classes at 11:00.
        If today's opening has already passed, the target rolls to tomorrow.
        """
        hour = (
            self._TATKAL_HOUR_AC
            if str(class_type or "").upper() in self._AC_CLASSES
            else self._TATKAL_HOUR_NON_AC
        )
        now = datetime.datetime.now()
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if now >= target:
            target += datetime.timedelta(days=1)
        self._countdown_target = target
        self._countdown_active = True

    def set_availability(self, text: str, is_available: bool = True) -> None:
        """Set availability pill text and color."""
        if is_available:
            self.avail_pill.setText(f"🟢  {text}")
            self.avail_pill.setStyleSheet("""
                background: #ecfdf5;
                color: #059669;
                border: 1px solid #a7f3d0;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 800;
                padding: 4px 12px;
            """)
        else:
            self.avail_pill.setText(f"🔴  {text}")
            self.avail_pill.setStyleSheet("""
                background: #fef2f2;
                color: #dc2626;
                border: 1px solid #fecaca;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 800;
                padding: 4px 12px;
            """)

    def _tick_clock(self) -> None:
        now = datetime.datetime.now()
        if self._countdown_active and self._countdown_target is not None:
            remaining = int((self._countdown_target - now).total_seconds())
            if remaining <= 0:
                self.clock_lbl.setText("TATKAL OPEN · BOOK NOW")
                self.clock_lbl.setStyleSheet("""
                    color: #34d399;
                    font-family: "Consolas", monospace;
                    font-size: 15px;
                    font-weight: 800;
                """)
            else:
                hours, rem = divmod(remaining, 3600)
                minutes, seconds = divmod(rem, 60)
                self.clock_lbl.setText(f"TATKAL IN {hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            self.clock_lbl.setText(now.strftime("%H:%M:%S"))

    def _on_close(self) -> None:
        self.close_clicked.emit(self.ticket_id, self.pair_index)
        self.hide()
