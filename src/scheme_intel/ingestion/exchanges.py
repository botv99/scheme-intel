"""
NSE / BSE exchange-activity collector.

Collects bulk deals (and block deals where exposed) plus tender / contract
announcements for the watchlist.

Primary path:
  * NSE bulk deals -> archives.nseindia.com public CSV (no session needed).

Best-effort paths (recorded as source errors when unreachable):
  * NSE block deals and corporate announcements -> www.nseindia.com JSON APIs
    (require a browser-like session; NSE blocks datacenter IPs, so these may
    fail from CI and are treated as non-fatal).
  * BSE bulk deals -> BSE bulk-deals report API.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timedelta

import requests

from ..exceptions import SourceAccessError
from ..logger import get_logger
from .models import Announcement, ExchangeDeal

logger = get_logger(__name__)

NSE_BULK_CSV = "https://archives.nseindia.com/content/equities/bulk.csv"
NSE_ANNOUNCEMENTS_API = (
    "https://www.nseindia.com/api/corporates-announcements?index=equities"
)
NSE_BLOCK_API = "https://www.nseindia.com/api/historical/block-deals"

BSE_BULK_PAGE = "https://www.bseindia.com/markets/equity/EQReports/BulkDeals.aspx"
BSE_BULK_API = "https://api.bseindia.com/BseIndiaAPI/api/BulkDeals/w"
BSE_ANNOUNCEMENT_API = "https://api.bseindia.com/BseIndiaAPI/api/Announcements/w"

DEFAULT_TIMEOUT = 25
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _browser_headers(referer: str | None = None) -> dict:
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _nse_session() -> requests.Session:
    """Session primed with NSE cookies (homepage visit) for API access."""
    session = requests.Session()
    session.headers.update(_browser_headers("https://www.nseindia.com/"))
    session.get("https://www.nseindia.com/", timeout=DEFAULT_TIMEOUT)
    return session


def _watchlist_symbols(config: dict) -> set[str]:
    symbols = set()
    for stock in config.get("stocks", []):
        symbol = stock.get("symbol")
        if symbol:
            symbols.add(symbol.split(".")[0].upper())
    return symbols


def _to_float(value: str) -> float | None:
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except ValueError:
        return None


def _parse_nse_csv(text: str, since: date, watchlist: set[str]) -> list[ExchangeDeal]:
    """Parse the NSE bulk-deals CSV and map to ExchangeDeal records."""
    deals = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        try:
            row_date = datetime.strptime(str(row.get("Date", "")).strip(), "%d-%b-%Y").date()
        except ValueError:
            continue
        if row_date < since:
            continue
        symbol = str(row.get("Symbol", "")).strip().upper()
        price = _to_float(row.get("Trade Price / Wght. Avg. Price"))
        quantity = _to_float(row.get("Quantity Traded"))
        deals.append(ExchangeDeal(
            exchange="NSE",
            deal_type="bulk",
            date=row_date.isoformat(),
            symbol=symbol,
            security=str(row.get("Security Name", "")).strip(),
            client=str(row.get("Client Name", "")).strip(),
            side=str(row.get("Buy/Sell", "")).strip().upper(),
            quantity=quantity or 0.0,
            price=price or 0.0,
            remarks=str(row.get("Remarks", "")).strip(),
            source_url=NSE_BULK_CSV,
            in_watchlist=symbol in watchlist,
        ))
    return deals


def collect_nse_bulk_deals(since: date, watchlist: set[str]) -> list[ExchangeDeal]:
    """Fetch NSE bulk deals from the public archives CSV."""
    response = requests.get(
        NSE_BULK_CSV,
        timeout=DEFAULT_TIMEOUT,
        headers=_browser_headers(),
    )
    response.raise_for_status()
    return _parse_nse_csv(response.text, since, watchlist)


def collect_nse_block_deals(since: date, config: dict) -> list[ExchangeDeal]:
    """Best-effort NSE block deals via the session-only historical API."""
    deals = []
    session = _nse_session()
    response = session.get(NSE_BLOCK_API, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    for row in payload.get("block_deals", []) or payload.get("data", []):
        try:
            raw_date = row.get("date", "")
            deal_date = datetime.fromisoformat(raw_date.replace("Z", "")).date()
        except (ValueError, TypeError):
            continue
        if deal_date < since:
            continue
        symbol = str(row.get("Symbol") or row.get("symbol") or "").upper()
        deals.append(ExchangeDeal(
            exchange="NSE",
            deal_type="block",
            date=deal_date.isoformat(),
            symbol=symbol,
            security=str(row.get("Security Name") or row.get("security") or "").strip(),
            client=str(row.get("Client Name") or row.get("client") or "").strip(),
            side="",
            quantity=_to_float(row.get("Quantity Traded") or row.get("quantity")) or 0.0,
            price=_to_float(row.get("Trade Price / Wght. Avg. Price") or row.get("price")) or 0.0,
            source_url=NSE_BLOCK_API,
            in_watchlist=symbol in watchlist,
        ))
    return deals


def collect_bse_bulk_deals(since: date, config: dict) -> list[ExchangeDeal]:
    """Best-effort BSE bulk deals via the BSE report API."""
    session = requests.Session()
    session.headers.update(_browser_headers(BSE_BULK_PAGE))
    session.get(BSE_BULK_PAGE, timeout=DEFAULT_TIMEOUT)

    params = {"Group": "", "Date": "", "Segment": "", "Scripcode": ""}
    response = session.get(BSE_BULK_API, params=params, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    payload = response.json()

    deals = []
    rows = payload.get("Table") if isinstance(payload, dict) else payload
    if isinstance(rows, str):
        raise SourceAccessError("BSE bulk-deals API returned non-JSON content")
    if not isinstance(rows, list):
        raise SourceAccessError("BSE bulk-deals API returned an unexpected shape")

    watchlist = _watchlist_symbols(config)
    for row in rows:
        try:
            deal_date = datetime.strptime(str(row.get("Date") or ""), "%d %b %Y").date()
        except (ValueError, TypeError):
            try:
                deal_date = datetime.strptime(str(row.get("Deal_Date") or ""), "%d %b %Y").date()
            except (ValueError, TypeError):
                continue
        if deal_date < since:
            continue
        symbol = str(row.get("ScripName") or row.get("Symbol") or row.get("SCName") or "").strip().upper()
        deals.append(ExchangeDeal(
            exchange="BSE",
            deal_type="bulk",
            date=deal_date.isoformat(),
            symbol=symbol,
            security=str(row.get("CompanyName") or row.get("Company") or symbol).strip(),
            client=str(row.get("ClientName") or row.get("Client") or "").strip(),
            side=str(row.get("BuySell") or row.get("Side") or "").strip().upper(),
            quantity=_to_float(row.get("Quantity") or row.get("Qty")) or 0.0,
            price=_to_float(row.get("TradePrice") or row.get("Price")) or 0.0,
            source_url=BSE_BULK_PAGE,
            in_watchlist=symbol in watchlist,
        ))
    return deals


def _match_announcement(keywords: list[str], title: str) -> list[str]:
    lowered = title.lower()
    return [kw for kw in keywords if kw.lower() in lowered]


def collect_nse_announcements(since: date, config: dict) -> list[Announcement]:
    """Best-effort NSE corporate announcements filtered by tender/contract keywords."""
    keywords = config.get("ingestion", {}).get("exchanges", {}).get(
        "announcement_keywords", ["tender", "contract", "order", "LOA", "award"]
    )
    watchlist = _watchlist_symbols(config)
    session = _nse_session()
    response = session.get(NSE_ANNOUNCEMENTS_API, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    payload = response.json()

    announcements = []
    rows = payload.get("data", []) if isinstance(payload, dict) else payload
    for row in rows:
        title = str(row.get("headline") or row.get("Heading") or row.get("title") or "").strip()
        if not _match_announcement(keywords, title):
            continue
        try:
            raw_date = row.get("date") or row.get("Date") or row.get("time") or ""
            ann_date = datetime.fromisoformat(str(raw_date).replace("Z", "")).date()
        except (ValueError, TypeError):
            continue
        if ann_date < since:
            continue
        symbol = str(row.get("symbol") or row.get("symbolName") or row.get("Symbol") or "").upper()
        matched = _match_announcement(keywords, title)
        announcements.append(Announcement(
            exchange="NSE",
            date=ann_date.isoformat(),
            symbol=symbol,
            company=str(row.get("company") or row.get("CompanyName") or symbol).strip(),
            title=title,
            url=str(row.get("link") or row.get("url") or NSE_ANNOUNCEMENTS_API).strip(),
            keywords=tuple(matched),
            category="tender/contract" if any(t in matched for t in ("tender", "contract", "LOA")) else "order",
            in_watchlist=symbol in watchlist,
        ))
    return announcements


def collect_bse_announcements(since: date, config: dict) -> list[Announcement]:
    """Best-effort BSE corporate announcements filtered by tender/contract keywords."""
    keywords = config.get("ingestion", {}).get("exchanges", {}).get(
        "announcement_keywords", ["tender", "contract", "order", "LOA", "award"]
    )
    watchlist = _watchlist_symbols(config)
    session = requests.Session()
    session.headers.update(_browser_headers("https://www.bseindia.com/corporates/ann.html"))
    session.get("https://www.bseindia.com/corporates/ann.html", timeout=DEFAULT_TIMEOUT)

    announcements = []
    for page in (1, 2):
        response = session.get(BSE_ANNOUNCEMENT_API, params={"pageno": page}, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("Table", [])
        if not rows:
            break
        for row in rows:
            title = str(row.get("Heading") or row.get("Title") or row.get("NewsTitle") or "").strip()
            if not _match_announcement(keywords, title):
                continue
            try:
                ann_date = datetime.strptime(str(row.get("Date") or ""), "%d-%b-%Y").date()
            except (ValueError, TypeError):
                continue
            if ann_date < since:
                continue
            symbol = str(row.get("ScripName") or row.get("Symbol") or row.get("SCName") or "").upper()
            matched = _match_announcement(keywords, title)
            announcements.append(Announcement(
                exchange="BSE",
                date=ann_date.isoformat(),
                symbol=symbol,
                company=str(row.get("CompanyName") or symbol).strip(),
                title=title,
                url=str(row.get("Url") or row.get("url") or "").strip(),
                keywords=tuple(matched),
                category="tender/contract" if any(t in matched for t in ("tender", "contract", "LOA")) else "order",
                in_watchlist=symbol in watchlist,
            ))
    return announcements


def collect_exchange_activity(config: dict, days_back: int | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Collect bulk/block deals and tender/contract announcements from NSE and BSE.

    Args:
        config: Loaded watchlist configuration.
        days_back: Keep activity from the last N days (defaults to config or 7).

    Returns:
        (bulk_deals, announcements, source_errors)
    """
    days_back = days_back or config.get("ingestion", {}).get("days_back", 7)
    since = date.today() - timedelta(days=days_back)
    watchlist = _watchlist_symbols(config)

    bulk_deals: list[ExchangeDeal] = []
    announcements: list[Announcement] = []
    source_errors: list[dict] = []

    tasks = {
        "NSE bulk deals": lambda: collect_nse_bulk_deals(since, watchlist),
        "NSE block deals": lambda: collect_nse_block_deals(since, config),
        "BSE bulk deals": lambda: collect_bse_bulk_deals(since, config),
        "NSE announcements (tenders/contracts)": lambda: collect_nse_announcements(since, config),
        "BSE announcements (tenders/contracts)": lambda: collect_bse_announcements(since, config),
    }
    collect_only_bulk = not config.get("ingestion", {}).get("exchanges", {}).get("bulk_deals", True)
    if collect_only_bulk:
        tasks = {k: v for k, v in tasks.items() if "announcement" not in k}

    for name, task in tasks.items():
        try:
            result = task()
            if "bulk" in name or "block" in name:
                deals = result if isinstance(result, list) else []
                anchor = bulk_deals
            else:
                anchor = announcements
            anchor.extend(result or [])
            logger.info(f"{name}: collected {len(result or [])} records")
        except Exception as exc:
            logger.warning(f"{name} failed: {str(exc)[:180]}")
            source_errors.append({"source": name, "error": str(exc)[:180]})

    bulk_deals.sort(key=lambda d: d.date, reverse=True)
    announcements.sort(key=lambda a: a.date, reverse=True)
    return [d.to_dict() for d in bulk_deals], [a.to_dict() for a in announcements], source_errors