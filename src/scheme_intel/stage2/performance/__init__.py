"""
Forward Performance Analytics and Validation Engine for Scheme-Intel Stage 2.
Modularized into submodules:
- models: Data classes, structures, and sufficiency constants
- metrics: Statistical P&L, excursion, holding period, and breakdown computations
- validation: Zero-lookahead walk-forward and out-of-sample validation and integrity checks
- reports: Markdown, JSON, and Telegram reporting formatters
- engine: PerformanceAnalytics coordinator
"""
from __future__ import annotations

from .engine import PerformanceAnalytics
from .metrics import (
    compute_archetype_breakdown,
    compute_benchmark_comparison,
    compute_daily_series,
    compute_excursion_metrics,
    compute_holding_metrics,
    compute_outcome_metrics,
    compute_pnl_metrics,
    compute_provider_breakdown,
    compute_score_band_breakdown,
    compute_setup_metrics,
    compute_symbol_breakdown,
)
from .models import (
    DEFAULT_SCORE_BANDS,
    MIN_ARCHETYPE_SAMPLE,
    MIN_COMPLETED_TRADES,
    MIN_STOCK_SAMPLE,
    ArchetypeStats,
    DailySeriesRecord,
    DataIntegrityReport,
    ExcursionMetrics,
    HoldingPeriodMetrics,
    OutcomeMetrics,
    OutOfSampleComparison,
    PerformanceReport,
    PnLMetrics,
    ProviderStats,
    ScoreBandStats,
    SetupMetrics,
    SymbolStats,
    WalkForwardWindow,
    _safe_round,
)
from .reports import generate_reports, get_telegram_summary, render_markdown
from .validation import (
    check_data_integrity,
    compute_out_of_sample_comparison,
    compute_walk_forward_validation,
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
    "DEFAULT_SCORE_BANDS",
    "_safe_round",
    "compute_setup_metrics",
    "compute_outcome_metrics",
    "compute_pnl_metrics",
    "compute_excursion_metrics",
    "compute_holding_metrics",
    "compute_archetype_breakdown",
    "compute_symbol_breakdown",
    "compute_provider_breakdown",
    "compute_score_band_breakdown",
    "compute_daily_series",
    "compute_benchmark_comparison",
    "compute_walk_forward_validation",
    "compute_out_of_sample_comparison",
    "check_data_integrity",
    "render_markdown",
    "get_telegram_summary",
    "generate_reports",
]
