"""Settings service layer.

Coordinates between the UI, repository layer, and master vault
for application settings management.

All settings data is non-sensitive (no credentials), so vault
encryption is not required for settings fields. The service
validates input, enforces business rules, and coordinates with
the SettingsRepository for persistent storage.
"""

from __future__ import annotations

from typing import Optional

from seatflow.database.database import Database
from seatflow.repositories import SettingsRepository


class SettingsServiceError(Exception):
    """Base exception for settings service errors."""


class InvalidSettingError(SettingsServiceError):
    """Raised when setting data fails validation."""


# Supported setting keys and their default values.
# These defaults are defined by this Python replacement application,
# NOT copied from the original SeatFlow Windows application.
SETTING_THEME = "theme"
SETTING_AUTO_LOCK_MINUTES = "auto_lock_minutes"
SETTING_REMEMBER_PREFERENCES = "remember_preferences"
SETTING_BRIDGE_ENABLED = "bridge_enabled"
SETTING_WORKER_COUNT = "worker_count"
SETTING_CHROME_BINARY = "chrome_binary_path"
SETTING_PNR_ENDPOINT_URL = "pnr_endpoint_url"
SETTING_PNR_COOLDOWN_SECONDS = "pnr_cooldown_seconds"

# All supported setting keys.
SUPPORTED_KEYS = frozenset(
    {
        SETTING_THEME,
        SETTING_AUTO_LOCK_MINUTES,
        SETTING_REMEMBER_PREFERENCES,
        SETTING_BRIDGE_ENABLED,
        SETTING_WORKER_COUNT,
        SETTING_CHROME_BINARY,
        SETTING_PNR_ENDPOINT_URL,
        SETTING_PNR_COOLDOWN_SECONDS,
    }
)

# Default values for each supported setting key.
DEFAULT_VALUES: dict[str, str] = {
    SETTING_THEME: "dark",
    SETTING_AUTO_LOCK_MINUTES: "0",
    SETTING_REMEMBER_PREFERENCES: "true",
    SETTING_BRIDGE_ENABLED: "false",
    SETTING_WORKER_COUNT: "1",
    SETTING_CHROME_BINARY: "",
    SETTING_PNR_ENDPOINT_URL: "",
    SETTING_PNR_COOLDOWN_SECONDS: "60",
}

# Valid theme values.
VALID_THEMES = frozenset({"dark", "light", "system"})

# Valid auto-lock range (in minutes).
AUTO_LOCK_MIN_MINUTES = 0
AUTO_LOCK_MAX_MINUTES = 120

# Valid concurrent worker range (MW-02: configurable 1-4).
WORKER_COUNT_MIN = 1
WORKER_COUNT_MAX = 4

# PNR sync cooldown bounds (seconds).
PNR_COOLDOWN_MIN_SECONDS = 0
PNR_COOLDOWN_MAX_SECONDS = 3600
PNR_COOLDOWN_DEFAULT_SECONDS = 60


