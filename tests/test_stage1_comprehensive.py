"""
Comprehensive test suite verifying Stage 1 (Phases 1 through 8) requirements.
Ensures every newly added Stage 1 functionality executes cleanly and handles edge cases.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from src.scheme_intel.analytics import Analytics, TradeSummary
from src.scheme_intel.catalyst import classify, MATERIAL_EVENTS
from src.scheme_intel.db import SchemeIntelDB
from src.scheme_intel.earnings import (
    EarningsTracker,
    EarningsReport,
    AnalystRating,
    ConcallTranscript,
    extract_corporate_intelligence,
)
from src.scheme_intel.models import (
    Article,
    Catalyst,
    SwingSetup,
    TIER_1_GOV_REGULATOR,
    TIER_2_COMPANY_DISCLOSURE,
    TIER_3_FINANCIAL_MEDIA,
    TIER_4_ANALYST_RESEARCH,
    TIER_5_UNVERIFIED_SOCIAL,
    resolve_source_tier,
)
from src.scheme_intel.notifier import (
    send_alert,
    send_telegram,
    format_daily_digest,
    LEVEL_INFO,
    LEVEL_QUALIFIED,
    LEVEL_CRITICAL,
)
from src.scheme_intel.reliability import (
    SourceReliabilityTracker,
    is_stale,
    format_corroboration_narrative,
)
from src.scheme_intel.signals import (
    make_setup,
    _roc,
    _atr_and_regime,
    _price_structure,
    _relative_strength_vs_benchmark,
)


@pytest.fixture
def db(tmp_path: Path):
    path = tmp_path / "stage1_test.db"
    scheme_db = SchemeIntelDB(db_path=path)
    yield scheme_db
    scheme_db.close()


# ==================================================================
# Phase 2: Data & Analytics
# ==================================================================

class TestPhase2DataAndAnalytics:
    def test_historical_prices_storage(self, db: SchemeIntelDB):
        prices = [
            {"date": "2026-09-01", "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 150000},
            {"date": "2026-09-02", "open": 104.0, "high": 108.0, "low": 103.0, "close": 107.5, "volume": 200000},
        ]
        saved = db.save_historical_prices("TEST.NS", prices)
        assert saved == 2
        assert db.count_historical_prices("TEST.NS") == 2

        # Fetch back
        rows = db.get_historical_prices("TEST.NS", limit=10)
        assert len(rows) == 2
        assert rows[0]["date"] == "2026-09-01"
        assert rows[1]["close"] == 107.5

        # Idempotent upsert
        saved_again = db.save_historical_prices("TEST.NS", [{"date": "2026-09-01", "close": 105.0}])
        assert saved_again == 1
        assert db.count_historical_prices("TEST.NS") == 2

    def test_max_drawdown_calculation(self, db: SchemeIntelDB):
        # 10% win, then 20% loss, then 5% win
        db.record_trade("T1", "T1.NS", 100, 95, 110, "2026-09-01")
        db.close_trade(1, 110, "2026-09-02", "WIN")  # +10% -> 110.0
        db.record_trade("T2", "T2.NS", 100, 90, 110, "2026-09-03")
        db.close_trade(2, 80, "2026-09-04", "LOSS")   # -20% -> 88.0 (DD: 22/110 = 20%)

        analytics = Analytics(db=db)
        mdd = analytics.max_drawdown()
        assert mdd == 20.0

        summary = analytics.trade_summary()
        assert summary.max_drawdown_pct == 20.0

    def test_technical_effectiveness(self, db: SchemeIntelDB):
        # Setup 1: Breakout confirmed, RSI 60
        run_id = db.save_run(
            generated_at="2026-09-01T10:00:00Z",
            catalysts=[],
            setups=[{
                "company": "TruAlt", "symbol": "TRUALT.NS", "breakout": 1,
                "rsi14": 60.0, "macd_hist": 0.5, "status": "QUALIFIED"
            }],
            source_errors=[],
        )
        setups = db.get_setups_for_run(run_id)
        setup_id = setups[0]["id"]

        t_id = db.record_trade("TruAlt", "TRUALT.NS", 100, 95, 110, "2026-09-01", setup_id=setup_id)
        db.close_trade(t_id, 115, "2026-09-05", "WIN")

        analytics = Analytics(db=db)
        tech_eff = analytics.technical_effectiveness()
        assert tech_eff["breakout_confirmed"]["win_rate"] == 100.0
        assert tech_eff["rsi_sweet_spot_50_70"]["win_rate"] == 100.0
        assert tech_eff["macd_hist_positive"]["win_rate"] == 100.0

    def test_periodic_summary(self, db: SchemeIntelDB):
        t1 = db.record_trade("Praj", "PRAJ.NS", 100, 95, 110, "2026-09-01")
        db.close_trade(t1, 110, "2026-09-05", "WIN")
        t2 = db.record_trade("GAIL", "GAIL.NS", 100, 95, 110, "2026-09-10")
        db.close_trade(t2, 90, "2026-09-15", "LOSS")

        analytics = Analytics(db=db)
        monthly = analytics.periodic_summary("monthly")
        assert len(monthly) == 1
        assert monthly[0]["period"] == "2026-09"
        assert monthly[0]["trades"] == 2
        assert monthly[0]["win_rate"] == 50.0


# ==================================================================
# Phase 3: Source Reliability & Hierarchy
# ==================================================================

class TestPhase3SourceReliability:
    def test_resolve_source_tier(self):
        assert resolve_source_tier("PIB Delhi") == TIER_1_GOV_REGULATOR
        assert resolve_source_tier("NSE Corporate Announcements") == TIER_1_GOV_REGULATOR
        assert resolve_source_tier("Praj Investor Relations") == TIER_2_COMPANY_DISCLOSURE
        assert resolve_source_tier("LiveMint") == TIER_3_FINANCIAL_MEDIA
        assert resolve_source_tier("Scripbox Analyst Research") == TIER_4_ANALYST_RESEARCH

    def test_is_stale_detection(self):
        now = datetime.now(timezone.utc)
        fresh_date = now - timedelta(hours=24)
        stale_date = now - timedelta(hours=96)
        assert not is_stale(fresh_date, max_age_hours=72)
        assert is_stale(stale_date, max_age_hours=72)
        assert not is_stale(None)

    def test_corroboration_narrative_formatting(self):
        lead = Article(title="Govt approves CBG incentive", url="http://pib.gov.in", source="PIB", published_at=None, source_tier=TIER_1_GOV_REGULATOR)
        art2 = Article(title="Cabinet greenlights CBG subsidy", url="http://mint.com", source="Mint", published_at=None, source_tier=TIER_3_FINANCIAL_MEDIA)
        art3 = Article(title="India announces CBG support", url="http://et.com", source="Economic Times", published_at=None, source_tier=TIER_3_FINANCIAL_MEDIA)

        narrative = format_corroboration_narrative(lead, [lead, art2, art3])
        assert "Confirmed by 3 independent sources" in narrative
        assert "Tier 1" in narrative

    def test_detect_conflicts(self, db: SchemeIntelDB):
        tracker = SourceReliabilityTracker(db=db)
        a1 = Article(title="TruAlt Bioenergy profit surges with record growth", url="http://a.com", source="ET", published_at=None)
        a2 = Article(title="TruAlt Bioenergy profit slump amid severe decline and loss", url="http://b.com", source="Blog", published_at=None)

        conflicts = tracker.detect_conflicts([a1, a2], threshold=0.50)
        assert len(conflicts) >= 1
        assert conflicts[0]["sentiment_a"] != conflicts[0]["sentiment_b"]


# ==================================================================
# Phase 4: Technical Analysis
# ==================================================================

class TestPhase4TechnicalAnalysis:
    @pytest.fixture
    def ohlc_series(self):
        dates = pd.date_range("2026-01-01", periods=120, freq="B")
        closes = [100.0 + (i * 0.8) for i in range(120)]
        highs = [c + 2.0 for c in closes]
        lows = [c - 2.0 for c in closes]
        volumes = [100000 + (i * 500) for i in range(120)]
        return pd.DataFrame({
            "Open": closes,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        }, index=dates)

    def test_rate_of_change(self, ohlc_series):
        close = ohlc_series["Close"]
        roc = _roc(close, period=10)
        assert roc is not None
        assert roc > 0

    def test_atr_and_volatility_regime(self, ohlc_series):
        atr, atr_pct, regime = _atr_and_regime(ohlc_series, period=14)
        assert atr > 0
        assert atr_pct > 0
        assert regime in ("LOW", "NORMAL", "HIGH", "EXTREME")

    def test_price_structure_support_resistance(self, ohlc_series):
        support, resistance, swing_low, swing_high = _price_structure(ohlc_series, window=20)
        assert support <= resistance
        assert swing_low <= swing_high

    def test_relative_strength_vs_benchmark(self, ohlc_series):
        stock_close = ohlc_series["Close"]
        # Benchmark rises slower than stock
        bm_close = pd.Series([1000.0 + (i * 2.0) for i in range(120)])
        rs = _relative_strength_vs_benchmark(stock_close, bm_close, period=20)
        assert rs is not None
        assert rs > 0  # stock outperformed benchmark

    def test_make_setup_populates_expanded_fields(self, ohlc_series):
        history = []
        for dt, row in ohlc_series.iterrows():
            history.append({
                "date": dt.strftime("%Y-%m-%d"),
                "open": row["Open"],
                "high": row["High"],
                "low": row["Low"],
                "close": row["Close"],
                "volume": row["Volume"],
            })
        setup = make_setup("TruAlt", "TRUALT.NS", catalyst_score=85, history=history)
        assert setup is not None
        assert setup.sma100 is not None
        assert setup.roc10 is not None
        assert setup.prior_high50 is not None
        assert setup.atr_pct is not None
        assert setup.volatility_regime is not None
        assert setup.support is not None
        assert setup.resistance is not None


# ==================================================================
# Phase 5: Catalyst Intelligence (19 Classifications)
# ==================================================================

class TestPhase5CatalystIntelligence:
    def test_all_19_classifications_mapped(self):
        expected = {
            "Cabinet approval", "Government policy", "Scheme announcement",
            "Subsidy", "Order win", "Tender", "Plant commissioning",
            "Capacity expansion", "Capex", "Pricing change",
            "Regulatory change", "JV / partnership", "Acquisition",
            "Results", "Management commentary", "Investor presentation",
            "Earnings call", "Analyst report", "Industry development",
        }
        mapped_categories = {cat for _, cat, _, _ in MATERIAL_EVENTS.values()}
        for exp in expected:
            assert exp in mapped_categories

    def test_catalyst_rich_fields(self):
        art = Article(
            title="Cabinet approval for new GOBARdhan CBG scheme in Bio-Energy",
            url="https://pib.gov.in/pressrelease",
            source="PIB Delhi",
            published_at=datetime.now(timezone.utc),
            summary="Government approved national bio-energy scheme and subsidy.",
        )
        companies = [{"name": "TruAlt Bioenergy", "aliases": ["TruAlt"]}]
        catalyst = classify(art, companies)

        assert catalyst is not None
        assert catalyst.catalyst_type == "Cabinet approval"
        assert catalyst.score == 95
        assert catalyst.source_tier == TIER_1_GOV_REGULATOR
        assert "GOBARdhan" in catalyst.related_scheme
        assert catalyst.sentiment_label == "positive"
        assert catalyst.expected_duration == "long-term"
        assert catalyst.affected_business_segment != ""


# ==================================================================
# Phase 6: Company Intelligence & Extractor
# ==================================================================

class TestPhase6CompanyIntelligence:
    def test_extract_corporate_intelligence(self):
        text = (
            "TruAlt Bioenergy announced capex of Rs 450 crore for 200 KLPD capacity expansion "
            "under GOBARdhan scheme. Secured order win valued at Rs 120 cr. Management guidance "
            "targets to achieve 25% revenue growth while raw material cost headwinds remain a risk."
        )
        intel = extract_corporate_intelligence(
            text=text,
            company="TruAlt",
            symbol="TRUALT.NS",
            source_type="disclosure",
        )
        assert intel.company == "TruAlt"
        assert "450" in intel.capex
        assert "120" in intel.orders
        assert "200 KLPD" in intel.capacity
        assert "GOBARdhan" in intel.scheme_exposure
        assert "risk" in intel.risks.lower() or "cost" in intel.risks.lower()

    def test_earnings_to_catalysts_bridge(self, db: SchemeIntelDB):
        tracker = EarningsTracker(db=db)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tracker.save_earnings([
            EarningsReport("Praj", "PRAJIND.NS", "Q1 FY25", today, 500.0, 65.0, 3.5),
        ])
        tracker.save_analyst_ratings([
            AnalystRating("Praj", "PRAJIND.NS", "ICICI Direct", "BUY", 650.0, date=today),
        ])

        catalysts = tracker.to_catalysts([{"name": "Praj", "symbol": "PRAJIND.NS"}], days=7)
        assert len(catalysts) >= 2
        types = {c.catalyst_type for c in catalysts}
        assert "Results" in types
        assert "Analyst report" in types


# ==================================================================
# Phase 8: Automation & Delivery (Alert Levels & Deduplication)
# ==================================================================

class TestPhase8AutomationAndDelivery:
    def test_alert_levels_and_deduplication(self, db: SchemeIntelDB):
        alert_key = "alert_test_unique_key_001"
        assert not db.is_alert_sent(alert_key)

        with patch("src.scheme_intel.notifier.send_telegram", return_value=True) as mock_send:
            # First send
            sent1 = send_alert("Material order win", alert_key=alert_key, level=LEVEL_CRITICAL, db=db)
            assert sent1
            assert mock_send.call_count == 1
            assert db.is_alert_sent(alert_key)

            # Duplicate send suppressed
            sent2 = send_alert("Material order win", alert_key=alert_key, level=LEVEL_CRITICAL, db=db)
            assert sent2
            assert mock_send.call_count == 1  # not called second time!

    def test_format_daily_digest(self):
        msg = format_daily_digest(
            date_str="2026-09-23",
            catalysts=[{"headline": "Cabinet approves CBG subsidy", "score": 95}],
            setups=[{"company": "TruAlt", "symbol": "TRUALT.NS", "entry": 105, "target": 120, "stop": 98, "status": "QUALIFIED"}],
            summary="Active trading day with major policy announcements.",
        )
        assert "Scheme-Intel Daily Briefing" in msg
        assert "Cabinet approves CBG subsidy" in msg
        assert "TruAlt" in msg
        assert "QUALIFIED" in msg or "Entry ₹105" in msg
