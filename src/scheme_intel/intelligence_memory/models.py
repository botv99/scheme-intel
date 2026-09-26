"""
Data contracts for Intelligence Memory and Prebuilt Snapshots.
Supports fast, lookahead-free, and structured retrieval for conversational terminal queries.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SnapshotHealthStatus(str, Enum):
    READY = "READY"
    STALE = "STALE"
    MISSING = "MISSING"
    INVALID = "INVALID"


class CompanyIntelligence(BaseModel):
    """Normalized company-level intelligence card data."""
    symbol: str                                 # e.g., "TRUALT.NS"
    short_symbol: str                           # e.g., "TRUALT"
    name: str                                   # e.g., "TruAlt Bioenergy"
    scheme_id: str                              # e.g., "gobardhan"
    scheme_name: str                            # e.g., "GOBARdhan"
    relevance: str = "High"                     # High, Medium, Low
    mapping_rationale: str = ""
    latest_development: Optional[str] = None
    catalyst: Optional[str] = None
    price: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[int] = None
    avg_volume: Optional[int] = None
    trend: Optional[str] = None
    support: Optional[float] = None
    resistance: Optional[float] = None
    rsi: Optional[float] = None
    status: str = "NO_TRADE"                    # QUALIFIED_SETUP, WAIT, NO_TRADE, DATA_UNAVAILABLE
    archetype: Optional[str] = None
    score: Optional[int] = None
    trigger_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    bull_thesis: Optional[str] = None
    bear_thesis: Optional[str] = None
    risk_summary: Optional[str] = None
    waiting_conditions: List[str] = Field(default_factory=list)
    next_session: Optional[str] = None
    ai_provider: Optional[str] = None
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    updated_at: str = ""


class SchemeIntelligence(BaseModel):
    """Scheme-level overview and watchlist statistics."""
    scheme_id: str
    name: str
    description: str = ""
    watchlist_count: int = 0
    qualified_setups_count: int = 0
    waiting_count: int = 0
    no_trade_count: int = 0
    data_unavailable_count: int = 0
    key_developments: List[str] = Field(default_factory=list)
    important_sources: List[str] = Field(default_factory=list)
    last_update: str = ""


class PerformanceIntelligence(BaseModel):
    """Forward performance validation overview."""
    completed_trades: int = 0
    validation_threshold: int = 30
    validation_status: str = "INSUFFICIENT_SAMPLE"  # INSUFFICIENT_SAMPLE or VALIDATED
    win_rate: Optional[float] = None
    avg_pnl: Optional[float] = None
    profit_factor: Optional[float] = None
    expectancy: Optional[float] = None
    summary_text: str = ""
    audit_status: str = "PASS"


class BenchmarkIntelligence(BaseModel):
    """Relative performance comparison against NIFTY 50."""
    status: str = "UNAVAILABLE — 0 completed trades"
    benchmark_id: str = "NIFTY50"
    completed_trades: int = 0
    trades_evaluated: int = 0
    strategy_return: Optional[float] = None
    benchmark_return: Optional[float] = None
    excess_return: Optional[float] = None
    win_rate_vs_benchmark_pct: Optional[float] = None
    trade_comparisons: List[Dict[str, Any]] = Field(default_factory=list)
    reason: Optional[str] = None


class IntelligenceSnapshot(BaseModel):
    """
    Versioned immutable intelligence snapshot created after daily pipeline execution.
    Acts as the primary retrieval store for the Telegram terminal.
    """
    snapshot_id: str
    schema_version: str = "1.0"
    generated_at: str                            # ISO 8601 UTC
    pipeline_run_id: Optional[str] = None
    scheme_ids: List[str] = Field(default_factory=list)
    schemes: Dict[str, SchemeIntelligence] = Field(default_factory=dict)
    companies: Dict[str, CompanyIntelligence] = Field(default_factory=dict)
    qualified_setups: List[str] = Field(default_factory=list)
    waiting_setups: List[str] = Field(default_factory=list)
    performance: PerformanceIntelligence = Field(default_factory=PerformanceIntelligence)
    benchmark: BenchmarkIntelligence = Field(default_factory=BenchmarkIntelligence)

    def get_age_seconds(self) -> float:
        """Return snapshot age in seconds."""
        try:
            gen_dt = datetime.fromisoformat(self.generated_at.replace("Z", "+00:00"))
            return max(0.0, (datetime.now(timezone.utc) - gen_dt).total_seconds())
        except Exception:
            return 0.0

    def get_age_display(self) -> str:
        """Return human-readable snapshot age, e.g. '2h 14m'."""
        sec = int(self.get_age_seconds())
        hours = sec // 3600
        minutes = (sec % 3600) // 60
        if hours > 0:
            return f"{hours}h {minutes:02d}m"
        return f"{minutes}m"

    def is_stale(self, max_age_hours: float = 26.0, threshold_hours: Optional[float] = None) -> bool:
        """Return True if the snapshot is older than max_age_hours."""
        if threshold_hours is not None:
            max_age_hours = threshold_hours
        return (self.get_age_seconds() / 3600.0) > max_age_hours

    def get_health_status(self, max_age_hours: float = 26.0) -> SnapshotHealthStatus:
        """Determine health status: READY or STALE."""
        if self.is_stale(max_age_hours=max_age_hours):
            return SnapshotHealthStatus.STALE
        return SnapshotHealthStatus.READY
