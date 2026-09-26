"""
Hard Mathematical Risk Engine.
Strict mathematical risk gates, stop distance veto, position sizing, and R:R checks.
"""
from __future__ import annotations

from ..stage2.risk import evaluate_risk_assessment

__all__ = ["evaluate_risk_assessment"]
