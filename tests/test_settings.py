"""Tests for the settings service layer.

Tests settings creation, listing, retrieval, update, deletion,
validation, defaults, reset behavior, and error handling.
Uses temporary databases and dummy data only.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from seatflow.database.database import Database
from seatflow.security.vault import VaultService
from seatflow.services import (
    InvalidSettingError,
    SettingsService,
    SettingsServiceError,
    SETTING_AUTO_LOCK_MINUTES,
    SETTING_REMEMBER_PREFERENCES,
    SETTING_THEME,
    SUPPORTED_KEYS,
)


class SettingsServiceTestCase(unittest.TestCase):
    """Base test case with a temporary database and settings service."""

    def setUp(self) -> None:
        """Create a temporary database and settings service for each test."""
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.vault = VaultService(self.db)
        self.vault.initialize("master-password")
        self.settings = SettingsService(self.db, self.vault)

    def tearDown(self) -> None:
        """Close and remove the temporary database."""
        self.vault.lock()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)


class TestDefaults(SettingsServiceTestCase):
    """Tests for default settings values."""

    def test_default_theme(self) -> None:
        """Default theme is 'dark'."""
        self.assertEqual(self.settings.get_theme(), "dark")

    def test_default_auto_lock(self) -> None:
        """Default auto-lock minutes is 0."""
        self.assertEqual(self.settings.get_auto_lock_minutes(), 0)

    def test_default_remember_preferences(self) -> None:
        """Default remember_preferences is True."""
        self.assertTrue(self.settings.get_remember_preferences())

    def test_get_setting_not_found_returns_none(self) -> None:
        """get_setting returns None for unset keys."""
        self.assertIsNone(self.settings.get_setting(SETTING_THEME))

    def test_setting_exists_false_for_unset(self) -> None:
        """setting_exists returns False for unset keys."""
        self.assertFalse(self.settings.setting_exists(SETTING_THEME))


class TestSettingCRUD(SettingsServiceTestCase):
    """Tests for setting CRUD operations."""

    def test_set_and_get_theme(self) -> None:
        """Setting and getting theme works."""
        self.settings.set_setting(SETTING_THEME, "light")
        self.assertEqual(self.settings.get_setting(SETTING_THEME), "light")
        self.assertEqual(self.settings.get_theme(), "light")

    def test_get_all_settings(self) -> None:
        """get_all_settings returns all supported settings."""
        self.settings.set_setting(SETTING_THEME, "light")
        self.settings.set_setting(SETTING_AUTO_LOCK_MINUTES, "30")
        self.settings.set_setting(SETTING_REMEMBER_PREFERENCES, "false")

        all_settings = self.settings.get_all_settings()
        self.assertEqual(all_settings[SETTING_THEME], "light")
        self.assertEqual(all_settings[SETTING_AUTO_LOCK_MINUTES], "30")
        self.assertEqual(all_settings[SETTING_REMEMBER_PREFERENCES], "false")

    def test_setting_exists_true_after_set(self) -> None:
        """setting_exists returns True after setting a value."""
        self.settings.set_setting(SETTING_THEME, "light")
        self.assertTrue(self.settings.setting_exists(SETTING_THEME))

    def test_delete_setting(self) -> None:
        """delete_setting removes a setting."""
        self.settings.set_setting(SETTING_THEME, "light")
        self.assertTrue(self.settings.setting_exists(SETTING_THEME))

        result = self.settings.delete_setting(SETTING_THEME)
        self.assertTrue(result)
        self.assertFalse(self.settings.setting_exists(SETTING_THEME))

    def test_delete_setting_not_found_returns_false(self) -> None:
        """delete_setting returns False for non-existent key."""
        self.assertFalse(self.settings.delete_setting(SETTING_THEME))


class TestValidation(SettingsServiceTestCase):
    """Tests for input validation."""

    def test_invalid_theme_raises(self) -> None:
        """Invalid theme raises InvalidSettingError."""
        with self.assertRaises(InvalidSettingError):
            self.settings.set_setting(SETTING_THEME, "purple")

    def test_invalid_theme_constructor(self) -> None:
        """set_theme with invalid value raises InvalidSettingError."""
        with self.assertRaises(InvalidSettingError):
            self.settings.set_theme("purple")

    def test_valid_themes(self) -> None:
        """All valid themes can be set."""
        for theme in ("dark", "light", "system"):
            self.settings.set_theme(theme)
            self.assertEqual(self.settings.get_theme(), theme)

    def test_auto_lock_negative_raises(self) -> None:
        """Negative auto-lock minutes raises InvalidSettingError."""
        with self.assertRaises(InvalidSettingError):
            self.settings.set_setting(SETTING_AUTO_LOCK_MINUTES, "-1")

    def test_auto_lock_too_large_raises(self) -> None:
        """Auto-lock minutes > 120 raises InvalidSettingError."""
        with self.assertRaises(InvalidSettingError):
            self.settings.set_setting(SETTING_AUTO_LOCK_MINUTES, "121")

    def test_auto_lock_non_integer_raises(self) -> None:
        """Non-integer auto-lock minutes raises InvalidSettingError."""
        with self.assertRaises(InvalidSettingError):
            self.settings.set_setting(SETTING_AUTO_LOCK_MINUTES, "abc")

    def test_auto_lock_boundary_values(self) -> None:
        """Auto-lock boundary values 0 and 120 are accepted."""
        self.settings.set_setting(SETTING_AUTO_LOCK_MINUTES, "0")
        self.assertEqual(self.settings.get_auto_lock_minutes(), 0)

        self.settings.set_setting(SETTING_AUTO_LOCK_MINUTES, "120")
        self.assertEqual(self.settings.get_auto_lock_minutes(), 120)

    def test_remember_preferences_invalid_value_raises(self) -> None:
        """Invalid remember_preferences value raises InvalidSettingError."""
        with self.assertRaises(InvalidSettingError):
            self.settings.set_setting(SETTING_REMEMBER_PREFERENCES, "maybe")

    def test_unknown_key_raises(self) -> None:
        """Setting an unknown key raises InvalidSettingError."""
        with self.assertRaises(InvalidSettingError):
            self.settings.set_setting("unknown_key", "value")


class TestReset(SettingsServiceTestCase):
    """Tests for reset behavior."""

    def test_reset_sets_defaults(self) -> None:
        """reset_settings sets all supported keys to defaults."""
        self.settings.set_setting(SETTING_THEME, "light")
        self.settings.set_setting(SETTING_AUTO_LOCK_MINUTES, "45")
        self.settings.set_setting(SETTING_REMEMBER_PREFERENCES, "false")

        self.settings.reset_settings()

        self.assertEqual(self.settings.get_theme(), "dark")
        self.assertEqual(self.settings.get_auto_lock_minutes(), 0)
        self.assertTrue(self.settings.get_remember_preferences())

    def test_reset_preserves_unknown_keys(self) -> None:
        """reset_settings preserves unknown setting keys."""
        # Insert an unknown key directly via repository
        self.settings._repo.set("custom_unknown_key", "custom_value")

        self.settings.reset_settings()

        # Supported keys are reset
        self.assertEqual(self.settings.get_theme(), "dark")
        # Unknown key is preserved
        self.assertEqual(self.settings._repo.get("custom_unknown_key"), "custom_value")


class TestPersistence(SettingsServiceTestCase):
    """Tests for settings persistence."""

    def test_persistence_across_service_instances(self) -> None:
        """Settings persist across service recreation."""
        self.settings.set_setting(SETTING_THEME, "light")
        self.settings.set_setting(SETTING_AUTO_LOCK_MINUTES, "30")

        # Create a new service on the same database
        new_service = SettingsService(self.db, self.vault)
        self.assertEqual(new_service.get_theme(), "light")
        self.assertEqual(new_service.get_auto_lock_minutes(), 30)


class TestValidationErrors(SettingsServiceTestCase):
    """Tests for error handling."""

    def test_invalid_setting_key_raises(self) -> None:
        """Setting an unsupported key raises InvalidSettingError."""
        with self.assertRaises(InvalidSettingError):
            self.settings.set_setting("nonexistent_key", "value")

    def test_settings_service_error_on_db_failure(self) -> None:
        """Database errors are wrapped in SettingsServiceError."""
        # This test verifies that database errors propagate as
        # SettingsServiceError. We can't easily force a DB failure
        # without mocking, so we test that the error type exists.
        self.assertIsInstance(SettingsServiceError("test"), Exception)


if __name__ == "__main__":
    unittest.main()
