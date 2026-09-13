"""Tests for expanded data sources, sector feeds, and source health."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.scheme_intel.sources_expanded import (
    SectorArticle,
    EconomicIndicator,
    CommodityPrice,
    BSECorporateAction,
    SourceHealth,
    SECTOR_FEEDS,
    fetch_sector_news,
    fetch_bse_corporate_actions,
    fetch_economic_indicators,
    fetch_commodity_prices,
    fetch_sector_headlines,
    check_source_health,
    _safe_float,
    _extract_number,
)


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


class TestSectorArticle:
    def test_to_dict(self):
        a = SectorArticle("Test", "https://example.com", "Mint", "renewable_energy")
        d = a.to_dict()
        assert d["sector"] == "renewable_energy"
        assert d["title"] == "Test"


class TestEconomicIndicator:
    def test_to_dict(self):
        i = EconomicIndicator("Repo Rate", 6.5, "Sep 2026", "RBI")
        d = i.to_dict()
        assert d["name"] == "Repo Rate"
        assert d["value"] == 6.5


class TestCommodityPrice:
    def test_to_dict(self):
        p = CommodityPrice("Crude Oil", 7500.0, "barrel", "INR", "MCX")
        d = p.to_dict()
        assert d["price"] == 7500.0


class TestBSECorporateAction:
    def test_to_dict(self):
        a = BSECorporateAction("GAIL", "GAIL", "Dividend", "2026-09-15")
        d = a.to_dict()
        assert d["action_type"] == "Dividend"


class TestSourceHealth:
    def test_to_dict(self):
        h = SourceHealth("NSE", "exchange", "ok", "2026-09-13T10:00:00", 150)
        d = h.to_dict()
        assert d["status"] == "ok"
        assert d["latency_ms"] == 150


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


class TestSafeFloat:
    def test_none(self):
        assert _safe_float(None) is None

    def test_valid(self):
        assert _safe_float("123.45") == 123.45

    def test_comma(self):
        assert _safe_float("1,234") == 1234.0

    def test_percent(self):
        assert _safe_float("5.2%") == 5.2

    def test_rupee(self):
        assert _safe_float("₹500") == 500.0

    def test_invalid(self):
        assert _safe_float("N/A") is None


class TestExtractNumber:
    def test_extracts_first(self):
        assert _extract_number("Crude oil rises 2.5% to $75") == 2.5

    def test_no_number(self):
        assert _extract_number("No numbers here") is None

    def test_comma_number(self):
        assert _extract_number("Market cap: 1,23,456 cr") == 123456.0


# ------------------------------------------------------------------
# Sector feeds config
# ------------------------------------------------------------------


class TestSectorFeeds:
    def test_has_all_sectors(self):
        assert "renewable_energy" in SECTOR_FEEDS
        assert "oil_gas" in SECTOR_FEEDS
        assert "water_infra" in SECTOR_FEEDS
        assert "government_policy" in SECTOR_FEEDS
        assert "commodities" in SECTOR_FEEDS

    def test_feeds_are_tuples(self):
        for sector, feeds in SECTOR_FEEDS.items():
            assert isinstance(feeds, list)
            for name, url in feeds:
                assert isinstance(name, str)
                assert url.startswith("http")


# ------------------------------------------------------------------
# Sector news (mocked)
# ------------------------------------------------------------------


class TestSectorNews:
    def test_fetch_with_mock(self):
        mock_articles = [
            MagicMock(title="CBG plant commissioned", url="https://example.com/1",
                      source="Mint", summary="New plant",
                      published_at=datetime(2026, 9, 13, tzinfo=timezone.utc)),
        ]
        with patch("src.scheme_intel.sources_expanded.fetch_rss", return_value=mock_articles):
            results = fetch_sector_news(sectors=["renewable_energy"])
            assert len(results) >= 1
            assert results[0].sector == "renewable_energy"

    def test_filters_by_watchlist(self):
        mock_articles = [
            MagicMock(title="TruAlt wins CBG order", url="https://example.com/1",
                      source="Mint", summary="", published_at=None),
            MagicMock(title="IOC quarterly results", url="https://example.com/2",
                      source="ET", summary="", published_at=None),
        ]
        with patch("src.scheme_intel.sources_expanded.fetch_rss", return_value=mock_articles):
            results = fetch_sector_news(
                sectors=["renewable_energy"],
                watchlist_aliases=["TruAlt"],
            )
            # Only TruAlt articles should pass the filter (from 3 feeds, 2 articles each)
            assert all("TruAlt" in r.title for r in results)
            assert len(results) > 0

    def test_empty_on_error(self):
        with patch("src.scheme_intel.sources_expanded.fetch_rss", side_effect=Exception("fail")):
            results = fetch_sector_news(sectors=["renewable_energy"])
            assert results == []


# ------------------------------------------------------------------
# BSE corporate actions (mocked)
# ------------------------------------------------------------------


class TestBSEActions:
    def test_fetch_success(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "Table": [
                {"CompanyName": "GAIL", "Purpose": "Dividend", "ExDate": "2026-09-15"},
            ]
        }
        with patch("src.scheme_intel.sources_expanded.SESSION.get", return_value=mock_resp):
            results = fetch_bse_corporate_actions("GAIL.NS")
            assert len(results) == 1
            assert results[0].action_type == "Dividend"

    def test_fetch_empty(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"Table": []}
        with patch("src.scheme_intel.sources_expanded.SESSION.get", return_value=mock_resp):
            results = fetch_bse_corporate_actions("GAIL.NS")
            assert results == []

    def test_fetch_error(self):
        with patch("src.scheme_intel.sources_expanded.SESSION.get", side_effect=Exception("fail")):
            results = fetch_bse_corporate_actions("GAIL.NS")
            assert results == []


# ------------------------------------------------------------------
# Google News sector search (mocked)
# ------------------------------------------------------------------


class TestSectorHeadlines:
    def test_fetch_success(self):
        mock_feed = MagicMock()
        mock_feed.entries = [
            MagicMock(title="CBG capacity expansion", link="https://example.com",
                      source={"title": "ET"}, published="2026-09-13"),
        ]
        with patch("src.scheme_intel.sources_expanded.feedparser.parse", return_value=mock_feed):
            results = fetch_sector_headlines("CBG expansion", max_results=5)
            assert len(results) == 1
            assert results[0].sector == "custom"

    def test_fetch_error(self):
        with patch("src.scheme_intel.sources_expanded.feedparser.parse", side_effect=Exception("fail")):
            results = fetch_sector_headlines("test")
            assert results == []


# ------------------------------------------------------------------
# Source health check (mocked)
# ------------------------------------------------------------------


class TestSourceHealthCheck:
    def test_all_healthy(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        with patch("src.scheme_intel.sources_expanded.SESSION.get", return_value=mock_resp):
            results = check_source_health([
                {"name": "Test", "url": "https://example.com", "category": "test"},
            ])
            assert len(results) == 1
            assert results[0].status == "ok"

    def test_degraded(self):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 403
        with patch("src.scheme_intel.sources_expanded.SESSION.get", return_value=mock_resp):
            results = check_source_health([
                {"name": "Test", "url": "https://example.com", "category": "test"},
            ])
            assert results[0].status == "degraded"

    def test_down(self):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500
        with patch("src.scheme_intel.sources_expanded.SESSION.get", return_value=mock_resp):
            results = check_source_health([
                {"name": "Test", "url": "https://example.com", "category": "test"},
            ])
            assert results[0].status == "down"

    def test_timeout(self):
        import requests as req_lib
        with patch("src.scheme_intel.sources_expanded.SESSION.get", side_effect=req_lib.Timeout("timeout")):
            results = check_source_health([
                {"name": "Test", "url": "https://example.com", "category": "test"},
            ])
            assert results[0].status == "down"
            assert results[0].error == "Timeout"

    def test_default_sources(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        with patch("src.scheme_intel.sources_expanded.SESSION.get", return_value=mock_resp):
            results = check_source_health()
            assert len(results) >= 5
