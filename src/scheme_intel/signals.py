from __future__ import annotations

from typing import Optional
import pandas as pd
import yfinance as yf

from .models import SwingSetup, now_utc

# Volume breakout is confirmed when the breakout day trades at least this many
# times the trailing 20-day average volume.
VOLUME_BREAKOUT_MULT = 1.5
# MACD = EMA(12) - EMA(26); signal line = EMA(9) of MACD.
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
# Minimum weekly bars required for the higher-timeframe trend read.
WEEKLY_TREND_BARS = 10


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = -delta.clip(upper=0).rolling(period).mean()
    down_safe = down.replace(0, 1e-9)
    rs = up / down_safe
    value = 100 - (100 / (1 + rs))
    return float(value.iloc[-1])


def _macd(close: pd.Series, fast: int = MACD_FAST, slow: int = MACD_SLOW,
          signal: int = MACD_SIGNAL) -> tuple[float | None, float | None, float | None]:
    """Return (macd_line, signal_line, histogram) for the last bar, or Nones."""
    if len(close) < slow + signal:
        return None, None, None
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return (
        float(macd_line.iloc[-1]),
        float(signal_line.iloc[-1]),
        float(macd_line.iloc[-1] - signal_line.iloc[-1]),
    )


def _roc(close: pd.Series, period: int = 10) -> float | None:
    """Rate of Change indicator: (Close - Close[n]) / Close[n] * 100."""
    if len(close) <= period:
        return None
    val_prev = float(close.iloc[-period - 1])
    if val_prev <= 0:
        return None
    val_curr = float(close.iloc[-1])
    return round(((val_curr - val_prev) / val_prev) * 100.0, 2)


def _weekly_trend(frame: pd.DataFrame, bars: int = WEEKLY_TREND_BARS) -> str | None:
    """Higher-timeframe trend: last weekly close vs its (bars)-week SMA."""
    weekly = frame["Close"].resample("W-FRI").last().dropna()
    if len(weekly) < bars:
        return None
    baseline = float(weekly.tail(bars).mean())
    last_close = float(weekly.iloc[-1])
    if last_close > baseline:
        return "UP"
    if last_close < baseline:
        return "DOWN"
    return "NEUTRAL"


def _volume_stats(frame: pd.DataFrame) -> tuple[float | None, float | None]:
    """Return (prior_20d_avg_volume, breakout_day_volume_ratio)."""
    if "Volume" not in frame.columns:
        return None, None
    volumes = frame["Volume"].dropna()
    if len(volumes) < 21:
        return None, None
    prior = volumes.iloc[-21:-1]
    if float(prior.mean()) <= 0:
        return None, None
    avg = float(prior.mean())
    current = float(volumes.iloc[-1]) or 0.0
    return round(avg, 0), round(current / avg, 2)


