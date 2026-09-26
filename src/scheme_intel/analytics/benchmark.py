"""
Benchmark Analytics and Relative Performance Engine.
Computes strategy vs NIFTY 50 excess returns and benchmark comparison metrics.
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Tuple
from ..market.benchmark import BenchmarkEngine
from ..logger import get_logger

logger = get_logger(__name__)


def evaluate_benchmark_performance(
    completed_trades: List[Any],
    benchmark_engine: Optional[BenchmarkEngine] = None,
    engine: Optional[BenchmarkEngine] = None,
) -> Dict[str, Any]:
    """
    Evaluate strategy returns against Nifty 50 benchmark returns over identical holding periods.

    CRITICAL RULES:
    1. Zero lookahead leakage: benchmark returns are only evaluated over [entry_date, exit_date].
    2. If 0 completed trades: reports 'Benchmark comparison: UNAVAILABLE — 0 completed trades'.
    3. If trades exist but benchmark data is missing: reports 'Benchmark: UNAVAILABLE — benchmark data missing'.
    4. Never fabricates synthetic benchmark numbers.
    """
    be = engine or benchmark_engine or BenchmarkEngine()
    n_total = len(completed_trades)
    if n_total == 0:
        return {
            "status": "UNAVAILABLE — 0 completed trades",
            "available": False,
            "completed_trades": 0,
            "benchmark_id": be.benchmark_id,
            "trades_evaluated": 0,
            "total_trades_compared": 0,
            "average_strategy_return": None,
            "average_benchmark_return": None,
            "average_excess_return": None,
            "alpha_pct": None,
            "median_excess_return": None,
            "cumulative_strategy_return": 0.0,
            "cumulative_benchmark_return": 0.0,
            "cumulative_excess_return": 0.0,
            "win_rate_vs_benchmark_pct": 0.0,
            "trade_comparisons": [],
        }

    trade_comparisons: List[Dict[str, Any]] = []
    strat_returns: List[float] = []
    bench_returns: List[float] = []
    excess_returns: List[float] = []

    for item in completed_trades:
        if isinstance(item, tuple):
            setup, outcome = item
            setup_id = getattr(setup, "setup_id", "")
            stock = getattr(setup, "stock", None)
            symbol = getattr(stock, "symbol", "") if stock else ""
            strat_ret = getattr(outcome, "realized_pnl_pct", None)
            entry_date = getattr(outcome, "entry_date", None)
            exit_date = getattr(outcome, "exit_date", None)
        elif isinstance(item, dict):
            setup_id = item.get("setup_id", "")
            symbol = item.get("symbol", "")
            strat_ret = item.get("realized_pnl_pct")
            entry_date = item.get("entry_date")
            exit_date = item.get("exit_date")
        else:
            setup_id = getattr(item, "setup_id", "")
            symbol = getattr(item, "symbol", "")
            strat_ret = getattr(item, "realized_pnl_pct", None)
            entry_date = getattr(item, "entry_date", None)
            exit_date = getattr(item, "exit_date", None)

        if strat_ret is None or not entry_date or not exit_date:
            continue

        b_ret = be.calculate_return(entry_date, exit_date)
        if b_ret is not None:
            excess = round(strat_ret - b_ret, 2)
            strat_returns.append(strat_ret)
            bench_returns.append(b_ret)
            excess_returns.append(excess)
            trade_comparisons.append({
                "setup_id": setup_id,
                "symbol": symbol,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "strategy_return": strat_ret,
                "benchmark_return": b_ret,
                "excess_return": excess,
            })

    if not trade_comparisons:
        return {
            "status": "UNAVAILABLE — benchmark data missing",
            "available": False,
            "completed_trades": n_total,
            "benchmark_id": be.benchmark_id,
            "trades_evaluated": 0,
            "total_trades_compared": 0,
            "average_strategy_return": None,
            "average_benchmark_return": None,
            "average_excess_return": None,
            "alpha_pct": None,
            "median_excess_return": None,
            "cumulative_strategy_return": 0.0,
            "cumulative_benchmark_return": 0.0,
            "cumulative_excess_return": 0.0,
            "win_rate_vs_benchmark_pct": 0.0,
            "trade_comparisons": [],
        }

    avg_strat = round(statistics.mean(strat_returns), 2)
    avg_bench = round(statistics.mean(bench_returns), 2)
    avg_excess = round(statistics.mean(excess_returns), 2)
    med_excess = round(statistics.median(excess_returns), 2)
    cum_strat = round(sum(strat_returns), 2)
    cum_bench = round(sum(bench_returns), 2)
    cum_excess = round(sum(excess_returns), 2)
    win_rate = round((len([e for e in excess_returns if e > 0]) / len(excess_returns)) * 100, 2)

    return {
        "status": "ACTIVE",
        "available": True,
        "completed_trades": n_total,
        "benchmark_id": be.benchmark_id,
        "trades_evaluated": len(trade_comparisons),
        "total_trades_compared": len(trade_comparisons),
        "average_strategy_return": avg_strat,
        "average_benchmark_return": avg_bench,
        "average_excess_return": avg_excess,
        "alpha_pct": avg_excess,
        "median_excess_return": med_excess,
        "cumulative_strategy_return": cum_strat,
        "cumulative_benchmark_return": cum_bench,
        "cumulative_excess_return": cum_excess,
        "win_rate_vs_benchmark_pct": win_rate,
        "trade_comparisons": trade_comparisons,
    }
