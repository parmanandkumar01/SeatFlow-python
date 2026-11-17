"""Database layer for SeatFlow Replacement.

Provides SQLite connection management, schema initialization,
migration tracking, and connection cleanup using the Python
standard-library sqlite3 module.

All sensitive credential fields are stored encrypted via the
vault (implemented separately). This module only handles
schema, connections, and basic DDL/DML operations.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

# Target schema version. Increment when the schema changes.
SCHEMA_VERSION = 1

# Default database location on Linux.
DEFAULT_DB_DIR = os.path.expanduser("~/.local/share/SeatFlow")
DEFAULT_DB_NAME = "seatflow.db"


def get_db_path(db_path: Optional[str] = None) -> str:
    """Resolve the database file path.

    Priority:
    1. Explicit ``db_path`` argument if provided.
    2. ``BINGO_DB_PATH`` environment variable if set.
    3. Default: ``~/.local/share/SeatFlow/seatflow.db``.

    Args:
        db_path: Explicit database path override.

    Returns:
        Resolved absolute database file path.
    """
    if db_path:
        return os.path.abspath(db_path)

    env_path = os.environ.get("SEATFLOW_DB_PATH") or os.environ.get("BINGO_DB_PATH")
    if env_path:
        return os.path.abspath(env_path)

    return os.path.join(DEFAULT_DB_DIR, DEFAULT_DB_NAME)


def ensure_db_directory(db_path: str) -> None:
    """Ensure the parent directory for the database exists.

    Creates the directory if it does not exist. Never overwrites
    an existing database file.

    Args:
        db_path: Path to the database file.
    """
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)


class DatabaseError(Exception):
    """Raised for database-layer errors."""


class Database:
    """Manages a SQLite database connection.

    Provides connection management, schema initialization,
    WAL journal mode, foreign-key enforcement, and migration
    tracking via the ``schema_version`` table.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize the database manager.

        Args:
            db_path: Optional explicit database file path.
        """
        self.db_path = get_db_path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """Open (or create) the SQLite database connection.

        Enables WAL journal mode and foreign-key constraints.
        Creates the database directory and file on first launch.

        Returns:
            The open SQLite connection.

        Raises:
            DatabaseError: If the connection cannot be opened.
        """
        if self._conn is not None:
            return self._conn

        ensure_db_directory(self.db_path)

        try:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error as exc:
            self._conn = None
            raise DatabaseError(f"Failed to open database: {exc}") from exc

        return self._conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Provide a transactional scope around a series of operations.

        Commits on success, rolls back on exception.

        Yields:
            The active SQLite connection.

        Raises:
            DatabaseError: If the connection is not open.
        """
        if self._conn is None:
            raise DatabaseError("Database connection is not open. Call connect() first.")
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self) -> None:
        """Close the database connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def initialize_schema(self) -> None:
        """Create all tables and indexes if they do not exist.

        Runs schema creation and inserts the initial schema version
        record. Safe to call repeatedly — uses ``IF NOT EXISTS``
        for all DDL statements.
        """
        conn = self.connect()

        with self.transaction():
            conn.executescript(_SCHEMA_DDL)

        self._ensure_schema_version(conn)

    def _ensure_schema_version(self, conn: sqlite3.Connection) -> None:
        """Ensure the schema_version table has a row for the current version.

        Args:
            conn: An open SQLite connection inside a transaction.
        """
        row = conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                (SCHEMA_VERSION, "Initial schema"),
            )
        elif row["version"] < SCHEMA_VERSION:
            # Migration would be applied here in future versions.
            # For now, the schema is at version 1.
            pass

    def get_schema_version(self) -> int:
        """Return the current schema version.

        Returns:
            The highest schema version number, or 0 if uninitialized.
        """
        conn = self.connect()
        row = conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return int(row["version"]) if row else 0


# Complete DDL for all approved tables and indexes.
_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vault (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    salt TEXT NOT NULL,
    hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    unlocked_at TEXT,
    is_configured INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS irctc_accounts (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_encrypted TEXT NOT NULL,
    mobile TEXT,
    email TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_irctc_accounts_username ON irctc_accounts(username);
CREATE INDEX IF NOT EXISTS idx_irctc_accounts_active ON irctc_accounts(is_active);
CREATE INDEX IF NOT EXISTS idx_irctc_accounts_deleted ON irctc_accounts(deleted_at);

CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    train_number TEXT NOT NULL,
    from_station TEXT NOT NULL,
    to_station TEXT NOT NULL,
    journey_date TEXT NOT NULL,
    class TEXT NOT NULL,
    quota TEXT NOT NULL,
    passenger_details TEXT NOT NULL,
    mobile TEXT,
    email TEXT,
    irctc_account_id TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT,
    FOREIGN KEY (irctc_account_id) REFERENCES irctc_accounts(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_irctc_account ON tickets(irctc_account_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_journey_date ON tickets(journey_date);
CREATE INDEX IF NOT EXISTS idx_tickets_deleted ON tickets(deleted_at);

CREATE TABLE IF NOT EXISTS proxies (
    id TEXT PRIMARY KEY,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    username TEXT,
    password_encrypted TEXT,
    type TEXT NOT NULL DEFAULT 'http',
    is_active INTEGER NOT NULL DEFAULT 0,
    last_tested TEXT,
    test_result TEXT,
    test_latency_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_proxies_active ON proxies(is_active);
CREATE INDEX IF NOT EXISTS idx_proxies_deleted ON proxies(deleted_at);

CREATE TABLE IF NOT EXISTS booking_history (
    id TEXT PRIMARY KEY,
    ticket_id TEXT,
    irctc_account_id TEXT,
    pnr_number TEXT,
    train_number TEXT,
    journey_date TEXT,
    booking_status TEXT NOT NULL,
    fare_amount REAL,
    booking_timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    error_message TEXT,
    deleted_at TEXT,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE SET NULL,
    FOREIGN KEY (irctc_account_id) REFERENCES irctc_accounts(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_booking_history_ticket ON booking_history(ticket_id);
CREATE INDEX IF NOT EXISTS idx_booking_history_irctc ON booking_history(irctc_account_id);
CREATE INDEX IF NOT EXISTS idx_booking_history_status ON booking_history(booking_status);
CREATE INDEX IF NOT EXISTS idx_booking_history_timestamp ON booking_history(booking_timestamp);
CREATE INDEX IF NOT EXISTS idx_booking_history_deleted ON booking_history(deleted_at);

CREATE TABLE IF NOT EXISTS pnr_records (
    id TEXT PRIMARY KEY,
    pnr_number TEXT NOT NULL UNIQUE,
    train_number TEXT,
    journey_date TEXT,
    passenger_names TEXT,
    booking_status TEXT,
    fare_amount REAL,
    looked_up_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_pnr_records_number ON pnr_records(pnr_number);

CREATE TABLE IF NOT EXISTS freecharge_sessions (
    id TEXT PRIMARY KEY,
    mobile TEXT NOT NULL,
    session_id TEXT,
    otp_verified INTEGER NOT NULL DEFAULT 0,
    bank_linked INTEGER NOT NULL DEFAULT 0,
    balance_cached REAL DEFAULT 0,
    last_checked TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_freecharge_sessions_mobile ON freecharge_sessions(mobile);
CREATE INDEX IF NOT EXISTS idx_freecharge_sessions_deleted ON freecharge_sessions(deleted_at);

CREATE TABLE IF NOT EXISTS news_acknowledgments (
    news_id TEXT PRIMARY KEY,
    acknowledged_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
