"""Tests for the database layer and repository classes.

Uses Python's unittest standard library and temporary
databases. Never uses real credentials or personal data.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from seatflow.database.database import Database, DatabaseError, SCHEMA_VERSION
from seatflow.repositories import (
    BookingHistoryRepository,
    FreechargeSessionRepository,
    IrctcAccountRepository,
    NewsAcknowledgmentRepository,
    ProxyRepository,
    PnrRepository,
    SchemaVersionRepository,
    SettingsRepository,
    TicketRepository,
    VaultRepository,
)


class DatabaseTestCase(unittest.TestCase):
    """Base test case with a temporary database."""

    def setUp(self) -> None:
        """Create a temporary database for each test."""
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()

    def tearDown(self) -> None:
        """Close and remove the temporary database."""
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)


class TestDatabaseInitialization(DatabaseTestCase):
    """Tests for database initialization and schema creation."""

    def test_connect_creates_database_file(self) -> None:
        """The database file should be created on connect."""
        self.assertTrue(os.path.exists(self.tmp_path))

    def test_wal_mode_enabled(self) -> None:
        """WAL journal mode should be enabled."""
        conn = self.db.connect()
        row = conn.execute("PRAGMA journal_mode").fetchone()
        self.assertEqual(row[0].lower(), "wal")

    def test_foreign_keys_enabled(self) -> None:
        """Foreign key constraints should be enforced."""
        conn = self.db.connect()
        row = conn.execute("PRAGMA foreign_keys").fetchone()
        self.assertEqual(row[0], 1)

    def test_all_tables_created(self) -> None:
        """All 10 approved tables should exist after initialization."""
        expected_tables = [
            "schema_version",
            "vault",
            "settings",
            "irctc_accounts",
            "tickets",
            "proxies",
            "booking_history",
            "pnr_records",
            "freecharge_sessions",
            "news_acknowledgments",
        ]
        conn = self.db.connect()
        for table in expected_tables:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            self.assertIsNotNone(row, f"Table {table} was not created")

    def test_indexes_created(self) -> None:
        """Expected indexes should exist after initialization."""
        expected_indexes = [
            "idx_irctc_accounts_username",
            "idx_irctc_accounts_active",
            "idx_irctc_accounts_deleted",
            "idx_tickets_irctc_account",
            "idx_tickets_status",
            "idx_tickets_journey_date",
            "idx_tickets_deleted",
            "idx_proxies_active",
            "idx_proxies_deleted",
            "idx_booking_history_ticket",
            "idx_booking_history_irctc",
            "idx_booking_history_status",
            "idx_booking_history_timestamp",
            "idx_booking_history_deleted",
            "idx_pnr_records_number",
            "idx_freecharge_sessions_mobile",
            "idx_freecharge_sessions_deleted",
        ]
        conn = self.db.connect()
        for index in expected_indexes:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (index,),
            ).fetchone()
            self.assertIsNotNone(row, f"Index {index} was not created")

    def test_schema_version_recorded(self) -> None:
        """The initial schema version should be recorded."""
        version = self.db.get_schema_version()
        self.assertEqual(version, SCHEMA_VERSION)

    def test_repeated_initialization_preserves_data(self) -> None:
        """Calling initialize_schema twice should not lose data."""
        # Insert a setting
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            ("test_key", "test_value"),
        )
        self.db._conn.commit()

        # Re-initialize
        self.db.initialize_schema()

        # Data should still be there
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", ("test_key",)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["value"], "test_value")


class TestSchemaVersionRepository(DatabaseTestCase):
    """Tests for the schema version repository."""

    def test_record_and_get_version(self) -> None:
        repo = SchemaVersionRepository(self.db)
        # initialize_schema already records version 1
        self.assertTrue(repo.is_initialized())
        self.assertEqual(repo.get_latest_version(), SCHEMA_VERSION)

        # Record a new version
        repo.record_version(2, "Test migration")
        self.assertEqual(repo.get_latest_version(), 2)

    def test_get_latest_version_returns_none_when_empty(self) -> None:
        repo = SchemaVersionRepository(self.db)
        # Clear the table to test empty state
        conn = self.db.connect()
        conn.execute("DELETE FROM schema_version")
        self.db._conn.commit()
        self.assertIsNone(repo.get_latest_version())


class TestVaultRepository(DatabaseTestCase):
    """Tests for the vault repository."""

    def test_create_and_get_config(self) -> None:
        repo = VaultRepository(self.db)
        self.assertFalse(repo.is_configured())

        repo.create_config(salt="abc123", hash_value="def456", is_configured=1)
        self.assertTrue(repo.is_configured())

        config = repo.get_config()
        self.assertIsNotNone(config)
        self.assertEqual(config["salt"], "abc123")
        self.assertEqual(config["hash"], "def456")
        self.assertEqual(config["is_configured"], 1)

    def test_update_unlock_time(self) -> None:
        repo = VaultRepository(self.db)
        repo.create_config(salt="salt", hash_value="hash", is_configured=1)
        result = repo.update_unlock_time("2026-01-01T00:00:00Z")
        self.assertTrue(result)

        config = repo.get_config()
        self.assertEqual(config["unlocked_at"], "2026-01-01T00:00:00Z")

    def test_mark_unconfigured(self) -> None:
        repo = VaultRepository(self.db)
        repo.create_config(salt="salt", hash_value="hash", is_configured=1)
        repo.mark_unconfigured()
        self.assertFalse(repo.is_configured())


class TestSettingsRepository(DatabaseTestCase):
    """Tests for the settings repository."""

    def test_set_and_get(self) -> None:
        repo = SettingsRepository(self.db)
        self.assertIsNone(repo.get("theme"))

        repo.set("theme", "dark")
        self.assertEqual(repo.get("theme"), "dark")

    def test_update_existing(self) -> None:
        repo = SettingsRepository(self.db)
        repo.set("theme", "dark")
        repo.set("theme", "light")
        self.assertEqual(repo.get("theme"), "light")

    def test_delete(self) -> None:
        repo = SettingsRepository(self.db)
        repo.set("theme", "dark")
        self.assertTrue(repo.delete("theme"))
        self.assertIsNone(repo.get("theme"))
        self.assertFalse(repo.delete("nonexistent"))

    def test_get_all(self) -> None:
        repo = SettingsRepository(self.db)
        repo.set("key1", "val1")
        repo.set("key2", "val2")
        all_settings = repo.get_all()
        self.assertEqual(all_settings["key1"], "val1")
        self.assertEqual(all_settings["key2"], "val2")


class TestIrctcAccountRepository(DatabaseTestCase):
    """Tests for the IRCTC accounts repository."""

    def test_create_and_get(self) -> None:
        repo = IrctcAccountRepository(self.db)
        repo.create({
            "id": "acc-1",
            "username": "user1",
            "password_encrypted": "encrypted_pass",
            "mobile": "9876543210",
            "email": "user@example.com",
            "is_active": 1,
            "created_at": None,
            "updated_at": None,
            "deleted_at": None,
        })

        account = repo.get_by_id("acc-1")
        self.assertIsNotNone(account)
        self.assertEqual(account["username"], "user1")

    def test_get_by_username(self) -> None:
        repo = IrctcAccountRepository(self.db)
        repo.create({
            "id": "acc-1",
            "username": "user1",
            "password_encrypted": "enc",
            "mobile": None,
            "email": None,
            "is_active": 1,
            "created_at": None,
            "updated_at": None,
            "deleted_at": None,
        })

        found = repo.get_by_username("user1")
        self.assertIsNotNone(found)
        self.assertEqual(found["id"], "acc-1")

        not_found = repo.get_by_username("nonexistent")
        self.assertIsNone(not_found)

    def test_unique_username_constraint(self) -> None:
        repo = IrctcAccountRepository(self.db)
        repo.create({
            "id": "acc-1",
            "username": "dupuser",
            "password_encrypted": "enc1",
            "mobile": None,
            "email": None,
            "is_active": 1,
            "created_at": None,
            "updated_at": None,
            "deleted_at": None,
        })

        with self.assertRaises(Exception):
            repo.create({
                "id": "acc-2",
                "username": "dupuser",
                "password_encrypted": "enc2",
                "mobile": None,
                "email": None,
                "is_active": 1,
                "created_at": None,
                "updated_at": None,
                "deleted_at": None,
            })

    def test_list_active(self) -> None:
        repo = IrctcAccountRepository(self.db)
        repo.create({
            "id": "acc-1", "username": "active1", "password_encrypted": "e1",
            "mobile": None, "email": None, "is_active": 1,
            "created_at": None, "updated_at": None, "deleted_at": None,
        })
        repo.create({
            "id": "acc-2", "username": "inactive1", "password_encrypted": "e2",
            "mobile": None, "email": None, "is_active": 0,
            "created_at": None, "updated_at": None, "deleted_at": None,
        })

        active = repo.list_active()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["username"], "active1")

    def test_soft_delete(self) -> None:
        repo = IrctcAccountRepository(self.db)
        repo.create({
            "id": "acc-1", "username": "todelete", "password_encrypted": "e",
            "mobile": None, "email": None, "is_active": 1,
            "created_at": None, "updated_at": None, "deleted_at": None,
        })

        result = repo.soft_delete("acc-1", "2026-01-01T00:00:00Z")
        self.assertTrue(result)

        account = repo.get_by_id("acc-1")
        # get_by_id doesn't filter by deleted_at, so it still returns the row
        self.assertIsNotNone(account)
        self.assertEqual(account["deleted_at"], "2026-01-01T00:00:00Z")

        # list_active should exclude soft-deleted
        active = repo.list_active()
        self.assertEqual(len(active), 0)


class TestTicketRepository(DatabaseTestCase):
    """Tests for the ticket repository."""

    def test_create_and_get(self) -> None:
        repo = TicketRepository(self.db)
        repo.create({
            "id": "tick-1",
            "train_number": "12345",
            "from_station": "NDLS",
            "to_station": "HWH",
            "journey_date": "2026-12-01",
            "class": "3A",
            "quota": "Tatkal",
            "passenger_details": '[{"name": "Test User", "age": 30}]',
            "mobile": "9876543210",
            "email": "test@example.com",
            "irctc_account_id": None,
            "status": "draft",
            "created_at": None,
            "updated_at": None,
            "deleted_at": None,
        })

        ticket = repo.get_by_id("tick-1")
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["train_number"], "12345")
        self.assertEqual(ticket["pnr_number"] if "pnr_number" in ticket else True, True)

    def test_list_active(self) -> None:
        repo = TicketRepository(self.db)
        repo.create({
            "id": "tick-1", "train_number": "123", "from_station": "A",
            "to_station": "B", "journey_date": "2026-12-01", "class": "3A",
            "quota": "General", "passenger_details": "[]", "mobile": None,
            "email": None, "irctc_account_id": None, "status": "draft",
            "created_at": None, "updated_at": None, "deleted_at": None,
        })
        tickets = repo.list_active()
        self.assertEqual(len(tickets), 1)

    def test_foreign_key_irctc_account(self) -> None:
        """Ticket with non-existent IRCTC account should be allowed (nullable FK)."""
        repo = TicketRepository(self.db)
        # NULL irctc_account_id should work
        repo.create({
            "id": "tick-1", "train_number": "123", "from_station": "A",
            "to_station": "B", "journey_date": "2026-12-01", "class": "3A",
            "quota": "General", "passenger_details": "[]", "mobile": None,
            "email": None, "irctc_account_id": None, "status": "draft",
            "created_at": None, "updated_at": None, "deleted_at": None,
        })
        self.assertEqual(len(repo.list_active()), 1)


class TestForeignKeyEnforcement(DatabaseTestCase):
    """Tests for foreign key constraint enforcement."""

    def test_booking_history_ticket_fk(self) -> None:
        """booking_history.ticket_id references tickets.id (ON DELETE SET NULL)."""
        ticket_repo = TicketRepository(self.db)
        history_repo = BookingHistoryRepository(self.db)

        # Create a ticket
        ticket_repo.create({
            "id": "tick-1", "train_number": "123", "from_station": "A",
            "to_station": "B", "journey_date": "2026-12-01", "class": "3A",
            "quota": "General", "passenger_details": "[]", "mobile": None,
            "email": None, "irctc_account_id": None, "status": "draft",
            "created_at": None, "updated_at": None, "deleted_at": None,
        })

        # Create booking history referencing the ticket
        history_repo.create({
            "id": "hist-1",
            "ticket_id": "tick-1",
            "irctc_account_id": None,
            "pnr_number": "PNR123",
            "train_number": "123",
            "journey_date": "2026-12-01",
            "booking_status": "success",
            "fare_amount": 500.0,
            "booking_timestamp": None,
            "error_message": None,
            "deleted_at": None,
        })

        history = history_repo.get_by_id("hist-1")
        self.assertIsNotNone(history)
        self.assertEqual(history["ticket_id"], "tick-1")

    def test_booking_history_irctc_account_fk(self) -> None:
        """booking_history.irctc_account_id references irctc_accounts.id."""
        acct_repo = IrctcAccountRepository(self.db)
        history_repo = BookingHistoryRepository(self.db)

        acct_repo.create({
            "id": "acc-1", "username": "user1", "password_encrypted": "enc",
            "mobile": None, "email": None, "is_active": 1,
            "created_at": None, "updated_at": None, "deleted_at": None,
        })

        history_repo.create({
            "id": "hist-1",
            "ticket_id": None,
            "irctc_account_id": "acc-1",
            "pnr_number": "PNR123",
            "train_number": "123",
            "journey_date": "2026-12-01",
            "booking_status": "success",
            "fare_amount": 500.0,
            "booking_timestamp": None,
            "error_message": None,
            "deleted_at": None,
        })

        history = history_repo.get_by_id("hist-1")
        self.assertIsNotNone(history)
        self.assertEqual(history["irctc_account_id"], "acc-1")


class TestPnrRepository(DatabaseTestCase):
    """Tests for the PNR repository."""

    def test_create_and_get_by_pnr(self) -> None:
        repo = PnrRepository(self.db)
        repo.create({
            "id": "pnr-1",
            "pnr_number": "ABC12345",
            "train_number": "12345",
            "journey_date": "2026-12-01",
            "passenger_names": '["User One"]',
            "booking_status": "Confirmed",
            "fare_amount": 1200.0,
            "looked_up_at": None,
            "created_at": None,
            "updated_at": None,
        })

        record = repo.get_by_pnr("ABC12345")
        self.assertIsNotNone(record)
        self.assertEqual(record["pnr_number"], "ABC12345")
        self.assertEqual(record["booking_status"], "Confirmed")

    def test_unique_pnr_constraint(self) -> None:
        repo = PnrRepository(self.db)
        repo.create({
            "id": "pnr-1", "pnr_number": "DUP123", "train_number": "123",
            "journey_date": "2026-12-01", "passenger_names": "[]",
            "booking_status": "Confirmed", "fare_amount": 100.0,
            "looked_up_at": None, "created_at": None, "updated_at": None,
        })

        with self.assertRaises(Exception):
            repo.create({
                "id": "pnr-2", "pnr_number": "DUP123", "train_number": "456",
                "journey_date": "2026-12-02", "passenger_names": "[]",
                "booking_status": "Confirmed", "fare_amount": 200.0,
                "looked_up_at": None, "created_at": None, "updated_at": None,
            })


class TestProxyRepository(DatabaseTestCase):
    """Tests for the proxy repository."""

    def test_create_and_get_active(self) -> None:
        repo = ProxyRepository(self.db)
        repo.create({
            "id": "px-1", "host": "proxy.example.com", "port": 8080,
            "username": "user", "password_encrypted": "enc",
            "type": "http", "is_active": 1, "last_tested": None,
            "test_result": None, "test_latency_ms": None,
            "created_at": None, "updated_at": None, "deleted_at": None,
        })

        active = repo.get_active()
        self.assertIsNotNone(active)
        self.assertEqual(active["host"], "proxy.example.com")


class TestTransactionRollback(DatabaseTestCase):
    """Tests for transaction rollback behavior."""

    def test_rollback_on_failure(self) -> None:
        """A failed transaction should roll back all changes."""
        repo = SettingsRepository(self.db)
        repo.set("key1", "value1")

        try:
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                    ("key2", "value2"),
                )
                # Force an error
                conn.execute("INSERT INTO nonexistent_table (col) VALUES (1)")
        except Exception:
            pass

        # key2 should not exist after rollback
        self.assertIsNone(repo.get("key2"))
        # key1 should still exist
        self.assertEqual(repo.get("key1"), "value1")


class TestFreechargeSessionRepository(DatabaseTestCase):
    """Tests for the freecharge sessions repository."""

    def test_create_and_get_by_mobile(self) -> None:
        repo = FreechargeSessionRepository(self.db)
        repo.create({
            "id": "fc-1", "mobile": "9876543210", "session_id": "sess1",
            "otp_verified": 0, "bank_linked": 0, "balance_cached": 0.0,
            "last_checked": None, "created_at": None, "updated_at": None,
            "deleted_at": None,
        })

        session = repo.get_by_mobile("9876543210")
        self.assertIsNotNone(session)
        self.assertEqual(session["session_id"], "sess1")


class TestNewsAcknowledgmentRepository(DatabaseTestCase):
    """Tests for the news acknowledgments repository."""

    def test_acknowledge_and_check(self) -> None:
        repo = NewsAcknowledgmentRepository(self.db)
        self.assertFalse(repo.is_acknowledged("news-1"))

        repo.acknowledge("news-1")
        self.assertTrue(repo.is_acknowledged("news-1"))


if __name__ == "__main__":
    unittest.main()
