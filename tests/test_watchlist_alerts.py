"""Tests for watchlist_alerts module."""
from __future__ import annotations

from src.scheme_intel.watchlist_alerts import (
    build_message,
    format_price,
    safe,
    truncate_message,
    TELEGRAM_MAX_LENGTH,
)


class TestSafe:
    def test_escapes_html(self):
        assert safe("<b>bold</b>") == "&lt;b&gt;bold&lt;/b&gt;"

    def test_none_returns_empty(self):
        assert safe(None) == ""

    def test_ampersand(self):
        assert safe("A & B") == "A &amp; B"


class TestFormatPrice:
    def test_unavailable(self):
        result = format_price({"available": False, "reason": "No data"})
        assert "Unavailable" in result
        assert "No data" in result

    def test_with_change(self):
        price = {
            "available": True,
            "price": 100.0,
            "previous_close": 95.0,
            "change": 5.0,
            "change_percent": 5.26,
        }
        result = format_price(price)
        assert "100.00" in result
        assert "+5.26%" in result

    def test_negative_change(self):
        price = {
            "available": True,
            "price": 90.0,
            "previous_close": 95.0,
            "change": -5.0,
            "change_percent": -5.26,
        }
        result = format_price(price)
        assert "90.00" in result
        assert "-5.26%" in result


class TestTruncateMessage:
    def test_short_message_unchanged(self):
        msg = "Hello world"
        assert truncate_message(msg) == msg

    def test_exact_limit_unchanged(self):
        msg = "x" * TELEGRAM_MAX_LENGTH
        assert truncate_message(msg) == msg

    def test_over_limit_is_truncated(self):
        msg = "x" * (TELEGRAM_MAX_LENGTH + 100)
        result = truncate_message(msg)
        assert len(result) < TELEGRAM_MAX_LENGTH
        assert "truncated" in result

    def test_truncated_message_ends_with_marker(self):
        msg = "word " * 2000
        result = truncate_message(msg)
        assert result.endswith("…(truncated)")


class TestBuildMessage:
    def _stock(self, name="Test Co", symbol="TEST"):
        return {"name": name, "symbol": symbol}

    def _price(self, available=True, price=100.0):
        return {
            "available": available,
            "price": price,
            "previous_close": 95.0,
            "change": 5.0,
            "change_percent": 5.26,
            "volume": 100000,
            "delayed": True,
            "source": "Yahoo Finance",
        }

    def test_basic_structure(self):
        msg = build_message(
            self._stock(),
            self._price(),
            [],
            [],
            [],
        )
        assert "Test Co" in msg
        assert "TEST" in msg
        assert "Market Price" in msg
        assert "Events" in msg
        assert "Block" in msg
        assert "Financial News" in msg

    def test_escapes_html_in_stock_name(self):
        msg = build_message(
            self._stock(name="Co <script>"),
            self._price(),
            [],
            [],
            [],
        )
        assert "&lt;script&gt;" in msg

    def test_events_appear(self):
        events = [
            {"title": "Board Meeting", "date": "2026-09-10", "url": "https://example.com"},
        ]
        msg = build_message(
            self._stock(),
            self._price(),
            events,
            [],
            [],
        )
        assert "Board Meeting" in msg

    def test_news_appear(self):
        news = [
            {"title": "Stock rallies 5%", "url": "https://news.example.com"},
        ]
        msg = build_message(
            self._stock(),
            self._price(),
            [],
            [],
            news,
        )
        assert "Stock rallies 5%" in msg

    def test_empty_sections(self):
        msg = build_message(
            self._stock(),
            self._price(),
            [],
            [],
            [],
        )
        assert "No event data returned" in msg
        assert "No media-reported" in msg
        assert "No recent news returned" in msg
