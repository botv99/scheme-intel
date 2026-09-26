"""
Intelligence Memory Subsystem.
Houses fast in-memory snapshots, intent resolution, and structured retrieval.
"""
from .models import (
    CompanyIntelligence,
    SchemeIntelligence,
    PerformanceIntelligence,
    BenchmarkIntelligence,
    IntelligenceSnapshot,
    SnapshotHealthStatus,
)
from .store import IntelligenceStore, DEFAULT_SNAPSHOT_PATH
from .builder import IntelligenceSnapshotBuilder
from .resolver import IntentResolver, IntentType, ResolvedIntent
from .retrieval import FastIntelligenceRetriever, IntelligenceRetrieval
from .cards import (
    render_stock_card,
    render_why_card,
    render_what_card,
    render_when_card,
    render_scheme_card,
    render_setups_card,
    render_waiting_card,
    render_performance_card,
    render_benchmark_card,
    render_schemes_list_card,
    render_help_card,
    render_unknown_stock,
    render_unknown_scheme,
    render_snapshot_unavailable,
    render_snapshot_missing,
    render_snapshot_invalid,
    render_health_card,
)

__all__ = [
    "CompanyIntelligence",
    "SchemeIntelligence",
    "PerformanceIntelligence",
    "BenchmarkIntelligence",
    "IntelligenceSnapshot",
    "SnapshotHealthStatus",
    "IntelligenceStore",
    "DEFAULT_SNAPSHOT_PATH",
    "IntelligenceSnapshotBuilder",
    "IntentResolver",
    "IntentType",
    "ResolvedIntent",
    "FastIntelligenceRetriever",
    "IntelligenceRetrieval",
    "render_stock_card",
    "render_why_card",
    "render_what_card",
    "render_when_card",
    "render_scheme_card",
    "render_setups_card",
    "render_waiting_card",
    "render_performance_card",
    "render_benchmark_card",
    "render_schemes_list_card",
    "render_help_card",
    "render_unknown_stock",
    "render_unknown_scheme",
    "render_snapshot_unavailable",
    "render_snapshot_missing",
    "render_snapshot_invalid",
    "render_health_card",
]
