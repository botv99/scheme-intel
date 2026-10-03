"""
Prebuilt Answer Cards and Terminal Renderers for Telegram Conversational Interface.
Formats structured intelligence memory into clean, readable, factual Markdown terminal cards.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from .models import (
    CompanyIntelligence,
    SchemeIntelligence,
    PerformanceIntelligence,
    BenchmarkIntelligence,
    IntelligenceSnapshot,
)


def _stale_banner(is_stale: bool, updated_at: str) -> str:
    if is_stale:
        return f"⚠️ *DATA NOTE: Snapshot is >26h old (Last update: {updated_at[:16]}).*\n\n"
    return ""


def is_recent_news(item: Dict[str, Any], current_date: Optional[str | datetime] = None) -> bool:
    """
    Deterministic news date filter.
    Allowed: current day (diff=0), previous day (diff=1).
    Rejected: older than previous day (diff>1), future date (diff<0), missing/invalid publication date.
    """
    if not item or not isinstance(item, dict):
        return False

    raw_date = (
        item.get("date")
        or item.get("published_at")
        or item.get("published")
        or item.get("publishedAt")
        or item.get("timestamp")
        or item.get("datetime")
    )
    if not raw_date or not isinstance(raw_date, str):
        return False

    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw_date.strip())
    if not match:
        return False

    try:
        item_dt = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc).date()
    except (ValueError, OverflowError):
        return False

    if current_date is None:
        ref_dt = datetime.now(timezone.utc).date()
    elif isinstance(current_date, datetime):
        ref_dt = current_date.date()
    elif isinstance(current_date, str):
        ref_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", current_date.strip())
        if not ref_match:
            return False
        try:
            ref_dt = datetime(int(ref_match.group(1)), int(ref_match.group(2)), int(ref_match.group(3)), tzinfo=timezone.utc).date()
        except (ValueError, OverflowError):
            return False
    else:
        return False

    diff_days = (ref_dt - item_dt).days
    return diff_days in (0, 1)


def render_stock_card(comp: CompanyIntelligence, is_stale: bool = False, snapshot_id: Optional[str] = None) -> str:
    """Format concise Scheme-Intel Stock Intelligence Card with exact 9-section order."""
    banner = _stale_banner(is_stale, comp.updated_at)
    snapshot_date = comp.updated_at or datetime.now(timezone.utc).isoformat()

    # 1. STOCK IDENTITY
    lines = [
        f"{banner}🏷️ *{comp.symbol or comp.short_symbol}*",
        f"_{comp.name}_",
        "",
        f"*Scheme:* {comp.scheme_name or comp.scheme_id or 'GOBARdhan'}",
        f"*Relevance:* {comp.relevance or 'High'}",
        "",
        # 2. PRICE
        "*PRICE*",
        f"Current Price: {f'₹{comp.price:,.2f}' if comp.price is not None else 'N/A'}",
        f"Today's Change: {f'{comp.change_pct:+.2f}%' if comp.change_pct is not None else 'N/A'}",
        "",
        # 3. VOLUME
        "*VOLUME*",
        f"Volume: {f'{comp.volume:,}' if comp.volume is not None else 'N/A'}",
    ]

    volume_change_str = "N/A"
    if comp.volume is not None and comp.avg_volume is not None and comp.avg_volume > 0:
        v_change = ((comp.volume - comp.avg_volume) / comp.avg_volume) * 100
        volume_change_str = f"{v_change:+.1f}% vs 20D avg"
    lines.append(f"Volume Change: {volume_change_str}")

    # 4. FUNDAMENTAL SCORE
    lines.extend(["", "*FUNDAMENTAL SCORE*"])
    fund_val = comp.fundamental_intelligence_score if comp.fundamental_intelligence_score is not None else comp.fundamental_score
    if fund_val is not None:
        cov_str = f" | Coverage: {comp.fundamental_score_coverage:.0f}%" if comp.fundamental_score_coverage is not None else ""
        as_of = f" | As of: {comp.fundamental_score_data_as_of}" if comp.fundamental_score_data_as_of else ""
        lines.append(f"Fundamental Score: {fund_val:.1f}/10{cov_str}{as_of}")
        if comp.fundamental_score_components:
            breakdown_parts = []
            for k in ("growth", "profitability", "balance_sheet", "cash_flow"):
                c_data = comp.fundamental_score_components.get(k)
                if isinstance(c_data, dict) and c_data.get("score") is not None:
                    breakdown_parts.append(f"{k.replace('_', ' ').title()}: {c_data['score']:.1f}")
            if breakdown_parts:
                lines.append("• " + " | ".join(breakdown_parts))
    else:
        lines.append("Fundamental Score: N/A\nReason: Fundamental scoring not available in current snapshot.")

    # 5. TECHNICAL / INTELLIGENCE SCORE
    lines.extend(["", "*TECHNICAL INTELLIGENCE*"])
    tech_val = comp.technical_intelligence_score if comp.technical_intelligence_score is not None else (comp.score / 10.0 if comp.score is not None else None)
    if tech_val is not None:
        cov_str = f" | Coverage: {comp.technical_score_coverage:.0f}%" if comp.technical_score_coverage is not None else ""
        as_of = f" | As of: {comp.technical_score_data_as_of}" if comp.technical_score_data_as_of else ""
        lines.append(f"Technical / Intel Score: {tech_val:.1f}/10{cov_str}{as_of}")
        if comp.technical_score_components:
            breakdown_parts = []
            for k in ("trend", "momentum", "structure", "volume"):
                c_data = comp.technical_score_components.get(k)
                if isinstance(c_data, dict) and c_data.get("score") is not None:
                    breakdown_parts.append(f"{k.capitalize()}: {c_data['score']:.1f}")
            if breakdown_parts:
                lines.append("• " + " | ".join(breakdown_parts))
    else:
        lines.append("Technical / Intel Score: N/A")

    # 6. TODAY'S CATALYST
    lines.extend(["", "*TODAY'S CATALYST*"])
    catalyst_rendered = False
    if comp.catalysts:
        for c in comp.catalysts:
            lines.append(f"• {c}")
        catalyst_rendered = True
    elif comp.catalyst:
        lines.append(f"• {comp.catalyst}")
        catalyst_rendered = True
    elif comp.latest_development and comp.status != "NO_TRADE":
        lines.append(f"• {comp.latest_development}")
        catalyst_rendered = True

    if not catalyst_rendered:
        lines.append("No major catalyst detected in the latest scan.")

    # 7. NEWS
    lines.extend(["", "*NEWS*"])
    all_news = comp.evidence or []
    recent_news = [item for item in all_news if is_recent_news(item, snapshot_date)][:5]
    if recent_news:
        for n in recent_news:
            headline = n.get("title") or n.get("headline") or "News Update"
            source = f" — _{n['source']}_" if n.get("source") else ""
            link = f"\n  {n['url']}" if n.get("url") else ""
            lines.append(f"• {headline}{source}{link}")
    else:
        lines.append("No relevant news from today/yesterday.")

    # 8. TRADE SETUP STATUS
    lines.extend(["", "*TRADE SETUP*", f"Status: `{comp.status or 'NO_TRADE'}`"])
    if comp.status in ("QUALIFIED_SETUP", "WAIT"):
        if comp.archetype:
            lines.append(f"• Archetype: {comp.archetype}")
        if comp.score is not None:
            lines.append(f"• Score: {comp.score}/100")
        if comp.trigger_price is not None:
            lines.append(f"• Trigger: ₹{comp.trigger_price:,.2f}")
        if comp.stop_loss is not None:
            lines.append(f"• Stop Loss: ₹{comp.stop_loss:,.2f}")
        if comp.target is not None:
            lines.append(f"• Target: ₹{comp.target:,.2f}")

    # 9. DATA TIMESTAMP
    updated_str = comp.updated_at[:16].replace("T", " ") + " UTC" if comp.updated_at else "N/A"
    snap_id = snapshot_id or "N/A"
    status_str = "⚠️ STALE (>26h)" if is_stale else "🟢 FRESH"
    lines.extend([
        "",
        "---",
        f"• Updated: {updated_str}",
        f"• Snapshot: `{snap_id}`",
        f"• Data Status: {status_str}",
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


def is_valid_qualified_setup(comp: Any) -> bool:
    """Validate that a qualified setup has real, non-null, valid numeric trading fields."""
    if not comp:
        return False
    sym = (getattr(comp, "symbol", "") or getattr(comp, "short_symbol", "") or "").strip()
    if not sym or sym.lower() in ("undefined", "null", "none"):
        return False
    arch = (getattr(comp, "archetype", "") or "").strip()
    if not arch or str(arch).lower() in ("undefined", "null", "none"):
        return False
    for attr in ("trigger_price", "stop_loss", "target", "score"):
        val = getattr(comp, attr, None)
        if val is None:
            return False
        if not isinstance(val, (int, float)):
            return False
        if math.isnan(val) or math.isinf(val):
            return False
    return True


def render_setups_card(setups: List[CompanyIntelligence], is_stale: bool = False, updated_str: str = "") -> str:
    """Format qualified setups list."""
    banner = _stale_banner(is_stale, updated_str)
    valid_setups = [s for s in (setups or []) if is_valid_qualified_setup(s)]
    if not valid_setups:
        return f"{banner}🎯 *CURRENT SETUPS*\n\nNo qualified setups in the latest completed intelligence cycle.\n\nAll watchlist candidates either failed quantitative risk filters or are in waiting conditions."

    lines = [
        f"{banner}🎯 *CURRENT QUALIFIED SETUPS*",
        f"Found {len(valid_setups)} actionable setups from latest cycle:\n",
    ]
    for i, s in enumerate(valid_setups, 1):
        trig = f"₹{s.trigger_price:.2f}"
        sl = f"₹{s.stop_loss:.2f}"
        t1 = f"₹{s.target:.2f}"
        score_val = f"{s.score:.0f}" if isinstance(s.score, float) and s.score.is_integer() else f"{s.score}"
        lines.append(
            f"*{i}. {s.short_symbol or s.symbol.split('.')[0]}* ({s.name})\n"
            f"   • Archetype: {s.archetype or 'Swing'}\n"
            f"   • Score: {score_val}/100\n"
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
        "• `/stock <symbol>` — Full intelligence card (e.g. `/stock GAIL`)\n"
        "• `/setups` — Current qualified setups\n"
        "• `/watchlist` — Monitored scheme watchlist\n"
        "• `/help` — Command guide\n\n"
        "*DEEP ASYNC RESEARCH*\n"
        "• `/research <question>` — Queue deep investigation\n\n"
        "_Fast commands retrieve precalculated memory. Research runs asynchronously._"
    )


def render_start_card() -> str:
    """Format concise terminal-style start menu."""
    return (
        "🤖 *SCHEME-INTEL TERMINAL*\n\n"
        "📊 *Intelligence Terminal*\n\n"
        "*Quick Commands:*\n"
        "• `/schemes` — Select and switch intelligence scheme\n"
        "• `/stock <symbol>` — Full stock intelligence card\n"
        "• `/setups` — Current qualified setups\n"
        "• `/watchlist` — Monitored companies\n"
        "• `/help` — Command guide\n\n"
        "*Deep Research:*\n"
        "• `/research <question>` — Deep async investigation"
    )


def render_stock_prompt_card(command: str = "/stock") -> str:
    """Format prompt when /stock or shortcut is called without a stock symbol."""
    return (
        "Which stock?\n\n"
        "Usage: `/stock <symbol>`\n"
        "Try:\n"
        "TRUALT\n"
        "PRAJ\n"
        "WABAG\n"
        "GAIL\n"
        "IOC\n\n"
        "Use /watchlist to see monitored companies."
    )


def render_watchlist_card(
    companies: Dict[str, CompanyIntelligence] | List[CompanyIntelligence],
    is_stale: bool = False,
    scheme_name: Optional[str] = None,
    scheme_id: Optional[str] = None,
) -> str:
    """Format watchlist overview card."""
    header_name = (scheme_name or "GOBARdhan").split("(")[0].strip().upper()
    lines = [
        f"📋 *{header_name} SCHEME WATCHLIST*",
        "",
    ]
    seen = set()
    items = list(companies.values()) if isinstance(companies, dict) else list(companies)
    if scheme_id:
        norm_sid = scheme_id.strip().lower()
        items = [c for c in items if (getattr(c, "scheme_id", None) or "").lower() in (norm_sid, "")]
    if not items:
        lines.append("No watchlist companies are currently configured for this scheme.")
        return "\n".join(lines)

    for comp in items:
        sym = comp.symbol or comp.short_symbol or ""
        base = sym.split(".")[0].upper()
        if not base or base in seen:
            continue
        seen.add(base)
        price_str = f"₹{comp.price:,.2f}" if comp.price is not None else "N/A"
        status_str = f"`{comp.status}`" if comp.status else "`WATCH`"
        lines.append(f"• *{base}* ({comp.name}) — {price_str} | {status_str}")

    sample_stock = "ONGC" if "samudra" in (scheme_name or "").lower() else "GAIL"
    lines.extend([
        "",
        f"Use `/stock <symbol>` (e.g. `/stock {sample_stock}`) to view full intelligence.",
    ])
    return "\n".join(lines)


def render_scheme_header_menu(scheme_cfg: Any, switched: bool = False) -> str:
    """Format post-selection scheme dashboard menu card with emoji, name, and focus."""
    sid = getattr(scheme_cfg, "id", getattr(scheme_cfg, "scheme_id", ""))
    sname = getattr(scheme_cfg, "name", sid)
    sfocus = getattr(scheme_cfg, "focus", "")
    sdesc = getattr(scheme_cfg, "description", "")

    emoji = "🌊" if "samudra" in sid.lower() else "🌱" if "gobar" in sid.lower() else "🏛️"

    lines = []
    if switched:
        lines.extend([
            "🔄 *Active Scheme Switched*",
            "",
        ])
    lines.append(f"{emoji} *{sname.upper()}*")
    if sfocus:
        lines.append(f"*Focus:* {sfocus}")
    if sdesc:
        lines.append(f"_{sdesc}_")
    lines.extend([
        "",
        "Select an intelligence action below:",
    ])
    return "\n".join(lines)


def get_scheme_inline_keyboard(scheme_id: str) -> Dict[str, Any]:
    """Generate structured interactive inline keyboard for the active scheme's menu."""
    return {
        "inline_keyboard": [
            [
                {"text": "📋 WATCHLIST", "callback_data": f"scheme_action:watchlist:{scheme_id}"},
                {"text": "📈 TRADES", "callback_data": f"scheme_action:trades:{scheme_id}"},
            ],
            [
                {"text": "🧠 RESEARCH", "callback_data": f"scheme_action:research:{scheme_id}"},
                {"text": "📰 INTELLIGENCE", "callback_data": f"scheme_action:intelligence:{scheme_id}"},
            ],
            [
                {"text": "📊 SNAPSHOT", "callback_data": f"scheme_action:snapshot:{scheme_id}"},
                {"text": "🔄 SWITCH SCHEME", "callback_data": "scheme_action:switch_scheme"},
            ],
        ]
    }


