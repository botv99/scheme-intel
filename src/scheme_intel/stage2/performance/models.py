"""
Data models and constants for Stage 2 Performance Analytics.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Configurable Data-Sufficiency Thresholds
MIN_COMPLETED_TRADES = 30
MIN_ARCHETYPE_SAMPLE = 20
MIN_STOCK_SAMPLE = 20
DEFAULT_SCORE_BANDS: List[Tuple[int, int]] = [(0, 20), (21, 40), (41, 60), (61, 80), (81, 100)]


def _safe_round(val: Optional[float], digits: int = 2) -> Optional[float]:
    if val is None or math.isnan(val):
        return None
    if math.isinf(val):
        return float("inf")
    return round(val, digits)


@dataclass
class SetupMetrics:
    total_setups: int = 0
    qualified_setups: int = 0
    rejected_setups: int = 0
    waiting_setups: int = 0
    watch_setups: int = 0
    triggered_setups: int = 0
    untriggered_setups: int = 0
    active_setups: int = 0
    completed_setups: int = 0
    expired_setups: int = 0


@dataclass
class OutcomeMetrics:
    completed_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    target_hits: int = 0
    stop_hits: int = 0
    expired: int = 0
    win_rate: Optional[float] = None
    loss_rate: Optional[float] = None
    expiry_rate: Optional[float] = None
    target_hit_rate: Optional[float] = None
    stop_hit_rate: Optional[float] = None


@dataclass
class PnLMetrics:
    average_pnl_pct: Optional[float] = None
    median_pnl_pct: Optional[float] = None
    cumulative_pnl_pct: float = 0.0
    average_win_pct: Optional[float] = None
    average_loss_pct: Optional[float] = None
    largest_winner_pct: Optional[float] = None
    largest_loser_pct: Optional[float] = None
    profit_factor: Optional[float] = None
    expectancy: Optional[float] = None
    std_dev_pnl_pct: Optional[float] = None


@dataclass
class ExcursionMetrics:
    average_mfe_pct: Optional[float] = None
    median_mfe_pct: Optional[float] = None
    maximum_mfe_pct: Optional[float] = None
    average_mae_pct: Optional[float] = None
    median_mae_pct: Optional[float] = None
    maximum_adverse_excursion: Optional[float] = None
    mfe_distribution: Dict[str, int] = field(default_factory=dict)
    mae_distribution: Dict[str, int] = field(default_factory=dict)


@dataclass
class HoldingPeriodMetrics:
    overall: Dict[str, Optional[float]] = field(default_factory=dict)
    wins: Dict[str, Optional[float]] = field(default_factory=dict)
    losses: Dict[str, Optional[float]] = field(default_factory=dict)
    expired: Dict[str, Optional[float]] = field(default_factory=dict)


@dataclass
class ArchetypeStats:
    archetype: str
    setups: int = 0
    qualified: int = 0
    triggered: int = 0
    completed: int = 0
    wins: int = 0
    losses: int = 0
    expired: int = 0
    win_rate: Optional[float] = None
    average_pnl_pct: Optional[float] = None
    expectancy: Optional[float] = None
    profit_factor: Optional[float] = None
    average_mfe_pct: Optional[float] = None
    average_mae_pct: Optional[float] = None
    average_holding_period: Optional[float] = None
    sample_status: str = "INSUFFICIENT_SAMPLE"


@dataclass
class SymbolStats:
    symbol: str
    setups: int = 0
    qualified: int = 0
    triggered: int = 0
    completed: int = 0
    wins: int = 0
    losses: int = 0
    expired: int = 0
    win_rate: Optional[float] = None
    average_pnl_pct: Optional[float] = None
    expectancy: Optional[float] = None
    average_mfe_pct: Optional[float] = None
    average_mae_pct: Optional[float] = None
    average_holding_period: Optional[float] = None
    sample_status: str = "INSUFFICIENT_SAMPLE"


@dataclass
class ProviderStats:
    provider: str
    setups: int = 0
    triggered: int = 0
    completed: int = 0
    wins: int = 0
    losses: int = 0
    expired: int = 0
    win_rate: Optional[float] = None
    average_pnl_pct: Optional[float] = None
    expectancy: Optional[float] = None
    average_mfe_pct: Optional[float] = None
    average_mae_pct: Optional[float] = None
    sample_status: str = "INSUFFICIENT_SAMPLE"
    observational_note: str = "Observational analysis only. Does not establish causation."


@dataclass
class ScoreBandStats:
    band_label: str
    min_score: int
    max_score: int
    setups: int = 0
    triggered: int = 0
    completed: int = 0
    wins: int = 0
    losses: int = 0
    average_pnl_pct: Optional[float] = None
    win_rate: Optional[float] = None
    expectancy: Optional[float] = None


@dataclass
class DailySeriesRecord:
    date: str
    setups_generated: int
    qualified_setups: int
    triggered: int
    completed: int
    wins: int
    losses: int
    expired: int
    daily_realized_pnl_pct: float
    cumulative_pnl_pct: float
    average_pnl_pct: Optional[float]


@dataclass
class WalkForwardWindow:
    window_name: str
    sample_size: int
    start_date: str
    end_date: str
    completed_trades: int
    win_rate: Optional[float]
    average_pnl_pct: Optional[float]
    expectancy: Optional[float]
    profit_factor: Optional[float]
    sample_status: str


@dataclass
class OutOfSampleComparison:
    split_date: str
    historical_trades: int
    historical_win_rate: Optional[float]
    historical_avg_pnl: Optional[float]
    historical_expectancy: Optional[float]
    forward_trades: int
    forward_win_rate: Optional[float]
    forward_avg_pnl: Optional[float]
    forward_expectancy: Optional[float]
    forward_status: str


@dataclass
class DataIntegrityReport:
    status: str  # PASS or WARN
    checks_performed: int
    issues_detected: int
    issues: List[str] = field(default_factory=list)


@dataclass
class PerformanceReport:
    generated_at: str
    data_period: Dict[str, str]
    data_sufficiency: Dict[str, Any]
    strategy_status: str  # INSUFFICIENT DATA / PRELIMINARY / VALIDATED
    setup_metrics: SetupMetrics
    outcome_metrics: OutcomeMetrics
    pnl_metrics: PnLMetrics
    excursion_metrics: ExcursionMetrics
    holding_period_metrics: HoldingPeriodMetrics
    archetype_breakdown: List[ArchetypeStats]
    symbol_breakdown: List[SymbolStats]
    provider_breakdown: List[ProviderStats]
    score_band_breakdown: List[ScoreBandStats]
    daily_series: List[DailySeriesRecord]
    walk_forward_windows: List[WalkForwardWindow]
    out_of_sample_comparison: Optional[OutOfSampleComparison]
    benchmark_comparison: Dict[str, Any]
    data_integrity: DataIntegrityReport

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
