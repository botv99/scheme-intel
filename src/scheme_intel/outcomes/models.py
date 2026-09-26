"""
Outcome Models and Data Contracts.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class SetupOutcome(BaseModel):
    setup_id: str
    symbol: str
    entry_triggered: bool = False
    actual_entry_price: Optional[float] = None
    entry_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    realized_pnl_pct: Optional[float] = None
    target_hit: bool = False
    stop_hit: bool = False
    expired: bool = False
    holding_period_days: int = 0
