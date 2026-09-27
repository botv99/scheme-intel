"""
Hard Mathematical Risk Engine.
Strict mathematical risk gates, stop distance veto, position sizing, and R:R checks.
"""
from __future__ import annotations

from ..stage2.risk import evaluate_risk

evaluate_risk_assessment = evaluate_risk

__all__ = ["evaluate_risk", "evaluate_risk_assessment"]
