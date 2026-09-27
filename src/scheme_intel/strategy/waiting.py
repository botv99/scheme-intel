"""
Waiting Engine Module.
Generates actionable trigger conditions and invalidation levels for WAIT setups.
"""
from __future__ import annotations

from ..stage2.waiting import generate_wait_condition

generate_waiting_conditions = generate_wait_condition

__all__ = ["generate_wait_condition", "generate_waiting_conditions"]
