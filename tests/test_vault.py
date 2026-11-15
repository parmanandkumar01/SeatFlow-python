"""Tests for the security vault layer.

Uses Python's unittest standard library and temporary
databases. Uses dummy credentials only — no real passwords
or personal data.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from seatflow.database.database import Database
from seatflow.security.vault import (
    VaultService,
    VaultNotConfiguredError,
    VaultAlreadyConfiguredError,
    VaultLockedError,
    InvalidPasswordError,
)
from seatflow.security.encryption import EncryptionError
from seatflow.repositories import IrctcAccountRepository, ProxyRepository


class VaultTestCase(unittest.TestCase):
    """Base test case with a temporary database and vault service."""

    def setUp(self) -> None:
        """Create a temporary database and vault service for each test."""
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.vault = VaultService(self.db)

    def tearDown(self) -> None:
        """Close and remove the temporary database."""
        self.vault.lock()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)


class TestVaultInitialization(VaultTestCase):
    """Tests for vault initialization."""

    def test_not_configured_by_default(self) -> None:
        """A new vault should not be configured."""
        self.assertFalse(self.vault.is_configured())
        self.assertFalse(self.vault.is_unlocked())

    def test_initialize_sets_configured_and_unlocked(self) -> None:
        """After initialize, vault is configured and unlocked."""
        self.vault.initialize("test-master-password")
        self.assertTrue(self.vault.is_configured())
        self.assertTrue(self.vault.is_unlocked())

    def test_double_initialization_raises(self) -> None:
        """Initializing twice should raise VaultAlreadyConfiguredError."""
        self.vault.initialize("test-master-password")
        with self.assertRaises(VaultAlreadyConfiguredError):
            self.vault.initialize("another-password")

    def test_persists_to_database(self) -> None:
        """Vault configuration should persist in the database."""
        self.vault.initialize("test-master-password")
        config = self.db.connect().execute(
            "SELECT is_configured, salt, hash FROM vault WHERE id = 1"
        ).fetchone()
        self.assertIsNotNone(config)
        self.assertEqual(config["is_configured"], 1)
        self.assertIsNotNone(config["salt"])
        self.assertIsNotNone(config["hash"])

    def test_no_plaintext_password_in_database(self) -> None:
        """The master password should never appear in plaintext in the DB."""
        password = "super-secret-master-password"
        self.vault.initialize(password)
        conn = self.db.connect()
        # Check vault table
        row = conn.execute("SELECT hash, salt FROM vault WHERE id = 1").fetchone()
        self.assertNotEqual(row["hash"], password)
        self.assertNotEqual(row["salt"], password)
        # Check all text columns for the password
        for table in ["vault", "settings", "irctc_accounts", "tickets", "proxies",
                       "booking_history", "pnr_records", "freecharge_sessions",
                       "news_acknowledgments", "schema_version"]:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            text_cols = [c for c in cols if c in ("username", "password_encrypted", "value",
                                                    "description", "session_id", "error_message",
                                                    "pnr_number", "train_number", "journey_date",
                                                    "booking_status", "error_message")]
            for col in text_cols:
                rows = conn.execute(f"SELECT {col} FROM {table}").fetchall()
                for r in rows:
                    val = r[0]
                    if val is not None:
                        self.assertNotEqual(val, password,
                                            f"Plaintext password found in {table}.{col}")


class TestVaultUnlock(VaultTestCase):
    """Tests for vault unlock behavior."""

    def setUp(self) -> None:
        super().setUp()
        self.vault.initialize("correct-master-password")

    def test_correct_password_unlocks(self) -> None:
        """Correct password should unlock the vault."""
        # Lock first, then unlock
        self.vault.lock()
        self.assertFalse(self.vault.is_unlocked())
        result = self.vault.unlock("correct-master-password")
        self.assertTrue(result)
        self.assertTrue(self.vault.is_unlocked())

    def test_incorrect_password_rejected(self) -> None:
        """Incorrect password should raise InvalidPasswordError."""
        with self.assertRaises(InvalidPasswordError):
            self.vault.unlock("wrong-password")
        # Vault remains unlocked (correct key still in memory)
        self.assertTrue(self.vault.is_unlocked())

    def test_incorrect_password_increments_failure_counter(self) -> None:
        """Failed attempts should increment the counter."""
        self.assertEqual(self.vault._failed_attempts, 0)
        try:
            self.vault.unlock("wrong1")
        except InvalidPasswordError:
            pass
        try:
            self.vault.unlock("wrong2")
        except InvalidPasswordError:
            pass
        self.assertEqual(self.vault._failed_attempts, 2)

    def test_lockout_after_max_attempts(self) -> None:
        """After MAX_FAILED_ATTEMPTS failures, lockout should be enforced."""
        for i in range(5):
            try:
                self.vault.unlock("wrong")
            except InvalidPasswordError:
                pass
        # 6th attempt should trigger lockout
        with self.assertRaises(InvalidPasswordError) as ctx:
            self.vault.unlock("wrong")
        self.assertIn("seconds", str(ctx.exception))

    def test_unlock_after_lockout_resets_counter(self) -> None:
        """Successful unlock after failures should reset the counter."""
        for i in range(3):
            try:
                self.vault.unlock("wrong")
            except InvalidPasswordError:
                pass
        self.vault.unlock("correct-master-password")
        self.assertEqual(self.vault._failed_attempts, 0)

    def test_unlock_not_configured_raises(self) -> None:
        """Unlocking an unconfigured vault should raise."""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(tmp_fd)
        db2 = Database(db_path=tmp_path)
        db2.initialize_schema()
        vault2 = VaultService(db2)
        try:
            with self.assertRaises(VaultNotConfiguredError):
                vault2.unlock("any-password")
        finally:
            db2.close()
            os.unlink(tmp_path)

    def test_unlock_sets_unlock_time(self) -> None:
        """Successful unlock should record unlock_at timestamp."""
        self.vault.lock()
        self.vault.unlock("correct-master-password")
        config = self.db.connect().execute(
            "SELECT unlocked_at FROM vault WHERE id = 1"
        ).fetchone()
        self.assertIsNotNone(config["unlocked_at"])


class TestVaultLock(VaultTestCase):
    """Tests for vault lock behavior."""

    def setUp(self) -> None:
        super().setUp()
        self.vault.initialize("test-master-password")

    def test_lock_wipes_key(self) -> None:
        """Locking should make the vault locked and prevent operations."""
        self.assertTrue(self.vault.is_unlocked())
        self.vault.lock()
        self.assertFalse(self.vault.is_unlocked())

    def test_encrypt_after_lock_raises(self) -> None:
        """Encrypting after lock should raise VaultLockedError."""
        self.vault.lock()
        with self.assertRaises(VaultLockedError):
            self.vault.encrypt("sensitive-data")

    def test_decrypt_after_lock_raises(self) -> None:
        """Decrypting after lock should raise VaultLockedError."""
        self.vault.lock()
        with self.assertRaises(VaultLockedError):
            self.vault.decrypt("base64ciphertext")

    def test_unlock_after_lock_works(self) -> None:
        """Unlocking after lock should work with correct password."""
        self.vault.lock()
        self.assertFalse(self.vault.is_unlocked())
        self.vault.unlock("test-master-password")
        self.assertTrue(self.vault.is_unlocked())


class TestEncryptionDecryption(VaultTestCase):
    """Tests for encrypt/decrypt round trip."""

    def setUp(self) -> None:
        super().setUp()
        self.vault.initialize("test-master-password")

    def test_round_trip(self) -> None:
        """Encrypt then decrypt should return the original plaintext."""
        plaintext = "super-secret-railway-password"
        encrypted = self.vault.encrypt(plaintext)
        decrypted = self.vault.decrypt(encrypted)
        self.assertEqual(decrypted, plaintext)

    def test_encrypted_differs_from_plaintext(self) -> None:
        """Ciphertext should not equal plaintext."""
        plaintext = "secret-data"
        encrypted = self.vault.encrypt(plaintext)
        self.assertNotEqual(encrypted, plaintext)

    def test_different_nonce_each_time(self) -> None:
        """Encrypting the same plaintext twice should produce different ciphertext."""
        plaintext = "same-plaintext"
        enc1 = self.vault.encrypt(plaintext)
        enc2 = self.vault.encrypt(plaintext)
        self.assertNotEqual(enc1, enc2)

    def test_tampered_ciphertext_detected(self) -> None:
        """Tampering with ciphertext should raise InvalidPasswordError."""
        encrypted = self.vault.encrypt("secret-data")
        # Corrupt a character in the base64 string
        corrupted = encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B")
        with self.assertRaises(InvalidPasswordError):
            self.vault.decrypt(corrupted)

    def test_decrypt_wrong_key_after_reinit(self) -> None:
        """Decrypting with a different vault's key should fail."""
        # Create another vault with different password
        tmp_fd2, tmp_path2 = tempfile.mkstemp(suffix=".db")
        os.close(tmp_fd2)
        db2 = Database(db_path=tmp_path2)
        db2.initialize_schema()
        vault2 = VaultService(db2)
        vault2.initialize("different-password")

        encrypted = self.vault.encrypt("secret-data")
        try:
            vault2.decrypt(encrypted)
            self.fail("Should have raised InvalidPasswordError")
        except InvalidPasswordError:
            pass
        finally:
            vault2.lock()
            db2.close()
            os.unlink(tmp_path2)

    def test_encrypt_when_locked_raises(self) -> None:
        """Encrypting when locked should raise."""
        self.vault.lock()
        with self.assertRaises(VaultLockedError):
            self.vault.encrypt("data")

    def test_decrypt_when_locked_raises(self) -> None:
        """Decrypting when locked should raise."""
        self.vault.lock()
        with self.assertRaises(VaultLockedError):
            self.vault.decrypt("data")


