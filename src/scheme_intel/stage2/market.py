"""
Market Data & Volume Engine for Stage 2.
Calculates comprehensive price, volume, momentum, trend, and relative strength metrics.
Supports both live production ingestion (Stage 1 price layer) and deterministic mock data.
"""
from __future__ import annotations

from typing import Optional, Dict, Any, List
import numpy as np
import pandas as pd

from .models import TechnicalSnapshot
from ..logger import get_logger

logger = get_logger(__name__)


def _to_dataframe(history: list[dict] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(history, pd.DataFrame):
        df = history.copy()
    else:
        df = pd.DataFrame(history)

    rename_map = {
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    }
    df = df.rename(columns=rename_map)
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "date" in df.columns:
        df.index = pd.to_datetime(df["date"], errors="coerce")
    elif "Date" in df.columns:
        df.index = pd.to_datetime(df["Date"], errors="coerce")

    return df.dropna(subset=["Close"]).sort_index()


def _rsi(close: pd.Series, period: int = 14) -> float:
    if len(close) < period + 1:
        return 50.0
    delta = close.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = -delta.clip(upper=0).rolling(period).mean()
    down_safe = down.replace(0, 1e-9)
    rs = up / down_safe
    val = 100 - (100 / (1 + rs))
    return float(val.iloc[-1])


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float | None, float | None, float | None]:
    if len(close) < slow + signal:
        return None, None, None
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return (
        float(macd_line.iloc[-1]),
        float(signal_line.iloc[-1]),
        float((macd_line - signal_line).iloc[-1]),
    )


def _bollinger_bands(close: pd.Series, period: int = 20, num_std: float = 2.0) -> tuple[float, float, float]:
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    return float(upper.iloc[-1]), float(sma.iloc[-1]), float(lower.iloc[-1])


def _adx(df: pd.DataFrame, period: int = 14) -> float | None:
    if len(df) < period * 2:
        return None
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(period).mean() / atr.replace(0, 1e-9))
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(period).mean() / atr.replace(0, 1e-9))

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)).fillna(0)
    adx_val = dx.rolling(period).mean().iloc[-1]
    return round(float(adx_val), 1) if not np.isnan(adx_val) else None


