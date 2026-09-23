from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from .models import Article, Catalyst, resolve_source_tier

# ------------------------------------------------------------------
# Full 19 Catalyst Classifications (Phase 5)
# ------------------------------------------------------------------
# (score, category, duration, default_sentiment)
MATERIAL_EVENTS: dict[str, tuple[int, str, str, str]] = {
    # 1. Cabinet approval
    "cabinet approval": (95, "Cabinet approval", "long-term", "positive"),
    "cabinet approves": (95, "Cabinet approval", "long-term", "positive"),
    "ccca approves": (95, "Cabinet approval", "long-term", "positive"),
    # 2. Government policy
    "government policy": (90, "Government policy", "long-term", "positive"),
    "policy announcement": (90, "Government policy", "long-term", "positive"),
    "national bio-energy programme": (90, "Government policy", "long-term", "positive"),
    # 3. Scheme announcement
    "scheme announcement": (90, "Scheme announcement", "long-term", "positive"),
    "gobardhan": (88, "Scheme announcement", "long-term", "positive"),
    "satat": (88, "Scheme announcement", "long-term", "positive"),
    "scheme approved": (88, "Scheme announcement", "long-term", "positive"),
    # 4. Subsidy & Fund release
    "funds released": (90, "Subsidy", "medium-term", "positive"),
    "fund release": (90, "Subsidy", "medium-term", "positive"),
    "subsidy disbursed": (88, "Subsidy", "medium-term", "positive"),
    "cfa released": (88, "Subsidy", "medium-term", "positive"),
    "subsidy": (80, "Subsidy", "medium-term", "positive"),
    # 5. Order win
    "order win": (92, "Order win", "medium-term", "positive"),
    "bags order": (90, "Order win", "medium-term", "positive"),
    "wins contract": (90, "Order win", "medium-term", "positive"),
    "secures order": (90, "Order win", "medium-term", "positive"),
    "letter of award": (90, "Order win", "medium-term", "positive"),
    "contract awarded": (90, "Order win", "medium-term", "positive"),
    # 6. Tender
    "tender awarded": (85, "Tender", "medium-term", "positive"),
    "awarded tender": (85, "Tender", "medium-term", "positive"),
    "tender issued": (70, "Tender", "medium-term", "neutral"),
    "tender invited": (65, "Tender", "medium-term", "neutral"),
    "tender": (60, "Tender", "medium-term", "neutral"),
    # 7. Plant commissioning
    "commercial operation": (85, "Plant commissioning", "long-term", "positive"),
    "commissioned": (85, "Plant commissioning", "long-term", "positive"),
    "plant commissioned": (85, "Plant commissioning", "long-term", "positive"),
    "cod declared": (80, "Plant commissioning", "long-term", "positive"),
    # 8. Capacity expansion
    "capacity expansion": (82, "Capacity expansion", "long-term", "positive"),
    "expanded capacity": (82, "Capacity expansion", "long-term", "positive"),
    "ramping up production": (78, "Capacity expansion", "medium-term", "positive"),
    # 9. Capex
    "capex announced": (82, "Capex", "long-term", "positive"),
    "investment of rs": (80, "Capex", "long-term", "positive"),
    "capital expenditure": (80, "Capex", "long-term", "positive"),
    # 10. Pricing change
    "procurement price": (75, "Pricing change", "medium-term", "positive"),
    "price revision": (75, "Pricing change", "medium-term", "neutral"),
    "pricing formula": (70, "Pricing change", "medium-term", "neutral"),
    "cbg price hike": (80, "Pricing change", "medium-term", "positive"),
    # 11. Regulatory change
    "blending obligation": (80, "Regulatory change", "long-term", "positive"),
    "mandate": (75, "Regulatory change", "long-term", "neutral"),
    "cbg blending mandate": (85, "Regulatory change", "long-term", "positive"),
    "regulatory approval": (75, "Regulatory change", "medium-term", "positive"),
    # 12. JV / partnership
    "joint venture": (78, "JV / partnership", "long-term", "positive"),
    "partnership agreement": (75, "JV / partnership", "medium-term", "positive"),
    "mou signed": (65, "JV / partnership", "medium-term", "positive"),
    "memorandum of understanding": (55, "JV / partnership", "medium-term", "positive"),
    # 13. Acquisition
    "acquisition": (80, "Acquisition", "long-term", "positive"),
    "acquires stake": (80, "Acquisition", "long-term", "positive"),
    "stake acquisition": (80, "Acquisition", "long-term", "positive"),
    # 14. Results
    "quarterly results": (75, "Results", "short-term", "neutral"),
    "q1 results": (75, "Results", "short-term", "neutral"),
    "q2 results": (75, "Results", "short-term", "neutral"),
    "q3 results": (75, "Results", "short-term", "neutral"),
    "q4 results": (75, "Results", "short-term", "neutral"),
    "net profit surges": (85, "Results", "short-term", "positive"),
    "net loss": (75, "Results", "short-term", "negative"),
    # 15. Management commentary
    "management commentary": (72, "Management commentary", "medium-term", "neutral"),
    "management guidance": (75, "Management commentary", "medium-term", "positive"),
    "md says": (68, "Management commentary", "medium-term", "neutral"),
    "ceo outlook": (70, "Management commentary", "medium-term", "neutral"),
    # 16. Investor presentation
    "investor presentation": (65, "Investor presentation", "medium-term", "neutral"),
    "analyst meet": (65, "Investor presentation", "medium-term", "neutral"),
    # 17. Earnings call
    "earnings call": (70, "Earnings call", "medium-term", "neutral"),
    "concall transcript": (70, "Earnings call", "medium-term", "neutral"),
    "conference call": (68, "Earnings call", "medium-term", "neutral"),
    # 18. Analyst report
    "analyst report": (68, "Analyst report", "medium-term", "neutral"),
    "target price raised": (75, "Analyst report", "short-term", "positive"),
    "downgrade": (75, "Analyst report", "short-term", "negative"),
    "brokerage initiates": (68, "Analyst report", "medium-term", "neutral"),
    # 19. Industry development
    "industry development": (60, "Industry development", "medium-term", "neutral"),
    "cbg sector": (65, "Industry development", "medium-term", "neutral"),
    "biogas plant": (65, "Industry development", "medium-term", "neutral"),
}

