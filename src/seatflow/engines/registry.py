"""Engine Registry & Factory for registering, discovering, and instantiating multiple engines."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

from seatflow.engines.base import BaseBookingEngine, EngineCapability

logger = logging.getLogger(__name__)


@dataclass
class EngineMetadata:
    """Metadata describing a registered booking engine."""
    engine_id: str
    display_name: str
    description: str = ""
    version: str = "1.0.0"
    capabilities: List[EngineCapability] = field(default_factory=list)
    engine_class: Optional[Type[BaseBookingEngine]] = None
    is_default: bool = False


class EngineRegistry:
    """Central registry and factory for all booking engine implementations."""

    _engines: Dict[str, EngineMetadata] = {}
    _default_id: Optional[str] = None
    _discovered: bool = False

    @classmethod
    def register(
        cls,
        engine_id: str,
        display_name: str,
        description: str = "",
        version: str = "1.0.0",
        capabilities: Optional[List[EngineCapability]] = None,
        is_default: bool = False,
    ) -> Callable[[Type[BaseBookingEngine]], Type[BaseBookingEngine]]:
        """Decorator to register a BaseBookingEngine subclass."""

        def decorator(engine_cls: Type[BaseBookingEngine]) -> Type[BaseBookingEngine]:
            meta = EngineMetadata(
                engine_id=engine_id,
                display_name=display_name,
                description=description,
                version=version,
                capabilities=capabilities or [],
                engine_class=engine_cls,
                is_default=is_default,
            )
            cls._engines[engine_id] = meta
            if is_default or cls._default_id is None:
                cls._default_id = engine_id
            logger.info("Registered engine '%s' (%s v%s)", engine_id, display_name, version)
            return engine_cls

        return decorator

    @classmethod
    def get_engine_class(cls, engine_id: str) -> Type[BaseBookingEngine]:
        """Retrieve the engine class by ID."""
        cls._ensure_discovered()
        if engine_id not in cls._engines:
            available = ", ".join(cls._engines.keys()) or "None"
            raise KeyError(f"Unknown engine '{engine_id}'. Available engines: {available}")
        engine_cls = cls._engines[engine_id].engine_class
        if engine_cls is None:
            raise ValueError(f"Engine '{engine_id}' has no registered class implementation")
        return engine_cls

    @classmethod
    def create_engine(cls, engine_id: Optional[str] = None, **kwargs: Any) -> BaseBookingEngine:
        """Instantiate an engine by ID (or default engine)."""
        cls._ensure_discovered()
        target_id = engine_id or cls._default_id
        if not target_id:
            raise ValueError("No engines registered in SeatFlow.")
        engine_cls = cls.get_engine_class(target_id)
        meta = cls._engines[target_id]
        return engine_cls(engine_id=meta.engine_id, name=meta.display_name, capabilities=meta.capabilities, **kwargs)

    @classmethod
    def list_engines(cls) -> List[EngineMetadata]:
        """Return a list of all registered engine metadata."""
        cls._ensure_discovered()
        return list(cls._engines.values())

    @classmethod
    def get_default_engine_id(cls) -> Optional[str]:
        """Return ID of the default engine."""
        cls._ensure_discovered()
        return cls._default_id

    @classmethod
    def set_default_engine_id(cls, engine_id: str) -> None:
        """Explicitly select the default engine."""
        cls._ensure_discovered()
        if engine_id not in cls._engines:
            raise KeyError(f"Engine '{engine_id}' not found in registry")
        cls._default_id = engine_id

    @classmethod
    def clear(cls) -> None:
        """Clear registry (useful for unit tests)."""
        cls._engines.clear()
        cls._default_id = None
        cls._discovered = False

    @classmethod
    def _ensure_discovered(cls) -> None:
        """Auto-discover engine implementations from implementations package."""
        if cls._discovered:
            return
        cls._discovered = True
        try:
            import seatflow.engines.implementations as impl_pkg
            for _, modname, ispkg in pkgutil.iter_modules(impl_pkg.__path__):
                try:
                    importlib.import_module(f"seatflow.engines.implementations.{modname}")
                except Exception as e:
                    logger.warning("Failed to auto-load engine implementation '%s': %s", modname, e)
        except Exception as e:
            logger.debug("Engine implementations package discovery skipped: %s", e)


def register_engine(
    engine_id: str,
    display_name: str,
    description: str = "",
    version: str = "1.0.0",
    capabilities: Optional[List[EngineCapability]] = None,
    is_default: bool = False,
) -> Callable[[Type[BaseBookingEngine]], Type[BaseBookingEngine]]:
    """Helper alias for EngineRegistry.register."""
    return EngineRegistry.register(
        engine_id=engine_id,
        display_name=display_name,
        description=description,
        version=version,
        capabilities=capabilities,
        is_default=is_default,
    )
