"""
GOBARdhan Scheme Keywords and Company Mapping Taxonomy.
"""
from __future__ import annotations

from typing import Dict, List

GOBARDHAN_KEYWORDS: List[str] = [
    "gobardhan",
    "galvanizing organic bio-agro resources",
    "cbg",
    "compressed bio-gas",
    "compressed biogas",
    "biogas",
    "bio-cng",
    "biocng",
    "satat",
    "sustainable alternative towards affordable transportation",
    "ethanol blending",
    "2g ethanol",
    "1g ethanol",
    "fermented organic manure",
    "fom",
    "liquid fermented organic manure",
    "lfom",
    "bio-manure",
    "waste to wealth",
    "waste to energy",
    "slurry",
    "anaerobic digestion",
    "biomass pellet",
    "central financial assistance",
    "market development assistance",
    "mda",
]

GOBARDHAN_ENTITIES: List[str] = [
    "Ministry of Petroleum and Natural Gas",
    "MoPNG",
    "Ministry of New and Renewable Energy",
    "MNRE",
    "Department of Drinking Water and Sanitation",
    "DDWS",
    "Ministry of Jal Shakti",
    "Department of Fertilisers",
    "Oil Marketing Companies",
    "OMCs",
    "Indian Oil Corporation",
    "GAIL",
    "Praj Industries",
    "TruAlt Bioenergy",
    "VA Tech Wabag",
    "Ion Exchange",
    "Kirloskar Pneumatic",
]

GOBARDHAN_COMPANY_MAPPINGS: Dict[str, List[str]] = {
    "Praj Industries": ["praj", "praj industries", "praj ind", "cbg plant technology"],
    "TruAlt Bioenergy": ["trualt", "trualt bioenergy", "trualt bio"],
    "Ion Exchange": ["ion exchange", "ieil", "ion exchange india"],
    "VA Tech Wabag": ["wabag", "va tech wabag", "va tech"],
    "Kirloskar Pneumatic": ["kirloskar pneumatic", "kpcl", "kirloskar pneum"],
    "GAIL (India)": ["gail", "gail india", "gas authority of india"],
    "Indian Oil Corporation": ["ioc", "iocl", "indian oil", "indianoil", "indigreen"],
}

GOBARDHAN_EVENT_TAXONOMY: List[str] = [
    "POLICY_ANNOUNCEMENT",
    "SUBSIDY_APPROVAL",
    "TENDER_ISSUED",
    "PLANT_COMMISSIONING",
    "OFFTAKE_AGREEMENT",
    "REGULATORY_MANDATE",
    "COMMERCIAL_CONTRACT",
]

COMPANY_KEYWORDS = GOBARDHAN_COMPANY_MAPPINGS

