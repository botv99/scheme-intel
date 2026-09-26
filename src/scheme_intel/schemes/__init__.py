"""
Schemes Subsystem.
Provides multi-scheme configuration, isolation, and registry.
"""
from .models import SchemeConfig, SchemeSource, SchemeStock
from .registry import SchemeRegistry
from .gobardhan import GOBARDHAN_CONFIG

# Auto-register default GOBARdhan scheme
SchemeRegistry.register(GOBARDHAN_CONFIG)

__all__ = [
    "SchemeConfig",
    "SchemeSource",
    "SchemeStock",
    "SchemeRegistry",
    "GOBARDHAN_CONFIG",
]
