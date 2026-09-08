from __future__ import annotations

import math

import pandas as pd
import yfinance as yf

from .models import SwingSetup


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = -delta.clip(upper=0).rolling(period).mean()
    down_safe = down.replace(0, 1e-9)
    rs = up / down_safe
    value = 100 - (100 / (1 + rs))
    return float(value.iloc[-1])


def make_setup(company: str, symbol: str, catalyst_score: int) -> SwingSetup | None:
    history = yf.Ticker(symbol).history(period="6mo", interval="1d", auto_adjust=True)
    if len(history) < 60:
        return None
    close = history["Close"]
    last = float(close.iloc[-1])
    sma20, sma50 = float(close.tail(20).mean()), float(close.tail(50).mean())
    rsi14 = _rsi(close)
    atr14 = float((history["High"] - history["Low"]).tail(14).mean())
    momentum = last > sma20 > sma50 and 50 <= rsi14 <= 70
    status = "QUALIFIED" if momentum and catalyst_score >= 60 else "WATCH"
    # Entry is only actionable after a confirmed close above the prior 20-day high.
    trigger = max(last, float(history["High"].tail(20).max()))
    stop = max(trigger - (2 * atr14), trigger * 0.94)
    target = trigger + (2 * (trigger - stop))
    return SwingSetup(company, symbol, round(last, 2), round(trigger, 2), round(stop, 2),
                      round(target, 2), round(rsi14, 1), catalyst_score, status,
                      pd.Timestamp.utcnow().isoformat())


