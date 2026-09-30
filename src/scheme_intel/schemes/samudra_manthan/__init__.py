"""
Samudra Manthan Scheme Package (Stage 4).
National Offshore Exploration Scheme covering deepwater, ultra-deepwater,
OALP blocks, seismic surveys, and offshore drilling.
"""
from __future__ import annotations

from .config import SAMUDRA_MANTHAN_CONFIG, SAMUDRA_STRUCTURED_KNOWLEDGE, SAMUDRA_RULES
from .watchlist import SAMUDRA_WATCHLIST, SAMUDRA_RELATIONSHIPS, WATCHLIST, RELATIONSHIPS
from .sources import SAMUDRA_SOURCES, SOURCES
from .mapping import (
    SAMUDRA_KEYWORDS,
    SAMUDRA_ENTITIES,
    SAMUDRA_COMPANY_MAPPINGS,
    SAMUDRA_EVENT_TAXONOMY,
    COMPANY_KEYWORDS,
)
from .rules import SamudraRulesEngine, DynamicBeneficiaryDiscovery

__all__ = [
    "SAMUDRA_MANTHAN_CONFIG",
    "SAMUDRA_STRUCTURED_KNOWLEDGE",
    "SAMUDRA_RULES",
    "SAMUDRA_WATCHLIST",
    "SAMUDRA_RELATIONSHIPS",
    "WATCHLIST",
    "RELATIONSHIPS",
    "SAMUDRA_SOURCES",
    "SOURCES",
    "SAMUDRA_KEYWORDS",
    "SAMUDRA_ENTITIES",
    "SAMUDRA_COMPANY_MAPPINGS",
    "SAMUDRA_EVENT_TAXONOMY",
    "COMPANY_KEYWORDS",
    "SamudraRulesEngine",
    "DynamicBeneficiaryDiscovery",
]
