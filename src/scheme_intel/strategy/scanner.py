"""
Watchlist Scanner Module.
Scans 100% of watchlist stocks and generates DailyStockCards.
"""
from __future__ import annotations

from ..stage2.scanner import scan_all_stocks

__all__ = ["scan_all_stocks"]
