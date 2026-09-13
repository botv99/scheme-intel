
"""
Gobardhan stock watchlist Telegram alerts.

Runs daily through GitHub Actions.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import requests
import yfinance as yf

# India Standard Time offset (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> datetime.date:
    """Return today's date in IST."""
    return datetime.now(IST).date()


def is_today(dt_str: str) -> bool:
    """Check if a date string (RFC 2822 or ISO 8601) is from today IST."""
    if not dt_str:
        return False
    try:
        # Try RFC 2822 (RSS format)
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(dt_str)
    except Exception:
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_ist = dt.astimezone(IST)
    return dt_ist.date() == today_ist()


def parse_date(dt_str: str | None) -> datetime | None:
    """Parse date string to datetime object (UTC)."""
    if not dt_str:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(dt_str).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
WATCHLIST_FILE = ROOT / "data" / "watchlist.json"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_IDS = [
    item.strip()
    for item in os.getenv("TELEGRAM_CHAT_ID", "").split(",")
    if item.strip()
]

TIMEOUT = 25

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger("gobardhan-alerts")

session = requests.Session()

session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/120 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
    }
)


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def safe(value) -> str:
    """Escape Telegram HTML characters."""
    return html.escape(str(value or ""))


def load_watchlist() -> list[dict]:
    """Load enabled companies from watchlist.json."""

    if not WATCHLIST_FILE.exists():
        raise FileNotFoundError(
            f"Missing watchlist file: {WATCHLIST_FILE}"
        )

    with WATCHLIST_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    return [
        stock
        for stock in data.get("stocks", [])
        if stock.get("enabled", True)
    ]


def yahoo_symbol(stock: dict) -> str | None:
    """Convert NSE/BSE symbol to Yahoo Finance symbol."""

    symbol = stock.get("symbol", "").strip()

    if not symbol:
        return None

    exchange = stock.get("exchange", "NSE").upper()

    if exchange == "NSE":
        return f"{symbol}.NS"

    if exchange == "BSE":
        return f"{symbol}.BO"

    return symbol


# --------------------------------------------------
# MARKET PRICE
# --------------------------------------------------

def get_price(stock: dict) -> dict:
    """Fetch delayed market price and previous close."""

    symbol = yahoo_symbol(stock)

    if not symbol:
        return {
            "available": False,
            "reason": "Exchange symbol not verified",
        }

    try:
        ticker = yf.Ticker(symbol)

        history = ticker.history(
            period="5d",
            interval="1d",
            auto_adjust=False,
        )

        if history.empty:
            return {
                "available": False,
                "reason": "No price data returned",
            }

        latest = history.iloc[-1]

        price = float(latest["Close"])

        previous_close = None

        if len(history) >= 2:
            previous_close = float(
                history.iloc[-2]["Close"]
            )

        change = None
        change_percent = None

        if previous_close:
            change = price - previous_close
            change_percent = (
                change / previous_close
            ) * 100

        volume = latest.get("Volume")

        return {
            "available": True,
            "price": price,
            "previous_close": previous_close,
            "change": change,
            "change_percent": change_percent,
            "volume": (
                int(volume)
                if volume and volume == volume
                else None
            ),
            "source": "Yahoo Finance",
            "delayed": True,
        }

    except Exception as exc:
        log.warning(
            "Price failed for %s: %s",
            symbol,
            exc,
        )

        return {
            "available": False,
            "reason": "Price source unavailable",
        }


def format_price(price: dict) -> str:
    """Format price for Telegram."""

    if not price.get("available"):
        return (
            "Unavailable — "
            + price.get("reason", "No data")
        )

    value = price["price"]

    result = f"₹{value:,.2f}"

    percent = price.get("change_percent")
    change = price.get("change")

    if percent is not None:
        sign = "+" if percent >= 0 else ""
        result += f" ({sign}{percent:.2f}%)"

    if change is not None:
        sign = "+" if change >= 0 else ""
        result += f" | {sign}₹{change:.2f}"

    return result


# --------------------------------------------------
# NSE CORPORATE ANNOUNCEMENTS
# --------------------------------------------------

