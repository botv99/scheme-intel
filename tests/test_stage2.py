"""
Comprehensive Unit and Integration Test Suite for Stage 2:
Daily Stock Intelligence + Adversarial Swing-Setup System.
Covers all 18 Stage 2 functional areas with deterministic mock testing.
"""
from __future__ import annotations

import pytest
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from src.scheme_intel.stage2.models import (
    Stock, NewsItem, CatalystImpact, TechnicalSnapshot, DailyStockCard,
    CandidateSetup, EvidenceItem, BullThesis, BearThesis, DebateResult,
    RiskAssessment, WaitCondition, TradeSetup, SetupOutcome,
)
from src.scheme_intel.stage2.calendar import (
    get_next_trading_day, get_market_session_info, is_trading_day,
    NSE_HOLIDAYS, IST, MarketSessionInfo,
)
from src.scheme_intel.stage2.market import (
    MarketDataEngine, build_technical_snapshot,
)
from src.scheme_intel.stage2.news import (
    NewsEngine, classify_news_item, extract_stock_news,
)
from src.scheme_intel.stage2.impact import (
    score_catalyst_impact, evaluate_stock_catalysts,
)
from src.scheme_intel.stage2.candidate import (
    find_candidate_setup, evaluate_breakout, evaluate_breakout_anticipation,
    evaluate_pullback, evaluate_momentum_continuation, evaluate_event_driven,
    ARCHETYPE_BREAKOUT, ARCHETYPE_BREAKOUT_ANTICIPATION, ARCHETYPE_PULLBACK,
    ARCHETYPE_MOMENTUM_CONTINUATION, ARCHETYPE_EVENT_DRIVEN,
)
from src.scheme_intel.stage2.providers.mock import MockProvider
from src.scheme_intel.stage2.agents.bull import BullAgent
from src.scheme_intel.stage2.agents.bear import BearAgent
from src.scheme_intel.stage2.agents.arbitrator import ArbitratorAgent
from src.scheme_intel.stage2.debate import DebateOrchestrator
from src.scheme_intel.stage2.risk import (
    evaluate_risk, MIN_RISK_REWARD_RATIO, MAX_STOP_LOSS_PCT, MIN_DAILY_VOLUME,
)
from src.scheme_intel.stage2.waiting import generate_wait_condition
from src.scheme_intel.stage2.scanner import scan_all_stocks, build_stock_card
from src.scheme_intel.stage2.storage import Stage2Database
from src.scheme_intel.stage2.telegram import (
    build_full_telegram_report, format_section1_daily_intelligence,
    format_section2_radar, format_section3_actionable_and_waiting,
)
from src.scheme_intel.stage2.pipeline import Stage2Pipeline, load_watchlist_stocks


# ============================================================================
# 1. Models & Data Contracts
# ============================================================================

def test_models_stock_and_news():
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS", aliases=["Praj"], sectors=["Bioenergy"])
    assert stock.symbol == "PRAJIND.NS"
    assert "Praj" in stock.aliases

    news = NewsItem(
        title="Cabinet Approves Biofuel Funding",
        source="PIB",
        source_tier=1,
        sentiment="positive",
        materiality=85,
    )
    assert news.source_tier == 1
    assert news.sentiment == "positive"


def test_models_technical_snapshot():
    snap = TechnicalSnapshot(
        close=500.0,
        volume=100_000,
        volume_20d_avg=50_000,
        volume_ratio=2.0,
        sma20=480.0,
        sma50=460.0,
        rsi14=65.0,
        support=475.0,
        resistance=510.0,
        trend_status="BULLISH",
    )
    assert snap.volume_ratio == 2.0
    assert snap.trend_status == "BULLISH"


# ============================================================================
# 2. Market Calendar & Timing Engine
# ============================================================================

