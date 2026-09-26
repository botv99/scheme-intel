"""
Forward Performance Analytics Module.
Calculates performance metrics, walk-forward validation, and reports.
"""
from __future__ import annotations

from ..stage2.performance import (
    PerformanceAnalytics,
    PerformanceReport,
    SetupMetrics,
    OutcomeMetrics,
    PnLMetrics,
    ExcursionMetrics,
    HoldingPeriodMetrics,
    ArchetypeStats,
    SymbolStats,
    ProviderStats,
    ScoreBandStats,
    DailySeriesRecord,
    WalkForwardWindow,
    OutOfSampleComparison,
    DataIntegrityReport,
    MIN_COMPLETED_TRADES,
    MIN_ARCHETYPE_SAMPLE,
    MIN_STOCK_SAMPLE,
)

__all__ = [
    "PerformanceAnalytics",
    "PerformanceReport",
    "SetupMetrics",
    "OutcomeMetrics",
    "PnLMetrics",
    "ExcursionMetrics",
    "HoldingPeriodMetrics",
    "ArchetypeStats",
    "SymbolStats",
    "ProviderStats",
    "ScoreBandStats",
    "DailySeriesRecord",
    "WalkForwardWindow",
    "OutOfSampleComparison",
    "DataIntegrityReport",
    "MIN_COMPLETED_TRADES",
    "MIN_ARCHETYPE_SAMPLE",
    "MIN_STOCK_SAMPLE",
]
