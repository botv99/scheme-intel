"""
Common Technical Indicators and Volatility Calculations.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple


def calculate_sma(prices: List[float], period: int) -> Optional[float]:
    if len(prices) < period or period <= 0:
        return None
    return sum(prices[-period:]) / period


def calculate_ema(prices: List[float], period: int) -> Optional[float]:
    if len(prices) < period or period <= 0:
        return None
    multiplier = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p - ema) * multiplier + ema
    return ema


def calculate_rsi(prices: List[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    n = min(len(highs), len(lows), len(closes))
    if n < 2:
        return 0.0
    trs: List[float] = []
    for i in range(1, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    if not trs:
        return 0.0
    if len(trs) < period:
        return sum(trs) / len(trs)
    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    return round(atr, 2)


def calculate_macd(prices: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if len(prices) < 26:
        return None, None, None
    fast = calculate_ema(prices, 12)
    slow = calculate_ema(prices, 26)
    if fast is None or slow is None:
        return None, None, None
    macd_line = fast - slow

    macd_series: List[float] = []
    for end_idx in range(26, len(prices) + 1):
        sub = prices[:end_idx]
        f = calculate_ema(sub, 12)
        s = calculate_ema(sub, 26)
        if f is not None and s is not None:
            macd_series.append(f - s)

    if len(macd_series) < 9:
        return round(macd_line, 2), None, None
    signal = calculate_ema(macd_series, 9)
    hist = (macd_line - signal) if signal is not None else None
    return (
        round(macd_line, 2),
        round(signal, 2) if signal is not None else None,
        round(hist, 2) if hist is not None else None,
    )


def calculate_roc(prices: List[float], period: int) -> Optional[float]:
    if len(prices) < period + 1 or prices[-period - 1] == 0:
        return None
    return round(((prices[-1] - prices[-period - 1]) / prices[-period - 1]) * 100.0, 2)
