"""
Watchlist Scanner Engine for Stage 2.
Generates comprehensive Daily Stock Intelligence Cards for EVERY watchlist stock.
Guarantees 100% full coverage without silent omissions.
"""
from __future__ import annotations

from typing import Optional, List, Dict
from .models import (
    Stock, DailyStockCard, TechnicalSnapshot, NewsItem, CandidateSetup, CatalystImpact,
    DATA_OK, DATA_UNAVAILABLE, DATA_STALE, DATA_INSUFFICIENT,
)
from ..logger import get_logger

logger = get_logger(__name__)


def build_stock_card(
    stock: Stock,
    snapshot: Optional[TechnicalSnapshot],
    news_items: List[NewsItem],
    catalysts: Optional[List[CatalystImpact]] = None,
    candidate: Optional[CandidateSetup] = None,
    tomorrow_status: str = "WAIT",
    data_status: Optional[str] = None,
) -> DailyStockCard:
    """
    Construct the Daily Stock Intelligence Card for a single watchlist stock.
    No stock is omitted. Missing data remains explicitly unavailable.
    """
    catalysts = catalysts or []

    if snapshot:
        price = snapshot.close
        day_pct = snapshot.day_change_pct
        vol = snapshot.volume
        vol_20d = snapshot.volume_20d_avg
        vol_ratio = snapshot.volume_ratio
        support = snapshot.support
        resistance = snapshot.resistance
        trend = snapshot.trend_status.title()
        current_data_status = data_status or DATA_OK
        card_tomorrow_status = tomorrow_status
    else:
        price = None
        day_pct = None
        vol = None
        vol_20d = None
        vol_ratio = None
        support = None
        resistance = None
        trend = "Unavailable"
        current_data_status = data_status or DATA_UNAVAILABLE
        card_tomorrow_status = tomorrow_status if tomorrow_status in (DATA_UNAVAILABLE, DATA_STALE, DATA_INSUFFICIENT) else DATA_UNAVAILABLE

    # Developments
    developments = []
    for item in news_items[:3]:
        developments.append(f"{item.title} ({item.source or 'Exchange/Press'})")
    if not developments:
        developments.append("No material company disclosures or news reported today.")

    # Catalysts
    cat_descriptions = []
    cat_direction = "Neutral"
    cat_strength = 50

    if catalysts:
        best_cat = catalysts[0]
        cat_direction = "Bullish" if best_cat.beneficiary_type in ("Direct", "Indirect") else (
            "Bearish" if best_cat.beneficiary_type == "Negative" else "Neutral"
        )
        cat_strength = best_cat.strength
        for cat in catalysts[:3]:
            emoji = "🟢" if cat.beneficiary_type in ("Direct", "Indirect") else ("🔴" if cat.beneficiary_type == "Negative" else "🟡")
            cat_descriptions.append(f"{emoji} {cat.beneficiary_type}: {cat.catalyst_name[:65]} (Str: {cat.strength})")
    else:
        for item in news_items:
            if item.materiality >= 60:
                emoji = "🟢" if item.sentiment == "positive" else ("🔴" if item.sentiment == "negative" else "🟡")
                cat_descriptions.append(f"{emoji} {item.category}: {item.title[:65]}")
        if not cat_descriptions:
            cat_descriptions.append("⚪ Sector / General policy monitoring")

    # Technical summary
    if snapshot:
        above_20 = "Above 20 DMA" if snapshot.close >= snapshot.sma20 else "Below 20 DMA"
        above_50 = "Above 50 DMA" if snapshot.close >= snapshot.sma50 else "Below 50 DMA"
        sup_str = f"Support: ₹{support:.1f}" if support is not None else "Support: N/A"
        res_str = f"Resistance: ₹{resistance:.1f}" if resistance is not None else "Resistance: N/A"
        tech_summary = (
            f"Trend: {trend} | RSI: {snapshot.rsi14:.0f} | "
            f"{above_20} | {above_50} | {sup_str} | {res_str}"
        )
    else:
        tech_summary = "Market data unavailable: no valid OHLCV history feed."

    return DailyStockCard(
        stock=stock,
        price=price,
        day_change_pct=day_pct,
        volume=vol,
        volume_avg_20d=vol_20d,
        volume_ratio=vol_ratio,
        developments=developments,
        catalysts=cat_descriptions,
        catalyst_direction=cat_direction,
        catalyst_strength=cat_strength,
        technical_summary=tech_summary,
        support=support,
        resistance=resistance,
        trend=trend,
        tomorrow_status=card_tomorrow_status,
        data_status=current_data_status,
    )


def scan_all_stocks(
    stocks: List[Stock],
    market_data: Dict[str, TechnicalSnapshot],
    stock_news: Dict[str, List[NewsItem]],
    stock_catalysts: Optional[Dict[str, List[CatalystImpact]]] = None,
    candidates: Optional[Dict[str, CandidateSetup]] = None,
    statuses: Optional[Dict[str, str]] = None,
    data_statuses: Optional[Dict[str, str]] = None,
) -> List[DailyStockCard]:
    """
    Generate daily intelligence cards for all watchlist stocks.
    Guarantees every configured stock is present in output.
    """
    candidates = candidates or {}
    stock_catalysts = stock_catalysts or {}
    statuses = statuses or {}
    data_statuses = data_statuses or {}
    cards: List[DailyStockCard] = []

    for stock in stocks:
        snapshot = market_data.get(stock.symbol) or market_data.get(stock.name)
        news = stock_news.get(stock.name, []) or stock_news.get(stock.symbol, [])
        cats = stock_catalysts.get(stock.symbol, []) or stock_catalysts.get(stock.name, [])
        candidate = candidates.get(stock.symbol) or candidates.get(stock.name)
        d_status = data_statuses.get(stock.symbol, data_statuses.get(stock.name, DATA_OK if snapshot else DATA_UNAVAILABLE))

        # Determine status: missing or stale data MUST produce DATA_UNAVAILABLE / DATA_STALE
        if d_status in (DATA_UNAVAILABLE, DATA_STALE, DATA_INSUFFICIENT):
            default_status = d_status
        elif not snapshot:
            default_status = DATA_UNAVAILABLE
        elif candidate:
            default_status = "QUALIFIED_SETUP"
        elif snapshot.trend_status == "BULLISH":
            default_status = "WATCH"
        else:
            default_status = "WAIT"

        status = statuses.get(stock.symbol, default_status)
        if d_status in (DATA_UNAVAILABLE, DATA_STALE, DATA_INSUFFICIENT) or not snapshot:
            status = d_status if d_status in (DATA_UNAVAILABLE, DATA_STALE, DATA_INSUFFICIENT) else DATA_UNAVAILABLE

        card = build_stock_card(
            stock=stock,
            snapshot=snapshot,
            news_items=news,
            catalysts=cats,
            candidate=candidate,
            tomorrow_status=status,
            data_status=d_status,
        )
        cards.append(card)

    logger.info("Scanned all %d watchlist stocks; cards generated.", len(cards))
    return cards