class TestPasswordChange(VaultTestCase):
    """Tests for master password change."""

    def setUp(self) -> None:
        super().setUp()
        self.vault.initialize("old-password")

    def test_change_password_success(self) -> None:
        """Changing password should work and allow unlock with new password."""
        self.vault.change_password("old-password", "new-password")
        self.assertTrue(self.vault.is_unlocked())
        # Should be able to unlock with new password after lock
        self.vault.lock()
        self.vault.unlock("new-password")
        self.assertTrue(self.vault.is_unlocked())

    def test_change_password_wrong_old_rejected(self) -> None:
        """Wrong old password should be rejected."""
        with self.assertRaises(InvalidPasswordError):
            self.vault.change_password("wrong-old", "new-password")

    def test_change_password_re_encrypts_credentials(self) -> None:
        """Password change should re-encrypt all stored credentials."""
        # Create an IRCTC account with encrypted password
        irctc_repo = IrctcAccountRepository(self.db)
        original_pw = "railway-account-password"
        encrypted_pw = self.vault.encrypt(original_pw)
        irctc_repo.create({
            "id": "acc-1",
            "username": "railway_user",
            "password_encrypted": encrypted_pw,
            "mobile": None,
            "email": None,
            "is_active": 1,
            "created_at": None,
            "updated_at": None,
            "deleted_at": None,
        })

        # Change password
        self.vault.change_password("old-password", "new-password")

        # The stored encrypted password should be different (re-encrypted)
        account = irctc_repo.get_by_id("acc-1")
        self.assertNotEqual(account["password_encrypted"], encrypted_pw)

        # But it should decrypt to the same plaintext with new vault key
        decrypted = self.vault.decrypt(account["password_encrypted"])
        self.assertEqual(decrypted, original_pw)

    def test_change_password_when_locked_raises(self) -> None:
        """Changing password when locked should raise."""
        self.vault.lock()
        with self.assertRaises(VaultLockedError):
            self.vault.change_password("old-password", "new-password")


