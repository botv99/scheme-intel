"""
Deterministic Swing Candidate Generator for Stage 2.
Evaluates market technical snapshots and catalyst impacts against 5 defined swing archetypes:
1. Breakout
2. Breakout Anticipation
3. Pullback
4. Momentum Continuation
5. Event-Driven
"""
from __future__ import annotations

from typing import Optional, List, Dict, Tuple
from .models import Stock, TechnicalSnapshot, CatalystImpact, CandidateSetup
from ..logger import get_logger

logger = get_logger(__name__)

# Archetypes
ARCHETYPE_BREAKOUT = "Breakout"
ARCHETYPE_BREAKOUT_ANTICIPATION = "Breakout Anticipation"
ARCHETYPE_PULLBACK = "Pullback"
ARCHETYPE_MOMENTUM_CONTINUATION = "Momentum Continuation"
ARCHETYPE_EVENT_DRIVEN = "Event-Driven"


def evaluate_breakout(tech: TechnicalSnapshot, catalysts: List[CatalystImpact]) -> Tuple[int, str]:
    """
    Check Breakout:
    - Close near or above 20d/50d high (within 1% or breaking out).
    - Volume surge (volume_ratio >= 1.4).
    - RSI in momentum band (55 <= RSI <= 75).
    - Above key DMAs (close > sma20 and close > sma50).
    """
    score = 0
    reasons = []

    # Price breakout
    near_high = tech.high_20d > 0 and (tech.close >= tech.high_20d * 0.99)
    clearing_resistance = tech.resistance > 0 and (tech.close >= tech.resistance * 0.995)
    if near_high or clearing_resistance:
        score += 35
        reasons.append(f"Price breaking out near 20d high (₹{tech.high_20d:.1f})")

    # Volume expansion
    if tech.volume_ratio >= 1.8:
        score += 30
        reasons.append(f"Massive volume surge ({tech.volume_ratio:.1f}x 20d avg)")
    elif tech.volume_ratio >= 1.4:
        score += 20
        reasons.append(f"Strong volume expansion ({tech.volume_ratio:.1f}x 20d avg)")

    # Trend and RSI
    if tech.close > tech.sma20 and tech.close > tech.sma50:
        score += 15
        reasons.append("Trading above 20 & 50 DMA")
    if 55 <= tech.rsi14 <= 75:
        score += 10
        reasons.append(f"RSI {tech.rsi14:.0f} in bullish expansion range")

    # Catalysts
    high_cat = [c for c in catalysts if c.beneficiary_type in ("Direct", "Indirect") and c.strength >= 65]
    if high_cat:
        score += 10
        reasons.append(f"Backed by high-impact catalyst: {high_cat[0].catalyst_name[:40]}")

    return min(100, score), "; ".join(reasons)


def evaluate_breakout_anticipation(tech: TechnicalSnapshot, catalysts: List[CatalystImpact]) -> Tuple[int, str]:
    """
    Check Breakout Anticipation:
    - Price coiling right below resistance (1% to 3.5% below resistance).
    - Low/contracting volatility (volatility_regime == 'LOW' or narrow ATR).
    - Accumulation volume picking up (volume_ratio >= 1.1).
    - RSI 50 <= RSI <= 68.
    """
    score = 0
    reasons = []

    if tech.resistance > 0:
        dist_to_res = (tech.resistance - tech.close) / tech.resistance
        if 0.0 <= dist_to_res <= 0.035:
            score += 35
            reasons.append(f"Coiling {dist_to_res*100:.1f}% below resistance (₹{tech.resistance:.1f})")

    if tech.volatility_regime in ("LOW", "NORMAL") or tech.atr_pct < 3.0:
        score += 25
        reasons.append("Volatility compression / tight consolidation")

    if tech.volume_ratio >= 1.1:
        score += 15
        reasons.append(f"Steady accumulation volume ({tech.volume_ratio:.1f}x)")

    if 50 <= tech.rsi14 <= 68:
        score += 15
        reasons.append(f"RSI coiling at {tech.rsi14:.0f}")

    if tech.close > tech.sma20:
        score += 10
        reasons.append("Holding above 20 DMA")

    return min(100, score), "; ".join(reasons)


def evaluate_pullback(tech: TechnicalSnapshot, catalysts: List[CatalystImpact]) -> Tuple[int, str]:
    """
    Check Pullback:
    - Primary uptrend intact (close > sma50 and sma20 > sma50). Must be strictly present.
    - Pullback near 20 DMA or 50 DMA (within 2.5%).
    - Low volume on pullback (volume_ratio < 1.2 - orderly retreat).
    - RSI reset to 42 - 58 range.
    """
    uptrend = (tech.sma20 > tech.sma50 > 0) and (tech.close >= tech.sma50)
    if not uptrend:
        return 0, "No confirmed primary uptrend (requires 20 DMA > 50 DMA and Close >= 50 DMA)"

    score = 30
    reasons = ["Primary uptrend intact (20 DMA > 50 DMA)"]

    # Proximity to 20 DMA or 50 DMA
    near_20 = tech.sma20 > 0 and abs(tech.close - tech.sma20) / tech.sma20 <= 0.025
    near_50 = tech.sma50 > 0 and abs(tech.close - tech.sma50) / tech.sma50 <= 0.025
    if near_20:
        score += 25
        reasons.append(f"Testing 20 DMA support (₹{tech.sma20:.1f})")
    elif near_50:
        score += 20
        reasons.append(f"Testing 50 DMA support (₹{tech.sma50:.1f})")

    # Orderly volume
    if tech.volume_ratio <= 1.15:
        score += 20
        reasons.append(f"Low-volume orderly pullback ({tech.volume_ratio:.1f}x)")

    # RSI support reset
    if 40 <= tech.rsi14 <= 58:
        score += 15
        reasons.append(f"RSI cooled off to {tech.rsi14:.0f}")

    # Support level holding
    if tech.support > 0 and tech.close >= tech.support * 0.99:
        score += 10
        reasons.append(f"Respecting swing support ₹{tech.support:.1f}")

    return min(100, score), "; ".join(reasons)


