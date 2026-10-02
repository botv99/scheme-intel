"""
Samudra Manthan Scheme Configuration Object.
National Offshore Exploration Scheme covering deepwater, ultra-deepwater,
OALP blocks, seismic acquisition, and offshore drilling.
"""
from __future__ import annotations

from ..models import SchemeConfig
from .watchlist import SAMUDRA_WATCHLIST
from .sources import SAMUDRA_SOURCES
from .mapping import (
    SAMUDRA_KEYWORDS,
    SAMUDRA_ENTITIES,
    SAMUDRA_COMPANY_MAPPINGS,
    SAMUDRA_EVENT_TAXONOMY,
)

SAMUDRA_STRUCTURED_KNOWLEDGE = {
    "scheme_name": "Samudra Manthan",
    "official_title": "National Offshore Exploration Scheme",
    "target_domains": [
        "Offshore Exploration",
        "Deepwater",
        "Ultra-Deepwater",
        "OALP Acreage",
        "Seismic Acquisition",
        "Drilling Rig Chartering",
    ],
    "implementation_period": "2025-2030",
    "total_outlay": "Government incentive framework and fiscal concessions to accelerate offshore exploration across EEZ",
    "exploration_support": "Revenue-sharing concessions, concessional royalties, and full seismic data access via NDR",
    "targeted_wells": "Targeted deepwater and ultra-deepwater exploratory & appraisal wells in KG, Andaman, Mahanadi, and Mumbai Offshore",
    "deepwater_scope": "Water depths exceeding 400 meters",
    "ultra_deepwater_scope": "Water depths exceeding 1,000 meters",
    "seismic_data_component": "2D/3D broadband seismic data acquisition across unappraised offshore and ultra-deepwater basins",
    "common_infrastructure": "Shared subsea facilities, offshore logistics bases, and emergency response infrastructure",
    "manufacturing_services_component": "Indigenization of subsea equipment, offshore drilling rigs, seismic vessels, and EPC services",
    "support_percentage": "Concessional royalty rates and customs duty exemptions for deepwater exploration assets",
    "per_well_support_ceiling": "Subject to DGH fiscal guidelines and OALP bidding round terms",
    "eligible_operators": [
        "National Oil Companies (ONGC, Oil India)",
        "Private E&P Operators (Reliance Industries, Cairn / Vedanta)",
        "International Deepwater Joint Ventures",
    ],
    "status_milestones": {
        "announcement": "Announced under India energy security and deepwater exploration mission",
        "guidelines": "DGH OALP bidding and fiscal guideline frameworks active",
        "implementation": "Active exploration and drilling tenders underway",
        "fund_allocation": "Concessional fiscal mechanisms and revenue-sharing terms active",
        "tendering": "ONGC and Oil India offshore drilling and rig chartering tenders live",
    },
}

SAMUDRA_RULES = {
    "min_evidence_confidence": 0.70,
    "core_promotions_require_contract_or_acreage": True,
    "allowed_relationship_types": [
        "DIRECT_OPERATOR",
        "BLOCK_HOLDER",
        "JV_PARTNER",
        "DEEPWATER_EXPLORER",
        "DRILLING_CONTRACTOR",
        "SEISMIC_PROVIDER",
        "OFFSHORE_ENGINEERING",
        "SUBSEA",
        "OFFSHORE_INFRASTRUCTURE",
        "EQUIPMENT_SUPPLIER",
        "MARINE_LOGISTICS",
        "OILFIELD_SERVICES",
        "EPC",
        "SECOND_ORDER_BENEFICIARY",
    ],
    "depth_classifications": {
        "shallow_water": "<400m",
        "deepwater": "400m-1000m",
        "ultra_deepwater": ">1000m",
    },
}

SAMUDRA_MANTHAN_CONFIG = SchemeConfig(
    id="samudra_manthan",
    name="Samudra Manthan (National Offshore Exploration Scheme)",
    enabled=True,
    description="Government umbrella initiative covering deepwater and ultra-deepwater oil and gas exploration, OALP block development, seismic surveys, and offshore drilling.",
    focus="Offshore / Deepwater / Ultra-Deepwater E&P",
    ministries=[
        "Ministry of Petroleum and Natural Gas (MoPNG)",
        "Directorate General of Hydrocarbons (DGH)",
        "Prime Minister's Office (PMO)",
        "Ministry of Earth Sciences (MoES)",
    ],
    sources=SAMUDRA_SOURCES,
    watchlist=SAMUDRA_WATCHLIST,
    keywords=SAMUDRA_KEYWORDS,
    entities=SAMUDRA_ENTITIES,
    industries=[
        "Upstream Oil & Gas",
        "Offshore Drilling",
        "Oilfield Services",
        "Marine Logistics",
        "Subsea Engineering",
    ],
    company_mappings=SAMUDRA_COMPANY_MAPPINGS,
    event_taxonomy=SAMUDRA_EVENT_TAXONOMY,
    structured_knowledge=SAMUDRA_STRUCTURED_KNOWLEDGE,
    rules=SAMUDRA_RULES,
)
