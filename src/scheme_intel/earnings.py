"""
Earnings, analyst reports, and investor-call tracker.

Fetches quarterly results, broker research, and concall transcripts from
NSE, BSE, and Screener.in for the watchlist stocks.  Stores everything in
SQLite and generates a concise digest for Telegram alerts.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import feedparser
import requests

from .db import SchemeIntelDB
from .logger import get_logger
from .exceptions import SourceAccessError

logger = get_logger(__name__)

TIMEOUT = 25
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
})


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@dataclass(frozen=True)
class EarningsReport:
    company: str
    symbol: str
    period: str
    report_date: str
    revenue: Optional[float] = None
    profit: Optional[float] = None
    eps: Optional[float] = None
    yoy_growth: Optional[float] = None
    source: str = "NSE"
    url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AnalystRating:
    company: str
    symbol: str
    broker: str
    rating: str
    target_price: Optional[float] = None
    current_price: Optional[float] = None
    date: str = ""
    summary: str = ""
    url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConcallTranscript:
    company: str
    symbol: str
    call_date: str
    title: str
    url: str = ""
    source: str = "Screener"
    key_highlights: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DigestItem:
    kind: str
    company: str
    symbol: str
    title: str
    date: str
    url: str = ""
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------
# DB helpers — extend schema for Phase 8 tables
# ------------------------------------------------------------------


_PHASE8_SCHEMA = """
CREATE TABLE IF NOT EXISTS earnings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company         TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    period          TEXT,
    report_date     TEXT,
    revenue         REAL,
    profit          REAL,
    eps             REAL,
    yoy_growth      REAL,
    source          TEXT,
    url             TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analyst_ratings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company         TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    broker          TEXT,
    rating          TEXT,
    target_price    REAL,
    current_price   REAL,
    report_date     TEXT,
    summary         TEXT,
    url             TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS concalls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company         TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    call_date       TEXT,
    title           TEXT,
    url             TEXT,
    source          TEXT,
    key_highlights  TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_earnings_company ON earnings(company);
