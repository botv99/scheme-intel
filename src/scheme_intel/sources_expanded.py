"""
Expanded data sources for scheme-intel.

Adds sector-specific RSS feeds, BSE corporate actions, economic indicators,
and commodity price tracking on top of the existing ingestion layer.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

import feedparser
import requests

from .logger import get_logger
from .models import Article
from .sources import deduplicate_articles, fetch_rss

logger = get_logger(__name__)

TIMEOUT = 25
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    ),
})


# ------------------------------------------------------------------
# Sector-specific RSS feeds
# ------------------------------------------------------------------

SECTOR_FEEDS = {
    "renewable_energy": [
        ("MNRE Press Releases", "https://mnre.gov.in/rss/mnre-latest-news.xml"),
        ("ET Green Energy", "https://economictimes.indiatimes.com/rss/4718937.cms"),
        ("Clean Energy News", "https://www.cleanenergywire.org/rss"),
    ],
    "oil_gas": [
        ("OilPrice.com", "https://oilprice.com/rss/main"),
        ("ET Energy World", "https://economictimes.indiatimes.com/rss/13717993.cms"),
        ("PETROTECH", "https://www.petrotech.in/rss"),
    ],
    "water_infra": [
        ("ET Water", "https://economictimes.indiatimes.com/rss/5418309.cms"),
        ("Water Online", "https://www.wateronline.com/rss"),
    ],
    "government_policy": [
        ("PIB All Releases", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"),
        ("Cabinet Secretariat", "https://cabinet.gov.in/rss"),
        ("RBI Press Releases", "https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx"),
    ],
    "commodities": [
        ("Commodity Online", "https://www.commodityonline.com/rss"),
        ("MCX News", "https://www.mcxindia.com/rss"),
    ],
}


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@dataclass(frozen=True)
class SectorArticle:
    title: str
    url: str
    source: str
    sector: str
    published_at: str = ""
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EconomicIndicator:
    name: str
    value: Optional[float]
    period: str
    source: str
    url: str = ""
    change_pct: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CommodityPrice:
    name: str
    price: Optional[float]
    unit: str
    currency: str
    source: str
    url: str = ""
    change_pct: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BSECorporateAction:
    company: str
    symbol: str
    action_type: str
    ex_date: str
    description: str = ""
    url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------
# Sector news collector
# ------------------------------------------------------------------


def fetch_sector_news(
    sectors: Optional[list[str]] = None,
    watchlist_aliases: Optional[list[str]] = None,
) -> list[SectorArticle]:
    """
    Fetch sector-specific news from RSS feeds.

    Args:
        sectors: List of sector keys to fetch (default: all).
        watchlist_aliases: If provided, only keep articles mentioning these names.
    """
    if sectors is None:
        sectors = list(SECTOR_FEEDS.keys())

    articles: list[SectorArticle] = []
    watchlist_aliases = watchlist_aliases or []

    for sector in sectors:
        feeds = SECTOR_FEEDS.get(sector, [])
        for name, url in feeds:
            try:
                fetched = fetch_rss(name, url)
                for art in fetched:
                    # Filter by watchlist if aliases provided
                    if watchlist_aliases:
                        text = f"{art.title} {art.summary}".lower()
                        if not any(a.lower() in text for a in watchlist_aliases):
                            continue
                    articles.append(SectorArticle(
                        title=art.title,
                        url=art.url,
                        source=art.source,
                        sector=sector,
                        published_at=art.published_at.isoformat() if art.published_at else "",
                        summary=art.summary,
                    ))
            except Exception as exc:
                logger.debug(f"Sector feed failed for {name}: {exc}")

    logger.info("Fetched %d sector articles across %d sectors", len(articles), len(sectors))
    return articles


# ------------------------------------------------------------------
# BSE corporate actions
# ------------------------------------------------------------------


def fetch_bse_corporate_actions(symbol: str) -> list[BSECorporateAction]:
    """
    Fetch corporate actions (dividends, bonuses, splits) from BSE.
    """
    base = symbol.split(".")[0]
    url = f"https://api.bseindia.com/BseIndiaAPI/api/CorpAction/w"
    try:
        resp = SESSION.get(url, params={"scripcode": base}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        actions = []
        for item in data.get("Table", []):
            actions.append(BSECorporateAction(
                company=item.get("CompanyName", ""),
                symbol=base,
                action_type=item.get("Purpose", ""),
                ex_date=item.get("ExDate", ""),
                description=item.get("Description", ""),
            ))
        return actions[:10]
    except Exception as exc:
        logger.debug(f"BSE corporate actions failed for {base}: {exc}")
        return []


# ------------------------------------------------------------------
# Economic indicators
# ------------------------------------------------------------------


def fetch_economic_indicators() -> list[EconomicIndicator]:
    """
    Fetch key economic indicators from public RSS/API sources.
    """
    indicators: list[EconomicIndicator] = []

    # RBI key rates
    try:
        resp = SESSION.get(
            "https://rbi.org.in/scripts/BS_PressReleaseDisplay.aspx",
            timeout=TIMEOUT,
        )
        if resp.ok:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            for row in soup.select("table tr")[:10]:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    name = cols[0].get_text(strip=True)
                    value = _safe_float(cols[1].get_text(strip=True))
                    period = cols[2].get_text(strip=True)
                    if name and value is not None:
                        indicators.append(EconomicIndicator(
                            name=name, value=value, period=period,
                            source="RBI", url="https://rbi.org.in",
                        ))
    except Exception as exc:
        logger.debug(f"RBI indicator fetch failed: {exc}")

    # crude oil, natural gas prices from commodity feeds
    try:
        feed = feedparser.parse("https://oilprice.com/rss/main")
        for entry in feed.entries[:5]:
            title = entry.get("title", "")
            value = _extract_number(title)
            if value:
                indicators.append(EconomicIndicator(
                    name=title[:60], value=value, period="",
                    source="OilPrice.com", url=entry.get("link", ""),
                ))
    except Exception as exc:
        logger.debug(f"Commodity indicator fetch failed: {exc}")

    return indicators[:15]


# ------------------------------------------------------------------
# Commodity prices
# ------------------------------------------------------------------


def fetch_commodity_prices() -> list[CommodityPrice]:
    """
    Fetch key commodity prices relevant to the bioenergy sector.
    """
    prices: list[CommodityPrice] = []

    # Try commodityonline.com
    try:
        resp = SESSION.get("https://www.commodityonline.com/market-price", timeout=TIMEOUT)
        if resp.ok:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            for row in soup.select("table tr")[:15]:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    name = cols[0].get_text(strip=True)
                    price = _safe_float(cols[1].get_text(strip=True))
                    unit = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                    if name and price:
                        prices.append(CommodityPrice(
                            name=name, price=price, unit=unit,
                            currency="INR", source="CommodityOnline",
                        ))
    except Exception as exc:
        logger.debug(f"Commodity price fetch failed: {exc}")

    return prices[:10]


# ------------------------------------------------------------------
# Google News sector search
# ------------------------------------------------------------------


def fetch_sector_headlines(
    query: str,
    max_results: int = 8,
) -> list[SectorArticle]:
    """
    Search Google News RSS for sector-specific headlines.
    """
    encoded = quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        feed = feedparser.parse(url)
        articles = []
        for entry in feed.entries[:max_results]:
            articles.append(SectorArticle(
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                source=entry.get("source", {}).get("title", "Google News"),
                sector="custom",
                published_at=entry.get("published", ""),
            ))
        return articles
    except Exception as exc:
        logger.debug(f"Google News sector search failed: {exc}")
        return []


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        cleaned = str(value).replace(",", "").replace("%", "").replace("₹", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _extract_number(text: str) -> Optional[float]:
    """Extract the first number from text."""
    match = re.search(r"[\d,]+(?:\.\d+)?", text)
    if match:
        return _safe_float(match.group())
    return None


# ------------------------------------------------------------------
# Source health
# ------------------------------------------------------------------


@dataclass
class SourceHealth:
    name: str
    category: str
    status: str  # "ok" | "degraded" | "down"
    last_checked: str
    latency_ms: Optional[int] = None
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def check_source_health(sources: Optional[list[dict]] = None) -> list[SourceHealth]:
    """
    Quick health check for configured sources.
    Returns status of each source (ok/degraded/down).
    """
    if sources is None:
        sources = [
            {"name": "NSE", "url": "https://www.nseindia.com/", "category": "exchange"},
            {"name": "BSE", "url": "https://www.bseindia.com/", "category": "exchange"},
            {"name": "Screener", "url": "https://www.screener.in/", "category": "data"},
            {"name": "Mint RSS", "url": "https://www.livemint.com/rss/markets", "category": "news"},
            {"name": "Moneycontrol RSS", "url": "https://www.moneycontrol.com/rss/marketreports.xml", "category": "news"},
            {"name": "PIB", "url": "https://pib.gov.in/", "category": "government"},
            {"name": "MNRE", "url": "https://mnre.gov.in/", "category": "government"},
        ]

    results = []
    now = datetime.now(timezone.utc).isoformat()

    for src in sources:
        name = src.get("name", "Unknown")
        url = src.get("url", "")
        category = src.get("category", "other")
        try:
            start = datetime.now(timezone.utc)
            resp = SESSION.get(url, timeout=10)
            latency = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            if resp.ok:
                status = "ok"
                error = ""
            elif resp.status_code < 500:
                status = "degraded"
                error = f"HTTP {resp.status_code}"
            else:
                status = "down"
                error = f"HTTP {resp.status_code}"
        except requests.Timeout:
            status = "down"
            latency = None
            error = "Timeout"
        except Exception as exc:
            status = "down"
            latency = None
            error = str(exc)[:100]

        results.append(SourceHealth(
            name=name, category=category, status=status,
            last_checked=now, latency_ms=latency, error=error,
        ))

    ok_count = sum(1 for r in results if r.status == "ok")
    logger.info("Source health: %d/%d sources healthy", ok_count, len(results))
    return results
