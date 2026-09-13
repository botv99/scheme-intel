"""
Trade recommendation engine for the consolidated GOBARdhan alert.

Combines technical analysis, volume signals, and catalyst scoring into
actionable trade recommendations with entry, exit, stop loss, target,
and suggested holding period. Generates a final Telegram digest message.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import SwingSetup
from .logger import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------
# Holding period heuristics based on ATR and trend
# ------------------------------------------------------------------

# ATR-based swing: wider stops = longer holding period
_SWING_DAYS = {
    "tight": (3, 7),    # ATR < 2% of price → quick scalp
    "normal": (5, 15),  # ATR 2-5% → standard swing
    "wide": (10, 25),   # ATR > 5% → longer swing
}


@dataclass
class TradeCall:
    """Complete trade recommendation for one stock."""
    company: str
    symbol: str
    action: str  # "BUY" | "WATCH" | "NO_SETUP"
    entry: float = 0.0
    exit_target: float = 0.0
    stop_loss: float = 0.0
    risk_reward: float = 0.0
    holding_days_min: int = 0
    holding_days_max: int = 0
    current_price: float = 0.0
    volume_signal: str = ""  # "BREAKOUT" | "ABOVE_AVG" | "NORMAL" | "LOW"
    volume_ratio: Optional[float] = None
    rsi: float = 0.0
    macd_signal: str = ""  # "BULLISH" | "BEARISH" | "NEUTRAL"
    weekly_trend: str = ""
    dma200_status: str = ""  # "ABOVE" | "BELOW" | "N/A"
    catalyst_score: int = 0
    rationale: str = ""
    technicals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "symbol": self.symbol,
            "action": self.action,
            "entry": self.entry,
            "exit_target": self.exit_target,
            "stop_loss": self.stop_loss,
            "risk_reward": self.risk_reward,
            "holding_days": f"{self.holding_days_min}-{self.holding_days_max}",
            "current_price": self.current_price,
            "volume_signal": self.volume_signal,
            "rsi": self.rsi,
            "macd_signal": self.macd_signal,
            "weekly_trend": self.weekly_trend,
            "dma200_status": self.dma200_status,
            "catalyst_score": self.catalyst_score,
            "rationale": self.rationale,
        }


# ------------------------------------------------------------------
# Technical indicator interpreters
# ------------------------------------------------------------------


def _interpret_volume(volume_ratio: Optional[float]) -> str:
    if volume_ratio is None:
        return "N/A"
    if volume_ratio >= 2.0:
        return "STRONG_BREAKOUT"
    if volume_ratio >= 1.5:
        return "BREAKOUT"
    if volume_ratio >= 1.2:
        return "ABOVE_AVG"
    if volume_ratio >= 0.8:
        return "NORMAL"
    return "LOW"


def _interpret_macd(macd: Optional[float], macd_signal: Optional[float],
                    macd_hist: Optional[float]) -> str:
    if macd_hist is None:
        return "N/A"
    if macd_hist > 0 and macd is not None and macd_signal is not None and macd > macd_signal:
        return "BULLISH"
    if macd_hist < 0:
        return "BEARISH"
    return "NEUTRAL"


def _interpret_dma200(price: float, dma200: Optional[float]) -> str:
    if dma200 is None:
        return "N/A"
    return "ABOVE" if price > dma200 else "BELOW"


def _holding_period(atr_pct: float, week_trend: str) -> tuple[int, int]:
    """Estimate holding period based on ATR % and weekly trend."""
    if atr_pct < 2.0:
        base_min, base_max = _SWING_DAYS["tight"]
    elif atr_pct < 5.0:
        base_min, base_max = _SWING_DAYS["normal"]
    else:
        base_min, base_max = _SWING_DAYS["wide"]

    # Adjust for trend strength
    if week_trend == "UP":
        base_max = int(base_max * 1.2)
    elif week_trend == "DOWN":
        base_min = max(2, int(base_min * 0.7))
        base_max = int(base_max * 0.7)

    return base_min, base_max


# ------------------------------------------------------------------
# Main recommendation logic
# ------------------------------------------------------------------


def evaluate_setup(setup: SwingSetup) -> TradeCall:
    """
    Convert a SwingSetup into a full TradeCall with entry/exit/holding period.

    Logic:
      - QUALIFIED setups → BUY recommendation with specific levels
      - WATCH setups → conditional recommendation (wait for trigger)
      - All setups → technical summary
    """
    price = setup.close
    entry = setup.entry
    stop = setup.stop
    target = setup.target

    # Risk / reward
    risk = entry - stop if entry > stop else 1.0
    reward = target - entry if target > entry else 0.0
    rr = round(reward / risk, 2) if risk > 0 else 0.0

    # Volume interpretation
    vol_signal = _interpret_volume(setup.volume_ratio)

    # MACD interpretation
    macd_sig = _interpret_macd(setup.macd, setup.macd_signal, setup.macd_hist)

    # DMA200 interpretation
    dma200_status = _interpret_dma200(price, setup.dma200)

    # ATR % for holding period
    atr_pct = ((entry - stop) / entry * 100) if entry > 0 else 3.0
    hold_min, hold_max = _holding_period(atr_pct, setup.week_trend or "")

    # Build rationale
    reasons = []
    if setup.breakout:
        reasons.append(f"20-day high breakout (prior high ₹{setup.prior_high20})")
    if vol_signal in ("BREAKOUT", "STRONG_BREAKOUT"):
        reasons.append(f"Volume {setup.volume_ratio}x avg confirms buying interest")
    if 50 <= setup.rsi14 <= 70:
        reasons.append(f"RSI {setup.rsi14} in healthy momentum zone")
    if macd_sig == "BULLISH":
        reasons.append("MACD bullish crossover")
    if setup.week_trend == "UP":
        reasons.append("Weekly uptrend confirmed")
    if dma200_status == "ABOVE":
        reasons.append("Price above 200-DMA (long-term bullish)")
    if setup.catalyst_score >= 80:
        reasons.append(f"Strong catalyst (score {setup.catalyst_score})")

    # Determine action
    if setup.status == "QUALIFIED":
        action = "BUY"
        rationale = " | ".join(reasons) if reasons else "All technical filters passed"
    else:
        action = "WATCH"
        blockers = []
        if not setup.breakout:
            blockers.append("no breakout yet")
        if setup.rsi14 > 70:
            blockers.append(f"RSI overbought ({setup.rsi14})")
        if setup.rsi14 < 50:
            blockers.append(f"RSI weak ({setup.rsi14})")
        if vol_signal == "LOW":
            blockers.append("low volume")
        if macd_sig == "BEARISH":
            blockers.append("MACD bearish")
        if setup.week_trend == "DOWN":
            blockers.append("weekly downtrend")
        if dma200_status == "BELOW":
            blockers.append("below 200-DMA")
        rationale = "Waiting for: " + (", ".join(blockers) if blockers else "catalyst confirmation")

    return TradeCall(
        company=setup.company,
        symbol=setup.symbol,
        action=action,
        entry=entry,
        exit_target=target,
        stop_loss=stop,
        risk_reward=rr,
        holding_days_min=hold_min,
        holding_days_max=hold_max,
        current_price=price,
        volume_signal=vol_signal,
        volume_ratio=setup.volume_ratio,
        rsi=setup.rsi14,
        macd_signal=macd_sig,
        weekly_trend=setup.week_trend or "N/A",
        dma200_status=dma200_status,
        catalyst_score=setup.catalyst_score,
        rationale=rationale,
        technicals={
            "sma20": round(float(price * 0.97), 2),  # approx
            "sma50": round(float(price * 0.93), 2),
            "prior_high20": setup.prior_high20,
            "volume_avg": setup.volume_avg,
            "volume_ratio": setup.volume_ratio,
            "macd": setup.macd,
            "macd_signal": setup.macd_signal,
            "macd_hist": setup.macd_hist,
        },
    )


# ------------------------------------------------------------------
# Telegram message formatting
# ------------------------------------------------------------------


def format_trade_call_telegram(call: TradeCall) -> str:
    """Format a single trade call as a Telegram HTML message."""
    if call.action == "NO_SETUP":
        return (
            f"📊 <b>{call.company}</b> ({call.symbol})\n"
            f"❌ <b>No swing setup</b> — scheme catalyst not detected.\n"
        )

    emoji = "🟢" if call.action == "BUY" else "🟡"
    action_label = "BUY SIGNAL" if call.action == "BUY" else "WATCH"

    lines = [
        f"{emoji} <b>{call.company}</b> ({call.symbol})",
        f"Action: <b>{action_label}</b>",
        "",
        f"💰 Current: ₹{call.current_price:,.2f}",
        f"🎯 Entry: ₹{call.entry:,.2f}",
        f"🛑 Stop Loss: ₹{call.stop_loss:,.2f}",
        f"📈 Target: ₹{call.exit_target:,.2f}",
        f"⚖️ Risk:Reward = 1:{call.risk_reward}",
        f"📅 Holding: {call.holding_days_min}-{call.holding_days_max} days",
        "",
        "<b>Technicals:</b>",
    ]

    # Volume
    vol_emoji = {"STRONG_BREAKOUT": "🔥", "BREAKOUT": "📈", "ABOVE_AVG": "📊",
                 "NORMAL": "📊", "LOW": "📉", "N/A": "—"}
    lines.append(f"  Volume: {vol_emoji.get(call.volume_signal, '')} {call.volume_signal}"
                 + (f" ({call.volume_ratio}x)" if call.volume_ratio else ""))

    # RSI
    rsi_emoji = "🟢" if 50 <= call.rsi <= 70 else "🔴"
    lines.append(f"  RSI(14): {rsi_emoji} {call.rsi}")

    # MACD
    macd_emoji = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "🟡", "N/A": "—"}
    lines.append(f"  MACD: {macd_emoji.get(call.macd_signal, '')} {call.macd_signal}")

    # Weekly trend
    week_emoji = {"UP": "🟢", "DOWN": "🔴", "NEUTRAL": "🟡", "N/A": "—"}
    lines.append(f"  Weekly: {week_emoji.get(call.weekly_trend, '')} {call.weekly_trend}")

    # DMA200
    dma_emoji = {"ABOVE": "🟢", "BELOW": "🔴", "N/A": "—"}
    lines.append(f"  200-DMA: {dma_emoji.get(call.dma200_status, '')} {call.dma200_status}")

    lines.append("")
    lines.append(f"<b>Reason:</b> {call.rationale}")

    return "\n".join(lines)


def format_final_digest_telegram(calls: list[TradeCall], catalysts_found: bool = True) -> str:
    """
    Format the final summary message that goes at the end of all stock alerts.

    This is the last message the user sees — summarizing all recommendations.
    """
    if not calls:
        return (
            "📋 <b>GOBARdhan Swing Setup Digest</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "❌ <b>No swing setup recommended.</b>\n\n"
            "No material catalysts detected for any watchlist stock.\n"
            "Next scan: tomorrow at 4:30 PM IST.\n\n"
            "⚠️ This is research, not investment advice."
        )

    buys = [c for c in calls if c.action == "BUY"]
    watches = [c for c in calls if c.action == "WATCH"]

    lines = [
        "📋 <b>GOBARdhan Swing Setup Digest</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if buys:
        lines.append(f"🟢 <b>{len(buys)} BUY signal(s):</b>")
        for c in buys:
            lines.append(
                f"  • <b>{c.company}</b>: Entry ₹{c.entry:,.2f} → "
                f"Target ₹{c.exit_target:,.2f} ({c.holding_days_min}-{c.holding_days_max}d)"
            )
        lines.append("")

    if watches:
        lines.append(f"🟡 <b>{len(watches)} WATCH (not yet triggered):</b>")
        for c in watches:
            lines.append(f"  • {c.company}: waiting for setup confirmation")
        lines.append("")

    if not buys and not watches:
        lines.append("❌ <b>No swing setup for any stock.</b>")
        lines.append("Scheme catalysts not triggering technical entries today.")
        lines.append("")

    # Top pick
    if buys:
        best = max(buys, key=lambda x: x.risk_reward)
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"⭐ <b>Best R:R pick: {best.company}</b>")
        lines.append(f"   Entry ₹{best.entry:,.2f} | SL ₹{best.stop_loss:,.2f} | "
                     f"Target ₹{best.exit_target:,.2f} | 1:{best.risk_reward}")
        lines.append("")

    lines.append("⚠️ Research only — not investment advice.")
    lines.append("Verify liquidity and position size before acting.")

    return "\n".join(lines)
