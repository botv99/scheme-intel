"""
Catalyst Impact Scoring Module.
Evaluates strength, certainty, duration, and priced-in status.
"""
from __future__ import annotations

from ..stage2.impact import evaluate_stock_catalysts

__all__ = ["evaluate_stock_catalysts"]
