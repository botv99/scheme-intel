"""
Strategy Subsystem.
Covers swing setup candidate detection, archetypes, risk management, waiting triggers, and scanning.
"""
from .archetypes import SetupArchetype
from .candidate import find_candidate_setup
from .risk import evaluate_risk_assessment
from .waiting import generate_waiting_conditions
from .scanner import scan_all_stocks

__all__ = [
    "SetupArchetype",
    "find_candidate_setup",
    "evaluate_risk_assessment",
    "generate_waiting_conditions",
    "scan_all_stocks",
]
