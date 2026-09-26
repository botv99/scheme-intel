"""
GOBARdhan / SATAT Scheme Official Information Sources.
Includes government ministries, PIB feeds, and scheme-specific portals.
"""
from __future__ import annotations

from typing import List
from ..models import SchemeSource

GOBARDHAN_SOURCES: List[SchemeSource] = [
    SchemeSource(
        id="pib_mopng",
        name="PIB Ministry of Petroleum & Natural Gas",
        type="rss",
        url="https://pib.gov.in/RssMain.aspx?ModId=2&MinId=30",
        tier=1,
        enabled=True,
        poll_interval_hours=2,
        categories=["policy", "satat", "cbg", "ethanol"],
    ),
    SchemeSource(
        id="gobardhan_portal",
        name="GOBARdhan Unified Registration Portal",
        type="html",
        url="https://gobardhan.co.in",
        tier=1,
        enabled=True,
        poll_interval_hours=4,
        categories=["registration", "subsidies", "plant_approvals"],
    ),
    SchemeSource(
        id="mnre_feed",
        name="Ministry of New and Renewable Energy",
        type="rss",
        url="https://mnre.gov.in/feed/",
        tier=1,
        enabled=True,
        poll_interval_hours=4,
        categories=["bio-energy", "renewable", "policy"],
    ),
    SchemeSource(
        id="jal_shakti",
        name="Ministry of Jal Shakti",
        type="html",
        url="https://jalshakti-ddws.gov.in",
        tier=2,
        enabled=True,
        poll_interval_hours=6,
        categories=["swachh_bharat", "slurry", "rural_sanitation"],
    ),
    SchemeSource(
        id="cppp_tenders",
        name="Central Public Procurement Portal (tenders)",
        type="tender",
        url="https://eprocure.gov.in/cppp/",
        tier=2,
        enabled=True,
        poll_interval_hours=6,
        categories=["cbg_tenders", "epc_contracts"],
    ),
]

SOURCES = GOBARDHAN_SOURCES

