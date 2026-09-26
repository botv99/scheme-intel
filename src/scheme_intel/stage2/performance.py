"""
Forward Performance Analytics and Validation Engine for Scheme-Intel Stage 2.

Evaluates historical and forward performance of trade setups and executed outcomes:
- Setup lifecycle statistics (All, Qualified, Waiting, Triggered, Completed)
- Return and P&L metrics with formal mathematical definitions
- Maximum Favorable Excursion (MFE) and Maximum Adverse Excursion (MAE) analytics
- Holding period distributions broken down by outcome
- Breakdowns by Archetype, Stock, AI Provider, and Candidate Score Bands
- Chronological Daily Time-Series
- Walk-Forward Validation without future outcome data leakage
- Data-Sufficiency Guards preventing premature statistical claims
- Out-of-Sample vs Historical evaluation
- Benchmark baseline comparison
- Data integrity and sanity checks
- Generation of machine-readable (JSON) and human-readable (Markdown) reports
- Compact Telegram summary generation
"""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import SetupOutcome, TradeSetup
from .storage import Stage2Database
from ..logger import get_logger

logger = get_logger(__name__)

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
    # Internal Calculation Helpers
    # -------------------------------------------------------------------------

    def _compute_setup_metrics(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> SetupMetrics:
        total = len(setups)
        qualified = sum(1 for s in setups if s.status == "QUALIFIED_SETUP")
        rejected = sum(1 for s in setups if s.status == "NO_TRADE")
        waiting = sum(1 for s in setups if s.status == "WAIT")
        watch = sum(1 for s in setups if s.status == "WATCH")

        triggered = 0
        active = 0
        completed = 0
        expired = 0

        for s in setups:
            o = outcome_map.get(s.setup_id)
            if o and o.entry_triggered:
                triggered += 1
                if o.target_hit or o.stop_hit or o.expired:
                    completed += 1
                    if o.expired:
                        expired += 1
                else:
                    active += 1

        untriggered = total - triggered

        return SetupMetrics(
            total_setups=total,
            qualified_setups=qualified,
            rejected_setups=rejected,
            waiting_setups=waiting,
            watch_setups=watch,
            triggered_setups=triggered,
            untriggered_setups=untriggered,
            active_setups=active,
            completed_setups=completed,
            expired_setups=expired,
        )

    def _compute_outcome_metrics(
        self,
        completed_data: List[Tuple[TradeSetup, SetupOutcome]],
    ) -> OutcomeMetrics:
        n = len(completed_data)
        if n == 0:
            return OutcomeMetrics()

        wins = 0
        losses = 0
        breakeven = 0
        target_hits = 0
        stop_hits = 0
        expired = 0

        for _, o in completed_data:
            pnl = o.realized_pnl_pct or 0.0
            if pnl > 0.0 or (o.target_hit and pnl >= 0.0):
                wins += 1
            elif pnl < 0.0 or (o.stop_hit and pnl <= 0.0):
                losses += 1
            else:
                breakeven += 1

            if o.target_hit:
                target_hits += 1
            if o.stop_hit:
                stop_hits += 1
            if o.expired:
                expired += 1

        return OutcomeMetrics(
            completed_trades=n,
            wins=wins,
            losses=losses,
            breakeven=breakeven,
            target_hits=target_hits,
            stop_hits=stop_hits,
            expired=expired,
            win_rate=_safe_round((wins / n) * 100.0, 1),
            loss_rate=_safe_round((losses / n) * 100.0, 1),
            expiry_rate=_safe_round((expired / n) * 100.0, 1),
            target_hit_rate=_safe_round((target_hits / n) * 100.0, 1),
            stop_hit_rate=_safe_round((stop_hits / n) * 100.0, 1),
        )

    def _compute_pnl_metrics(
        self,
        completed_data: List[Tuple[TradeSetup, SetupOutcome]],
        win_rate_pct: Optional[float],
        loss_rate_pct: Optional[float],
    ) -> PnLMetrics:
        if not completed_data:
            return PnLMetrics()

        pnls: List[float] = [o.realized_pnl_pct for _, o in completed_data if o.realized_pnl_pct is not None]
        if not pnls:
            return PnLMetrics()

        n = len(pnls)
        avg_pnl = sum(pnls) / n
        med_pnl = statistics.median(pnls)
        cum_pnl = sum(pnls)

        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p < 0]

        avg_win = (sum(winners) / len(winners)) if winners else None
        avg_loss = (sum(losers) / len(losers)) if losers else None

        largest_win = max(pnls) if pnls else None
        largest_loss = min(pnls) if pnls else None

        # Profit Factor = gross profits / absolute gross losses
        gross_profits = sum(winners)
        gross_losses = abs(sum(losers))
        if gross_losses > 0:
            profit_factor = gross_profits / gross_losses
        elif gross_profits > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        # Expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)
        # Note: avg_loss is negative, so adding loss_rate * avg_loss subtracts the loss
        if avg_win is not None and avg_loss is not None and win_rate_pct is not None and loss_rate_pct is not None:
            w_dec = win_rate_pct / 100.0
            l_dec = loss_rate_pct / 100.0
            expectancy = (w_dec * avg_win) + (l_dec * avg_loss)
        elif avg_win is not None and win_rate_pct == 100.0:
            expectancy = avg_win
        elif avg_loss is not None and loss_rate_pct == 100.0:
            expectancy = avg_loss
        else:
            expectancy = None

        std_dev = statistics.stdev(pnls) if len(pnls) >= 2 else 0.0

        return PnLMetrics(
            average_pnl_pct=_safe_round(avg_pnl),
            median_pnl_pct=_safe_round(med_pnl),
            cumulative_pnl_pct=_safe_round(cum_pnl) or 0.0,
            average_win_pct=_safe_round(avg_win),
            average_loss_pct=_safe_round(avg_loss),
            largest_winner_pct=_safe_round(largest_win),
            largest_loser_pct=_safe_round(largest_loss),
            profit_factor=_safe_round(profit_factor),
            expectancy=_safe_round(expectancy),
            std_dev_pnl_pct=_safe_round(std_dev),
        )

    def _compute_excursion_metrics(
        self,
        triggered_outcomes: List[SetupOutcome],
    ) -> ExcursionMetrics:
        if not triggered_outcomes:
            return ExcursionMetrics(
                mfe_distribution={"<0%": 0, "0–2%": 0, "2–5%": 0, "5–10%": 0, ">10%": 0},
                mae_distribution={"0 to -1%": 0, "-1 to -3%": 0, "-3 to -5%": 0, "<-5%": 0},
            )

        mfes = [o.mfe_pct for o in triggered_outcomes if o.mfe_pct is not None]
        maes = [o.mae_pct for o in triggered_outcomes if o.mae_pct is not None]

        avg_mfe = statistics.mean(mfes) if mfes else None
        med_mfe = statistics.median(mfes) if mfes else None
        max_mfe = max(mfes) if mfes else None

        avg_mae = statistics.mean(maes) if maes else None
        med_mae = statistics.median(maes) if maes else None
        max_ae = min(maes) if maes else None  # worst adverse movement

        # Distributions
        mfe_dist = {"<0%": 0, "0–2%": 0, "2–5%": 0, "5–10%": 0, ">10%": 0}
        for m in mfes:
            if m < 0:
                mfe_dist["<0%"] += 1
            elif m <= 2.0:
                mfe_dist["0–2%"] += 1
            elif m <= 5.0:
                mfe_dist["2–5%"] += 1
            elif m <= 10.0:
                mfe_dist["5–10%"] += 1
            else:
                mfe_dist[">10%"] += 1

        mae_dist = {"0 to -1%": 0, "-1 to -3%": 0, "-3 to -5%": 0, "<-5%": 0}
        for a in maes:
            if a >= -1.0:
                mae_dist["0 to -1%"] += 1
            elif a >= -3.0:
                mae_dist["-1 to -3%"] += 1
            elif a >= -5.0:
                mae_dist["-3 to -5%"] += 1
            else:
                mae_dist["<-5%"] += 1

        return ExcursionMetrics(
            average_mfe_pct=_safe_round(avg_mfe),
            median_mfe_pct=_safe_round(med_mfe),
            maximum_mfe_pct=_safe_round(max_mfe),
            average_mae_pct=_safe_round(avg_mae),
            median_mae_pct=_safe_round(med_mae),
            maximum_adverse_excursion=_safe_round(max_ae),
            mfe_distribution=mfe_dist,
            mae_distribution=mae_dist,
        )

    def _compute_holding_metrics(
        self,
        completed_data: List[Tuple[TradeSetup, SetupOutcome]],
    ) -> HoldingPeriodMetrics:
        def stats_dict(h_list: List[int]) -> Dict[str, Optional[float]]:
            if not h_list:
                return {"average": None, "median": None, "min": None, "max": None}
            return {
                "average": _safe_round(statistics.mean(h_list), 1),
                "median": _safe_round(statistics.median(h_list), 1),
                "min": _safe_round(float(min(h_list)), 1),
                "max": _safe_round(float(max(h_list)), 1),
            }

        all_hp = [o.holding_period_days for _, o in completed_data if o.holding_period_days is not None]
        win_hp = [o.holding_period_days for _, o in completed_data if o.realized_pnl_pct is not None and o.realized_pnl_pct > 0]
        loss_hp = [o.holding_period_days for _, o in completed_data if o.realized_pnl_pct is not None and o.realized_pnl_pct < 0]
        exp_hp = [o.holding_period_days for _, o in completed_data if o.expired]

        return HoldingPeriodMetrics(
            overall=stats_dict(all_hp),
            wins=stats_dict(win_hp),
            losses=stats_dict(loss_hp),
            expired=stats_dict(exp_hp),
        )

    def _compute_archetype_breakdown(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> List[ArchetypeStats]:
        groups: Dict[str, List[Tuple[TradeSetup, Optional[SetupOutcome]]]] = {}
        for s in setups:
            arch = s.candidate.archetype if s.candidate and s.candidate.archetype else "Unspecified"
            groups.setdefault(arch, []).append((s, outcome_map.get(s.setup_id)))

        results: List[ArchetypeStats] = []
        for arch, pairs in sorted(groups.items()):
            n_setups = len(pairs)
            n_qual = sum(1 for s, _ in pairs if s.status == "QUALIFIED_SETUP")
            triggered_outcomes = [o for _, o in pairs if o and o.entry_triggered]
            completed_outcomes = [o for o in triggered_outcomes if o.target_hit or o.stop_hit or o.expired]

            n_trig = len(triggered_outcomes)
            n_comp = len(completed_outcomes)
            wins = sum(1 for o in completed_outcomes if (o.realized_pnl_pct or 0) > 0 or o.target_hit)
            losses = sum(1 for o in completed_outcomes if (o.realized_pnl_pct or 0) < 0 or o.stop_hit)
            expired = sum(1 for o in completed_outcomes if o.expired)

            win_rate = (wins / n_comp * 100.0) if n_comp > 0 else None
            pnls = [o.realized_pnl_pct for o in completed_outcomes if o.realized_pnl_pct is not None]
            avg_pnl = (sum(pnls) / len(pnls)) if pnls else None

            # Expectancy & Profit Factor
            win_pnls = [p for p in pnls if p > 0]
            loss_pnls = [p for p in pnls if p < 0]
            avg_win = (sum(win_pnls) / len(win_pnls)) if win_pnls else None
            avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else None

            if win_rate is not None and avg_win is not None and avg_loss is not None:
                exp = ((win_rate / 100.0) * avg_win) + (((100.0 - win_rate) / 100.0) * avg_loss)
            elif avg_pnl is not None and n_comp > 0:
                exp = avg_pnl
            else:
                exp = None

            gross_win = sum(win_pnls)
            gross_loss = abs(sum(loss_pnls))
            if gross_loss > 0:
                pf = gross_win / gross_loss
            elif gross_win > 0:
                pf = float("inf")
            else:
                pf = None

            mfes = [o.mfe_pct for o in triggered_outcomes if o.mfe_pct is not None]
            maes = [o.mae_pct for o in triggered_outcomes if o.mae_pct is not None]
            hps = [o.holding_period_days for o in completed_outcomes if o.holding_period_days is not None]

            sample_status = "VALIDATED_SAMPLE" if n_comp >= self.min_archetype_sample else "INSUFFICIENT_SAMPLE"

            results.append(ArchetypeStats(
                archetype=arch,
                setups=n_setups,
                qualified=n_qual,
                triggered=n_trig,
                completed=n_comp,
                wins=wins,
                losses=losses,
                expired=expired,
                win_rate=_safe_round(win_rate, 1),
                average_pnl_pct=_safe_round(avg_pnl),
                expectancy=_safe_round(exp),
                profit_factor=_safe_round(pf),
                average_mfe_pct=_safe_round(statistics.mean(mfes)) if mfes else None,
                average_mae_pct=_safe_round(statistics.mean(maes)) if maes else None,
                average_holding_period=_safe_round(statistics.mean(hps), 1) if hps else None,
                sample_status=sample_status,
            ))

        return results

    def _compute_symbol_breakdown(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> List[SymbolStats]:
        groups: Dict[str, List[Tuple[TradeSetup, Optional[SetupOutcome]]]] = {}
        for s in setups:
            sym = s.stock.symbol
            groups.setdefault(sym, []).append((s, outcome_map.get(s.setup_id)))

        results: List[SymbolStats] = []
        for sym, pairs in sorted(groups.items()):
            n_setups = len(pairs)
            n_qual = sum(1 for s, _ in pairs if s.status == "QUALIFIED_SETUP")
            triggered_outcomes = [o for _, o in pairs if o and o.entry_triggered]
            completed_outcomes = [o for o in triggered_outcomes if o.target_hit or o.stop_hit or o.expired]

            n_trig = len(triggered_outcomes)
            n_comp = len(completed_outcomes)
            wins = sum(1 for o in completed_outcomes if (o.realized_pnl_pct or 0) > 0 or o.target_hit)
            losses = sum(1 for o in completed_outcomes if (o.realized_pnl_pct or 0) < 0 or o.stop_hit)
            expired = sum(1 for o in completed_outcomes if o.expired)

            win_rate = (wins / n_comp * 100.0) if n_comp > 0 else None
            pnls = [o.realized_pnl_pct for o in completed_outcomes if o.realized_pnl_pct is not None]
            avg_pnl = (sum(pnls) / len(pnls)) if pnls else None

            win_pnls = [p for p in pnls if p > 0]
            loss_pnls = [p for p in pnls if p < 0]
            avg_win = (sum(win_pnls) / len(win_pnls)) if win_pnls else None
            avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else None

            if win_rate is not None and avg_win is not None and avg_loss is not None:
                exp = ((win_rate / 100.0) * avg_win) + (((100.0 - win_rate) / 100.0) * avg_loss)
            elif avg_pnl is not None and n_comp > 0:
                exp = avg_pnl
            else:
                exp = None

            mfes = [o.mfe_pct for o in triggered_outcomes if o.mfe_pct is not None]
            maes = [o.mae_pct for o in triggered_outcomes if o.mae_pct is not None]
            hps = [o.holding_period_days for o in completed_outcomes if o.holding_period_days is not None]

            sample_status = "VALIDATED_SAMPLE" if n_comp >= self.min_stock_sample else "INSUFFICIENT_SAMPLE"

            results.append(SymbolStats(
                symbol=sym,
                setups=n_setups,
                qualified=n_qual,
                triggered=n_trig,
                completed=n_comp,
                wins=wins,
                losses=losses,
                expired=expired,
                win_rate=_safe_round(win_rate, 1),
                average_pnl_pct=_safe_round(avg_pnl),
                expectancy=_safe_round(exp),
                average_mfe_pct=_safe_round(statistics.mean(mfes)) if mfes else None,
                average_mae_pct=_safe_round(statistics.mean(maes)) if maes else None,
                average_holding_period=_safe_round(statistics.mean(hps), 1) if hps else None,
                sample_status=sample_status,
            ))

        return results

    def _compute_provider_breakdown(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> List[ProviderStats]:
        groups: Dict[str, List[Tuple[TradeSetup, Optional[SetupOutcome]]]] = {}
        for s in setups:
            prov = s.ai_provider or (s.debate.provider if s.debate else None) or "Deterministic Fallback"
            groups.setdefault(prov, []).append((s, outcome_map.get(s.setup_id)))

        results: List[ProviderStats] = []
        for prov, pairs in sorted(groups.items()):
            n_setups = len(pairs)
            triggered_outcomes = [o for _, o in pairs if o and o.entry_triggered]
            completed_outcomes = [o for o in triggered_outcomes if o.target_hit or o.stop_hit or o.expired]

            n_trig = len(triggered_outcomes)
            n_comp = len(completed_outcomes)
            wins = sum(1 for o in completed_outcomes if (o.realized_pnl_pct or 0) > 0 or o.target_hit)
            losses = sum(1 for o in completed_outcomes if (o.realized_pnl_pct or 0) < 0 or o.stop_hit)
            expired = sum(1 for o in completed_outcomes if o.expired)

            win_rate = (wins / n_comp * 100.0) if n_comp > 0 else None
            pnls = [o.realized_pnl_pct for o in completed_outcomes if o.realized_pnl_pct is not None]
            avg_pnl = (sum(pnls) / len(pnls)) if pnls else None

            win_pnls = [p for p in pnls if p > 0]
            loss_pnls = [p for p in pnls if p < 0]
            avg_win = (sum(win_pnls) / len(win_pnls)) if win_pnls else None
            avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else None

            if win_rate is not None and avg_win is not None and avg_loss is not None:
                exp = ((win_rate / 100.0) * avg_win) + (((100.0 - win_rate) / 100.0) * avg_loss)
            elif avg_pnl is not None and n_comp > 0:
                exp = avg_pnl
            else:
                exp = None

            mfes = [o.mfe_pct for o in triggered_outcomes if o.mfe_pct is not None]
            maes = [o.mae_pct for o in triggered_outcomes if o.mae_pct is not None]

            sample_status = "VALIDATED_SAMPLE" if n_comp >= self.min_completed_trades else "INSUFFICIENT_SAMPLE"

            results.append(ProviderStats(
                provider=prov,
                setups=n_setups,
                triggered=n_trig,
                completed=n_comp,
                wins=wins,
                losses=losses,
                expired=expired,
                win_rate=_safe_round(win_rate, 1),
                average_pnl_pct=_safe_round(avg_pnl),
                expectancy=_safe_round(exp),
                average_mfe_pct=_safe_round(statistics.mean(mfes)) if mfes else None,
                average_mae_pct=_safe_round(statistics.mean(maes)) if maes else None,
                sample_status=sample_status,
            ))

        return results

    def _compute_score_band_breakdown(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> List[ScoreBandStats]:
        results: List[ScoreBandStats] = []
        for low, high in self.score_bands:
            band_label = f"{low}–{high}"
            band_setups = [
                s for s in setups
                if s.candidate and s.candidate.score is not None and low <= s.candidate.score <= high
            ]

            n_setups = len(band_setups)
            triggered = [outcome_map[s.setup_id] for s in band_setups if s.setup_id in outcome_map and outcome_map[s.setup_id].entry_triggered]
            completed = [o for o in triggered if o.target_hit or o.stop_hit or o.expired]

            wins = sum(1 for o in completed if (o.realized_pnl_pct or 0) > 0 or o.target_hit)
            losses = sum(1 for o in completed if (o.realized_pnl_pct or 0) < 0 or o.stop_hit)

            n_comp = len(completed)
            win_rate = (wins / n_comp * 100.0) if n_comp > 0 else None
            pnls = [o.realized_pnl_pct for o in completed if o.realized_pnl_pct is not None]
            avg_pnl = (sum(pnls) / len(pnls)) if pnls else None

            win_pnls = [p for p in pnls if p > 0]
            loss_pnls = [p for p in pnls if p < 0]
            avg_win = (sum(win_pnls) / len(win_pnls)) if win_pnls else None
            avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else None

            if win_rate is not None and avg_win is not None and avg_loss is not None:
                exp = ((win_rate / 100.0) * avg_win) + (((100.0 - win_rate) / 100.0) * avg_loss)
            elif avg_pnl is not None and n_comp > 0:
                exp = avg_pnl
            else:
                exp = None

            results.append(ScoreBandStats(
                band_label=band_label,
                min_score=low,
                max_score=high,
                setups=n_setups,
                triggered=len(triggered),
                completed=n_comp,
                wins=wins,
                losses=losses,
                average_pnl_pct=_safe_round(avg_pnl),
                win_rate=_safe_round(win_rate, 1),
                expectancy=_safe_round(exp),
            ))

        return results

    def _compute_daily_series(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> List[DailySeriesRecord]:
        daily_groups: Dict[str, List[TradeSetup]] = {}
        for s in setups:
            d = s.setup_date or s.analysis_date or "Unknown"
            daily_groups.setdefault(d, []).append(s)

        series: List[DailySeriesRecord] = []
        cum_pnl = 0.0

        for d in sorted(daily_groups.keys()):
            day_setups = daily_groups[d]
            n_gen = len(day_setups)
            n_qual = sum(1 for s in day_setups if s.status == "QUALIFIED_SETUP")

            day_outcomes = [outcome_map[s.setup_id] for s in day_setups if s.setup_id in outcome_map]
            trig = sum(1 for o in day_outcomes if o.entry_triggered)
            comp = [o for o in day_outcomes if o.entry_triggered and (o.target_hit or o.stop_hit or o.expired)]

            wins = sum(1 for o in comp if (o.realized_pnl_pct or 0) > 0 or o.target_hit)
            losses = sum(1 for o in comp if (o.realized_pnl_pct or 0) < 0 or o.stop_hit)
            expired = sum(1 for o in comp if o.expired)

            pnls = [o.realized_pnl_pct for o in comp if o.realized_pnl_pct is not None]
            day_pnl = sum(pnls)
            cum_pnl += day_pnl
            avg_pnl = (day_pnl / len(pnls)) if pnls else None

            series.append(DailySeriesRecord(
                date=d,
                setups_generated=n_gen,
                qualified_setups=n_qual,
                triggered=trig,
                completed=len(comp),
                wins=wins,
                losses=losses,
                expired=expired,
                daily_realized_pnl_pct=_safe_round(day_pnl) or 0.0,
                cumulative_pnl_pct=_safe_round(cum_pnl) or 0.0,
                average_pnl_pct=_safe_round(avg_pnl),
            ))

        return series

    def _compute_walk_forward_validation(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> List[WalkForwardWindow]:
        """
        Evaluate performance across rolling windows strictly sorted by setup_date.
        CRITICAL NO-LEAKAGE RULE:
        A setup at index i is only evaluated using outcomes that occurred forward
        in time after its setup_date.
        """
        # Sort setups chronologically by setup_date
        sorted_setups = sorted(
            [s for s in setups if s.setup_date],
            key=lambda s: s.setup_date,
        )

        completed_pairs: List[Tuple[TradeSetup, SetupOutcome]] = []
        for s in sorted_setups:
            o = outcome_map.get(s.setup_id)
            # Ensure outcome respects forward-in-time condition (entry/exit on or after setup)
            if o and o.entry_triggered and (o.target_hit or o.stop_hit or o.expired):
                completed_pairs.append((s, o))

        windows: List[WalkForwardWindow] = []
        eval_sizes = [20, 50, 100]

        total_comp = len(completed_pairs)
        for w_size in eval_sizes:
            if total_comp < w_size:
                # Still provide status record indicating insufficient sample for this window size
                windows.append(WalkForwardWindow(
                    window_name=f"Rolling {w_size} Trades",
                    sample_size=w_size,
                    start_date="N/A",
                    end_date="N/A",
                    completed_trades=total_comp,
                    win_rate=None,
                    average_pnl_pct=None,
                    expectancy=None,
                    profit_factor=None,
                    sample_status="INSUFFICIENT_SAMPLE",
                ))
            else:
                # Take the most recent w_size completed forward trades
                chunk = completed_pairs[-w_size:]
                start_d = chunk[0][0].setup_date
                end_d = chunk[-1][0].setup_date

                pnls = [o.realized_pnl_pct for _, o in chunk if o.realized_pnl_pct is not None]
                wins = sum(1 for p in pnls if p > 0)
                losses = sum(1 for p in pnls if p < 0)

                w_rate = (wins / len(pnls) * 100.0) if pnls else None
                avg_pnl = (sum(pnls) / len(pnls)) if pnls else None

                win_pnls = [p for p in pnls if p > 0]
                loss_pnls = [p for p in pnls if p < 0]
                avg_win = (sum(win_pnls) / len(win_pnls)) if win_pnls else None
                avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else None

                if w_rate is not None and avg_win is not None and avg_loss is not None:
                    exp = ((w_rate / 100.0) * avg_win) + (((100.0 - w_rate) / 100.0) * avg_loss)
                else:
                    exp = avg_pnl

                gross_w = sum(win_pnls)
                gross_l = abs(sum(loss_pnls))
                pf = (gross_w / gross_l) if gross_l > 0 else (float("inf") if gross_w > 0 else None)

                windows.append(WalkForwardWindow(
                    window_name=f"Rolling {w_size} Trades",
                    sample_size=w_size,
                    start_date=start_d,
                    end_date=end_d,
                    completed_trades=w_size,
                    win_rate=_safe_round(w_rate, 1),
                    average_pnl_pct=_safe_round(avg_pnl),
                    expectancy=_safe_round(exp),
                    profit_factor=_safe_round(pf),
                    sample_status="VALIDATED_SAMPLE",
                ))

        return windows

    def _compute_out_of_sample_comparison(
        self,
        setups: List[TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> Optional[OutOfSampleComparison]:
        """
        Split chronological setups into Historical (In-Sample) and Forward (Out-of-Sample)
        partitions without any leakage of future outcomes into the historical phase.
        """
        completed = [
            (s, outcome_map[s.setup_id])
            for s in sorted(setups, key=lambda x: x.setup_date or "")
            if s.setup_id in outcome_map and outcome_map[s.setup_id].entry_triggered
            and (outcome_map[s.setup_id].target_hit or outcome_map[s.setup_id].stop_hit or outcome_map[s.setup_id].expired)
        ]

        if len(completed) < 4:
            return None

        # 50/50 chronological split
        split_idx = len(completed) // 2
        hist_chunk = completed[:split_idx]
        fwd_chunk = completed[split_idx:]

        split_date = fwd_chunk[0][0].setup_date or "N/A"

        def chunk_stats(chunk: List[Tuple[TradeSetup, SetupOutcome]]) -> Tuple[int, Optional[float], Optional[float], Optional[float]]:
            pnls = [o.realized_pnl_pct for _, o in chunk if o.realized_pnl_pct is not None]
            n = len(pnls)
            if n == 0:
                return 0, None, None, None
            wins = sum(1 for p in pnls if p > 0)
            wr = (wins / n) * 100.0
            avg = sum(pnls) / n

            w_pnls = [p for p in pnls if p > 0]
            l_pnls = [p for p in pnls if p < 0]
            avg_w = (sum(w_pnls) / len(w_pnls)) if w_pnls else None
            avg_l = (sum(l_pnls) / len(l_pnls)) if l_pnls else None
            if avg_w is not None and avg_l is not None:
                exp = ((wr / 100.0) * avg_w) + (((100.0 - wr) / 100.0) * avg_l)
            else:
                exp = avg
            return n, _safe_round(wr, 1), _safe_round(avg), _safe_round(exp)

        h_n, h_wr, h_avg, h_exp = chunk_stats(hist_chunk)
        f_n, f_wr, f_avg, f_exp = chunk_stats(fwd_chunk)

        f_status = "VALIDATED_SAMPLE" if f_n >= self.min_completed_trades else "INSUFFICIENT_SAMPLE"

        return OutOfSampleComparison(
            split_date=split_date,
            historical_trades=h_n,
            historical_win_rate=h_wr,
            historical_avg_pnl=h_avg,
            historical_expectancy=h_exp,
            forward_trades=f_n,
            forward_win_rate=f_wr,
            forward_avg_pnl=f_avg,
            forward_expectancy=f_exp,
            forward_status=f_status,
        )

    def _compute_benchmark_comparison(
        self,
        completed_data: List[Tuple[TradeSetup, SetupOutcome]],
    ) -> Dict[str, Any]:
        """
        Compare realized returns against available benchmark data.
        Explicitly reports 'Benchmark unavailable' if real market benchmark cannot be deduced.
        """
        # We do not fabricate or invent benchmark indices
        return {
            "status": "Benchmark unavailable",
            "reason": "Broader index (Nifty 50 / Equal-Weight Watchlist) historical intraday feed not stored locally in database",
            "strategy_avg_pnl": _safe_round(statistics.mean([o.realized_pnl_pct for _, o in completed_data if o.realized_pnl_pct is not None])) if completed_data else None,
        }

    def _check_data_integrity(
        self,
        setups: List[TradeSetup],
        outcomes: List[SetupOutcome],
        setup_map: Dict[str, TradeSetup],
        outcome_map: Dict[str, SetupOutcome],
    ) -> DataIntegrityReport:
        """Audit records for duplicates, orphan records, conflicting flags, and impossible dates."""
        issues: List[str] = []
        checks = 10

        # 1. Duplicate setup IDs
        seen_sids: set[str] = set()
        for s in setups:
            if s.setup_id in seen_sids:
                issues.append(f"Duplicate setup_id in setups: {s.setup_id}")
            seen_sids.add(s.setup_id)

        # 2. Duplicate outcome IDs
        seen_oids: set[str] = set()
        for o in outcomes:
            if o.setup_id in seen_oids:
                issues.append(f"Duplicate setup_id in outcomes: {o.setup_id}")
            seen_oids.add(o.setup_id)

        # 3. Orphan outcomes (outcome exists but setup does not)
        for o in outcomes:
            if o.setup_id not in setup_map:
                issues.append(f"Orphan outcome detected: setup_id={o.setup_id} has no matching stage2_setups record")

        # 4-10: Value & Date Sanity Checks on outcomes
        for o in outcomes:
            s = setup_map.get(o.setup_id)

            # Impossible dates: exit before entry
            if o.entry_date and o.exit_date and o.exit_date < o.entry_date:
                issues.append(f"Setup {o.setup_id}: exit_date ({o.exit_date}) is earlier than entry_date ({o.entry_date})")

            # Entry date before setup date
            if s and s.setup_date and o.entry_date and o.entry_date < s.setup_date:
                issues.append(f"Setup {o.setup_id}: entry_date ({o.entry_date}) is earlier than setup_date ({s.setup_date})")

            # Exit without entry
            if (o.exit_price or o.exit_date) and not o.entry_triggered:
                issues.append(f"Setup {o.setup_id}: exit recorded without entry_triggered=True")

            # Contradictory outcomes: target AND stop both marked
            if o.target_hit and o.stop_hit:
                issues.append(f"Setup {o.setup_id}: both target_hit and stop_hit are marked True simultaneously")

            # Missing P&L on completed trade
            if (o.target_hit or o.stop_hit or o.expired) and o.realized_pnl_pct is None:
                issues.append(f"Setup {o.setup_id}: completed trade missing realized_pnl_pct")

            # Invalid MFE / MAE values
            if o.mfe_pct is not None and o.mfe_pct < -0.01:
                issues.append(f"Setup {o.setup_id}: invalid negative MFE ({o.mfe_pct}%)")
            if o.mae_pct is not None and o.mae_pct > 0.01:
                issues.append(f"Setup {o.setup_id}: invalid positive MAE ({o.mae_pct}%)")

            # Impossible holding period
            if o.holding_period_days < 0 or o.holding_period_days > 365:
                issues.append(f"Setup {o.setup_id}: impossible holding_period_days ({o.holding_period_days})")

        status = "WARN" if issues else "PASS"
        return DataIntegrityReport(
            status=status,
            checks_performed=checks,
            issues_detected=len(issues),
            issues=issues,
        )

    # -------------------------------------------------------------------------
    # Report Generation: JSON, Markdown, Telegram
    # -------------------------------------------------------------------------

    def generate_reports(self, output_dir: Path | str = "data/performance") -> Tuple[Path, Path, PerformanceReport]:
        """Generate and save both latest.json and latest.md reports."""
        report = self.calculate()
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        json_file = out_path / "latest.json"
        md_file = out_path / "latest.md"

        # 1. Machine-readable JSON
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        logger.info("Saved machine-readable performance report to %s", json_file)

        # 2. Human-readable Markdown
        md_content = self.render_markdown(report)
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info("Saved human-readable performance report to %s", md_file)

        return json_file, md_file, report

    def render_markdown(self, report: PerformanceReport) -> str:
        """Format an authoritative human-readable Markdown report."""
        sm = report.setup_metrics
        om = report.outcome_metrics
        pm = report.pnl_metrics
        em = report.excursion_metrics
        hp = report.holding_period_metrics
        di = report.data_integrity
        ds = report.data_sufficiency

        lines: List[str] = [
            "# Scheme-Intel Forward Performance & Validation Report",
            f"\n**Generated At:** {report.generated_at} UTC",
            f"**Data Period:** {report.data_period['start_date']} → {report.data_period['end_date']}",
            f"**Data Sufficiency Status:** `{ds['status']}` — *{ds['label']}*",
            f"**Strategy Validation Status:** `{report.strategy_status}`",
            "\n---\n",
            "## 1. Setup Lifecycle Sample",
            f"- **Total Setups Recorded:** {sm.total_setups}",
            f"- **Qualified Setups:** {sm.qualified_setups}",
            f"- **Waiting Setups:** {sm.waiting_setups}",
            f"- **Rejected Setups (Hard Risk Veto / No Trade):** {sm.rejected_setups}",
            f"- **Triggered Entries:** {sm.triggered_setups}",
            f"- **Untriggered Setups:** {sm.untriggered_setups} *(never counted as losses)*",
            f"- **Currently Active (Open) Trades:** {sm.active_setups}",
            f"- **Completed Trades:** {sm.completed_setups}",
            f"- **Expired Positions:** {sm.expired_setups}",
            "\n---\n",
            "## 2. Outcome Statistics",
            f"- **Completed Triggered Trades:** {om.completed_trades}",
            f"- **Target 1 Hits (Wins):** {om.target_hits}",
            f"- **Stop Loss Hits (Losses):** {om.stop_hits}",
            f"- **Expired at Max Age:** {om.expired}",
            f"- **Win Rate:** {f'{om.win_rate}%' if om.win_rate is not None else 'N/A'} *(wins / completed trades)*",
            f"- **Loss Rate:** {f'{om.loss_rate}%' if om.loss_rate is not None else 'N/A'}",
            f"- **Expiry Rate:** {f'{om.expiry_rate}%' if om.expiry_rate is not None else 'N/A'}",
            "\n---\n",
            "## 3. Return & P&L Metrics",
            f"- **Average Realized P&L:** {f'{pm.average_pnl_pct:+.2f}%' if pm.average_pnl_pct is not None else 'N/A'}",
            f"- **Median Realized P&L:** {f'{pm.median_pnl_pct:+.2f}%' if pm.median_pnl_pct is not None else 'N/A'}",
            f"- **Cumulative Realized P&L:** {f'{pm.cumulative_pnl_pct:+.2f}%'}",
            f"- **Average Winning Trade:** {f'{pm.average_win_pct:+.2f}%' if pm.average_win_pct is not None else 'N/A'}",
            f"- **Average Losing Trade:** {f'{pm.average_loss_pct:+.2f}%' if pm.average_loss_pct is not None else 'N/A'}",
            f"- **Largest Winner:** {f'{pm.largest_winner_pct:+.2f}%' if pm.largest_winner_pct is not None else 'N/A'}",
            f"- **Largest Loser:** {f'{pm.largest_loser_pct:+.2f}%' if pm.largest_loser_pct is not None else 'N/A'}",
            f"- **Profit Factor:** {pm.profit_factor if pm.profit_factor is not None else 'N/A'} *(gross profits / gross losses)*",
            f"- **Expectancy:** {f'{pm.expectancy:+.2f}%' if pm.expectancy is not None else 'N/A'} per triggered trade",
            f"- **Standard Deviation of Returns:** {f'{pm.std_dev_pnl_pct:.2f}%' if pm.std_dev_pnl_pct is not None else 'N/A'}",
            "\n---\n",
            "## 4. MFE & MAE Excursions",
            f"- **Average MFE (Max Favorable Excursion):** {f'+{em.average_mfe_pct:.2f}%' if em.average_mfe_pct is not None else 'N/A'}",
            f"- **Median MFE:** {f'+{em.median_mfe_pct:.2f}%' if em.median_mfe_pct is not None else 'N/A'}",
            f"- **Maximum MFE Observed:** {f'+{em.maximum_mfe_pct:.2f}%' if em.maximum_mfe_pct is not None else 'N/A'}",
            f"- **Average MAE (Max Adverse Excursion):** {f'{em.average_mae_pct:.2f}%' if em.average_mae_pct is not None else 'N/A'}",
            f"- **Median MAE:** {f'{em.median_mae_pct:.2f}%' if em.median_mae_pct is not None else 'N/A'}",
            f"- **Maximum Adverse Excursion (Worst Dip):** {f'{em.maximum_adverse_excursion:.2f}%' if em.maximum_adverse_excursion is not None else 'N/A'}",
            "\n### Excursion Distributions",
            "| MFE Bucket | Trades | MAE Bucket | Trades |",
            "| :--- | :--- | :--- | :--- |",
        ]

        mfe_keys = ["<0%", "0–2%", "2–5%", "5–10%", ">10%"]
        mae_keys = ["0 to -1%", "-1 to -3%", "-3 to -5%", "<-5%"]
        for i in range(max(len(mfe_keys), len(mae_keys))):
            m_k = mfe_keys[i] if i < len(mfe_keys) else ""
            m_v = em.mfe_distribution.get(m_k, "") if m_k else ""
            a_k = mae_keys[i] if i < len(mae_keys) else ""
            a_v = em.mae_distribution.get(a_k, "") if a_k else ""
            lines.append(f"| {m_k} | {m_v} | {a_k} | {a_v} |")

        def _fmt_hp(d: Dict[str, Optional[float]], key: str) -> str:
            v = d.get(key)
            return f"{v} days" if v is not None else "N/A"

        lines.extend([
            "\n---\n",
            "## 5. Holding Period Analytics",
            f"- **Overall Holding Period:** Avg {_fmt_hp(hp.overall, 'average')} | Median {_fmt_hp(hp.overall, 'median')} (Min {_fmt_hp(hp.overall, 'min')} - Max {_fmt_hp(hp.overall, 'max')})",
            f"- **Winning Trades:** Avg {_fmt_hp(hp.wins, 'average')}",
            f"- **Losing Trades:** Avg {_fmt_hp(hp.losses, 'average')}",
            f"- **Expired Trades:** Avg {_fmt_hp(hp.expired, 'average')}",
            "\n---\n",
            "## 6. Breakdown by Archetype",
            "| Archetype | Setups | Trig | Comp | Win Rate | Avg P&L | Expectancy | PF | Avg MFE | Avg MAE | Status |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ])

        for a in report.archetype_breakdown:
            wr_str = f"{a.win_rate}%" if a.win_rate is not None else "N/A"
            pnl_str = f"{a.average_pnl_pct:+.2f}%" if a.average_pnl_pct is not None else "N/A"
            exp_str = f"{a.expectancy:+.2f}%" if a.expectancy is not None else "N/A"
            pf_str = f"{a.profit_factor:.2f}" if a.profit_factor is not None else "N/A"
            mfe_str = f"+{a.average_mfe_pct:.1f}%" if a.average_mfe_pct is not None else "N/A"
            mae_str = f"{a.average_mae_pct:.1f}%" if a.average_mae_pct is not None else "N/A"
            lines.append(f"| {a.archetype} | {a.setups} | {a.triggered} | {a.completed} | {wr_str} | {pnl_str} | {exp_str} | {pf_str} | {mfe_str} | {mae_str} | `{a.sample_status}` |")

        lines.extend([
            "\n---\n",
            "## 7. Breakdown by Stock Symbol",
            "| Symbol | Setups | Trig | Comp | Win Rate | Avg P&L | Expectancy | Avg MFE | Avg MAE | Status |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ])

        for s in report.symbol_breakdown:
            wr_str = f"{s.win_rate}%" if s.win_rate is not None else "N/A"
            pnl_str = f"{s.average_pnl_pct:+.2f}%" if s.average_pnl_pct is not None else "N/A"
            exp_str = f"{s.expectancy:+.2f}%" if s.expectancy is not None else "N/A"
            mfe_str = f"+{s.average_mfe_pct:.1f}%" if s.average_mfe_pct is not None else "N/A"
            mae_str = f"{s.average_mae_pct:.1f}%" if s.average_mae_pct is not None else "N/A"
            lines.append(f"| {s.symbol} | {s.setups} | {s.triggered} | {s.completed} | {wr_str} | {pnl_str} | {exp_str} | {mfe_str} | {mae_str} | `{s.sample_status}` |")

        lines.extend([
            "\n---\n",
            "## 8. Breakdown by AI Provider",
            "*(Observational measurement only. Does not imply causation.)*",
            "| Provider | Setups | Trig | Comp | Win Rate | Avg P&L | Expectancy | Avg MFE | Avg MAE | Status |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ])

        for p in report.provider_breakdown:
            wr_str = f"{p.win_rate}%" if p.win_rate is not None else "N/A"
            pnl_str = f"{p.average_pnl_pct:+.2f}%" if p.average_pnl_pct is not None else "N/A"
            exp_str = f"{p.expectancy:+.2f}%" if p.expectancy is not None else "N/A"
            mfe_str = f"+{p.average_mfe_pct:.1f}%" if p.average_mfe_pct is not None else "N/A"
            mae_str = f"{p.average_mae_pct:.1f}%" if p.average_mae_pct is not None else "N/A"
            lines.append(f"| {p.provider} | {p.setups} | {p.triggered} | {p.completed} | {wr_str} | {pnl_str} | {exp_str} | {mfe_str} | {mae_str} | `{p.sample_status}` |")

        lines.extend([
            "\n---\n",
            "## 9. Score-Band Analysis",
            "| Candidate Score Band | Setups | Triggered | Completed | Win Rate | Avg P&L | Expectancy |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ])

        for b in report.score_band_breakdown:
            wr_str = f"{b.win_rate}%" if b.win_rate is not None else "N/A"
            pnl_str = f"{b.average_pnl_pct:+.2f}%" if b.average_pnl_pct is not None else "N/A"
            exp_str = f"{b.expectancy:+.2f}%" if b.expectancy is not None else "N/A"
            lines.append(f"| {b.band_label} | {b.setups} | {b.triggered} | {b.completed} | {wr_str} | {pnl_str} | {exp_str} |")

        lines.extend([
            "\n---\n",
            "## 10. Walk-Forward & Out-of-Sample Validation",
            "### Rolling Forward Windows",
            "| Window Name | Trades | Start Date | End Date | Win Rate | Avg P&L | Expectancy | PF | Status |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ])

        for w in report.walk_forward_windows:
            wr_str = f"{w.win_rate}%" if w.win_rate is not None else "N/A"
            pnl_str = f"{w.average_pnl_pct:+.2f}%" if w.average_pnl_pct is not None else "N/A"
            exp_str = f"{w.expectancy:+.2f}%" if w.expectancy is not None else "N/A"
            pf_str = f"{w.profit_factor:.2f}" if w.profit_factor is not None else "N/A"
            lines.append(f"| {w.window_name} | {w.completed_trades} | {w.start_date} | {w.end_date} | {wr_str} | {pnl_str} | {exp_str} | {pf_str} | `{w.sample_status}` |")

        if report.out_of_sample_comparison:
            oos = report.out_of_sample_comparison
            lines.extend([
                "\n### Out-of-Sample Partition Comparison",
                f"- **Chronological Split Date:** {oos.split_date}",
                f"- **Historical (In-Sample):** {oos.historical_trades} trades | Win Rate: {oos.historical_win_rate or 'N/A'}% | Avg P&L: {oos.historical_avg_pnl or 'N/A'}% | Exp: {oos.historical_expectancy or 'N/A'}%",
                f"- **Forward (Out-of-Sample):** {oos.forward_trades} trades | Win Rate: {oos.forward_win_rate or 'N/A'}% | Avg P&L: {oos.forward_avg_pnl or 'N/A'}% | Exp: {oos.forward_expectancy or 'N/A'}% (`{oos.forward_status}`)",
            ])

        lines.extend([
            "\n---\n",
            "## 11. Baseline Benchmark Comparison",
            f"- **Status:** `{report.benchmark_comparison.get('status', 'Benchmark unavailable')}`",
            f"- **Details:** {report.benchmark_comparison.get('reason', 'N/A')}",
            "\n---\n",
            "## 12. Data Integrity Checks",
            f"- **Audit Status:** `{di.status}`",
            f"- **Checks Performed:** {di.checks_performed}",
            f"- **Issues Detected:** {di.issues_detected}",
        ])

        if di.issues:
            lines.append("\n**Integrity Warnings:**")
            for iss in di.issues:
                lines.append(f"- ⚠️ {iss}")
        else:
            lines.append("- ✅ Zero schema violations, orphan records, or date inversions detected.")

        return "\n".join(lines)

    def get_telegram_summary(self, report: Optional[PerformanceReport] = None) -> str:
        """
        Produce a compact, non-spammy Telegram summary:
        - If completed_trades < min_completed_trades:
            `📊 *FORWARD PERFORMANCE:* collecting data — {N} completed trades`
        - If completed_trades >= min_completed_trades:
            Full compact statistical summary.
        """
        rep = report or self.calculate()
        om = rep.outcome_metrics
        pm = rep.pnl_metrics
        n_comp = om.completed_trades

        if n_comp < self.min_completed_trades:
            return f"📊 *FORWARD PERFORMANCE:* collecting data — {n_comp} completed trades (needs {self.min_completed_trades} for validated sample)"

        wr_str = f"{om.win_rate:.1f}%" if om.win_rate is not None else "N/A"
        pnl_str = f"{pm.average_pnl_pct:+.2f}%" if pm.average_pnl_pct is not None else "N/A"
        exp_str = f"{pm.expectancy:+.2f}%" if pm.expectancy is not None else "N/A"
        pf_str = f"{pm.profit_factor:.2f}" if pm.profit_factor is not None else "N/A"

        return (
            f"📊 *FORWARD PERFORMANCE (VALIDATED)*\n"
            f"• Trades: *{n_comp}* | Wins: *{om.wins}* | Losses: *{om.losses}* | Expired: *{om.expired}*\n"
            f"• Win Rate: *{wr_str}* | Avg P&L: *{pnl_str}*\n"
            f"• Expectancy: *{exp_str}* | Profit Factor: *{pf_str}*"
        )
