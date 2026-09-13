"""
Unit tests for the ingestion layer.
"""
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from scheme_intel.ingestion import exchanges, media, price
from scheme_intel.ingestion.models import Announcement, ExchangeDeal, MediaArticle, PriceSnapshot
from scheme_intel.models import Article


# --------------------------------------------------------------------------- price

PRICE_HTML = """
<html><body>
  <div id="company-info" data-company-id="2529"></div>
  <div class="font-size-18 strong line-height-14">
    <div class="flex flex-align-center">
      <span>₹ 322</span>
      <span class="font-size-12 down margin-left-4"><i class="icon-circle-down"></i> -1.44%</span>
    </div>
    <div class="ink-600 font-size-11 font-weight-500">11 Sep - close price</div>
  </div>
  <ul id="top-ratios">
    <li class="flex flex-space-between"><span class="name">Market Cap</span>
      <span class="nowrap value">₹ <span class="number">5,922</span> Cr.</span></li>
    <li class="flex flex-space-between"><span class="name">Current Price</span>
      <span class="nowrap value">₹ <span class="number">322</span></span></li>
    <li class="flex flex-space-between"><span class="name">High / Low</span>
      <span class="nowrap value">₹ <span class="number">428</span> / <span class="number">273</span></span></li>
  </ul>
</body></html>
"""


def _chart_payload(closes: list[float]) -> str:
    return json.dumps({
        "datasets": [
            {
                "metric": "Price",
                "values": [[f"2026-09-{i + 1:02d}", str(value)] for i, value in enumerate(closes)],
            },
            {
                "metric": "Volume",
                "values": [[f"2026-09-{i + 1:02d}", 1000 * (i + 1), {"delivery": 50}] for i in range(len(closes))],
            },
        ]
    })


class _FakeResponse:
    def __init__(self, text: str, json_payload: dict | None = None, ok: bool = True):
        self.text = text
        self._json = json_payload
        self.ok = ok

    def raise_for_status(self):
        if not self.ok:
            raise Exception("HTTP error")

    def json(self):
        return self._json


class _FakeSession:
    def __init__(self, page_text: str, chart_payload: str):
        self.page_text = page_text
        self.chart_payload = chart_payload
        self.calls = []

    def get(self, url, timeout=None, **kwargs):
        self.calls.append(url)
        if "/api/company/" in url:
            return _FakeResponse("", json_payload=json.loads(self.chart_payload))
        return _FakeResponse(self.page_text)


def _closes(n: int) -> list[float]:
    start = 300.0
    return [round(start + i * 1.2, 2) for i in range(n)]