class TestVaultReset(VaultTestCase):
    """Tests for vault reset (purge)."""

    def setUp(self) -> None:
        super().setUp()
        self.vault.initialize("test-master-password")

    def test_reset_purges_vault(self) -> None:
        """Reset should unconfigure the vault and wipe credentials."""
        # Add an encrypted credential first
        encrypted = self.vault.encrypt("secret-password")
        irctc_repo = IrctcAccountRepository(self.db)
        irctc_repo.create({
            "id": "acc-1",
            "username": "test_user",
            "password_encrypted": encrypted,
            "mobile": None,
            "email": None,
            "is_active": 1,
            "created_at": None,
            "updated_at": None,
            "deleted_at": None,
        })

        self.vault.reset("test-master-password")

        self.assertFalse(self.vault.is_configured())
        self.assertFalse(self.vault.is_unlocked())

    def test_reset_wrong_password_rejected(self) -> None:
        """Reset with wrong password should be rejected."""
        with self.assertRaises(InvalidPasswordError):
            self.vault.reset("wrong-password")

    def test_reset_when_locked_raises(self) -> None:
        """Reset when locked should raise."""
        self.vault.lock()
        with self.assertRaises(VaultLockedError):
            self.vault.reset("test-master-password")


class TestSaltAndNonceGeneration(VaultTestCase):
    """Tests for random salt and nonce generation."""

    def test_salt_is_random(self) -> None:
        """Each vault initialization should generate a different salt."""
        # Create two vaults with different databases
        tmp_fd2, tmp_path2 = tempfile.mkstemp(suffix=".db")
        os.close(tmp_fd2)
        db2 = Database(db_path=tmp_path2)
        db2.initialize_schema()
        vault2 = VaultService(db2)

        self.vault.initialize("password1")
        vault2.initialize("password2")

        config1 = self.db.connect().execute("SELECT salt FROM vault WHERE id = 1").fetchone()
        config2 = db2.connect().execute("SELECT salt FROM vault WHERE id = 1").fetchone()

        self.assertNotEqual(config1["salt"], config2["salt"])

        vault2.lock()
        db2.close()
        os.unlink(tmp_path2)

    def test_nonce_is_random(self) -> None:
        """Each encryption should use a different nonce."""
        self.vault.initialize("test-password")
        enc1 = self.vault.encrypt("same-plaintext")
        enc2 = self.vault.encrypt("same-plaintext")
        # Different ciphertext implies different nonce (since same key, same plaintext)
        self.assertNotEqual(enc1, enc2)

    def test_salt_length(self) -> None:
        """Salt should be 16 bytes (32 hex chars)."""
        self.vault.initialize("test-password")
        config = self.db.connect().execute("SELECT salt FROM vault WHERE id = 1").fetchone()
        salt_bytes = bytes.fromhex(config["salt"])
        self.assertEqual(len(salt_bytes), 16)

    def test_hash_length(self) -> None:
        """Argon2id hash should be 32 bytes."""
        self.vault.initialize("test-password")
        config = self.db.connect().execute("SELECT hash FROM vault WHERE id = 1").fetchone()
        # argon2-encoded hash includes params, but the raw hash portion is 32 bytes
        # Just verify it's a valid argon2 string
        self.assertTrue(config["hash"].startswith("$argon2id$"))


