"""
PerformanceAnalytics coordination engine for Stage 2.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models import SetupOutcome, TradeSetup
from ..storage import Stage2Database
from ...logger import get_logger
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
)
from .reports import generate_reports, get_telegram_summary, render_markdown
from .validation import (
    check_data_integrity,
    compute_out_of_sample_comparison,
    compute_walk_forward_validation,
)

logger = get_logger(__name__)


class PerformanceAnalytics:
    """
    Authoritative forward performance calculation and validation engine for Stage 2.
    Reads from stage2_setups and stage2_outcomes in SQLite and computes unbiased metrics.
    """

    def __init__(
        self,
        db: Stage2Database,
        min_completed_trades: int = MIN_COMPLETED_TRADES,
        min_archetype_sample: int = MIN_ARCHETYPE_SAMPLE,
        min_stock_sample: int = MIN_STOCK_SAMPLE,
        score_bands: Optional[List[Tuple[int, int]]] = None,
    ):
        self.db = db
        self.min_completed_trades = min_completed_trades
        self.min_archetype_sample = min_archetype_sample
        self.min_stock_sample = min_stock_sample
        self.score_bands = score_bands or DEFAULT_SCORE_BANDS

    def calculate(self) -> PerformanceReport:
        """
        Execute full analytics pass:
        1. Fetch all setups and outcomes
        2. Perform comprehensive data integrity audit
        3. Compute setup & outcome metrics
        4. Compute return, P&L, MFE/MAE, and holding period metrics
        5. Build breakdowns by archetype, stock, provider, and score bands
        6. Compute daily time series
        7. Execute walk-forward and out-of-sample validation without leakage
        8. Evaluate baseline benchmark
        9. Assemble PerformanceReport
        """
        setups = self.db.list_setups()
        outcomes = self.db.list_outcomes()

        # Map outcomes by setup_id for O(1) joins
        outcome_map: Dict[str, SetupOutcome] = {o.setup_id: o for o in outcomes}
        setup_map: Dict[str, TradeSetup] = {s.setup_id: s for s in setups}

        # 1. Data Integrity Checks
        integrity = self._check_data_integrity(setups, outcomes, setup_map, outcome_map)

        # 2. Setup Lifecycle Metrics
        setup_metrics = self._compute_setup_metrics(setups, outcome_map)

        # 3. Filter completed trades for PnL & outcome metrics
        completed_trades_data: List[Tuple[TradeSetup, SetupOutcome]] = []
        for s in setups:
            o = outcome_map.get(s.setup_id)
            if o and o.entry_triggered and (o.target_hit or o.stop_hit or o.expired):
                completed_trades_data.append((s, o))

        outcome_metrics = self._compute_outcome_metrics(completed_trades_data)
        pnl_metrics = self._compute_pnl_metrics(completed_trades_data, outcome_metrics.win_rate, outcome_metrics.loss_rate)

        # 4. MFE / MAE Excursion Metrics (all triggered trades, active + completed)
        triggered_outcomes = [o for o in outcomes if o.entry_triggered]
        excursion_metrics = self._compute_excursion_metrics(triggered_outcomes)

        # 5. Holding Period Metrics
        holding_metrics = self._compute_holding_metrics(completed_trades_data)

        # 6. Breakdowns
        archetype_stats = self._compute_archetype_breakdown(setups, outcome_map)
        symbol_stats = self._compute_symbol_breakdown(setups, outcome_map)
        provider_stats = self._compute_provider_breakdown(setups, outcome_map)
        score_band_stats = self._compute_score_band_breakdown(setups, outcome_map)

        # 7. Chronological Daily Series
        daily_series = self._compute_daily_series(setups, outcome_map)

        # 8. Walk-Forward and Out-of-Sample Validation
        wf_windows = self._compute_walk_forward_validation(setups, outcome_map)
        oos_comparison = self._compute_out_of_sample_comparison(setups, outcome_map)

        # 9. Benchmark Baseline Comparison
        benchmark = self._compute_benchmark_comparison(completed_trades_data)

        # 10. Period & Data Sufficiency
        dates = [s.setup_date for s in setups if s.setup_date]
        data_period = {
            "start_date": min(dates) if dates else "N/A",
            "end_date": max(dates) if dates else "N/A",
        }

        n_completed = outcome_metrics.completed_trades
        if n_completed < 10:
            suff_status = "INSUFFICIENT_SAMPLE"
            strategy_status = "INSUFFICIENT DATA"
            suff_label = f"Insufficient sample ({n_completed} completed trades; minimum {self.min_completed_trades} required for statistical validity)"
        elif n_completed < self.min_completed_trades:
            suff_status = "PRELIMINARY"
            strategy_status = "PRELIMINARY"
            suff_label = f"Preliminary observations ({n_completed}/{self.min_completed_trades} completed trades; ongoing sample collection)"
        else:
            suff_status = "VALIDATED_SAMPLE"
            strategy_status = "VALIDATED"
            suff_label = f"Validated sample ({n_completed} completed trades meet sample-size thresholds)"

        data_sufficiency = {
            "status": suff_status,
            "completed_trades": n_completed,
            "min_required": self.min_completed_trades,
            "label": suff_label,
        }

        return PerformanceReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            data_period=data_period,
            data_sufficiency=data_sufficiency,
            strategy_status=strategy_status,
            setup_metrics=setup_metrics,
            outcome_metrics=outcome_metrics,
            pnl_metrics=pnl_metrics,
            excursion_metrics=excursion_metrics,
            holding_period_metrics=holding_metrics,
            archetype_breakdown=archetype_stats,
            symbol_breakdown=symbol_stats,
            provider_breakdown=provider_stats,
            score_band_breakdown=score_band_stats,
            daily_series=daily_series,
            walk_forward_windows=wf_windows,
            out_of_sample_comparison=oos_comparison,
            benchmark_comparison=benchmark,
            data_integrity=integrity,
        )

    # -------------------------------------------------------------------------
    # Backward-Compatible Helper Delegation
    # -------------------------------------------------------------------------

    def _compute_setup_metrics(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> SetupMetrics:
        return compute_setup_metrics(setups, outcome_map)

    def _compute_outcome_metrics(
        self,
        completed_data: List[Tuple[TradeSetup, SetupOutcome]],
    ) -> OutcomeMetrics:
        return compute_outcome_metrics(completed_data)

    def _compute_pnl_metrics(
        self,
        completed_data: List[Tuple[TradeSetup, SetupOutcome]],
        win_rate_pct: Optional[float],
        loss_rate_pct: Optional[float],
    ) -> PnLMetrics:
        return compute_pnl_metrics(completed_data, win_rate_pct, loss_rate_pct)

    def _compute_excursion_metrics(
        self,
        triggered_outcomes: List[SetupOutcome],
    ) -> ExcursionMetrics:
        return compute_excursion_metrics(triggered_outcomes)

    def _compute_holding_metrics(
        self,
        completed_data: List[Tuple[TradeSetup, SetupOutcome]],
    ) -> HoldingPeriodMetrics:
        return compute_holding_metrics(completed_data)

    def _compute_archetype_breakdown(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> List[ArchetypeStats]:
        return compute_archetype_breakdown(setups, outcome_map, self.min_archetype_sample)

    def _compute_symbol_breakdown(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> List[SymbolStats]:
        return compute_symbol_breakdown(setups, outcome_map, self.min_stock_sample)

    def _compute_provider_breakdown(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> List[ProviderStats]:
        return compute_provider_breakdown(setups, outcome_map, self.min_completed_trades)

    def _compute_score_band_breakdown(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> List[ScoreBandStats]:
        return compute_score_band_breakdown(setups, outcome_map, self.score_bands)

    def _compute_daily_series(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> List[DailySeriesRecord]:
        return compute_daily_series(setups, outcome_map)

    def _compute_walk_forward_validation(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> List[WalkForwardWindow]:
        return compute_walk_forward_validation(setups, outcome_map)

    def _compute_out_of_sample_comparison(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> Optional[OutOfSampleComparison]:
        return compute_out_of_sample_comparison(setups, outcome_map, self.min_completed_trades)

    def _compute_benchmark_comparison(
        self,
        completed_data: List[Tuple[TradeSetup, SetupOutcome]],
    ) -> Dict[str, Any]:
        return compute_benchmark_comparison(completed_data, self.db.db_path)

    def _check_data_integrity(
        self,
        setups: List[TradeSetup],
        outcomes: List[SetupOutcome],
        setup_map: Dict[str, TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> DataIntegrityReport:
        return check_data_integrity(setups, outcomes, setup_map, outcome_map)

    # -------------------------------------------------------------------------
    # Report Generation: JSON, Markdown, Telegram
    # -------------------------------------------------------------------------

    def generate_reports(self, output_dir: Path | str = "data/performance") -> Tuple[Path, Path, PerformanceReport]:
        report = self.calculate()
        return generate_reports(report, output_dir)

    def render_markdown(self, report: PerformanceReport) -> str:
        return render_markdown(report)

    def get_telegram_summary(self, report: Optional[PerformanceReport] = None) -> str:
        rep = report or self.calculate()
        return get_telegram_summary(rep, self.min_completed_trades)
