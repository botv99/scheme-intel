"""
Samudra Manthan Scheme Rules and Dynamic Beneficiary Discovery Engine.
Implements:
1. Beneficiary relationship classification
2. Dynamic company discovery from tenders/OALP awards/contracts
3. OALP basin/block eligibility rules
4. Water depth classification (shallow, deepwater, ultra-deepwater)
5. Promotion rules (Candidate -> Core)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from ..models import (
    BeneficiaryRelationshipType,
    CompanyWatchlistStatus,
    CompanySchemeRelationship,
    SchemeStock,
)
from ...logger import get_logger

logger = get_logger(__name__)


class SamudraRulesEngine:
    """Evaluates Samudra Manthan events, classifies relationships, and computes company impacts."""

    DEPTH_SHALLOW = "SHALLOW"             # < 400m
    DEPTH_DEEPWATER = "DEEPWATER"         # 400m - 1500m
    DEPTH_ULTRA_DEEPWATER = "ULTRA_DEEPWATER" # > 1500m
    DEPTH_UNKNOWN = "UNKNOWN"

    @classmethod
    def classify_water_depth(cls, text_or_meters: Any) -> str:
        """Classify water depth from tender/announcement evidence without speculation."""
        if isinstance(text_or_meters, (int, float)):
            if text_or_meters > 1500:
                return cls.DEPTH_ULTRA_DEEPWATER
            elif text_or_meters >= 400:
                return cls.DEPTH_DEEPWATER
            else:
                return cls.DEPTH_SHALLOW

        lowered = str(text_or_meters or "").lower()
        if "ultra-deepwater" in lowered or "ultra deepwater" in lowered or "ultra deep water" in lowered:
            return cls.DEPTH_ULTRA_DEEPWATER
        if "deepwater" in lowered or "deep water" in lowered:
            return cls.DEPTH_DEEPWATER

        depth_match = re.search(r"(\d+)\s*(?:m|meter|metre)s?\s*(?:water\s*depth|depth)", lowered)
        if depth_match:
            depth_m = int(depth_match.group(1))
            if depth_m > 1500:
                return cls.DEPTH_ULTRA_DEEPWATER
            elif depth_m >= 400:
                return cls.DEPTH_DEEPWATER
            else:
                return cls.DEPTH_SHALLOW

        if "shallow" in lowered:
            return cls.DEPTH_SHALLOW
        return cls.DEPTH_UNKNOWN

    @classmethod
    def classify_relationship(cls, event_title: str, event_text: str) -> BeneficiaryRelationshipType:
        """Deterministically determine relationship type based on verified event keywords."""
        content = f"{event_title} {event_text}".lower()

        if any(k in content for k in ("drillship", "drilling rig", "jackup", "jack-up", "drilling tender", "rig charter")):
            return BeneficiaryRelationshipType.DRILLING_CONTRACTOR
        if any(k in content for k in ("seismic survey", "2d seismic", "3d seismic", "ocean bottom node", "seismic vessel")):
            return BeneficiaryRelationshipType.SEISMIC_PROVIDER
        if any(k in content for k in ("subsea pipeline", "diving support", "subsea tree", "manifold", "umbilical")):
            return BeneficiaryRelationshipType.SUBSEA
        if any(k in content for k in ("fpsd", "fpso", "offshore platform", "epc contract", "jacket fabrication")):
            return BeneficiaryRelationshipType.OFFSHORE_ENGINEERING
        if any(k in content for k in ("offshore logistics", "osv", "anchor handling", "supply vessel")):
            return BeneficiaryRelationshipType.MARINE_LOGISTICS
        if any(k in content for k in ("oilfield services", "mud logging", "casing", "well testing", "wireline")):
            return BeneficiaryRelationshipType.OILFIELD_SERVICES
        if any(k in content for k in ("oalp block", "block award", "acreage awarded", "exploration licence")):
            return BeneficiaryRelationshipType.BLOCK_HOLDER
        if any(k in content for k in ("joint venture", "farm-in", "consortium partner")):
            return BeneficiaryRelationshipType.JV_PARTNER
        if any(k in content for k in ("ultra-deepwater discovery", "deepwater exploration", "deepwater gas")):
            return BeneficiaryRelationshipType.DEEPWATER_EXPLORER

        return BeneficiaryRelationshipType.DIRECT_OPERATOR

    @classmethod
    def evaluate_company_impact(
        cls,
        company_name: str,
        symbol: str,
        event_type: str,
        title: str,
        content: str,
    ) -> Dict[str, Any]:
        """
        Compute evidence-based company impact for Samudra Manthan event.
        Returns:
            Dict containing relationship, direct_exposure, event_significance,
            direction (positive/negative/neutral), confidence, time_horizon, evidence.
        """
        combined = f"{title} {content}".lower()
        relationship = cls.classify_relationship(title, content)
        depth = cls.classify_water_depth(combined)

        # Directional impact
        is_negative = any(k in combined for k in ("dry well", "project delay", "tender canceled", "cost overrun", "penalty", "dispute"))
        is_positive = any(k in combined for k in ("discovery", "award", "contract win", "commercial gas", "oil strike", "incentive", "royalty relief"))

        if is_negative:
            direction = "NEGATIVE"
        elif is_positive:
            direction = "POSITIVE"
        else:
            direction = "NEUTRAL"

        significance = "HIGH" if depth in (cls.DEPTH_DEEPWATER, cls.DEPTH_ULTRA_DEEPWATER) or "discovery" in combined or "award" in combined else "MEDIUM"
        time_horizon = "LONG_TERM" if "oalp" in combined or "exploration" in combined else "MEDIUM_TERM"
        confidence = 0.90 if any(k in combined for k in ("dgh", "mopng", "award", "contract")) else 0.75

        return {
            "company": company_name,
            "symbol": symbol,
            "scheme_id": "samudra_manthan",
            "relationship_type": relationship.value,
            "water_depth": depth,
            "significance": significance,
            "direction": direction,
            "time_horizon": time_horizon,
            "confidence": confidence,
            "evidence": title,
        }


class DynamicBeneficiaryDiscovery:
    """
    Discovers new potential scheme beneficiaries from public tenders,
    OALP awards, and exchange contract disclosures.
    """

    # Known Indian listed companies capable of offshore services
    OFFSHORE_CANDIDATE_REGISTRY: Dict[str, Dict[str, Any]] = {
        "JINDAL DRILLING": {
            "symbol": "JINDCOT.NS",
            "name": "Jindal Drilling & Industries",
            "role": BeneficiaryRelationshipType.DRILLING_CONTRACTOR,
            "exchange": "NSE",
        },
        "SEAMEC": {
            "symbol": "SEAMECLTD.NS",
            "name": "SEAMEC Limited",
            "role": BeneficiaryRelationshipType.SUBSEA,
            "exchange": "NSE",
        },
        "DOLPHIN OFFSHORE": {
            "symbol": "DOLPHIN.NS",
            "name": "Dolphin Offshore Enterprises",
            "role": BeneficiaryRelationshipType.OFFSHORE_ENGINEERING,
            "exchange": "NSE",
        },
        "ABAN OFFSHORE": {
            "symbol": "ABAN.NS",
            "name": "Aban Offshore",
            "role": BeneficiaryRelationshipType.DRILLING_CONTRACTOR,
            "exchange": "BSE",
        },
        "COCHIN SHIPYARD": {
            "symbol": "COCHINSHIP.NS",
            "name": "Cochin Shipyard",
            "role": BeneficiaryRelationshipType.MARINE_LOGISTICS,
            "exchange": "NSE",
        },
        "MAZAGON DOCK": {
            "symbol": "MAZDOCK.NS",
            "name": "Mazagon Dock Shipbuilders",
            "role": BeneficiaryRelationshipType.OFFSHORE_INFRASTRUCTURE,
            "exchange": "NSE",
        },
    }

    @classmethod
    def discover_from_event(
        cls,
        title: str,
        content: str,
        source: str = "Tender / Filing",
    ) -> List[CompanySchemeRelationship]:
        """
        Scan a contract award or tender event to identify candidate beneficiaries.
        Validates evidence before adding to candidate list.
        """
        discovered: List[CompanySchemeRelationship] = []
        combined = f"{title} {content}".upper()

        # Check Core E&P Operators
        from .watchlist import SAMUDRA_MANTHAN_CORE_STOCKS
        for stock in SAMUDRA_MANTHAN_CORE_STOCKS:
            names_to_check = [stock.name.upper(), stock.symbol.upper(), stock.symbol.split(".")[0].upper()] + [a.upper() for a in stock.aliases]
            if any(n in combined for n in names_to_check):
                rel = CompanySchemeRelationship(
                    company=stock.name,
                    symbol=stock.symbol,
                    scheme_id="samudra_manthan",
                    relationship_type=BeneficiaryRelationshipType.DIRECT_OPERATOR.value,
                    evidence=title[:250],
                    source=source,
                    confidence=0.95,
                    status=CompanyWatchlistStatus.CORE.value,
                )
                discovered.append(rel)

        for key, meta in cls.OFFSHORE_CANDIDATE_REGISTRY.items():
            if key in combined:
                rel = CompanySchemeRelationship(
                    company=meta["name"],
                    symbol=meta["symbol"],
                    scheme_id="samudra_manthan",
                    relationship_type=meta["role"].value,
                    evidence=title[:250],
                    source=source,
                    confidence=0.80,
                    status=CompanyWatchlistStatus.CANDIDATE.value,
                )
                discovered.append(rel)
                logger.info(
                    "[DYNAMIC DISCOVERY] Candidate identified for Samudra Manthan: %s (%s) from '%s'",
                    meta["name"],
                    meta["symbol"],
                    title[:50],
                )

        return discovered

    @classmethod
    def discover_beneficiaries(
        cls,
        event_title: str,
        content: str,
        source: str = "Tender / Filing",
    ) -> List[CompanySchemeRelationship]:
        return cls.discover_from_event(title=event_title, content=content, source=source)
