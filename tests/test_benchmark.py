"""
Unit and integration tests for BenchmarkEngine and benchmark comparative performance.
Ensures zero-lookahead bias, proper handling of market holidays/weekends,
and graceful degradation when benchmark data or completed trades are unavailable.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import pandas as pd

from scheme_intel.market.benchmark import BenchmarkEngine
from scheme_intel.analytics.benchmark import evaluate_benchmark_performance


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_scheme_intel.db"
    return db_file


@pytest.fixture
def populated_engine(temp_db: Path) -> BenchmarkEngine:
    engine = BenchmarkEngine(db_path=temp_db)
    # Populate with synthetic NIFTY 50 trading days
    # Day 1: 2026-09-01 -> 25000.0
    # Day 2: 2026-09-02 -> 25100.0 (+0.4%)
    # Day 3: 2026-09-03 -> 24900.0 (-0.8% from Day 2)
    # Day 4: 2026-09-04 -> 25250.0 (Friday)
    # Weekend: 2026-09-05 (Sat), 2026-09-06 (Sun) - no data
    # Day 5: 2026-09-07 -> 25300.0 (Monday)
    with engine._get_connection() as conn:
        records = [
            ("NIFTY50", "2026-09-01", 24950.0, 25050.0, 24900.0, 25000.0, 10000.0, "synthetic"),
            ("NIFTY50", "2026-09-02", 25020.0, 25150.0, 25000.0, 25100.0, 12000.0, "synthetic"),
            ("NIFTY50", "2026-09-03", 25100.0, 25120.0, 24850.0, 24900.0, 11000.0, "synthetic"),
            ("NIFTY50", "2026-09-04", 24920.0, 25300.0, 24900.0, 25250.0, 15000.0, "synthetic"),
            ("NIFTY50", "2026-09-07", 25280.0, 25350.0, 25200.0, 25300.0, 14000.0, "synthetic"),
        ]
        conn.executemany(
            """INSERT INTO benchmark_prices (benchmark_id, date, open, high, low, close, volume, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            records,
        )
        conn.commit()
    return engine


def test_benchmark_schema_init(temp_db: Path):
    engine = BenchmarkEngine(db_path=temp_db)
    with engine._get_connection() as conn:
        res = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='benchmark_prices';").fetchone()
        assert res is not None
        assert res[0] == "benchmark_prices"


def test_calculate_benchmark_return_exact_dates(populated_engine: BenchmarkEngine):
    # From 2026-09-01 (25000) to 2026-09-04 (25250)
    # Expected return: (25250 - 25000) / 25000 * 100 = +1.0%
    ret = populated_engine.calculate_benchmark_return("2026-09-01", "2026-09-04")
    assert ret == pytest.approx(1.0, rel=1e-3)


def test_calculate_benchmark_return_zero_holding_days(populated_engine: BenchmarkEngine):
    # Entry and exit on same date -> return is 0.0%
    ret = populated_engine.calculate_benchmark_return("2026-09-02", "2026-09-02")
    assert ret == 0.0


def test_calculate_benchmark_return_zero_lookahead_weekend(populated_engine: BenchmarkEngine):
    # Exit date is Saturday 2026-09-05.
    # The nearest PRIOR available trading day must be Friday 2026-09-04 (25250).
    # Zero-lookahead MUST NOT pick Monday 2026-09-07 (25300).
    ret = populated_engine.calculate_benchmark_return("2026-09-01", "2026-09-05")
    assert ret == pytest.approx(1.0, rel=1e-3)

    # Sunday 2026-09-06 should also resolve to Friday 2026-09-04.
    ret_sun = populated_engine.calculate_benchmark_return("2026-09-01", "2026-09-06")
    assert ret_sun == pytest.approx(1.0, rel=1e-3)


def test_calculate_benchmark_return_missing_dates(populated_engine: BenchmarkEngine):
    # Requested date before any historical record -> returns None
    ret = populated_engine.calculate_benchmark_return("2025-01-01", "2025-01-05")
    assert ret is None


def test_evaluate_benchmark_performance_no_trades(populated_engine: BenchmarkEngine):
    # When zero trades have exited
    result = evaluate_benchmark_performance([], engine=populated_engine)
    assert result["status"] == "UNAVAILABLE — 0 completed trades"
    assert result["trade_comparisons"] == []
    assert result["total_trades_compared"] == 0


def test_evaluate_benchmark_performance_missing_benchmark(temp_db: Path):
    # Empty DB with no benchmark prices
    empty_engine = BenchmarkEngine(db_path=temp_db)
    completed_trades = [
        {"setup_id": "setup-1", "symbol": "DEEPAKFERT", "realized_pnl_pct": 5.0, "entry_date": "2026-09-01", "exit_date": "2026-09-04"}
    ]
    result = evaluate_benchmark_performance(completed_trades, engine=empty_engine)
    assert result["status"] == "UNAVAILABLE — benchmark data missing"
    assert result["total_trades_compared"] == 0


def test_evaluate_benchmark_performance_with_trades(populated_engine: BenchmarkEngine):
    completed_trades = [
        # Trade 1: +5.0% vs Benchmark +1.0% -> Outperformance +4.0%
        {"setup_id": "setup-1", "symbol": "DEEPAKFERT", "realized_pnl_pct": 5.0, "entry_date": "2026-09-01", "exit_date": "2026-09-04"},
        # Trade 2: -2.0% vs Benchmark -0.8% (2026-09-02 to 2026-09-03: (24900-25100)/25100 = -0.7968%) -> Underperformance
        {"setup_id": "setup-2", "symbol": "NFL", "realized_pnl_pct": -2.0, "entry_date": "2026-09-02", "exit_date": "2026-09-03"},
    ]
    result = evaluate_benchmark_performance(completed_trades, engine=populated_engine)
    assert result["status"] == "ACTIVE"
    assert result["total_trades_compared"] == 2
    assert len(result["trade_comparisons"]) == 2
    assert result["win_rate_vs_benchmark_pct"] == 50.0
    assert result["alpha_pct"] is not None
    assert "benchmark_id" in result
    assert result["benchmark_id"] == "NIFTY50"


def test_sync_benchmark_mocked(temp_db: Path):
    engine = BenchmarkEngine(db_path=temp_db)
    dates = pd.date_range("2026-09-01", periods=3, freq="D")
    df = pd.DataFrame({
        "Open": [25000.0, 25100.0, 25200.0],
        "High": [25050.0, 25150.0, 25250.0],
        "Low": [24950.0, 25050.0, 25150.0],
        "Close": [25020.0, 25120.0, 25220.0],
        "Volume": [1000, 2000, 3000],
    }, index=dates)

    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.return_value = df
        mock_ticker.return_value = mock_instance

        count = engine.sync_benchmark(days_back=5)
        assert count == 3

        # Sync again with duplicate data -> upsert count should be 3
        count2 = engine.sync_benchmark(days_back=5)
        assert count2 == 3
