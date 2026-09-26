"""
Swing Setup Archetypes and Definitions.
"""
from __future__ import annotations

from enum import Enum


class SetupArchetype(str, Enum):
    BREAKOUT = "Breakout"
    BREAKOUT_ANTICIPATION = "Breakout Anticipation"
    PULLBACK = "Pullback"
    MOMENTUM_CONTINUATION = "Momentum Continuation"
    EVENT_DRIVEN = "Event-Driven"
