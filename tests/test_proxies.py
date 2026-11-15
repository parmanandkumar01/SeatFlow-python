"""Unit tests for the Proxy service layer.

Tests proxy creation, vault-backed credential encryption, updating,
soft deletion, active proxy enforcement, connection testing, and
signal emission.
"""

from __future__ import annotations

import os
import socket
import tempfile
import unittest

from PySide6.QtCore import QCoreApplication

from seatflow.database.database import Database
from seatflow.security.vault import VaultService
from seatflow.services.proxy_service import (
    InvalidProxyError,
    ProxyNotFoundError,
    ProxyService,
    VaultRequiredError,
)


class ProxyServiceTestCase(unittest.TestCase):
    """Base test case with isolated temporary database and vault."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure a QCoreApplication exists for Qt signals."""
        if QCoreApplication.instance() is None:
            cls.app = QCoreApplication([])

    def setUp(self) -> None:
        """Create a temporary database, vault, and ProxyService for each test."""
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.vault = VaultService(self.db)
        self.vault.initialize("test-master-password")
        self.proxy_service = ProxyService(self.db, self.vault)

    def tearDown(self) -> None:
        """Clean up database and vault."""
        self.vault.lock()
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)


class TestProxyCreation(ProxyServiceTestCase):
    """Tests for adding proxies."""

    def test_add_minimal_proxy(self) -> None:
        """Add proxy with required host and port only."""
        proxy_id = self.proxy_service.add_proxy(
            host="127.0.0.1",
            port=8080,
        )
        self.assertTrue(proxy_id)
        proxy = self.proxy_service.get_proxy(proxy_id)
        self.assertEqual(proxy["host"], "127.0.0.1")
        self.assertEqual(proxy["port"], 8080)
        self.assertEqual(proxy["type"], "http")
        self.assertIsNone(proxy["username"])
        self.assertEqual(proxy["is_active"], 0)
        self.assertNotIn("password_encrypted", proxy)

    def test_add_proxy_with_credentials_and_vault(self) -> None:
        """Proxy password is encrypted via the vault."""
        proxy_id = self.proxy_service.add_proxy(
            host="proxy.corp.net",
            port=3128,
            proxy_type="https",
            username="admin",
            password="SecretProxyPassword123!",
            is_active=True,
        )
        proxy = self.proxy_service.get_proxy(proxy_id, reveal_password=True)
        self.assertEqual(proxy["username"], "admin")
        self.assertEqual(proxy["password"], "SecretProxyPassword123!")
        self.assertEqual(proxy["type"], "https")
        self.assertEqual(proxy["is_active"], 1)

    def test_add_proxy_with_password_requires_unlocked_vault(self) -> None:
        """Adding a password when vault is locked raises VaultRequiredError."""
        self.vault.lock()
        with self.assertRaises(VaultRequiredError):
            self.proxy_service.add_proxy(
                host="1.1.1.1",
                port=8080,
                password="secret_pass",
            )

    def test_invalid_host(self) -> None:
        """Empty host raises InvalidProxyError."""
        with self.assertRaises(InvalidProxyError):
            self.proxy_service.add_proxy(host="   ", port=8080)

    def test_invalid_ports(self) -> None:
        """Ports outside 1-65535 raise InvalidProxyError."""
        with self.assertRaises(InvalidProxyError):
            self.proxy_service.add_proxy(host="1.1.1.1", port=0)
        with self.assertRaises(InvalidProxyError):
            self.proxy_service.add_proxy(host="1.1.1.1", port=70000)

    def test_invalid_proxy_type(self) -> None:
        """Unsupported proxy protocols raise InvalidProxyError."""
        with self.assertRaises(InvalidProxyError):
            self.proxy_service.add_proxy(host="1.1.1.1", port=8080, proxy_type="ftp")


