"""
Unit and regression test suite for Forward Performance Analytics and Validation Engine.
Covers:
- Zero setups, single untriggered setup (untriggered never counted as loss)
- Insufficient sample guards and labeling
- Wins, losses, expired, target hit, stop hit calculations
- P&L metrics: average, median, cumulative, profit factor, expectancy, std dev
- MFE / MAE excursion distributions and extremes
- Holding period metrics broken down by outcome
- Archetype, Symbol, AI Provider, and Score-Band breakdowns
- Chronological daily time series
- Walk-forward rolling windows
- Out-of-sample partition separation
- Data integrity checks (duplicates, orphans, inverted dates, contradictory flags)
- JSON and Markdown report generation
- Compact Telegram summary generation
- CRITICAL REGRESSION TEST: Absolute prevention of future data leakage into historical evaluation
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from scheme_intel.stage2.models import (
    CandidateSetup,
    Stock,
    TechnicalSnapshot,
    TradeSetup,
    SetupOutcome,
    BullThesis,
    BearThesis,
    DebateResult,
    RiskAssessment,
)
from scheme_intel.stage2.storage import Stage2Database
from scheme_intel.stage2.performance import (
    PerformanceAnalytics,
    MIN_COMPLETED_TRADES,
    MIN_ARCHETYPE_SAMPLE,
    MIN_STOCK_SAMPLE,
)


def _make_dummy_setup(
    setup_id: str,
    symbol: str,
    date: str,
    status: str = "QUALIFIED_SETUP",
    archetype: str = "Breakout",
    score: int = 80,
    ai_provider: str = "groq",
) -> TradeSetup:
    stock = Stock(name=symbol, symbol=symbol, sectors=["Energy"])
    tech = TechnicalSnapshot(
        close=100.0, open=99.0, high=102.0, low=98.0, prev_close=99.0,
        volume=1_000_000, volume_20d_avg=500_000, atr14=3.0,
    )
    cand = CandidateSetup(
        stock=stock,
        archetype=archetype,
        score=score,
        rationale="Strong volume breakout above resistance",
        technicals=tech,
    )
    risk = RiskAssessment(
        passed=True,
        entry_min=99.0,
        entry_max=101.0,
        ideal_entry=100.0,
        stop_loss=95.0,
        target_1=110.0,
        target_2=115.0,
        target_3=120.0,
        risk_reward_ratio=2.0,
    )
    debate = DebateResult(symbol=symbol, provider=ai_provider)
    return TradeSetup(
        setup_id=setup_id,
        analysis_date=date,
        setup_date=date,
        next_trading_session=f"Next ({date})",
        stock=stock,
        status=status,
        candidate=cand,
        risk=risk,
        debate=debate,
        ai_provider=ai_provider,
    )


@pytest.fixture
def temp_db(tmp_path: Path) -> Stage2Database:
    db_file = tmp_path / "test_perf.db"
    return Stage2Database(db_path=db_file)


# -----------------------------------------------------------------------------
# 1. Zero Setups Test
# -----------------------------------------------------------------------------
def test_zero_setups(temp_db: Stage2Database):
    pa = PerformanceAnalytics(temp_db)
    rep = pa.calculate()

    assert rep.setup_metrics.total_setups == 0
    assert rep.outcome_metrics.completed_trades == 0
    assert rep.outcome_metrics.win_rate is None
    assert rep.pnl_metrics.average_pnl_pct is None
    assert rep.data_sufficiency["status"] == "INSUFFICIENT_SAMPLE"
    assert rep.strategy_status == "INSUFFICIENT DATA"
    assert rep.data_integrity.status == "PASS"

    summary = pa.get_telegram_summary(rep)
    assert "collecting data — 0 completed trades" in summary


# -----------------------------------------------------------------------------
# 2. Single Untriggered Setup (Never Counted as a Loss)
# -----------------------------------------------------------------------------
def test_untriggered_setup_not_counted_as_loss(temp_db: Stage2Database):
    s = _make_dummy_setup("S1", "IOC.NS", "2026-09-01")
    temp_db.save_setup(s)

    pa = PerformanceAnalytics(temp_db)
    rep = pa.calculate()

    assert rep.setup_metrics.total_setups == 1
    assert rep.setup_metrics.qualified_setups == 1
    assert rep.setup_metrics.triggered_setups == 0
    assert rep.setup_metrics.untriggered_setups == 1
    assert rep.outcome_metrics.completed_trades == 0
    assert rep.outcome_metrics.losses == 0  # CRITICAL: untriggered is NOT a loss
    assert rep.outcome_metrics.win_rate is None
    assert rep.pnl_metrics.average_pnl_pct is None


# -----------------------------------------------------------------------------
# 3. Insufficient Sample Guards and Labels
# -----------------------------------------------------------------------------
def test_insufficient_sample_guards(temp_db: Stage2Database):
    # Create 2 completed trades (1 win, 1 loss)
    for i in range(2):
        sid = f"S{i}"
        s = _make_dummy_setup(sid, "IOC.NS", "2026-09-01")
        temp_db.save_setup(s)

    temp_db.save_outcome(SetupOutcome(
        setup_id="S0", symbol="IOC.NS", entry_triggered=True,
        actual_entry_price=100.0, entry_date="2026-09-02",
        exit_price=110.0, exit_date="2026-09-05",
        target_hit=True, realized_pnl_pct=10.0, holding_period_days=3,
    ))
    temp_db.save_outcome(SetupOutcome(
        setup_id="S1", symbol="IOC.NS", entry_triggered=True,
        actual_entry_price=100.0, entry_date="2026-09-02",
        exit_price=95.0, exit_date="2026-09-04",
        stop_hit=True, realized_pnl_pct=-5.0, holding_period_days=2,
    ))

    pa = PerformanceAnalytics(temp_db)
    rep = pa.calculate()

    assert rep.outcome_metrics.completed_trades == 2
    assert rep.outcome_metrics.win_rate == 50.0
    # Must be explicitly labeled as insufficient sample
    assert rep.data_sufficiency["status"] == "INSUFFICIENT_SAMPLE"
    assert "Insufficient sample (2 completed trades" in rep.data_sufficiency["label"]
    assert rep.strategy_status == "INSUFFICIENT DATA"

    # Telegram summary must not state validated stats
    summary = pa.get_telegram_summary(rep)
    assert "collecting data — 2 completed trades" in summary


# -----------------------------------------------------------------------------
# 4. Return and P&L Mathematical Precision
# -----------------------------------------------------------------------------
def test_pnl_mathematical_precision(temp_db: Stage2Database):
    # Setup outcomes: 3 wins (+5%, +10%, +3%), 2 losses (-2%, -4%), 1 expired (-1%)
    trade_specs = [
        ("S1", True, False, False, 5.0, 3),
        ("S2", True, False, False, 10.0, 5),
        ("S3", True, False, False, 3.0, 2),
        ("S4", False, True, False, -2.0, 1),
        ("S5", False, True, False, -4.0, 3),
        ("S6", False, False, True, -1.0, 5),
    ]

    for sid, tgt, sl, exp, pnl, hp in trade_specs:
        s = _make_dummy_setup(sid, "TEST.NS", "2026-09-01")
        temp_db.save_setup(s)
        temp_db.save_outcome(SetupOutcome(
            setup_id=sid,
            symbol="TEST.NS",
            entry_triggered=True,
            actual_entry_price=100.0,
            entry_date="2026-09-02",
            exit_price=100.0 * (1.0 + pnl / 100.0),
            exit_date="2026-09-05",
            mfe_pct=max(0.0, pnl + 1.0),
            mae_pct=min(0.0, pnl - 1.0),
            target_hit=tgt,
            stop_hit=sl,
            expired=exp,
            realized_pnl_pct=pnl,
            holding_period_days=hp,
        ))

    pa = PerformanceAnalytics(temp_db)
    rep = pa.calculate()

    om = rep.outcome_metrics
    pm = rep.pnl_metrics

    # Denominator = 6 completed trades
    assert om.completed_trades == 6
    assert om.wins == 3
    assert om.losses == 3
    assert om.target_hits == 3
    assert om.stop_hits == 2
    assert om.expired == 1
    assert om.win_rate == 50.0
    assert om.loss_rate == 50.0
    assert om.expiry_rate == round(1 / 6 * 100, 1)

    # Average P&L = (5 + 10 + 3 - 2 - 4 - 1) / 6 = 11 / 6 = +1.83%
    assert pm.average_pnl_pct == 1.83
    # Median of [-4, -2, -1, 3, 5, 10] = (-1 + 3) / 2 = +1.0%
    assert pm.median_pnl_pct == 1.00
    assert pm.cumulative_pnl_pct == 11.00
    # Average win: (5 + 10 + 3) / 3 = 6.00%
    assert pm.average_win_pct == 6.00
    # Average loss: (-2 + -4 + -1) / 3 = -2.33%
    assert pm.average_loss_pct == -2.33
    assert pm.largest_winner_pct == 10.00
    assert pm.largest_loser_pct == -4.00

    # Profit Factor = gross profits (18) / abs(gross losses) (7) = 2.57
    assert pm.profit_factor == 2.57

    # Expectancy = (0.50 * 6.00) + (0.50 * -2.333) = 3.00 - 1.167 = +1.83%
    assert pm.expectancy == 1.83


# -----------------------------------------------------------------------------
# 5. Profit Factor with Zero Losses
# -----------------------------------------------------------------------------
def test_profit_factor_zero_losses(temp_db: Stage2Database):
    s = _make_dummy_setup("S1", "TEST.NS", "2026-09-01")
    temp_db.save_setup(s)
    temp_db.save_outcome(SetupOutcome(
        setup_id="S1", symbol="TEST.NS", entry_triggered=True,
        actual_entry_price=100.0, entry_date="2026-09-02",
        target_hit=True, realized_pnl_pct=5.0, holding_period_days=2,
    ))

    pa = PerformanceAnalytics(temp_db)
    rep = pa.calculate()
    assert rep.pnl_metrics.profit_factor == float("inf")


# -----------------------------------------------------------------------------
# 6. MFE / MAE Analytics & Bucket Distributions
# -----------------------------------------------------------------------------
def test_mfe_mae_distributions(temp_db: Stage2Database):
    s1 = _make_dummy_setup("S1", "TEST.NS", "2026-09-01")
    s2 = _make_dummy_setup("S2", "TEST.NS", "2026-09-01")
    temp_db.save_setup(s1)
    temp_db.save_setup(s2)

    temp_db.save_outcome(SetupOutcome(
        setup_id="S1", symbol="TEST.NS", entry_triggered=True,
        mfe_pct=4.5, mae_pct=-0.5, holding_period_days=2,
    ))
    temp_db.save_outcome(SetupOutcome(
        setup_id="S2", symbol="TEST.NS", entry_triggered=True,
        mfe_pct=11.2, mae_pct=-4.2, holding_period_days=4,
    ))

    pa = PerformanceAnalytics(temp_db)
    rep = pa.calculate()
    em = rep.excursion_metrics

    assert em.average_mfe_pct == round((4.5 + 11.2) / 2, 2)
    assert em.maximum_mfe_pct == 11.2
    assert em.average_mae_pct == round((-0.5 + -4.2) / 2, 2)
    assert em.maximum_adverse_excursion == -4.2

    # Check distribution buckets
    assert em.mfe_distribution["2–5%"] == 1
    assert em.mfe_distribution[">10%"] == 1
    assert em.mae_distribution["0 to -1%"] == 1
    assert em.mae_distribution["-3 to -5%"] == 1


# -----------------------------------------------------------------------------
# 7. Holding Period Breakdown
# -----------------------------------------------------------------------------
def test_holding_period_breakdown(temp_db: Stage2Database):
    s1 = _make_dummy_setup("S1", "TEST.NS", "2026-09-01")
    s2 = _make_dummy_setup("S2", "TEST.NS", "2026-09-01")
    s3 = _make_dummy_setup("S3", "TEST.NS", "2026-09-01")
    temp_db.save_setup(s1)
    temp_db.save_setup(s2)
    temp_db.save_setup(s3)

    temp_db.save_outcome(SetupOutcome(
        setup_id="S1", symbol="TEST.NS", entry_triggered=True,
        target_hit=True, realized_pnl_pct=5.0, holding_period_days=2,
    ))
    temp_db.save_outcome(SetupOutcome(
        setup_id="S2", symbol="TEST.NS", entry_triggered=True,
        stop_hit=True, realized_pnl_pct=-3.0, holding_period_days=4,
    ))
    temp_db.save_outcome(SetupOutcome(
        setup_id="S3", symbol="TEST.NS", entry_triggered=True,
        expired=True, realized_pnl_pct=-0.5, holding_period_days=5,
    ))

    pa = PerformanceAnalytics(temp_db)
    rep = pa.calculate()
    hp = rep.holding_period_metrics

    assert hp.overall["average"] == round((2 + 4 + 5) / 3, 1)
    assert hp.overall["min"] == 2.0
    assert hp.overall["max"] == 5.0
    assert hp.wins["average"] == 2.0
    assert hp.losses["average"] == 4.5  # S2 (4d) + S3 (5d) are both losing trades: (4+5)/2 = 4.5
    assert hp.expired["average"] == 5.0


# -----------------------------------------------------------------------------
# 8. Breakdowns by Archetype, Symbol, AI Provider, Score Band
# -----------------------------------------------------------------------------
def test_breakdowns_and_disclaimers(temp_db: Stage2Database):
    s1 = _make_dummy_setup("S1", "IOC.NS", "2026-09-01", archetype="Breakout", score=85, ai_provider="groq")
    s2 = _make_dummy_setup("S2", "GAIL.NS", "2026-09-01", archetype="Pullback", score=65, ai_provider="gemini")
    temp_db.save_setup(s1)
    temp_db.save_setup(s2)

    temp_db.save_outcome(SetupOutcome(
        setup_id="S1", symbol="IOC.NS", entry_triggered=True,
        target_hit=True, realized_pnl_pct=6.0, holding_period_days=2,
    ))
    temp_db.save_outcome(SetupOutcome(
        setup_id="S2", symbol="GAIL.NS", entry_triggered=True,
        stop_hit=True, realized_pnl_pct=-3.0, holding_period_days=3,
    ))

    pa = PerformanceAnalytics(temp_db)
    rep = pa.calculate()

    # Archetypes
    arch_map = {a.archetype: a for a in rep.archetype_breakdown}
    assert "Breakout" in arch_map
    assert arch_map["Breakout"].completed == 1
    assert arch_map["Breakout"].win_rate == 100.0
    assert arch_map["Breakout"].sample_status == "INSUFFICIENT_SAMPLE"  # < 20 sample

    # Symbols
    sym_map = {s.symbol: s for s in rep.symbol_breakdown}
    assert "IOC.NS" in sym_map
    assert sym_map["IOC.NS"].win_rate == 100.0
    assert sym_map["IOC.NS"].sample_status == "INSUFFICIENT_SAMPLE"

    # AI Providers (observational only)
    prov_map = {p.provider: p for p in rep.provider_breakdown}
    assert "groq" in prov_map
    assert prov_map["groq"].average_pnl_pct == 6.0
    assert "Observational analysis only" in prov_map["groq"].observational_note

    # Score Bands
    bands = {b.band_label: b for b in rep.score_band_breakdown}
    assert "81–100" in bands
    assert bands["81–100"].completed == 1
    assert bands["81–100"].win_rate == 100.0
    assert "61–80" in bands
    assert bands["61–80"].completed == 1
    assert bands["61–80"].win_rate == 0.0


# -----------------------------------------------------------------------------
# 9. Chronological Daily Time Series
# -----------------------------------------------------------------------------
def test_chronological_daily_time_series(temp_db: Stage2Database):
    # Day 1: 1 win (+4%)
    s1 = _make_dummy_setup("S1", "IOC.NS", "2026-09-01")
    temp_db.save_setup(s1)
    temp_db.save_outcome(SetupOutcome(
        setup_id="S1", symbol="IOC.NS", entry_triggered=True,
        target_hit=True, realized_pnl_pct=4.0, holding_period_days=1,
    ))

    # Day 2: 1 loss (-2%)
    s2 = _make_dummy_setup("S2", "GAIL.NS", "2026-09-02")
    temp_db.save_setup(s2)
    temp_db.save_outcome(SetupOutcome(
        setup_id="S2", symbol="GAIL.NS", entry_triggered=True,
        stop_hit=True, realized_pnl_pct=-2.0, holding_period_days=1,
    ))

    pa = PerformanceAnalytics(temp_db)
    rep = pa.calculate()

    series = rep.daily_series
    assert len(series) == 2
    assert series[0].date == "2026-09-01"
    assert series[0].daily_realized_pnl_pct == 4.0
    assert series[0].cumulative_pnl_pct == 4.0

    assert series[1].date == "2026-09-02"
    assert series[1].daily_realized_pnl_pct == -2.0
    assert series[1].cumulative_pnl_pct == 2.0  # 4.0 - 2.0 = 2.0


# -----------------------------------------------------------------------------
# 10. Data Integrity Audit Checks
# -----------------------------------------------------------------------------
def test_data_integrity_duplicate_and_orphan_detection(temp_db: Stage2Database):
    s1 = _make_dummy_setup("S1", "IOC.NS", "2026-09-01")
    temp_db.save_setup(s1)

    # 1. Orphan outcome (setup does not exist) - insert with FK check bypassed
    with temp_db._get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = OFF;")
        conn.execute(
            "INSERT INTO stage2_outcomes (setup_id, symbol, entry_triggered, realized_pnl_pct, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("ORPHAN_999", "UNKNOWN.NS", 1, 5.0, "2026-09-01"),
        )
        conn.commit()

    # 2. Contradictory flags: target_hit AND stop_hit both True
    temp_db.save_outcome(SetupOutcome(
        setup_id="S1", symbol="IOC.NS", entry_triggered=True,
        target_hit=True, stop_hit=True, realized_pnl_pct=2.0,
    ))

    pa = PerformanceAnalytics(temp_db)
    rep = pa.calculate()

    assert rep.data_integrity.status == "WARN"
    assert rep.data_integrity.issues_detected >= 2
    issue_text = " ".join(rep.data_integrity.issues)
    assert "Orphan outcome detected" in issue_text
    assert "both target_hit and stop_hit are marked True simultaneously" in issue_text


def test_data_integrity_impossible_dates_detection(temp_db: Stage2Database):
    s = _make_dummy_setup("S1", "IOC.NS", "2026-09-10")
    temp_db.save_setup(s)

    # Exit date earlier than entry date
    temp_db.save_outcome(SetupOutcome(
        setup_id="S1", symbol="IOC.NS", entry_triggered=True,
        entry_date="2026-09-12", exit_date="2026-09-11",
        target_hit=True, realized_pnl_pct=3.0,
    ))

    pa = PerformanceAnalytics(temp_db)
    rep = pa.calculate()

    assert rep.data_integrity.status == "WARN"
    issue_text = " ".join(rep.data_integrity.issues)
    assert "exit_date (2026-09-11) is earlier than entry_date (2026-09-12)" in issue_text


# -----------------------------------------------------------------------------
# 11. Report Generation: JSON, Markdown, and Telegram
# -----------------------------------------------------------------------------
def test_json_and_markdown_generation(temp_db: Stage2Database, tmp_path: Path):
    s = _make_dummy_setup("S1", "IOC.NS", "2026-09-01")
    temp_db.save_setup(s)
    temp_db.save_outcome(SetupOutcome(
        setup_id="S1", symbol="IOC.NS", entry_triggered=True,
        target_hit=True, realized_pnl_pct=5.0, holding_period_days=2,
    ))

    out_dir = tmp_path / "perf_out"
    pa = PerformanceAnalytics(temp_db)
    json_file, md_file, rep = pa.generate_reports(output_dir=out_dir)

    assert json_file.exists()
    assert md_file.exists()

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["setup_metrics"]["total_setups"] == 1
    assert data["outcome_metrics"]["completed_trades"] == 1
    assert data["pnl_metrics"]["average_pnl_pct"] == 5.0

    with open(md_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "# Scheme-Intel Forward Performance & Validation Report" in content
    assert "Breakout" in content
    assert "IOC.NS" in content


# -----------------------------------------------------------------------------
# 12. Telegram Summary Behavior
# -----------------------------------------------------------------------------
def test_telegram_summary_states(temp_db: Stage2Database):
    pa = PerformanceAnalytics(temp_db)

    # 1. Under MIN_COMPLETED_TRADES
    s1 = _make_dummy_setup("S1", "IOC.NS", "2026-09-01")
    temp_db.save_setup(s1)
    temp_db.save_outcome(SetupOutcome(
        setup_id="S1", symbol="IOC.NS", entry_triggered=True,
        target_hit=True, realized_pnl_pct=5.0,
    ))
    rep = pa.calculate()
    sum1 = pa.get_telegram_summary(rep)
    assert "collecting data — 1 completed trades" in sum1
    assert "VALIDATED" not in sum1

    # 2. At or over MIN_COMPLETED_TRADES
    pa_small = PerformanceAnalytics(temp_db, min_completed_trades=1)
    rep2 = pa_small.calculate()
    sum2 = pa_small.get_telegram_summary(rep2)
    assert "FORWARD PERFORMANCE (VALIDATED)" in sum2
    assert "Trades: *1*" in sum2
    assert "Win Rate: *100.0%*" in sum2


# -----------------------------------------------------------------------------
# 13. CRITICAL REGRESSION: NO FUTURE DATA LEAKAGE
# -----------------------------------------------------------------------------
def test_no_future_data_leakage_regression(temp_db: Stage2Database):
    """
    REGRESSION PROOF:
    A setup evaluated on date T1 cannot use any outcome occurring after T1
    to influence earlier evaluations.
    Walk-forward validation respects chronological setup dates strictly.
    """
    # 3 setups across consecutive dates:
    # Day 1: 2026-09-01
    s1 = _make_dummy_setup("S1", "IOC.NS", "2026-09-01")
    temp_db.save_setup(s1)
    temp_db.save_outcome(SetupOutcome(
        setup_id="S1", symbol="IOC.NS", entry_triggered=True,
        actual_entry_price=100.0, entry_date="2026-09-02",
        exit_price=105.0, exit_date="2026-09-04",
        target_hit=True, realized_pnl_pct=5.0, holding_period_days=2,
    ))

    # Day 2: 2026-09-05
    s2 = _make_dummy_setup("S2", "GAIL.NS", "2026-09-05")
    temp_db.save_setup(s2)
    temp_db.save_outcome(SetupOutcome(
        setup_id="S2", symbol="GAIL.NS", entry_triggered=True,
        actual_entry_price=200.0, entry_date="2026-09-06",
        exit_price=190.0, exit_date="2026-09-08",
        stop_hit=True, realized_pnl_pct=-5.0, holding_period_days=2,
    ))

    # Day 3: 2026-09-10 (Future setup with huge win +50%)
    s3 = _make_dummy_setup("S3", "PRAJIND.NS", "2026-09-10")
    temp_db.save_setup(s3)
    temp_db.save_outcome(SetupOutcome(
        setup_id="S3", symbol="PRAJIND.NS", entry_triggered=True,
        actual_entry_price=500.0, entry_date="2026-09-11",
        exit_price=750.0, exit_date="2026-09-15",
        target_hit=True, realized_pnl_pct=50.0, holding_period_days=4,
    ))

    pa = PerformanceAnalytics(temp_db)

    # 1. Verify daily series preserves chronological isolation
    series = pa._compute_daily_series(temp_db.list_setups(), {o.setup_id: o for o in temp_db.list_outcomes()})
    assert series[0].date == "2026-09-01"
    # S3 (+50%) did NOT exist on 2026-09-01; day 1 PnL must be strictly 5.0%
    assert series[0].daily_realized_pnl_pct == 5.0
    assert series[0].cumulative_pnl_pct == 5.0

    assert series[1].date == "2026-09-05"
    assert series[1].daily_realized_pnl_pct == -5.0
    assert series[1].cumulative_pnl_pct == 0.0  # 5.0 - 5.0

    # 2. Out of Sample separation check
    oos = pa._compute_out_of_sample_comparison(temp_db.list_setups(), {o.setup_id: o for o in temp_db.list_outcomes()})
    # With 3 trades, partition requires at least 4 trades to ensure valid in-sample + out-sample
    assert oos is None  # Guard prevents leaking incomplete partitions

    # Add a 4th trade to test partition boundary
    s4 = _make_dummy_setup("S4", "WABAG.NS", "2026-09-12")
    temp_db.save_setup(s4)
    temp_db.save_outcome(SetupOutcome(
        setup_id="S4", symbol="WABAG.NS", entry_triggered=True,
        actual_entry_price=1000.0, entry_date="2026-09-13",
        exit_price=1020.0, exit_date="2026-09-16",
        target_hit=True, realized_pnl_pct=2.0, holding_period_days=3,
    ))

    oos2 = pa._compute_out_of_sample_comparison(temp_db.list_setups(), {o.setup_id: o for o in temp_db.list_outcomes()})
    assert oos2 is not None
    # Historical chunk (S1: +5%, S2: -5%) -> average P&L = 0.0%
    assert oos2.historical_trades == 2
    assert oos2.historical_avg_pnl == 0.0
    # Future outcomes (+50%, +2%) are strictly isolated to forward chunk!
    assert oos2.forward_trades == 2
    assert oos2.forward_avg_pnl == round((50.0 + 2.0) / 2, 2)
    assert oos2.historical_avg_pnl != oos2.forward_avg_pnl
