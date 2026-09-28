"""
Query Classification Engine for Scheme-Intel (Stage 3).
Classifies incoming terminal queries to control provider fan-out and API costs:
- SIMPLE_QUERY: Straightforward stock price/status/catalyst lookups (snapshot/context answer sufficient)
- RESEARCH_QUERY: Complex comparative, policy, thematic, or multi-factor inquiries (fresh multi-provider research)
- DEEP_RESEARCH: Explicit /research commands, comprehensive deep-dive requests (maximum provider/agent fan-out)
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class QueryType(str, Enum):
    SIMPLE_QUERY = "SIMPLE_QUERY"
    RESEARCH_QUERY = "RESEARCH_QUERY"
    DEEP_RESEARCH = "DEEP_RESEARCH"


class QueryClassifier:
    """
    Classifies conversational queries for cost control and execution routing.
    Never demotes a genuine research query to simple merely because snapshot facts exist.
    """

    DEEP_RESEARCH_INDICATORS = [
        "/research",
        "deep research",
        "exhaustive analysis",
        "investigate",
        "stress test",
        "bear and bull",
        "deep dive",
    ]

    RESEARCH_INDICATORS = [
        "compare",
        "versus",
        " vs ",
        "strongest catalyst",
        "why is",
        "underperforming",
        "outperforming",
        "what changed in",
        "affected companies",
        "policy change",
        "impact of",
        "catalyst interaction",
        "macro impact",
        "order intake",
        "subsidy disbursement",
        "mandate",
        "implications",
        "pros and cons",
        "thesis",
    ]

    SIMPLE_PATTERNS = [
        r"^/stock\b",
        r"^/setups\b",
        r"^/waiting\b",
        r"^/watchlist\b",
        r"^/performance\b",
        r"^/benchmark\b",
        r"^/start\b",
        r"^/help\b",
        r"^/health\b",
        r"^/status\b",
        r"^(what is the price of|price of|cmp of|target of|sl of)\b",
    ]

    @classmethod
    def classify(cls, query: str) -> QueryType:
        """
        Determine QueryType for a given query text.
        """
        raw = (query or "").strip()
        lowered = raw.lower()

        if not raw:
            return QueryType.SIMPLE_QUERY

        # 1. Check Deep Research Indicators
        if any(ind in lowered for ind in cls.DEEP_RESEARCH_INDICATORS):
            return QueryType.DEEP_RESEARCH

        # 2. Check explicitly simple command patterns
        for pattern in cls.SIMPLE_PATTERNS:
            if re.search(pattern, lowered):
                return QueryType.SIMPLE_QUERY

        # 3. Check Research Query Indicators
        if any(ind in lowered for ind in cls.RESEARCH_INDICATORS):
            return QueryType.RESEARCH_QUERY

        # 4. Multi-entity detection (e.g. mentions multiple tickers or "and" with companies)
        tokens = [t.strip().upper() for t in re.split(r"[\s,]+", raw) if len(t) >= 3]
        known_tickers = {"TRUALT", "PRAJ", "PRAJIND", "WABAG", "ORGANIC", "ORGANICREC", "KIRLPN", "KIRLPNU", "GAIL", "IOC", "IONEXCHANG"}
        found_tickers = [t for t in tokens if t in known_tickers]
        if len(found_tickers) >= 2:
            return QueryType.RESEARCH_QUERY

        # 5. Question word + length heuristics
        words = raw.split()
        if len(words) >= 6 and ("?" in raw or any(q in lowered for q in ("why", "how", "what", "which", "where", "who"))):
            # Exclude standard simple questions
            simple_exclusions = [
                "what are the setups",
                "what are today's setups",
                "what are the waiting setups",
                "which stocks are waiting",
                "how is gobardhan doing",
            ]
            if not any(exc in lowered for exc in simple_exclusions):
                return QueryType.RESEARCH_QUERY

        return QueryType.SIMPLE_QUERY