def test_calendar_trading_day_detection():
    # Regular Wednesday
    wed = date(2026, 9, 23)
    assert is_trading_day(wed) is True

    # Weekend: Saturday & Sunday
    sat = date(2026, 9, 26)
    sun = date(2026, 9, 27)
    assert is_trading_day(sat) is False
    assert is_trading_day(sun) is False

    # NSE Holiday: Gandhi Jayanti
    gandhi = date(2026, 10, 2)
    assert gandhi in NSE_HOLIDAYS
    assert is_trading_day(gandhi) is False


def test_calendar_next_trading_day():
    # Thursday -> Friday
    assert get_next_trading_day("2026-09-24") == date(2026, 9, 25)

    # Friday -> Monday (skipping Saturday & Sunday)
    assert get_next_trading_day("2026-09-25") == date(2026, 9, 28)

    # Thursday before Gandhi Jayanti (2026-10-01) -> skips Friday (holiday) to Monday (2026-10-05)
    assert get_next_trading_day("2026-10-01") == date(2026, 10, 5)


def test_calendar_market_session_info():
    # Simulate execution on a weekday after market close (17:00 IST)
    dt_after_close = datetime(2026, 9, 23, 17, 0, tzinfo=IST)
    info = get_market_session_info(dt_after_close)
    assert info.analysis_date == "2026-09-23"
    assert info.setup_date == "2026-09-24"
    assert info.is_after_market_close is True
    assert info.is_official_run_window is True
    assert "2026-09-23T15:30:00" in info.market_close_timestamp


# ============================================================================
# 3. Market Data Engine
# ============================================================================

def test_market_technical_snapshot_builder():
    bars = []
    base_price = 100.0
    for i in range(25):
        p = base_price + i * 2.0
        bars.append({
            "Date": f"2026-08-{i+1:02d}",
            "Open": p - 1.0,
            "High": p + 2.0,
            "Low": p - 1.5,
            "Close": p,
            "Volume": 100_000 + i * 5_000,
        })
    snap = build_technical_snapshot(bars)
    assert snap.close == 148.0
    assert snap.sma20 > 0
    assert snap.rsi14 > 50.0
    assert snap.trend_status == "BULLISH"


def test_market_data_engine_defaults():
    engine = MarketDataEngine(mode="mock")
    snap = engine.get_snapshot("PRAJIND.NS")
    assert snap is not None
    assert snap.close > 0
    assert snap.trend_status == "BULLISH"


# ============================================================================
# 4. News Classification & Grouping
# ============================================================================

def test_news_classification():
    stocks = [Stock(name="Praj Industries", symbol="PRAJIND.NS", aliases=["Praj"])]
    item = classify_news_item(
        title="Praj secures order worth ₹250 Cr for CBG plant",
        source="NSE Corporate Filings",
        url="https://nseindia.com",
        summary="Company awarded major contract.",
        stocks=stocks,
    )
    assert "Praj Industries" in item.companies_mentioned
    assert item.source_tier == 1
    assert item.sentiment == "positive"


def test_news_engine_grouping():
    stocks = [
        Stock(name="Praj Industries", symbol="PRAJIND.NS", aliases=["Praj"]),
        Stock(name="VA Tech Wabag", symbol="WABAG.NS", aliases=["Wabag"]),
    ]
    raw = [
        {"title": "Praj receives order", "source": "BSE", "summary": "Praj Bags order"},
        {"title": "Wabag signs water deal", "source": "Mint", "summary": "Wabag expansion"},
    ]
    engine = NewsEngine(raw, mode="mock")
    grouped = engine.group_by_stock(raw, stocks)
    assert len(grouped["Praj Industries"]) == 1
    assert len(grouped["VA Tech Wabag"]) == 1


# ============================================================================
# 5. Catalyst Impact Scoring
# ============================================================================

def test_catalyst_impact_scoring_direct():
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS", aliases=["Praj"])
    news = NewsItem(
        title="Praj awarded major GOBARdhan contract",
        source="PIB",
        source_tier=1,
        materiality=80,
        sentiment="positive",
    )
    impact = score_catalyst_impact(news, stock)
    assert impact.beneficiary_type == "Direct"
    assert impact.strength >= 80
    assert impact.certainty == "High"
    assert impact.is_fresh is True


