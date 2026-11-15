"""Proxy service layer.

Coordinates between the UI, repository layer, and master vault
for proxy configuration and management.

Features:
- CRUD operations for HTTP, HTTPS, and SOCKS5 proxies
- Vault-backed password encryption
- Active proxy toggle (single active proxy constraint)
- Socket-based latency and connectivity testing
"""

from __future__ import annotations

import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal

from bingo_linux.database.database import Database
from bingo_linux.repositories.proxy_repository import ProxyRepository
from bingo_linux.security.vault import (
    VaultLockedError,
    VaultNotConfiguredError,
    VaultService,
)


class ProxyServiceError(Exception):
    """Base exception for proxy service errors."""


class ProxyNotFoundError(ProxyServiceError):
    """Raised when a proxy is not found."""


class InvalidProxyError(ProxyServiceError):
    """Raised when invalid proxy parameters are provided."""


class VaultRequiredError(ProxyServiceError):
    """Raised when vault is required to encrypt/decrypt proxy credentials."""


SUPPORTED_PROXY_TYPES = ("http", "https", "socks5")


class ProxyService(QObject):
    """Service for managing network proxy configurations.

    Attributes:
        proxies_changed: Qt Signal emitted when proxies are added, modified, or deleted.
    """

    proxies_changed = Signal()

    def __init__(self, db: Database, vault: VaultService) -> None:
        """Initialize the proxy service.

        Args:
            db: Database instance.
            vault: VaultService instance.
        """
        super().__init__()
        self._db = db
        self._vault = vault
        self._repo = ProxyRepository(db)

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def list_proxies(self, include_deleted: bool = False) -> list[dict[str, Any]]:
        """List all proxies.

        Args:
            include_deleted: Whether to include soft-deleted proxies.

        Returns:
            List of proxy dicts with password_encrypted omitted.
        """
        if include_deleted:
            proxies = self._repo.list_all()
        else:
            proxies = self._repo.list_all("deleted_at IS NULL")

        for p in proxies:
            p.pop("password_encrypted", None)
        return proxies

    def get_proxy(self, proxy_id: str, reveal_password: bool = False) -> dict[str, Any]:
        """Get a single proxy by ID.

        Args:
            proxy_id: UUID of the proxy.
            reveal_password: If True, decrypts password from the vault.

        Returns:
            Proxy dictionary.

        Raises:
            ProxyNotFoundError: If proxy does not exist or is deleted.
            VaultRequiredError: If reveal_password is True but vault is locked.
        """
        proxy = self._repo.get_by_id(proxy_id)
        if proxy is None or proxy.get("deleted_at") is not None:
            raise ProxyNotFoundError(f"Proxy '{proxy_id}' not found")

        encrypted_pw = proxy.get("password_encrypted")
        proxy.pop("password_encrypted", None)

        if reveal_password:
            if not encrypted_pw:
                proxy["password"] = None
            else:
                if not self._vault.is_configured():
                    raise VaultRequiredError("Vault is not configured")
                if not self._vault.is_unlocked():
                    raise VaultRequiredError("Vault is locked")
                proxy["password"] = self._vault.decrypt(encrypted_pw)

        return proxy

    def get_active_proxy(self) -> Optional[dict[str, Any]]:
        """Get the currently active proxy, if any.

        Returns:
            Active proxy dictionary without encrypted password, or None.
        """
        proxy = self._repo.get_active()
        if proxy:
            proxy.pop("password_encrypted", None)
        return proxy

    # ------------------------------------------------------------------
    # Mutation operations
    # ------------------------------------------------------------------

    def add_proxy(
        self,
        host: str,
        port: int,
        proxy_type: str = "http",
        username: Optional[str] = None,
        password: Optional[str] = None,
        is_active: bool = False,
    ) -> str:
        """Add a new proxy.

        Args:
            host: IP or hostname.
            port: Port number (1-65535).
            proxy_type: 'http', 'https', or 'socks5'.
            username: Optional authentication username.
            password: Optional authentication password (encrypted via vault).
            is_active: Whether to activate this proxy immediately.

        Returns:
            The created proxy UUID string.

        Raises:
            InvalidProxyError: On invalid input.
            VaultRequiredError: If password is provided but vault is locked.
        """
        host = host.strip() if host else ""
        if not host:
            raise InvalidProxyError("Host cannot be empty")

        if not isinstance(port, int) or port < 1 or port > 65535:
            raise InvalidProxyError(f"Invalid port: {port}. Must be between 1 and 65535")

        proxy_type = proxy_type.lower().strip()
        if proxy_type not in SUPPORTED_PROXY_TYPES:
            raise InvalidProxyError(
                f"Unsupported proxy type '{proxy_type}'. Must be one of: {SUPPORTED_PROXY_TYPES}"
            )

        encrypted_password: Optional[str] = None
        if password:
            if not self._vault.is_configured():
                raise VaultRequiredError("Vault is not configured")
            if not self._vault.is_unlocked():
                raise VaultRequiredError("Vault is locked")
            encrypted_password = self._vault.encrypt(password)

        proxy_id = str(uuid.uuid4())

        if is_active:
            self._deactivate_all()

        self._repo.create({
            "id": proxy_id,
            "host": host,
            "port": port,
            "username": username.strip() if username else None,
            "password_encrypted": encrypted_password,
            "type": proxy_type,
            "is_active": 1 if is_active else 0,
            "last_tested": None,
            "test_result": None,
            "test_latency_ms": None,
            "created_at": None,
            "updated_at": None,
            "deleted_at": None,
        })

        self.proxies_changed.emit()
        return proxy_id

    def update_proxy(
        self,
        proxy_id: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        proxy_type: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        """Update an existing proxy.

        Args:
            proxy_id: ID of the proxy to update.
            host: New host, if provided.
            port: New port, if provided.
            proxy_type: New type, if provided.
            username: New username, if provided.
            password: New password (encrypted), or empty string to remove.
            is_active: Active state.

        Returns:
            True if updated.

        Raises:
            ProxyNotFoundError: If proxy does not exist.
            InvalidProxyError: On validation failure.
            VaultRequiredError: If password is provided but vault is locked.
        """
        existing = self._repo.get_by_id(proxy_id)
        if existing is None or existing.get("deleted_at") is not None:
            raise ProxyNotFoundError(f"Proxy '{proxy_id}' not found")

        updates: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if host is not None:
            host_clean = host.strip()
            if not host_clean:
                raise InvalidProxyError("Host cannot be empty")
            updates["host"] = host_clean

        if port is not None:
            if not isinstance(port, int) or port < 1 or port > 65535:
                raise InvalidProxyError(f"Invalid port: {port}. Must be between 1 and 65535")
            updates["port"] = port

        if proxy_type is not None:
            type_clean = proxy_type.lower().strip()
            if type_clean not in SUPPORTED_PROXY_TYPES:
                raise InvalidProxyError(
                    f"Unsupported proxy type '{type_clean}'. Must be one of: {SUPPORTED_PROXY_TYPES}"
                )
            updates["type"] = type_clean

        if username is not None:
            updates["username"] = username.strip() if username else None

        if password is not None:
            if password == "":
                updates["password_encrypted"] = None
            else:
                if not self._vault.is_configured():
                    raise VaultRequiredError("Vault is not configured")
                if not self._vault.is_unlocked():
                    raise VaultRequiredError("Vault is locked")
                updates["password_encrypted"] = self._vault.encrypt(password)

        if is_active is not None:
            if is_active:
                self._deactivate_all()
                updates["is_active"] = 1
            else:
                updates["is_active"] = 0

        success = self._repo.update(proxy_id, updates)
        if success:
            self.proxies_changed.emit()
        return success

    def delete_proxy(self, proxy_id: str) -> bool:
        """Soft-delete a proxy.

        Args:
            proxy_id: UUID of proxy to delete.

        Returns:
            True if soft-deleted.

        Raises:
            ProxyNotFoundError: If proxy not found.
        """
        existing = self._repo.get_by_id(proxy_id)
        if existing is None or existing.get("deleted_at") is not None:
            raise ProxyNotFoundError(f"Proxy '{proxy_id}' not found")

        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.connect()
        cursor = conn.execute(
            "UPDATE proxies SET deleted_at = ?, is_active = 0, updated_at = ? WHERE id = ?",
            (now, now, proxy_id),
        )
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            self.proxies_changed.emit()
        return success

    def set_active(self, proxy_id: Optional[str]) -> bool:
        """Set the single active proxy, or deactivate all if proxy_id is None.

        Args:
            proxy_id: UUID of proxy to activate, or None to deactivate all.

        Returns:
            True if successful.

        Raises:
            ProxyNotFoundError: If non-None proxy_id does not exist.
        """
        self._deactivate_all()
        if proxy_id is None:
            self.proxies_changed.emit()
            return True

        existing = self._repo.get_by_id(proxy_id)
        if existing is None or existing.get("deleted_at") is not None:
            raise ProxyNotFoundError(f"Proxy '{proxy_id}' not found")

        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.connect()
        cursor = conn.execute(
            "UPDATE proxies SET is_active = 1, updated_at = ? WHERE id = ?",
            (now, proxy_id),
        )
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            self.proxies_changed.emit()
        return success

    def _deactivate_all(self) -> None:
        """Internal helper to set is_active=0 for all proxies."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.connect()
        conn.execute("UPDATE proxies SET is_active = 0, updated_at = ?", (now,))
        conn.commit()

    # ------------------------------------------------------------------
    # Connectivity testing
    # ------------------------------------------------------------------

    def test_proxy(self, proxy_id: str, timeout: float = 3.0) -> dict[str, Any]:
        """Test TCP reachability and measure connection latency of a proxy.

        Args:
            proxy_id: UUID of the proxy.
            timeout: Socket timeout in seconds.

        Returns:
            Dict with 'success', 'latency_ms', 'message'.

        Raises:
            ProxyNotFoundError: If proxy does not exist.
        """
        proxy = self._repo.get_by_id(proxy_id)
        if proxy is None or proxy.get("deleted_at") is not None:
            raise ProxyNotFoundError(f"Proxy '{proxy_id}' not found")

        host = proxy["host"]
        port = int(proxy["port"])

        start_time = time.perf_counter()
        success = False
        message = ""
        latency_ms: Optional[int] = None

        try:
            with socket.create_connection((host, port), timeout=timeout):
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                success = True
                message = f"Connected in {latency_ms} ms"
        except socket.timeout:
            message = f"Connection timed out after {timeout}s"
        except ConnectionRefusedError:
            message = "Connection refused"
        except Exception as exc:
            message = f"Connection failed: {str(exc)}"

        now = datetime.now(timezone.utc).isoformat()
        self._repo.update(proxy_id, {
            "last_tested": now,
            "test_result": "success" if success else message,
            "test_latency_ms": latency_ms,
            "updated_at": now,
        })
        self.proxies_changed.emit()

        return {
            "success": success,
            "latency_ms": latency_ms,
            "message": message,
        }
