"""
Central Scheme Registry for Scheme-Intel.
Enables pluggable multi-scheme discovery and isolation across the platform.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from .models import SchemeConfig, SchemeSource, SchemeStock
from ..logger import get_logger

logger = get_logger(__name__)


class SchemeRegistry:
    """Central registry holding registered government schemes."""

    _schemes: Dict[str, SchemeConfig] = {}
    _active_scheme_id: str = "gobardhan"

    @classmethod
    def ensure_defaults(cls) -> None:
        """Ensure standard schemes (GOBARdhan, Samudra Manthan) are registered."""
        if "gobardhan" not in cls._schemes:
            try:
                from .gobardhan.config import GOBARDHAN_CONFIG
                cls.register(GOBARDHAN_CONFIG)
            except Exception as e:
                logger.debug("Failed auto-registering GOBARdhan: %s", e)

        if "samudra_manthan" not in cls._schemes:
            try:
                from .samudra_manthan.config import SAMUDRA_MANTHAN_CONFIG
                cls.register(SAMUDRA_MANTHAN_CONFIG)
            except Exception as e:
                logger.debug("Failed auto-registering Samudra Manthan: %s", e)

    @classmethod
    def register(cls, scheme: SchemeConfig) -> None:
        """Register a new scheme configuration."""
        cls._schemes[scheme.id.lower()] = scheme
        logger.debug("Registered scheme: %s (%s)", scheme.name, scheme.id)

    @classmethod
    def register_scheme(cls, scheme: SchemeConfig) -> None:
        """Alias for register to adhere to specification."""
        cls.register(scheme)

    @classmethod
    def get(cls, scheme_id: str) -> Optional[SchemeConfig]:
        """Retrieve a registered scheme by ID."""
        cls.ensure_defaults()
        return cls._schemes.get(scheme_id.lower())

    @classmethod
    def get_scheme(cls, scheme_id: str) -> Optional[SchemeConfig]:
        """Alias for get to adhere to specification."""
        return cls.get(scheme_id)

    @classmethod
    def get_config(cls, scheme_id: str) -> Optional[SchemeConfig]:
        """Retrieve the configuration for a given scheme."""
        return cls.get(scheme_id)

    @classmethod
    def is_enabled(cls, scheme_id: str) -> bool:
        """Check if a registered scheme is currently enabled."""
        scheme = cls.get(scheme_id)
        return bool(scheme and scheme.enabled)

    @classmethod
    def get_sources(cls, scheme_id: str) -> List[SchemeSource]:
        """Get all configured sources for a scheme."""
        scheme = cls.get(scheme_id)
        return scheme.sources if scheme else []

    @classmethod
    def get_watchlist(cls, scheme_id: str) -> List[SchemeStock]:
        """Get the full watchlist for a scheme."""
        scheme = cls.get(scheme_id)
        return scheme.watchlist if scheme else []

    @classmethod
    def get_rules(cls, scheme_id: str) -> Dict[str, Any]:
        """Get the rules dictionary for a scheme."""
        scheme = cls.get(scheme_id)
        return scheme.rules if scheme else {}

    @classmethod
    def get_active(cls) -> SchemeConfig:
        """Get the default active scheme (defaults to GOBARdhan)."""
        cls.ensure_defaults()
        scheme = cls.get(cls._active_scheme_id)
        if not scheme:
            from .gobardhan.config import GOBARDHAN_CONFIG
            cls.register(GOBARDHAN_CONFIG)
            return GOBARDHAN_CONFIG
        return scheme

    @classmethod
    def set_active(cls, scheme_id: str) -> None:
        """Set the process-level default fallback scheme ID."""
        cls.ensure_defaults()
        if scheme_id.lower() not in cls._schemes:
            raise KeyError(f"Scheme '{scheme_id}' is not registered.")
        cls._active_scheme_id = scheme_id.lower()

    @classmethod
    def list_schemes(cls) -> List[SchemeConfig]:
        """Return all registered schemes."""
        cls.ensure_defaults()
        return list(cls._schemes.values())

    @classmethod
    def list_scheme_ids(cls) -> List[str]:
        """Return all registered scheme IDs."""
        cls.ensure_defaults()
        return list(cls._schemes.keys())

    @classmethod
    def get_active_schemes(cls) -> List[SchemeConfig]:
        """Return all registered schemes that are currently enabled."""
        cls.ensure_defaults()
        return [s for s in cls._schemes.values() if s.enabled]

    @classmethod
    def clear(cls) -> None:
        """Clear the registry (useful for testing)."""
        cls._schemes.clear()
        cls._active_scheme_id = "gobardhan"