def build_technical_snapshot(
    history: list[dict] | pd.DataFrame,
    benchmark_history: Optional[list[dict] | pd.DataFrame] = None,
    sector_history: Optional[list[dict] | pd.DataFrame] = None,
) -> TechnicalSnapshot:
    """
    Build a comprehensive TechnicalSnapshot from OHLCV history.
    """
    df = _to_dataframe(history)
    if len(df) < 20:
        raise ValueError("At least 20 bars of history required for technical snapshot")

    close = df["Close"]
    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) >= 2 else last_close
    open_p = float(df["Open"].iloc[-1])
    high_p = float(df["High"].iloc[-1])
    low_p = float(df["Low"].iloc[-1])

    # Performance
    day_chg = round(((last_close - prev_close) / prev_close) * 100.0, 2) if prev_close else 0.0
    gap = round(((open_p - prev_close) / prev_close) * 100.0, 2) if prev_close else 0.0
    p5d = round(((last_close - float(close.iloc[-6])) / float(close.iloc[-6])) * 100.0, 2) if len(close) >= 6 else 0.0
    p20d = round(((last_close - float(close.iloc[-21])) / float(close.iloc[-21])) * 100.0, 2) if len(close) >= 21 else 0.0
    p1m = round(((last_close - float(close.iloc[-22])) / float(close.iloc[-22])) * 100.0, 2) if len(close) >= 22 else p20d
    p3m = round(((last_close - float(close.iloc[-64])) / float(close.iloc[-64])) * 100.0, 2) if len(close) >= 64 else 0.0

    # Volume
    today_vol = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0.0
    vol_series = df["Volume"].dropna() if "Volume" in df.columns else pd.Series()
    vol20_avg = float(vol_series.iloc[-21:-1].mean()) if len(vol_series) >= 21 else float(vol_series.mean() or 1.0)
    vol50_avg = float(vol_series.iloc[-51:-1].mean()) if len(vol_series) >= 51 else vol20_avg
    vol_ratio = round(today_vol / vol20_avg, 2) if vol20_avg > 0 else 1.0
    rel_vol = round(today_vol / vol50_avg, 2) if vol50_avg > 0 else vol_ratio

    # Moving Averages
    sma20 = round(float(close.tail(20).mean()), 2)
    sma50 = round(float(close.tail(50).mean()), 2) if len(close) >= 50 else round(float(close.mean()), 2)
    sma100 = round(float(close.tail(100).mean()), 2) if len(close) >= 100 else None
    sma200 = round(float(close.tail(200).mean()), 2) if len(close) >= 200 else None
    ema20 = round(float(close.ewm(span=20, adjust=False).mean().iloc[-1]), 2)
    ema50 = round(float(close.ewm(span=50, adjust=False).mean().iloc[-1]), 2) if len(close) >= 50 else None

    # Momentum
    rsi14 = round(_rsi(close, 14), 1)
    macd, macd_sig, macd_hist = _macd(close)
    roc10 = round(((last_close - float(close.iloc[-11])) / float(close.iloc[-11])) * 100.0, 2) if len(close) >= 11 else None
    roc21 = round(((last_close - float(close.iloc[-22])) / float(close.iloc[-22])) * 100.0, 2) if len(close) >= 22 else None

    # Volatility
    highs = df["High"]
    lows = df["Low"]
    c_prev = close.shift(1)
    tr = pd.concat([highs - lows, (highs - c_prev).abs(), (lows - c_prev).abs()], axis=1).max(axis=1)
    atr14 = round(float(tr.tail(14).mean()), 2)
    atr_pct = round((atr14 / last_close) * 100.0, 2) if last_close else 0.0

    if atr_pct < 2.0:
        vol_regime = "LOW"
    elif atr_pct <= 4.5:
        vol_regime = "NORMAL"
    elif atr_pct <= 7.0:
        vol_regime = "HIGH"
    else:
        vol_regime = "EXTREME"

    # Bollinger & ADX
    bb_u, bb_m, bb_l = _bollinger_bands(close, 20, 2.0)
    adx14 = _adx(df, 14)

    # Structure
    high_20d = round(float(highs.iloc[-21:-1].max()), 2) if len(highs) >= 21 else round(float(highs.max()), 2)
    high_50d = round(float(highs.iloc[-51:-1].max()), 2) if len(highs) >= 51 else high_20d
    resistance = round(float(highs.tail(20).max()), 2)
    support = round(float(lows.tail(20).min()), 2)
    swing_high = round(float(highs.tail(10).max()), 2)
    swing_low = round(float(lows.tail(10).min()), 2)

    # Relative Strength
    rs_nifty = None
    if benchmark_history is not None:
        b_df = _to_dataframe(benchmark_history)
        if len(b_df) >= 21:
            b_close = b_df["Close"]
            b_ret = ((float(b_close.iloc[-1]) - float(b_close.iloc[-21])) / float(b_close.iloc[-21])) * 100.0
            rs_nifty = round(p20d - b_ret, 2)

    rs_sector = None
    if sector_history is not None:
        s_df = _to_dataframe(sector_history)
        if len(s_df) >= 21:
            s_close = s_df["Close"]
            s_ret = ((float(s_close.iloc[-1]) - float(s_close.iloc[-21])) / float(s_close.iloc[-21])) * 100.0
            rs_sector = round(p20d - s_ret, 2)

    # Trend status
    if last_close > sma20 and sma20 > sma50:
        trend = "BULLISH"
    elif last_close < sma20 and sma20 < sma50:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    return TechnicalSnapshot(
        close=round(last_close, 2),
        open=round(open_p, 2),
        high=round(high_p, 2),
        low=round(low_p, 2),
        prev_close=round(prev_close, 2),
        day_change_pct=day_chg,
        gap_pct=gap,
        performance_5d=p5d,
        performance_20d=p20d,
        performance_1m=p1m,
        performance_3m=p3m,
        volume=today_vol,
        volume_20d_avg=round(vol20_avg, 0),
        volume_50d_avg=round(vol50_avg, 0),
        volume_ratio=vol_ratio,
        relative_volume=rel_vol,
        sma20=sma20,
        sma50=sma50,
        sma100=sma100,
        sma200=sma200,
        ema20=ema20,
        ema50=ema50,
        rsi14=rsi14,
        macd=round(macd, 3) if macd is not None else None,
        macd_signal=round(macd_sig, 3) if macd_sig is not None else None,
        macd_hist=round(macd_hist, 4) if macd_hist is not None else None,
        roc10=roc10,
        roc21=roc21,
        atr14=atr14,
        atr_pct=atr_pct,
        volatility_regime=vol_regime,
        bb_upper=round(bb_u, 2),
        bb_middle=round(bb_m, 2),
        bb_lower=round(bb_l, 2),
        adx14=adx14,
        high_20d=high_20d,
        high_50d=high_50d,
        support=support,
        resistance=resistance,
        swing_high=swing_high,
        swing_low=swing_low,
        relative_strength_nifty=rs_nifty,
        relative_strength_sector=rs_sector,
        trend_status=trend,
    )