def render_schemes_select_menu(licensed_schemes: List[Any]) -> str:
    """Format scheme selector prompt listing authorized schemes."""
    lines = [
        "📊 *SCHEMES — SUPPORTED POLICY SCHEMES*",
        "",
        "*Select Scheme*",
        "Choose an authorized scheme below to activate:",
        "",
    ]
    for s in licensed_schemes:
        sid = getattr(s, "id", getattr(s, "scheme_id", ""))
        name = getattr(s, "name", sid)
        emoji = "🌊" if "samudra" in sid.lower() else "🌱" if "gobar" in sid.lower() else "🏛️"
        lines.append(f"• {emoji} *{name}* (`{sid}`)")
    lines.extend([
        "",
        "Tap a scheme button below or type `/switch <scheme_id>`:",
    ])
    return "\n".join(lines)


def get_schemes_inline_keyboard(licensed_schemes: List[Any]) -> Dict[str, Any]:
    """Generate keyboard containing only schemes the user is entitled to."""
    keyboard: List[List[Dict[str, str]]] = []
    for s in licensed_schemes:
        sid = getattr(s, "id", getattr(s, "scheme_id", ""))
        raw_name = getattr(s, "name", sid)
        display_name = raw_name.split("(")[0].strip()
        emoji = "🌊 " if "samudra" in sid.lower() else "🌱 " if "gobar" in sid.lower() else "🏛️ "
        keyboard.append([
            {"text": f"{emoji}{display_name}", "callback_data": f"scheme_select:{sid}"}
        ])
    return {"inline_keyboard": keyboard}


