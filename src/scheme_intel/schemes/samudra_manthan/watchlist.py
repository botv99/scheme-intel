"""
Samudra Manthan / National Offshore Exploration Scheme Watchlist.
Direct E&P operator universe and verified offshore beneficiaries with evidence-based relationship classifications.
"""
from __future__ import annotations

from typing import List
from ..models import (
    SchemeStock,
    CompanySchemeRelationship,
    BeneficiaryRelationshipType,
    CompanyWatchlistStatus,
)

SAMUDRA_WATCHLIST: List[SchemeStock] = [
    SchemeStock(
        name="Oil and Natural Gas Corporation",
        symbol="ONGC.NS",
        aliases=["ONGC", "Oil & Natural Gas Corp", "Oil and Natural Gas Corp"],
        screener_id="ONGC",
        sectors=["Upstream Oil & Gas", "Offshore Exploration", "Deepwater Drilling"],
        rationale="Primary national E&P operator leading deepwater offshore development (KG-DWN-98/2, Mumbai High, Andaman basin) and primary beneficiary of offshore exploration incentives.",
        relationship_type=BeneficiaryRelationshipType.DIRECT_OPERATOR.value,
        status=CompanyWatchlistStatus.CORE.value,
        confidence=1.0,
        evidence="Largest offshore block holder in India; leading operator for deepwater and ultra-deepwater exploration under OALP.",
        source="DGH / MoPNG Official Reports",
        last_verified="2026-09-28",
    ),
    SchemeStock(
        name="Oil India Limited",
        symbol="OIL.NS",
        aliases=["Oil India", "OIL", "OIL INDIA LTD"],
        screener_id="OIL",
        sectors=["Upstream Oil & Gas", "Offshore Exploration", "Exploration & Production"],
        rationale="National upstream exploration company expanding offshore drilling footprint in Andaman, Mahanadi, and Kerala-Konkan offshore blocks.",
        relationship_type=BeneficiaryRelationshipType.DIRECT_OPERATOR.value,
        status=CompanyWatchlistStatus.CORE.value,
        confidence=0.95,
        evidence="Awarded multiple offshore exploration blocks under recent OALP rounds; active offshore drilling tenders.",
        source="DGH OALP Bidding Data / Oil India Annual Report",
        last_verified="2026-09-28",
    ),
    SchemeStock(
        name="Reliance Industries",
        symbol="RELIANCE.NS",
        aliases=["Reliance", "RIL", "Reliance Ind", "Reliance Industries Ltd"],
        screener_id="RELIANCE",
        sectors=["Upstream Oil & Gas", "Deepwater Production", "Energy Conglomerate"],
        rationale="Pioneer in Indian ultra-deepwater gas production in the KG-D6 basin in partnership with bp; key stakeholder in deepwater infrastructure.",
        relationship_type=BeneficiaryRelationshipType.DEEPWATER_EXPLORER.value,
        status=CompanyWatchlistStatus.CORE.value,
        confidence=0.95,
        evidence="Operates KG-D6 deepwater fields (R-Cluster, Satellite Cluster, MJ); direct exposure to deepwater gas policy.",
        source="MoPNG Hydrocarbon Production Reports / RIL Investor Presentations",
        last_verified="2026-09-28",
    ),
    SchemeStock(
        name="Vedanta Limited",
        symbol="VEDL.NS",
        aliases=["Vedanta", "VEDL", "Cairn Oil & Gas", "Cairn India"],
        screener_id="VEDL",
        sectors=["Upstream Oil & Gas", "Offshore Exploration", "Diversified Natural Resources"],
        rationale="Operates upstream exploration through Cairn Oil & Gas; holds significant acreage in OALP offshore blocks including Cambay, Ravva, and offshore exploratory tracts.",
        relationship_type=BeneficiaryRelationshipType.BLOCK_HOLDER.value,
        status=CompanyWatchlistStatus.CORE.value,
        confidence=0.90,
        evidence="Largest private acreage holder under OALP; active offshore exploration in Ravva and Cambay offshore.",
        source="DGH Block Award Disclosures / Cairn Oil & Gas Releases",
        last_verified="2026-09-28",
    ),
]

