"""
Statistical and P&L metric computation functions for Stage 2 Performance Analytics.
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Tuple

from ..models import SetupOutcome, TradeSetup
from ...logger import get_logger
from .models import (
    ArchetypeStats,
    DailySeriesRecord,
    ExcursionMetrics,
    HoldingPeriodMetrics,
    OutcomeMetrics,
    PnLMetrics,
    ProviderStats,
    ScoreBandStats,
    SetupMetrics,
    SymbolStats,
    _safe_round,
)

logger = get_logger(__name__)


def compute_setup_metrics(
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


def compute_outcome_metrics(
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


def compute_pnl_metrics(
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


def compute_excursion_metrics(
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


def compute_holding_metrics(
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


def compute_archetype_breakdown(
    setups: List[TradeSetup],
    outcome_map: Dict[str, SetupOutcome],
    min_archetype_sample: int = 20,
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

        sample_status = "VALIDATED_SAMPLE" if n_comp >= min_archetype_sample else "INSUFFICIENT_SAMPLE"

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


def compute_symbol_breakdown(
    setups: List[TradeSetup],
    outcome_map: Dict[str, SetupOutcome],
    min_stock_sample: int = 20,
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

        sample_status = "VALIDATED_SAMPLE" if n_comp >= min_stock_sample else "INSUFFICIENT_SAMPLE"

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


def compute_provider_breakdown(
    setups: List[TradeSetup],
    outcome_map: Dict[str, SetupOutcome],
    min_completed_trades: int = 30,
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

        sample_status = "VALIDATED_SAMPLE" if n_comp >= min_completed_trades else "INSUFFICIENT_SAMPLE"

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


def compute_score_band_breakdown(
    setups: List[TradeSetup],
    outcome_map: Dict[str, SetupOutcome],
    score_bands: List[Tuple[int, int]],
) -> List[ScoreBandStats]:
    results: List[ScoreBandStats] = []
    for low, high in score_bands:
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


def compute_daily_series(
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


def compute_benchmark_comparison(
    completed_data: List[Tuple[TradeSetup, SetupOutcome]],
    db_path: Any,
) -> Dict[str, Any]:
    try:
        from ...analytics.benchmark import evaluate_benchmark_performance
        from ...market.benchmark import BenchmarkEngine
        be = BenchmarkEngine(db_path=db_path)
        return evaluate_benchmark_performance(completed_data, benchmark_engine=be)
    except Exception as e:
        logger.warning("Error evaluating benchmark performance: %s", e)
        return {
            "status": "UNAVAILABLE — benchmark data missing",
            "available": False,
            "reason": str(e),
            "strategy_avg_pnl": _safe_round(statistics.mean([o.realized_pnl_pct for _, o in completed_data if o.realized_pnl_pct is not None])) if completed_data else None,
        }
