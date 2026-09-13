"""Tests for the analytics module."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.scheme_intel.analytics import Analytics
from src.scheme_intel.db import SchemeIntelDB


@pytest.fixture
def db(tmp_path: Path):
    path = tmp_path / "test_analytics.db"
    scheme_db = SchemeIntelDB(db_path=path)
    yield scheme_db
    scheme_db.close()


@pytest.fixture
def analytics(db: SchemeIntelDB):
    return Analytics(db=db)


class TestTradeSummary:
    def test_empty_when_no_trades(self, analytics: Analytics):
        summary = analytics.trade_summary()
        assert summary.total_trades == 0
        assert summary.win_rate == 0.0

    def test_all_wins(self, analytics: Analytics, db: SchemeIntelDB):
        t1 = db.record_trade("A", "A.NS", 100, 90, 120, "2026-09-01")
        t2 = db.record_trade("B", "B.NS", 200, 180, 240, "2026-09-02")
        db.close_trade(t1, 120, "2026-09-10", "WIN")
        db.close_trade(t2, 240, "2026-09-11", "WIN")
        summary = analytics.trade_summary()
        assert summary.total_trades == 2
        assert summary.wins == 2
        assert summary.win_rate == 100.0
        assert summary.losses == 0

    def test_mixed_outcomes(self, analytics: Analytics, db: SchemeIntelDB):
        t1 = db.record_trade("A", "A.NS", 100, 90, 120, "2026-09-01")
        t2 = db.record_trade("B", "B.NS", 200, 180, 240, "2026-09-02")
        t3 = db.record_trade("C", "C.NS", 150, 140, 170, "2026-09-03")
        db.close_trade(t1, 120, "2026-09-10", "WIN")
        db.close_trade(t2, 180, "2026-09-11", "LOSS")
        db.close_trade(t3, 150, "2026-09-12", "BREAKEVEN")
        summary = analytics.trade_summary()
        assert summary.total_trades == 3
        assert summary.wins == 1
        assert summary.losses == 1
        assert summary.breakevens == 1
        assert summary.win_rate == pytest.approx(33.33, abs=0.1)

    def test_pnl_calculation(self, analytics: Analytics, db: SchemeIntelDB):
        t1 = db.record_trade("A", "A.NS", 100, 90, 120, "2026-09-01")
        db.close_trade(t1, 110, "2026-09-10", "WIN")
        summary = analytics.trade_summary()
        assert summary.avg_pnl_pct == 10.0
        assert summary.best_trade_pct == 10.0
        assert summary.worst_trade_pct == 10.0

    def test_best_and_worst(self, analytics: Analytics, db: SchemeIntelDB):
        t1 = db.record_trade("A", "A.NS", 100, 90, 120, "2026-09-01")
        t2 = db.record_trade("B", "B.NS", 200, 180, 240, "2026-09-02")
        db.close_trade(t1, 130, "2026-09-10", "WIN")
        db.close_trade(t2, 180, "2026-09-11", "LOSS")
        summary = analytics.trade_summary()
        assert summary.best_trade_pct == 30.0
        assert summary.worst_trade_pct == -10.0


class TestPerSymbol:
    def test_empty(self, analytics: Analytics):
        assert analytics.per_symbol() == []

    def test_groups_by_symbol(self, analytics: Analytics, db: SchemeIntelDB):
        t1 = db.record_trade("TruAlt", "TRUALT.NS", 100, 90, 120, "2026-09-01")
        t2 = db.record_trade("TruAlt", "TRUALT.NS", 110, 100, 130, "2026-09-02")
        t3 = db.record_trade("Praj", "PRAJIND.NS", 200, 180, 240, "2026-09-01")
        db.close_trade(t1, 120, "2026-09-10", "WIN")
        db.close_trade(t2, 100, "2026-09-11", "LOSS")
        db.close_trade(t3, 240, "2026-09-12", "WIN")
        per_symbol = analytics.per_symbol()
        assert len(per_symbol) == 2
        trualt = next(s for s in per_symbol if s.symbol == "TRUALT.NS")
        assert trualt.trades == 2
        assert trualt.wins == 1
        assert trualt.win_rate == 50.0

    def test_avg_pnl_per_symbol(self, analytics: Analytics, db: SchemeIntelDB):
        t1 = db.record_trade("A", "A.NS", 100, 90, 120, "2026-09-01")
        t2 = db.record_trade("A", "A.NS", 100, 90, 120, "2026-09-02")
        db.close_trade(t1, 120, "2026-09-10", "WIN")
        db.close_trade(t2, 130, "2026-09-11", "WIN")
        per_symbol = analytics.per_symbol()
        assert per_symbol[0].avg_pnl_pct == 25.0


class TestCatalystEffectiveness:
    def test_empty(self, analytics: Analytics):
        assert analytics.catalyst_effectiveness() == []

    def test_groups_by_score_bucket(self, analytics: Analytics, db: SchemeIntelDB):
        # Create a run with setups at different catalyst scores
        run_id = db.save_run(
            generated_at="2026-09-13T10:00:00+00:00",
            catalysts=[],
            setups=[
                {"company": "A", "symbol": "A.NS", "close": 100, "entry": 105,
                 "stop": 95, "target": 120, "rsi14": 55, "catalyst_score": 95,
                 "status": "qualified", "breakout": True, "week_trend": "UP"},
                {"company": "B", "symbol": "B.NS", "close": 200, "entry": 210,
                 "stop": 190, "target": 240, "rsi14": 60, "catalyst_score": 70,
                 "status": "qualified", "breakout": True, "week_trend": "UP"},
            ],
            source_errors=[],
        )
        setups = db.get_setups_for_run(run_id)

        # Record trades linked to these setups
        t1 = db.record_trade("A", "A.NS", 105, 95, 120, "2026-09-13", setup_id=setups[0]["id"])
        t2 = db.record_trade("B", "B.NS", 210, 190, 240, "2026-09-13", setup_id=setups[1]["id"])
        db.close_trade(t1, 130, "2026-09-20", "WIN")
        db.close_trade(t2, 195, "2026-09-18", "LOSS")

        effectiveness = analytics.catalyst_effectiveness()
        assert len(effectiveness) == 2
        high = next(c for c in effectiveness if c.score_bucket == "90-100")
        assert high.trades == 1
        assert high.wins == 1
        low = next(c for c in effectiveness if c.score_bucket == "60-74")
        assert low.trades == 1
        assert low.wins == 0


class TestPipelineStats:
    def test_empty(self, analytics: Analytics):
        stats = analytics.pipeline_stats()
        assert stats["total_runs"] == 0
        assert stats["total_setups"] == 0
        assert stats["total_trades"] == 0

    def test_populated(self, analytics: Analytics, db: SchemeIntelDB):
        db.save_run("2026-09-13T10:00:00+00:00", [], [
            {"company": "A", "symbol": "A.NS", "close": 100, "entry": 105,
             "stop": 95, "target": 120, "rsi14": 55, "catalyst_score": 80,
             "status": "qualified", "breakout": True, "week_trend": "UP"},
        ], [])
        db.record_trade("A", "A.NS", 105, 95, 120, "2026-09-13")
        stats = analytics.pipeline_stats()
        assert stats["total_runs"] == 1
        assert stats["total_setups"] == 1
        assert stats["total_trades"] == 1


class TestDashboard:
    def test_dashboard_structure(self, analytics: Analytics):
        dash = analytics.dashboard()
        assert "pipeline" in dash
        assert "trade_summary" in dash
        assert "per_symbol" in dash
        assert "catalyst_effectiveness" in dash
