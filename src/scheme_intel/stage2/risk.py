"""
Hard Risk Engine for Stage 2.
Non-overridable mathematical risk enforcement, trade sizing, and invalidation rules.
AI agents CANNOT override these quantitative rules.
"""
from __future__ import annotations

from typing import Optional, Tuple
from .models import CandidateSetup, BullThesis, TechnicalSnapshot, RiskAssessment
from ..logger import get_logger

logger = get_logger(__name__)

# Hard Risk Constraints (Configurable defaults)
MIN_RISK_REWARD_RATIO = 1.5
MAX_STOP_LOSS_PCT = 8.0  # Maximum allowable stop loss distance from entry
MIN_DAILY_VOLUME = 20_000  # Minimum share volume for swing liquidity
DEFAULT_PORTFOLIO_CAPITAL = 1_000_000.0  # ₹10 Lakhs standard trading capital
DEFAULT_PORTFOLIO_RISK_PCT = 1.0  # Max risk of total account on 1 trade (₹10,000)
MAX_POSITION_SIZE_PCT = 10.0  # Maximum capital allocated to 1 stock (10% = ₹100,000)


def evaluate_risk(
    candidate: CandidateSetup,
    bull_thesis: Optional[BullThesis] = None,
    min_rr: float = MIN_RISK_REWARD_RATIO,
    max_stop_pct: float = MAX_STOP_LOSS_PCT,
    min_volume: int = MIN_DAILY_VOLUME,
    portfolio_capital: float = DEFAULT_PORTFOLIO_CAPITAL,
    risk_per_trade_pct: float = DEFAULT_PORTFOLIO_RISK_PCT,
) -> RiskAssessment:
    """
    Enforce hard quantitative risk parameters:
    - Precise entry zones & tomorrow trigger condition
    - Non-negotiable stop loss below technical support / ATR
    - Mathematical targets (T1, T2, T3)
    - Strict Risk-to-Reward >= 1.5:1 with explicit calculation basis
    - Directionally consistent technical invalidation & breakout failure condition
    - Mathematically verified share quantity & rupee loss sizing
    """
    tech = candidate.technicals
    close = tech.close

    # 1. Determine Entry Zone and Tomorrow Trigger Condition
    if candidate.archetype == "Breakout":
        entry_min = round(close * 0.995, 2)
        entry_max = round(close * 1.015, 2)
        ideal_entry = close
        break_lvl = round(tech.resistance if tech.resistance > 0 else close * 1.008, 1)
        trigger_cond = f"Break above ₹{break_lvl} + volume >1.5x 20D average"
    elif candidate.archetype == "Breakout Anticipation":
        entry_min = round(close * 0.99, 2)
        entry_max = round(close * 1.005, 2)
        ideal_entry = close
        break_lvl = round(tech.resistance, 1)
        trigger_cond = f"Clean break and 15m candle close above ₹{break_lvl} on expanding volume"
    elif candidate.archetype == "Pullback":
        entry_min = round(tech.sma20 * 0.99 if tech.sma20 > 0 else close * 0.98, 2)
        entry_max = round(close * 1.005, 2)
        ideal_entry = round((entry_min + entry_max) / 2, 2)
        trigger_cond = f"Bullish price action rebound from ₹{entry_min}–₹{entry_max} zone with green candle close"
    else:
        entry_min = round(close * 0.99, 2)
        entry_max = round(close * 1.01, 2)
        ideal_entry = close
        trigger_cond = f"Follow-through above today's high ₹{tech.high:.1f} with volume confirmation"

    # 2. Determine Stop Loss Level
    atr_buffer = tech.atr14 * 0.75 if tech.atr14 > 0 else (ideal_entry * 0.02)
    potential_stops = []

    if tech.support > 0 and tech.support < ideal_entry:
        potential_stops.append(tech.support - (atr_buffer * 0.5))
    if tech.swing_low > 0 and tech.swing_low < ideal_entry:
        potential_stops.append(tech.swing_low - (atr_buffer * 0.5))
    if tech.sma20 > 0 and tech.sma20 < ideal_entry:
        potential_stops.append(tech.sma20 - (atr_buffer * 0.5))

    if potential_stops:
        stop_loss = round(max(potential_stops), 2)  # Highest valid support below entry
    else:
        stop_loss = round(ideal_entry - (atr_buffer * 1.5), 2)

    if stop_loss >= ideal_entry:
        stop_loss = round(ideal_entry * 0.95, 2)

    risk_per_share = round(ideal_entry - stop_loss, 2)
    risk_pct = round((risk_per_share / ideal_entry) * 100, 2)

    # Noise floor: minimum 1.5% stop distance
    if risk_pct < 1.5:
        stop_loss = round(ideal_entry * 0.975, 2)
        risk_per_share = round(ideal_entry - stop_loss, 2)
        risk_pct = round((risk_per_share / ideal_entry) * 100, 2)

    # 3. Determine Targets
    target_1 = round(ideal_entry + (risk_per_share * 1.8), 2)
    target_2 = round(ideal_entry + (risk_per_share * 2.8), 2)
    target_3 = round(ideal_entry + (risk_per_share * 4.2), 2)

    if bull_thesis and bull_thesis.expected_target > target_1:
        if bull_thesis.expected_target > target_2:
            target_3 = round(bull_thesis.expected_target, 2)
        else:
            target_2 = round(bull_thesis.expected_target, 2)

    reward_per_share = round(target_1 - ideal_entry, 2)
    rr_ratio = round(reward_per_share / risk_per_share, 2)

    # 4. Strict Calculation of Maximum Acceptable Entry Price
    # Formula: (Target1 - MaxEntry) / (MaxEntry - Stop) >= min_rr
    # => MaxEntry = (Target1 + min_rr * Stop) / (1 + min_rr)
    max_acceptable_entry = round((target_1 + (min_rr * stop_loss)) / (1.0 + min_rr), 2)

    # Cap the actionable entry zone so no displayed price violates the minimum R:R threshold!
    entry_max = min(entry_max, max_acceptable_entry)

    risk_at_max_entry = round(max_acceptable_entry - stop_loss, 2)
    reward_at_max_entry = round(target_1 - max_acceptable_entry, 2)
    rr_at_max = round(reward_at_max_entry / max(0.01, risk_at_max_entry), 2)

    rr_basis = (
        f"Ideal Entry ₹{ideal_entry:.2f} (Risk: ₹{risk_per_share:.2f}, Reward to T1: ₹{reward_per_share:.2f} -> R:R 1:{rr_ratio:.2f}). "
        f"Maximum Acceptable Entry: ₹{max_acceptable_entry:.2f} (R:R at ceiling: 1:{rr_at_max:.2f}). "
        f"DO NOT ENTER ABOVE ₹{max_acceptable_entry:.2f} because R:R falls below required {min_rr:.1f}:1."
    )

    # 4. Invalidation Logic (Directionally Consistent for Long Swing)
    technical_invalidation = f"Daily close below stop loss ₹{stop_loss:.2f}"
    if tech.sma20 > 0 and tech.sma20 > stop_loss:
        technical_invalidation += f" or decisive break below 20 DMA (₹{tech.sma20:.1f})"

    res_level = tech.resistance if tech.resistance > 0 else round(ideal_entry * 1.02, 1)
    breakout_failure_condition = (
        f"Fails to hold above breakout level ₹{res_level:.1f}; closes back below ₹{res_level:.1f} with intraday rejection"
    )

    # 5. Position Sizing & Capital Allocation
    max_rupee_risk = round(portfolio_capital * (risk_per_trade_pct / 100.0), 2)
    risk_shares_allowed = int(max_rupee_risk / risk_per_share) if risk_per_share > 0 else 0
    max_capital_allowed = round(portfolio_capital * (MAX_POSITION_SIZE_PCT / 100.0), 2)
    capital_shares_allowed = int(max_capital_allowed / ideal_entry) if ideal_entry > 0 else 0
    liquidity_shares_allowed = int(tech.volume * 0.02) if tech.volume > 0 else risk_shares_allowed

    share_quantity = max(1, min(risk_shares_allowed, capital_shares_allowed, liquidity_shares_allowed))
    capital_deployed = round(share_quantity * ideal_entry, 2)
    position_size_pct = round((capital_deployed / portfolio_capital) * 100.0, 1)
    maximum_loss_at_stop = round(share_quantity * risk_per_share, 2)
    actual_risk_pct = round((maximum_loss_at_stop / portfolio_capital) * 100.0, 2)

    # 6. Hard Veto Checks
    # Liquidity Veto
    if tech.volume > 0 and tech.volume < min_volume:
        return RiskAssessment(
            passed=False,
            veto_reason=f"Insufficient liquidity: today's volume ({tech.volume:,.0f}) is below minimum {min_volume:,} shares.",
            entry_min=entry_min,
            entry_max=entry_max,
            ideal_entry=ideal_entry,
            max_acceptable_entry=max_acceptable_entry,
            min_rr_at_max_entry=min_rr,
            trigger_condition="Volume threshold not met",
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            target_3=target_3,
            expected_holding_period="5–15 sessions",
            risk_reward_ratio=rr_ratio,
            rr_basis=rr_basis,
            risk_per_share=risk_per_share,
            reward_per_share=reward_per_share,
            technical_invalidation=technical_invalidation,
            breakout_failure_condition=breakout_failure_condition,
            share_quantity=share_quantity,
            capital_deployed=capital_deployed,
            position_size_pct=position_size_pct,
            maximum_loss_at_stop=maximum_loss_at_stop,
            actual_risk_pct=actual_risk_pct,
            volume_to_watch=f">{min_volume:,} shares",
            portfolio_capital=portfolio_capital,
            max_portfolio_risk_pct=risk_per_trade_pct,
        )

    # Maximum Stop Loss Veto
    if risk_pct > max_stop_pct:
        return RiskAssessment(
            passed=False,
            veto_reason=f"Stop loss distance ({risk_pct:.1f}%) exceeds maximum allowable risk limit of {max_stop_pct:.1f}%.",
            entry_min=entry_min,
            entry_max=entry_max,
            ideal_entry=ideal_entry,
            max_acceptable_entry=max_acceptable_entry,
            min_rr_at_max_entry=min_rr,
            trigger_condition=trigger_cond,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            target_3=target_3,
            expected_holding_period="5–15 sessions",
            risk_reward_ratio=rr_ratio,
            rr_basis=rr_basis,
            risk_per_share=risk_per_share,
            reward_per_share=reward_per_share,
            technical_invalidation=technical_invalidation,
            breakout_failure_condition=breakout_failure_condition,
            share_quantity=share_quantity,
            capital_deployed=capital_deployed,
            position_size_pct=position_size_pct,
            maximum_loss_at_stop=maximum_loss_at_stop,
            actual_risk_pct=actual_risk_pct,
            volume_to_watch=">1.5x 20D average",
            portfolio_capital=portfolio_capital,
            max_portfolio_risk_pct=risk_per_trade_pct,
        )

    # Minimum R:R Veto
    if rr_ratio < min_rr:
        return RiskAssessment(
            passed=False,
            veto_reason=f"Risk-to-reward ratio ({rr_ratio:.2f}:1) is below minimum required {min_rr:.1f}:1.",
            entry_min=entry_min,
            entry_max=entry_max,
            ideal_entry=ideal_entry,
            max_acceptable_entry=max_acceptable_entry,
            min_rr_at_max_entry=min_rr,
            trigger_condition=trigger_cond,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            target_3=target_3,
            expected_holding_period="5–15 sessions",
            risk_reward_ratio=rr_ratio,
            rr_basis=rr_basis,
            risk_per_share=risk_per_share,
            reward_per_share=reward_per_share,
            technical_invalidation=technical_invalidation,
            breakout_failure_condition=breakout_failure_condition,
            share_quantity=share_quantity,
            capital_deployed=capital_deployed,
            position_size_pct=position_size_pct,
            maximum_loss_at_stop=maximum_loss_at_stop,
            actual_risk_pct=actual_risk_pct,
            volume_to_watch=">1.5x 20D average",
            portfolio_capital=portfolio_capital,
            max_portfolio_risk_pct=risk_per_trade_pct,
        )

    # Inverted Entry Zone Veto
    if entry_max < entry_min:
        return RiskAssessment(
            passed=False,
            veto_reason=f"Entry zone inverted: maximum acceptable entry (₹{max_acceptable_entry:.2f}) for 1:{min_rr:.1f} R:R is below entry floor (₹{entry_min:.2f}).",
            entry_min=entry_min,
            entry_max=entry_max,
            ideal_entry=ideal_entry,
            max_acceptable_entry=max_acceptable_entry,
            min_rr_at_max_entry=min_rr,
            trigger_condition=trigger_cond,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            target_3=target_3,
            expected_holding_period="5–15 sessions",
            risk_reward_ratio=rr_ratio,
            rr_basis=rr_basis,
            risk_per_share=risk_per_share,
            reward_per_share=reward_per_share,
            technical_invalidation=technical_invalidation,
            breakout_failure_condition=breakout_failure_condition,
            share_quantity=share_quantity,
            capital_deployed=capital_deployed,
            position_size_pct=position_size_pct,
            maximum_loss_at_stop=maximum_loss_at_stop,
            actual_risk_pct=actual_risk_pct,
            volume_to_watch=">1.5x 20D average",
            portfolio_capital=portfolio_capital,
            max_portfolio_risk_pct=risk_per_trade_pct,
        )

    return RiskAssessment(
        passed=True,
        veto_reason=None,
        entry_min=entry_min,
        entry_max=entry_max,
        ideal_entry=ideal_entry,
        max_acceptable_entry=max_acceptable_entry,
        min_rr_at_max_entry=min_rr,
        trigger_condition=trigger_cond,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        target_3=target_3,
        expected_holding_period="5–15 sessions",
        risk_reward_ratio=rr_ratio,
        rr_basis=rr_basis,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
        technical_invalidation=technical_invalidation,
        breakout_failure_condition=breakout_failure_condition,
        share_quantity=share_quantity,
        capital_deployed=capital_deployed,
        position_size_pct=position_size_pct,
        maximum_loss_at_stop=maximum_loss_at_stop,
        actual_risk_pct=actual_risk_pct,
        volume_to_watch=">1.5x 20D average",
        portfolio_capital=portfolio_capital,
        max_portfolio_risk_pct=risk_per_trade_pct,
    )
