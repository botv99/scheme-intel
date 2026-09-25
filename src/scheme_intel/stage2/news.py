"""
Today's News Intelligence Engine for Stage 2.
Scans and parses news, filings, and official announcements across all watchlist stocks.
Supports both live production ingestion (Stage 1 database & media feeds) and deterministic mock data.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from .models import NewsItem, Stock
from ..logger import get_logger
from ..catalyst import MATERIAL_EVENTS, _detect_scheme, _detect_sector
from ..models import resolve_source_tier

logger = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[3]


def classify_news_item(
    title: str,
    url: str = "",
    source: str = "Media",
    summary: str = "",
    published_at: Optional[str] = None,
    stocks: Optional[List[Stock]] = None,
) -> NewsItem:
    """
    Parse a news headline or corporate disclosure into a structured NewsItem.
    """
    text = f"{title} {summary}".lower()
    tier = resolve_source_tier(source, url)

    # Category and materiality
    matched_cat = "General Market"
    matched_score = 50
    matched_sentiment = "neutral"

    for term, (score, cat, dur, sent) in MATERIAL_EVENTS.items():
        if term in text:
            if score > matched_score:
                matched_score = score
                matched_cat = cat
                matched_sentiment = sent

    # Match watchlist companies with robust word-bounded entity matching
    matched_companies = []
    if stocks:
        raw_text = f"{title} {summary}"
        for stock in stocks:
            terms = [stock.name] + list(stock.aliases)
            if stock.symbol:
                terms.append(stock.symbol)
                ticker = stock.symbol.split(".")[0]
                if len(ticker) >= 3:
                    terms.append(ticker)
            if stock.screener_id and len(stock.screener_id) >= 3:
                terms.append(stock.screener_id)

            matched = False
            for term in terms:
                if not term or len(term.strip()) < 2:
                    continue
                term_clean = term.strip()
                pattern = rf"\b{re.escape(term_clean)}\b"
                if re.search(pattern, raw_text, re.IGNORECASE):
                    matched = True
                    break
            if matched:
                matched_companies.append(stock.name)

    return NewsItem(
        title=title,
        url=url,
        source=source,
        source_tier=tier,
        published_at=published_at or datetime.now(timezone.utc).isoformat(),
        summary=summary,
        sentiment=matched_sentiment,
        category=matched_cat,
        materiality=matched_score,
        companies_mentioned=matched_companies,
    )


def extract_stock_news(
    articles: list[dict | Any],
    stocks: list[Stock],
) -> dict[str, list[NewsItem]]:
    """
    Map each watchlist stock to its relevant news items today.
    Ensures every stock has an entry (even if empty).
    """
    by_stock: dict[str, list[NewsItem]] = {s.name: [] for s in stocks}

    for item in articles:
        if isinstance(item, NewsItem):
            news_obj = item
        elif isinstance(item, dict):
            title = item.get("title") or item.get("headline", "")
            url = item.get("url", "")
            source = item.get("source", "Media")
            summary = item.get("summary", "")
            pub = item.get("published_at")
            if not title:
                continue
            news_obj = classify_news_item(title, url, source, summary, pub, stocks)
        else:
            title = getattr(item, "title", "")
            url = getattr(item, "url", "")
            source = getattr(item, "source", "Media")
            summary = getattr(item, "summary", "")
            pub = getattr(item, "published_at", None)
            if isinstance(pub, datetime):
                pub = pub.isoformat()
            if not title:
                continue
            news_obj = classify_news_item(title, url, source, summary, pub, stocks)

        for comp in news_obj.companies_mentioned:
            if comp in by_stock:
                by_stock[comp].append(news_obj)

    return by_stock


class NewsEngine:
    """
    News & Corporate Disclosures Ingestion Engine for Stage 2.
    Explicitly distinguishes production mode (real Stage 1 DB & feeds) from mock mode.
    """

    def __init__(
        self,
        raw_news: Optional[List[Dict[str, Any]]] = None,
        mode: str = "production",
    ):
        self.raw_news = raw_news or []
        self.mode = mode

    def fetch_latest_news(self) -> List[Dict[str, Any]]:
        """Fetch today's news items from live database/feeds or mock defaults."""
        if self.raw_news:
            return self.raw_news

        if self.mode == "production":
            # Attempt to retrieve live ingested catalysts and articles from Stage 1 SQLite DB
            live_items: List[Dict[str, Any]] = []
            try:
                from ..db import SchemeIntelDB
                db = SchemeIntelDB()
                catalysts = db.get_recent_catalysts(days=3)
                for cat in catalysts:
                    live_items.append({
                        "title": cat.title if hasattr(cat, "title") else cat.get("title", ""),
                        "url": cat.url if hasattr(cat, "url") else cat.get("url", ""),
                        "source": cat.source if hasattr(cat, "source") else cat.get("source", "Exchange/PIB"),
                        "summary": cat.headline if hasattr(cat, "headline") else cat.get("headline", ""),
                        "published_at": cat.published_at if hasattr(cat, "published_at") else cat.get("published_at"),
                    })
                if live_items:
                    return live_items
            except Exception as e:
                logger.debug("Stage 1 database news lookup unavailable (%s)", e)

            if not live_items:
                # Fallback to data/ingested.json news and announcements
                try:
                    candidates = [
                        ROOT / "data" / "ingested.json",
                        Path.cwd() / "data" / "ingested.json",
                    ]
                    data_file = next((p for p in candidates if p.is_file()), None)
                    if data_file:
                        ing = json.loads(data_file.read_text(encoding="utf-8"))
                        for n in ing.get("news", []):
                            live_items.append({
                                "title": n.get("title", ""),
                                "url": n.get("url", ""),
                                "source": n.get("source", "Media"),
                                "summary": n.get("summary", ""),
                                "published_at": n.get("published_at"),
                            })
                        for a in ing.get("announcements", []):
                            live_items.append({
                                "title": a.get("headline") or a.get("title", ""),
                                "url": a.get("url", ""),
                                "source": f"{a.get('exchange', 'Exchange')} Filing",
                                "summary": a.get("details") or a.get("summary", ""),
                                "published_at": a.get("date"),
                            })
                except Exception as e:
                    logger.debug("Failed reading news from ingested.json: %s", e)

            return live_items

        # Mode == 'mock': Return deterministic offline test news
        return [
            {
                "title": "Cabinet Approves ₹10,000 Cr GOBARdhan Bioenergy Infrastructure Support Scheme",
                "source": "PIB Ministry of Petroleum & Natural Gas",
                "url": "https://pib.gov.in/PressReleasePage.aspx?PRID=2056001",
                "summary": "Government fast-tracks subsidies for 500 new commercial CBG and compressed biogas plants with priority allocation to Praj Industries and TruAlt Bioenergy consortiums.",
                "published_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "title": "VA Tech Wabag Secures ₹850 Cr Water Treatment Order from Middle East Utility",
                "source": "BSE Corporate Announcements",
                "url": "https://www.bseindia.com/corporates/ann.html",
                "summary": "Company has been awarded an international engineering and construction order for industrial wastewater recycling.",
                "published_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "title": "BEML bags ₹3,658 Cr Metro Rolling Stock Contract for Chennai Metro Rail Phase 2",
                "source": "NSE Corporate Filings",
                "url": "https://www.nseindia.com/companies-listing/corporate-filings",
                "summary": "BEML receives contract for design, manufacture and commissioning of metro trainsets.",
                "published_at": datetime.now(timezone.utc).isoformat(),
            },
        ]

    def group_by_stock(
        self,
        news_items: List[Dict[str, Any]],
        stocks: List[Stock],
    ) -> Dict[str, List[NewsItem]]:
        """Group news by stock name."""
        return extract_stock_news(news_items, stocks)