class MarketDataEngine:
    """
    Market Data & Technical Snapshot Engine for Stage 2.
    Explicitly distinguishes production mode (real Stage 1 ingestion) from mock mode.
    """

    def __init__(
        self,
        price_lookup: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        mode: str = "production",
    ):
        self.price_lookup = price_lookup or {}
        self.mode = mode

    def get_snapshot(self, symbol: str) -> Optional[TechnicalSnapshot]:
        """Fetch snapshot for symbol using production sources or mock fallback."""
        if symbol in self.price_lookup:
            return build_technical_snapshot(self.price_lookup[symbol])

        if self.mode == "production":
            # Attempt to retrieve live OHLCV price history from Stage 1 ingestion
            try:
                from ..ingestion.price import get_stock_history
                bars = get_stock_history(symbol, days=120)
                if bars and len(bars) >= 20:
                    return build_technical_snapshot(bars)
            except Exception as e:
                logger.debug("Stage 1 live price ingestion unavailable for %s (%s)", symbol, e)

            # In production, do NOT silently generate synthetic breakout data if live feed is absent
            return None

        # Mode == 'mock': Return deterministic offline test snapshot
        return self._generate_default_snapshot(symbol)

    def _generate_default_snapshot(self, symbol: str) -> TechnicalSnapshot:
        """Create deterministic, realistic snapshot for offline testing."""
        sym = symbol.upper()
        if "PRAJ" in sym:
            # Bullish Breakout profile
            close = 522.50
            return TechnicalSnapshot(
                close=close,
                open=508.0,
                high=526.0,
                low=506.0,
                prev_close=505.0,
                day_change_pct=3.47,
                performance_5d=6.2,
                performance_20d=14.5,
                volume=450_000,
                volume_20d_avg=250_000,
                volume_ratio=1.80,
                sma20=495.0,
                sma50=465.0,
                rsi14=63.5,
                atr14=16.5,
                atr_pct=3.15,
                high_20d=525.0,
                resistance=525.0,
                support=495.0,
                trend_status="BULLISH",
            )
        elif "WABAG" in sym:
            # Consolidating / Pullback profile with confirmed primary uptrend
            close = 1240.0
            return TechnicalSnapshot(
                close=close,
                open=1245.0,
                high=1255.0,
                low=1232.0,
                prev_close=1242.0,
                day_change_pct=-0.16,
                performance_5d=-1.2,
                performance_20d=4.1,
                volume=85_000,
                volume_20d_avg=95_000,
                volume_ratio=0.89,
                sma20=1230.0,
                sma50=1180.0,
                rsi14=54.0,
                atr14=32.0,
                atr_pct=2.58,
                high_20d=1285.0,
                resistance=1285.0,
                support=1210.0,
                trend_status="BULLISH",
            )
        elif "TRUALT" in sym:
            # Breakout Anticipation profile
            close = 185.0
            return TechnicalSnapshot(
                close=close,
                open=182.0,
                high=187.0,
                low=181.0,
                prev_close=181.5,
                day_change_pct=1.93,
                performance_5d=3.8,
                performance_20d=10.2,
                volume=120_000,
                volume_20d_avg=105_000,
                volume_ratio=1.14,
                sma20=178.0,
                sma50=168.0,
                rsi14=58.2,
                atr14=5.5,
                atr_pct=2.97,
                high_20d=190.0,
                resistance=190.0,
                support=176.0,
                trend_status="BULLISH",
            )
        else:
            # Generic baseline
            close = 250.0
            return TechnicalSnapshot(
                close=close,
                open=248.0,
                high=252.0,
                low=247.0,
                prev_close=249.0,
                day_change_pct=0.40,
                performance_5d=0.8,
                performance_20d=1.5,
                volume=50_000,
                volume_20d_avg=55_000,
                volume_ratio=0.91,
                sma20=248.0,
                sma50=252.0,
                rsi14=49.0,
                atr14=6.0,
                atr_pct=2.40,
                high_20d=262.0,
                resistance=262.0,
                support=242.0,
                trend_status="NEUTRAL",
            )
