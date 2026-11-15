"""Tests for the railway account service layer.

Tests account creation, listing, editing, deletion, duplicate
username handling, vault lock behavior, and encrypted credential
persistence. Uses temporary databases and dummy credentials only.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from seatflow.database.database import Database
from seatflow.security.vault import (
    InvalidPasswordError,
    VaultLockedError,
    VaultNotConfiguredError,
    VaultService,
)
from seatflow.services import (
    DuplicateUsernameError,
    IrctcAccountNotFoundError,
    IrctcAccountService,
    VaultRequiredError,
)


class AccountServiceTestCase(unittest.TestCase):
    """Base test case with a temporary database, vault, and account service."""

    def setUp(self) -> None:
        """Create a temporary database, vault, and account service for each test."""
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.vault = VaultService(self.db)
        self.service = IrctcAccountService(self.db, self.vault)

    def tearDown(self) -> None:
        """Close and remove the temporary database."""
        self.vault.lock()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def _unlock_vault(self, password: str = "test-master-password") -> None:
        """Helper to initialize and unlock the vault."""
        self.vault.initialize(password)
        self.assertTrue(self.vault.is_configured())
        self.assertTrue(self.vault.is_unlocked())


class TestAccountCreation(AccountServiceTestCase):
    """Tests for account creation."""

    def test_add_account_success(self) -> None:
        """Account can be created when vault is unlocked."""
        self._unlock_vault()
        account_id = self.service.add_account(
            username="railway_user",
            password="railway_password",
            mobile="9876543210",
            email="user@example.com",
            is_active=True,
        )
        self.assertIsNotNone(account_id)

        account = self.service.get_account(account_id)
        self.assertEqual(account["username"], "railway_user")
        self.assertEqual(account["mobile"], "9876543210")
        self.assertEqual(account["email"], "user@example.com")
        self.assertEqual(account["is_active"], 1)

    def test_add_account_password_encrypted(self) -> None:
        """Password is stored encrypted, not plaintext."""
        self._unlock_vault()
        self.service.add_account(
            username="user1",
            password="secret123",
        )
        # Verify via repository that password_encrypted != plaintext
        conn = self.db.connect()
        row = conn.execute(
            "SELECT password_encrypted FROM irctc_accounts WHERE username = ?",
            ("user1",),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertNotEqual(row["password_encrypted"], "secret123")

        # But it can be decrypted back
        decrypted = self.vault.decrypt(row["password_encrypted"])
        self.assertEqual(decrypted, "secret123")

    def test_add_account_vault_locked_raises(self) -> None:
        """Adding account when vault is locked raises VaultRequiredError."""
        self.vault.initialize("test-master-password")
        self.vault.lock()
        with self.assertRaises(VaultRequiredError):
            self.service.add_account(
                username="user1",
                password="pass123",
            )

    def test_add_account_vault_not_configured_raises(self) -> None:
        """Adding account when vault is not configured raises VaultRequiredError."""
        with self.assertRaises(VaultRequiredError):
            self.service.add_account(
                username="user1",
                password="pass123",
            )

    def test_add_account_duplicate_username_raises(self) -> None:
        """Adding duplicate username raises DuplicateUsernameError."""
        self._unlock_vault()
        self.service.add_account(
            username="dupuser",
            password="pass1",
        )
        with self.assertRaises(DuplicateUsernameError):
            self.service.add_account(
                username="dupuser",
                password="pass2",
            )


class TestAccountListing(AccountServiceTestCase):
    """Tests for account listing."""

    def test_list_accounts_returns_non_sensitive_fields(self) -> None:
        """List accounts returns non-sensitive fields only, no passwords."""
        self._unlock_vault()
        self.service.add_account(
            username="user1",
            password="pass1",
            mobile="1234567890",
            email="user1@example.com",
            is_active=True,
        )
        self.service.add_account(
            username="user2",
            password="pass2",
            is_active=True,
        )

        accounts = self.service.list_accounts()
        self.assertEqual(len(accounts), 2)

        for acct in accounts:
            # Non-sensitive fields present
            self.assertIn("id", acct)
            self.assertIn("username", acct)
            self.assertIn("mobile", acct)
            self.assertIn("email", acct)
            self.assertIn("is_active", acct)
            # Password never returned
            self.assertNotIn("password_encrypted", acct)
            self.assertNotIn("password", acct)

    def test_list_accounts_excludes_deleted(self) -> None:
        """Soft-deleted accounts are not returned."""
        self._unlock_vault()
        self.service.add_account(username="user1", password="pass1")
        self.service.add_account(username="user2", password="pass2")

        accounts = self.service.list_accounts()
        self.assertEqual(len(accounts), 2)

        # Delete one
        self.service.delete_account(accounts[0]["id"])

        accounts = self.service.list_accounts()
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["username"], "user2")


class TestAccountEditing(AccountServiceTestCase):
    """Tests for account editing."""

    def test_edit_account_success(self) -> None:
        """Account can be edited when vault is unlocked."""
        self._unlock_vault()
        account_id = self.service.add_account(
            username="old_user",
            password="old_pass",
            mobile="111",
            email="old@example.com",
            is_active=True,
        )

        self.service.update_account(
            account_id=account_id,
            username="new_user",
            mobile="222",
            email="new@example.com",
            is_active=False,
        )

        account = self.service.get_account(account_id)
        self.assertEqual(account["username"], "new_user")
        self.assertEqual(account["mobile"], "222")
        self.assertEqual(account["email"], "new@example.com")
        self.assertEqual(account["is_active"], 0)

    def test_edit_account_password_change(self) -> None:
        """Account password can be changed and is re-encrypted."""
        self._unlock_vault()
        account_id = self.service.add_account(
            username="user1",
            password="old_password",
        )

        # Verify old password decrypts
        account = self.service.get_account(account_id)
        # Get the encrypted password from DB
        conn = self.db.connect()
        row = conn.execute(
            "SELECT password_encrypted FROM irctc_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        old_decrypted = self.vault.decrypt(row["password_encrypted"])
        self.assertEqual(old_decrypted, "old_password")

        # Change password
        self.service.update_account(
            account_id=account_id,
            password="new_password",
        )

        # Verify new password decrypts
        row = conn.execute(
            "SELECT password_encrypted FROM irctc_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        new_decrypted = self.vault.decrypt(row["password_encrypted"])
        self.assertEqual(new_decrypted, "new_password")
        self.assertNotEqual(row["password_encrypted"], self.vault.encrypt("old_password"))

    def test_edit_account_not_found_raises(self) -> None:
        """Editing non-existent account raises IrctcAccountNotFoundError."""
        self._unlock_vault()
        with self.assertRaises(IrctcAccountNotFoundError):
            self.service.update_account(account_id="nonexistent", username="new")

    def test_edit_account_duplicate_username_raises(self) -> None:
        """Editing to a duplicate username raises DuplicateUsernameError."""
        self._unlock_vault()
        self.service.add_account(username="user1", password="pass1")
        self.service.add_account(username="user2", password="pass2")

        account2 = self.service.list_accounts()[1]
        with self.assertRaises(DuplicateUsernameError):
            self.service.update_account(
                account_id=account2["id"],
                username="user1",
            )

    def test_edit_account_password_when_locked_raises(self) -> None:
        """Changing password when vault is locked raises VaultRequiredError."""
        self._unlock_vault()
        account_id = self.service.add_account(
            username="user1",
            password="pass1",
        )
        self.vault.lock()

        with self.assertRaises(VaultRequiredError):
            self.service.update_account(
                account_id=account_id,
                password="new_pass",
            )

    def test_edit_account_non_password_fields_when_locked(self) -> None:
        """Non-password fields can be updated when vault is locked."""
        self._unlock_vault()
        account_id = self.service.add_account(
            username="user1",
            password="pass1",
            mobile="111",
        )
        self.vault.lock()

        # Non-password update should work without vault
        self.service.update_account(
            account_id=account_id,
            mobile="222",
        )
        account = self.service.get_account(account_id)
        self.assertEqual(account["mobile"], "222")


class TestAccountDeletion(AccountServiceTestCase):
    """Tests for account deletion."""

    def test_delete_account_success(self) -> None:
        """Account can be soft-deleted."""
        self._unlock_vault()
        account_id = self.service.add_account(username="todelete", password="pass")

        self.service.delete_account(account_id)

        accounts = self.service.list_accounts()
        self.assertEqual(len(accounts), 0)

    def test_delete_account_not_found_raises(self) -> None:
        """Deleting non-existent account raises IrctcAccountNotFoundError."""
        self._unlock_vault()
        with self.assertRaises(IrctcAccountNotFoundError):
            self.service.delete_account("nonexistent")

    def test_delete_account_foreign_key_respected(self) -> None:
        """Deleting account respects FK constraints (tickets reference via SET NULL).

        Soft delete sets deleted_at but keeps the row, so FKs remain intact.
        Related tickets are NOT cascaded-deleted.
        """
        self._unlock_vault()
        account_id = self.service.add_account(
            username="user_with_tickets",
            password="pass",
        )

        # Create a ticket referencing this account
        self.db.connect().execute(
            """INSERT INTO tickets
               (id, train_number, from_station, to_station, journey_date,
                class, quota, passenger_details, mobile, email,
                irctc_account_id, status, created_at, updated_at, deleted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), NULL)""",
            (
                "ticket-1",
                "12345",
                "NDLS",
                "HWH",
                "2026-12-01",
                "3A",
                "Tatkal",
                '[]',
                None,
                None,
                account_id,
                "draft",
            ),
        )
        self.db._conn.commit()

        # Soft-delete the account - should succeed
        self.service.delete_account(account_id)

        # Account is soft-deleted (deleted_at set)
        account = self._repo_get_by_id(account_id)
        self.assertIsNotNone(account.get("deleted_at"))

        # Ticket still exists (not cascaded-deleted)
        conn = self.db.connect()
        row = conn.execute(
            "SELECT id, irctc_account_id FROM tickets WHERE id = ?",
            ("ticket-1",),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], "ticket-1")
        # Soft delete doesn't NULL FKs since row still exists
        self.assertEqual(row["irctc_account_id"], account_id)

    def _repo_get_by_id(self, account_id: str) -> dict:
        """Get account row directly from repository (including sensitive fields)."""
        return self.service._repo.get_by_id(account_id)


class TestVaultLockBehavior(AccountServiceTestCase):
    """Tests for vault lock behavior with account service."""

    def test_account_operations_blocked_when_locked(self) -> None:
        """Add account is blocked when vault is locked."""
        self.vault.initialize("test-password")
        self.vault.lock()

        with self.assertRaises(VaultRequiredError):
            self.service.add_account(
                username="user1",
                password="pass1",
            )

    def test_account_listing_works_when_locked(self) -> None:
        """Listing accounts works even when vault is locked (non-sensitive)."""
        self._unlock_vault()
        self.service.add_account(username="user1", password="pass1")
        self.vault.lock()

        accounts = self.service.list_accounts()
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["username"], "user1")

    def test_is_vault_unlocked(self) -> None:
        """is_vault_unlocked reflects vault state."""
        self.assertFalse(self.service.is_vault_unlocked())
        self._unlock_vault()
        self.assertTrue(self.service.is_vault_unlocked())
        self.vault.lock()
        self.assertFalse(self.service.is_vault_unlocked())

    def test_is_vault_configured(self) -> None:
        """is_vault_configured reflects vault state."""
        self.assertFalse(self.service.is_vault_configured())
        self._unlock_vault()
        self.assertTrue(self.service.is_vault_configured())


class TestGetAccount(AccountServiceTestCase):
    """Tests for get_account."""

    def test_get_account_success(self) -> None:
        """get_account returns non-sensitive fields."""
        self._unlock_vault()
        account_id = self.service.add_account(
            username="user1",
            password="pass1",
            mobile="123",
            email="a@b.com",
            is_active=True,
        )

        account = self.service.get_account(account_id)
        self.assertEqual(account["username"], "user1")
        self.assertEqual(account["mobile"], "123")
        self.assertEqual(account["email"], "a@b.com")
        self.assertEqual(account["is_active"], 1)
        # No password field
        self.assertNotIn("password", account)
        self.assertNotIn("password_encrypted", account)

    def test_get_account_not_found(self) -> None:
        """get_account raises for non-existent ID."""
        self._unlock_vault()
        with self.assertRaises(IrctcAccountNotFoundError):
            self.service.get_account("nonexistent")


class TestUsernameExists(AccountServiceTestCase):
    """Tests for username_exists."""

    def test_username_exists(self) -> None:
        """username_exists detects duplicates."""
        self._unlock_vault()
        self.service.add_account(username="existing", password="pass")

        self.assertTrue(self.service.username_exists("existing"))
        self.assertFalse(self.service.username_exists("nonexistent"))

    def test_username_exists_exclude_id(self) -> None:
        """username_exists with exclude_id allows editing same username."""
        self._unlock_vault()
        account_id = self.service.add_account(
            username="sameuser", password="pass"
        )

        # Without exclude_id, returns True
        self.assertTrue(self.service.username_exists("sameuser"))

        # With exclude_id, returns False (same account)
        self.assertFalse(self.service.username_exists("sameuser", exclude_id=account_id))


if __name__ == "__main__":
    unittest.main()
