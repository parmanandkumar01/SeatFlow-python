"""Unit tests for the Transfer / Backup and Restore service layer.

Tests export counts, encrypted .bingo archive creation, password validation,
import preview decryption, merge restoration, and replace restoration.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from PySide6.QtCore import QCoreApplication

from seatflow.database.database import Database
from seatflow.security.vault import VaultService
from seatflow.services.history_service import HistoryService
from seatflow.services.irctc_account_service import IrctcAccountService
from seatflow.services.proxy_service import ProxyService
from seatflow.services.ticket_service import TicketService
from seatflow.services.transfer_service import (
    BACKUP_FORMAT_TAG,
    BackupDecryptionError,
    InvalidBackupFormatError,
    InvalidExportPasswordError,
    MIN_EXPORT_PASSWORD_LEN,
    TransferService,
    TransferServiceError,
)


class TransferServiceTestCase(unittest.TestCase):
    """Base test case with isolated temporary database, vault, and services."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure a QCoreApplication exists for Qt signals."""
        if QCoreApplication.instance() is None:
            cls.app = QCoreApplication([])

    def setUp(self) -> None:
        """Create a temporary database, vault, and services."""
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()

        self.vault = VaultService(self.db)
        self.vault.initialize("test-master-password-123")

        self.account_service = IrctcAccountService(self.db, self.vault)
        self.ticket_service = TicketService(self.db)
        self.proxy_service = ProxyService(self.db, self.vault)
        self.history_service = HistoryService(self.db)
        self.transfer_service = TransferService(self.db, self.vault)

        self._created_files: list[str] = []

    def tearDown(self) -> None:
        """Clean up database, vault, and temp files."""
        self.vault.lock()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)
        for f in self._created_files:
            if os.path.exists(f):
                os.unlink(f)

    def _temp_file(self, suffix: str = ".bingo") -> str:
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        self._created_files.append(path)
        return path


class TestExportCounts(TransferServiceTestCase):
    """Tests for export_counts."""

    def test_empty_database_counts(self) -> None:
        """Empty database returns all zeros."""
        counts = self.transfer_service.export_counts()
        self.assertEqual(counts["tickets"], 0)
        self.assertEqual(counts["irctc_accounts"], 0)
        self.assertEqual(counts["proxies"], 0)
        self.assertEqual(counts["history"], 0)

    def test_populated_database_counts(self) -> None:
        """Database with active records returns accurate counts."""
        acct_id = self.account_service.add_account("user1", "pass123")
        self.proxy_service.add_proxy("127.0.0.1", 8080)
        tkt_id = self.ticket_service.add_ticket(
            train_number="12301",
            from_station="NDLS",
            to_station="HWH",
            journey_date="2026-12-01",
            class_type="3A",
            quota="GN",
            passenger_details='[{"name": "Test User", "age": 30, "gender": "M"}]',
            mobile="9876543210",
            irctc_account_id=acct_id,
        )
        self.history_service.add_history(
            pnr_number="1234567890",
            train_number="12301",
            journey_date="2026-12-01",
            booking_status="success",
            fare_amount=1500.0,
            ticket_id=tkt_id,
            irctc_account_id=acct_id,
        )

        counts = self.transfer_service.export_counts()
        self.assertEqual(counts["tickets"], 1)
        self.assertEqual(counts["irctc_accounts"], 1)
        self.assertEqual(counts["proxies"], 1)
        self.assertEqual(counts["history"], 1)

    def test_soft_deleted_records_excluded_from_counts(self) -> None:
        """Soft-deleted records are not counted for export."""
        acct_id = self.account_service.add_account("to_delete", "pass123")
        proxy_id = self.proxy_service.add_proxy("10.0.0.1", 9090)

        self.account_service.delete_account(acct_id)
        self.proxy_service.delete_proxy(proxy_id)

        counts = self.transfer_service.export_counts()
        self.assertEqual(counts["irctc_accounts"], 0)
        self.assertEqual(counts["proxies"], 0)


class TestExportData(TransferServiceTestCase):
    """Tests for export_data."""

    def test_password_too_short_raises_error(self) -> None:
        """Export with password shorter than MIN_EXPORT_PASSWORD_LEN raises error."""
        out_file = self._temp_file()
        with self.assertRaises(InvalidExportPasswordError):
            self.transfer_service.export_data(out_file, "12345")

    def test_empty_password_raises_error(self) -> None:
        """Export with empty password raises error."""
        out_file = self._temp_file()
        with self.assertRaises(InvalidExportPasswordError):
            self.transfer_service.export_data(out_file, "")

    def test_successful_export_structure(self) -> None:
        """Export writes a valid encrypted JSON envelope with expected keys."""
        self.account_service.add_account("exportuser", "secretpass")
        self.proxy_service.add_proxy("1.2.3.4", 8080)

        out_file = self._temp_file()
        res = self.transfer_service.export_data(out_file, "backup-password-123")

        self.assertTrue(res["success"])
        self.assertEqual(res["file_path"], out_file)
        self.assertEqual(res["counts"]["irctc_accounts"], 1)
        self.assertEqual(res["counts"]["proxies"], 1)

        # Inspect raw file on disk: envelope format
        with open(out_file, "r", encoding="utf-8") as f:
            envelope = json.load(f)

        self.assertEqual(envelope["format"], BACKUP_FORMAT_TAG)
        self.assertIn("salt", envelope)
        self.assertIn("payload", envelope)
        self.assertIn("exported_at", envelope)
        # Ensure raw password is NOT present in envelope plaintext
        with open(out_file, "r", encoding="utf-8") as f:
            raw_text = f.read()
        self.assertNotIn("secretpass", raw_text)