def evaluate_momentum_continuation(tech: TechnicalSnapshot, catalysts: List[CatalystImpact]) -> Tuple[int, str]:
    """
    Check Momentum Continuation:
    - Strong recent run (20d performance >= 8%).
    - Close > 20 DMA > 50 DMA.
    - Positive Relative Strength vs NIFTY.
    - Healthy momentum RSI (55 <= RSI <= 72).
    """
    score = 0
    reasons = []

    if tech.performance_20d >= 8.0:
        score += 30
        reasons.append(f"Strong 20d momentum (+{tech.performance_20d:.1f}%)")

    if tech.close > tech.sma20 > tech.sma50 > 0:
        score += 25
        reasons.append("Bullish moving average alignment (Close > 20 > 50 DMA)")

    if tech.relative_strength_nifty and tech.relative_strength_nifty > 0:
        score += 20
        reasons.append(f"Outperforming benchmark by +{tech.relative_strength_nifty:.1f}%")

    if 55 <= tech.rsi14 <= 72:
        score += 15
        reasons.append(f"RSI steady at {tech.rsi14:.0f}")

    if tech.day_change_pct > 0 and tech.volume_ratio >= 1.0:
        score += 10
        reasons.append("Green session with sustained volume")

    return min(100, score), "; ".join(reasons)


def evaluate_event_driven(tech: TechnicalSnapshot, catalysts: List[CatalystImpact]) -> Tuple[int, str]:
    """
    Check Event-Driven:
    - High-materiality direct/indirect catalyst (strength >= 70).
    - Fresh news (is_fresh is True).
    - Not already priced in.
    - Technical structure not broken (close >= sma50).
    """
    score = 0
    reasons = []

    fresh_direct = [c for c in catalysts if c.beneficiary_type == "Direct" and c.strength >= 70 and c.is_fresh]
    fresh_indirect = [c for c in catalysts if c.beneficiary_type == "Indirect" and c.strength >= 65 and c.is_fresh]

    if fresh_direct:
        cat = fresh_direct[0]
        score += 45
        reasons.append(f"Direct high-certainty catalyst: {cat.catalyst_name[:45]}")
        if not cat.already_priced_in:
            score += 15
            reasons.append("Catalyst appears fresh & not fully priced in")
    elif fresh_indirect:
        cat = fresh_indirect[0]
        score += 30
        reasons.append(f"Indirect policy catalyst: {cat.catalyst_name[:45]}")

    if tech.volume_ratio >= 1.3:
        score += 20
        reasons.append(f"Institutions reacting with volume ({tech.volume_ratio:.1f}x)")

    if tech.close >= tech.sma50:
        score += 10
        reasons.append("Technical trend constructive (>= 50 DMA)")

    if tech.day_change_pct > 1.0:
        score += 10
        reasons.append(f"Positive price response (+{tech.day_change_pct:.1f}%)")

    return min(100, score), "; ".join(reasons)


def find_candidate_setup(
    stock: Stock,
    tech: Optional[TechnicalSnapshot],
    catalysts: List[CatalystImpact],
    min_score: int = 65,
) -> Optional[CandidateSetup]:
    """
    Evaluate all 5 archetypes for a given stock and select the highest-scoring archetype.
    Returns CandidateSetup if score >= min_score, otherwise None.
    """
    if not tech:
        return None

    # Don't evaluate setups if stock is broken (e.g. trading far below 200 DMA with heavy selling)
    if tech.sma200 and tech.close < tech.sma200 * 0.85 and tech.trend_status == "BEARISH":
        logger.debug("Skipping candidate for %s: structurally broken downtrend", stock.symbol)
        return None

    evaluators = [
        (ARCHETYPE_BREAKOUT, evaluate_breakout),
        (ARCHETYPE_BREAKOUT_ANTICIPATION, evaluate_breakout_anticipation),
        (ARCHETYPE_PULLBACK, evaluate_pullback),
        (ARCHETYPE_MOMENTUM_CONTINUATION, evaluate_momentum_continuation),
        (ARCHETYPE_EVENT_DRIVEN, evaluate_event_driven),
    ]

    best_archetype = None
    best_score = 0
    best_rationale = ""

    for archetype_name, eval_fn in evaluators:
        score, rationale = eval_fn(tech, catalysts)
        if score > best_score:
            best_score = score
            best_archetype = archetype_name
            best_rationale = rationale

    if best_score >= min_score and best_archetype:
        return CandidateSetup(
            stock=stock,
            archetype=best_archetype,
            score=best_score,
            rationale=best_rationale,
            technicals=tech,
            catalysts=catalysts,
        )

    return None
