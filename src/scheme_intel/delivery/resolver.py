"""
Re-export of deterministic IntentResolver for delivery package convenience.
"""
from ..intelligence_memory.resolver import (
    IntentResolver,
    IntentType,
    ResolvedIntent,
    ExecutionPath,
    GLOBAL_STOCK_ALIASES,
    STOCK_SLASH_SHORTCUTS,
)

__all__ = [
    "IntentResolver",
    "IntentType",
    "ResolvedIntent",
    "ExecutionPath",
    "GLOBAL_STOCK_ALIASES",
    "STOCK_SLASH_SHORTCUTS",
]