CREATE INDEX IF NOT EXISTS idx_earnings_symbol  ON earnings(symbol);
CREATE INDEX IF NOT EXISTS idx_ratings_company  ON analyst_ratings(company);
CREATE INDEX IF NOT EXISTS idx_concalls_company ON concalls(company);
"""


def _ensure_phase8_schema(db: SchemeIntelDB) -> None:
    conn = db.connect()
    try:
        conn.executescript(_PHASE8_SCHEMA)
    except sqlite3.Error as exc:
        logger.warning(f"Phase 8 schema init failed: {exc}")


# ------------------------------------------------------------------
# NSE earnings
# ------------------------------------------------------------------


def fetch_nse_results(symbol: str) -> list[EarningsReport]:
    """
    Fetch quarterly results from NSE corporate filings API.

    Returns an empty list on failure (API may block).
    """
    base = symbol.split(".")[0].upper()
    url = "https://www.nseindia.com/api/top-corp-info"
    try:
        SESSION.get("https://www.nseindia.com/", timeout=TIMEOUT)
        resp = SESSION.get(url, params={"symbol": base}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        results: list[EarningsReport] = []
        for item in data.get("data", []):
            period = item.get("finendedOn", item.get("fin_end_date", ""))
            results.append(EarningsReport(
                company=base,
                symbol=symbol,
                period=str(period),
                report_date=str(item.get("filDate", item.get("date", ""))),
                revenue=_safe_float(item.get("revenue")),
                profit=_safe_float(item.get("profit")),
                eps=_safe_float(item.get("eps")),
                source="NSE",
            ))
        return results[:8]
    except Exception as exc:
        logger.debug(f"NSE results fetch failed for {base}: {exc}")
        return []


# ------------------------------------------------------------------
# Screener.in data
# ------------------------------------------------------------------


def fetch_screener_announcements(screener_id: str, symbol: str, company_name: str) -> list[dict]:
    """
    Fetch recent announcements from Screener.in for a company.

    Returns list of dicts with title, date, url.
    """
    url = f"https://www.screener.in/company/{screener_id}/consolidated/"
    try:
        resp = SESSION.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        # Parse announcements from HTML
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[dict] = []
        for row in soup.select(". announcements li, .documents li, .annual-reports li"):
            link = row.find("a", href=True)
            if link:
                title = link.get_text(strip=True)
                href = link["href"]
                if not href.startswith("http"):
                    href = f"https://www.screener.in{href}"
                date_span = row.find("span", class_="date") or row.find("time")
                date_text = date_span.get_text(strip=True) if date_span else ""
                items.append({"title": title, "date": date_text, "url": href})
        return items[:10]
    except Exception as exc:
        logger.debug(f"Screener fetch failed for {screener_id}: {exc}")
        return []


def fetch_scripbox_analyst(screener_id: str, symbol: str) -> list[AnalystRating]:
    """
    Scrape analyst ratings from Screener.in analyst-consensus section.
    """
    url = f"https://www.screener.in/company/{screener_id}/consolidated/"
    try:
        resp = SESSION.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        ratings: list[AnalystRating] = []
        for row in soup.select(".analyst-targets tr, .peer-comparison tr"):
            cols = row.find_all("td")
            if len(cols) >= 3:
                broker = cols[0].get_text(strip=True)
                rating = cols[1].get_text(strip=True)
                target = _safe_float(cols[2].get_text(strip=True).replace(",", ""))
                if broker and rating:
                    ratings.append(AnalystRating(
                        company=screener_id,
                        symbol=symbol,
                        broker=broker,
                        rating=rating,
                        target_price=target,
                    ))
        return ratings[:5]
    except Exception as exc:
        logger.debug(f"Screener analyst fetch failed for {screener_id}: {exc}")
        return []


# ------------------------------------------------------------------
# Google News RSS for concalls and earnings
# ------------------------------------------------------------------


def _google_news_rss(query: str, max_results: int = 5) -> list[dict]:
    """Fetch Google News RSS for a query."""
    encoded = quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_results]:
            items.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": entry.get("source", {}).get("title", "Google News"),
            })
        return items
    except Exception as exc:
        logger.debug(f"Google News RSS failed for '{query}': {exc}")
        return []


def fetch_concall_transcripts(company: str, symbol: str) -> list[ConcallTranscript]:
    """Search for investor call transcripts and earnings call summaries."""
    queries = [
        f'"{company}" earnings call transcript',
        f'"{company}" investor call Q',
        f'"{company}" concall summary',
    ]
    seen_titles: set[str] = set()
    transcripts: list[ConcallTranscript] = []
    base = symbol.split(".")[0]

    for query in queries:
        for item in _google_news_rss(query, max_results=3):
            title = item["title"]
            if title in seen_titles:
                continue
            seen_titles.add(title)
            transcripts.append(ConcallTranscript(
                company=company,
                symbol=symbol,
                call_date=item.get("published", ""),
                title=title,
                url=item.get("url", ""),
                source=item.get("source", "Google News"),
            ))
    return transcripts[:6]


def fetch_analyst_reports(company: str, symbol: str) -> list[AnalystRating]:
    """Search for broker research reports and analyst ratings."""
    queries = [
        f'"{company}" analyst report buy sell',
        f'"{company}" broker research rating',
        f'"{company}" target price recommendation',
    ]
    seen: set[str] = set()
    reports: list[AnalystRating] = []

    for query in queries:
        for item in _google_news_rss(query, max_results=3):
            title = item["title"]
            if title in seen:
                continue
            seen.add(title)
            # Try to extract rating from title
            rating = _extract_rating(title)
            target = _extract_target_price(title)
            reports.append(AnalystRating(
                company=company,
                symbol=symbol,
                broker=item.get("source", "Media"),
                rating=rating,
                target_price=target,
                date=item.get("published", ""),
                summary=title,
                url=item.get("url", ""),
            ))
    return reports[:6]


def fetch_earnings_news(company: str, symbol: str) -> list[EarningsReport]:
    """Search for quarterly results announcements."""
    queries = [
        f'"{company}" quarterly results',
        f'"{company}" Q results revenue profit',
    ]
    seen: set[str] = set()
    reports: list[EarningsReport] = []

    for query in queries:
        for item in _google_news_rss(query, max_results=3):
            title = item["title"]
            if title in seen:
                continue
            seen.add(title)
            period = _extract_period(title)
            reports.append(EarningsReport(
                company=company,
                symbol=symbol,
                period=period,
                report_date=item.get("published", ""),
                source="Google News",
                url=item.get("url", ""),
            ))
    return reports[:6]


# ------------------------------------------------------------------
# Extractors
# ------------------------------------------------------------------


def _extract_rating(text: str) -> str:
    """Extract buy/sell/hold rating from analyst text."""
    lower = text.lower()
    if any(w in lower for w in ["buy", "outperform", "overweight", "accumulate"]):
        return "BUY"
    if any(w in lower for w in ["sell", "underperform", "underweight", "reduce"]):
        return "SELL"
    if any(w in lower for w in ["hold", "neutral", "equal-weight", "maintain"]):
        return "HOLD"
    return "NEUTRAL"


def _extract_target_price(text: str) -> Optional[float]:
    """Try to extract a target price from analyst text."""
    patterns = [
        r"target\s*(?:price)?\s*(?:of|:)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",
        r"(?:rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*target",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return _safe_float(match.group(1).replace(",", ""))
    return None


def _extract_period(text: str) -> str:
    """Try to extract a quarter/period from earnings text."""
    patterns = [
        r"(Q[1-4]\s*FY\d{2,4})",
        r"(FY\s*\d{2,4})",
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s*\d{4})",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _safe_float(value) -> Optional[float]:
    """Safely convert a value to float."""
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return None


# ------------------------------------------------------------------
# Main tracker class
# ------------------------------------------------------------------


class EarningsTracker:
    """Fetch, store, and digest earnings/analyst/concall data for watchlist stocks."""

    def __init__(self, db: Optional[SchemeIntelDB] = None):
        self.db = db or SchemeIntelDB()
        _ensure_phase8_schema(self.db)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def save_earnings(self, reports: list[EarningsReport]) -> int:
        conn = self.db.connect()
        count = 0
        for r in reports:
            # Deduplicate by company + period
            existing = conn.execute(
                "SELECT id FROM earnings WHERE company=? AND period=?",
                (r.company, r.period),
            ).fetchone()
            if existing:
                continue
            conn.execute(
                "INSERT INTO earnings (company, symbol, period, report_date, revenue, profit, eps, yoy_growth, source, url) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.company, r.symbol, r.period, r.report_date,
                 r.revenue, r.profit, r.eps, r.yoy_growth, r.source, r.url),
            )
            count += 1
        conn.commit()
        logger.info("Saved %d new earnings reports", count)
        return count

    def save_analyst_ratings(self, ratings: list[AnalystRating]) -> int:
        conn = self.db.connect()
        count = 0
        for r in ratings:
            existing = conn.execute(
                "SELECT id FROM analyst_ratings WHERE company=? AND broker=? AND rating=?",
                (r.company, r.broker, r.rating),
            ).fetchone()
            if existing:
                continue
            conn.execute(
                "INSERT INTO analyst_ratings (company, symbol, broker, rating, target_price, current_price, report_date, summary, url) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.company, r.symbol, r.broker, r.rating,
                 r.target_price, r.current_price, r.date, r.summary, r.url),
            )
            count += 1
        conn.commit()
        logger.info("Saved %d new analyst ratings", count)
        return count

    def save_concalls(self, transcripts: list[ConcallTranscript]) -> int:
        conn = self.db.connect()
        count = 0
        for t in transcripts:
            existing = conn.execute(
                "SELECT id FROM concalls WHERE company=? AND title=?",
                (t.company, t.title),
            ).fetchone()
            if existing:
                continue
            conn.execute(
                "INSERT INTO concalls (company, symbol, call_date, title, url, source, key_highlights) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (t.company, t.symbol, t.call_date, t.title, t.url, t.source, t.key_highlights),
            )
            count += 1
        conn.commit()
        logger.info("Saved %d new concall transcripts", count)
        return count

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_earnings(self, company: Optional[str] = None, limit: int = 20) -> list[dict]:
        conn = self.db.connect()
        if company:
            rows = conn.execute(
                "SELECT * FROM earnings WHERE company=? ORDER BY id DESC LIMIT ?",
                (company, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM earnings ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_analyst_ratings(self, company: Optional[str] = None, limit: int = 20) -> list[dict]:
        conn = self.db.connect()
        if company:
            rows = conn.execute(
                "SELECT * FROM analyst_ratings WHERE company=? ORDER BY id DESC LIMIT ?",
                (company, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM analyst_ratings ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_concalls(self, company: Optional[str] = None, limit: int = 20) -> list[dict]:
        conn = self.db.connect()
        if company:
            rows = conn.execute(
                "SELECT * FROM concalls WHERE company=? ORDER BY id DESC LIMIT ?",
                (company, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM concalls ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Fetch + store for all watchlist stocks
    # ------------------------------------------------------------------

    def refresh(self, stocks: list[dict]) -> dict:
        """
        Fetch earnings, analyst reports, and concall data for all watchlist stocks.

        Returns a summary dict with counts.
        """
        stats = {"earnings": 0, "analyst_ratings": 0, "concalls": 0, "stocks_processed": 0}

        for stock in stocks:
            name = stock["name"]
            symbol = stock.get("symbol", "")
            screener_id = stock.get("screener_id", "")

            logger.info("Refreshing Phase 8 data for %s", name)

            # Earnings
            earnings = fetch_earnings_news(name, symbol)
            if screener_id:
                earnings.extend(fetch_nse_results(symbol))
            stats["earnings"] += self.save_earnings(earnings)

            # Analyst ratings
            ratings = fetch_analyst_reports(name, symbol)
            if screener_id:
                ratings.extend(fetch_scripbox_analyst(screener_id, symbol))
            stats["analyst_ratings"] += self.save_analyst_ratings(ratings)

            # Concall transcripts
            transcripts = fetch_concall_transcripts(name, symbol)
            stats["concalls"] += self.save_concalls(transcripts)

            stats["stocks_processed"] += 1

        logger.info(
            "Phase 8 refresh complete: %d earnings, %d ratings, %d concalls across %d stocks",
            stats["earnings"], stats["analyst_ratings"], stats["concalls"], stats["stocks_processed"],
        )
        return stats

    # ------------------------------------------------------------------
    # Digest generation
    # ------------------------------------------------------------------

    def generate_digest(self, stocks: list[dict], days: int = 7) -> list[DigestItem]:
        """
        Generate a digest of recent earnings, analyst updates, and concalls
        for the given watchlist stocks from the last N days.
        """
        items: list[DigestItem] = []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        for stock in stocks:
            name = stock["name"]
            symbol = stock.get("symbol", "")

            # Recent earnings
            for e in self.get_earnings(company=name, limit=5):
                if e.get("report_date", "") >= cutoff or not e.get("report_date"):
                    summary_parts = []
                    if e.get("revenue"):
                        summary_parts.append(f"Rev ₹{e['revenue']:,.0f}")
                    if e.get("profit"):
                        summary_parts.append(f"PAT ₹{e['profit']:,.0f}")
                    if e.get("eps"):
                        summary_parts.append(f"EPS ₹{e['eps']:.1f}")
                    items.append(DigestItem(
                        kind="earnings",
                        company=name,
                        symbol=symbol,
                        title=f"📊 {e.get('period', 'Results')}: {', '.join(summary_parts) or 'Quarterly results'}",
                        date=e.get("report_date", ""),
                        url=e.get("url", ""),
                    ))

            # Recent analyst ratings
            for r in self.get_analyst_ratings(company=name, limit=5):
                if r.get("report_date", "") >= cutoff or not r.get("report_date"):
                    tp = f" → ₹{r['target_price']:.0f}" if r.get("target_price") else ""
                    items.append(DigestItem(
                        kind="analyst",
                        company=name,
                        symbol=symbol,
                        title=f"🏷️ {r['broker']}: {r['rating']}{tp}",
                        date=r.get("report_date", ""),
                        url=r.get("url", ""),
                        summary=r.get("summary", ""),
                    ))

            # Recent concalls
            for c in self.get_concalls(company=name, limit=3):
                if c.get("call_date", "") >= cutoff or not c.get("call_date"):
                    items.append(DigestItem(
                        kind="concall",
                        company=name,
                        symbol=symbol,
                        title=f"📞 {c['title'][:80]}",
                        date=c.get("call_date", ""),
                        url=c.get("url", ""),
                    ))

        # Sort by date descending
        items.sort(key=lambda x: x.date or "", reverse=True)
        return items

    def format_digest_telegram(self, digest: list[DigestItem]) -> str:
        """Format digest items into a Telegram-friendly message."""
        if not digest:
            return "📋 No recent earnings, analyst updates, or concalls found."

        lines = ["📋 <b>Scheme-Intel Earnings & Analyst Digest</b>", ""]

        by_company: dict[str, list[DigestItem]] = {}
        for item in digest:
            by_company.setdefault(item.company, []).append(item)

        for company, items in by_company.items():
            lines.append(f"<b>{company}</b>")
            for item in items[:8]:
                url_part = f" — <a href=\"{item.url}\">link</a>" if item.url else ""
                lines.append(f"  {item.title}{url_part}")
            lines.append("")

        lines.append("⚠️ Data from public sources. Not investment advice.")
        return "\n".join(lines)