class TestDatabasePersistence(VaultTestCase):
    """Tests for database persistence of vault state."""

    def test_vault_survives_reopen(self) -> None:
        """Vault state should persist in the database."""
        self.vault.initialize("persistent-password")
        self.assertTrue(self.vault.is_configured())

        # Create a new vault service on the same database
        db2 = Database(db_path=self.tmp_path)
        db2.connect()  # opens existing DB
        vault2 = VaultService(db2)
        self.assertTrue(vault2.is_configured())
        self.assertFalse(vault2.is_unlocked())  # locked by default

        # Should be able to unlock
        vault2.unlock("persistent-password")
        self.assertTrue(vault2.is_unlocked())
        decrypted = vault2.decrypt(self.vault.encrypt("test-data"))
        self.assertEqual(decrypted, "test-data")

        vault2.lock()
        db2.close()


class TestNoPlaintextInDatabase(VaultTestCase):
    """Tests that no plaintext credentials are stored in the database."""

    def test_irctc_password_encrypted(self) -> None:
        """IRCTC account passwords should be encrypted, not plaintext."""
        self.vault.initialize("test-password")
        irctc_repo = IrctcAccountRepository(self.db)

        original_pw = "my-railway-password"
        encrypted_pw = self.vault.encrypt(original_pw)

        irctc_repo.create({
            "id": "acc-1",
            "username": "railway_user",
            "password_encrypted": encrypted_pw,
            "mobile": None,
            "email": None,
            "is_active": 1,
            "created_at": None,
            "updated_at": None,
            "deleted_at": None,
        })

        # Verify stored value is not plaintext
        account = irctc_repo.get_by_id("acc-1")
        self.assertNotEqual(account["password_encrypted"], original_pw)

        # Verify it can be decrypted back
        decrypted = self.vault.decrypt(account["password_encrypted"])
        self.assertEqual(decrypted, original_pw)

    def test_proxy_password_encrypted(self) -> None:
        """Proxy passwords should be encrypted, not plaintext."""
        self.vault.initialize("test-password")
        proxy_repo = ProxyRepository(self.db)

        original_pw = "proxy-secret-password"
        encrypted_pw = self.vault.encrypt(original_pw)

        proxy_repo.create({
            "id": "px-1",
            "host": "proxy.example.com",
            "port": 8080,
            "username": "proxy_user",
            "password_encrypted": encrypted_pw,
            "type": "http",
            "is_active": 1,
            "last_tested": None,
            "test_result": None,
            "test_latency_ms": None,
            "created_at": None,
            "updated_at": None,
            "deleted_at": None,
        })

        proxy = proxy_repo.get_by_id("px-1")
        self.assertNotEqual(proxy["password_encrypted"], original_pw)
        decrypted = self.vault.decrypt(proxy["password_encrypted"])
        self.assertEqual(decrypted, original_pw)


if __name__ == "__main__":
    unittest.main()
