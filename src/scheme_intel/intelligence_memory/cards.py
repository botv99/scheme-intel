"""
Prebuilt Answer Cards and Terminal Renderers for Telegram Conversational Interface.
Formats structured intelligence memory into clean, readable, factual Markdown terminal cards.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from .models import (
    CompanyIntelligence,
    SchemeIntelligence,
    PerformanceIntelligence,
    BenchmarkIntelligence,
)


def _stale_banner(is_stale: bool, updated_at: str) -> str:
    if is_stale:
        return f"⚠️ *DATA NOTE: Snapshot is >26h old (Last update: {updated_at[:16]}).*\n\n"
    return ""


def render_stock_card(comp: CompanyIntelligence, is_stale: bool = False) -> str:
    """Format compact stock intelligence card."""
    banner = _stale_banner(is_stale, comp.updated_at)
    price_str = f"₹{comp.price:,.2f}" if comp.price is not None else "N/A"
    change_str = f"{comp.change_pct:+.2f}%" if comp.change_pct is not None else "N/A"

    lines = [
        f"{banner}🏷️ *{comp.short_symbol}*",
        f"_{comp.name}_",
        "",
        f"*Scheme:* {comp.scheme_name}",
        f"*Relevance:* {comp.relevance}",
        "",
        "*PRICE*",
        f"{price_str} ({change_str})",
    ]

    if comp.trend or comp.support or comp.resistance:
        lines.extend([
            "",
            "*TECHNICAL STATE*",
            f"• Trend: {comp.trend or 'N/A'}",
            f"• Support: ₹{comp.support:.2f}" if comp.support else "• Support: N/A",
            f"• Resistance: ₹{comp.resistance:.2f}" if comp.resistance else "• Resistance: N/A",
            f"• RSI (14): {comp.rsi:.1f}" if comp.rsi else "• RSI (14): N/A",
        ])

    lines.extend([
        "",
        f"*CURRENT STATUS:* `{comp.status}`",
    ])

    if comp.archetype:
        lines.extend([
            "",
            "*SETUP*",
            f"• Archetype: {comp.archetype}",
            f"• Score: {comp.score or 'N/A'}/100",
            f"• Trigger: ₹{comp.trigger_price:.2f}" if comp.trigger_price else "• Trigger: N/A",
            f"• Stop Loss: ₹{comp.stop_loss:.2f}" if comp.stop_loss else "• Stop Loss: N/A",
            f"• Target 1: ₹{comp.target:.2f}" if comp.target else "• Target 1: N/A",
        ])

    if comp.bull_thesis or comp.bear_thesis:
        lines.extend([
            "",
            "*AI VIEW*",
            f"• Bull: {comp.bull_thesis[:140]}..." if comp.bull_thesis and len(comp.bull_thesis) > 140 else f"• Bull: {comp.bull_thesis or 'N/A'}",
            f"• Bear: {comp.bear_thesis[:140]}..." if comp.bear_thesis and len(comp.bear_thesis) > 140 else f"• Bear: {comp.bear_thesis or 'N/A'}",
        ])

    if comp.risk_summary:
        lines.extend([
            "",
            f"*RISK:* {comp.risk_summary}",
        ])

    if comp.waiting_conditions:
        lines.extend([
            "",
            "*WAITING CONDITIONS*",
        ])
        for wc in comp.waiting_conditions[:3]:
            lines.append(f"• {wc}")

    if comp.updated_at:
        lines.extend([
            "",
            f"_Updated: {comp.updated_at[:16]} UTC_",
        ])

    return "\n".join(lines)


def render_why_card(comp: CompanyIntelligence, is_stale: bool = False) -> str:
    """Format response answering: Why is this stock relevant to this scheme?"""
    banner = _stale_banner(is_stale, comp.updated_at)
    lines = [
        f"{banner}*WHY {comp.short_symbol}?*",
        f"_{comp.name}_",
        "",
        f"*Scheme:* {comp.scheme_name}",
        "",
        "*Why it is relevant:*",
        f"• {comp.mapping_rationale or 'Direct participant in government policy mandates.'}",
    ]

    if comp.catalyst:
        lines.extend([
            "",
            "*Latest policy / catalyst evidence:*",
            f"• {comp.catalyst}",
        ])

    lines.extend([
        "",
        f"*Current Scheme-Intel status:* `{comp.status}`",
    ])

    if comp.evidence:
        lines.extend([
            "",
            "*Evidence:*",
        ])
        for ev in comp.evidence[:3]:
            d = f" — {ev['date']}" if ev.get("date") else ""
            lines.append(f"• {ev.get('source', 'Source')}: {ev.get('title', 'Report')[:60]}...{d}")
    else:
        lines.extend([
            "",
            "_Verified against Scheme-Intel company mapping taxonomy._",
        ])

    return "\n".join(lines)


def render_what_card(comp: CompanyIntelligence, is_stale: bool = False) -> str:
    """Format response answering: What is happening with this company in the context of this scheme?"""
    banner = _stale_banner(is_stale, comp.updated_at)
    price_str = f"₹{comp.price:,.2f}" if comp.price is not None else "N/A"
    change_str = f"{comp.change_pct:+.2f}%" if comp.change_pct is not None else "N/A"

    lines = [
        f"{banner}*WHAT'S HAPPENING — {comp.short_symbol}*",
        f"_{comp.name}_",
        "",
        "*Latest development:*",
        f"{comp.latest_development or 'No new material policy catalyst detected in latest session.'}",
        "",
        f"*Scheme relevance:* {comp.relevance} ({comp.scheme_name})",
        f"*Market reaction:* {price_str} ({change_str})",
    ]

    if comp.trend:
        lines.append(f"*Technical state:* {comp.trend}")

    if comp.catalyst:
        lines.append(f"*Catalyst:* {comp.catalyst}")

    lines.append(f"*Current setup state:* `{comp.status}`")

    if comp.updated_at:
        lines.extend([
            "",
            f"_Last updated: {comp.updated_at[:16]} UTC_",
        ])

    return "\n".join(lines)


def render_when_card(comp: CompanyIntelligence, is_stale: bool = False) -> str:
    """Format response answering: What event/trigger should I watch next?"""
    banner = _stale_banner(is_stale, comp.updated_at)
    lines = [
        f"{banner}*WHEN TO WATCH — {comp.short_symbol}*",
        f"_{comp.name}_",
        "",
        f"*Current Status:* `{comp.status}`",
    ]

    if comp.trigger_price:
        lines.append(f"• *Technical trigger:* ₹{comp.trigger_price:.2f}")
    if comp.stop_loss:
        lines.append(f"• *Invalidation / Stop:* ₹{comp.stop_loss:.2f}")
    if comp.target:
        lines.append(f"• *Target 1:* ₹{comp.target:.2f}")

    if comp.waiting_conditions:
        lines.extend([
            "",
            "*Waiting conditions:*",
        ])
        for wc in comp.waiting_conditions:
            lines.append(f"• {wc}")

    if comp.next_session:
        lines.extend([
            "",
            f"*Expected next trading session:* {comp.next_session}",
        ])

    lines.extend([
        "",
        "⚠️ _Important: This is the existing Scheme-Intel quantitative setup state, not a prediction or financial advice._",
    ])
    return "\n".join(lines)


def render_scheme_card(scheme: SchemeIntelligence, is_stale: bool = False) -> str:
    """Format scheme overview card."""
    banner = _stale_banner(is_stale, scheme.last_update)
    lines = [
        f"{banner}🏛️ *{scheme.name.upper()}*",
        f"_{scheme.description}_",
        "",
        f"*Watchlist:* {scheme.watchlist_count} companies",
        "",
        "*Current intelligence:*",
        f"• Qualified setups: {scheme.qualified_setups_count}",
        f"• Waiting: {scheme.waiting_count}",
        f"• No trade: {scheme.no_trade_count}",
        f"• Data unavailable: {scheme.data_unavailable_count}",
    ]

    if scheme.key_developments:
        lines.extend([
            "",
            "*Key developments:*",
        ])
        for kd in scheme.key_developments[:4]:
            lines.append(f"• {kd}")

    if scheme.important_sources:
        lines.extend([
            "",
            "*Official Sources Monitored:*",
            ", ".join(scheme.important_sources),
        ])

    if scheme.last_update:
        lines.extend([
            "",
            f"_Last intelligence update: {scheme.last_update[:16]} UTC_",
        ])

    return "\n".join(lines)


def render_setups_card(setups: List[CompanyIntelligence], is_stale: bool = False, updated_str: str = "") -> str:
    """Format qualified setups list."""
    banner = _stale_banner(is_stale, updated_str)
    if not setups:
        return f"{banner}🎯 *CURRENT SETUPS*\n\nNo qualified setups in the latest completed intelligence cycle.\n\nAll watchlist candidates either failed quantitative risk filters or are in waiting conditions."

    lines = [
        f"{banner}🎯 *CURRENT QUALIFIED SETUPS*",
        f"Found {len(setups)} actionable setups from latest cycle:\n",
    ]
    for i, s in enumerate(setups, 1):
        trig = f"₹{s.trigger_price:.2f}" if s.trigger_price else "Market"
        sl = f"₹{s.stop_loss:.2f}" if s.stop_loss else "N/A"
        t1 = f"₹{s.target:.2f}" if s.target else "N/A"
        lines.append(
            f"*{i}. {s.short_symbol}* ({s.name})\n"
            f"   • Archetype: {s.archetype or 'Swing'}\n"
            f"   • Score: {s.score or 'N/A'}/100\n"
            f"   • Trigger: {trig} | SL: {sl} | T1: {t1}\n"
            f"   • Status: `{s.status}`\n"
        )
    return "\n".join(lines)


def render_waiting_card(waiting: List[CompanyIntelligence], is_stale: bool = False) -> str:
    """Format waiting setups list."""
    banner = _stale_banner(is_stale, "")
    if not waiting:
        return f"{banner}⏳ *WAITING SETUPS*\n\nNo setups currently waiting for trigger conditions."

    lines = [
        f"{banner}⏳ *WAITING SETUPS*",
        f"{len(waiting)} stocks under active surveillance:\n",
    ]
    for w in waiting:
        lines.append(f"*{w.short_symbol}* ({w.name})")
        if w.waiting_conditions:
            for wc in w.waiting_conditions[:2]:
                lines.append(f"• {wc}")
        else:
            lines.append("• Waiting for price trigger confirmation")
        lines.append("")
    return "\n".join(lines).strip()


def render_performance_card(perf: PerformanceIntelligence, is_stale: bool = False) -> str:
    """Format PerformanceAnalytics summary card."""
    banner = _stale_banner(is_stale, "")
    lines = [
        f"{banner}📊 *FORWARD PERFORMANCE*",
        "",
    ]
    if perf.completed_trades < perf.validation_threshold:
        lines.extend([
            "Forward performance is currently collecting live forward trade data.",
            "",
            f"• *Completed trades:* {perf.completed_trades}",
            f"• *Validation threshold:* {perf.validation_threshold}",
            f"• *Status:* `{perf.validation_status}`",
            f"• *Integrity Audit:* `{perf.audit_status}`",
            "",
            "_Note: Per institutional guidelines, strategy metrics are declared statistically valid only after reaching the 30 completed trade threshold._",
        ])
    else:
        win_str = f"{perf.win_rate:.1f}%" if perf.win_rate is not None else "N/A"
        pnl_str = f"{perf.avg_pnl:+.2f}%" if perf.avg_pnl is not None else "N/A"
        pf_str = f"{perf.profit_factor:.2f}" if perf.profit_factor is not None else "N/A"
        lines.extend([
            f"• *Completed trades:* {perf.completed_trades}",
            f"• *Validation status:* `{perf.validation_status}`",
            f"• *Win Rate:* {win_str}",
            f"• *Average P&L:* {pnl_str}",
            f"• *Profit Factor:* {pf_str}",
            f"• *Audit Status:* `{perf.audit_status}`",
        ])
    return "\n".join(lines)


def render_benchmark_card(bench: BenchmarkIntelligence, is_stale: bool = False) -> str:
    """Format NIFTY 50 comparative performance card."""
    banner = _stale_banner(is_stale, "")
    lines = [
        f"{banner}📈 *NIFTY 50 BENCHMARK COMPARISON*",
        "",
        f"• *Benchmark ID:* `{bench.benchmark_id}`",
        f"• *Status:* `{bench.status}`",
    ]

    if bench.trades_evaluated > 0:
        strat = f"{bench.strategy_return:+.2f}%" if bench.strategy_return is not None else "N/A"
        nifty = f"{bench.benchmark_return:+.2f}%" if bench.benchmark_return is not None else "N/A"
        excess = f"{bench.excess_return:+.2f}%" if bench.excess_return is not None else "N/A"
        wr = f"{bench.win_rate_vs_benchmark_pct:.1f}%" if bench.win_rate_vs_benchmark_pct is not None else "N/A"

        lines.extend([
            f"• *Trades Evaluated:* {bench.trades_evaluated} / {bench.completed_trades}",
            f"• *Strategy Avg Return:* {strat}",
            f"• *Nifty Avg Return:* {nifty}",
            f"• *Average Alpha (Excess):* {excess}",
            f"• *Win Rate vs Benchmark:* {wr}",
        ])
    else:
        reason = bench.reason or bench.status
        lines.extend([
            "",
            f"Details: {reason}",
        ])

    lines.extend([
        "",
        "_Leakage Protection: Benchmark returns are evaluated strictly over [entry_date, exit_date] with zero lookahead._",
    ])
    return "\n".join(lines)


def render_schemes_list_card(schemes: List[SchemeIntelligence]) -> str:
    """Format list of supported schemes."""
    lines = [
        "🏛️ *SUPPORTED POLICY SCHEMES*",
        "",
    ]
    for s in schemes:
        lines.append(f"• *{s.scheme_id}* — {s.name} ({s.watchlist_count} stocks)")
    lines.extend([
        "",
        "Use `/scheme <id>` to inspect detailed scheme intelligence.",
    ])
    return "\n".join(lines)


def render_help_card() -> str:
    """Format help menu."""
    return (
        "🤖 *SCHEME-INTEL TERMINAL*\n\n"
        "*FAST INTELLIGENCE*\n"
        "• `TRUALT` (or any watchlist symbol)\n"
        "• `/stock <symbol>` — Full intelligence card\n"
        "• `/why <symbol>` — Why stock is relevant to scheme\n"
        "• `/what <symbol>` — What is happening with company\n"
        "• `/when <symbol>` — Triggers & surveillance conditions\n"
        "• `/schemes` — List covered schemes\n"
        "• `/scheme <id>` — Scheme overview & developments\n"
        "• `/setups` — Current qualified setups\n"
        "• `/waiting` — Current waiting setups\n"
        "• `/performance` — Forward validation metrics\n"
        "• `/benchmark` — NIFTY 50 comparative analytics\n\n"
        "*DEEP ASYNC RESEARCH*\n"
        "• `/research <question>` — Queue deep investigation\n\n"
        "_Fast commands retrieve precalculated memory. Research runs asynchronously._"
    )


def render_unknown_stock(symbol: str) -> str:
    return (
        f"I don't recognize `{symbol}` in the active Scheme-Intel watchlist.\n\n"
        "Use `/schemes` or `/help` to view covered schemes and stocks."
    )


def render_unknown_scheme(scheme_id: str) -> str:
    return (
        f"I don't recognize scheme `{scheme_id}` in Scheme-Intel.\n\n"
        "Use `/schemes` to view currently registered schemes."
    )


def render_snapshot_missing() -> str:
    return (
        "⚠️ *Intelligence memory is currently unavailable.*\n\n"
        "The latest intelligence refresh has not produced a valid snapshot yet.\n"
        "Please try again after the next successful refresh."
    )


def render_snapshot_invalid(error_msg: str = "") -> str:
    err_snippet = f"\n_Diagnostic:_ `{error_msg[:120]}`" if error_msg else ""
    return (
        "⚠️ *Intelligence memory is currently corrupted or invalid.*\n\n"
        "The snapshot failed integrity validation checks. Please wait for the next automated refresh."
        f"{err_snippet}"
    )


def render_snapshot_unavailable() -> str:
    return render_snapshot_missing()


def render_health_card(
    telegram_status: str = "OK",
    snapshot_status: str = "READY",
    snapshot_age: str = "N/A",
    queue_status: str = "OK",
    worker_status: str = "RUNNING",
    active_jobs: int = 0,
) -> str:
    return (
        "🩺 *SCHEME-INTEL OPERATIONAL HEALTH*\n\n"
        f"• *Telegram Gateway:* `{telegram_status}`\n"
        f"• *Intelligence Snapshot:* `{snapshot_status}`\n"
        f"• *Snapshot Age:* `{snapshot_age}`\n"
        f"• *Research Queue:* `{queue_status}` ({active_jobs} pending/active)\n"
        f"• *Research Worker:* `{worker_status}`\n\n"
        f"_Health checked at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC_"
    )