def test_catalyst_priced_in_check():
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    snap = TechnicalSnapshot(
        close=550.0,
        performance_20d=24.5,
        performance_5d=15.0,
        rsi14=78.0,
    )
    news = NewsItem(title="Praj bags order", source="Media", materiality=75)
    impact = score_catalyst_impact(news, stock, snap)
    assert impact.already_priced_in is True


# ============================================================================
# 6. Candidate Generation (5 Archetypes)
# ============================================================================

def test_candidate_breakout():
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    tech = TechnicalSnapshot(
        close=522.0,
        high_20d=520.0,
        resistance=520.0,
        volume_ratio=1.9,
        sma20=490.0,
        sma50=460.0,
        rsi14=64.0,
        trend_status="BULLISH",
    )
    cand = find_candidate_setup(stock, tech, [])
    assert cand is not None
    assert cand.archetype == ARCHETYPE_BREAKOUT
    assert cand.score >= 65


def test_candidate_breakout_anticipation():
    stock = Stock(name="TruAlt Bioenergy", symbol="TRUALT.NS")
    tech = TechnicalSnapshot(
        close=186.0,
        resistance=190.0,
        volatility_regime="LOW",
        atr_pct=2.1,
        volume_ratio=1.2,
        sma20=180.0,
        rsi14=58.0,
        trend_status="BULLISH",
    )
    cand = find_candidate_setup(stock, tech, [])
    assert cand is not None
    assert cand.archetype == ARCHETYPE_BREAKOUT_ANTICIPATION


def test_candidate_pullback():
    stock = Stock(name="VA Tech Wabag", symbol="WABAG.NS")
    tech = TechnicalSnapshot(
        close=1235.0,
        sma20=1230.0,
        sma50=1150.0,
        volume_ratio=0.9,
        rsi14=52.0,
        support=1210.0,
        trend_status="BULLISH",
    )
    cand = find_candidate_setup(stock, tech, [])
    assert cand is not None
    assert cand.archetype == ARCHETYPE_PULLBACK


def test_candidate_momentum_continuation():
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    tech = TechnicalSnapshot(
        close=520.0,
        sma20=490.0,
        sma50=450.0,
        performance_20d=15.0,
        relative_strength_nifty=8.5,
        rsi14=66.0,
        volume_ratio=1.1,
        day_change_pct=1.5,
        trend_status="BULLISH",
    )
    cand = find_candidate_setup(stock, tech, [])
    assert cand is not None
    assert cand.archetype in (ARCHETYPE_MOMENTUM_CONTINUATION, ARCHETYPE_BREAKOUT)


def test_candidate_event_driven():
    stock = Stock(name="BEML Ltd", symbol="BEML.NS")
    tech = TechnicalSnapshot(
        close=4200.0,
        sma50=4000.0,
        volume_ratio=1.6,
        day_change_pct=2.5,
        trend_status="BULLISH",
    )
    cat = CatalystImpact(
        company="BEML Ltd",
        catalyst_name="BEML awarded ₹3,600 Cr Metro tender",
        beneficiary_type="Direct",
        strength=85,
        is_fresh=True,
        already_priced_in=False,
    )
    score, rationale = evaluate_event_driven(tech, [cat])
    assert score >= 75


# ============================================================================
# 7. AI Agents & Adversarial Debate
# ============================================================================

def test_bull_agent():
    provider = MockProvider()
    agent = BullAgent(provider)
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    tech = TechnicalSnapshot(close=520.0, sma20=490.0, sma50=460.0, volume_ratio=1.8, rsi14=62.0)
    cand = CandidateSetup(stock=stock, archetype="Breakout", score=85, rationale="Volume breakout", technicals=tech)
    evidence = agent.format_evidence_dossier(cand)
    thesis = agent.build_thesis(cand, evidence)
    assert thesis.symbol == "PRAJIND.NS"
    assert thesis.expected_target > tech.close
    assert thesis.invalidation_level < tech.close
    assert len(thesis.key_risks_acknowledged) >= 1