def _atr_and_regime(frame: pd.DataFrame, period: int = 14) -> tuple[float, float, str]:
    """
    Calculate True Range, 14-period ATR, ATR % of current close,
    and the volatility regime (LOW, NORMAL, HIGH, EXTREME).
    """
    high = frame["High"]
    low = frame["Low"]
    close = frame["Close"]
    last_close = float(close.iloc[-1]) if float(close.iloc[-1]) > 0 else 1.0

    # True range = max(H - L, |H - C_prev|, |L - C_prev|)
    c_prev = close.shift(1)
    tr1 = high - low
    tr2 = (high - c_prev).abs()
    tr3 = (low - c_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = float(tr.tail(period).mean())
    atr_pct = round((atr / last_close) * 100.0, 2)

    if atr_pct < 2.0:
        regime = "LOW"
    elif atr_pct <= 4.5:
        regime = "NORMAL"
    elif atr_pct <= 7.0:
        regime = "HIGH"
    else:
        regime = "EXTREME"

    return round(atr, 2), atr_pct, regime


def _price_structure(frame: pd.DataFrame, window: int = 20) -> tuple[float, float, float, float]:
    """
    Compute price support, resistance, recent swing low, and swing high
    over the lookback window.
    """
    highs = frame["High"].tail(window)
    lows = frame["Low"].tail(window)
    resistance = float(highs.max())
    support = float(lows.min())
    swing_high = float(highs.iloc[-window // 2:].max())
    swing_low = float(lows.iloc[-window // 2:].min())
    return round(support, 2), round(resistance, 2), round(swing_low, 2), round(swing_high, 2)


def _relative_strength_vs_benchmark(
    stock_close: pd.Series,
    benchmark_close: pd.Series | None = None,
    period: int = 20,
) -> float | None:
    """
    Compute 20-period relative strength outperformance vs benchmark (e.g. NIFTY 50).
    """
    if len(stock_close) <= period:
        return None
    s_curr = float(stock_close.iloc[-1])
    s_prev = float(stock_close.iloc[-period - 1])
    if s_prev <= 0:
        return None
    stock_ret = ((s_curr - s_prev) / s_prev) * 100.0

    if benchmark_close is not None and len(benchmark_close) > period:
        b_curr = float(benchmark_close.iloc[-1])
        b_prev = float(benchmark_close.iloc[-period - 1])
        if b_prev > 0:
            bm_ret = ((b_curr - b_prev) / b_prev) * 100.0
            return round(stock_ret - bm_ret, 2)

    return round(stock_ret, 2)


def make_setup(
    company: str,
    symbol: str,
    catalyst_score: int,
    history: list[dict] | None = None,
    dma200: float | None = None,
    benchmark_history: list[dict] | None = None,
) -> SwingSetup | None:
    """
    Build a swing setup for a company from daily OHLC history.

    Calculates comprehensive Stage 1 technical metrics:
      * Trend: 20 DMA, 50 DMA, 100 DMA, 200 DMA.
      * Momentum: RSI(14), MACD(12,26,9), ROC(10), ROC(21).
      * Breakout: 20-day high, 50-day high, volume breakout ratio, breakout distance %.
      * Volatility: ATR(14), ATR %, volatility regime.
      * Price Structure: support, resistance, swing high, swing low.
      * Relative Strength: stock vs benchmark over 20 days.
      * Multi-timeframe: daily trend vs 10-week SMA.
    """
    if history is not None:
        frame = pd.DataFrame(history)
        frame = frame.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })
        for col in ("Open", "High", "Low", "Close", "Volume"):
            if col in frame.columns:
                frame[col] = pd.to_numeric(frame[col], errors="coerce")
        if "date" in frame.columns:
            frame.index = pd.to_datetime(frame["date"], errors="coerce")
            frame = frame.drop(columns=["date"])
        frame = frame[frame.index.notna()].dropna(subset=["Close"]).sort_index()
    else:
        frame = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True)

    if len(frame) < 60:
        return None

    close = frame["Close"]
    last = float(close.iloc[-1])

    # Trend moving averages
    sma20 = float(close.tail(20).mean())
    sma50 = float(close.tail(50).mean())
    sma100 = float(close.tail(100).mean()) if len(close) >= 100 else None
    computed_dma200 = float(close.tail(200).mean()) if len(close) >= 200 else None
    effective_dma200 = dma200 if dma200 is not None else computed_dma200

    # Momentum
    rsi14 = _rsi(close)
    macd, macd_signal, macd_hist = _macd(close)
    roc10 = _roc(close, period=10)
    roc21 = _roc(close, period=21)

    # Volatility
    atr14, atr_pct, vol_regime = _atr_and_regime(frame, period=14)

    # Breakout levels
    prior_high20 = float(frame["High"].iloc[-21:-1].max()) if len(frame) >= 21 else float(frame["High"].max())
    prior_high50 = float(frame["High"].iloc[-51:-1].max()) if len(frame) >= 51 else prior_high20
    breakout = last > prior_high20
    breakout_dist_pct = round(((last - prior_high20) / prior_high20) * 100.0, 2) if prior_high20 > 0 else 0.0

    # Volume & Higher-timeframe
    volume_avg, volume_ratio = _volume_stats(frame)
    week_trend = _weekly_trend(frame)

    # Price Structure
    support, resistance, swing_low, swing_high = _price_structure(frame, window=20)

    # Relative strength
    bm_close = None
    if benchmark_history:
        bm_df = pd.DataFrame(benchmark_history)
        if "close" in bm_df.columns:
            bm_close = pd.to_numeric(bm_df["close"], errors="coerce")
        elif "Close" in bm_df.columns:
            bm_close = pd.to_numeric(bm_df["Close"], errors="coerce")
    rs_nifty = _relative_strength_vs_benchmark(close, bm_close, period=20)

    # Qualification criteria
    momentum = last > sma20 > sma50
    rsi_ok = 50 <= rsi14 <= 70
    volume_ok = volume_ratio is None or volume_ratio >= VOLUME_BREAKOUT_MULT
    macd_ok = macd_hist is None or macd_hist > 0
    trend_ok = week_trend in (None, "UP")
    dma200_ok = effective_dma200 is None or last > effective_dma200

    qualified = (
        momentum and breakout and rsi_ok and volume_ok and macd_ok
        and trend_ok and dma200_ok and catalyst_score >= 60
    )
    status = "QUALIFIED" if qualified else "WATCH"

    # Trade levels
    trigger = max(last, float(frame["High"].tail(20).max()))
    stop = max(trigger - (2 * atr14), trigger * 0.94)
    target = trigger + (2 * (trigger - stop))

    return SwingSetup(
        company=company,
        symbol=symbol,
        close=round(last, 2),
        entry=round(trigger, 2),
        stop=round(stop, 2),
        target=round(target, 2),
        rsi14=round(rsi14, 1),
        catalyst_score=catalyst_score,
        status=status,
        generated_at=now_utc().isoformat(),
        prior_high20=round(prior_high20, 2),
        breakout=breakout,
        volume_avg=volume_avg,
        volume_ratio=volume_ratio,
        macd=round(macd, 3) if macd is not None else None,
        macd_signal=round(macd_signal, 3) if macd_signal is not None else None,
        macd_hist=round(macd_hist, 4) if macd_hist is not None else None,
        week_trend=week_trend,
        dma200=round(effective_dma200, 2) if effective_dma200 is not None else None,
        sma100=round(sma100, 2) if sma100 is not None else None,
        roc10=roc10,
        roc21=roc21,
        prior_high50=round(prior_high50, 2),
        breakout_dist_pct=breakout_dist_pct,
        atr_pct=atr_pct,
        volatility_regime=vol_regime,
        support=support,
        resistance=resistance,
        swing_high=swing_high,
        swing_low=swing_low,
        rs_nifty=rs_nifty,
    )