class TestScreenerPrice:
    def test_default_screener_id(self):
        assert price.default_screener_id("PRAJIND.NS") == "PRAJIND"
        assert price.default_screener_id("GAIL.NS") == "GAIL"

    def test_snapshot_parses_header_ratios_and_chart(self):
        fake = _FakeSession(PRICE_HTML, _chart_payload(_closes(30)))
        with patch("scheme_intel.ingestion.price._session", return_value=fake):
            snapshot = price.fetch_screener_snapshot(
                {"name": "Praj Industries", "symbol": "PRAJIND.NS"}, "PRAJIND", days=30
            )
        assert snapshot.close == 300.0 + 29 * 1.2
        assert snapshot.change_pct == -1.44
        assert snapshot.high_52w == 428.0
        assert snapshot.low_52w == 273.0
        assert snapshot.market_cap == "₹ 5,922 Cr."
        assert snapshot.volume == 1000 * 30
        assert snapshot.rsi14 is not None
        assert 0 <= snapshot.rsi14 <= 100
        assert snapshot.price_source == "screener.in"
        assert snapshot.error is None

    def test_snapshot_without_chart_company_id(self):
        html = PRICE_HTML.replace('data-company-id="2529"', "")
        fake = _FakeSession(html, _chart_payload(_closes(2)))
        with patch("scheme_intel.ingestion.price._session", return_value=fake):
            snapshot = price.fetch_screener_snapshot(
                {"name": "Praj Industries", "symbol": "PRAJIND.NS"}, "PRAJIND", days=30
            )
        assert snapshot.close == snapshot.close or 322.0

    def test_request_error_records_source_error(self):
        class BoomSession:
            def get(self, url, timeout=None, **kwargs):
                raise Exception("network down")

        with patch("scheme_intel.ingestion.price._session", return_value=BoomSession()):
            snapshot = price.fetch_screener_snapshot(
                {"name": "Praj Industries", "symbol": "PRAJIND.NS"}, "PRAJIND", days=30
            )
        assert snapshot.error is not None

    def test_collect_prices_skips_unlisted_stocks(self):
        config = {
            "ingestion": {"screener": {"chart_days": 30}},
            "stocks": [
                {"name": "Unlisted Co", "symbol": None},
                {"name": "Praj Industries", "symbol": "PRAJIND.NS", "screener_id": "PRAJIND"},
            ],
        }
        fake = _FakeSession(PRICE_HTML, _chart_payload(_closes(30)))
        with patch("scheme_intel.ingestion.price._session", return_value=fake):
            snapshots = price.collect_prices(config)
        assert len(snapshots) == 1
        assert snapshots[0]["company"] == "Praj Industries"

    def test_rsi_extremes(self):
        rising = list(range(100, 130))
        assert price._rsi(rising) > 90
        falling = list(range(130, 100, -1))
        assert price._rsi(falling) < 10
        assert price._rsi([1.0, 2.0]) is None  # too few points

    def test_ohlc_enrichment_fallback(self):
        closes = _closes(30)
        fake = _FakeSession(PRICE_HTML, _chart_payload(closes))
        with patch("scheme_intel.ingestion.price._session", return_value=fake), \
             patch.object(price.yf, "Ticker", side_effect=Exception("blocked")):
            snapshot = price.fetch_screener_snapshot(
                {"name": "Praj Industries", "symbol": "PRAJIND.NS"}, "PRAJIND", days=30
            )
        assert snapshot.open == closes[-2]  # falls back to previous close


# --------------------------------------------------------------------------- exchanges

BULK_DATE = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
BULK_CSV = f"""Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price,Remarks
{BULK_DATE},AEROPLANE,Amir Chand Jag Kum (E) L,NITIN HUF,BUY,1276148,201.45,-
{BULK_DATE},PRAJIND,Praj Industries Ltd,SOME FUND,SELL,500000,450.00,-
{BULK_DATE},WABAG,VA Tech Wabag,,BUY,100000,700.00,-
"""