def test_bear_agent():
    provider = MockProvider()
    agent = BearAgent(provider)
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    tech = TechnicalSnapshot(close=520.0, sma20=490.0, sma50=460.0, volume_ratio=1.8, rsi14=62.0, resistance=530.0)
    cand = CandidateSetup(stock=stock, archetype="Breakout", score=85, rationale="Volume breakout", technicals=tech)
    evidence = agent.format_evidence_dossier(cand)
    thesis = agent.build_thesis(cand, evidence)
    assert thesis.symbol == "PRAJIND.NS"
    assert len(thesis.technical_flaws) >= 1
    assert thesis.what_would_invalidate_bear != ""
    assert thesis.required_confirmation_to_buy != ""


def test_debate_orchestrator():
    provider = MockProvider()
    orchestrator = DebateOrchestrator(provider)
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    tech = TechnicalSnapshot(close=520.0, sma20=490.0, sma50=460.0, volume_ratio=1.8, rsi14=62.0)
    cand = CandidateSetup(stock=stock, archetype="Breakout", score=85, rationale="Breakout", technicals=tech)

    bull, bear, debate = orchestrator.run_debate(cand)
    assert bull.symbol == "PRAJIND.NS"
    assert bear.symbol == "PRAJIND.NS"
    assert debate.bull_strength > 0
    assert debate.bear_strength > 0
    assert len(debate.rounds) >= 3


# ============================================================================
# 8. Hard Risk Engine, Invalidation, and Position Sizing
# ============================================================================

def test_risk_engine_passing_setup():
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    tech = TechnicalSnapshot(
        close=520.0,
        support=495.0,
        resistance=525.0,
        atr14=12.0,
        volume=250_000,
    )
    cand = CandidateSetup(stock=stock, archetype="Breakout", score=85, rationale="Breakout", technicals=tech)
    risk = evaluate_risk(cand)
    assert risk.passed is True
    assert risk.veto_reason is None
    assert risk.risk_reward_ratio >= 1.5
    assert risk.stop_loss < risk.ideal_entry
    assert risk.target_1 > risk.ideal_entry
    assert risk.share_quantity > 0
    assert risk.capital_deployed > 0
    assert risk.maximum_loss_at_stop <= (risk.portfolio_capital * (risk.max_portfolio_risk_pct / 100.0) + 1.0)


def test_invalidation_logic_directionally_consistent():
    """Verify that for a long setup, technical invalidation is strictly below entry/stop loss."""
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    tech = TechnicalSnapshot(
        close=522.50,
        support=495.0,
        resistance=525.0,
        sma20=495.0,
        atr14=12.0,
        volume=250_000,
    )
    cand = CandidateSetup(stock=stock, archetype="Breakout", score=85, rationale="Breakout", technicals=tech)
    risk = evaluate_risk(cand)

    # 1. Technical Invalidation must be BELOW entry (never above resistance!)
    assert "below stop level" in risk.technical_invalidation or "below 20 DMA" in risk.technical_invalidation
    assert "above" not in risk.technical_invalidation
    assert f"{risk.stop_loss:.2f}" in risk.technical_invalidation

    # 2. Breakout Failure Condition must be explicitly separated
    assert "Fails to hold above breakout level" in risk.breakout_failure_condition
    assert "closes back below" in risk.breakout_failure_condition


def test_risk_reward_explicit_calculation():
    """Verify explicit R:R calculation, basis, and transparent component display."""
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    tech = TechnicalSnapshot(
        close=520.0,
        support=495.0,
        resistance=525.0,
        atr14=12.0,
        volume=250_000,
    )
    cand = CandidateSetup(stock=stock, archetype="Breakout", score=85, rationale="Breakout", technicals=tech)
    risk = evaluate_risk(cand)

    # Mathematical identity check
    expected_risk = round(risk.ideal_entry - risk.stop_loss, 2)
    expected_reward = round(risk.target_1 - risk.ideal_entry, 2)
    expected_rr = round(expected_reward / expected_risk, 2)

    assert risk.risk_per_share == expected_risk
    assert risk.reward_per_share == expected_reward
    assert risk.risk_reward_ratio == expected_rr
    assert "Ideal Entry" in risk.rr_basis
    assert "Maximum Acceptable Entry" in risk.rr_basis
    assert "DO NOT ENTER ABOVE" in risk.rr_basis