def get_back_and_switch_inline_keyboard(scheme_id: Optional[str] = None) -> Dict[str, Any]:
    """Generate Back & Switch Scheme navigation buttons."""
    back_cb = f"scheme_action:menu:{scheme_id}" if scheme_id else "scheme_action:menu"
    return {
        "inline_keyboard": [
            [
                {"text": "⬅️ Back", "callback_data": back_cb},
                {"text": "🔄 Switch Scheme", "callback_data": "scheme_action:switch_scheme"},
            ]
        ]
    }


def render_intelligence_card(
    scheme_id: str,
    snapshot: Optional[IntelligenceSnapshot] = None,
    scheme_cfg: Optional[Any] = None,
) -> str:
    """Render latest scheme intelligence, news, and developments."""
    name = (getattr(scheme_cfg, "name", None) or scheme_id).upper()
    lines = [
        f"📰 *{name} INTELLIGENCE*",
        "",
    ]
    if snapshot and scheme_id in snapshot.schemes:
        s_intel = snapshot.schemes[scheme_id]
        if s_intel.key_developments:
            lines.append("*Key Developments:*")
            for kd in s_intel.key_developments[:5]:
                lines.append(f"• {kd}")
            lines.append("")
        if s_intel.important_sources:
            lines.append(f"*Sources:* {', '.join(s_intel.important_sources[:4])}")
            lines.append("")
        if s_intel.last_update:
            lines.append(f"_Updated: {s_intel.last_update[:16]} UTC_")
    elif scheme_cfg:
        lines.append(f"_{scheme_cfg.description}_")
        lines.append("")
        if scheme_cfg.sources:
            lines.append(f"*Sources Monitored:* {len(scheme_cfg.sources)} official & industry feeds")
    else:
        lines.append("No recent intelligence reports available for this scheme.")
    return "\n".join(lines).strip()


