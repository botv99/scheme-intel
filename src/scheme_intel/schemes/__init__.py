"""
Schemes Subsystem.
Provides multi-scheme configuration, isolation, and registry.
"""
from .models import (
    SchemeConfig,
    SchemeSource,
    SchemeStock,
    BeneficiaryRelationshipType,
    CompanyWatchlistStatus,
    CompanySchemeRelationship,
)
from .registry import SchemeRegistry
from .gobardhan import GOBARDHAN_CONFIG
from .samudra_manthan import SAMUDRA_MANTHAN_CONFIG

# Auto-register default schemes
SchemeRegistry.register(GOBARDHAN_CONFIG)
SchemeRegistry.register(SAMUDRA_MANTHAN_CONFIG)

__all__ = [
    "SchemeConfig",
    "SchemeSource",
    "SchemeStock",
    "BeneficiaryRelationshipType",
    "CompanyWatchlistStatus",
    "CompanySchemeRelationship",
    "SchemeRegistry",
    "GOBARDHAN_CONFIG",
    "SAMUDRA_MANTHAN_CONFIG",
]
