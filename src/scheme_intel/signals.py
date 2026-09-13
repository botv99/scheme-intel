from __future__ import annotations

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


def _weekly_trend(frame: pd.DataFrame, bars: int = WEEKLY_TREND_BARS) -> str | None:
    """Higher-timeframe trend: last weekly close vs its (bars)-week SMA.

    Weekly bars are resampled from daily closes (Friday-anchored), so no extra
    data source is needed. Returns None when there is not enough weekly data.
    """
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


def make_setup(company: str, symbol: str, catalyst_score: int,
               history: list[dict] | None = None) -> SwingSetup | None:
    """
    Build a swing setup for a company from daily OHLC history.

    Args:
        company: Company display name.
        symbol: Yahoo Finance symbol (e.g. ``PRAJIND.NS``).
        catalyst_score: Materiality score of the triggering catalyst.
        history: Optional pre-fetched OHLC rows (date/open/high/low/close/volume
            or Date/Open/High/Low/Close/Volume). When provided, the (potentially
            slow/blocked) live yfinance call is skipped; otherwise history is
            fetched from Yahoo Finance directly.

    Returns:
        A SwingSetup, or None when there is not enough history.

    Technical checks applied before a setup qualifies:
      * Price above the 20/50-day SMAs (momentum) with RSI(14) in 50-70.
      * Volume breakout: close above the prior 20-day high, confirmed by volume
        at least VOLUME_BREAKOUT_MULT times the trailing 20-day average.
      * MACD(12,26,9) filter: histogram positive (MACD line above its signal).
      * Multi-timeframe: the weekly close must be above its 10-week SMA
        (SKIPPED, not blocking, when weekly data is too short).
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
        frame = yf.Ticker(symbol).history(period="6mo", interval="1d", auto_adjust=True)
    if len(frame) < 60:
        return None

    close = frame["Close"]
    last = float(close.iloc[-1])
    sma20, sma50 = float(close.tail(20).mean()), float(close.tail(50).mean())
    rsi14 = _rsi(close)
    atr14 = float((frame["High"] - frame["Low"]).tail(14).mean())
    prior_high20 = float(frame["High"].iloc[-21:-1].max())
    breakout = last > prior_high20
    volume_avg, volume_ratio = _volume_stats(frame)
    macd, macd_signal, macd_hist = _macd(close)
    week_trend = _weekly_trend(frame)

    momentum = last > sma20 > sma50
    rsi_ok = 50 <= rsi14 <= 70
    volume_ok = volume_ratio is None or volume_ratio >= VOLUME_BREAKOUT_MULT
    macd_ok = macd_hist is None or macd_hist > 0
    # A missing higher-timeframe read never blocks qualification.
    trend_ok = week_trend in (None, "UP")
    qualified = (
        momentum and breakout and rsi_ok and volume_ok and macd_ok
        and trend_ok and catalyst_score >= 60
    )
    status = "QUALIFIED" if qualified else "WATCH"

    # Entry is only actionable after a confirmed close above the prior 20-day high.
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
    )


