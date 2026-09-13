"""Tests for the consolidated GOBARdhan alert runner."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.scheme_intel.models import SwingSetup, now_utc
from src.scheme_intel.consolidated import _yahoo_symbol, run_all


def _fake_setup(company="TruAlt Bioenergy", symbol="TRUALT.NS", status="QUALIFIED"):
    return SwingSetup(
        company=company,
        symbol=symbol,
        close=450.0,
        entry=460.0,
        stop=435.0,
        target=510.0,
        rsi14=58.0,
        catalyst_score=85,
        status=status,
        generated_at=now_utc().isoformat(),
        prior_high20=445.0,
        breakout=True,
        volume_avg=500000.0,
        volume_ratio=1.8,
        macd=2.5,
        macd_signal=1.2,
        macd_hist=1.3,
        week_trend="UP",
        dma200=400.0,
    )


class TestYahooSymbol(unittest.TestCase):
    def test_nse(self):
        self.assertEqual(_yahoo_symbol({"symbol": "TRUALT", "exchange": "NSE"}), "TRUALT.NS")

    def test_bse(self):
        self.assertEqual(_yahoo_symbol({"symbol": "TRUALT", "exchange": "BSE"}), "TRUALT.BO")

    def test_empty_symbol(self):
        self.assertIsNone(_yahoo_symbol({"symbol": ""}))

    def test_no_exchange(self):
        self.assertEqual(_yahoo_symbol({"symbol": "IOC"}), "IOC.NS")


class TestRunAll(unittest.TestCase):
    @patch("src.scheme_intel.consolidated.send_telegram")
    @patch("src.scheme_intel.consolidated.Pipeline")
    @patch("src.scheme_intel.consolidated.load_watchlist")
    @patch("src.scheme_intel.consolidated.get_news", return_value=[])
    @patch("src.scheme_intel.consolidated.get_block_deal_news", return_value=[])
    @patch("src.scheme_intel.consolidated.get_events", return_value=[])
    @patch("src.scheme_intel.consolidated.get_price")
    @patch("src.scheme_intel.consolidated.make_setup")
    def test_run_all_returns_summary(
        self, mock_make, mock_price, mock_events, mock_deals,
        mock_news, mock_wl, mock_pipeline, mock_send,
    ):
        mock_wl.return_value = [
            {"name": "TruAlt", "symbol": "TRUALT", "exchange": "NSE", "enabled": True},
        ]
        mock_price.return_value = {"available": True, "price": 450.0, "change_percent": 1.2}
        mock_make.return_value = _fake_setup()
        mock_pipeline.return_value.run.return_value = {
            "catalysts": [], "setups": [], "source_errors": [],
        }

        result = run_all(send=False)

        self.assertIn("stocks_processed", result)
        self.assertEqual(result["stocks_processed"], 1)
        self.assertEqual(result["stocks_succeeded"], 1)

    @patch("src.scheme_intel.consolidated.send_telegram")
    @patch("src.scheme_intel.consolidated.Pipeline")
    @patch("src.scheme_intel.consolidated.load_watchlist")
    @patch("src.scheme_intel.consolidated.get_news", return_value=[])
    @patch("src.scheme_intel.consolidated.get_block_deal_news", return_value=[])
    @patch("src.scheme_intel.consolidated.get_events", return_value=[])
    @patch("src.scheme_intel.consolidated.get_price")
    @patch("src.scheme_intel.consolidated.make_setup")
    def test_run_all_sends_digest(
        self, mock_make, mock_price, mock_events, mock_deals,
        mock_news, mock_wl, mock_pipeline, mock_send,
    ):
        mock_wl.return_value = [
            {"name": "TruAlt", "symbol": "TRUALT", "exchange": "NSE", "enabled": True},
        ]
        mock_price.return_value = {"available": True, "price": 450.0}
        mock_make.return_value = _fake_setup()
        mock_pipeline.return_value.run.return_value = {
            "catalysts": [], "setups": [], "source_errors": [],
        }

        result = run_all(send=True)

        self.assertTrue(result["digest_sent"])
        self.assertGreater(mock_send.call_count, 0)

    @patch("src.scheme_intel.consolidated.send_telegram")
    @patch("src.scheme_intel.consolidated.Pipeline")
    @patch("src.scheme_intel.consolidated.load_watchlist", return_value=[])
    def test_run_all_empty_watchlist(self, mock_wl, mock_pipeline, mock_send):
        mock_pipeline.return_value.run.return_value = {
            "catalysts": [], "setups": [], "source_errors": [],
        }

        result = run_all(send=False)

        self.assertEqual(result["stocks_processed"], 0)
        self.assertEqual(result["trade_calls"], [])

    @patch("src.scheme_intel.consolidated.send_telegram")
    @patch("src.scheme_intel.consolidated.Pipeline")
    @patch("src.scheme_intel.consolidated.load_watchlist")
    @patch("src.scheme_intel.consolidated.get_news", return_value=[])
    @patch("src.scheme_intel.consolidated.get_block_deal_news", return_value=[])
    @patch("src.scheme_intel.consolidated.get_events", return_value=[])
    @patch("src.scheme_intel.consolidated.get_price")
    def test_run_all_handles_price_failure(
        self, mock_price, mock_events, mock_deals,
        mock_news, mock_wl, mock_pipeline, mock_send,
    ):
        mock_wl.return_value = [
            {"name": "IOC", "symbol": "IOC", "exchange": "NSE", "enabled": True},
        ]
        mock_price.side_effect = Exception("yfinance blocked")
        mock_pipeline.return_value.run.return_value = {
            "catalysts": [], "setups": [], "source_errors": [],
        }

        result = run_all(send=False)

        self.assertEqual(result["stocks_failed"], 1)
        self.assertTrue(any("IOC" in e for e in result["errors"]))


if __name__ == "__main__":
    unittest.main()