def test_entry_zone_strictly_satisfies_minimum_rr():
    """Verify that for qualified setups, entry_max is strictly <= max_acceptable_entry and worst-case R:R >= 1.5:1."""
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    tech = TechnicalSnapshot(
        close=520.0,
        support=495.0,
        resistance=525.0,
        atr14=12.0,
        volume=250_000,
    )
    cand = CandidateSetup(stock=stock, archetype="Breakout", score=85, rationale="Breakout", technicals=tech)
    risk = evaluate_risk(cand, min_rr=1.5)

    assert risk.passed is True
    # The ceiling of the entry zone must never exceed max_acceptable_entry
    assert risk.entry_max <= risk.max_acceptable_entry

    # Calculate R:R at entry_max
    risk_at_max = risk.entry_max - risk.stop_loss
    reward_at_max = risk.target_1 - risk.entry_max
    rr_at_max = reward_at_max / risk_at_max

    # Worst case R:R in the entire displayed entry zone must be at least 1.50:1
    assert rr_at_max >= 1.49  # rounding tolerance
    assert risk.min_rr_at_max_entry >= 1.5


def test_position_sizing_mathematical_limits():
    """Verify position sizing honors 1% risk limit and 10% max capital cap."""
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    tech = TechnicalSnapshot(
        close=520.0,
        support=495.0,
        atr14=12.0,
        volume=250_000,
    )
    cand = CandidateSetup(stock=stock, archetype="Breakout", score=85, rationale="Breakout", technicals=tech)
    portfolio_cap = 1_000_000.0  # ₹10 Lakhs
    risk = evaluate_risk(cand, portfolio_capital=portfolio_cap, risk_per_trade_pct=1.0)

    max_allowed_loss = portfolio_cap * 0.01  # ₹10,000
    max_allowed_capital = portfolio_cap * 0.10  # ₹100,000

    assert risk.maximum_loss_at_stop <= max_allowed_loss
    assert risk.capital_deployed <= max_allowed_capital + 1000.0  # single share granularity
    assert risk.actual_risk_pct <= 1.05


def test_risk_engine_stop_distance_veto():
    stock = Stock(name="Volatile Stock", symbol="VOLT.NS")
    tech = TechnicalSnapshot(
        close=100.0,
        support=84.0,  # 16% risk
        volume=100_000,
    )
    cand = CandidateSetup(stock=stock, archetype="Breakout", score=75, rationale="Test", technicals=tech)
    risk = evaluate_risk(cand, max_stop_pct=8.0)
    assert risk.passed is False
    assert "exceeds maximum allowable risk limit" in risk.veto_reason


def test_risk_engine_liquidity_veto():
    stock = Stock(name="Illiquid Stock", symbol="ILLIQ.NS")
    tech = TechnicalSnapshot(
        close=100.0,
        support=95.0,
        volume=5_000,  # Below 20,000 threshold
    )
    cand = CandidateSetup(stock=stock, archetype="Breakout", score=75, rationale="Test", technicals=tech)
    risk = evaluate_risk(cand, min_volume=20_000)
    assert risk.passed is False
    assert "Insufficient liquidity" in risk.veto_reason


def test_risk_engine_inverted_entry_zone_veto():
    """Verify that if max acceptable entry falls below entry_min, risk engine vetoes setup."""
    stock = Stock(name="Marginal Stock", symbol="MARG.NS")
    tech = TechnicalSnapshot(
        close=520.0,
        support=495.0,
        resistance=525.0,
        atr14=12.0,
        volume=250_000,
    )
    cand = CandidateSetup(stock=stock, archetype="Breakout", score=85, rationale="Test", technicals=tech)
    # Require an extremely high min_rr that forces max_acceptable_entry below entry_min
    risk = evaluate_risk(cand, min_rr=4.0)
    assert risk.passed is False
    assert "below minimum required" in risk.veto_reason or "Entry zone inverted" in risk.veto_reason


