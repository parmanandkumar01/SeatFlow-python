"""Dashboard page with railway booking overview and dynamic statistics."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seatflow.security.vault import VaultService
from seatflow.services.history_service import HistoryService
from seatflow.services.irctc_account_service import IrctcAccountService
from seatflow.services.news_service import NewsService
from seatflow.services.payment_service import PaymentService
from seatflow.services.pnr_service import PnrService
from seatflow.services.proxy_service import ProxyService
from seatflow.services.ticket_service import TicketService

# Card styles
CARD_STYLE = """
    QFrame {
        background-color: #252525;
        border: 1px solid #3d3d3d;
        border-radius: 8px;
        padding: 0;
    }
"""

CARD_TITLE_STYLE = """
    QLabel {
        color: #8e8e8e;
        font-size: 12px;
        font-weight: bold;
        background-color: transparent;
        border: none;
    }
"""

CARD_VALUE_STYLE = """
    QLabel {
        color: #ffffff;
        font-size: 26px;
        font-weight: bold;
        background-color: transparent;
        border: none;
    }
"""


class SummaryCard(QFrame):
    """A reusable summary card with title and dynamic value."""

    def __init__(self, title: str, value: str = "0", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(CARD_STYLE)
        self.setFixedHeight(105)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setStyleSheet(CARD_TITLE_STYLE)
        layout.addWidget(title_label)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(CARD_VALUE_STYLE)
        layout.addWidget(self.value_label)

        layout.addStretch()

    def set_value(self, value: str) -> None:
        """Update card display value."""
        self.value_label.setText(value)


class Dashboard(QWidget):
    """Dashboard home page with dynamic railway booking metrics."""

    create_ticket_requested = Signal()
    manage_accounts_requested = Signal()
    manage_proxies_requested = Signal()
    manage_payment_requested = Signal()
    view_news_requested = Signal()
    view_transfer_requested = Signal()

    def __init__(
        self,
        account_service: Optional[IrctcAccountService] = None,
        ticket_service: Optional[TicketService] = None,
        history_service: Optional[HistoryService] = None,
        pnr_service: Optional[PnrService] = None,
        proxy_service: Optional[ProxyService] = None,
        news_service: Optional[NewsService] = None,
        payment_service: Optional[PaymentService] = None,
        vault: Optional[VaultService] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._account_service = account_service
        self._ticket_service = ticket_service
        self._history_service = history_service
        self._pnr_service = pnr_service
        self._proxy_service = proxy_service
        self._news_service = news_service
        self._payment_service = payment_service
        self._vault = vault

        self._setup_ui()
        self.refresh_data()

        # Connect reactive signals where available
        if self._news_service is not None:
            self._news_service.news_updated.connect(self.refresh_data)
        if self._proxy_service is not None:
            self._proxy_service.proxies_changed.connect(self.refresh_data)
        if self._payment_service is not None:
            self._payment_service.sessions_changed.connect(self.refresh_data)

    def _setup_ui(self) -> None:
        """Initialize the dashboard layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        # Welcome section
        top_row = QHBoxLayout()
        welcome_label = QLabel("SeatFlow - Train Ticket Booking")
        welcome_font = QFont()
        welcome_font.setPointSize(22)
        welcome_font.setBold(True)
        welcome_label.setFont(welcome_font)
        welcome_label.setStyleSheet("color: #ffffff; background-color: transparent; border: none;")
        top_row.addWidget(welcome_label)
        top_row.addStretch()

        # Vault status pill
        self.vault_status_pill = QLabel("Vault: Locked")
        self.vault_status_pill.setStyleSheet(
            "background-color: #333333; color: #ffb74d; border: 1px solid #ff9800; "
            "border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: bold;"
        )
        top_row.addWidget(self.vault_status_pill)
        layout.addLayout(top_row)

        subtitle_label = QLabel(
            "Local train ticket management, credential vault, and booking workflows."
        )
        subtitle_label.setStyleSheet(
            "color: #b0b0b0; font-size: 13px; background-color: transparent; border: none;"
        )
        layout.addWidget(subtitle_label)

        # Urgent / Unread Announcements Banner
        self.news_banner = QFrame()
        self.news_banner.setStyleSheet(
            "QFrame { background-color: #1e3a5f; border: 1px solid #2196f3; border-radius: 6px; padding: 6px; }"
        )
        banner_layout = QHBoxLayout(self.news_banner)
        banner_layout.setContentsMargins(12, 6, 12, 6)

        self.lbl_news_alert = QLabel("📢 Unread announcements available")
        self.lbl_news_alert.setStyleSheet("color: #90caf9; font-size: 12px; font-weight: bold; border: none;")
        banner_layout.addWidget(self.lbl_news_alert)
        banner_layout.addStretch()

        btn_view_news = QPushButton("View Bulletins")
        btn_view_news.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_view_news.setStyleSheet(
            "QPushButton { background-color: #2196f3; color: #ffffff; border: none; "
            "border-radius: 4px; padding: 4px 12px; font-size: 11px; font-weight: bold; }"
            "QPushButton:hover { background-color: #42a5f5; }"
        )
        btn_view_news.clicked.connect(self.view_news_requested.emit)
        banner_layout.addWidget(btn_view_news)
        self.news_banner.setVisible(False)
        layout.addWidget(self.news_banner)

        # Summary cards grid
        cards_layout = QGridLayout()
        cards_layout.setSpacing(14)

        self.card_accounts = SummaryCard("Railway Accounts", "0")
        self.card_tickets = SummaryCard("Ticket Profiles", "0")
        self.card_history = SummaryCard("Journey Records", "0")
        self.card_pnr = SummaryCard("Monitored PNRs", "0")
        self.card_proxy = SummaryCard("Active Proxy", "Direct")

        cards_layout.addWidget(self.card_accounts, 0, 0)
        cards_layout.addWidget(self.card_tickets, 0, 1)
        cards_layout.addWidget(self.card_history, 0, 2)
        cards_layout.addWidget(self.card_pnr, 0, 3)
        cards_layout.addWidget(self.card_proxy, 0, 4)

        layout.addLayout(cards_layout)

        # Upcoming Journeys section
        upcoming_frame = QFrame()
        upcoming_frame.setStyleSheet(CARD_STYLE)
        upcoming_layout = QVBoxLayout(upcoming_frame)
        upcoming_layout.setContentsMargins(16, 14, 16, 14)
        upcoming_layout.setSpacing(10)

        upcoming_title = QLabel("Upcoming Journeys & Profiles")
        upcoming_title.setStyleSheet(CARD_TITLE_STYLE)
        upcoming_layout.addWidget(upcoming_title)

        self.upcoming_empty = QLabel(
            "No upcoming journeys scheduled. Create a ticket record to get started."
        )
        self.upcoming_empty.setStyleSheet(
            "color: #8e8e8e; font-size: 13px; background-color: transparent; border: none;"
        )
        upcoming_layout.addWidget(self.upcoming_empty)

        # Compact table for upcoming tickets
        self.table_upcoming = QTableWidget()
        self.table_upcoming.setColumnCount(5)
        self.table_upcoming.setHorizontalHeaderLabels(
            ["Train", "Route", "Date", "Class/Quota", "Status"]
        )
        self.table_upcoming.horizontalHeader().setStretchLastSection(True)
        self.table_upcoming.verticalHeader().setVisible(False)
        self.table_upcoming.setStyleSheet(
            "QTableWidget { background-color: #1e1e1e; border: 1px solid #3d3d3d; border-radius: 4px; color: #ffffff; }"
            "QHeaderView::section { background-color: #2b2b2b; color: #b0b0b0; padding: 4px; border: none; font-size: 11px; font-weight: bold; }"
            "QTableWidget::item { padding: 4px; border-bottom: 1px solid #2a2a2a; font-size: 12px; }"
        )
        self.table_upcoming.setFixedHeight(130)
        self.table_upcoming.setVisible(False)
        upcoming_layout.addWidget(self.table_upcoming)

        layout.addWidget(upcoming_frame)

        # Quick actions section
        actions_frame = QFrame()
        actions_frame.setStyleSheet(CARD_STYLE)
        actions_layout = QVBoxLayout(actions_frame)
        actions_layout.setContentsMargins(16, 14, 16, 14)
        actions_layout.setSpacing(10)

        actions_title = QLabel("Quick Actions")
        actions_title.setStyleSheet(CARD_TITLE_STYLE)
        actions_layout.addWidget(actions_title)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        btn_create_ticket = QPushButton("Create Ticket Record")
        btn_create_ticket.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_create_ticket.setStyleSheet(
            "QPushButton { background-color: #4caf50; color: #ffffff; border: none; "
            "border-radius: 6px; padding: 9px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #5fbf60; }"
        )
        btn_create_ticket.clicked.connect(self.create_ticket_requested.emit)
        buttons_layout.addWidget(btn_create_ticket)

        btn_accounts = QPushButton("Railway Accounts")
        btn_accounts.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_accounts.setStyleSheet(
            "QPushButton { background-color: #3d3d3d; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 6px; padding: 9px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        btn_accounts.clicked.connect(self.manage_accounts_requested.emit)
        buttons_layout.addWidget(btn_accounts)

        btn_proxies = QPushButton("Proxy Config")
        btn_proxies.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_proxies.setStyleSheet(
            "QPushButton { background-color: #3d3d3d; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 6px; padding: 9px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        btn_proxies.clicked.connect(self.manage_proxies_requested.emit)
        buttons_layout.addWidget(btn_proxies)

        btn_payment = QPushButton("Payment Setup")
        btn_payment.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_payment.setStyleSheet(
            "QPushButton { background-color: #3d3d3d; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 6px; padding: 9px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        btn_payment.clicked.connect(self.manage_payment_requested.emit)
        buttons_layout.addWidget(btn_payment)

        btn_bulletins = QPushButton("Bulletins")
        btn_bulletins.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_bulletins.setStyleSheet(
            "QPushButton { background-color: #3d3d3d; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 6px; padding: 9px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        btn_bulletins.clicked.connect(self.view_news_requested.emit)
        buttons_layout.addWidget(btn_bulletins)

        btn_backup = QPushButton("Backup & Restore (.bingo)")
        btn_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_backup.setStyleSheet(
            "QPushButton { background-color: #42a5f5; color: #ffffff; border: none; "
            "border-radius: 6px; padding: 9px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #54b3f6; }"
        )
        btn_backup.clicked.connect(self.view_transfer_requested.emit)
        buttons_layout.addWidget(btn_backup)

        buttons_layout.addStretch()
        actions_layout.addLayout(buttons_layout)
        layout.addWidget(actions_frame)

        layout.addStretch()

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Refresh dashboard data whenever the page becomes visible."""
        super().showEvent(event)
        self.refresh_data()

    def refresh_data(self) -> None:
        """Query services and update summary cards, alerts, and tables."""
        # Vault status
        if self._vault is not None:
            if self._vault.is_unlocked():
                self.vault_status_pill.setText("Vault: Unlocked 🔓")
                self.vault_status_pill.setStyleSheet(
                    "background-color: #1b381e; color: #81c784; border: 1px solid #4caf50; "
                    "border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: bold;"
                )
            else:
                self.vault_status_pill.setText("Vault: Locked 🔒")
                self.vault_status_pill.setStyleSheet(
                    "background-color: #3d2314; color: #ffb74d; border: 1px solid #ff9800; "
                    "border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: bold;"
                )

        # Accounts count
        if self._account_service is not None:
            try:
                accounts = self._account_service.list_accounts()
                self.card_accounts.set_value(str(len(accounts)))
            except Exception:
                pass

        # History count
        if self._history_service is not None:
            try:
                hist = self._history_service.list_history()
                self.card_history.set_value(str(len(hist)))
            except Exception:
                pass

        # PNR count
        if self._pnr_service is not None:
            try:
                pnrs = self._pnr_service.list_pnrs()
                self.card_pnr.set_value(str(len(pnrs)))
            except Exception:
                pass

        # Proxy info
        if self._proxy_service is not None:
            try:
                active = self._proxy_service.get_active_proxy()
                if active:
                    self.card_proxy.set_value(f"{active.get('type', 'http').upper()}")
                else:
                    self.card_proxy.set_value("Direct")
            except Exception:
                self.card_proxy.set_value("Direct")

        # News alert banner
        if self._news_service is not None:
            try:
                unread = self._news_service.unread_count()
                if unread > 0:
                    self.lbl_news_alert.setText(f"📢 {unread} unread railway circular(s) available")
                    self.news_banner.setVisible(True)
                else:
                    self.news_banner.setVisible(False)
            except Exception:
                pass

        # Tickets count & upcoming table
        if self._ticket_service is not None:
            try:
                tickets = self._ticket_service.list_tickets()
                self.card_tickets.set_value(str(len(tickets)))

                if tickets:
                    self.upcoming_empty.setVisible(False)
                    self.table_upcoming.setVisible(True)
                    self.table_upcoming.setRowCount(min(len(tickets), 4))
                    for i, t in enumerate(tickets[:4]):
                        self.table_upcoming.setItem(i, 0, QTableWidgetItem(f"{t.get('train_number', '')} {t.get('train_name', '')}"))
                        self.table_upcoming.setItem(i, 1, QTableWidgetItem(f"{t.get('from_station', '')} → {t.get('to_station', '')}"))
                        self.table_upcoming.setItem(i, 2, QTableWidgetItem(str(t.get('journey_date', ''))))
                        self.table_upcoming.setItem(i, 3, QTableWidgetItem(f"{t.get('class', '')} / {t.get('quota', '')}"))
                        self.table_upcoming.setItem(i, 4, QTableWidgetItem(str(t.get('status', 'draft')).upper()))
                else:
                    self.table_upcoming.setVisible(False)
                    self.upcoming_empty.setVisible(True)
            except Exception:
                pass
