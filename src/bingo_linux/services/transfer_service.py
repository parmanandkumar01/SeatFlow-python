"""Transfer / Data export and import service layer.

Provides encrypted backup and restore (.bingo files) for:
- Ticket profiles
- IRCTC accounts (with credentials re-encrypted via vault)
- Proxy configurations (with credentials re-encrypted via vault)
- Journey history

Corresponds to the original application's `data:*` and `transfer:*` IPC domain:
- data:export-counts
- data:export
- data:import-preview
- data:import (mode: 'merge' | 'replace')
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Final, Optional

from PySide6.QtCore import QObject, Signal

from bingo_linux.database.database import Database
from bingo_linux.repositories.booking_history_repository import BookingHistoryRepository
from bingo_linux.repositories.irctc_account_repository import IrctcAccountRepository
from bingo_linux.repositories.proxy_repository import ProxyRepository
from bingo_linux.repositories.ticket_repository import TicketRepository
from bingo_linux.security.encryption import Encryption, EncryptionError
from bingo_linux.security.password_hash import PasswordHasher
from bingo_linux.security.vault import VaultService


class TransferServiceError(Exception):
    """Base exception for transfer and export/import operations."""


class InvalidExportPasswordError(TransferServiceError):
    """Raised when password does not meet export requirements."""


class BackupDecryptionError(TransferServiceError):
    """Raised when backup file cannot be decrypted (wrong password or corrupted)."""


class InvalidBackupFormatError(TransferServiceError):
    """Raised when backup file format or metadata is invalid."""


MIN_EXPORT_PASSWORD_LEN: Final[int] = 6
BACKUP_FORMAT_TAG: Final[str] = "bingo-backup-v1"


class TransferService(QObject):
    """Service for encrypted data export, import preview, and restoration.

    Emits:
        data_imported: Emitted after a successful import with the mode string.
    """

    data_imported = Signal(str)

    def __init__(self, db: Database, vault: VaultService) -> None:
        """Initialize the transfer service.

        Args:
            db: Database instance.
            vault: VaultService instance for credential encryption/decryption.
        """
        super().__init__()
        self._db = db
        self._vault = vault
        self._ticket_repo = TicketRepository(db)
        self._account_repo = IrctcAccountRepository(db)
        self._proxy_repo = ProxyRepository(db)
        self._history_repo = BookingHistoryRepository(db)
        self._hasher = PasswordHasher()

    # ------------------------------------------------------------------
    # Export Counts
    # ------------------------------------------------------------------

    def export_counts(self) -> dict[str, int]:
        """Return counts of available non-deleted records for export.

        Returns:
            Dict with counts of tickets, accounts, proxies, and history.
        """
        tickets = self._ticket_repo.list_all("deleted_at IS NULL")
        accounts = self._account_repo.list_all("deleted_at IS NULL")
        proxies = self._proxy_repo.list_all("deleted_at IS NULL")
        history = self._history_repo.list_all("deleted_at IS NULL")

        return {
            "tickets": len(tickets),
            "irctc_accounts": len(accounts),
            "proxies": len(proxies),
            "history": len(history),
        }

    # ------------------------------------------------------------------
    # Data Export
    # ------------------------------------------------------------------

    def export_data(self, file_path: str, password: str) -> dict[str, Any]:
        """Export tickets, accounts, proxies, and history into an encrypted .bingo file.

        Args:
            file_path: Output file destination path.
            password: User-provided encryption password for the backup file.

        Returns:
            Dict containing export summary, file_path, counts, and timestamp.

        Raises:
            InvalidExportPasswordError: If password is too short.
            TransferServiceError: On export or file writing error.
        """
        if not password or len(password) < MIN_EXPORT_PASSWORD_LEN:
            raise InvalidExportPasswordError(
                f"Export password must be at least {MIN_EXPORT_PASSWORD_LEN} characters."
            )

        now = datetime.now(timezone.utc).isoformat()
        counts = self.export_counts()

        # Gather records
        raw_tickets = self._ticket_repo.list_all("deleted_at IS NULL")
        raw_accounts = self._account_repo.list_all("deleted_at IS NULL")
        raw_proxies = self._proxy_repo.list_all("deleted_at IS NULL")
        raw_history = self._history_repo.list_all("deleted_at IS NULL")

        # Handle account credentials
        accounts_payload: list[dict[str, Any]] = []
        for acct in raw_accounts:
            a_copy = dict(acct)
            enc_pw = a_copy.pop("password_encrypted", None)
            plaintext_pw = None
            if enc_pw and self._vault.is_unlocked():
                try:
                    plaintext_pw = self._vault.decrypt(enc_pw)
                except Exception:
                    plaintext_pw = None
            a_copy["password_plaintext"] = plaintext_pw
            accounts_payload.append(a_copy)

        # Handle proxy credentials
        proxies_payload: list[dict[str, Any]] = []
        for prx in raw_proxies:
            p_copy = dict(prx)
            enc_pw = p_copy.pop("password_encrypted", None)
            plaintext_pw = None
            if enc_pw and self._vault.is_unlocked():
                try:
                    plaintext_pw = self._vault.decrypt(enc_pw)
                except Exception:
                    plaintext_pw = None
            p_copy["password_plaintext"] = plaintext_pw
            proxies_payload.append(p_copy)

        payload_obj = {
            "version": "1.0",
            "exported_at": now,
            "counts": counts,
            "data": {
                "tickets": raw_tickets,
                "irctc_accounts": accounts_payload,
                "proxies": proxies_payload,
                "history": raw_history,
            },
        }

        # Derive encryption key and encrypt payload
        salt_hex = self._hasher.generate_salt()
        derived_key = self._hasher.derive_key(password, salt_hex)
        cipher = Encryption(derived_key)
        encrypted_payload = cipher.encrypt(json.dumps(payload_obj))

        envelope = {
            "format": BACKUP_FORMAT_TAG,
            "exported_at": now,
            "salt": salt_hex,
            "payload": encrypted_payload,
        }

        # Write to destination
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(envelope, f, indent=2)
        except Exception as exc:
            raise TransferServiceError(f"Failed to write export file: {exc}") from exc

        return {
            "success": True,
            "file_path": file_path,
            "counts": counts,
            "exported_at": now,
        }

    # ------------------------------------------------------------------
    # Import Preview
    # ------------------------------------------------------------------

    def import_preview(self, file_path: str, password: str) -> dict[str, Any]:
        """Decrypt and validate a .bingo backup file without modifying the database.

        Args:
            file_path: Path to the backup file.
            password: Password used during export.

        Returns:
            Dict containing validation status, exported_at, counts, and decrypted data.

        Raises:
            InvalidBackupFormatError: If file structure is invalid.
            BackupDecryptionError: If password is wrong or decryption fails.
        """
        if not os.path.exists(file_path):
            raise InvalidBackupFormatError(f"File not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                envelope = json.load(f)
        except Exception as exc:
            raise InvalidBackupFormatError(f"Cannot read backup file: {exc}") from exc

        if not isinstance(envelope, dict) or envelope.get("format") != BACKUP_FORMAT_TAG:
            raise InvalidBackupFormatError("Invalid or unsupported .bingo backup format.")

        salt_hex = envelope.get("salt")
        payload_cipher = envelope.get("payload")
        if not salt_hex or not payload_cipher:
            raise InvalidBackupFormatError("Corrupted backup file: missing salt or payload.")

        try:
            derived_key = self._hasher.derive_key(password, salt_hex)
            cipher = Encryption(derived_key)
            decrypted_json = cipher.decrypt(payload_cipher)
            payload = json.loads(decrypted_json)
        except (EncryptionError, Exception) as exc:
            raise BackupDecryptionError("Incorrect password or corrupted file.") from exc

        counts = payload.get("counts", {})
        exported_at = payload.get("exported_at")
        data = payload.get("data", {})

        return {
            "valid": True,
            "exported_at": exported_at,
            "counts": counts,
            "data": data,
        }

    # ------------------------------------------------------------------
    # Data Import
    # ------------------------------------------------------------------

    def import_data(
        self,
        file_path: str,
        password: str,
        mode: str = "merge",
    ) -> dict[str, Any]:
        """Restore data from an encrypted .bingo backup file.

        Args:
            file_path: Path to the backup file.
            password: Password used during export.
            mode: 'merge' (add new/skip duplicates) or 'replace' (wipe existing first).

        Returns:
            Dict containing import results and record counts.

        Raises:
            TransferServiceError: On validation or import failure.
        """
        mode = mode.lower().strip()
        if mode not in ("merge", "replace"):
            raise TransferServiceError(f"Invalid import mode '{mode}'. Must be 'merge' or 'replace'.")

        preview = self.import_preview(file_path, password)
        data = preview.get("data", {})

        tickets_list = data.get("tickets", [])
        accounts_list = data.get("irctc_accounts", [])
        proxies_list = data.get("proxies", [])
        history_list = data.get("history", [])

        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.connect()

        try:
            with conn:
                if mode == "replace":
                    # Mark existing records as deleted or clear them
                    conn.execute("UPDATE tickets SET deleted_at = ? WHERE deleted_at IS NULL", (now,))
                    conn.execute("UPDATE irctc_accounts SET deleted_at = ? WHERE deleted_at IS NULL", (now,))
                    conn.execute("UPDATE proxies SET deleted_at = ? WHERE deleted_at IS NULL", (now,))
                    conn.execute("UPDATE booking_history SET deleted_at = ? WHERE deleted_at IS NULL", (now,))

                imported_tickets = 0
                imported_accounts = 0
                imported_proxies = 0
                imported_history = 0

                # 1. Import IRCTC Accounts
                for acct in accounts_list:
                    username = acct.get("username")
                    if not username:
                        continue

                    # In merge mode, check if username exists
                    if mode == "merge":
                        row = conn.execute(
                            "SELECT 1 FROM irctc_accounts WHERE username = ? AND deleted_at IS NULL",
                            (username,),
                        ).fetchone()
                        if row:
                            continue

                    acct_id = acct.get("id") or str(uuid.uuid4())
                    plaintext_pw = acct.get("password_plaintext")
                    encrypted_pw = None
                    if plaintext_pw and self._vault.is_unlocked():
                        encrypted_pw = self._vault.encrypt(plaintext_pw)

                    conn.execute(
                        """
                        INSERT OR REPLACE INTO irctc_accounts
                        (id, username, password_encrypted, mobile, email, is_active, created_at, updated_at, deleted_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                        """,
                        (
                            acct_id,
                            username,
                            encrypted_pw,
                            acct.get("mobile"),
                            acct.get("email"),
                            acct.get("is_active", 1),
                            acct.get("created_at") or now,
                            now,
                        ),
                    )
                    imported_accounts += 1

                # 2. Import Proxies
                for prx in proxies_list:
                    host = prx.get("host")
                    port = prx.get("port")
                    if not host or not port:
                        continue

                    if mode == "merge":
                        row = conn.execute(
                            "SELECT 1 FROM proxies WHERE host = ? AND port = ? AND deleted_at IS NULL",
                            (host, port),
                        ).fetchone()
                        if row:
                            continue

                    prx_id = prx.get("id") or str(uuid.uuid4())
                    plaintext_pw = prx.get("password_plaintext")
                    encrypted_pw = None
                    if plaintext_pw and self._vault.is_unlocked():
                        encrypted_pw = self._vault.encrypt(plaintext_pw)

                    conn.execute(
                        """
                        INSERT OR REPLACE INTO proxies
                        (id, host, port, username, password_encrypted, type, is_active, last_tested, test_result, test_latency_ms, created_at, updated_at, deleted_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                        """,
                        (
                            prx_id,
                            host,
                            port,
                            prx.get("username"),
                            encrypted_pw,
                            prx.get("type", "http"),
                            prx.get("is_active", 0),
                            prx.get("last_tested"),
                            prx.get("test_result"),
                            prx.get("test_latency_ms"),
                            prx.get("created_at") or now,
                            now,
                        ),
                    )
                    imported_proxies += 1

                # 3. Import Tickets
                for tkt in tickets_list:
                    tkt_id = tkt.get("id") or str(uuid.uuid4())
                    if mode == "merge":
                        row = conn.execute(
                            "SELECT 1 FROM tickets WHERE id = ? AND deleted_at IS NULL",
                            (tkt_id,),
                        ).fetchone()
                        if row:
                            continue

                    conn.execute(
                        """
                        INSERT OR REPLACE INTO tickets
                        (id, train_number, from_station, to_station, journey_date, class, quota, passenger_details, mobile, email, irctc_account_id, status, created_at, updated_at, deleted_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                        """,
                        (
                            tkt_id,
                            tkt.get("train_number"),
                            tkt.get("from_station"),
                            tkt.get("to_station"),
                            tkt.get("journey_date"),
                            tkt.get("class"),
                            tkt.get("quota"),
                            tkt.get("passenger_details"),
                            tkt.get("mobile"),
                            tkt.get("email"),
                            tkt.get("irctc_account_id"),
                            tkt.get("status", "draft"),
                            tkt.get("created_at") or now,
                            now,
                        ),
                    )
                    imported_tickets += 1

                # 4. Import History
                for hist in history_list:
                    h_id = hist.get("id") or str(uuid.uuid4())
                    if mode == "merge":
                        row = conn.execute(
                            "SELECT 1 FROM booking_history WHERE id = ? AND deleted_at IS NULL",
                            (h_id,),
                        ).fetchone()
                        if row:
                            continue

                    conn.execute(
                        """
                        INSERT OR REPLACE INTO booking_history
                        (id, ticket_id, irctc_account_id, pnr_number, train_number, booking_status, booking_timestamp, failure_reason, total_fare, created_at, deleted_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                        """,
                        (
                            h_id,
                            hist.get("ticket_id"),
                            hist.get("irctc_account_id"),
                            hist.get("pnr_number"),
                            hist.get("train_number"),
                            hist.get("booking_status"),
                            hist.get("booking_timestamp") or now,
                            hist.get("failure_reason"),
                            hist.get("total_fare"),
                            hist.get("created_at") or now,
                        ),
                    )
                    imported_history += 1

        except Exception as exc:
            raise TransferServiceError(f"Import transaction failed: {exc}") from exc

        imported_counts = {
            "tickets": imported_tickets,
            "irctc_accounts": imported_accounts,
            "proxies": imported_proxies,
            "history": imported_history,
        }

        self.data_imported.emit(mode)
        return {
            "success": True,
            "mode": mode,
            "imported_counts": imported_counts,
        }
