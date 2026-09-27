"""
Deterministic Unit Tests for Technical Intelligence Score Engine (Stage 3).
Verifies:
  - Strong uptrend & downtrend
  - High-volume & low-volume breakouts
  - Momentum deterioration & oversold recovery
  - Insufficient history & missing volume/benchmark
  - Incomplete component re-normalization
  - Range boundaries (0.0 <= score <= 10.0)
  - Version ("v1.0") and coverage calculation
"""
import pytest
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from scheme_intel.intelligence.technical_score import (
    TechnicalScoreEngine,
    TECHNICAL_SCORE_VERSION,
)


def _generate_bars(
    count: int = 60,
    start_price: float = 100.0,
    daily_gain_pct: float = 0.5,
    volume_base: float = 100000.0,
    volume_last: Optional[float] = None,
    start_date: Optional[datetime] = None,
) -> list[dict]:
    """Helper to generate synthetic daily OHLCV bars."""
    bars = []
    price = start_price
    base_date = start_date or datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(count):
        date_str = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        vol = volume_base
        if i == count - 1 and volume_last is not None:
            vol = volume_last
        open_p = price
        close_p = round(price * (1.0 + daily_gain_pct / 100.0), 2)
        high_p = round(max(open_p, close_p) * 1.01, 2)
        low_p = round(min(open_p, close_p) * 0.99, 2)
        bars.append({
            "Date": date_str,
            "Open": open_p,
            "High": high_p,
            "Low": low_p,
            "Close": close_p,
            "Volume": vol,
        })
        price = close_p
    return bars


class TestTechnicalScoreEngine:
    def setup_method(self):
        self.engine = TechnicalScoreEngine()

    def test_version_field(self):
        assert TECHNICAL_SCORE_VERSION == "v1.0"
        bars = _generate_bars(30)
        res = self.engine.calculate(bars)
        assert res.version == "v1.0"

    def test_strong_uptrend(self):
        # 60 consecutive rising bars with healthy volume
        bars = _generate_bars(count=60, start_price=100.0, daily_gain_pct=0.6, volume_base=50000.0)
        res = self.engine.calculate(bars)
        assert res.score is not None
        assert res.score >= 7.5, f"Expected strong uptrend score >= 7.5, got {res.score}"
        assert res.components["trend"].score is not None
        assert res.components["trend"].score >= 8.0

    def test_strong_downtrend(self):
        # 60 consecutive falling bars
        bars = _generate_bars(count=60, start_price=200.0, daily_gain_pct=-0.8, volume_base=50000.0)
        res = self.engine.calculate(bars)
        assert res.score is not None
        assert res.score <= 4.0, f"Expected downtrend score <= 4.0, got {res.score}"
        assert res.components["trend"].score is not None
        assert res.components["trend"].score <= 3.0

    def test_high_volume_breakout(self):
        # 50 flat bars followed by large positive surge on 3x volume
        bars = _generate_bars(count=50, start_price=100.0, daily_gain_pct=0.0, volume_base=50000.0)
        # Final breakout bar
        bars.append({
            "Date": "2026-09-25",
            "Open": 100.0,
            "High": 108.0,
            "Low": 99.5,
            "Close": 107.5,
            "Volume": 160000.0,  # >3x average
        })
        res = self.engine.calculate(bars)
        assert res.score is not None
        assert res.components["volume"].score is not None
        assert res.components["volume"].score >= 9.0
        assert res.components["structure"].score is not None
        assert res.components["structure"].score >= 8.0

    def test_low_volume_breakout(self):
        # Breakout on 0.5x volume (low confirmation)
        bars = _generate_bars(count=50, start_price=100.0, daily_gain_pct=0.0, volume_base=50000.0)
        bars.append({
            "Date": "2026-09-25",
            "Open": 100.0,
            "High": 106.0,
            "Low": 99.5,
            "Close": 105.0,
            "Volume": 20000.0,  # 0.4x volume
        })
        res = self.engine.calculate(bars)
        assert res.score is not None
        assert res.components["volume"].score is not None
        assert res.components["volume"].score <= 6.0

    def test_momentum_deterioration(self):
        # Rising prices but last 15 days rolling over
        bars = _generate_bars(count=40, start_price=100.0, daily_gain_pct=1.0)
        start_drop = datetime(2026, 7, 1, tzinfo=timezone.utc) + timedelta(days=40)
        bars_drop = _generate_bars(
            count=15,
            start_price=bars[-1]["Close"],
            daily_gain_pct=-1.2,
            start_date=start_drop,
        )
        all_bars = bars + bars_drop
        res = self.engine.calculate(all_bars)
        assert res.score is not None
        assert res.components["momentum"].score is not None
        assert res.components["momentum"].score <= 4.5

    def test_oversold_recovery(self):
        # Deep sell-off then first bullish reversal candle
        bars = _generate_bars(count=30, start_price=150.0, daily_gain_pct=-1.5)
        bars.append({
            "Date": "2026-09-25",
            "Open": 95.0,
            "High": 102.0,
            "Low": 94.0,
            "Close": 101.5,
            "Volume": 120000.0,
        })
        res = self.engine.calculate(bars)
        assert res.score is not None
        assert res.components["price_action"].score is not None
        assert res.components["price_action"].score >= 8.0

    def test_insufficient_history(self):
        # Only 3 bars -> should return None score with reason
        bars = _generate_bars(count=3)
        res = self.engine.calculate(bars)
        assert res.score is None
        assert res.status == "INSUFFICIENT_COVERAGE"
        assert res.coverage_pct < 60.0
        assert "Insufficient technical history" in (res.reason or "")

    def test_missing_volume_handled_gracefully(self):
        # Bars with 0 or missing volume
        bars = _generate_bars(count=30)
        for b in bars:
            b["Volume"] = 0.0
        res = self.engine.calculate(bars)
        # Should re-normalize across remaining components without crashing
        assert res.components["volume"].data_available is False
        assert res.score is not None
        assert 0.0 <= res.score <= 10.0

    def test_missing_benchmark_renormalizes(self):
        bars = _generate_bars(count=30)
        res_no_bench = self.engine.calculate(bars, benchmark_bars=None)
        assert res_no_bench.components["relative_strength"].data_available is False
        assert res_no_bench.coverage_pct < 100.0
        assert res_no_bench.score is not None
        assert 0.0 <= res_no_bench.score <= 10.0

        # With benchmark
        bench_bars = _generate_bars(count=30, start_price=20000.0, daily_gain_pct=0.1)
        res_with_bench = self.engine.calculate(bars, benchmark_bars=bench_bars)
        assert res_with_bench.components["relative_strength"].data_available is True
        assert res_with_bench.coverage_pct >= 90.0

    def test_score_always_bounded_between_0_and_10(self):
        # Extreme volatility and giant numbers
        bars_huge = _generate_bars(count=40, start_price=10.0, daily_gain_pct=15.0)
        res = self.engine.calculate(bars_huge)
        assert 0.0 <= res.score <= 10.0

        bars_crash = _generate_bars(count=40, start_price=1000.0, daily_gain_pct=-15.0)
        res_crash = self.engine.calculate(bars_crash)
        assert 0.0 <= res_crash.score <= 10.0

    def test_deterministic_output(self):
        bars = _generate_bars(count=35, start_price=120.0, daily_gain_pct=0.3)
        res1 = self.engine.calculate(bars)
        res2 = self.engine.calculate(bars)
        assert res1.score == res2.score
        assert res1.coverage_pct == res2.coverage_pct
        for k in res1.components:
            assert res1.components[k].score == res2.components[k].score