class SettingsService:
    """Service for managing application settings.

    Responsibilities:
    - Get individual setting values
    - Set individual setting values
    - List all settings
    - Validate setting names and values
    - Apply defaults for missing settings
    - Reset supported settings to defaults
    - Provide convenience methods for theme and auto-lock

    Settings are stored in the ``settings`` table as key-value pairs.
    Credentials are never stored here -- they belong in the vault.
    """

    def __init__(self, db, vault=None) -> None:
        """Initialize the settings service.

        Args:
            db: An initialized Database instance.
            vault: An optional VaultService instance for auto-lock
                integration. If None, auto-lock integration is disabled.
        """
        self._db = db
        self._repo = SettingsRepository(db)
        self._vault = vault

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_setting(self, key: str) -> Optional[str]:
        """Return the value for a setting key.

        Args:
            key: The setting key.

        Returns:
            The setting value, or None if not found.
        """
        if key not in SUPPORTED_KEYS:
            return None
        return self._repo.get(key)

    def get_all_settings(self) -> dict[str, str]:
        """Return all supported settings as a dictionary.

        Returns:
            Dictionary mapping setting keys to their values. Only
            supported keys are returned; unknown keys in the database
            are preserved but not exposed through this method.
        """
        all_settings = self._repo.get_all()
        return {k: v for k, v in all_settings.items() if k in SUPPORTED_KEYS}

    def setting_exists(self, key: str) -> bool:
        """Return True if a setting key exists in the database.

        Args:
            key: The setting key.

        Returns:
            True if the key exists and has a non-None value.
        """
        return self._repo.get(key) is not None

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def get_theme(self) -> str:
        """Return the current theme setting.

        Returns:
            One of: "dark", "light", "system". Defaults to "dark".
        """
        value = self._repo.get(SETTING_THEME)
        if value not in VALID_THEMES:
            return DEFAULT_VALUES[SETTING_THEME]
        return value

    def set_theme(self, theme: str) -> None:
        """Set the theme preference.

        Args:
            theme: One of "dark", "light", "system".

        Raises:
            InvalidSettingError: If the theme value is invalid.
        """
        if theme not in VALID_THEMES:
            raise InvalidSettingError(
                f"Invalid theme: {theme!r}. Must be one of: "
                f"{', '.join(sorted(VALID_THEMES))}."
            )
        self._repo.set(SETTING_THEME, theme)

    def get_auto_lock_minutes(self) -> int:
        """Return the auto-lock vault timeout in minutes.

        Returns:
            Auto-lock timeout in minutes. 0 means disabled.
            Defaults to 0.
        """
        value = self._repo.get(SETTING_AUTO_LOCK_MINUTES)
        if value is None:
            return int(DEFAULT_VALUES[SETTING_AUTO_LOCK_MINUTES])
        try:
            minutes = int(value)
        except (ValueError, TypeError):
            return int(DEFAULT_VALUES[SETTING_AUTO_LOCK_MINUTES])
        # Clamp to valid range
        return max(AUTO_LOCK_MIN_MINUTES, min(AUTO_LOCK_MAX_MINUTES, minutes))

    def set_auto_lock_minutes(self, minutes: int) -> None:
        """Set the auto-lock vault timeout in minutes.

        Args:
            minutes: Auto-lock timeout in minutes. 0 means disabled.
                     Must be between 0 and 120 inclusive.

        Raises:
            InvalidSettingError: If the minutes value is out of range.
        """
        if not isinstance(minutes, int) or minutes < AUTO_LOCK_MIN_MINUTES or minutes > AUTO_LOCK_MAX_MINUTES:
            raise InvalidSettingError(
                f"Auto-lock minutes must be an integer between "
                f"{AUTO_LOCK_MIN_MINUTES} and {AUTO_LOCK_MAX_MINUTES}."
            )
        self._repo.set(SETTING_AUTO_LOCK_MINUTES, str(minutes))

    def get_remember_preferences(self) -> bool:
        """Return whether application preferences are remembered.

        Returns:
            True if preferences should be remembered across restarts,
            False otherwise. Defaults to True.
        """
        value = self._repo.get(SETTING_REMEMBER_PREFERENCES)
        if value is None:
            return DEFAULT_VALUES[SETTING_REMEMBER_PREFERENCES] == "true"
        return value.strip().lower() == "true"

    def set_remember_preferences(self, value: bool) -> None:
        """Set whether application preferences are remembered.

        Args:
            value: True to remember preferences, False otherwise.
        """
        self._repo.set(SETTING_REMEMBER_PREFERENCES, "true" if value else "false")

    # ------------------------------------------------------------------
    # Bridge enabled setting
    # ------------------------------------------------------------------

    def get_bridge_enabled(self) -> bool:
        """Return whether the Browser Extension Bridge is enabled.

        Returns:
            True if the bridge is enabled, False otherwise. Defaults
            to False (bridge disabled; clipboard fallback used).
        """
        value = self._repo.get(SETTING_BRIDGE_ENABLED)
        if value is None:
            return DEFAULT_VALUES[SETTING_BRIDGE_ENABLED] == "true"
        return value.strip().lower() == "true"

    def set_bridge_enabled(self, value: bool) -> None:
        """Set whether the Browser Extension Bridge is enabled.

        Args:
            value: True to enable the bridge, False to disable it.
        """
        self._repo.set(SETTING_BRIDGE_ENABLED, "true" if value else "false")

    # ------------------------------------------------------------------
    # Chrome worker settings
    # ------------------------------------------------------------------

    def get_worker_count(self) -> int:
        """Return the configured number of concurrent Chrome workers.

        Returns:
            Worker count between 1 and 4. Defaults to 1.
        """
        value = self._repo.get(SETTING_WORKER_COUNT)
        if value is None:
            return int(DEFAULT_VALUES[SETTING_WORKER_COUNT])
        try:
            count = int(value)
        except (ValueError, TypeError):
            return int(DEFAULT_VALUES[SETTING_WORKER_COUNT])
        return max(WORKER_COUNT_MIN, min(WORKER_COUNT_MAX, count))

    def set_worker_count(self, count: int) -> None:
        """Set the number of concurrent Chrome workers.

        Args:
            count: Worker count between 1 and 4 inclusive.

        Raises:
            InvalidSettingError: If the count is out of range.
        """
        self.set_setting(SETTING_WORKER_COUNT, str(count))

    def get_chrome_binary(self) -> str:
        """Return the configured Chrome/Chromium binary path.

        Returns:
            Absolute path to the Chrome binary, or empty string to let the
            service resolve Chrome from PATH / standard install locations.
        """
        return self._repo.get(SETTING_CHROME_BINARY) or ""

    def set_chrome_binary(self, path: str) -> None:
        """Set the Chrome/Chromium binary path.

        Args:
            path: Absolute path to the Chrome binary, or empty to use
                auto-detection.
        """
        self._repo.set(SETTING_CHROME_BINARY, path)

    # ------------------------------------------------------------------
    # PNR sync settings
    # ------------------------------------------------------------------

    def get_pnr_endpoint_url(self) -> str:
        """Return the configured PNR status endpoint URL.

        Returns:
            The endpoint URL, or empty string if not configured.
            When empty, live PNR refresh is unavailable (blocked pending
            endpoint contract recovery).
        """
        return self._repo.get(SETTING_PNR_ENDPOINT_URL) or ""

    def set_pnr_endpoint_url(self, url: str) -> None:
        """Set the PNR status endpoint URL.

        Args:
            url: An http(s) URL, or empty to disable live PNR refresh.
        """
        self.set_setting(SETTING_PNR_ENDPOINT_URL, url)

    def get_pnr_cooldown_seconds(self) -> int:
        """Return the PNR refresh cooldown in seconds.

        Returns:
            Cooldown between PNR lookups for the same PNR number.
            Defaults to 60 seconds.
        """
        value = self._repo.get(SETTING_PNR_COOLDOWN_SECONDS)
        if value is None:
            return PNR_COOLDOWN_DEFAULT_SECONDS
        try:
            cooldown = int(value)
        except (ValueError, TypeError):
            return PNR_COOLDOWN_DEFAULT_SECONDS
        return max(
            PNR_COOLDOWN_MIN_SECONDS,
            min(PNR_COOLDOWN_MAX_SECONDS, cooldown),
        )

    def set_pnr_cooldown_seconds(self, cooldown: int) -> None:
        """Set the PNR refresh cooldown in seconds.

        Args:
            cooldown: Cooldown between PNR lookups for the same PNR number.

        Raises:
            InvalidSettingError: If the cooldown is out of range.
        """
        self.set_setting(SETTING_PNR_COOLDOWN_SECONDS, str(cooldown))

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def set_setting(self, key: str, value: str) -> None:
        """Set a setting value.

        Args:
            key: The setting key.
            value: The setting value as a string.

        Raises:
            InvalidSettingError: If the key is not supported or the
                value is invalid for the key.
            SettingsServiceError: If persistence fails.
        """
        if key not in SUPPORTED_KEYS:
            raise InvalidSettingError(
                f"Unsupported setting key: {key!r}. Supported keys: "
                f"{', '.join(sorted(SUPPORTED_KEYS))}."
            )

        # Validate value based on key type
        if key == SETTING_THEME:
            if value not in VALID_THEMES:
                raise InvalidSettingError(
                    f"Invalid theme value: {value!r}. Must be one of: "
                    f"{', '.join(sorted(VALID_THEMES))}."
                )
        elif key == SETTING_AUTO_LOCK_MINUTES:
            try:
                minutes = int(value)
            except (ValueError, TypeError):
                raise InvalidSettingError(
                    f"Invalid auto-lock minutes: {value!r}. Must be an integer."
                )
            if minutes < AUTO_LOCK_MIN_MINUTES or minutes > AUTO_LOCK_MAX_MINUTES:
                raise InvalidSettingError(
                    f"Auto-lock minutes {minutes} out of range "
                    f"[{AUTO_LOCK_MIN_MINUTES}-{AUTO_LOCK_MAX_MINUTES}]."
                )
        elif key == SETTING_REMEMBER_PREFERENCES:
            if value.strip().lower() not in ("true", "false"):
                raise InvalidSettingError(
                    f"Invalid remember_preferences value: {value!r}. "
                    f"Must be 'true' or 'false'."
                )
        elif key == SETTING_BRIDGE_ENABLED:
            if value.strip().lower() not in ("true", "false"):
                raise InvalidSettingError(
                    f"Invalid bridge_enabled value: {value!r}. "
                    f"Must be 'true' or 'false'."
                )
        elif key == SETTING_WORKER_COUNT:
            try:
                count = int(value)
            except (ValueError, TypeError):
                raise InvalidSettingError(
                    f"Invalid worker_count value: {value!r}. "
                    f"Must be an integer between {WORKER_COUNT_MIN} and {WORKER_COUNT_MAX}."
                )
            if count < WORKER_COUNT_MIN or count > WORKER_COUNT_MAX:
                raise InvalidSettingError(
                    f"Worker count {count} out of range "
                    f"[{WORKER_COUNT_MIN}-{WORKER_COUNT_MAX}]."
                )
        elif key == SETTING_CHROME_BINARY:
            # Chrome binary path is a free-form filesystem path; no value
            # restriction beyond being a string when present.
            if not isinstance(value, str):
                raise InvalidSettingError(
                    f"Invalid chrome_binary_path value: {value!r}. Must be a string."
                )
        elif key == SETTING_PNR_ENDPOINT_URL:
            # PNR endpoint is a user-configurable URL or empty. Validate that,
            # when non-empty, it parses as an absolute http(s) URL.
            if not isinstance(value, str):
                raise InvalidSettingError(
                    f"Invalid pnr_endpoint_url value: {value!r}. Must be a string."
                )
            if value.strip():
                from urllib.parse import urlparse

                parsed = urlparse(value.strip())
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    raise InvalidSettingError(
                        f"Invalid pnr_endpoint_url value: {value!r}. "
                        f"Must be an http(s) URL or empty."
                    )
        elif key == SETTING_PNR_COOLDOWN_SECONDS:
            try:
                cooldown = int(value)
            except (ValueError, TypeError):
                raise InvalidSettingError(
                    f"Invalid pnr_cooldown_seconds value: {value!r}. "
                    f"Must be an integer between {PNR_COOLDOWN_MIN_SECONDS} and "
                    f"{PNR_COOLDOWN_MAX_SECONDS}."
                )
            if cooldown < PNR_COOLDOWN_MIN_SECONDS or cooldown > PNR_COOLDOWN_MAX_SECONDS:
                raise InvalidSettingError(
                    f"PNR cooldown {cooldown}s out of range "
                    f"[{PNR_COOLDOWN_MIN_SECONDS}-{PNR_COOLDOWN_MAX_SECONDS}]."
                )

        try:
            self._repo.set(key, value)
        except Exception as exc:
            raise SettingsServiceError(f"Failed to save setting {key!r}: {exc}") from exc

    def delete_setting(self, key: str) -> bool:
        """Delete a setting by key.

        Args:
            key: The setting key to delete.

        Returns:
            True if the setting was deleted, False if not found.

        Raises:
            SettingsServiceError: If deletion fails.
        """
        if key not in SUPPORTED_KEYS:
            return False
        try:
            return self._repo.delete(key)
        except Exception as exc:
            raise SettingsServiceError(f"Failed to delete setting {key!r}: {exc}") from exc

    def reset_settings(self) -> None:
        """Reset all supported settings to their default values.

        Unknown settings (not in SUPPORTED_KEYS) are preserved.
        Only supported keys are reset to their documented defaults.
        """
        for key, default_value in DEFAULT_VALUES.items():
            try:
                self._repo.set(key, default_value)
            except Exception as exc:
                raise SettingsServiceError(
                    f"Failed to reset setting {key!r}: {exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Vault integration
    # ------------------------------------------------------------------

    def is_auto_lock_enabled(self) -> bool:
        """Return whether auto-lock is enabled (timeout > 0).

        Returns:
            True if auto-lock is enabled, False otherwise.
        """
        return self.get_auto_lock_minutes() > 0

    def apply_auto_lock(self) -> None:
        """Apply the auto-lock setting to the vault.

        If auto-lock is enabled and the vault service is available,
        this method can be called to trigger vault locking after the
        configured inactivity period. The actual inactivity tracking
        is handled by the UI layer; this method provides the
        configuration value.

        Raises:
            SettingsServiceError: If the vault service is not available.
        """
        if self._vault is None:
            raise SettingsServiceError(
                "Vault service not available for auto-lock integration."
            )
        # The vault service itself handles locking; this service only
        # provides the configuration value. The UI layer is responsible
        # for tracking inactivity and calling vault.lock() when the
        # auto-lock timeout is reached.
