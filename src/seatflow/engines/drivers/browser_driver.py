"""Abstract base browser driver interface for browser-based engines."""

from __future__ import annotations

import abc
from typing import Any, Dict, Optional


class BaseBrowserDriver(abc.ABC):
    """Interface for browser control (Chrome, DevTools Protocol, Playwright, or Selenium)."""

    def __init__(self, headless: bool = False, proxy_url: Optional[str] = None):
        self.headless = headless
        self.proxy_url = proxy_url
        self._is_active = False

    @property
    def is_active(self) -> bool:
        """Whether the browser session is currently running."""
        return self._is_active

    @abc.abstractmethod
    def launch(self) -> bool:
        """Launch browser instance."""
        pass

    @abc.abstractmethod
    def navigate(self, url: str, wait_until: str = "load") -> bool:
        """Navigate to URL."""
        pass

    @abc.abstractmethod
    def execute_script(self, script: str, *args: Any) -> Any:
        """Execute JavaScript in page context."""
        pass

    @abc.abstractmethod
    def find_element(self, selector: str, timeout_ms: int = 5000) -> Optional[Any]:
        """Find DOM element by CSS/XPath selector."""
        pass

    @abc.abstractmethod
    def click(self, selector: str) -> bool:
        """Click element matching selector."""
        pass

    @abc.abstractmethod
    def fill(self, selector: str, text: str) -> bool:
        """Fill text into element matching selector."""
        pass

    @abc.abstractmethod
    def close(self) -> None:
        """Close browser and clean up processes."""
        pass