def get_nse_announcements(stock: dict) -> list[dict]:
    """
    Fetch recent NSE corporate announcements.

    Availability depends on NSE access and response format.
    """

    symbol = stock.get("symbol", "").strip()

    if not symbol:
        return []

    url = (
        "https://www.nseindia.com/"
        "api/corporate-announcements"
    )

    try:
        # Establish NSE session cookies.
        session.get(
            "https://www.nseindia.com/",
            timeout=TIMEOUT,
        )

        response = session.get(
            url,
            params={
                "index": "equities",
                "symbol": symbol,
            },
            timeout=TIMEOUT,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, list):
            return []

        results = []

        for item in data[:15]:

            title = (
                item.get("subject")
                or item.get("desc")
                or "Corporate announcement"
            )

            results.append(
                {
                    "title": title,
                    "date": (
                        item.get("an_dt")
                        or item.get("sort_date")
                        or item.get("date")
                        or "Date unavailable"
                    ),
                    "url": (
                        item.get("attchmntFile")
                        or item.get("fileName")
                        or "https://www.nseindia.com/"
                    ),
                    "source": "NSE",
                }
            )

        return results

    except Exception as exc:
        log.warning(
            "NSE announcements failed: %s",
            exc,
        )

        return []


# --------------------------------------------------
# EVENTS CALENDAR
# --------------------------------------------------

def get_events(stock: dict) -> list[dict]:
    """
    Extract event-related NSE announcements from today only.

    This is not a complete future events calendar.
    """

    announcements = get_nse_announcements(stock)

    keywords = [
        "board meeting",
        "financial results",
        "earnings",
        "dividend",
        "agm",
        "annual general meeting",
        "bonus",
        "split",
        "buyback",
        "rights issue",
        "record date",
        "investor meet",
        "analyst meet",
        "conference call",
    ]

    events = []

    for item in announcements:

        title = item.get("title", "")
        date_str = item.get("date", "")

        # Only include today's announcements
        if date_str and not is_today(date_str):
            continue

        if any(
            keyword in title.lower()
            for keyword in keywords
        ):
            events.append(item)

    return events[:8]


# --------------------------------------------------
# MEDIA-REPORTED BLOCK DEAL NEWS
# --------------------------------------------------

