"""
Regression test suite for Stage 2 Market Data Connection and Fail-Safes.
Covers:
1. DB history reaches Stage 2 and builds valid TechnicalSnapshot
2. Missing data produces DATA_UNAVAILABLE instead of WAIT
3. Reports never contain fabricated zero price / triggers
4. Repository's current data/ingested.json produces valid snapshots for all 7 stocks
5. News isolation: unrelated articles (e.g. D-Link) never attach to Organic Recycling Systems
6. Valid company match: genuine company disclosures correctly attach to stock
7. Stale market data produces DATA_STALE instead of WAIT
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from scheme_intel.stage2.models import (
    Stock, TechnicalSnapshot, DailyStockCard, TradeSetup, NewsItem,
    DATA_OK, DATA_UNAVAILABLE, DATA_STALE,
)
from scheme_intel.stage2.market import (
    MarketDataEngine, validate_ohlcv_bars, check_history_freshness, load_ingested_history,
)
from scheme_intel.stage2.pipeline import Stage2Pipeline
from scheme_intel.stage2.news import classify_news_item, extract_stock_news
from scheme_intel.stage2.impact import score_catalyst_impact, evaluate_stock_catalysts
from scheme_intel.stage2.scanner import scan_all_stocks, build_stock_card
from scheme_intel.stage2.waiting import generate_wait_condition
from scheme_intel.stage2.telegram import (
    build_full_telegram_report, format_section1_daily_intelligence, format_section3_actionable_and_waiting,
)


def _generate_synthetic_bars(count: int = 120, base_price: float = 170.0, end_date: str = "2026-09-25") -> list[dict]:
    """Generate chronological, strictly valid OHLCV daily bars."""
    end_d = date.fromisoformat(end_date)
    bars = []
    d = end_d
    dates = []
    while len(dates) < count:
        if d.weekday() < 5:  # Mon-Fri
            dates.append(d.isoformat())
        d -= timedelta(days=1)
    dates.reverse()

    price = base_price
    for d_str in dates:
        open_p = round(price, 2)
        high_p = round(price * 1.02, 2)
        low_p = round(price * 0.98, 2)
        close_p = round(price * 1.01, 2)
        volume = 250_000
        bars.append({
            "date": d_str,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": volume,
        })
        price = close_p
    return bars


class TestStage2MarketDataRegression:

    def test_1_db_history_reaches_stage2(self):
        """Test 1: DB history reaches Stage 2 and returns a valid TechnicalSnapshot."""
        bars = _generate_synthetic_bars(count=120, base_price=170.0, end_date="2026-09-25")
        mock_db = MagicMock()
        mock_db.get_historical_prices.return_value = bars

        engine = MarketDataEngine(mode="production", db=mock_db)
        snapshot = engine.get_snapshot("GAIL.NS")

        assert snapshot is not None, "Snapshot should not be None when 120 valid bars exist in DB"
        assert snapshot.close > 0
        assert snapshot.volume > 0
        assert snapshot.volume_20d_avg > 0
        assert snapshot.support > 0
        assert snapshot.resistance > 0
        mock_db.get_historical_prices.assert_called_with("GAIL.NS", limit=120)
    def test_2_missing_data_becomes_data_unavailable_not_wait(self):
        """Test 2: Missing data results in DATA_UNAVAILABLE and not WAIT."""
        mock_db = MagicMock()
        mock_db.get_historical_prices.return_value = []

        engine = MarketDataEngine(mode="production", db=mock_db)
        snap, status, reason = engine.get_snapshot_with_status("NONEXISTENT.NS")
        assert snap is None
        assert status == DATA_UNAVAILABLE

        stock = Stock(name="Nonexistent Co", symbol="NONEXISTENT.NS", sectors=["Energy"])
        cards = scan_all_stocks(
            stocks=[stock],
            market_data={},
            stock_news={},
        )
        assert len(cards) == 1
        assert cards[0].tomorrow_status == DATA_UNAVAILABLE
        assert cards[0].data_status == DATA_UNAVAILABLE
        assert cards[0].price is None


    def test_3_no_zero_in_reports(self):
        """Test 3: Reports with unavailable data never show ₹0.00, ₹0.0, or ₹0 triggers."""
        stock = Stock(name="GAIL (India) Ltd", symbol="GAIL.NS", sectors=["Energy"])
        card = build_stock_card(
            stock=stock,
            snapshot=None,
            news_items=[],
            tomorrow_status="DATA_UNAVAILABLE",
        )
        trade_setup = TradeSetup(
            setup_id="SETUP-GAIL_NS-20260925",
            analysis_date="2026-09-25",
            setup_date="2026-09-25",
            next_trading_session="Next Session (2026-09-28)",
            stock=stock,
            status=DATA_UNAVAILABLE,
            data_status=DATA_UNAVAILABLE,
            no_trade_reason="No valid OHLCV history was available for this symbol.",
        )

        report = build_full_telegram_report(
            session_title="2026-09-25 — AFTER MARKET",
            cards=[card],
            candidates=[],
            setups=[trade_setup],
            health_stats={"total": 1, "valid": 0, "stale": 0, "unavailable": 1},
        )
        full_text = report["full_text"]

        assert "₹0.00" not in full_text
        assert "₹0.0" not in full_text
        assert "Daily close above ₹0.0" not in full_text
        assert "Potential Entry: ₹0.0" not in full_text
        assert "Daily close below ₹0.0" not in full_text
        assert "GAIL.NS" in full_text
        assert "DATA_UNAVAILABLE" in full_text

    def test_4_current_ingestion_snapshot_works(self):
        """Test 4: Repository's data/ingested.json fixture builds valid technical snapshots for all 7 stocks."""
        ingested_file = Path(__file__).resolve().parents[1] / "data" / "ingested.json"
        assert ingested_file.is_file(), f"data/ingested.json not found at {ingested_file}"

        data = json.loads(ingested_file.read_text(encoding="utf-8"))
        symbols = [p["symbol"] for p in data.get("prices", [])]
        assert len(symbols) == 7

        engine = MarketDataEngine(mode="production", ingested_path=ingested_file)

        for sym in symbols:
            snap, status, reason = engine.get_snapshot_with_status(sym, analysis_date="2026-09-25")
            assert snap is not None, f"Failed to build snapshot for {sym}: status={status}, reason={reason}"
            assert status == DATA_OK
            assert snap.close > 0, f"Close <= 0 for {sym}"
            assert snap.volume >= 0, f"Volume < 0 for {sym}"
            assert snap.support > 0, f"Support <= 0 for {sym}"
            assert snap.resistance > 0, f"Resistance <= 0 for {sym}"

    def test_5_news_isolation_dlink_not_attached_to_organic_recycling(self):
        """Test 5: Unrelated news mentioning directors or investors does NOT match ORS (Organic Recycling Systems)."""
        ors_stock = Stock(
            name="Organic Recycling Systems",
            symbol="ORGANICREC.BO",
            aliases=["Organic Recycling Systems", "ORSL", "ORS"],
            sectors=["Waste to Energy", "Bioenergy"],
        )

        dlink_article = {
            "title": "D-Link (India) Ltd Mutual Fund Share Holding Increases",
            "summary": "The directors and investors held mutual funds across technology sectors.",
            "source": "Financial Express",
            "url": "https://example.com/dlink",
        }

        grouped = extract_stock_news([dlink_article], [ors_stock])
        ors_news = grouped.get("Organic Recycling Systems", [])
        assert len(ors_news) == 0, f"D-Link article should NOT be attached to Organic Recycling Systems, but got: {ors_news}"

        classified = classify_news_item(
            title=dlink_article["title"],
            summary=dlink_article["summary"],
            stocks=[ors_stock],
        )
        assert "Organic Recycling Systems" not in classified.companies_mentioned

    def test_6_valid_company_match(self):
        """Test 6: Valid company match with name or valid alias is correctly attached."""
        ors_stock = Stock(
            name="Organic Recycling Systems",
            symbol="ORGANICREC.BO",
            aliases=["Organic Recycling Systems", "ORSL", "ORS"],
            sectors=["Waste to Energy", "Bioenergy"],
        )

        valid_article = {
            "title": "Organic Recycling Systems wins municipal waste contract",
            "summary": "Organic Recycling Systems secured a 20-year concession for city waste to biogas plant.",
            "source": "BSE Announcements",
            "url": "https://example.com/ors-contract",
        }

        grouped = extract_stock_news([valid_article], [ors_stock])
        ors_news = grouped.get("Organic Recycling Systems", [])
        assert len(ors_news) == 1
        assert ors_news[0].title == valid_article["title"]

        catalysts = evaluate_stock_catalysts(ors_news, ors_stock)
        assert len(catalysts) == 1
        assert catalysts[0].beneficiary_type == "Direct"

    def test_7_stale_data_produces_data_stale(self):
        """Test 7: Bars whose latest date is outside acceptable trading freshness window yield DATA_STALE."""
        stale_date = (date(2026, 9, 25) - timedelta(days=30)).isoformat()
        bars = _generate_synthetic_bars(count=120, base_price=170.0, end_date=stale_date)

        mock_db = MagicMock()
        mock_db.get_historical_prices.return_value = bars

        engine = MarketDataEngine(mode="production", db=mock_db, freshness_max_trading_days=3)
        snap, status, reason = engine.get_snapshot_with_status("GAIL.NS", analysis_date="2026-09-25")

        assert snap is None
        assert status == DATA_STALE
        assert "trading days old" in (reason or "").lower()
