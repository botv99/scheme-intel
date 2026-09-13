"""Tests for the trade recommendation engine."""
from __future__ import annotations

import unittest

from src.scheme_intel.models import SwingSetup, now_utc
from src.scheme_intel.trade_call import (
    TradeCall,
    _interpret_dma200,
    _interpret_macd,
    _interpret_volume,
    _holding_period,
    evaluate_setup,
    format_final_digest_telegram,
    format_trade_call_telegram,
)


def _make_setup(**overrides) -> SwingSetup:
    """Create a SwingSetup with sensible defaults for testing."""
    defaults = dict(
        company="TruAlt Bioenergy",
        symbol="TRUALT.NS",
        close=450.0,
        entry=460.0,
        stop=435.0,
        target=510.0,
        rsi14=58.0,
        catalyst_score=85,
        status="QUALIFIED",
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
    defaults.update(overrides)
    return SwingSetup(**defaults)


class TestInterpretVolume(unittest.TestCase):
    def test_strong_breakout(self):
        self.assertEqual(_interpret_volume(2.5), "STRONG_BREAKOUT")

    def test_breakout(self):
        self.assertEqual(_interpret_volume(1.6), "BREAKOUT")

    def test_above_avg(self):
        self.assertEqual(_interpret_volume(1.3), "ABOVE_AVG")

    def test_normal(self):
        self.assertEqual(_interpret_volume(1.0), "NORMAL")

    def test_low(self):
        self.assertEqual(_interpret_volume(0.5), "LOW")

    def test_none(self):
        self.assertEqual(_interpret_volume(None), "N/A")


class TestInterpretMACD(unittest.TestCase):
    def test_bullish(self):
        self.assertEqual(_interpret_macd(2.0, 1.0, 1.0), "BULLISH")

    def test_bearish(self):
        self.assertEqual(_interpret_macd(1.0, 2.0, -0.5), "BEARISH")

    def test_neutral(self):
        self.assertEqual(_interpret_macd(1.0, 1.0, 0.0), "NEUTRAL")

    def test_none_histogram(self):
        self.assertEqual(_interpret_macd(None, None, None), "N/A")


class TestInterpretDMA200(unittest.TestCase):
    def test_above(self):
        self.assertEqual(_interpret_dma200(500.0, 400.0), "ABOVE")

    def test_below(self):
        self.assertEqual(_interpret_dma200(350.0, 400.0), "BELOW")

    def test_none(self):
        self.assertEqual(_interpret_dma200(500.0, None), "N/A")


class TestHoldingPeriod(unittest.TestCase):
    def test_tight_atr(self):
        days = _holding_period(1.5, "UP")
        self.assertGreaterEqual(days[0], 3)
        self.assertLessEqual(days[1], 30)

    def test_wide_atr(self):
        days = _holding_period(6.0, "UP")
        self.assertGreaterEqual(days[0], 10)

    def test_downtrend_reduces(self):
        up_min, up_max = _holding_period(3.0, "UP")
        down_min, down_max = _holding_period(3.0, "DOWN")
        self.assertLessEqual(down_max, up_max)


class TestEvaluateSetup(unittest.TestCase):
    def test_qualified_setup_returns_buy(self):
        setup = _make_setup(status="QUALIFIED", breakout=True)
        call = evaluate_setup(setup)
        self.assertEqual(call.action, "BUY")
        self.assertGreater(call.risk_reward, 0)
        self.assertGreater(call.holding_days_min, 0)

    def test_watch_setup_returns_watch(self):
        setup = _make_setup(status="WATCH", breakout=False, rsi14=40.0)
        call = evaluate_setup(setup)
        self.assertEqual(call.action, "WATCH")

    def test_entry_stop_target_preserved(self):
        setup = _make_setup(entry=460.0, stop=435.0, target=510.0)
        call = evaluate_setup(setup)
        self.assertEqual(call.entry, 460.0)
        self.assertEqual(call.stop_loss, 435.0)
        self.assertEqual(call.exit_target, 510.0)

    def test_volume_signal_populated(self):
        setup = _make_setup(volume_ratio=2.1)
        call = evaluate_setup(setup)
        self.assertEqual(call.volume_signal, "STRONG_BREAKOUT")

    def test_macd_signal_populated(self):
        setup = _make_setup(macd=3.0, macd_signal=1.0, macd_hist=2.0)
        call = evaluate_setup(setup)
        self.assertEqual(call.macd_signal, "BULLISH")

    def test_weekly_trend_populated(self):
        setup = _make_setup(week_trend="UP")
        call = evaluate_setup(setup)
        self.assertEqual(call.weekly_trend, "UP")

    def test_dma200_above(self):
        setup = _make_setup(close=500.0, dma200=400.0)
        call = evaluate_setup(setup)
        self.assertEqual(call.dma200_status, "ABOVE")

    def test_dma200_below(self):
        setup = _make_setup(close=350.0, dma200=400.0)
        call = evaluate_setup(setup)
        self.assertEqual(call.dma200_status, "BELOW")

    def test_rationale_empty_when_no_reasons(self):
        setup = _make_setup(
            status="WATCH",
            breakout=False, volume_ratio=0.5, rsi14=30.0,
            macd=-1.0, macd_signal=0.0, macd_hist=-1.0,
            week_trend="DOWN", dma200=999.0, catalyst_score=40,
        )
        call = evaluate_setup(setup)
        self.assertEqual(call.action, "WATCH")
        self.assertTrue(
            call.rationale.startswith("Waiting for:")
            or "catalyst" in call.rationale.lower(),
            f"Unexpected rationale: {call.rationale}",
        )

    def test_to_dict(self):
        setup = _make_setup()
        call = evaluate_setup(setup)
        d = call.to_dict()
        self.assertEqual(d["company"], "TruAlt Bioenergy")
        self.assertIn("entry", d)
        self.assertIn("exit_target", d)
        self.assertIn("holding_days", d)


class TestFormatTradeCallTelegram(unittest.TestCase):
    def test_buy_message_has_emoji_and_levels(self):
        setup = _make_setup(status="QUALIFIED", breakout=True)
        call = evaluate_setup(setup)
        msg = format_trade_call_telegram(call)
        self.assertIn("BUY SIGNAL", msg)
        self.assertIn("Entry", msg)
        self.assertIn("Target", msg)
        self.assertIn("Stop Loss", msg)
        self.assertIn("Holding", msg)

    def test_watch_message(self):
        setup = _make_setup(status="WATCH")
        call = evaluate_setup(setup)
        msg = format_trade_call_telegram(call)
        self.assertIn("WATCH", msg)

    def test_no_setup_message(self):
        call = TradeCall(
            company="IOC", symbol="IOC.NS", action="NO_SETUP"
        )
        msg = format_trade_call_telegram(call)
        self.assertIn("No swing setup", msg)


class TestFormatFinalDigest(unittest.TestCase):
    def test_empty_calls(self):
        msg = format_final_digest_telegram([])
        self.assertIn("No swing setup recommended", msg)

    def test_with_buys_and_watches(self):
        buy_setup = _make_setup(
            company="TruAlt", status="QUALIFIED", breakout=True,
            entry=460.0, stop=435.0, target=510.0,
        )
        watch_setup = _make_setup(
            company="GAIL", status="WATCH", breakout=False, rsi14=40.0,
            entry=200.0, stop=190.0, target=220.0,
        )
        calls = [evaluate_setup(buy_setup), evaluate_setup(watch_setup)]
        msg = format_final_digest_telegram(calls)
        self.assertIn("BUY signal", msg)
        self.assertIn("WATCH", msg)
        self.assertIn("Best R:R pick", msg)

    def test_only_watches_no_best_pick(self):
        setup = _make_setup(status="WATCH", breakout=False)
        call = evaluate_setup(setup)
        msg = format_final_digest_telegram([call])
        self.assertIn("WATCH", msg)
        self.assertNotIn("Best R:R pick", msg)


if __name__ == "__main__":
    unittest.main()
