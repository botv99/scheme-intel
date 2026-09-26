"""
Central Scheme Registry for Scheme-Intel.
Enables pluggable multi-scheme discovery and isolation across the platform.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from .models import SchemeConfig
from ..logger import get_logger

logger = get_logger(__name__)


class SchemeRegistry:
    """Singleton registry holding registered government schemes."""

    _schemes: Dict[str, SchemeConfig] = {}
    _active_scheme_id: str = "gobardhan"

    @classmethod
    def register(cls, scheme: SchemeConfig) -> None:
        """Register a new scheme configuration."""
        cls._schemes[scheme.id.lower()] = scheme
        logger.debug("Registered scheme: %s (%s)", scheme.name, scheme.id)

    @classmethod
    def get(cls, scheme_id: str) -> Optional[SchemeConfig]:
        """Retrieve a registered scheme by ID."""
        return cls._schemes.get(scheme_id.lower())

    @classmethod
    def get_active(cls) -> SchemeConfig:
        """Get the currently active scheme (defaults to GOBARdhan)."""
        scheme = cls.get(cls._active_scheme_id)
        if not scheme:
            from .gobardhan.config import GOBARDHAN_CONFIG
            cls.register(GOBARDHAN_CONFIG)
            return GOBARDHAN_CONFIG
        return scheme

    @classmethod
    def set_active(cls, scheme_id: str) -> None:
        """Set the active scheme ID."""
        if scheme_id.lower() not in cls._schemes:
            raise KeyError(f"Scheme '{scheme_id}' is not registered.")
        cls._active_scheme_id = scheme_id.lower()

    @classmethod
    def list_schemes(cls) -> List[SchemeConfig]:
        """Return all registered schemes."""
        return list(cls._schemes.values())

    @classmethod
    def list_scheme_ids(cls) -> List[str]:
        """Return all registered scheme IDs."""
        return list(cls._schemes.keys())

    @classmethod
    def get_active_schemes(cls) -> List[SchemeConfig]:
        """Return all registered schemes that are currently enabled."""
        return [s for s in cls._schemes.values() if s.enabled]

    @classmethod
    def clear(cls) -> None:
        """Clear the registry (useful for testing)."""
        cls._schemes.clear()
        cls._active_scheme_id = "gobardhan"

