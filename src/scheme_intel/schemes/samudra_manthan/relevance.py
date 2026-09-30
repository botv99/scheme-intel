"""
Deterministic Scheme Relevance and Importance Filter for Samudra Manthan (Stage 4B).
Classifies and scores offshore exploration, regulatory, corporate, and tender events.
Stores clear, deterministic relevance reasons and importance levels.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, NamedTuple, Optional, Tuple


class RelevanceEvaluationResult(NamedTuple):
    """Result of evaluating scheme relevance. Can be unpacked as 4-tuple or accessed via attributes."""
    is_relevant: bool
    category: str
    reason: str
    confidence: float

    @property
    def importance(self) -> str:
        cat = self.category.lower() if isinstance(self.category, str) else ""
        if any(k in cat for k in ("direct_scheme", "discovery", "ultra_deepwater", "oalp")):
            return "critical"
        if any(k in cat for k in ("deepwater", "contract", "drilling", "seismic")):
            return "high"
        if any(k in cat for k in ("marine", "subsea", "policy", "regulatory", "tender")):
            return "medium"
        return "low"


class SamudraRelevanceCategory(str, Enum):
    """Taxonomy of deterministic relevance categories for Samudra Manthan."""
    DIRECT_SCHEME = "DIRECT_SCHEME"
    OFFSHORE_EXPLORATION = "OFFSHORE_EXPLORATION"
    DEEPWATER = "DEEPWATER"
    ULTRA_DEEPWATER = "ULTRA_DEEPWATER"
    OALP = "OALP"
    BLOCK = "BLOCK"
    SEISMIC = "SEISMIC"
    DRILLING = "DRILLING"
    DISCOVERY = "DISCOVERY"
    OFFSHORE_CONTRACT = "OFFSHORE_CONTRACT"
    OFFSHORE_EPC = "OFFSHORE_EPC"
    SUBSEA = "SUBSEA"
    MARINE = "MARINE"
    OILFIELD_SERVICES = "OILFIELD_SERVICES"
    REGULATORY = "REGULATORY"
    POLICY = "POLICY"
    TENDER = "TENDER"
    CAPEX = "CAPEX"
    JV = "JV"
    NON_RELEVANT = "NON_RELEVANT"


class SamudraEventImportance(str, Enum):
    """Deterministic event importance tiers."""
    CRITICAL = "CRITICAL"   # Policy shift, major discovery, Cabinet decision
    HIGH = "HIGH"           # Block award, deepwater drilling start, major offshore contract (>500 Cr)
    MEDIUM = "MEDIUM"       # Tender notice, seismic campaign, routine JV, capex announcement
    LOW = "LOW"             # Generic corporate announcement, routine compliance


# Keyword triggers mapped to categories with priority weighting
RELEVANCE_PATTERNS: List[Tuple[SamudraRelevanceCategory, List[str], str]] = [
    (
        SamudraRelevanceCategory.DIRECT_SCHEME,
        ["samudra manthan", "national offshore exploration", "national offshore mission"],
        "Explicit mention of Samudra Manthan national offshore exploration scheme",
    ),
    (
        SamudraRelevanceCategory.DISCOVERY,
        ["hydrocarbon discovery", "gas discovery", "oil strike", "commercial discovery", "gas find", "oil find", "notified discovery"],
        "Offshore oil or natural gas discovery",
    ),
    (
        SamudraRelevanceCategory.ULTRA_DEEPWATER,
        ["ultra-deepwater", "ultra deepwater", "ultra deep water", ">1500m water depth"],
        "Ultra-deepwater exploration activity (>1500m)",
    ),
    (
        SamudraRelevanceCategory.DEEPWATER,
        ["deepwater", "deep water", "kg-dwn", "deep offshore", "kg-d6", "kg basin deepwater"],
        "Deepwater upstream development (400m-1500m)",
    ),
    (
        SamudraRelevanceCategory.OALP,
        ["oalp", "open acreage", "bidding round", "acreage award", "disclosed blocks", "exploration licence", "cbm round"],
        "Open Acreage Licensing Programme (OALP) bidding or block award",
    ),
    (
        SamudraRelevanceCategory.SEISMIC,
        ["seismic survey", "2d seismic", "3d seismic", "ocean bottom node", "obn", "seismic vessel", "geophysical survey"],
        "Offshore seismic / geophysical survey program",
    ),
    (
        SamudraRelevanceCategory.DRILLING,
        ["drillship", "drilling rig", "jack-up rig", "jackup rig", "semi-submersible", "exploration well", "appraisal well", "development well", "rig charter"],
        "Offshore drilling rig mobilization or campaign",
    ),
    (
        SamudraRelevanceCategory.SUBSEA,
        ["subsea pipeline", "subsea tree", "subsea manifold", "umbilical", "diving support vessel", "dsv", "subsea engineering"],
        "Subsea engineering, pipeline, or subsea production infrastructure",
    ),
    (
        SamudraRelevanceCategory.OFFSHORE_EPC,
        ["offshore platform", "fpso", "floating production", "jacket fabrication", "offshore epc", "central processing platform"],
        "Offshore EPC platform or floating production development",
    ),
    (
        SamudraRelevanceCategory.OFFSHORE_CONTRACT,
        ["offshore contract", "rig contract", "well services contract", "charter contract", "epc award"],
        "Offshore contract or charter award",
    ),
    (
        SamudraRelevanceCategory.MARINE,
        ["marine logistics", "offshore supply vessel", "osv", "anchor handling", "ahts", "towing vessel", "crewing vessel"],
        "Offshore marine supply and logistics vessels",
    ),
    (
        SamudraRelevanceCategory.OILFIELD_SERVICES,
        ["oilfield services", "mud logging", "casing", "well testing", "wireline", "directional drilling", "cementing services"],
        "Upstream oilfield services and well engineering",
    ),
    (
        SamudraRelevanceCategory.BLOCK,
        ["offshore block", "exploration block", "acreage", "kg-dwn-98/2", "nec-osn", "mb-oshp", "andaman block", "cambay offshore", "cauvery offshore", "mahanadi offshore"],
        "Designated offshore sedimentary basin or exploration block",
    ),
    (
        SamudraRelevanceCategory.REGULATORY,
        ["dgh", "directorate general of hydrocarbons", "petroleum and natural gas regulatory board", "pngrb", "mopng guideline", "upstream regulation"],
        "DGH or MoPNG regulatory circular or policy directive",
    ),
    (
        SamudraRelevanceCategory.POLICY,
        ["hydrocarbon policy", "exploration policy", "royalty relief", "gas pricing freedom", "revenue sharing contract", "help policy"],
        "National hydrocarbon exploration policy or fiscal incentives",
    ),
    (
        SamudraRelevanceCategory.TENDER,
        ["eprocure", "cppp tender", "drilling tender", "seismic tender", "offshore tender", "procurement notice", "tender id"],
        "Hydrocarbon or offshore public procurement tender",
    ),
    (
        SamudraRelevanceCategory.CAPEX,
        ["upstream capex", "exploration expenditure", "offshore investment", "field development plan", "fdp approval"],
        "Upstream exploration and offshore development capital expenditure",
    ),
    (
        SamudraRelevanceCategory.JV,
        ["joint venture", "farm-in", "farm-out", "consortium partner", "participating interest"],
        "Joint venture or participating interest in exploration acreage",
    ),
    (
        SamudraRelevanceCategory.OFFSHORE_EXPLORATION,
        ["offshore", "hydrocarbon", "crude oil exploration", "upstream oil and gas", "basin exploration", "shelf", "continental shelf"],
        "General offshore hydrocarbon exploration context",
    ),
]


class SamudraRelevanceFilter:
    """Evaluates raw records/events to determine deterministic scheme relevance and importance."""

    @classmethod
    def evaluate(cls, title: str, content: str = "") -> Tuple[bool, str, str, float]:
        """
        Evaluate text for Samudra Manthan scheme relevance.
        Returns:
            (is_relevant, category, reason, confidence)
        """
        combined = f"{title} {content}".lower()

        # Check for explicit exclusions (non-relevant sectors e.g. purely downstream retail, sports, or administrative notices)
        if any(exc in combined for exc in [
            "petrol pump dealer", "retail outlet dealership", "cricket tournament",
            "sports training centre", "canteen tender", "stationery tender", "security guard tender",
            "holiday list", "list of holidays", "national holidays", "office holiday",
            "non-offshore", "multi-cloud managed services", "generative ai center", "it services",
            "offshore wind", "wind farm", "wind turbine", "solar farm"
        ]):
            # Unless explicit deepwater or oalp or drillship is mentioned
            if not any(k in combined for k in ["deepwater", "oalp", "drillship", "ultra-deepwater", "seismic acquisition"]):
                return RelevanceEvaluationResult(False, SamudraRelevanceCategory.NON_RELEVANT.value, "Excluded non-upstream or administrative activity", 0.1)

        for category, keywords, reason in RELEVANCE_PATTERNS:
            for kw in keywords:
                pattern = rf"\b(?<!non-){re.escape(kw)}\b" if kw == "offshore" else rf"\b{re.escape(kw)}\b"
                if re.search(pattern, combined):
                    confidence = 0.95 if category in (
                        SamudraRelevanceCategory.DIRECT_SCHEME,
                        SamudraRelevanceCategory.DISCOVERY,
                        SamudraRelevanceCategory.ULTRA_DEEPWATER,
                        SamudraRelevanceCategory.DEEPWATER,
                        SamudraRelevanceCategory.OALP,
                    ) else 0.85
                    return RelevanceEvaluationResult(True, category.value, f"{reason} (matched: '{kw}')", confidence)

        return RelevanceEvaluationResult(False, SamudraRelevanceCategory.NON_RELEVANT.value, "No offshore hydrocarbon relevance detected", 0.0)

    @classmethod
    def determine_importance(cls, title: str, content: str = "", category: str = "") -> str:
        """
        Deterministically assign event importance based on operational significance.
        """
        combined = f"{title} {content}".lower()

        # Critical: Policy shift, major discovery, cabinet decision, PM review, direct national scheme
        if any(k in combined for k in [
            "cabinet approves", "major discovery", "commercial gas discovery",
            "oil strike", "policy reform", "royalty waiver", "strategic reserve",
            "samudra manthan", "pm reviews", "pm chairs", "prime minister"
        ]) or category in (
            SamudraRelevanceCategory.DIRECT_SCHEME.value,
            SamudraRelevanceCategory.DISCOVERY.value,
        ):
            return SamudraEventImportance.CRITICAL.value

        # High: Block award, deepwater drilling start, major offshore contract
        if any(k in combined for k in [
            "block awarded", "oalp round award", "deepwater drilling", "ultra-deepwater",
            "drillship charter", "contract awarded", "award of block", "dry well", "project delay"
        ]) or category in (
            SamudraRelevanceCategory.OALP.value,
            SamudraRelevanceCategory.ULTRA_DEEPWATER.value,
            SamudraRelevanceCategory.DEEPWATER.value,
            SamudraRelevanceCategory.OFFSHORE_CONTRACT.value,
        ):
            return SamudraEventImportance.HIGH.value

        # Medium: Tender notices, seismic campaigns, JVs, capex
        if any(k in combined for k in [
            "tender", "seismic survey", "farm-in", "joint venture", "capex", "rig tender", "expression of interest"
        ]) or category in (
            SamudraRelevanceCategory.SEISMIC.value,
            SamudraRelevanceCategory.TENDER.value,
            SamudraRelevanceCategory.JV.value,
            SamudraRelevanceCategory.CAPEX.value,
        ):
            return SamudraEventImportance.MEDIUM.value

        return SamudraEventImportance.LOW.value
