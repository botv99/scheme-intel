"""
Screener.in price collector.

Screener.in does not expose daily OHLC or RSI on its free company page, so this
module reads what it does expose (current price, change %, 52-week high/low,
market cap, and a daily close series + volume via the chart API) and computes
RSI(14) locally. A 6-month OHLC history is persisted from Yahoo Finance so the
downstream pipeline can build swing setups without re-fetching price data. When
screener.in is unreachable (datacenter/CI IPs are sometimes blocked) or a stock
has no name-based screener slug, a Yahoo Finance-only snapshot is produced and
the screener error is recorded on the snapshot.
"""
from __future__ import annotations

import re
from typing import Optional

import requests
import yfinance as yf
from bs4 import BeautifulSoup

from ..exceptions import SourceAccessError
from ..logger import get_logger
from .models import PriceSnapshot

logger = get_logger(__name__)

SCREENER_BASE = "https://www.screener.in"
DEFAULT_TIMEOUT = 25
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_NUMBER_RE = re.compile(r"-?[0-9.]+")


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": BROWSER_UA})
    return session


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    match = _NUMBER_RE.search(str(value).replace(",", ""))
    return float(match.group()) if match else None


def default_screener_id(symbol: str) -> str:
    """Derive a screener.in company slug from a Yahoo-style symbol.

    Screener.in uses the NSE ticker for most NSE-listed firms, so
    ``PRAJIND.NS`` -> ``PRAJIND``. Override with an explicit ``screener_id``
    in the watchlist when the slug differs from the exchange ticker (for
    example BSE SME names like ``ORGANICREC`` have no name-based slug and use
    the numeric scrip code as the screener slug).
    """
    return symbol.split(".")[0].upper()


def _yfinance_history(symbol: str) -> tuple[list[dict], Optional[float], Optional[float], Optional[float]]:
    """Fetch a 6-month OHLC history from Yahoo Finance for a symbol.

    Returns:
        (history, last_open, last_high, last_low).
    """
    if not symbol:
        return [], None, None, None
    try:
        hist = yf.Ticker(symbol).history(period="6mo", interval="1d", auto_adjust=True)
        if hist.empty:
            return [], None, None, None
        history = [
            {
                "date": str(idx.date()),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(float(row["Volume"])),
            }
            for idx, row in hist.iterrows()
        ]
        last = hist.iloc[-1]
        return history, float(last["Open"]), float(last["High"]), float(last["Low"])
    except Exception as exc:  # pragma: no cover - network dependent
        logger.debug(f"yfinance history failed for {symbol}: {exc}")
        return [], None, None, None


def _yfinance_fallback_snapshot(stock: dict, screener_id: str, error: Exception) -> PriceSnapshot:
    """
    Build a Yahoo Finance-only snapshot when the screener.in page is unreachable.

    Screener.in blocks datacenter IPs (so CI runners can be rejected) and some
    BSE SME names have no name-based screener slug. In those cases the snapshot
    is still produced from Yahoo Finance OHLC and the screener error is recorded,
    keeping the downstream pipeline able to read the stock.
    """
    name = stock.get("name", "Unknown")
    symbol = stock.get("symbol")
    history, open_, high, low = _yfinance_history(symbol)
    close = change_pct = None
    if history:
        close = history[-1]["close"]
        if len(history) >= 2 and history[-2]["close"]:
            change_pct = round((history[-1]["close"] / history[-2]["close"] - 1) * 100, 2)
        if open_ is None and len(history) >= 2:
            open_ = history[-2]["close"]
    return PriceSnapshot(
        company=name,
        symbol=symbol or "",
        screener_id=screener_id,
        date=str(history[-1]["date"]) if history else None,
        open=open_,
        close=close,
        high=high,
        low=low,
        volume=history[-1]["volume"] if history else None,
        change_pct=change_pct,
        rsi14=None,
        market_cap=None,
        high_52w=None,
        low_52w=None,
        price_source="yfinance",
        error=str(error)[:180],
        history=history or None,
    )


def _rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Wilder's RSI computed from a daily close series."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)


def _parse_top_header(soup: BeautifulSoup) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """Parse current price, change % and the header date from the price block."""
    price = change = date_text = None
    block = soup.select_one("div.font-size-18.strong")
    if block:
        spans = block.select("span")
        if spans:
            price = _to_float(re.sub(r"[^0-9.]", "", spans[0].get_text(" ", strip=True)))
        if len(spans) > 1:
            change = _to_float(spans[-1].get_text(" ", strip=True))
    date_el = soup.select_one("div.ink-600.font-size-11")
    if date_el:
        date_text = date_el.get_text(" ", strip=True)
    return price, change, date_text


def _parse_ratios(soup: BeautifulSoup) -> dict:
    """Parse the #top-ratios list into a name -> value mapping."""
    ratios: dict[str, str] = {}
    ul = soup.select_one("ul#top-ratios")
    if not ul:
        return ratios
    for item in ul.select("li"):
        name = item.select_one("span.name")
        value = item.select_one("span.value")
        if name and value:
            ratios[name.get_text(" ", strip=True).lower()] = value.get_text(" ", strip=True)
    return ratios


