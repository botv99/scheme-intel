"""
Outcomes Subsystem.
Covers trade execution monitoring, MFE/MAE tracking, and outcome persistence.
"""
from .models import SetupOutcome
from .tracker import OutcomeTracker

__all__ = [
    "SetupOutcome",
    "OutcomeTracker",
]
