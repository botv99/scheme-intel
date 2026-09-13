"""
Unit tests for Pipeline ingestion wiring.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from scheme_intel.main import load_config
from scheme_intel.pipeline import Pipeline
from scheme_intel.models import Catalyst

import scheme_intel.pipeline as pipeline_module


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _ingested() -> dict:
    return {
        "generated_at": _now_iso(),
        "prices": [
            {
                "symbol": "PRAJIND.NS",
                "company": "Praj Industries",
                "history": [{"date": "2026-07-01", "Open": 450.0, "High": 455.0,
                             "Low": 445.0, "Close": 450.0, "Volume": 1000000}],
            }
        ],
        "news": [
            {"title": "Praj Industries wins CBG order", "url": "https://example.com/x",
             "source": "Mint", "published_at": _now_iso(), "summary": "summary text"},
        ],
        "announcements": [
            {"title": "receives order worth Rs 300 crore", "url": "https://example.com/y",
             "date": _now_iso(), "company": "Praj Industries", "exchange": "NSE",
             "category": "contract", "in_watchlist": True},
        ],
        "source_errors": [{"source": "NSE block deals", "error": "HTTP 503"}],
    }


class TestIngestedArticles:
    def test_converts_news_and_announcements(self):
        articles = Pipeline().ingested_articles(_ingested())

        assert len(articles) == 2
        news = articles[0]
        assert news.title == "Praj Industries wins CBG order"
        assert news.source == "Mint"
        assert news.published_at is not None and news.published_at.tzinfo is not None
        ann = articles[1]
        assert "Praj Industries" in ann.title
        assert ann.source == "NSE announcement"

    def test_empty_ingest(self):
        assert Pipeline().ingested_articles({}) == []


class TestHistoryBySymbol:
    def test_fresh_snapshot_maps_symbol(self):
        history_map = Pipeline().history_by_symbol(_ingested())
        assert "PRAJIND" in history_map
        assert history_map["PRAJIND"][0]["Close"] == 450.0

    def test_stale_snapshot_is_rejected(self):
        ingested = _ingested()
        ingested["generated_at"] = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        assert Pipeline().history_by_symbol(ingested) == {}

    def test_missing_timestamp_is_rejected(self):
        ingested = _ingested()
        del ingested["generated_at"]
        assert Pipeline().history_by_symbol(ingested) == {}


class TestFetchArticles:
    @patch('scheme_intel.pipeline.fetch_rss', return_value=[])
    @patch('scheme_intel.pipeline.scan_page', return_value=[])
    def test_ingested_articles_are_added(self, mock_scan, mock_rss):
        config = load_config()
        articles, errors = Pipeline().fetch_articles(config, _ingested())

        assert len(articles) == 2
        assert any("ingestion" in e["source"] for e in errors)

    @patch('scheme_intel.pipeline.fetch_rss', return_value=[])
    @patch('scheme_intel.pipeline.scan_page', return_value=[])
    def test_no_ingest_keeps_previous_behaviour(self, mock_scan, mock_rss):
        config = load_config()
        articles, errors = Pipeline().fetch_articles(config)
        assert articles == []
        assert errors == []


class TestGenerateSetups:
    @patch('scheme_intel.pipeline.make_setup')
    def test_uses_ingested_history_for_matching_stock(self, mock_setup):
        config = load_config()
        article = Mock(title="Praj CBG contract", url="https://example.com", source="NSE",
                       published_at=None, summary="")
        catalyst = Catalyst(article, 90, "contract award", "rationale", ("Praj Industries",))

        pipelines = Pipeline()
        pipelines.generate_setups([catalyst], config, {"PRAJIND": [{"Close": 450.0}]})

        mock_setup.assert_called_once()
        _, kwargs = mock_setup.call_args
        assert kwargs["history"] is not None

    @patch('scheme_intel.pipeline.make_setup')
    def test_nonmatching_stock_skipped(self, mock_setup):
        config = load_config()
        article = Mock(title="IOCL contract", url="https://example.com", source="NSE",
                       published_at=None, summary="")
        catalyst = Catalyst(article, 90, "contract award", "rationale", ("IOCL",))

        Pipeline().generate_setups([catalyst], config, {})

        mock_setup.assert_not_called()