# ============================================================================
# 9. Setup Waiting Engine
# ============================================================================

def test_waiting_engine_generation():
    stock = Stock(name="VA Tech Wabag", symbol="WABAG.NS")
    tech = TechnicalSnapshot(close=1240.0, resistance=1285.0, support=1210.0, trend_status="NEUTRAL")
    wait = generate_wait_condition(stock, tech)
    assert wait.symbol == "WABAG.NS"
    assert wait.current_price == 1240.0
    assert len(wait.exact_confirmation_required) >= 1
    assert "Daily close above ₹1285.0" in wait.exact_price_confirmation
    assert wait.technical_invalidation_floor == "Daily close below ₹1210.0"


# ============================================================================
# 10. Watchlist Full Coverage Scanner
# ============================================================================

def test_watchlist_full_coverage():
    stocks = [
        Stock(name="Stock A", symbol="A.NS"),
        Stock(name="Stock B", symbol="B.NS"),
        Stock(name="Stock C", symbol="C.NS"),
    ]
    market_data = {
        "A.NS": TechnicalSnapshot(close=100.0),
        "B.NS": TechnicalSnapshot(close=200.0),
    }
    cards = scan_all_stocks(stocks, market_data, {})
    assert len(cards) == 3
    symbols = [c.stock.symbol for c in cards]
    assert "A.NS" in symbols
    assert "B.NS" in symbols
    assert "C.NS" in symbols


# ============================================================================
# 11. SQLite Persistence & Outcome Tracking
# ============================================================================

def test_storage_and_outcome_tracking(tmp_path: Path):
    db_file = tmp_path / "test_stage2.db"
    db = Stage2Database(db_file)

    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    setup = TradeSetup(
        setup_id="SETUP-PRAJIND-20260923",
        analysis_date="2026-09-23",
        setup_date="2026-09-24",
        next_trading_session="24 Sep 2026 (Thursday)",
        market_close_timestamp="2026-09-23T15:30:00+05:30",
        stock=stock,
        status="QUALIFIED_SETUP",
    )
    db.save_setup(setup)

    retrieved = db.get_setup("SETUP-PRAJIND-20260923")
    assert retrieved is not None
    assert retrieved.stock.symbol == "PRAJIND.NS"
    assert retrieved.status == "QUALIFIED_SETUP"

    # Outcome tracking
    outcome = SetupOutcome(
        setup_id="SETUP-PRAJIND-20260923",
        symbol="PRAJIND.NS",
        entry_triggered=True,
        actual_entry_price=518.0,
        mfe_pct=8.5,
        mae_pct=-1.2,
        target_hit=True,
    )
    db.save_outcome(outcome)
    retrieved_out = db.get_outcome("SETUP-PRAJIND-20260923")
    assert retrieved_out is not None
    assert retrieved_out.mfe_pct == 8.5
    assert retrieved_out.target_hit is True


# ============================================================================
# 12. Telegram Report Formatter & Next-Day Semantics
# ============================================================================

