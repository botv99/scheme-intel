"""
Report rendering and export engines (Markdown, JSON, Telegram) for Stage 2 Performance Analytics.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ...logger import get_logger
from .models import MIN_COMPLETED_TRADES, PerformanceReport

logger = get_logger(__name__)


def render_markdown(report: PerformanceReport) -> str:
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
        "## 11. Baseline Benchmark Comparison (NIFTY 50)",
        f"- **Status:** `{report.benchmark_comparison.get('status', 'Benchmark unavailable')}`",
    ])
    bc = report.benchmark_comparison
    avg_strat = f"{bc['average_strategy_return']:+.2f}%" if bc.get("average_strategy_return") is not None else "N/A"
    avg_bench = f"{bc['average_benchmark_return']:+.2f}%" if bc.get("average_benchmark_return") is not None else "N/A"
    avg_excess = f"{bc['average_excess_return']:+.2f}%" if bc.get("average_excess_return") is not None else "N/A"
    med_excess = f"{bc['median_excess_return']:+.2f}%" if bc.get("median_excess_return") is not None else "N/A"
    cum_excess = f"{bc['cumulative_excess_return']:+.2f}%" if bc.get("cumulative_excess_return") is not None else "N/A"
    if bc.get("available"):
        lines.extend([
            f"- **Trades Evaluated:** {bc.get('trades_evaluated', 0)} / {bc.get('completed_trades', 0)}",
            f"- **Average Strategy Return:** {avg_strat}",
            f"- **Average Benchmark Return (Nifty 50):** {avg_bench}",
            f"- **Average Excess Return (Alpha):** {avg_excess}",
            f"- **Median Excess Return:** {med_excess}",
            f"- **Cumulative Excess Return:** {cum_excess}",
        ])
        if bc.get("trade_comparisons"):
            lines.extend([
                "\n### Trade-by-Trade Benchmark Comparison",
                "| Setup ID | Symbol | Entry Date | Exit Date | Strategy P&L | Nifty Return | Excess Return |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            ])
            for tc in bc["trade_comparisons"]:
                lines.append(f"| {tc['setup_id']} | {tc['symbol']} | {tc['entry_date']} | {tc['exit_date']} | {tc['strategy_return']:+.2f}% | {tc['benchmark_return']:+.2f}% | {tc['excess_return']:+.2f}% |")
    else:
        reason = bc.get("reason") or bc.get("status")
        lines.append(f"- **Details:** {reason}")

    lines.extend([
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


def get_telegram_summary(report: PerformanceReport, min_completed_trades: int = MIN_COMPLETED_TRADES) -> str:
    """
    Produce a compact, non-spammy Telegram summary:
    - If completed_trades < min_completed_trades:
        `📊 *FORWARD PERFORMANCE:* collecting data — {N} completed trades`
    - If completed_trades >= min_completed_trades:
        Full compact statistical summary.
    """
    om = report.outcome_metrics
    pm = report.pnl_metrics
    n_comp = om.completed_trades

    if n_comp < min_completed_trades:
        return f"📊 *FORWARD PERFORMANCE:* collecting data — {n_comp} completed trades (needs {min_completed_trades} for validated sample)"

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


def generate_reports(report: PerformanceReport, output_dir: Path | str = "data/performance") -> Tuple[Path, Path, PerformanceReport]:
    """Generate and save both latest.json and latest.md reports."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    json_file = out_path / "latest.json"
    md_file = out_path / "latest.md"

    # 1. Machine-readable JSON
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)
    logger.info("Saved machine-readable performance report to %s", json_file)

    # 2. Human-readable Markdown
    md_content = render_markdown(report)
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info("Saved human-readable performance report to %s", md_file)

    return json_file, md_file, report
