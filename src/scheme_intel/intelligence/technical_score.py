"""
Technical Intelligence Score Engine (Stage 3).
Calculates deterministic 0.0-10.0 technical intelligence score from OHLCV data.
This is an information layer, NOT a predictive trading signal or strategy trigger.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from ..logger import get_logger

logger = get_logger(__name__)

TECHNICAL_SCORE_VERSION = "v1.0"

# Standard component weights (sum to 1.00)
DEFAULT_WEIGHTS = {
    "trend": 0.20,
    "momentum": 0.15,
    "structure": 0.15,
    "volume": 0.15,
    "relative_strength": 0.10,
    "volatility_structure": 0.10,
    "market_regime": 0.10,
    "price_action": 0.05,
}


@dataclass
class ComponentScore:
    """Individual technical score component report."""
    name: str
    score: Optional[float]
    weight: float
    data_available: bool
    value: Any = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 1) if self.score is not None else None,
            "weight": self.weight,
            "data_available": self.data_available,
            "value": self.value,
            "reason": self.reason,
        }


@dataclass
class TechnicalScoreResult:
    """Full Technical Intelligence Score result container."""
    score: Optional[float]                          # 0.0 - 10.0 or None if insufficient coverage
    version: str = TECHNICAL_SCORE_VERSION
    calculated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data_as_of: Optional[str] = None
    coverage_pct: float = 0.0                      # Percentage of total weight available
    min_coverage_pct: float = 60.0
    status: str = "VALID"                          # VALID, INSUFFICIENT_COVERAGE, ERROR
    reason: Optional[str] = None
    components: Dict[str, ComponentScore] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "version": self.version,
            "calculated_at": self.calculated_at,
            "data_as_of": self.data_as_of,
            "coverage_pct": self.coverage_pct,
            "min_coverage_pct": self.min_coverage_pct,
            "status": self.status,
            "reason": self.reason,
            "components": {k: v.to_dict() for k, v in self.components.items()},
        }


class TechnicalScoreEngine:
    """
    Deterministic quantitative technical intelligence scoring engine.
    Produces an explainable 0.0–10.0 score based on 8 weighted technical dimensions.
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        min_coverage_pct: float = 60.0,
    ):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self.min_coverage_pct = min_coverage_pct

    def calculate(
        self,
        bars: List[Dict[str, Any]],
        benchmark_bars: Optional[List[Dict[str, Any]]] = None,
        market_regime: Optional[str] = None,
    ) -> TechnicalScoreResult:
        """
        Calculate Technical Intelligence Score from historical daily OHLCV bars.

        Args:
            bars: List of dicts with Open, High, Low, Close, Volume, and Date.
            benchmark_bars: Optional benchmark (e.g. Nifty 50) bars for relative strength.
            market_regime: Optional market context ("BULLISH", "NEUTRAL", "BEARISH").
        """
        now_str = datetime.now(timezone.utc).isoformat()
        if not bars or len(bars) < 5:
            return TechnicalScoreResult(
                score=None,
                version=TECHNICAL_SCORE_VERSION,
                calculated_at=now_str,
                data_as_of=None,
                coverage_pct=0.0,
                min_coverage_pct=self.min_coverage_pct,
                status="INSUFFICIENT_COVERAGE",
                reason="Insufficient technical history (fewer than 5 bars available).",
                components={},
            )

        df = self._to_dataframe(bars)
        if df.empty or len(df) < 5:
            return TechnicalScoreResult(
                score=None,
                version=TECHNICAL_SCORE_VERSION,
                calculated_at=now_str,
                data_as_of=None,
                coverage_pct=0.0,
                min_coverage_pct=self.min_coverage_pct,
                status="INSUFFICIENT_COVERAGE",
                reason="Invalid or unparseable price bars.",
                components={},
            )

        data_as_of = str(df["Date"].iloc[-1])[:10] if "Date" in df.columns else None

        # 1. TREND (20%)
        trend_comp = self._eval_trend(df)

        # 2. MOMENTUM (15%)
        momentum_comp = self._eval_momentum(df)

        # 3. PRICE STRUCTURE / BREAKOUT (15%)
        structure_comp = self._eval_structure(df)

        # 4. VOLUME CONFIRMATION (15%)
        volume_comp = self._eval_volume(df)

        # 5. RELATIVE STRENGTH (10%)
        rs_comp = self._eval_relative_strength(df, benchmark_bars)

        # 6. VOLATILITY / RISK STRUCTURE (10%)
        vol_comp = self._eval_volatility(df)

        # 7. MARKET REGIME / CONTEXT (10%)
        regime_comp = self._eval_market_regime(market_regime, benchmark_bars)

        # 8. PRICE ACTION QUALITY (5%)
        pa_comp = self._eval_price_action(df)

        components = {
            "trend": trend_comp,
            "momentum": momentum_comp,
            "structure": structure_comp,
            "volume": volume_comp,
            "relative_strength": rs_comp,
            "volatility_structure": vol_comp,
            "market_regime": regime_comp,
            "price_action": pa_comp,
        }

        # Calculate coverage and weighted score
        total_weight = sum(self.weights.values())
        available_weight = sum(self.weights[k] for k, c in components.items() if c.data_available and c.score is not None)
        coverage_pct = round((available_weight / total_weight) * 100.0, 1)

        if coverage_pct < self.min_coverage_pct:
            return TechnicalScoreResult(
                score=None,
                version=TECHNICAL_SCORE_VERSION,
                calculated_at=now_str,
                data_as_of=data_as_of,
                coverage_pct=coverage_pct,
                min_coverage_pct=self.min_coverage_pct,
                status="INSUFFICIENT_COVERAGE",
                reason=f"Insufficient technical history. Data coverage ({coverage_pct}%) is below minimum required ({self.min_coverage_pct}%).",
                components=components,
            )

        # Re-normalize across valid available components
        weighted_sum = sum(
            c.score * self.weights[k]
            for k, c in components.items()
            if c.data_available and c.score is not None
        )
        normalized_score = weighted_sum / available_weight
        final_score = round(max(0.0, min(10.0, normalized_score)), 1)

        return TechnicalScoreResult(
            score=final_score,
            version=TECHNICAL_SCORE_VERSION,
            calculated_at=now_str,
            data_as_of=data_as_of,
            coverage_pct=coverage_pct,
            min_coverage_pct=self.min_coverage_pct,
            status="VALID",
            reason=None,
            components=components,
        )

    # -------------------------------------------------------------------------
    # Component Evaluators
    # -------------------------------------------------------------------------

    def _eval_trend(self, df: pd.DataFrame) -> ComponentScore:
        weight = self.weights["trend"]
        n = len(df)
        close = df["Close"]
        last_close = float(close.iloc[-1])

        if n < 10:
            return ComponentScore("trend", None, weight, False, reason="Need at least 10 bars for trend assessment")

        sma20 = float(close.tail(20).mean()) if n >= 20 else float(close.mean())
        ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1]) if n >= 20 else sma20
        has_50 = n >= 50
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1]) if has_50 else None
        has_200 = n >= 150
        sma200 = float(close.tail(200).mean()) if n >= 200 else (float(close.mean()) if has_200 else None)

        score_points = 0.0
        max_possible = 0.0

        # Price vs 20 EMA
        max_possible += 3.0
        if last_close > ema20 * 1.01:
            score_points += 3.0
        elif last_close >= ema20 * 0.99:
            score_points += 2.0
        else:
            dist = (last_close - ema20) / ema20
            score_points += max(0.0, 1.5 + dist * 10)

        # 20 EMA vs 50 EMA (Medium-term trend)
        if has_50 and ema50 is not None:
            max_possible += 4.0
            if ema20 > ema50 * 1.01:
                score_points += 4.0
            elif ema20 >= ema50 * 0.99:
                score_points += 2.5
            else:
                score_points += 0.5
        else:
            # Scaled on shorter history
            max_possible += 2.0
            p10 = float(close.iloc[-10]) if n >= 10 else float(close.iloc[0])
            if last_close > p10:
                score_points += 2.0
            else:
                score_points += 0.5

        # Long term (200 SMA)
        if has_200 and sma200 is not None:
            max_possible += 3.0
            if last_close > sma200:
                score_points += 3.0
            else:
                score_points += 0.5

        trend_score = min(10.0, max(0.0, (score_points / max_possible) * 10.0))
        reason = f"Price ₹{last_close:,.2f} vs EMA20 ₹{ema20:,.2f}"
        if ema50 is not None:
            reason += f", EMA50 ₹{ema50:,.2f}"

        return ComponentScore(
            name="trend",
            score=round(trend_score, 1),
            weight=weight,
            data_available=True,
            value={"ema20": round(ema20, 2), "ema50": round(ema50, 2) if ema50 else None, "sma200": round(sma200, 2) if sma200 else None},
            reason=reason,
        )

    def _eval_momentum(self, df: pd.DataFrame) -> ComponentScore:
        weight = self.weights["momentum"]
        n = len(df)
        close = df["Close"]

        if n < 15:
            return ComponentScore("momentum", None, weight, False, reason="Need at least 15 bars for RSI/MACD")

        # 14-period RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).tail(14).mean()
        loss = (-delta.where(delta < 0, 0)).tail(14).mean()
        if loss == 0:
            rsi = 100.0
        else:
            rs = gain / loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        # MACD (12, 26, 9)
        if n >= 26:
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd_val = float(macd_line.iloc[-1])
            sig_val = float(signal_line.iloc[-1])
            hist_val = macd_val - sig_val
        else:
            macd_val = None
            sig_val = None
            hist_val = None

        # Bounded RSI scoring model:
        # 55-68 is optimal bullish momentum
        if 55 <= rsi <= 68:
            rsi_score = 9.0 + (rsi - 55) / 13.0
        elif 50 <= rsi < 55:
            rsi_score = 7.5
        elif 45 <= rsi < 50:
            rsi_score = 6.0
        elif 68 < rsi <= 75:
            rsi_score = 8.0  # strong but hot
        elif rsi > 75:
            rsi_score = 5.5  # overbought / exhaustion risk
        elif 35 <= rsi < 45:
            rsi_score = 4.0  # weak momentum
        elif 25 <= rsi < 35:
            rsi_score = 4.5  # oversold bounce candidate
        else:
            rsi_score = 2.0  # deep breakdown

        # MACD confirmation
        if hist_val is not None:
            if macd_val > sig_val and hist_val > 0:
                macd_score = 9.0 if macd_val > 0 else 7.5
            elif macd_val > sig_val and hist_val <= 0:
                macd_score = 6.5
            elif macd_val <= sig_val and hist_val < 0:
                macd_score = 3.0 if macd_val < 0 else 4.5
            else:
                macd_score = 5.0
            momentum_score = 0.60 * rsi_score + 0.40 * macd_score
        else:
            momentum_score = rsi_score

        return ComponentScore(
            name="momentum",
            score=round(min(10.0, max(0.0, momentum_score)), 1),
            weight=weight,
            data_available=True,
            value={"rsi14": round(rsi, 1), "macd_hist": round(hist_val, 3) if hist_val is not None else None},
            reason=f"RSI(14) at {rsi:.1f}" + (f", MACD hist {hist_val:+.3f}" if hist_val is not None else ""),
        )

    def _eval_structure(self, df: pd.DataFrame) -> ComponentScore:
        weight = self.weights["structure"]
        n = len(df)
        close = df["Close"]
        highs = df["High"]
        lows = df["Low"]
        last_close = float(close.iloc[-1])

        if n < 10:
            return ComponentScore("structure", None, weight, False, reason="Need at least 10 bars for price structure")

        lookback_20 = min(n - 1, 20)
        high_20 = float(highs.iloc[-lookback_20 - 1:-1].max()) if lookback_20 >= 5 else float(highs.max())
        low_20 = float(lows.iloc[-lookback_20 - 1:-1].min()) if lookback_20 >= 5 else float(lows.min())

        # Proximity to 20-day high vs low
        rng = high_20 - low_20
        if rng > 0:
            pos_ratio = (last_close - low_20) / rng
        else:
            pos_ratio = 0.5

        # Higher High / Higher Low check over recent 10 bars
        if n >= 10:
            first_half_high = float(highs.iloc[-10:-5].max())
            second_half_high = float(highs.iloc[-5:].max())
            first_half_low = float(lows.iloc[-10:-5].min())
            second_half_low = float(lows.iloc[-5:].min())

            hh = second_half_high >= first_half_high
            hl = second_half_low >= first_half_low
            lh = second_half_high < first_half_high
            ll = second_half_low < first_half_low
        else:
            hh, hl, lh, ll = False, False, False, False

        # Structure score calculation
        score = pos_ratio * 7.0
        if hh and hl:
            score += 3.0  # Clear higher high & higher low constructive structure
        elif hh or hl:
            score += 1.5
        elif lh and ll:
            score = max(1.0, score - 2.0)  # Downward structure

        # Breakout to new high bonus
        if last_close >= high_20 * 0.99:
            score = max(score, 8.5)

        return ComponentScore(
            name="structure",
            score=round(min(10.0, max(0.0, score)), 1),
            weight=weight,
            data_available=True,
            value={"high_20d": round(high_20, 2), "low_20d": round(low_20, 2), "pos_in_range_pct": round(pos_ratio * 100, 1)},
            reason=f"Position in 20D range: {pos_ratio*100:.1f}% (20D High ₹{high_20:,.2f})",
        )

    def _eval_volume(self, df: pd.DataFrame) -> ComponentScore:
        weight = self.weights["volume"]
        n = len(df)
        if "Volume" not in df.columns or n < 5:
            return ComponentScore("volume", None, weight, False, reason="Missing volume history")

        vol = df["Volume"]
        today_vol = float(vol.iloc[-1])
        if today_vol <= 0:
            return ComponentScore("volume", None, weight, False, reason="Zero or invalid volume data")

        avg_vol_20 = float(vol.tail(20).mean()) if n >= 20 else float(vol.mean())
        if avg_vol_20 <= 0:
            return ComponentScore("volume", None, weight, False, reason="Zero 20D average volume")

        vol_ratio = today_vol / avg_vol_20
        close = df["Close"]
        day_chg = ((float(close.iloc[-1]) - float(close.iloc[-2])) / float(close.iloc[-2])) * 100.0 if n >= 2 else 0.0

        # Evaluate volume confirmation: Volume must support price action
        if day_chg > 0:
            # Positive price movement
            if vol_ratio >= 2.0:
                score = 10.0
            elif vol_ratio >= 1.5:
                score = 8.5
            elif vol_ratio >= 1.0:
                score = 7.0
            else:
                score = 5.5  # Low volume up day
        elif day_chg < 0:
            # Negative price movement
            if vol_ratio >= 2.0:
                score = 1.5  # Heavy volume distribution
            elif vol_ratio >= 1.5:
                score = 3.0
            elif vol_ratio >= 1.0:
                score = 4.5
            else:
                score = 6.0  # Light volume pullback (constructive)
        else:
            score = 5.0

        return ComponentScore(
            name="volume",
            score=round(min(10.0, max(0.0, score)), 1),
            weight=weight,
            data_available=True,
            value={"volume_ratio": round(vol_ratio, 2), "day_change_pct": round(day_chg, 2)},
            reason=f"Volume ratio {vol_ratio:.2f}x 20D avg on {day_chg:+.2f}% day",
        )

    def _eval_relative_strength(
        self, df: pd.DataFrame, benchmark_bars: Optional[List[Dict[str, Any]]]
    ) -> ComponentScore:
        weight = self.weights["relative_strength"]
        if not benchmark_bars or len(benchmark_bars) < 10 or len(df) < 10:
            return ComponentScore("relative_strength", None, weight, False, reason="Benchmark data not available")

        b_df = self._to_dataframe(benchmark_bars)
        if b_df.empty or len(b_df) < 10:
            return ComponentScore("relative_strength", None, weight, False, reason="Insufficient benchmark bars")

        lookback = min(len(df), len(b_df), 20)
        s_close = df["Close"]
        b_close = b_df["Close"]

        s_ret = ((float(s_close.iloc[-1]) - float(s_close.iloc[-lookback])) / float(s_close.iloc[-lookback])) * 100.0
        b_ret = ((float(b_close.iloc[-1]) - float(b_close.iloc[-lookback])) / float(b_close.iloc[-lookback])) * 100.0
        excess = s_ret - b_ret

        if excess >= 10.0:
            score = 10.0
        elif excess >= 5.0:
            score = 8.5
        elif excess >= 0.0:
            score = 6.5
        elif excess >= -5.0:
            score = 4.5
        else:
            score = 2.0

        return ComponentScore(
            name="relative_strength",
            score=round(min(10.0, max(0.0, score)), 1),
            weight=weight,
            data_available=True,
            value={"excess_return_pct": round(excess, 2), "lookback_days": lookback},
            reason=f"Alpha vs Nifty: {excess:+.2f}% over {lookback}D",
        )

    def _eval_volatility(self, df: pd.DataFrame) -> ComponentScore:
        weight = self.weights["volatility_structure"]
        n = len(df)
        if n < 10:
            return ComponentScore("volatility_structure", None, weight, False, reason="Need at least 10 bars for ATR")

        highs = df["High"]
        lows = df["Low"]
        close = df["Close"]
        c_prev = close.shift(1)
        tr = pd.concat([highs - lows, (highs - c_prev).abs(), (lows - c_prev).abs()], axis=1).max(axis=1)

        atr14 = float(tr.tail(14).mean()) if n >= 14 else float(tr.mean())
        last_close = float(close.iloc[-1])
        atr_pct = (atr14 / last_close) * 100.0 if last_close > 0 else 0.0

        # Stable constructive trend should score higher than chaotic volatility
        if 1.5 <= atr_pct <= 3.8:
            score = 9.0  # Healthy constructive trading range
        elif atr_pct < 1.5:
            score = 7.5  # Low volatility consolidation
        elif 3.8 < atr_pct <= 5.5:
            score = 6.0  # Moderate elevated volatility
        elif 5.5 < atr_pct <= 7.5:
            score = 4.0  # High volatility risk
        else:
            score = 2.0  # Extreme erratic volatility

        return ComponentScore(
            name="volatility_structure",
            score=round(min(10.0, max(0.0, score)), 1),
            weight=weight,
            data_available=True,
            value={"atr_pct": round(atr_pct, 2), "atr14": round(atr14, 2)},
            reason=f"ATR% {atr_pct:.2f}% (constructive volatility regime)",
        )

    def _eval_market_regime(
        self, market_regime: Optional[str], benchmark_bars: Optional[List[Dict[str, Any]]]
    ) -> ComponentScore:
        weight = self.weights["market_regime"]
        if market_regime:
            reg = market_regime.upper()
            if reg in ("BULLISH", "EXPANSION", "RISK_ON"):
                score = 9.0
            elif reg in ("NEUTRAL", "CONSOLIDATION"):
                score = 6.0
            elif reg in ("BEARISH", "CONTRACTION", "RISK_OFF"):
                score = 3.0
            else:
                score = 5.0
            return ComponentScore("market_regime", score, weight, True, value=reg, reason=f"Market regime: {reg}")

        if benchmark_bars and len(benchmark_bars) >= 20:
            b_df = self._to_dataframe(benchmark_bars)
            b_close = b_df["Close"]
            b_sma20 = float(b_close.tail(20).mean())
            last_b = float(b_close.iloc[-1])
            if last_b > b_sma20 * 1.01:
                score = 8.5
                reg = "BULLISH"
            elif last_b >= b_sma20 * 0.99:
                score = 6.0
                reg = "NEUTRAL"
            else:
                score = 3.5
                reg = "BEARISH"
            return ComponentScore("market_regime", score, weight, True, value=reg, reason=f"Nifty trend {reg} vs 20 SMA")

        return ComponentScore("market_regime", None, weight, False, reason="Market regime data not provided")

    def _eval_price_action(self, df: pd.DataFrame) -> ComponentScore:
        weight = self.weights["price_action"]
        n = len(df)
        if n < 1:
            return ComponentScore("price_action", None, weight, False, reason="No price bar")

        high = float(df["High"].iloc[-1])
        low = float(df["Low"].iloc[-1])
        close = float(df["Close"].iloc[-1])
        open_p = float(df["Open"].iloc[-1])

        rng = high - low
        if rng <= 0:
            return ComponentScore("price_action", 5.0, weight, True, value=5.0, reason="Flat price range")

        close_pos = (close - low) / rng  # 0.0 (low) to 1.0 (high)

        # Body vs wick
        body = abs(close - open_p)
        body_ratio = body / rng

        # Score based on close position and candle quality
        if close_pos >= 0.80:
            score = 9.5 if close >= open_p else 7.5  # Strong finish near highs
        elif close_pos >= 0.60:
            score = 7.5
        elif close_pos >= 0.40:
            score = 5.5
        elif close_pos >= 0.20:
            score = 3.5
        else:
            score = 2.0  # Weak finish near session lows

        return ComponentScore(
            name="price_action",
            score=round(min(10.0, max(0.0, score)), 1),
            weight=weight,
            data_available=True,
            value={"close_position_pct": round(close_pos * 100, 1), "body_ratio": round(body_ratio, 2)},
            reason=f"Closed at {close_pos*100:.1f}% of daily range",
        )

    def _to_dataframe(self, bars: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert list of bar dicts to normalized pandas DataFrame."""
        if not bars:
            return pd.DataFrame()
        norm_rows = []
        for b in bars:
            o = b.get("Open") or b.get("open")
            h = b.get("High") or b.get("high")
            l = b.get("Low") or b.get("low")
            c = b.get("Close") or b.get("close")
            v = b.get("Volume") or b.get("volume") or 0.0
            d = b.get("Date") or b.get("date") or ""
            if None not in (o, h, l, c):
                try:
                    norm_rows.append({
                        "Date": str(d),
                        "Open": float(o),
                        "High": float(h),
                        "Low": float(l),
                        "Close": float(c),
                        "Volume": float(v),
                    })
                except (ValueError, TypeError):
                    continue
        if not norm_rows:
            return pd.DataFrame()
        df = pd.DataFrame(norm_rows)
        if "Date" in df.columns and df["Date"].iloc[0]:
            try:
                df["Date_dt"] = pd.to_datetime(df["Date"])
                df = df.sort_values("Date_dt").reset_index(drop=True)
            except Exception:
                pass
        return df
