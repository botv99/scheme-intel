if not WATCHLIST_FILE.exists():
    raise FileNotFoundError(
        f"Missing watchlist: {WATCHLIST_FILE}"
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
try:

    response = session.get(
        url,
        params=params,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    return response.json()

except Exception as exc:

    log.warning(
        "Request failed: %s | %s",
        url,
        exc,
    )

    return None
  result = []

for item in items:

    if item and item not in result:
        result.append(item)

return result
symbol = stock.get("symbol", "").strip()

exchange = stock.get(
    "exchange",
    "NSE",
).upper()

if not symbol:

    return {
        "available": False,
        "reason": "NSE symbol not verified",
    }

yahoo_symbol = (
    f"{symbol}.NS"
    if exchange == "NSE"
    else f"{symbol}.BO"
)

try:

    ticker = yf.Ticker(yahoo_symbol)

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
            if volume
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
    if not price.get("available"):
    return (
        "Unavailable — "
        + price.get(
            "reason",
            "No data",
        )
    )

value = price["price"]

result = f"₹{value:,.2f}"

percent = price.get("change_percent")

change = price.get("change")

if percent is not None:

    sign = "+" if percent >= 0 else ""

    result += (
        f" ({sign}{percent:.2f}%)"
    )

if change is not None:

    sign = "+" if change >= 0 else ""

    result += (
        f" | {sign}₹{change:.2f}"
    )

return result
symbol = stock.get("symbol", "").strip()

if not symbol:
    return []

url = (
    "https://www.nseindia.com/"
    "api/corporate-announcements"
)

try:

    # Visit NSE homepage first for cookies.
    session.get(
        "https://www.nseindia.com/",
        timeout=TIMEOUT,
    )

    data = get_json(
        url,
        params={
            "index": "equities",
            "symbol": symbol,
        },
    )

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
    """
Extract event-related announcements.

This is not a complete future events calendar.
Confirmed event dates require a verified calendar
source or company exchange filing.
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

    if any(
        keyword in title.lower()
        for keyword in keywords
    ):

        events.append(item)

return events[:8]
"""
Best-effort event calendar.

Availability depends on Yahoo Finance coverage.
"""

symbol = stock.get("symbol", "").strip()

if not symbol:
    return []

exchange = stock.get(
    "exchange",
    "NSE",
).upper()

yahoo_symbol = (
    f"{symbol}.NS"
    if exchange == "NSE"
    else f"{symbol}.BO"
)

try:

    ticker = yf.Ticker(yahoo_symbol)

    calendar = ticker.calendar

    if calendar is None:
        return []

    if hasattr(calendar, "to_dict"):
        calendar = calendar.to_dict()

    if not isinstance(calendar, dict):
        return []

    results = []

    for key, value in calendar.items():

        results.append(
            {
                "title": str(key),
                "date": str(value),
                "source": "Yahoo Finance",
            }
        )

    return results[:8]

except Exception as exc:

    log.warning(
        "Calendar failed for %s: %s",
        symbol,
        exc,
    )

    return []
    """
Placeholder until a verified exchange deal
adapter is connected.

Do not fabricate bulk/block deal information.
"""

# The official exchange deal pages should be used
# for a reliable production adapter.
#
# NSE:
# https://www.nseindia.com/
#
# BSE:
# https://www.bseindia.com/

return []
name = stock["name"]

symbol = stock.get("symbol", "").strip()

search_terms = [f'"{name}"']

if symbol:
    search_terms.append(f'"{symbol}"')

query = quote_plus(
    " OR ".join(search_terms)
)

url = (
    "https://news.google.com/rss/search"
    f"?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)

try:

    feed = feedparser.parse(url)

    news = []

    for entry in feed.entries[:6]:

        news.append(
            {
                "title": entry.get(
                    "title",
                    "Untitled news",
                ),
                "url": entry.get("link"),
                "published": entry.get(
                    "published",
                    "",
                ),
                "source": "Google News RSS",
            }
        )

    return news

except Exception as exc:

    log.warning(
        "News failed: %s",
        exc,
    )

    return []
    if not BOT_TOKEN:
    raise RuntimeError(
        "Missing TELEGRAM_BOT_TOKEN"
    )

if not CHAT_ID:
    raise RuntimeError(
        "Missing TELEGRAM_CHAT_ID"
    )

url = (
    "https://api.telegram.org/"
    f"bot{BOT_TOKEN}/sendMessage"
)

response = requests.post(
    url,
    json={
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    },
    timeout=TIMEOUT,
)

response.raise_for_status()
name = safe_text(stock["name"])

symbol = safe_text(
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

lines.append(
    f"💰 <b>Market Price:</b> "
    f"{safe_text(format_price(price))}"
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
lines.append("📅 <b>Events Calendar / Filings</b>")

combined_events = events + calendar

if combined_events:

    for event in combined_events[:8]:

        title = safe_text(
            event.get(
                "title",
                "Event",
            )
        )

        date = safe_text(
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
                f"  {safe_text(event['url'])}"
            )

else:

    lines.append(
        "• No event data returned."
    )

# DEALS

lines.append("")
li::chatgpt-content-reference{index="8"}
