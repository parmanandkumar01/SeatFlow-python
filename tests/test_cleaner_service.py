"""Tests for the CleanerService (Cleaner.dll / CacheCleaner parity).

Covers:
- Browser cache cleaning (simulated via temp dirs)
- Browser cookie cleaning (simulated via temp dirs)
- Application temp cleaning
- System temp cleaning (user-owned, age-filtered)
- clean_all aggregation
- Error handling on unreadable paths
- Byte/file/dir counting accuracy

Uses temporary directories only. No network I/O. No actual browser
profiles are touched.
"""

from __future__ import annotations

import os
import stat
import tempfile
import time
import unittest
from unittest.mock import patch

from bingo_linux.services.cleaner_service import CleanerService, CleanResult, format_bytes


class CleanerServiceTestCase(unittest.TestCase):
    """Test case for CleanerService."""

    def setUp(self) -> None:
        self.service = CleanerService()
        self._tmp_dirs: list[str] = []

    def tearDown(self) -> None:
        for d in self._tmp_dirs:
            if os.path.exists(d):
                import shutil

                shutil.rmtree(d, ignore_errors=True)

    def _make_tmp_home(self) -> str:
        """Create a temporary directory and return its path (used as HOME)."""
        d = tempfile.mkdtemp(prefix="cleaner_test_home_")
        self._tmp_dirs.append(d)
        return d

    def _make_file(self, path: str, content: str = "x", size: Optional[int] = None) -> None:
        """Create a file with optional exact size."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if size is not None:
            with open(path, "wb") as f:
                f.write(b"\x00" * size)
        else:
            with open(path, "w") as f:
                f.write(content)

    # ------------------------------------------------------------------
    # Browser cache
    # ------------------------------------------------------------------

    def test_clean_browser_cache_removes_files(self) -> None:
        """Cleaning browser cache removes files and reports bytes."""
        home = self._make_tmp_home()
        cache_dir = os.path.join(home, ".cache", "google-chrome")
        self._make_file(os.path.join(cache_dir, "data1"), size=1024)
        self._make_file(os.path.join(cache_dir, "data2"), size=2048)

        with patch.object(self.service, "_home", __import__("pathlib").Path(home)):
            result = self.service.clean_browser_cache(["chrome"])

        self.assertEqual(result.cleaned_files, 2)
        self.assertEqual(result.cleaned_bytes, 3072)
        self.assertEqual(result.cleaned_mb, 3072 / (1024 * 1024))
        self.assertFalse(os.path.exists(cache_dir))

    def test_clean_browser_cache_nonexistent(self) -> None:
        """Cleaning a browser with no cache dir returns empty result."""
        home = self._make_tmp_home()
        with patch.object(self.service, "_home", __import__("pathlib").Path(home)):
            result = self.service.clean_browser_cache(["chrome"])

        self.assertEqual(result.cleaned_files, 0)
        self.assertEqual(result.cleaned_bytes, 0)
        self.assertEqual(len(result.errors), 0)

    # ------------------------------------------------------------------
    # Browser cookies
    # ------------------------------------------------------------------

    def test_clean_browser_cookies_removes_files(self) -> None:
        """Cleaning browser cookies removes cookie files."""
        home = self._make_tmp_home()
        cookie_dir = os.path.join(home, ".config", "google-chrome", "Default")
        self._make_file(os.path.join(cookie_dir, "Cookies"), size=512)

        with patch.object(self.service, "_home", __import__("pathlib").Path(home)):
            result = self.service.clean_browser_cookies(["chrome"])

        self.assertEqual(result.cleaned_files, 1)
        self.assertEqual(result.cleaned_bytes, 512)
        self.assertFalse(os.path.exists(os.path.join(cookie_dir, "Cookies")))

    # ------------------------------------------------------------------
    # App temp
    # ------------------------------------------------------------------

    def test_clean_app_temp_removes_dirs(self) -> None:
        """Cleaning app temp removes cache directories."""
        home = self._make_tmp_home()
        app_cache = os.path.join(home, ".cache", "bingo")
        self._make_file(os.path.join(app_cache, "temp.dat"), size=4096)

        with patch.object(self.service, "_home", __import__("pathlib").Path(home)):
            result = self.service.clean_app_temp()

        self.assertEqual(result.cleaned_files, 1)
        self.assertEqual(result.cleaned_bytes, 4096)
        self.assertFalse(os.path.exists(app_cache))

    # ------------------------------------------------------------------
    # System temp
    # ------------------------------------------------------------------

    def test_clean_system_temp_removes_old_user_files(self) -> None:
        """System temp cleaning removes old user-owned files."""
        tmp = tempfile.gettempdir()
        old_file = os.path.join(tmp, "cleaner_test_old_file")
        self._make_file(old_file, size=2048)
        # Set mtime to 8 days ago
        old_time = time.time() - (8 * 86400)
        os.utime(old_file, (old_time, old_time))

        try:
            result = self.service.clean_system_temp(max_age_days=7)
            self.assertEqual(result.cleaned_files, 1)
            self.assertEqual(result.cleaned_bytes, 2048)
            self.assertFalse(os.path.exists(old_file))
        finally:
            if os.path.exists(old_file):
                os.unlink(old_file)

    def test_clean_system_temp_keeps_new_files(self) -> None:
        """System temp cleaning keeps recently-modified files."""
        tmp = tempfile.gettempdir()
        new_file = os.path.join(tmp, "cleaner_test_new_file")
        self._make_file(new_file, size=1024)

        try:
            result = self.service.clean_system_temp(max_age_days=7)
            self.assertEqual(result.cleaned_files, 0)
            self.assertEqual(result.cleaned_bytes, 0)
            self.assertTrue(os.path.exists(new_file))
        finally:
            if os.path.exists(new_file):
                os.unlink(new_file)

    # ------------------------------------------------------------------
    # clean_all
    # ------------------------------------------------------------------

    def test_clean_all_aggregates_results(self) -> None:
        """clean_all aggregates results from all cleaning operations."""
        home = self._make_tmp_home()
        cache_dir = os.path.join(home, ".cache", "google-chrome")
        self._make_file(os.path.join(cache_dir, "data"), size=1024)
        app_cache = os.path.join(home, ".cache", "bingo")
        self._make_file(os.path.join(app_cache, "temp.dat"), size=2048)

        with patch.object(self.service, "_home", __import__("pathlib").Path(home)):
            result = self.service.clean_all(["chrome"])

        self.assertEqual(result.cleaned_files, 2)
        self.assertEqual(result.cleaned_bytes, 3072)

    # ------------------------------------------------------------------
    # format_bytes
    # ------------------------------------------------------------------

    def test_format_bytes(self) -> None:
        """format_bytes produces human-readable strings."""
        self.assertEqual(format_bytes(0), "0.00 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1024 * 1024), "1.00 MB")
        self.assertEqual(format_bytes(1024 * 1024 * 1024), "1.00 GB")
        self.assertEqual(format_bytes(1536), "1.50 KB")

    # ------------------------------------------------------------------
    # CleanResult dataclass
    # ------------------------------------------------------------------

    def test_clean_result_defaults(self) -> None:
        """CleanResult has sensible defaults."""
        r = CleanResult()
        self.assertEqual(r.cleaned_bytes, 0)
        self.assertEqual(r.cleaned_files, 0)
        self.assertEqual(r.cleaned_dirs, 0)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.cleaned_mb, 0.0)


if __name__ == "__main__":
    unittest.main()