# Evidence-backed company relationships across CORE, CANDIDATE, and WATCH categories
SAMUDRA_RELATIONSHIPS: List[CompanySchemeRelationship] = [
    CompanySchemeRelationship(
        company="Oil and Natural Gas Corporation",
        symbol="ONGC.NS",
        scheme_id="samudra_manthan",
        relationship_type=BeneficiaryRelationshipType.DIRECT_OPERATOR.value,
        evidence="Largest operator in KG-DWN-98/2 deepwater block and Mumbai Offshore; chartered ultra-deepwater drillships.",
        source="DGH Official Records",
        source_date="2026-09-15",
        confidence=1.0,
        status=CompanyWatchlistStatus.CORE.value,
    ),
    CompanySchemeRelationship(
        company="Oil India Limited",
        symbol="OIL.NS",
        scheme_id="samudra_manthan",
        relationship_type=BeneficiaryRelationshipType.DIRECT_OPERATOR.value,
        evidence="Awarded shallow and deepwater blocks in Andaman and Mahanadi basins under OALP VII/VIII.",
        source="DGH OALP Gazette",
        source_date="2026-08-20",
        confidence=0.95,
        status=CompanyWatchlistStatus.CORE.value,
    ),
    CompanySchemeRelationship(
        company="Reliance Industries",
        symbol="RELIANCE.NS",
        scheme_id="samudra_manthan",
        relationship_type=BeneficiaryRelationshipType.DEEPWATER_EXPLORER.value,
        evidence="Producing ~30 MMSCMD gas from ultra-deepwater KG-D6 field with bp.",
        source="MoPNG Hydrocarbon Statistics",
        source_date="2026-09-01",
        confidence=0.95,
        status=CompanyWatchlistStatus.CORE.value,
    ),
    CompanySchemeRelationship(
        company="Vedanta Limited",
        symbol="VEDL.NS",
        scheme_id="samudra_manthan",
        relationship_type=BeneficiaryRelationshipType.BLOCK_HOLDER.value,
        evidence="Cairn Oil & Gas subsidiary awarded 51+ OALP exploration blocks, including offshore acreage.",
        source="DGH Exploration Summary",
        source_date="2026-07-10",
        confidence=0.90,
        status=CompanyWatchlistStatus.CORE.value,
    ),
    CompanySchemeRelationship(
        company="Jindal Drilling & Industries",
        symbol="JINDCOT.NS",
        scheme_id="samudra_manthan",
        relationship_type=BeneficiaryRelationshipType.DRILLING_CONTRACTOR.value,
        evidence="Provides jack-up offshore drilling rigs to ONGC on long-term deployment contracts.",
        source="NSE Corporate Filing / ONGC Tender Award",
        source_date="2026-06-30",
        confidence=0.85,
        status=CompanyWatchlistStatus.CANDIDATE.value,
    ),
    CompanySchemeRelationship(
        company="SEAMEC Limited",
        symbol="SEAMECLTD.NS",
        scheme_id="samudra_manthan",
        relationship_type=BeneficiaryRelationshipType.SUBSEA.value,
        evidence="Operates diving support vessels (DSV) and subsea inspection/maintenance for offshore platforms in Mumbai High and KG Basin.",
        source="BSE Corporate Disclosures",
        source_date="2026-05-18",
        confidence=0.80,
        status=CompanyWatchlistStatus.CANDIDATE.value,
    ),
    CompanySchemeRelationship(
        company="Dolphin Offshore Enterprises",
        symbol="DOLPHIN.NS",
        scheme_id="samudra_manthan",
        relationship_type=BeneficiaryRelationshipType.OFFSHORE_ENGINEERING.value,
        evidence="Underwater engineering, marine construction, and diving services for offshore oilfield infrastructure.",
        source="BSE Filing",
        source_date="2026-04-12",
        confidence=0.75,
        status=CompanyWatchlistStatus.CANDIDATE.value,
    ),
]

WATCHLIST = SAMUDRA_WATCHLIST
RELATIONSHIPS = SAMUDRA_RELATIONSHIPS
SAMUDRA_MANTHAN_CORE_STOCKS = SAMUDRA_WATCHLIST
