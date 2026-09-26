"""
Waiting Engine Module.
Generates actionable trigger conditions and invalidation levels for WAIT setups.
"""
from __future__ import annotations

from ..stage2.waiting import generate_waiting_conditions

__all__ = ["generate_waiting_conditions"]
