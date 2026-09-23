"""Tests for the earnings, analyst ratings, and concall tracker."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.scheme_intel.db import SchemeIntelDB
from src.scheme_intel.earnings import (
    EarningsTracker,
    EarningsReport,
    AnalystRating,
    ConcallTranscript,
    DigestItem,
    _extract_rating,
    _extract_target_price,
    _extract_period,
    _safe_float,
    _ensure_phase8_schema,
)


@pytest.fixture
def db(tmp_path: Path):
    path = tmp_path / "test_earnings.db"
    scheme_db = SchemeIntelDB(db_path=path)
    yield scheme_db
    scheme_db.close()


@pytest.fixture
def tracker(db: SchemeIntelDB):
    return EarningsTracker(db=db)


# ------------------------------------------------------------------
# Helper extractors
# ------------------------------------------------------------------


class TestSafeFloat:
    def test_none(self):
        assert _safe_float(None) is None

    def test_valid(self):
        assert _safe_float("123.45") == 123.45

    def test_comma_separated(self):
        assert _safe_float("1,234.56") == 1234.56

    def test_percent(self):
        assert _safe_float("12.5%") == 12.5

    def test_invalid(self):
        assert _safe_float("N/A") is None


class TestExtractRating:
    def test_buy(self):
        assert _extract_rating("Buy with target Rs 500") == "BUY"

    def test_sell(self):
        assert _extract_rating("Sell recommendation") == "SELL"

    def test_hold(self):
        assert _extract_rating("Hold — maintain position") == "HOLD"

    def test_neutral(self):
        assert _extract_rating("Analyst initiates coverage") == "NEUTRAL"

    def test_outperform(self):
        assert _extract_rating("Outperform rating maintained") == "BUY"

    def test_reduce(self):
        assert _extract_rating("Reduce rating from broker") == "SELL"


class TestExtractTargetPrice:
    def test_target_price(self):
        assert _extract_target_price("Target price of Rs 500") == 500.0

    def test_target_rs(self):
        assert _extract_target_price("Rs 1,250 target") == 1250.0

    def test_no_target(self):
        assert _extract_target_price("Buy rating") is None


class TestExtractPeriod:
    def test_q1_fy25(self):
        assert _extract_period("Q1 FY25 results announced") == "Q1 FY25"

    def test_fy2025(self):
        assert _extract_period("FY2025 annual results") == "FY2025"

    def test_month_year(self):
        assert _extract_period("March 2025 results") == "March 2025"

    def test_no_period(self):
        assert _extract_period("Company reports strong growth") == ""


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


class TestEarningsReport:
    def test_to_dict(self):
        r = EarningsReport(
            company="TruAlt", symbol="TRUALT.NS", period="Q1 FY25",
            report_date="2026-09-01", revenue=100.0, profit=20.0, eps=5.0,
        )
        d = r.to_dict()
        assert d["company"] == "TruAlt"
        assert d["revenue"] == 100.0
        assert d["period"] == "Q1 FY25"


class TestAnalystRating:
    def test_to_dict(self):
        r = AnalystRating(
            company="Praj", symbol="PRAJIND.NS", broker="ICICI",
            rating="BUY", target_price=600.0,
        )
        d = r.to_dict()
        assert d["broker"] == "ICICI"
        assert d["rating"] == "BUY"


class TestConcallTranscript:
    def test_to_dict(self):
        t = ConcallTranscript(
            company="GAIL", symbol="GAIL.NS", call_date="2026-09-10",
            title="Q1 FY25 Earnings Call", url="https://example.com",
        )
        d = t.to_dict()
        assert d["company"] == "GAIL"


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------


class TestSchema:
    def test_creates_tables(self, db: SchemeIntelDB):
        _ensure_phase8_schema(db)
        conn = db.connect()
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "earnings" in tables
        assert "analyst_ratings" in tables
        assert "concalls" in tables

    def test_idempotent(self, db: SchemeIntelDB):
        _ensure_phase8_schema(db)
        _ensure_phase8_schema(db)  # should not raise


# ------------------------------------------------------------------
# Save / read earnings
# ------------------------------------------------------------------


class TestEarningsStorage:
    def test_save_earnings(self, tracker: EarningsTracker):
        reports = [
            EarningsReport("TruAlt", "TRUALT.NS", "Q1 FY25", "2026-09-01", 100.0, 20.0),
            EarningsReport("TruAlt", "TRUALT.NS", "Q4 FY24", "2026-06-01", 90.0, 15.0),
        ]
        count = tracker.save_earnings(reports)
        assert count == 2
        assert len(tracker.get_earnings(company="TruAlt")) == 2

    def test_deduplicates(self, tracker: EarningsTracker):
        r = EarningsReport("TruAlt", "TRUALT.NS", "Q1 FY25", "2026-09-01")
        tracker.save_earnings([r])
        tracker.save_earnings([r])  # duplicate
        assert len(tracker.get_earnings(company="TruAlt")) == 1

    def test_get_earnings_all(self, tracker: EarningsTracker):
        tracker.save_earnings([
            EarningsReport("A", "A.NS", "Q1", "2026-09-01"),
            EarningsReport("B", "B.NS", "Q1", "2026-09-01"),
        ])
        assert len(tracker.get_earnings()) == 2

    def test_get_earnings_empty(self, tracker: EarningsTracker):
        assert tracker.get_earnings() == []


# ------------------------------------------------------------------
# Save / read analyst ratings
# ------------------------------------------------------------------


class TestAnalystStorage:
    def test_save_ratings(self, tracker: EarningsTracker):
        ratings = [
            AnalystRating("Praj", "PRAJIND.NS", "ICICI", "BUY", 600.0),
            AnalystRating("Praj", "PRAJIND.NS", "HDFC", "HOLD", 550.0),
        ]
        count = tracker.save_analyst_ratings(ratings)
        assert count == 2

    def test_deduplicates(self, tracker: EarningsTracker):
        r = AnalystRating("Praj", "PRAJIND.NS", "ICICI", "BUY", 600.0)
        tracker.save_analyst_ratings([r])
        tracker.save_analyst_ratings([r])
        assert len(tracker.get_analyst_ratings(company="Praj")) == 1

    def test_get_ratings_filter(self, tracker: EarningsTracker):
        tracker.save_analyst_ratings([
            AnalystRating("A", "A.NS", "Broker1", "BUY"),
            AnalystRating("B", "B.NS", "Broker2", "SELL"),
        ])
        assert len(tracker.get_analyst_ratings(company="A")) == 1


# ------------------------------------------------------------------
# Save / read concalls
# ------------------------------------------------------------------


class TestConcallStorage:
    def test_save_concalls(self, tracker: EarningsTracker):
        transcripts = [
            ConcallTranscript("GAIL", "GAIL.NS", "2026-09-10", "Q1 FY25 Earnings Call"),
        ]
        count = tracker.save_concalls(transcripts)
        assert count == 1

    def test_deduplicates(self, tracker: EarningsTracker):
        t = ConcallTranscript("GAIL", "GAIL.NS", "2026-09-10", "Q1 FY25 Call")
        tracker.save_concalls([t])
        tracker.save_concalls([t])
        assert len(tracker.get_concalls(company="GAIL")) == 1


# ------------------------------------------------------------------
# Digest generation
# ------------------------------------------------------------------


class TestDigest:
    def test_empty_digest(self, tracker: EarningsTracker):
        digest = tracker.generate_digest([])
        assert digest == []

    def test_includes_earnings(self, tracker: EarningsTracker):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tracker.save_earnings([
            EarningsReport("TruAlt", "TRUALT.NS", "Q1 FY25", today, 100.0, 20.0, 5.0),
        ])
        stocks = [{"name": "TruAlt", "symbol": "TRUALT.NS"}]
        digest = tracker.generate_digest(stocks)
        assert any(d.kind == "earnings" for d in digest)

    def test_includes_ratings(self, tracker: EarningsTracker):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tracker.save_analyst_ratings([
            AnalystRating("Praj", "PRAJIND.NS", "ICICI", "BUY", 600.0, date=today),
        ])
        stocks = [{"name": "Praj", "symbol": "PRAJIND.NS"}]
        digest = tracker.generate_digest(stocks)
        assert any(d.kind == "analyst" for d in digest)

    def test_includes_concalls(self, tracker: EarningsTracker):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tracker.save_concalls([
            ConcallTranscript("GAIL", "GAIL.NS", today, "Q1 Earnings Call"),
        ])
        stocks = [{"name": "GAIL", "symbol": "GAIL.NS"}]
        digest = tracker.generate_digest(stocks)
        assert any(d.kind == "concall" for d in digest)


# ------------------------------------------------------------------
# Telegram formatting
# ------------------------------------------------------------------


class TestTelegramFormat:
    def test_empty_format(self, tracker: EarningsTracker):
        msg = tracker.format_digest_telegram([])
        assert "No recent" in msg

    def test_formats_earnings(self, tracker: EarningsTracker):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tracker.save_earnings([
            EarningsReport("TruAlt", "TRUALT.NS", "Q1 FY25", today, 100.0, 20.0),
        ])
        stocks = [{"name": "TruAlt", "symbol": "TRUALT.NS"}]
        digest = tracker.generate_digest(stocks)
        msg = tracker.format_digest_telegram(digest)
        assert "TruAlt" in msg
        assert "Q1 FY25" in msg
        assert "Digest" in msg

    def test_formats_ratings(self, tracker: EarningsTracker):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tracker.save_analyst_ratings([
            AnalystRating("Praj", "PRAJIND.NS", "ICICI", "BUY", 600.0, date=today),
        ])
        stocks = [{"name": "Praj", "symbol": "PRAJIND.NS"}]
        digest = tracker.generate_digest(stocks)
        msg = tracker.format_digest_telegram(digest)
        assert "ICICI" in msg
        assert "BUY" in msg
        assert "600" in msg


# ------------------------------------------------------------------
# Fetch (mocked)
# ------------------------------------------------------------------


class TestFetch:
    def test_fetch_concall_transcripts(self):
        with patch("src.scheme_intel.earnings._google_news_rss", return_value=[
            {"title": "TruAlt Q1 earnings call transcript", "url": "https://example.com/1",
             "published": "2026-09-10", "source": "Moneycontrol"},
        ]):
            from src.scheme_intel.earnings import fetch_concall_transcripts
            results = fetch_concall_transcripts("TruAlt Bioenergy", "TRUALT.NS")
            assert len(results) >= 1
            assert results[0].company == "TruAlt Bioenergy"

    def test_fetch_analyst_reports(self):
        with patch("src.scheme_intel.earnings._google_news_rss", return_value=[
            {"title": "Buy with target Rs 500", "url": "https://example.com/2",
             "published": "2026-09-12", "source": "ICICI Securities"},
        ]):
            from src.scheme_intel.earnings import fetch_analyst_reports
            results = fetch_analyst_reports("Praj Industries", "PRAJIND.NS")
            assert len(results) >= 1
            assert results[0].rating == "BUY"
            assert results[0].target_price == 500.0

    def test_fetch_earnings_news(self):
        with patch("src.scheme_intel.earnings._google_news_rss", return_value=[
            {"title": "Q1 FY25 results announced", "url": "https://example.com/3",
             "published": "2026-09-10", "source": "ET"},
        ]):
            from src.scheme_intel.earnings import fetch_earnings_news
            results = fetch_earnings_news("GAIL", "GAIL.NS")
            assert len(results) >= 1
            assert results[0].period == "Q1 FY25"