def render_research_prompt_card(scheme_cfg: Optional[Any] = None, scheme_id: Optional[str] = None) -> str:
    """Render instructional card for asynchronous research queries."""
    raw_name = getattr(scheme_cfg, "name", scheme_id or "Scheme")
    sname = raw_name.split("(")[0].strip()
    sfocus = getattr(scheme_cfg, "focus", "")
    lines = [
        f"🧠 *{sname.upper()} RESEARCH*",
        "",
    ]
    if sfocus:
        lines.extend([f"*Context:* {sfocus}", ""])
    lines.extend([
        "To run deep asynchronous research on this scheme, send:",
        "`/research <your question>`",
        "",
        "*Examples:*",
    ])
    if "samudra" in (scheme_id or getattr(scheme_cfg, "id", "")).lower():
        lines.extend([
            "• `/research What are the latest deepwater drilling contract updates?`",
            "• `/research Analyze ONGC KG-Basin offshore ultra-deepwater catalysts`",
        ])
    else:
        lines.extend([
            "• `/research What changed in Gobardhan CBG policy this month?`",
            "• `/research Compare SATAT procurement pricing vs natural gas`",
        ])
    return "\n".join(lines)


def get_terminal_inline_keyboard(active_scheme: Optional[str] = None) -> Dict[str, Any]:
    """Generate structured interactive inline keyboard buttons for Telegram."""
    sid = (active_scheme or "gobardhan").strip().lower()
    return {
        "inline_keyboard": [
            [
                {"text": "📊 SCHEMES", "callback_data": "/schemes"},
            ],
            [
                {"text": "📋 WATCHLIST", "callback_data": f"scheme_action:watchlist:{sid}"},
                {"text": "📈 TRADES", "callback_data": f"scheme_action:trades:{sid}"},
            ],
            [
                {"text": "🧠 RESEARCH", "callback_data": f"scheme_action:research:{sid}"},
                {"text": "📰 INTELLIGENCE", "callback_data": f"scheme_action:intelligence:{sid}"},
            ],
            [
                {"text": "❓ HELP", "callback_data": "/help"},
            ],
        ]
    }


def render_unknown_stock(symbol: str, scheme_id: Optional[str] = None) -> str:
    scheme_label = f"the active {scheme_id.replace('_', ' ').title()}" if scheme_id else "the active Scheme-Intel"
    return (
        "🏷️ *Stock Not Found*\n\n"
        f"I don't recognize `{symbol.upper()}` in {scheme_label} watchlist.\n\n"
        f"`{symbol.upper()}` is not currently in {scheme_label} research universe / watchlist.\n\n"
        "Use /watchlist or /schemes to see monitored companies."
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


