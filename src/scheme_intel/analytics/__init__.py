"""
Analytics Subsystem.
Houses forward performance analytics, NIFTY 50 benchmark evaluations, and reporting.
"""
from .stage1 import Analytics, TradeSummary
from .benchmark import evaluate_benchmark_performance
from .performance import (
    PerformanceAnalytics,
    PerformanceReport,
    MIN_COMPLETED_TRADES,
    MIN_ARCHETYPE_SAMPLE,
    MIN_STOCK_SAMPLE,
)

__all__ = [
    "Analytics",
    "TradeSummary",
    "evaluate_benchmark_performance",
    "PerformanceAnalytics",
    "PerformanceReport",
    "MIN_COMPLETED_TRADES",
    "MIN_ARCHETYPE_SAMPLE",
    "MIN_STOCK_SAMPLE",
]
