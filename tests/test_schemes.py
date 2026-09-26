"""
Unit tests for the Scheme subsystem and SchemeRegistry.
Validates scheme modularity, configuration isolation, and GOBARdhan default configuration.
"""
from __future__ import annotations

import pytest
from scheme_intel.schemes.models import SchemeConfig, SchemeStock, SchemeSource
from scheme_intel.schemes.registry import SchemeRegistry
from scheme_intel.schemes.gobardhan.config import GOBARDHAN_CONFIG
from scheme_intel.schemes.gobardhan.watchlist import WATCHLIST
from scheme_intel.schemes.gobardhan.sources import SOURCES
from scheme_intel.schemes.gobardhan.mapping import COMPANY_KEYWORDS


def test_gobardhan_config_structure():
    assert GOBARDHAN_CONFIG.scheme_id == "gobardhan"
    assert "GOBARdhan" in GOBARDHAN_CONFIG.name
    assert GOBARDHAN_CONFIG.is_active is True
    assert len(GOBARDHAN_CONFIG.watchlist) == 7
    symbols = [s.symbol for s in GOBARDHAN_CONFIG.watchlist]
    assert "PRAJIND.NS" in symbols
    assert "TRUALT.NS" in symbols
    assert "IONEXCHANG.NS" in symbols
    assert "WABAG.NS" in symbols
    assert "KIRLPNU.NS" in symbols
    assert "GAIL.NS" in symbols
    assert "IOC.NS" in symbols


def test_scheme_registry_default():
    registry = SchemeRegistry()
    assert "gobardhan" in registry.list_scheme_ids()
    cfg = registry.get("gobardhan")
    assert cfg is not None
    assert cfg.scheme_id == "gobardhan"
    assert cfg.is_active is True


def test_scheme_registry_custom_registration():
    registry = SchemeRegistry()
    custom_scheme = SchemeConfig(
        id="custom_scheme_test",
        name="Custom Test Scheme",
        description="Testing scheme registry extensibility",
        enabled=True,
        watchlist=[
            SchemeStock(symbol="TEST1", name="Test Company 1", sectors=["Industrial"]),
        ],
        sources=[
            SchemeSource(id="test_src", name="Test Source", type="rss", url="https://example.com/feed"),
        ],
    )
    registry.register(custom_scheme)
    assert "custom_scheme_test" in registry.list_scheme_ids()
    retrieved = registry.get("custom_scheme_test")
    assert retrieved is not None
    assert retrieved.name == "Custom Test Scheme"
    assert len(retrieved.watchlist) == 1


def test_scheme_registry_active_filtering():
    registry = SchemeRegistry()
    inactive_scheme = SchemeConfig(
        id="inactive_test",
        name="Inactive Scheme",
        enabled=False,
    )
    registry.register(inactive_scheme)
    active_schemes = registry.get_active_schemes()
    active_ids = [s.id for s in active_schemes]
    assert "gobardhan" in active_ids
    assert "inactive_test" not in active_ids


def test_gobardhan_exports():
    assert len(WATCHLIST) == 7
    assert len(SOURCES) >= 3
    assert len(COMPANY_KEYWORDS) >= 7
    for company in ["Praj Industries", "TruAlt Bioenergy", "Ion Exchange", "VA Tech Wabag", "Kirloskar Pneumatic", "GAIL (India)", "Indian Oil Corporation"]:
        assert company in COMPANY_KEYWORDS
