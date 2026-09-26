"""
Telegram Report Formatter for Stage 2.
Formats the complete 3-Section After-Market Intelligence Report:
SECTION 1: DAILY MARKET / SCHEME INTELLIGENCE (Every single watchlist stock)
SECTION 2: SWING SETUP RADAR (Candidate breakdown)
SECTION 3: FINAL ACTIONABLE SETUPS + WAITING SETUPS
"""
from __future__ import annotations

from typing import List, Dict, Optional
from .models import DailyStockCard, TradeSetup, CandidateSetup


def format_section1_daily_intelligence(
    session_title: str,
    cards: List[DailyStockCard],
    stats: Dict[str, int],
    health_stats: Optional[Dict[str, int]] = None,
) -> str:
    """
    SECTION 1: DAILY MARKET/SCHEME INTELLIGENCE
    Guarantees 100% full coverage across every watchlist stock.
    """
    total = len(cards)
    health = health_stats or {}
    total_health = health.get("total", total)
    valid_health = health.get("valid", sum(1 for c in cards if getattr(c, "data_status", "DATA_OK") == "DATA_OK" and c.price is not None))
    stale_health = health.get("stale", sum(1 for c in cards if getattr(c, "data_status", "") == "DATA_STALE"))
    unavail_health = health.get("unavailable", sum(1 for c in cards if getattr(c, "data_status", "") in ("DATA_UNAVAILABLE", "DATA_INSUFFICIENT") or c.price is None))

    lines = [
        f"📊 *SECTION 1: DAILY MARKET & SCHEME INTELLIGENCE*",
        f"*{session_title}*",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Global Market-Data Health Banner
    if total_health > 0 and unavail_health == total_health:
        lines.append("🚨 *MARKET DATA FAILURE*\n")
        lines.append(f"*{total_health}/{total_health} stocks have unavailable market data.*")
        lines.append("No technical setups or trade triggers generated.\n")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    elif unavail_health > 0 or stale_health > 0:
        lines.append(f"• *Market Data Health:* Valid: {valid_health}/{total_health} | Stale: {stale_health}/{total_health} | Unavailable: {unavail_health}/{total_health}")

    lines.extend([
        f"• *Watchlist scanned:* {total}",
        f"• *Catalysts found:* {stats.get('catalysts_found', 0)}",
        f"• *Swing candidates:* {stats.get('candidates', 0)}",
        f"• *Qualified setups:* {stats.get('qualified', 0)}",
        f"• *Waiting:* {stats.get('waiting', 0)}",
        f"• *No trade:* {stats.get('no_trade', 0)}",
        f"• *Data unavailable:* {stats.get('data_unavailable', unavail_health)}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
        f"📋 *ALL WATCHLIST STOCKS (100% COVERAGE):*",
    ])

    for card in cards:
        status_badge = f"`[{card.tomorrow_status}]`"
        lines.append(f"\n🏷️ *{card.stock.name}* (`{card.stock.symbol}`) {status_badge}")

        if card.tomorrow_status in ("DATA_UNAVAILABLE", "DATA_STALE", "DATA_INSUFFICIENT") or card.price is None:
            lines.append("• *Price:* —")
            lines.append("• *Volume:* —")
        else:
            chg_emoji = "🟢" if (card.day_change_pct or 0.0) >= 0 else "🔴"
            day_pct_str = f"{card.day_change_pct:+.2f}%" if card.day_change_pct is not None else "+0.00%"
            vol_str = f"{card.volume:,.0f}" if card.volume is not None else "0"
            vol_ratio_str = f"{card.volume_ratio:.1f}x" if card.volume_ratio is not None else "1.0x"
            vol_avg_str = f"{card.volume_avg_20d:,.0f}" if card.volume_avg_20d is not None else "0"
            lines.append(
                f"• *Price:* ₹{card.price:.2f} ({chg_emoji} {day_pct_str}) | "
                f"*Vol:* {vol_str} ({vol_ratio_str} of 20D {vol_avg_str})"
            )

        # News & Disclosures
        news_summary = card.developments[0] if card.developments else "No material disclosures."
        lines.append(f"• *News:* {news_summary}")

        # Catalyst & Strength
        cat_summary = card.catalysts[0] if card.catalysts else "Sector policy monitoring"
        lines.append(f"• *Catalyst:* {cat_summary} (Dir: {card.catalyst_direction}, Str: {card.catalyst_strength}/100)")

        # Technical State
        if card.tomorrow_status in ("DATA_UNAVAILABLE", "DATA_STALE", "DATA_INSUFFICIENT") or card.price is None:
            lines.append("• *Technicals:* Market data unavailable")
        else:
            sup_str = f"₹{card.support:.1f}" if card.support is not None else "N/A"
            res_str = f"₹{card.resistance:.1f}" if card.resistance is not None else "N/A"
            lines.append(
                f"• *Technicals:* Trend: {card.trend} | Support: {sup_str} | "
                f"Resistance: {res_str} | {card.technical_summary}"
            )
        lines.append(f"• *Status for Next Session:* *{card.tomorrow_status}*")
        lines.append("───────────────────────────")

    return "\n".join(lines)


def format_section2_radar(candidates: List[CandidateSetup]) -> str:
    """
    SECTION 2: SWING SETUP RADAR
    Displays only meaningful candidates that passed deterministic pre-filtering.
    """
    if not candidates:
        return (
            "🎯 *SECTION 2: SWING SETUP RADAR*\n\n"
            "_No stocks met the strict 5-archetype pre-filtering criteria in today's session._\n"
        )

    lines = [
        "🎯 *SECTION 2: SWING SETUP RADAR*",
        "_(Pre-filtered candidates based on 5 swing archetypes)_\n",
    ]

    for cand in candidates:
        tech = cand.technicals
        lines.append(f"⚡ *{cand.stock.name}* (`{cand.stock.symbol}`)")
        lines.append(f"• *Archetype:* *{cand.archetype}* (Score: *{cand.score}/100*)")
        lines.append(f"• *Setup Rationale:* {cand.rationale}")
        lines.append(f"• *RSI-14:* {tech.rsi14:.0f} | *Vol Ratio:* {tech.volume_ratio:.1f}x | *20 DMA:* ₹{tech.sma20:.1f}")
        if cand.catalysts:
            lines.append(f"• *Key Catalyst:* {cand.catalysts[0].catalyst_name[:70]}")
        lines.append("───────────────────────────")

    return "\n".join(lines)


def format_section3_actionable_and_waiting(setups: List[TradeSetup]) -> str:
    """
    SECTION 3: FINAL ACTIONABLE SETUPS + WAITING SETUPS
    Provides complete institutional trade execution plans for QUALIFIED_SETUP,
    actionable trigger blueprints for WAIT, and specific diagnostic reasons for NO_TRADE.
    """
    lines = [
        "⚖️ *SECTION 3: FINAL ACTIONABLE SETUPS & WAITING ENGINE*",
        "_(Dual-Agent Adjudication + Hard Risk Engine Veto)_\n",
    ]

    qualified = [s for s in setups if s.status == "QUALIFIED_SETUP"]
    waiting = [s for s in setups if s.status == "WAIT"]
    no_trade = [s for s in setups if s.status == "NO_TRADE"]
    data_unavailable = [s for s in setups if s.status in ("DATA_UNAVAILABLE", "DATA_STALE", "DATA_INSUFFICIENT")]

    # 1. QUALIFIED SETUPS
    if qualified:
        for s in qualified:
            stock = s.stock
            cand = s.candidate
            bull = s.bull_thesis
            bear = s.bear_thesis
            risk = s.risk
            tech = cand.technicals if cand else None

            lines.append("🚨 *QUALIFIED SETUP*")
            lines.append(f"*{stock.name.upper()}* (`{stock.symbol}`)")
            lines.append(f"*NEXT SESSION:* {s.next_trading_session}")
            lines.append(f"*Current Close:* ₹{tech.close:.2f}" if tech and tech.close > 0 else "*Current Close:* —")
            lines.append("")

            if risk:
                lines.append(f"*Entry Zone:* ₹{risk.entry_min:.2f}–{risk.entry_max:.2f}")
                lines.append(f"*Ideal Entry:* ₹{risk.ideal_entry:.2f}")
                if risk.max_acceptable_entry > 0:
                    lines.append(f"*Maximum Acceptable Entry:* ₹{risk.max_acceptable_entry:.2f} _(DO NOT ENTER ABOVE ₹{risk.max_acceptable_entry:.2f} — R:R falls below 1.5:1)_")
                lines.append(f"*Trigger:* {risk.trigger_condition}")
                lines.append(f"*Stop Loss:* ₹{risk.stop_loss:.2f} (Risk: ₹{risk.risk_per_share:.2f} / share, {(risk.risk_per_share/risk.ideal_entry)*100:.1f}%)")
                lines.append(f"*Target 1:* ₹{risk.target_1:.2f} (Reward: ₹{risk.reward_per_share:.2f} / share)")
                lines.append(f"*Target 2:* ₹{risk.target_2:.2f}")
                if risk.target_3:
                    lines.append(f"*Target 3 (Runner):* ₹{risk.target_3:.2f}")
                lines.append(f"*Expected Holding Period:* {risk.expected_holding_period}")
                lines.append(f"*R:R:* 1:{risk.risk_reward_ratio:.2f}")
                lines.append(f"  _({risk.rr_basis})_")
                lines.append(f"*Volume Requirement:* {risk.volume_to_watch}")

                # Position Sizing Breakdown
                lines.append(f"\n*Position Sizing & Risk Management (₹10 Lakh Trading Account):*")
                lines.append(f"• Share Quantity: *{risk.share_quantity} shares*")
                lines.append(f"• Capital Deployed: *₹{risk.capital_deployed:,.2f}* ({risk.position_size_pct:.1f}% of capital)")
                lines.append(f"• Risk per Trade: *{risk.max_portfolio_risk_pct:.1f}%* (₹{risk.maximum_loss_at_stop:,.2f} max loss if SL hit)")
                lines.append(f"• Actual Account Risk: *{risk.actual_risk_pct:.2f}%*")

            if cand and cand.catalysts:
                lines.append(f"\n*Catalyst:*\n{cand.catalysts[0].catalyst_name} ({cand.catalysts[0].beneficiary_type})")

            if tech:
                lines.append(f"\n*Technical Confirmation:*\nClose ₹{tech.close:.2f} holding above 20 DMA ₹{tech.sma20:.1f}, RSI {tech.rsi14:.0f}")

            if bull:
                lines.append(f"\n🐂 *Bull Case:*\n{bull.core_thesis}")
                if bull.technical_arguments:
                    lines.append(f"• {bull.technical_arguments[0]}")

            if bear:
                lines.append(f"\n🐻 *Bear Case:*\n{bear.core_thesis}")

            # Directionally Consistent Invalidation & Failure Rules
            if risk:
                lines.append(f"\n🛑 *Technical Invalidation:*\n{risk.technical_invalidation}")
                lines.append(f"\n⚠️ *Breakout Failure Condition:*\n{risk.breakout_failure_condition}")
            if s.ai_provider:
                lines.append(f"• *AI:* {s.ai_provider}")

            lines.append(f"\n*FINAL: QUALIFIED_SETUP*")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    else:
        lines.append("🚨 *QUALIFIED SETUPS:* None today. Strict risk parameters maintained.\n")

    # 2. WAITING SETUPS
    if waiting:
        lines.append("⏳ *WAITING SETUPS*\n")
        for s in waiting:
            stock = s.stock
            wc = s.wait_conditions
            lines.append(f"*{stock.name.upper()}* (`{stock.symbol}`)")
            if wc:
                lines.append(f"*Current Status:* {wc.current_status}")
                lines.append(f"*Why Not Ready:*\n{wc.why_not_ready}")
                lines.append(f"*Exact Price Confirmation:* {wc.exact_price_confirmation}")
                lines.append(f"*Exact Volume Confirmation:* {wc.exact_volume_confirmation}")
                lines.append(f"*Potential Entry:* {wc.potential_entry}")
                lines.append(f"*Technical Invalidation Floor:* {wc.technical_invalidation_floor}")
                lines.append(f"*Catalyst Condition:* {wc.catalyst_remaining_valid}")
            elif s.no_trade_reason:
                lines.append(f"*Why Not Ready:*\n{s.no_trade_reason}")
            if s.ai_provider:
                lines.append(f"• *AI:* {s.ai_provider}")
            lines.append(f"*FINAL: WAIT*")
            lines.append("───────────────────────────\n")

    # 3. NO TRADE
    if no_trade:
        lines.append("⚪ *NO TRADE*\n")
        for s in no_trade:
            reason = s.no_trade_reason or "Structurally weak trend or lack of catalyst"
            lines.append(f"• *{s.stock.name}* (`{s.stock.symbol}`): {reason}")
            lines.append(f"  *FINAL: NO_TRADE*")
        lines.append("───────────────────────────\n")

    # 4. DATA UNAVAILABLE / STALE
    if data_unavailable:
        lines.append("⚠️ *MARKET DATA UNAVAILABLE / STALE*\n")
        for s in data_unavailable:
            reason = s.no_trade_reason or "Market data unavailable or stale"
            lines.append(f"• *{s.stock.name}* (`{s.stock.symbol}`): {reason}")
            lines.append(f"  *FINAL: {s.status}*")
        lines.append("───────────────────────────\n")

    return "\n".join(lines)


def build_full_telegram_report(
    session_title: str,
    cards: List[DailyStockCard],
    candidates: List[CandidateSetup],
    setups: List[TradeSetup],
    health_stats: Optional[Dict[str, int]] = None,
) -> Dict[str, str]:
    """
    Build the complete 3-Section Telegram report payload.
    """
    qualified_count = sum(1 for s in setups if s.status == "QUALIFIED_SETUP")
    wait_count = sum(1 for s in setups if s.status == "WAIT")
    no_trade_count = sum(1 for s in setups if s.status == "NO_TRADE")
    data_unavail_count = sum(1 for s in setups if s.status in ("DATA_UNAVAILABLE", "DATA_STALE", "DATA_INSUFFICIENT"))
    cat_count = sum(1 for c in cards if c.catalysts and "Sector" not in c.catalysts[0])

    stats = {
        "catalysts_found": cat_count,
        "candidates": len(candidates),
        "qualified": qualified_count,
        "waiting": wait_count,
        "no_trade": no_trade_count,
        "data_unavailable": data_unavail_count,
    }

    sec1 = format_section1_daily_intelligence(session_title, cards, stats, health_stats=health_stats)
    sec2 = format_section2_radar(candidates)
    sec3 = format_section3_actionable_and_waiting(setups)

    full = f"{sec1}\n\n{sec2}\n\n{sec3}"
    return {
        "section1": sec1,
        "section2": sec2,
        "section3": sec3,
        "full_text": full,
    }