SCHEME_KEYWORDS = {
    "GOBARdhan": ("gobardhan", "galvanizing organic bio-agro resources"),
    "SATAT": ("satat", "sustainable alternative towards affordable transportation"),
    "National Bioenergy": ("national bio-energy", "bioenergy programme", "mnre bioenergy"),
    "Ethanol Blending": ("ethanol blending", "ebp programme", "20% ethanol"),
    "CBG Blending Mandate": ("cbg blending obligation", "cbo mandate", "compressed biogas blending"),
}

SECTOR_KEYWORDS = {
    "Bio-Energy & CBG": ("cbg", "biogas", "biomass", "bio-cng", "bio energy", "methane"),
    "Ethanol & Distilleries": ("ethanol", "distillery", "distilleries", "grain-based", "molasses"),
    "City Gas Distribution": ("cgd", "cng station", "piped gas", "png", "city gas"),
    "EPC & Equipment": ("fermenter", "purification", "compressor", "epc contract", "technology provider"),
}

BUSINESS_SEGMENTS = {
    "Clean Fuels": ("cbg", "bio-cng", "ethanol", "green hydrogen"),
    "Engineering & Tech": ("process equipment", "brewery", "turnkey", "purification system"),
    "Gas Utility & CGD": ("city gas", "pipeline", "gas distribution", "cng station"),
    "Feedstock Supply": ("paddy straw", "pressmud", "agri waste", "cow dung"),
}


def _detect_scheme(text: str) -> str:
    for scheme, words in SCHEME_KEYWORDS.items():
        if any(w in text for w in words):
            return scheme
    return "GOBARdhan / General Biogas"


def _detect_sector(text: str) -> str:
    for sector, words in SECTOR_KEYWORDS.items():
        if any(w in text for w in words):
            return sector
    return "Renewable Energy / Biofuels"


def _detect_segment(text: str) -> str:
    for segment, words in BUSINESS_SEGMENTS.items():
        if any(w in text for w in words):
            return segment
    return "Bio-Energy"


def classify(article: Article, companies: list[dict]) -> Catalyst | None:
    """
    Classify an article into one of the 19 Stage 1 catalyst classifications.
    Returns an enriched Catalyst object containing all required Stage 1 fields.
    """
    text = f"{article.title} {article.summary}".lower()

    # Match strongest material event pattern
    best_match = None
    best_score = -1
    best_term = ""
    best_cat = ""
    best_dur = "medium-term"
    best_sentiment = "neutral"

    for term, (score, cat, dur, sent) in MATERIAL_EVENTS.items():
        if term in text:
            if score > best_score:
                best_score = score
                best_match = (score, cat, dur, sent)
                best_term = term
                best_cat = cat
                best_dur = dur
                best_sentiment = sent

    if not best_match:
        return None

    # Identify matched watchlist companies
    names = []
    for company in companies:
        aliases = [company["name"], *company.get("aliases", [])]
        if any(alias.lower() in text for alias in aliases):
            names.append(company["name"])

    # Determine source tier
    tier = resolve_source_tier(article.source, article.url)
    if tier == 3 and getattr(article, "source_tier", None) is not None and article.source_tier != 3:
        tier = article.source_tier

    # Contextual metadata
    scheme = _detect_scheme(text)
    sector = _detect_sector(text)
    segment = _detect_segment(text)

    # Event date / Published date
    pub_iso = article.published_at.isoformat() if article.published_at else None
    rationale = f"Detected {best_cat} language ('{best_term}') in {article.source}."

    # Return Catalyst with full Phase 5 metadata
    return Catalyst(
        article=article,
        score=best_score,
        category=best_cat.lower(),
        rationale=rationale,
        companies=tuple(names),
        catalyst_type=best_cat,
        headline=article.title,
        published_at=pub_iso,
        event_date=pub_iso[:10] if pub_iso else None,
        confidence=float(best_score),
        sentiment_label=best_sentiment,
        expected_duration=best_dur,
        affected_business_segment=segment,
        related_scheme=scheme,
        related_sector=sector,
        source_tier=tier,
    )
