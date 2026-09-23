"""
Catalyst Impact Relevance Scoring Engine for Stage 2.
Maps news, policy schemes, and corporate developments to stock-level impact.
"""
from __future__ import annotations

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from .models import Stock, NewsItem, CatalystImpact, TechnicalSnapshot
from ..logger import get_logger

logger = get_logger(__name__)

# Keywords for beneficiary classification
DIRECT_KEYWORDS = [
    "awarded", "secures order", "won contract", "bags order", "wins tender",
    "loi received", "commissioned", "partnership with", "jv with", "acquires",
    "received approval", "fda approval", "patent granted", "selected for pli"
]

NEGATIVE_KEYWORDS = [
    "penalty", "fine", "fraud", "investigation", "raids", "ban", "restriction",
    "duty hike", "tax hike", "windfall tax", "downgrade", "cancelled",
    "rejected", "loss widened", "curb", "probe", "default"
]

INDIRECT_KEYWORDS = [
    "cabinet approves", "pli scheme", "budget allocation", "tariff cut",
    "import duty hike", "government pushes", "incentive", "sector outlook",
    "policy framework", "subsidies announced", "guidelines issued"
]

HIGH_CERTAINTY_SOURCES = [
    "PIB", "Gazette of India", "BSE", "NSE", "Cabinet", "Ministry", "SEBI", "RBI"
]


def score_catalyst_impact(
    news: NewsItem,
    stock: Stock,
    snapshot: Optional[TechnicalSnapshot] = None
) -> CatalystImpact:
    """
    Score the impact of a news/catalyst item on a given stock.
    Determines beneficiary type, strength (0-100), duration, certainty, freshness,
    and whether it is already priced in based on technical snapshot.
    """
    title_lower = news.title.lower()
    summary_lower = news.summary.lower()
    full_text = f"{title_lower} {summary_lower}"

    # 1. Beneficiary Type
    # Check if stock explicitly mentioned
    symbol_match = stock.symbol.lower() in full_text
    name_match = stock.name.lower() in full_text
    alias_match = any(a.lower() in full_text for a in stock.aliases)
    directly_named = symbol_match or name_match or alias_match or (stock.name in news.companies_mentioned)

    is_negative = any(neg in full_text for neg in NEGATIVE_KEYWORDS) or news.sentiment == "negative"
    is_direct_action = any(dk in full_text for dk in DIRECT_KEYWORDS)

    if is_negative and directly_named:
        beneficiary_type = "Negative"
    elif directly_named and is_direct_action:
        beneficiary_type = "Direct"
    elif directly_named:
        beneficiary_type = "Direct" if news.sentiment == "positive" else ("Negative" if is_negative else "Neutral")
    elif any(ik in full_text for ik in INDIRECT_KEYWORDS) or any(s.lower() in full_text for s in stock.sectors):
        beneficiary_type = "Negative" if is_negative else "Indirect"
    else:
        beneficiary_type = "Neutral"

    # 2. Certainty based on Source Tier & Authority
    source_name = news.source
    if news.source_tier == 1 or any(auth.lower() in source_name.lower() for auth in HIGH_CERTAINTY_SOURCES):
        certainty = "High"
    elif news.source_tier == 2:
        certainty = "High"
    elif news.source_tier == 3:
        certainty = "Medium"
    else:
        certainty = "Low"

    # 3. Strength (0-100)
    base_strength = news.materiality
    if beneficiary_type == "Direct":
        strength = min(100, int(base_strength * 1.15))
    elif beneficiary_type == "Indirect":
        strength = int(base_strength * 0.85)
    elif beneficiary_type == "Negative":
        strength = min(100, int(base_strength * 1.20))
    else:
        strength = int(base_strength * 0.50)

    # Boost strength if source tier is 1
    if certainty == "High":
        strength = min(100, strength + 5)

    # 4. Duration
    if any(k in full_text for k in ["pli", "capex", "5-year", "roadmap", "policy", "reform", "commissioning"]):
        duration = "long-term"
    elif any(k in full_text for k in ["order", "quarterly", "contract", "tender", "tariff", "subsidy"]):
        duration = "medium-term"
    else:
        duration = "short-term"

    # 5. Freshness
    is_fresh = True
    if news.published_at:
        try:
            pub_dt = datetime.fromisoformat(news.published_at.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            delta = now_dt - pub_dt
            if delta.total_seconds() > 48 * 3600:
                is_fresh = False
        except Exception:
            is_fresh = True

    # 6. Already Priced In Check
    # If the stock has already run up > 15-20% in the last 20 days or has an RSI > 75
    # with fading volume, catalyst may be priced in ("buy the rumor, sell the news")
    already_priced_in = False
    if snapshot:
        excessive_runup = snapshot.performance_20d > 18.0 or snapshot.performance_5d > 12.0
        overbought = snapshot.rsi14 > 72.0
        if (excessive_runup and overbought) or (snapshot.performance_1m > 25.0):
            already_priced_in = True

    # 7. Rationale
    rationale = (
        f"{beneficiary_type} catalyst for {stock.name}: '{news.title[:70]}' "
        f"(Source: {news.source} - Tier {news.source_tier}, Certainty: {certainty}, "
        f"Strength: {strength}/100, Duration: {duration})."
    )
    if already_priced_in:
        rationale += f" Caution: Recent run-up ({snapshot.performance_20d:.1f}% 20d) suggests news may be partially priced in."

    return CatalystImpact(
        company=stock.name,
        catalyst_name=news.title,
        beneficiary_type=beneficiary_type,
        strength=strength,
        duration=duration,
        certainty=certainty,
        is_fresh=is_fresh,
        already_priced_in=already_priced_in,
        rationale=rationale,
    )


def evaluate_stock_catalysts(
    news_items: List[NewsItem],
    stock: Stock,
    snapshot: Optional[TechnicalSnapshot] = None,
) -> List[CatalystImpact]:
    """
    Score all relevant news items for a stock, sorted by impact strength descending.
    """
    impacts: List[CatalystImpact] = []
    for item in news_items:
        impact = score_catalyst_impact(item, stock, snapshot)
        # Keep non-neutral or significant catalysts
        if impact.beneficiary_type != "Neutral" or impact.strength >= 60:
            impacts.append(impact)

    impacts.sort(key=lambda x: x.strength, reverse=True)
    return impacts
