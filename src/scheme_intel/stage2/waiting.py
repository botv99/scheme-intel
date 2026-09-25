"""
Setup Waiting Engine for Stage 2.
Transforms unready or non-qualifying setups into actionable future trigger conditions.
Never outputs a passive 'NO TRADE'; always defines 'What we are waiting for'.
"""
from __future__ import annotations

from typing import Optional, List
from .models import Stock, TechnicalSnapshot, CandidateSetup, BearThesis, RiskAssessment, WaitCondition
from ..logger import get_logger

logger = get_logger(__name__)


def generate_wait_condition(
    stock: Stock,
    snapshot: Optional[TechnicalSnapshot],
    candidate: Optional[CandidateSetup] = None,
    bear_thesis: Optional[BearThesis] = None,
    risk: Optional[RiskAssessment] = None,
) -> WaitCondition:
    """
    Construct a precise WaitCondition specifying what concrete triggers
    would turn this stock into a qualified swing trade.
    Requires a valid TechnicalSnapshot with positive price.
    """
    if snapshot is None or snapshot.close <= 0:
        raise ValueError(
            f"Cannot generate wait condition for {stock.symbol}: missing or non-positive price snapshot."
        )

    price = snapshot.close
    support = snapshot.support
    resistance = snapshot.resistance

    confirmations: List[str] = []
    trigger_price = round(resistance if resistance > 0 else price * 1.02, 1)
    vol_trigger = ">1.4x 20D average"

    # 1. Diagnose Why Not Ready & Extract Confirmations
    if risk and not risk.passed:
        why_not_ready = f"Risk engine veto: {risk.veto_reason}"
        if "Stop loss distance" in (risk.veto_reason or ""):
            confirmations.append(f"Wait for price pullback closer to support ₹{support:.1f} to narrow stop loss risk.")
            trigger_price = support
        elif "liquidity" in (risk.veto_reason or "").lower():
            confirmations.append("Wait for daily traded volume to exceed 20,000 shares.")
            vol_trigger = ">20,000 shares"
        else:
            confirmations.append("Wait for favorable entry price that yields R:R >= 1.5:1.")
    elif bear_thesis and bear_thesis.required_confirmation_to_buy:
        why_not_ready = f"Bear vulnerability: {bear_thesis.core_thesis[:90]}"
        confirmations.append(bear_thesis.required_confirmation_to_buy)
        if bear_thesis.what_would_invalidate_bear:
            confirmations.append(f"Bear invalidation signal: {bear_thesis.what_would_invalidate_bear}")
    elif candidate and candidate.archetype == "Breakout Anticipation":
        dist_pct = ((resistance - price) / resistance) * 100 if resistance > 0 else 0.0
        why_not_ready = f"Stock is consolidating tightly {dist_pct:.1f}% below resistance ₹{resistance:.1f}."
        confirmations.append(f"Daily close above ₹{resistance:.1f} with volume >1.5x 20D average.")
        confirmations.append("Confirm hold above breakout level without intraday rejection wick.")
        trigger_price = resistance
        vol_trigger = ">1.5x 20D average"
    elif candidate and candidate.archetype == "Pullback":
        sma20 = snapshot.sma20 if snapshot else price
        why_not_ready = f"Pullback underway; waiting for confirmation of support hold near 20 DMA (₹{sma20:.1f})."
        confirmations.append(f"Bullish reversal candle (hammer / engulfing) at 20 DMA ₹{sma20:.1f}.")
        confirmations.append("Volume contraction on dip followed by volume pickup on green close.")
        trigger_price = round(sma20 * 1.01, 1)
        vol_trigger = "Volume pickup on green close"
    elif snapshot and snapshot.trend_status == "BEARISH":
        why_not_ready = f"Stock is in a corrective phase below 50 DMA (₹{snapshot.sma50:.1f})."
        confirmations.append(f"Reclaim and close above 50 DMA (₹{snapshot.sma50:.1f}).")
        confirmations.append("RSI-14 crossing back above 50 with higher lows structure.")
        trigger_price = snapshot.sma50
    else:
        why_not_ready = "Lacks decisive breakout momentum or institutional volume surge."
        if resistance > 0:
            confirmations.append(f"Decisive breakout and close above resistance ₹{resistance:.1f}.")
            trigger_price = resistance
        confirmations.append("Institutional volume expansion (>1.4x 20D average volume).")

    # Determine potential entry and invalidation floor
    if resistance > 0:
        potential_entry = f"₹{resistance * 1.005:.1f} - ₹{resistance * 1.015:.1f} (on breakout) or ₹{support:.1f} (on dip)"
    else:
        potential_entry = f"₹{price * 1.01:.1f} (on confirmation)"

    invalidation_level = support if support > 0 else round(price * 0.94, 1)
    invalidation_floor = f"Daily close below ₹{invalidation_level:.1f}"

    exact_price_conf = f"Daily close above ₹{trigger_price:.1f}"

    return WaitCondition(
        symbol=stock.symbol,
        current_price=price,
        current_status="WAIT",
        why_not_ready=why_not_ready,
        exact_price_confirmation=exact_price_conf,
        exact_volume_confirmation=vol_trigger,
        exact_confirmation_required=confirmations,
        trigger_price=trigger_price,
        volume_trigger=vol_trigger,
        invalidation_level=invalidation_level,
        technical_invalidation_floor=invalidation_floor,
        catalyst_remaining_valid="Active policy scheme tailwind",
        potential_entry=potential_entry,
    )