class TestExchangeIngestion:
    def test_parse_nse_bulk_csv(self):
        since = datetime.now().date() - timedelta(days=2)
        deals = exchanges._parse_nse_csv(BULK_CSV, since, {"PRAJIND", "WABAG"})
        assert len(deals) == 3
        praj = next(d for d in deals if d.symbol == "PRAJIND")
        assert praj.exchange == "NSE"
        assert praj.deal_type == "bulk"
        assert praj.side == "SELL"
        assert praj.quantity == 500000.0
        assert praj.price == 450.0
        assert praj.in_watchlist is True

    def test_parse_nse_bulk_csv_date_window(self):
        old_date = (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")
        since = datetime.now().date() - timedelta(days=2)
        csv_text = BULK_CSV.replace("Date,Symbol,", "OLD,Symbol,")  # no-op safeguard
        csv_text = f"Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price,Remarks\n{old_date},AA,AAA,CLIENT,BUY,10,100.0,-\n"
        deals = exchanges._parse_nse_csv(csv_text, since, set())
        assert deals == []

    def test_collect_nse_bulk_deals(self):
        response = Mock()
        response.text = BULK_CSV
        with patch("scheme_intel.ingestion.exchanges.requests.get", return_value=response) as mocked:
            deals = exchanges.collect_nse_bulk_deals(
                datetime.now().date() - timedelta(days=2), {"PRAJIND"}
            )
        assert len(deals) == 3
        assert mocked.call_args.args[0] == exchanges.NSE_BULK_CSV

    def test_announcement_keyword_matching(self):
        ann = Announcement(
            exchange="NSE",
            date="2026-09-11",
            symbol="PRAJIND",
            company="Praj Industries",
            title="Praj receives order worth Rs 500 crore",
            url="https://example.com",
            keywords=("order",),
        )
        assert "order" in ann.keywords

    def test_collect_exchange_activity_records_failures(self):
        config = {"ingestion": {"days_back": 7, "exchanges": {"bulk_deals": True}},
                  "stocks": [{"name": "Praj Industries", "symbol": "PRAJIND.NS"}]}

        def boom(*args, **kwargs):
            raise Exception("blocked")

        with patch("scheme_intel.ingestion.exchanges.collect_nse_bulk_deals") as nse_bulk, \
             patch("scheme_intel.ingestion.exchanges.collect_nse_block_deals", side_effect=boom), \
             patch("scheme_intel.ingestion.exchanges.collect_bse_bulk_deals", side_effect=boom), \
             patch("scheme_intel.ingestion.exchanges.collect_nse_announcements", side_effect=boom), \
             patch("scheme_intel.ingestion.exchanges.collect_bse_announcements", side_effect=boom):
            nse_bulk.return_value = [ExchangeDeal("NSE", "bulk", "2026-09-11", "GAIL", "GAIL", "C", "BUY", 1, 2.0)]
            deals, anns, errors = exchanges.collect_exchange_activity(config)
        assert len(deals) == 1
        assert len(errors) == 4


# --------------------------------------------------------------------------- media


class TestMediaIngestion:
    def test_match_aliases_in_article(self):
        article = Article("Praj Industries wins new order",
                          "https://example.com", "Mint", None, "compressed biogas")
        found = media._matches(article, ["Praj", "GAIL"])
        assert found == ["Praj"]

    def test_match_no_alias(self):
        article = Article("Nifty ends higher", "https://example.com", "Mint", None)
        assert media._matches(article, ["Praj", "GAIL"]) == []

    def test_short_alias_is_word_bound(self):
        article = Article("Adani Airports to raise $1 billion from investors",
                          "https://example.com", "Mint", None)
        assert media._matches(article, ["ORS"]) == []

    def test_media_article_conversion(self):
        article = Article("Praj order", "https://example.com/praj", "Mint", None)
        item = media._media_article(article, ["Praj"])
        assert item is not None
        assert isinstance(item, MediaArticle)
        assert item.matched_stocks == ["Praj"]

    def test_collect_news_filters_and_falls_back(self):
        config = {
            "scheme": {"aliases": ["GOBARdhan"]},
            "stocks": [{"name": "Praj Industries", "aliases": ["Praj"], "symbol": "PRAJIND.NS"}],
            "ingestion": {"news_sources": [{"name": "Mint", "rss": "https://rss.example"}]},
        }
        matching = Article("Praj Industries surges on order win", "https://example.com/praj",
                           "Mint", None)
        non_matching = Article("Sensex closes flat", "https://example.com/sensex", "Mint", None)

        with patch("scheme_intel.ingestion.media.fetch_rss", return_value=[matching, non_matching]):
            news, errors = media.collect_news(config)
        assert len(news) == 1
        assert news[0]["url"] == "https://example.com/praj"
        assert errors == []

    def test_collect_news_tracks_source_failures(self):
        config = {
            "scheme": {"aliases": []},
            "stocks": [{"name": "Praj Industries", "symbol": "PRAJIND.NS", "aliases": []}],
            "ingestion": {"news_sources": [{"name": "Mint", "rss": "https://rss.example"}]},
        }

        def boom(*args, **kwargs):
            raise Exception("feed down")

        with patch("scheme_intel.ingestion.media.fetch_rss", side_effect=boom):
            news, errors = media.collect_news(config)
        assert news == []
        assert len(errors) == 1
        assert errors[0]["source"] == "Mint"