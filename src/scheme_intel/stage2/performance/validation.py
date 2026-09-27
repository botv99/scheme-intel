"""
Validation and data integrity engines for Stage 2 Performance Analytics.
Ensures zero-lookahead walk-forward validation and data sanity without leakage.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..models import SetupOutcome, TradeSetup
from .models import (
    DataIntegrityReport,
    OutOfSampleComparison,
    WalkForwardWindow,
    _safe_round,
)


def compute_walk_forward_validation(
    setups: List[TradeSetup],
    outcome_map: Dict[str, SetupOutcome],
) -> List[WalkForwardWindow]:
    """
    Evaluate performance across rolling windows strictly sorted by setup_date.
    CRITICAL NO-LEAKAGE RULE:
    A setup at index i is only evaluated using outcomes that occurred forward
    in time after its setup_date.
    """
    sorted_setups = sorted(
        [s for s in setups if s.setup_date],
        key=lambda s: s.setup_date,
    )

    completed_pairs: List[Tuple[TradeSetup, SetupOutcome]] = []
    for s in sorted_setups:
        o = outcome_map.get(s.setup_id)
        if o and o.entry_triggered and (o.target_hit or o.stop_hit or o.expired):
            completed_pairs.append((s, o))

    windows: List[WalkForwardWindow] = []
    eval_sizes = [20, 50, 100]

    total_comp = len(completed_pairs)
    for w_size in eval_sizes:
        if total_comp < w_size:
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


def compute_out_of_sample_comparison(
    setups: List[TradeSetup],
    outcome_map: Dict[str, SetupOutcome],
    min_completed_trades: int = 30,
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

    f_status = "VALIDATED_SAMPLE" if f_n >= min_completed_trades else "INSUFFICIENT_SAMPLE"

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


def check_data_integrity(
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
