"""
GOBARdhan Scheme Configuration Object.
"""
from __future__ import annotations

from ..models import SchemeConfig
from .watchlist import GOBARDHAN_WATCHLIST
from .sources import GOBARDHAN_SOURCES
from .mapping import (
    GOBARDHAN_KEYWORDS,
    GOBARDHAN_ENTITIES,
    GOBARDHAN_COMPANY_MAPPINGS,
    GOBARDHAN_EVENT_TAXONOMY,
)

GOBARDHAN_CONFIG = SchemeConfig(
    id="gobardhan",
    name="GOBARdhan (Galvanizing Organic Bio-Agro Resources Dhan)",
    enabled=True,
    description="Government umbrella initiative covering CBG, Bio-CNG, SATAT, and organic bio-fertilizer commercialization.",
    ministries=[
        "Ministry of Petroleum and Natural Gas (MoPNG)",
        "Ministry of New and Renewable Energy (MNRE)",
        "Ministry of Jal Shakti (DDWS)",
        "Ministry of Agriculture & Farmers Welfare",
        "Department of Fertilisers",
    ],
    sources=GOBARDHAN_SOURCES,
    watchlist=GOBARDHAN_WATCHLIST,
    keywords=GOBARDHAN_KEYWORDS,
    entities=GOBARDHAN_ENTITIES,
    industries=["Bio-Energy", "Water & Waste Management", "Oil & Gas Distribution", "Industrial Machinery"],
    company_mappings=GOBARDHAN_COMPANY_MAPPINGS,
    event_taxonomy=GOBARDHAN_EVENT_TAXONOMY,
)
