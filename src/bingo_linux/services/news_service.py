"""News and announcement service.

Provides railway announcements, circulars, and system bulletins
with read/acknowledged tracking in the local database.

Corresponds to the original application's `news:*` IPC domain:
- news:get
- news:acknowledged
"""

from __future__ import annotations

import json
import os
from typing import Any, Final, Optional

from PySide6.QtCore import QObject, Signal

from bingo_linux.database.database import Database
from bingo_linux.repositories.news_acknowledgment_repository import NewsAcknowledgmentRepository


DEFAULT_NEWS_ITEMS: Final[list[dict[str, Any]]] = [
    {
        "id": "news-v610-welcome",
        "title": "Welcome to Bingo Desktop",
        "category": "announcement",
        "date": "2026-11-01",
        "urgent": False,
        "summary": "Multi-account management, proxy testing, and secure vault storage.",
        "content": (
            "Welcome to Bingo Desktop. This platform provides streamlined tools for "
            "managing railway account credentials, booking profiles, proxy connections, "
            "and journey logs.\n\n"
            "Key capabilities include:\n"
            "• Argon2id + AES-256-GCM local vault encryption for all credentials\n"
            "• Multi-account management with isolated credential storage\n"
            "• Proxy management with live socket connectivity & latency testing\n"
            "• Encrypted .bingo data backup and restoration (merge & replace modes)\n"
            "• Manual verification checkpoints for CAPTCHA and 2FA"
        ),
    },
    {
        "id": "news-irctc-timings",
        "title": "Important Railway Booking Timings & Quotas",
        "category": "circular",
        "date": "2026-11-05",
        "urgent": True,
        "summary": "Official Tatkal and General quota opening schedules.",
        "content": (
            "Please review the official quota opening timings:\n\n"
            "• AC Tatkal Quota (1A, 2A, 3A, CC, EC): Opens at 10:00 AM IST\n"
            "• Non-AC Tatkal Quota (SL, 2S): Opens at 11:00 AM IST\n"
            "• General Quota: Opens 120 days in advance at 08:00 AM IST\n\n"
            "Ensure ticket profiles are prepared and verified before quota opening."
        ),
    },
    {
        "id": "news-proxy-guidelines",
        "title": "Network and Proxy Usage Guidelines",
        "category": "security",
        "date": "2026-11-10",
        "urgent": False,
        "summary": "Recommendations for proxy configuration and connection latency.",
        "content": (
            "When using proxies for network connections:\n\n"
            "• Ensure your proxy endpoint latency is below 300ms for reliable connectivity.\n"
            "• Use dedicated residential or static data center proxies where appropriate.\n"
            "• Only one proxy may be active at any given time.\n"
            "• Credentials are automatically encrypted inside the master vault."
        ),
    },
]


class NewsServiceError(Exception):
    """Base exception for news service operations."""


class NewsNotFoundError(NewsServiceError):
    """Raised when a requested news item does not exist."""


class NewsService(QObject):
    """Service for managing announcements and user acknowledgment tracking.

    Emits:
        news_acknowledged: Emitted when an announcement is acknowledged (news_id).
        news_updated: Emitted when news acknowledgment status changes.
    """

    news_acknowledged = Signal(str)
    news_updated = Signal()

    def __init__(
        self,
        db: Database,
        news_file: Optional[str] = None,
    ) -> None:
        """Initialize the news service.

        Args:
            db: Database instance.
            news_file: Optional path to a JSON file containing custom announcements.
        """
        super().__init__()
        self._db = db
        self._repo = NewsAcknowledgmentRepository(db)
        self._news_file = news_file
        self._items: list[dict[str, Any]] = []
        self._load_items()

    def _load_items(self) -> None:
        """Load news items from external file if available, else use default items."""
        if self._news_file and os.path.exists(self._news_file):
            try:
                with open(self._news_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._items = data
                    return
            except Exception:
                pass
        self._items = [dict(item) for item in DEFAULT_NEWS_ITEMS]

    def set_custom_news_items(self, items: list[dict[str, Any]]) -> None:
        """Set in-memory news items (useful for testing or external sync).

        Args:
            items: List of news item dictionaries.
        """
        self._items = [dict(item) for item in items]
        self.news_updated.emit()

    def get_all_news(self) -> list[dict[str, Any]]:
        """Return all news items with their current acknowledgment status.

        Returns:
            List of news items with 'is_acknowledged' boolean field.
        """
        ack_ids = self._repo.get_all_acknowledged_ids()
        result: list[dict[str, Any]] = []
        for item in self._items:
            item_copy = dict(item)
            item_copy["is_acknowledged"] = item.get("id") in ack_ids
            result.append(item_copy)
        return result

    def get_news_by_id(self, news_id: str) -> dict[str, Any]:
        """Return a single news item by ID.

        Args:
            news_id: Identifier of the news item.

        Returns:
            News item dictionary with 'is_acknowledged'.

        Raises:
            NewsNotFoundError: If news item is not found.
        """
        for item in self._items:
            if item.get("id") == news_id:
                item_copy = dict(item)
                item_copy["is_acknowledged"] = self._repo.is_acknowledged(news_id)
                return item_copy
        raise NewsNotFoundError(f"News item '{news_id}' not found.")

    def get_unread_news(self) -> list[dict[str, Any]]:
        """Return all unacknowledged news items.

        Returns:
            List of unacknowledged news items.
        """
        return [item for item in self.get_all_news() if not item["is_acknowledged"]]

    def unread_count(self) -> int:
        """Return the count of unacknowledged news items.

        Returns:
            Number of unread news items.
        """
        return len(self.get_unread_news())

    def has_unread_news(self) -> bool:
        """Return True if there are any unacknowledged news items.

        Returns:
            True if unread count > 0, False otherwise.
        """
        return self.unread_count() > 0

    def acknowledge_news(self, news_id: str) -> None:
        """Mark a news item as acknowledged by the user.

        Args:
            news_id: Identifier of the news item.

        Raises:
            NewsNotFoundError: If news item is not found.
        """
        # Validate existence
        if not any(item.get("id") == news_id for item in self._items):
            raise NewsNotFoundError(f"News item '{news_id}' not found.")

        self._repo.acknowledge(news_id)
        self.news_acknowledged.emit(news_id)
        self.news_updated.emit()

    def acknowledge_all(self) -> None:
        """Mark all news items as acknowledged."""
        for item in self._items:
            n_id = item.get("id")
            if n_id:
                self._repo.acknowledge(n_id)
        self.news_updated.emit()

    def reset_acknowledgments(self) -> None:
        """Reset all acknowledgments (useful for testing)."""
        for item in self._items:
            n_id = item.get("id")
            if n_id:
                self._repo.unacknowledge(n_id)
        self.news_updated.emit()