def test_telegram_report_formatting():
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS")
    cards = [
        DailyStockCard(
            stock=stock,
            price=522.50,
            day_change_pct=3.4,
            volume=450_000,
            volume_avg_20d=250_000,
            volume_ratio=1.8,
            developments=["GOBARdhan policy approval"],
            catalysts=["GOBARdhan Bioenergy"],
            support=495.0,
            resistance=525.0,
            tomorrow_status="QUALIFIED_SETUP",
        )
    ]
    setup = TradeSetup(
        setup_id="SETUP-01",
        analysis_date="2026-09-23",
        setup_date="2026-09-24",
        next_trading_session="24 Sep 2026 (Thursday)",
        stock=stock,
        status="QUALIFIED_SETUP",
        risk=RiskAssessment(
            passed=True,
            entry_min=518.0,
            entry_max=525.0,
            ideal_entry=522.0,
            trigger_condition="Break ₹525 on volume",
            stop_loss=495.0,
            target_1=565.0,
            target_2=590.0,
            target_3=620.0,
            risk_reward_ratio=1.6,
            rr_basis="Ideal Entry ₹522",
            technical_invalidation="Daily close below stop loss ₹495.00",
            breakout_failure_condition="Closes back below ₹525.0",
            share_quantity=192,
            capital_deployed=100224.0,
            position_size_pct=10.0,
            maximum_loss_at_stop=5184.0,
            actual_risk_pct=0.52,
        ),
    )
    report = build_full_telegram_report("23 Sep 2026 — AFTER MARKET", cards, [], [setup])
    assert "SECTION 1" in report["section1"]
    assert "SECTION 2" in report["section2"]
    assert "SECTION 3" in report["section3"]
    assert "PRAJ INDUSTRIES" in report["full_text"]
    assert "*NEXT SESSION:* 24 Sep 2026 (Thursday)" in report["full_text"]
    assert "Technical Invalidation:" in report["full_text"]
    assert "Daily close below stop loss ₹495.00" in report["full_text"]
    assert "Breakout Failure Condition:" in report["full_text"]
    assert "Position Sizing & Risk Management" in report["full_text"]
    assert "QUALIFIED_SETUP" in report["full_text"]


def test_telegram_empty_catalysts_safe():
    """Verify build_full_telegram_report does not crash when catalysts list is empty."""
    stock = Stock(name="Quiet Stock", symbol="QUIET.NS")
    card = DailyStockCard(
        stock=stock,
        price=100.0,
        day_change_pct=0.0,
        volume=50_000,
        volume_avg_20d=50_000,
        volume_ratio=1.0,
        catalysts=[],  # completely empty
        developments=[],
    )
    report = build_full_telegram_report("23 Sep 2026 — AFTER MARKET", [card], [], [])
    assert report is not None
    assert "QUIET" in report["full_text"]


# ============================================================================
# 13. Live Production vs Mock Separation
# ============================================================================

def test_production_mode_uses_live_sources_not_mocks():
    """Verify production pipeline enforces live sources and does not mock data."""
    # Production pipeline
    pipeline = Stage2Pipeline(mode="production")
    assert pipeline.mode == "production"
    assert pipeline.market_engine.mode == "production"
    assert pipeline.news_engine.mode == "production"

    # In production mode with unknown ticker, it returns None (never silent mock)
    snap = pipeline.market_engine.get_snapshot("UNKNOWN_SYMBOL.NS")
    assert snap is None

    # In mock mode, it uses deterministic mock engine
    mock_pipeline = Stage2Pipeline(mode="mock")
    assert mock_pipeline.mode == "mock"
    assert mock_pipeline.market_engine.mode == "mock"
    mock_snap = mock_pipeline.market_engine.get_snapshot("PRAJIND.NS")
    assert mock_snap is not None
    assert mock_snap.close == 522.50


# ============================================================================
# 14. Full End-to-End Pipeline Dry-Run
# ============================================================================

def test_full_pipeline_run():
    provider = MockProvider()
    pipeline = Stage2Pipeline(provider=provider, mode="mock")
    result = pipeline.run(dry_run=True, session_date="2026-09-23")

    assert result["session_info"].analysis_date == "2026-09-23"
    assert len(result["cards"]) > 0
    assert len(result["setups"]) == len(result["cards"])
    assert "report" in result
    assert "SECTION 1" in result["report"]["section1"]
    assert "SECTION 3" in result["report"]["section3"]
    assert "NEXT SESSION:" in result["report"]["full_text"]
    assert "Technical Invalidation:" in result["report"]["full_text"]
    assert "Position Sizing & Risk Management" in result["report"]["full_text"]