class TestImportPreview(TransferServiceTestCase):
    """Tests for import_preview."""

    def setUp(self) -> None:
        super().setUp()
        self.account_service.add_account("preview_user", "password123")
        self.backup_password = "secure-backup-pass"
        self.backup_path = self._temp_file()
        self.transfer_service.export_data(self.backup_path, self.backup_password)

    def test_nonexistent_file_raises_error(self) -> None:
        """Previewing a non-existent file raises InvalidBackupFormatError."""
        with self.assertRaises(InvalidBackupFormatError):
            self.transfer_service.import_preview("/tmp/nonexistent_file_xyz.bingo", "pass")

    def test_malformed_json_raises_error(self) -> None:
        """Previewing a corrupted non-JSON file raises InvalidBackupFormatError."""
        bad_file = self._temp_file()
        with open(bad_file, "w") as f:
            f.write("not json content at all")

        with self.assertRaises(InvalidBackupFormatError):
            self.transfer_service.import_preview(bad_file, "pass")

    def test_invalid_format_tag_raises_error(self) -> None:
        """Previewing a JSON file without the correct format tag raises error."""
        bad_file = self._temp_file()
        with open(bad_file, "w") as f:
            json.dump({"format": "wrong-tag", "salt": "abc", "payload": "def"}, f)

        with self.assertRaises(InvalidBackupFormatError):
            self.transfer_service.import_preview(bad_file, "pass")

    def test_wrong_password_raises_decryption_error(self) -> None:
        """Preview with an incorrect password raises BackupDecryptionError."""
        with self.assertRaises(BackupDecryptionError):
            self.transfer_service.import_preview(self.backup_path, "wrong-password")

    def test_valid_preview_returns_metadata_and_counts(self) -> None:
        """Preview with correct password returns counts and decrypted data without modifying DB."""
        preview = self.transfer_service.import_preview(self.backup_path, self.backup_password)
        self.assertTrue(preview["valid"])
        self.assertEqual(preview["counts"]["irctc_accounts"], 1)
        self.assertIn("exported_at", preview)
        self.assertIn("data", preview)


class TestImportData(TransferServiceTestCase):
    """Tests for import_data in both merge and replace modes."""

    def setUp(self) -> None:
        super().setUp()
        # Create initial data in DB 1
        self.account_service.add_account("orig_user", "pass_orig")
        self.proxy_service.add_proxy("192.168.1.1", 8080)
        self.backup_password = "my-backup-password-999"
        self.backup_path = self._temp_file()
        self.transfer_service.export_data(self.backup_path, self.backup_password)

    def test_invalid_mode_raises_error(self) -> None:
        """Invalid import mode raises TransferServiceError."""
        with self.assertRaises(TransferServiceError):
            self.transfer_service.import_data(self.backup_path, self.backup_password, mode="invalid_mode")

    def test_import_data_merge_mode(self) -> None:
        """Merge mode imports records and skips duplicates."""
        # Add a new account in current DB
        self.account_service.add_account("current_user", "current_pass")

        signals_received: list[str] = []
        self.transfer_service.data_imported.connect(signals_received.append)

        res = self.transfer_service.import_data(self.backup_path, self.backup_password, mode="merge")
        self.assertTrue(res["success"])
        self.assertEqual(res["mode"], "merge")
        self.assertEqual(len(signals_received), 1)
        self.assertEqual(signals_received[0], "merge")

        # In merge mode, "orig_user" was already in DB so it was skipped. "current_user" remains intact.
        all_accounts = self.account_service.list_accounts()
        usernames = [a["username"] for a in all_accounts]
        self.assertIn("orig_user", usernames)
        self.assertIn("current_user", usernames)

    def test_import_data_replace_mode(self) -> None:
        """Replace mode wipes existing records and restores backup records."""
        # Add extra account in current DB
        self.account_service.add_account("temporary_user", "temp_pass")

        signals_received: list[str] = []
        self.transfer_service.data_imported.connect(signals_received.append)

        res = self.transfer_service.import_data(self.backup_path, self.backup_password, mode="replace")
        self.assertTrue(res["success"])
        self.assertEqual(res["mode"], "replace")
        self.assertEqual(len(signals_received), 1)

        # In replace mode, "temporary_user" was soft-deleted, and "orig_user" is restored
        all_accounts = self.account_service.list_accounts()
        usernames = [a["username"] for a in all_accounts]
        self.assertIn("orig_user", usernames)
        self.assertNotIn("temporary_user", usernames)

    def test_credential_re_encryption_on_import(self) -> None:
        """Imported accounts and proxies have their credentials re-encrypted by current vault."""
        # Clean current DB accounts and proxies
        conn = self.db.connect()
        conn.execute("UPDATE irctc_accounts SET deleted_at = CURRENT_TIMESTAMP")
        conn.execute("UPDATE proxies SET deleted_at = CURRENT_TIMESTAMP")

        self.transfer_service.import_data(self.backup_path, self.backup_password, mode="merge")

        # Verify decrypted password works via repository and vault
        accounts = self.account_service.list_accounts()
        self.assertEqual(len(accounts), 1)
        acct_id = accounts[0]["id"]
        raw_acct = self.account_service._repo.get_by_id(acct_id)
        self.assertIsNotNone(raw_acct)
        decrypted_pass = self.vault.decrypt(raw_acct["password_encrypted"])
        self.assertEqual(decrypted_pass, "pass_orig")


if __name__ == "__main__":
    unittest.main()
