"""
Structured Entity Models and Taxonomy for Samudra Manthan (Stage 4B).
Covers:
- Sedimentary basins and offshore exploration blocks
- OALP bidding round catalog and context
- Water depth classification (strictly verified depth rules)
- Joint venture and contract entity models
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WaterDepthCategory(str, Enum):
    """
    Water depth classification strictly based on verified physical measurements or official designations.
    RULE: Never infer deepwater merely from the word 'offshore'.
    """
    SHALLOW = "SHALLOW"                   # < 400 meters
    DEEPWATER = "DEEPWATER"               # 400 - 1500 meters
    ULTRA_DEEPWATER = "ULTRA_DEEPWATER"   # > 1500 meters
    UNKNOWN = "UNKNOWN"                   # Unverified water depth

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.value.lower() == other.lower()
        if isinstance(other, WaterDepthCategory):
            return self.value == other.value
        return super().__eq__(other)


class SedimentaryBasinCategory(str, Enum):
    """Category classification of Indian sedimentary basins (DGH classification)."""
    CATEGORY_I = "CATEGORY_I"     # Established commercial production (KG, Mumbai Offshore, Cambay, Assam Shelf, Rajasthan, Cauvery)
    CATEGORY_II = "CATEGORY_II"   # Known accumulation, no commercial production yet (Mahanadi, Andaman-Nicobar, Saurashtra, Kutch)
    CATEGORY_III = "CATEGORY_III" # Prospective basins / frontier (Kerala-Konkan, Bengal)


class ProjectBlockEntity(BaseModel):
    """Structured representation of an offshore block or development project."""
    block_id: str                                  # e.g., "KG-DWN-98/2", "MB-OSHP-2023/1"
    name: str = ""                                 # e.g., "Cluster-2 Deepwater Block"
    basin: str                                     # e.g., "Krishna-Godavari", "Mumbai Offshore", "Andaman"
    operator: str                                  # e.g., "ONGC", "Oil India", "Reliance Industries"
    jv_partners: List[str] = Field(default_factory=list) # e.g., ["BP", "Indian Oil"]
    water_depth: WaterDepthCategory = WaterDepthCategory.UNKNOWN
    water_depth_meters: Optional[float] = None
    oalp_round: Optional[str] = None               # e.g., "OALP-VIII", "OALP-IX"
    award_date: Optional[str] = None
    status: str = "ACTIVE"                         # "EXPLORATION", "APPRAISAL", "DEVELOPMENT", "PRODUCING", "RELINQUISHED"
    activity: str = ""                             # e.g., "Drilling 3 deepwater wells"
    contract_type: str = "RSC"                     # RSC (Revenue Sharing Contract) or PSC (Production Sharing Contract)


class TenderRecord(BaseModel):
    """Structured offshore procurement tender record."""
    tender_id: str
    issuer: str                                    # e.g., "ONGC", "OIL", "DGH"
    title: str
    scope: str = ""
    published_date: Optional[str] = None
    closing_date: Optional[str] = None
    estimated_value_cr: Optional[float] = None
    location: str = ""
    category: str = "DRILLING"                     # DRILLING, SEISMIC, SUBSEA, RIG_CHARTER, EPC, OSV, SERVICES
    status: str = "OPEN"                           # OPEN, CLOSED, AWARDED, CANCELLED
    winner: Optional[str] = None
    award_date: Optional[str] = None
    contract_value_cr: Optional[float] = None


class OALPRoundModel(BaseModel):
    """Structured OALP Bidding Round context."""
    round_name: str                                # e.g., "OALP Round IX"
    blocks_offered: int = 0
    onshore_blocks: int = 0
    shallow_water_blocks: int = 0
    deepwater_blocks: int = 0
    ultra_deepwater_blocks: int = 0
    bid_start_date: Optional[str] = None
    bid_closing_date: Optional[str] = None
    award_status: str = "IN_PROGRESS"              # "BIDDING", "EVALUATING", "AWARDED"


# Known Major Offshore Sedimentary Basins
MAJOR_OFFSHORE_BASINS: Dict[str, Dict[str, Any]] = {
    "KRISHNA_GODAVARI": {
        "name": "Krishna-Godavari (KG) Basin",
        "category": SedimentaryBasinCategory.CATEGORY_I.value,
        "region": "East Coast",
        "key_blocks": ["KG-DWN-98/2", "KG-D6", "KG-OSN-2009/1", "KG-DWN-98/3"],
        "known_operators": ["ONGC", "Reliance Industries"],
    },
    "MUMBAI_OFFSHORE": {
        "name": "Mumbai Offshore / Mumbai High",
        "category": SedimentaryBasinCategory.CATEGORY_I.value,
        "region": "West Coast",
        "key_blocks": ["Mumbai High", "Bassein", "Neelam-Heera", "B-127"],
        "known_operators": ["ONGC"],
    },
    "CAMBAY_OFFSHORE": {
        "name": "Cambay Offshore",
        "category": SedimentaryBasinCategory.CATEGORY_I.value,
        "region": "West Coast",
        "key_blocks": ["CB-OS/2", "CB-OSN-2003/1"],
        "known_operators": ["Vedanta", "Cairn Oil & Gas", "ONGC"],
    },
    "MAHANADI": {
        "name": "Mahanadi Offshore Basin",
        "category": SedimentaryBasinCategory.CATEGORY_II.value,
        "region": "East Coast",
        "key_blocks": ["MN-OSN-2000/2", "MN-DWN-98/2"],
        "known_operators": ["Oil India", "ONGC"],
    },
    "ANDAMAN_NICOBAR": {
        "name": "Andaman-Nicobar Deepwater Basin",
        "category": SedimentaryBasinCategory.CATEGORY_II.value,
        "region": "Frontier Island Arc",
        "key_blocks": ["AN-DWN-2002/1", "AN-OSHP-2018/1"],
        "known_operators": ["Oil India", "ONGC"],
    },
    "CAUVERY_OFFSHORE": {
        "name": "Cauvery Offshore Basin",
        "category": SedimentaryBasinCategory.CATEGORY_I.value,
        "region": "East Coast",
        "key_blocks": ["CY-OS-90/1", "CY-DWN-2001/1"],
        "known_operators": ["ONGC"],
    },
}


def classify_water_depth_strict(text_or_meters: Any) -> WaterDepthCategory:
    """
    Classify water depth with strict verification.
    NEVER infer deepwater merely from 'offshore'.
    - SHALLOW: < 400 meters
    - DEEPWATER: 400 - 1500 meters
    - ULTRA_DEEPWATER: > 1500 meters
    - UNKNOWN: when depth measurement is absent
    """
    if isinstance(text_or_meters, (int, float)):
        if text_or_meters > 1500:
            return WaterDepthCategory.ULTRA_DEEPWATER
        elif text_or_meters >= 400:
            return WaterDepthCategory.DEEPWATER
        elif text_or_meters > 0:
            return WaterDepthCategory.SHALLOW
        return WaterDepthCategory.UNKNOWN

    raw = str(text_or_meters or "").lower()

    if any(k in raw for k in ("ultra-deepwater", "ultra deepwater", "ultra deep water", ">1500m")):
        return WaterDepthCategory.ULTRA_DEEPWATER

    if any(k in raw for k in ("deepwater", "deep water", "kg-dwn")):
        return WaterDepthCategory.DEEPWATER

    # Look for explicit meter measurements, e.g. "600m water depth", "1800 meters depth", "water depth 350 meters", "water depths of 850m"
    m_match = re.search(r"(\d+)\s*(?:m|meter|metre)s?\s*(?:water\s*depths?|depths?|subsea)", raw)
    if not m_match:
        m_match = re.search(r"(?:water\s*depths?|depths?)\s*(?:rating\s*)?(?:up\s*to\s*)?(?:of\s*)?(\d+)\s*(?:m|meter|metre)s?", raw)
    if m_match:
        val = float(m_match.group(1))
        if val > 1500:
            return WaterDepthCategory.ULTRA_DEEPWATER
        elif val >= 400:
            return WaterDepthCategory.DEEPWATER
        else:
            return WaterDepthCategory.SHALLOW

    if "shallow water" in raw or "shallow-water" in raw:
        return WaterDepthCategory.SHALLOW

    return WaterDepthCategory.UNKNOWN
