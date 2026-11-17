"""Abstract base HTTP driver interface for API-driven booking engines."""

from __future__ import annotations

import abc
from typing import Any, Dict, Optional


class BaseHttpDriver(abc.ABC):
    """Interface for direct HTTP / API automation with cookie, header, and TLS session persistence."""

    def __init__(self, proxy_url: Optional[str] = None, timeout: int = 30):
        self.proxy_url = proxy_url
        self.timeout = timeout
        self.headers: Dict[str, str] = {}
        self.cookies: Dict[str, str] = {}

    @abc.abstractmethod
    def set_header(self, key: str, value: str) -> None:
        """Set a default request header."""
        pass

    @abc.abstractmethod
    def get(self, url: str, params: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
        """Perform HTTP GET request."""
        pass

    @abc.abstractmethod
    def post(self, url: str, data: Optional[Any] = None, json: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
        """Perform HTTP POST request."""
        pass

    @abc.abstractmethod
    def close(self) -> None:
        """Close session and release sockets."""
        pass