def get_block_deal_news(stock: dict) -> list[dict]:
    """
    Fetch today's media-reported block/bulk deal news only.

    This is NOT an official exchange block-deal feed.
    """

    name = stock["name"]

    symbol = stock.get("symbol", "").strip()

    search_terms = [
        f'"{name}" "block deal"',
        f'"{name}" "bulk deal"',
    ]

    if symbol:
        search_terms.extend(
            [
                f'"{symbol}" "block deal"',
                f'"{symbol}" "bulk deal"',
            ]
        )

    query = quote_plus(
        " OR ".join(search_terms)
    )

    url = (
        "https://news.google.com/rss/search"
        f"?q={query}"
        "&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:

        feed = feedparser.parse(url)

        results = []

        for entry in feed.entries[:10]:

            published = entry.get("published", "")

            # Only include today's news
            if published and not is_today(published):
                continue

            title = entry.get(
                "title",
                "Block/bulk deal news",
            )

            results.append(
                {
                    "title": title,
                    "url": entry.get("link"),
                    "published": published,
                    "source": "Media-reported",
                }
            )

        return results[:5]

    except Exception as exc:

        log.warning(
            "Block deal news failed for %s: %s",
            name,
            exc,
        )

        return []


# --------------------------------------------------
# FINANCIAL NEWS
# --------------------------------------------------

def get_news(stock: dict) -> list[dict]:
    """Fetch today's financial news only."""

    name = stock["name"]

    symbol = stock.get("symbol", "").strip()

    # Source-specific searches through Google News RSS.
    sources = [
        "moneycontrol.com",
        "livemint.com",
        "economictimes.indiatimes.com",
        "financialexpress.com",
        "upstox.com",
    ]

    news = []

    for source in sources:

        search = f'"{name}" site:{source}'

        if symbol:
            search += f' OR "{symbol}" site:{source}'

        query = quote_plus(search)

        url = (
            "https://news.google.com/rss/search"
            f"?q={query}"
            "&hl=en-IN&gl=IN&ceid=IN:en"
        )

        try:

            feed = feedparser.parse(url)

            for entry in feed.entries[:5]:

                published = entry.get("published", "")

                # Only include today's news
                if published and not is_today(published):
                    continue

                news.append(
                    {
                        "title": entry.get(
                            "title",
                            "Untitled news",
                        ),
                        "url": entry.get("link"),
                        "published": published,
                        "source": source,
                    }
                )

        except Exception as exc:

            log.warning(
                "News failed for %s: %s",
                source,
                exc,
            )

    # Remove duplicate headlines.
    unique = []
    seen = set()

    for item in news:

        title = item.get("title", "")

        if title not in seen:
            unique.append(item)
            seen.add(title)

    return unique[:8]


# --------------------------------------------------
# TELEGRAM MESSAGE
# --------------------------------------------------

def build_message(
    stock: dict,
    price: dict,
    events: list[dict],
    deals: list[dict],
    news: list[dict],
) -> str:

    name = safe(stock["name"])

    symbol = safe(
        stock.get("symbol")
        or "Symbol pending"
    )

    lines = []

    lines.append(
        f"📊 <b>{name}</b>"
    )

    lines.append(
        f"Symbol: {symbol}"
    )

    lines.append("")

    lines.append(
        "💰 <b>Market Price</b>"
    )

    lines.append(
        safe(format_price(price))
    )

    if price.get("delayed"):
        lines.append(
            "ℹ️ Price may be delayed."
        )

    volume = price.get("volume")

    if volume:
        lines.append(
            f"📦 Volume: {volume:,}"
        )

    # EVENTS

    lines.append("")

    lines.append(
        "📅 <b>Events / Corporate Announcements</b>"
    )

    if events:

        for event in events[:6]:

            title = safe(
                event.get(
                    "title",
                    "Event",
                )
            )

            date = safe(
                event.get(
                    "date",
                    "Date unavailable",
                )
            )

            lines.append(
                f"• {date}: {title}"
            )

            if event.get("url"):
                lines.append(
                    safe(event["url"])
                )

    else:

        lines.append(
            "• No event data returned."
        )

    # BLOCK DEALS

    lines.append("")

    lines.append(
        "🔍 <b>Block / Bulk Deal News</b>"
    )

    if deals:

        for deal in deals[:4]:

            title = safe(
                deal.get(
                    "title",
                    "Deal news",
                )
            )

            lines.append(
                f"• {title}"
            )

            if deal.get("url"):
                lines.append(
                    safe(deal["url"])
                )

    else:

        lines.append(
            "• No media-reported block/bulk deal news found."
        )

    # NEWS

    lines.append("")

    lines.append(
        "📰 <b>Financial News</b>"
    )

    if news:

        for item in news[:6]:

            title = safe(
                item.get(
                    "title",
                    "News",
                )
            )

            lines.append(
                f"• {title}"
            )

            if item.get("url"):
                lines.append(
                    safe(item["url"])
                )

    else:

        lines.append(
            "• No recent news returned."
        )

    return "\n".join(lines)


# --------------------------------------------------
# TELEGRAM SENDING
# --------------------------------------------------

def send_telegram(message: str) -> None:

    if not BOT_TOKEN:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN"
        )

    if not CHAT_IDS:
        raise RuntimeError(
            "Missing TELEGRAM_CHAT_ID"
        )

    url = (
        "https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    for chat_id in CHAT_IDS:

        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        response = requests.post(
            url,
            json=payload,
            timeout=TIMEOUT,
        )

        if not response.ok:
            log.error(
                "Telegram API error %s for chat %s: %s",
                response.status_code,
                chat_id,
                response.text[:500],
            )

        response.raise_for_status()

        log.info(
            "Telegram message sent to %s",
            chat_id,
        )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

TELEGRAM_MAX_LENGTH = 4096


def truncate_message(message: str) -> str:
    """Truncate message to Telegram's 4096 char limit."""

    if len(message) <= TELEGRAM_MAX_LENGTH:
        return message

    truncated = message[: TELEGRAM_MAX_LENGTH - 20]
    truncated += "\n\n…(truncated)"
    return truncated


def main() -> None:

    stocks = load_watchlist()

    log.info(
        "Loaded %s stocks",
        len(stocks),
    )

    if not BOT_TOKEN or not CHAT_IDS:
        raise RuntimeError(
            "Telegram secrets are missing."
        )

    succeeded = 0
    failed = 0

    for stock in stocks:

        name = stock["name"]

        log.info(
            "Processing %s",
            name,
        )

        try:

            price = get_price(stock)

            events = get_events(stock)

            deals = get_block_deal_news(stock)

            news = get_news(stock)

            message = build_message(
                stock=stock,
                price=price,
                events=events,
                deals=deals,
                news=news,
            )

            message = truncate_message(message)

            send_telegram(message)

            succeeded += 1

            log.info(
                "Completed %s",
                name,
            )

        except Exception as exc:
            failed += 1
            log.error(
                "FAILED %s: %s",
                name,
                exc,
            )

    log.info(
        "Summary: %s succeeded, %s failed out of %s stocks",
        succeeded,
        failed,
        len(stocks),
    )


if __name__ == "__main__":
    main()
