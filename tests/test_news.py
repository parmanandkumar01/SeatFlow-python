"""Unit tests for the News & Announcement service layer.

Tests loading default circulars, custom JSON announcements, acknowledgment
tracking in the database, unread counting, and Qt signal emissions.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from PySide6.QtCore import QCoreApplication

from seatflow.database.database import Database
from seatflow.services.news_service import (
    DEFAULT_NEWS_ITEMS,
    NewsNotFoundError,
    NewsService,
)


class NewsServiceTestCase(unittest.TestCase):
    """Base test case for NewsService with isolated temporary database."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure a QCoreApplication exists for Qt signals."""
        if QCoreApplication.instance() is None:
            cls.app = QCoreApplication([])

    def setUp(self) -> None:
        """Create a temporary database and NewsService for each test."""
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.news_service = NewsService(self.db)
        self._temp_files: list[str] = []

    def tearDown(self) -> None:
        """Clean up database and temp files."""
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _create_temp_file(self, content: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self._temp_files.append(path)
        return path


class TestNewsLoading(NewsServiceTestCase):
    """Tests for loading announcements and circulars."""

    def test_default_news_items_loaded(self) -> None:
        """NewsService loads default circulars on initialization."""
        items = self.news_service.get_all_news()
        self.assertEqual(len(items), len(DEFAULT_NEWS_ITEMS))
        ids = [item["id"] for item in items]
        self.assertIn("news-v610-welcome", ids)
        self.assertIn("news-irctc-timings", ids)
        self.assertIn("news-proxy-guidelines", ids)

    def test_initial_state_all_unread(self) -> None:
        """With an empty database, all items are unacknowledged."""
        self.assertTrue(self.news_service.has_unread_news())
        self.assertEqual(self.news_service.unread_count(), len(DEFAULT_NEWS_ITEMS))
        for item in self.news_service.get_all_news():
            self.assertFalse(item["is_acknowledged"])

    def test_load_from_custom_json_file(self) -> None:
        """NewsService can load announcements from a custom JSON file."""
        custom_data = [
            {
                "id": "custom-1",
                "title": "Custom Test Notice",
                "category": "test",
                "date": "2026-11-14",
                "urgent": False,
                "summary": "Summary",
                "content": "Full text",
            }
        ]
        file_path = self._create_temp_file(json.dumps(custom_data))
        custom_service = NewsService(self.db, news_file=file_path)

        items = custom_service.get_all_news()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "custom-1")
        self.assertEqual(items[0]["title"], "Custom Test Notice")


class TestNewsQueries(NewsServiceTestCase):
    """Tests for querying individual news items."""

    def test_get_news_by_valid_id(self) -> None:
        """Querying an existing news ID returns the item dictionary."""
        item = self.news_service.get_news_by_id("news-irctc-timings")
        self.assertEqual(item["id"], "news-irctc-timings")
        self.assertTrue(item["urgent"])
        self.assertFalse(item["is_acknowledged"])

    def test_get_news_by_invalid_id_raises_not_found(self) -> None:
        """Querying a non-existent ID raises NewsNotFoundError."""
        with self.assertRaises(NewsNotFoundError):
            self.news_service.get_news_by_id("non-existent-news-id")

    def test_get_unread_news(self) -> None:
        """get_unread_news returns only unacknowledged items."""
        self.news_service.acknowledge_news("news-v610-welcome")
        unread = self.news_service.get_unread_news()
        unread_ids = [item["id"] for item in unread]
        self.assertNotIn("news-v610-welcome", unread_ids)
        self.assertIn("news-irctc-timings", unread_ids)
        self.assertEqual(len(unread), len(DEFAULT_NEWS_ITEMS) - 1)


class TestNewsAcknowledgment(NewsServiceTestCase):
    """Tests for acknowledging news items."""

    def test_acknowledge_single_item(self) -> None:
        """Acknowledging an item updates status and emits signals."""
        signals_ack: list[str] = []
        updates: list[bool] = []

        self.news_service.news_acknowledged.connect(signals_ack.append)
        self.news_service.news_updated.connect(lambda: updates.append(True))

        target_id = "news-irctc-timings"
        self.news_service.acknowledge_news(target_id)

        self.assertEqual(len(signals_ack), 1)
        self.assertEqual(signals_ack[0], target_id)
        self.assertEqual(len(updates), 1)

        item = self.news_service.get_news_by_id(target_id)
        self.assertTrue(item["is_acknowledged"])
        self.assertEqual(self.news_service.unread_count(), len(DEFAULT_NEWS_ITEMS) - 1)

    def test_acknowledge_invalid_id_raises_error(self) -> None:
        """Acknowledging a non-existent ID raises NewsNotFoundError."""
        with self.assertRaises(NewsNotFoundError):
            self.news_service.acknowledge_news("bad-id")

    def test_acknowledge_is_idempotent(self) -> None:
        """Acknowledging an already-acknowledged item does not fail or duplicate."""
        target_id = "news-proxy-guidelines"
        self.news_service.acknowledge_news(target_id)
        self.news_service.acknowledge_news(target_id)

        item = self.news_service.get_news_by_id(target_id)
        self.assertTrue(item["is_acknowledged"])

    def test_acknowledge_all(self) -> None:
        """Acknowledge all marks every item as read and zeroes unread count."""
        updates: list[bool] = []
        self.news_service.news_updated.connect(lambda: updates.append(True))

        self.news_service.acknowledge_all()

        self.assertEqual(self.news_service.unread_count(), 0)
        self.assertFalse(self.news_service.has_unread_news())
        self.assertEqual(len(updates), 1)

        for item in self.news_service.get_all_news():
            self.assertTrue(item["is_acknowledged"])

    def test_reset_acknowledgments(self) -> None:
        """Reset acknowledgments restores all items to unacknowledged state."""
        self.news_service.acknowledge_all()
        self.assertEqual(self.news_service.unread_count(), 0)

        self.news_service.reset_acknowledgments()
        self.assertEqual(self.news_service.unread_count(), len(DEFAULT_NEWS_ITEMS))
        self.assertTrue(self.news_service.has_unread_news())


if __name__ == "__main__":
    unittest.main()