def _fetch_chart_series(company_id: str, days: int) -> tuple[list, list]:
    """Fetch the daily close series and volume series from the screener chart API."""
    url = f"{SCREENER_BASE}/api/company/{company_id}/chart/?days={days}&metrics=Price-DMA50-DMA200-Volume"
    response = _session().get(url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    closes: list = []
    volumes: list = []
    for dataset in payload.get("datasets", []):
        if dataset.get("metric") == "Price":
            closes = dataset.get("values", [])
        elif dataset.get("metric") == "Volume":
            volumes = dataset.get("values", [])
    return closes, volumes


def fetch_screener_snapshot(stock: dict, screener_id: Optional[str], days: int = 365) -> PriceSnapshot:
    """
    Build a daily price snapshot for one watchlist stock from screener.in.

    Args:
        stock: Watchlist stock record (name, symbol, aliases, ...).
        screener_id: Screener.in company slug (defaults to derived from symbol).
        days: Number of daily closes to pull from the chart API.

    Returns:
        PriceSnapshot (with ``error`` set when the record could not be fetched).
    """
    name = stock.get("name", "Unknown")
    symbol = stock.get("symbol")
    screener_id = screener_id or default_screener_id(symbol or "")

    try:
        page_url = f"{SCREENER_BASE}/company/{screener_id}/"
        response = _session().get(page_url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        company_id = None
        info = soup.select_one("#company-info")
        if info:
            company_id = info.get("data-company-id")

        price, change_pct, date_header = _parse_top_header(soup)
        ratios = _parse_ratios(soup)

        market_cap = ratios.get("market cap")
        high_low = ratios.get("high / low")
        high_52w, low_52w = None, None
        if high_low:
            parts = high_low.replace("₹", "").split("/")
            if len(parts) == 2:
                high_52w, low_52w = _to_float(parts[0]), _to_float(parts[1])

        closes, volumes = [], []
        if company_id:
            closes, volumes = _fetch_chart_series(company_id, days)
        else:
            logger.warning(f"No screener company id found for {name} ({screener_id})")

        close = _to_float(str(closes[-1][1])) if closes else price
        volume = int(volumes[-1][1]) if volumes else None
        date = str(closes[-1][0]) if closes else None

        close_series = [_to_float(str(row[1])) for row in closes]
        close_series = [c for c in close_series if c is not None]
        rsi14 = _rsi(close_series)

        computed_change = None
        if len(close_series) >= 2 and close_series[-2]:
            computed_change = round((close_series[-1] / close_series[-2] - 1) * 100, 2)
        if change_pct is None:
            change_pct = computed_change

        open_, high, low = None, None, None
        history, open_, high, low = _yfinance_history(symbol)
        if open_ is None and len(close_series) >= 2:
            open_ = close_series[-2]

        return PriceSnapshot(
            company=name,
            symbol=symbol or "",
            screener_id=screener_id,
            date=date,
            open=round(open_, 2) if open_ is not None else None,
            close=round(close, 2) if close is not None else None,
            high=round(high, 2) if high is not None else None,
            low=round(low, 2) if low is not None else None,
            volume=volume,
            change_pct=change_pct,
            rsi14=rsi14,
            market_cap=market_cap,
            high_52w=round(high_52w, 2) if high_52w else None,
            low_52w=round(low_52w, 2) if low_52w else None,
            price_source="screener.in",
            error=None,
            history=history,
        )
    except requests.RequestException as exc:
        logger.warning(f"Screener fetch failed for {name} ({screener_id}); using yfinance fallback: {exc}")
        return _yfinance_fallback_snapshot(stock, screener_id, exc)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Unexpected error parsing screener data for {name}: {exc}")
        return _yfinance_fallback_snapshot(stock, screener_id, exc)


def collect_prices(config: dict, days: int | None = None) -> list[dict]:
    """
    Collect daily price snapshots for every listed stock in the watchlist.

    Unlisted stocks (``symbol: null``) are skipped for prices, matching the
    project behaviour of news-monitoring them only.
    """
    ingestion = config.get("ingestion", {})
    screener_cfg = ingestion.get("screener", {})
    days = days or screener_cfg.get("chart_days", 365)

    snapshots = []
    for stock in config.get("stocks", []):
        symbol = stock.get("symbol")
        if not symbol:
            logger.info(f"Skipping price for unlisted stock '{stock.get('name')}'")
            continue
        screener_id = stock.get("screener_id") or default_screener_id(symbol)
        snapshot = fetch_screener_snapshot(stock, screener_id, days=days)
        snapshots.append(snapshot.to_dict())
        if snapshot.error:
            logger.warning(f"Price snapshot error for {stock['name']}: {snapshot.error}")
    return snapshots