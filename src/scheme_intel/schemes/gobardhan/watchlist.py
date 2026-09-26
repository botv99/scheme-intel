"""
GOBARdhan / Bio-CBG Scheme Watchlist.
7 focused stocks across bio-energy, ethanol technology, water treatment, and infrastructure.
"""
from __future__ import annotations

from typing import List
from ..models import SchemeStock

GOBARDHAN_WATCHLIST: List[SchemeStock] = [
    SchemeStock(
        name="Praj Industries",
        symbol="PRAJIND.NS",
        aliases=["Praj", "Praj Ind"],
        screener_id="PRAJIND",
        sectors=["Bio-Energy", "Engineering"],
        rationale="Leading technology provider for 1G/2G ethanol, CBG (Compressed Bio-Gas), and brewery plants.",
    ),
    SchemeStock(
        name="TruAlt Bioenergy",
        symbol="TRUALT.NS",
        aliases=["TruAlt", "Trualt Bio"],
        screener_id="TRUALT",
        sectors=["Bio-Energy", "Ethanol"],
        rationale="Largest ethanol producer in India; major CBG plant setup under SATAT scheme.",
    ),
    SchemeStock(
        name="Ion Exchange",
        symbol="IONEXCHANG.NS",
        aliases=["Ion Exchange India", "IEIL"],
        screener_id="IONEXCHANG",
        sectors=["Water Treatment", "Waste Management"],
        rationale="Water treatment and effluent management for bio-CNG plants; Gobardhan slurry handling.",
    ),
    SchemeStock(
        name="VA Tech Wabag",
        symbol="WABAG.NS",
        aliases=["Wabag", "VA Tech"],
        screener_id="WABAG",
        sectors=["Water Treatment", "Infrastructure"],
        rationale="Municipal and industrial wastewater-to-energy projects; biogas generation from sewage.",
    ),
    SchemeStock(
        name="Kirloskar Pneumatic",
        symbol="KIRLPNU.NS",
        aliases=["KPCL", "Kirloskar Pneum"],
        screener_id="KIRLPNU",
        sectors=["Compressors", "Gas Systems"],
        rationale="Gas compressors for CNG/CBG booster stations, essential for SATAT grid injection.",
    ),
    SchemeStock(
        name="GAIL (India)",
        symbol="GAIL.NS",
        aliases=["GAIL India", "GAIL"],
        screener_id="GAIL",
        sectors=["Gas Utility", "Infrastructure"],
        rationale="National gas grid operator; mandated CBG offtake under SATAT; setting up 500+ CBG plants.",
    ),
    SchemeStock(
        name="Indian Oil Corporation",
        symbol="IOC.NS",
        aliases=["IOCL", "Indian Oil"],
        screener_id="IOC",
        sectors=["Oil Marketing", "Energy"],
        rationale="Largest OMC with CBG offtake agreements (IndiGreen brand); SATAT commercial offtake.",
    ),
]

WATCHLIST = GOBARDHAN_WATCHLIST