class TestProxyListingAndActive(ProxyServiceTestCase):
    """Tests for listing and active proxy enforcement."""

    def test_list_proxies(self) -> None:
        """Listing proxies returns all non-deleted proxies."""
        p1 = self.proxy_service.add_proxy(host="10.0.0.1", port=8080)
        p2 = self.proxy_service.add_proxy(host="10.0.0.2", port=1080, proxy_type="socks5")

        proxies = self.proxy_service.list_proxies()
        self.assertEqual(len(proxies), 2)
        hosts = [p["host"] for p in proxies]
        self.assertIn("10.0.0.1", hosts)
        self.assertIn("10.0.0.2", hosts)

    def test_single_active_proxy_enforcement(self) -> None:
        """Activating a new proxy automatically deactivates the previous active one."""
        p1 = self.proxy_service.add_proxy(host="10.0.0.1", port=8080, is_active=True)
        self.assertEqual(self.proxy_service.get_active_proxy()["id"], p1)

        p2 = self.proxy_service.add_proxy(host="10.0.0.2", port=8080, is_active=True)
        self.assertEqual(self.proxy_service.get_active_proxy()["id"], p2)

        # p1 should now be inactive
        self.assertEqual(self.proxy_service.get_proxy(p1)["is_active"], 0)

    def test_set_active_and_deactivate_all(self) -> None:
        """set_active toggles active proxy or clears all if None."""
        p1 = self.proxy_service.add_proxy(host="10.0.0.1", port=8080)
        self.proxy_service.set_active(p1)
        self.assertEqual(self.proxy_service.get_active_proxy()["id"], p1)

        self.proxy_service.set_active(None)
        self.assertIsNone(self.proxy_service.get_active_proxy())


class TestProxyUpdateAndDeletion(ProxyServiceTestCase):
    """Tests for updating and deleting proxies."""

    def test_update_proxy_fields(self) -> None:
        """Update host, port, type, and username."""
        pid = self.proxy_service.add_proxy(host="10.0.0.1", port=8080)
        self.proxy_service.update_proxy(
            pid,
            host="proxy.new.com",
            port=9090,
            proxy_type="socks5",
            username="user2",
        )
        updated = self.proxy_service.get_proxy(pid)
        self.assertEqual(updated["host"], "proxy.new.com")
        self.assertEqual(updated["port"], 9090)
        self.assertEqual(updated["type"], "socks5")
        self.assertEqual(updated["username"], "user2")

    def test_update_proxy_password(self) -> None:
        """Update encrypted password in vault."""
        pid = self.proxy_service.add_proxy(
            host="10.0.0.1",
            port=8080,
            password="initial_pass",
        )
        self.assertEqual(self.proxy_service.get_proxy(pid, reveal_password=True)["password"], "initial_pass")

        self.proxy_service.update_proxy(pid, password="updated_pass")
        self.assertEqual(self.proxy_service.get_proxy(pid, reveal_password=True)["password"], "updated_pass")

    def test_soft_delete_proxy(self) -> None:
        """Deleting a proxy marks it deleted and deactivates it."""
        pid = self.proxy_service.add_proxy(host="10.0.0.1", port=8080, is_active=True)
        self.proxy_service.delete_proxy(pid)

        self.assertIsNone(self.proxy_service.get_active_proxy())
        self.assertEqual(len(self.proxy_service.list_proxies()), 0)
        with self.assertRaises(ProxyNotFoundError):
            self.proxy_service.get_proxy(pid)


class TestProxyConnectivity(ProxyServiceTestCase):
    """Tests for proxy reachability testing."""

    def test_test_proxy_unreachable(self) -> None:
        """Testing an unreachable port records failure and updates proxy record."""
        # Use localhost with an unbound port
        pid = self.proxy_service.add_proxy(host="127.0.0.1", port=59999)
        result = self.proxy_service.test_proxy(pid, timeout=0.2)

        self.assertFalse(result["success"])
        self.assertIn("Connection", result["message"])

        proxy = self.proxy_service.get_proxy(pid)
        self.assertIsNotNone(proxy["last_tested"])
        self.assertIsNotNone(proxy["test_result"])
        self.assertIsNone(proxy["test_latency_ms"])

    def test_test_proxy_reachable(self) -> None:
        """Testing a reachable local TCP server records latency and success."""
        # Start a dummy listening TCP socket
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        srv.listen(1)

        try:
            pid = self.proxy_service.add_proxy(host="127.0.0.1", port=port)
            result = self.proxy_service.test_proxy(pid, timeout=1.0)

            self.assertTrue(result["success"])
            self.assertIsNotNone(result["latency_ms"])
            self.assertGreaterEqual(result["latency_ms"], 0)

            proxy = self.proxy_service.get_proxy(pid)
            self.assertEqual(proxy["test_result"], "success")
            self.assertIsNotNone(proxy["test_latency_ms"])
        finally:
            srv.close()


if __name__ == "__main__":
    unittest.main()
