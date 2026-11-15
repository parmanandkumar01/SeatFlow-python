"""Cleaner utilities service (Cleaner.dll / CacheCleaner parity).

Clean-room Linux implementation of cache, cookie, and temporary artifact
cleaning matching the original Cleaner.dll capabilities. Provides safe,
user-controlled cleaning of browser cache, cookies, and application
temporary files.

No network I/O. All file operations are local and user-initiated.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal


@dataclass
class CleanResult:
    """Result of a cleaning operation."""

    cleaned_bytes: int = 0
    cleaned_files: int = 0
    cleaned_dirs: int = 0
    errors: list[str] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []

    @property
    def cleaned_mb(self) -> float:
        """Return cleaned size in megabytes."""
        return self.cleaned_bytes / (1024 * 1024)


class CleanerService(QObject):
    """Cleans cache, cookies, and temporary artifacts.

    Mirrors the capabilities of the original Cleaner.dll / CacheCleaner:
    - Browser cache (Chrome, Edge, Firefox, Opera, Brave)
    - Browser cookies
    - Application temporary files
    - System temp directory (user-owned files only)

    All operations are user-initiated and emit Qt signals for UI
    integration (wired to SettingsWindow).
    """

    #: Emitted when a cleaning pass starts.
    cleaning_started = Signal()

    #: Emitted when a cleaning pass completes with results.
    cleaning_completed = Signal(object)  # CleanResult

    #: Emitted on error during cleaning.
    cleaning_error = Signal(str)

    # Browser cache subdirectories (relative to home)
    _BROWSER_CACHE_RELATIVE = {
        "chrome": [".cache/google-chrome", ".cache/chromium"],
        "edge": [".cache/microsoft-edge"],
        "firefox": [".cache/mozilla/firefox"],
        "opera": [".cache/opera"],
        "brave": [".cache/brave-browser"],
    }

    # Browser cookie paths (relative to home; glob patterns supported)
    _BROWSER_COOKIE_RELATIVE = {
        "chrome": [
            ".config/google-chrome/Default/Cookies",
            ".config/chromium/Default/Cookies",
        ],
        "edge": [".config/microsoft-edge/Default/Cookies"],
        "firefox": [".mozilla/firefox/*/cookies.sqlite"],
        "opera": [".config/opera/Default/Cookies"],
        "brave": [".config/brave-browser/Default/Cookies"],
    }

    # Application temp/cache directories (relative to home)
    _APP_CACHE_RELATIVE = [
        ".cache/bingo",
        ".local/share/bingo/cache",
        ".bingo/cache",
    ]

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._home = Path.home()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clean_browser_cache(self, browsers: Optional[list[str]] = None) -> CleanResult:
        """Clean browser cache directories.

        Args:
            browsers: List of browser names (chrome, edge, firefox, opera,
                brave). If None, all known browsers are cleaned.

        Returns:
            CleanResult with bytes/files/dirs cleaned and any errors.
        """
        result = CleanResult()
        targets = browsers or list(self._BROWSER_CACHE_RELATIVE.keys())

        self.cleaning_started.emit()

        for browser in targets:
            for rel in self._BROWSER_CACHE_RELATIVE.get(browser, []):
                path = self._home / rel
                if path.exists():
                    try:
                        r = self._remove_path(path)
                        result.cleaned_bytes += r.cleaned_bytes
                        result.cleaned_files += r.cleaned_files
                        result.cleaned_dirs += r.cleaned_dirs
                    except Exception as exc:
                        result.errors.append(f"{browser} cache: {exc}")

        self.cleaning_completed.emit(result)
        return result

    def clean_browser_cookies(self, browsers: Optional[list[str]] = None) -> CleanResult:
        """Clean browser cookie files/databases.

        Args:
            browsers: List of browser names. If None, all known browsers
                are cleaned.

        Returns:
            CleanResult with bytes/files cleaned and any errors.
        """
        result = CleanResult()
        targets = browsers or list(self._BROWSER_COOKIE_RELATIVE.keys())

        self.cleaning_started.emit()

        for browser in targets:
            for rel in self._BROWSER_COOKIE_RELATIVE.get(browser, []):
                pattern = self._home / rel
                if "*" in str(pattern):
                    # Glob pattern (e.g. Firefox profile dirs)
                    parent = pattern.parent
                    name = pattern.name
                    if parent.exists():
                        for match in parent.glob(name):
                            try:
                                r = self._remove_path(match)
                                result.cleaned_bytes += r.cleaned_bytes
                                result.cleaned_files += r.cleaned_files
                            except Exception as exc:
                                result.errors.append(f"{browser} cookies: {exc}")
                elif pattern.exists():
                    try:
                        r = self._remove_path(pattern)
                        result.cleaned_bytes += r.cleaned_bytes
                        result.cleaned_files += r.cleaned_files
                    except Exception as exc:
                        result.errors.append(f"{browser} cookies: {exc}")

        self.cleaning_completed.emit(result)
        return result

    def clean_app_temp(self) -> CleanResult:
        """Clean application temporary/cache directories.

        Returns:
            CleanResult with bytes/files/dirs cleaned and any errors.
        """
        result = CleanResult()
        self.cleaning_started.emit()

        for rel in self._APP_CACHE_RELATIVE:
            path = self._home / rel
            if path.exists():
                try:
                    r = self._remove_path(path)
                    result.cleaned_bytes += r.cleaned_bytes
                    result.cleaned_files += r.cleaned_files
                    result.cleaned_dirs += r.cleaned_dirs
                except Exception as exc:
                    result.errors.append(f"app temp {rel}: {exc}")

        self.cleaning_completed.emit(result)
        return result

    def clean_system_temp(self, max_age_days: int = 7) -> CleanResult:
        """Clean user-owned files in the system temp directory.

        Only removes files older than max_age_days that are owned by the
        current user, to avoid deleting files in use by other processes.

        Args:
            max_age_days: Maximum age in days for temp files to be removed.

        Returns:
            CleanResult with bytes/files cleaned and any errors.
        """
        result = CleanResult()
        temp_dir = Path(tempfile.gettempdir())
        now = time.time()
        max_age_seconds = max_age_days * 86400
        uid = os.getuid()

        self.cleaning_started.emit()

        try:
            for entry in temp_dir.iterdir():
                try:
                    stat = entry.stat()
                    if stat.st_uid != uid:
                        continue
                    age = now - stat.st_mtime
                    if age > max_age_seconds:
                        if entry.is_file() or entry.is_symlink():
                            result.cleaned_bytes += stat.st_size
                            entry.unlink()
                            result.cleaned_files += 1
                        elif entry.is_dir():
                            r = self._remove_path(entry)
                            result.cleaned_bytes += r.cleaned_bytes
                            result.cleaned_files += r.cleaned_files
                            result.cleaned_dirs += r.cleaned_dirs
                except Exception as exc:
                    result.errors.append(f"system temp {entry}: {exc}")
        except Exception as exc:
            result.errors.append(f"system temp scan: {exc}")

        self.cleaning_completed.emit(result)
        return result

    def clean_all(
        self,
        browsers: Optional[list[str]] = None,
        max_age_days: int = 7,
    ) -> CleanResult:
        """Run all cleaning operations in sequence.

        Args:
            browsers: List of browser names to clean cache/cookies for.
            max_age_days: Max age for system temp files.

        Returns:
            Aggregated CleanResult.
        """
        total = CleanResult()
        self.cleaning_started.emit()

        for result in [
            self.clean_browser_cache(browsers),
            self.clean_browser_cookies(browsers),
            self.clean_app_temp(),
            self.clean_system_temp(max_age_days),
        ]:
            total.cleaned_bytes += result.cleaned_bytes
            total.cleaned_files += result.cleaned_files
            total.cleaned_dirs += result.cleaned_dirs
            total.errors.extend(result.errors)

        self.cleaning_completed.emit(total)
        return total

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _remove_path(path: Path) -> CleanResult:
        """Remove a file or directory tree, returning bytes/files/dirs."""
        result = CleanResult()
        if path.is_symlink() or path.is_file():
            try:
                result.cleaned_bytes = path.stat().st_size
                path.unlink()
                result.cleaned_files = 1
            except Exception:
                pass
        elif path.is_dir():
            # Collect all files first, then remove bottom-up
            files = []
            dirs = []
            for child in path.rglob("*"):
                if child.is_file() or child.is_symlink():
                    files.append(child)
                elif child.is_dir():
                    dirs.append(child)

            for child in files:
                try:
                    result.cleaned_bytes += child.stat().st_size
                    child.unlink()
                    result.cleaned_files += 1
                except Exception:
                    pass

            # Remove directories deepest first
            for child in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
                try:
                    child.rmdir()
                    result.cleaned_dirs += 1
                except Exception:
                    pass

            try:
                path.rmdir()
                result.cleaned_dirs += 1
            except Exception:
                pass
        return result


def format_bytes(num_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"
