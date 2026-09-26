"""
Deterministic Intent & Entity Resolver for Telegram Terminal Queries.
Resolves user messages into structured intents and normalizes company / scheme entities
via SchemeRegistry without relying on external web crawling or non-deterministic LLMs.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from ..schemes.registry import SchemeRegistry
from ..schemes.models import SchemeConfig, SchemeStock
from ..logger import get_logger

logger = get_logger(__name__)


class IntentType(str, Enum):
    START = "START"
    HELP = "HELP"
    SCHEMES = "SCHEMES"
    SCHEME_LOOKUP = "SCHEME_LOOKUP"
    STOCK_LOOKUP = "STOCK_LOOKUP"
    STOCK_WHY = "STOCK_WHY"
    STOCK_WHAT = "STOCK_WHAT"
    STOCK_WHEN = "STOCK_WHEN"
    SETUPS_LOOKUP = "SETUPS_LOOKUP"
    WAITING_LOOKUP = "WAITING_LOOKUP"
    OUTCOMES_LOOKUP = "OUTCOMES_LOOKUP"
    PERFORMANCE_LOOKUP = "PERFORMANCE_LOOKUP"
    BENCHMARK_LOOKUP = "BENCHMARK_LOOKUP"
    RESEARCH_REQUEST = "RESEARCH_REQUEST"
    UNKNOWN = "UNKNOWN"


class ResolvedIntent(BaseModel):
    """Normalized intent result with extracted entities."""
    intent_type: IntentType
    symbol: Optional[str] = None           # Canonical symbol e.g., "TRUALT.NS"
    short_symbol: Optional[str] = None     # Base ticker e.g., "TRUALT"
    company_name: Optional[str] = None     # Full company name e.g., "TruAlt Bioenergy"
    scheme_id: Optional[str] = None        # Scheme ID e.g., "gobardhan"
    raw_query: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)


class IntentResolver:
    """Deterministic parser and entity resolver."""

    @classmethod
    def resolve_stock(cls, text: str) -> Optional[Tuple[SchemeStock, str]]:
        """
        Resolve a string token to a SchemeStock and its scheme_id via SchemeRegistry.
        Matches symbol (exact or sans suffix), company name, or aliases.
        """
        token = text.strip().upper()
        if not token:
            return None

        # Clean punctuation from token (e.g. TRUALT? -> TRUALT)
        token_clean = re.sub(r"[^\w\.]", "", token)

        for scheme in SchemeRegistry.list_schemes():
            for stock in scheme.watchlist:
                sym_upper = stock.symbol.upper()
                short_upper = sym_upper.split(".")[0]

                # 1. Exact or short symbol match
                if token_clean in (sym_upper, short_upper, short_upper.replace("-", "_")):
                    return stock, scheme.id

                # 2. Screener ID match
                if stock.screener_id and token_clean == stock.screener_id.upper():
                    return stock, scheme.id

                # 3. Name or alias match
                if token_clean == stock.name.upper():
                    return stock, scheme.id
                for alias in stock.aliases:
                    if token_clean == alias.upper():
                        return stock, scheme.id

        return None

    @classmethod
    def resolve_scheme(cls, text: str) -> Optional[SchemeConfig]:
        """Resolve scheme name or ID to SchemeConfig."""
        token = text.strip().lower()
        if not token:
            return None
        token_clean = re.sub(r"[^\w\s]", "", token).strip()

        for scheme in SchemeRegistry.list_schemes():
            if token_clean in (scheme.id.lower(), scheme.name.lower()):
                return scheme
            # Partial word match e.g. "gobardhan" inside "GOBARdhan Scheme"
            if scheme.id.lower() in token_clean or token_clean in scheme.id.lower():
                return scheme
        return None

    @classmethod
    def resolve(cls, message: str) -> ResolvedIntent:
        """Parse user Telegram message into a ResolvedIntent."""
        raw = (message or "").strip()
        if not raw:
            return ResolvedIntent(intent_type=IntentType.UNKNOWN, raw_query=raw)

        parts = raw.split(maxsplit=1)
        first_token = parts[0].lower()
        remainder = parts[1].strip() if len(parts) > 1 else ""

        # ----------------------------------------------------
        # 1. Explicit Slash Commands
        # ----------------------------------------------------
        if first_token in ("/start", "start"):
            return ResolvedIntent(intent_type=IntentType.START, raw_query=raw)

        if first_token in ("/help", "help"):
            return ResolvedIntent(intent_type=IntentType.HELP, raw_query=raw)

        if first_token in ("/schemes", "schemes"):
            return ResolvedIntent(intent_type=IntentType.SCHEMES, raw_query=raw)

        if first_token in ("/scheme", "scheme"):
            scheme_target = remainder or "gobardhan"
            scheme = cls.resolve_scheme(scheme_target)
            return ResolvedIntent(
                intent_type=IntentType.SCHEME_LOOKUP,
                scheme_id=scheme.id if scheme else scheme_target,
                raw_query=raw,
            )

        if first_token in ("/research", "research"):
            question = remainder
            # Determine scheme context if mentioned
            scheme_id = "gobardhan"
            for s in SchemeRegistry.list_schemes():
                if s.id.lower() in question.lower() or s.name.lower() in question.lower():
                    scheme_id = s.id
                    break
            return ResolvedIntent(
                intent_type=IntentType.RESEARCH_REQUEST,
                scheme_id=scheme_id,
                raw_query=raw,
                parameters={"question": question},
            )

        if first_token in ("/setups", "setups"):
            return ResolvedIntent(intent_type=IntentType.SETUPS_LOOKUP, raw_query=raw)

        if first_token in ("/waiting", "waiting"):
            return ResolvedIntent(intent_type=IntentType.WAITING_LOOKUP, raw_query=raw)

        if first_token in ("/outcomes", "outcomes"):
            return ResolvedIntent(intent_type=IntentType.OUTCOMES_LOOKUP, raw_query=raw)

        if first_token in ("/performance", "performance"):
            return ResolvedIntent(intent_type=IntentType.PERFORMANCE_LOOKUP, raw_query=raw)

        if first_token in ("/benchmark", "benchmark"):
            return ResolvedIntent(intent_type=IntentType.BENCHMARK_LOOKUP, raw_query=raw)

        if first_token in ("/stock", "stock") and remainder:
            match = cls.resolve_stock(remainder)
            if match:
                stock, s_id = match
                return ResolvedIntent(
                    intent_type=IntentType.STOCK_LOOKUP,
                    symbol=stock.symbol,
                    short_symbol=stock.symbol.split(".")[0],
                    company_name=stock.name,
                    scheme_id=s_id,
                    raw_query=raw,
                )
            return ResolvedIntent(
                intent_type=IntentType.STOCK_LOOKUP,
                raw_query=raw,
                parameters={"unresolved_symbol": remainder},
            )

        if first_token in ("/why", "why") and remainder:
            match = cls.resolve_stock(remainder)
            if not match:
                for w in remainder.split():
                    clean_w = re.sub(r"[^\w]", "", w)
                    m = cls.resolve_stock(clean_w)
                    if m:
                        match = m
                        break
            if match:
                stock, s_id = match
                return ResolvedIntent(
                    intent_type=IntentType.STOCK_WHY,
                    symbol=stock.symbol,
                    short_symbol=stock.symbol.split(".")[0],
                    company_name=stock.name,
                    scheme_id=s_id,
                    raw_query=raw,
                )
            return ResolvedIntent(
                intent_type=IntentType.STOCK_WHY,
                raw_query=raw,
                parameters={"unresolved_symbol": remainder},
            )

        if first_token in ("/what", "what") and remainder:
            # Check if user asks "/what happened with gobardhan"
            scheme = cls.resolve_scheme(remainder)
            if scheme:
                return ResolvedIntent(
                    intent_type=IntentType.SCHEME_LOOKUP,
                    scheme_id=scheme.id,
                    raw_query=raw,
                )
            match = cls.resolve_stock(remainder)
            if not match:
                for w in remainder.split():
                    clean_w = re.sub(r"[^\w]", "", w)
                    m = cls.resolve_stock(clean_w)
                    if m:
                        match = m
                        break
            if match:
                stock, s_id = match
                return ResolvedIntent(
                    intent_type=IntentType.STOCK_WHAT,
                    symbol=stock.symbol,
                    short_symbol=stock.symbol.split(".")[0],
                    company_name=stock.name,
                    scheme_id=s_id,
                    raw_query=raw,
                )
            return ResolvedIntent(
                intent_type=IntentType.STOCK_WHAT,
                raw_query=raw,
                parameters={"unresolved_symbol": remainder},
            )

        if first_token in ("/when", "when") and remainder:
            match = cls.resolve_stock(remainder)
            if not match:
                for w in remainder.split():
                    clean_w = re.sub(r"[^\w]", "", w)
                    m = cls.resolve_stock(clean_w)
                    if m:
                        match = m
                        break
            if match:
                stock, s_id = match
                return ResolvedIntent(
                    intent_type=IntentType.STOCK_WHEN,
                    symbol=stock.symbol,
                    short_symbol=stock.symbol.split(".")[0],
                    company_name=stock.name,
                    scheme_id=s_id,
                    raw_query=raw,
                )
            return ResolvedIntent(
                intent_type=IntentType.STOCK_WHEN,
                raw_query=raw,
                parameters={"unresolved_symbol": remainder},
            )

        # ----------------------------------------------------
        # 2. Watchlist Shorthand (e.g., "TRUALT", "PRAJIND")
        # ----------------------------------------------------
        stock_match = cls.resolve_stock(raw)
        if stock_match:
            stock, s_id = stock_match
            return ResolvedIntent(
                intent_type=IntentType.STOCK_LOOKUP,
                symbol=stock.symbol,
                short_symbol=stock.symbol.split(".")[0],
                company_name=stock.name,
                scheme_id=s_id,
                raw_query=raw,
            )

        # Check if single word matches a scheme name
        scheme_match = cls.resolve_scheme(raw)
        if scheme_match:
            return ResolvedIntent(
                intent_type=IntentType.SCHEME_LOOKUP,
                scheme_id=scheme_match.id,
                raw_query=raw,
            )

        # ----------------------------------------------------
        # 3. Natural Language Heuristic Matching
        # ----------------------------------------------------
        lowered = raw.lower()

        # Scheme queries: "what happened with gobardhan", "tell me about gobardhan"
        if ("what happened" in lowered or "about" in lowered) and "gobardhan" in lowered:
            return ResolvedIntent(
                intent_type=IntentType.SCHEME_LOOKUP,
                scheme_id="gobardhan",
                raw_query=raw,
            )

        # Why queries: "why is TRUALT relevant", "why PRAJIND"
        if "why" in lowered:
            for word in raw.split():
                clean_word = re.sub(r"[^\w]", "", word)
                m = cls.resolve_stock(clean_word)
                if m:
                    stock, s_id = m
                    return ResolvedIntent(
                        intent_type=IntentType.STOCK_WHY,
                        symbol=stock.symbol,
                        short_symbol=stock.symbol.split(".")[0],
                        company_name=stock.name,
                        scheme_id=s_id,
                        raw_query=raw,
                    )

        # What queries: "what is happening with TRUALT", "what happened to TRUALT"
        if "what" in lowered or "happening" in lowered or "happened" in lowered:
            for word in raw.split():
                clean_word = re.sub(r"[^\w]", "", word)
                m = cls.resolve_stock(clean_word)
                if m:
                    stock, s_id = m
                    return ResolvedIntent(
                        intent_type=IntentType.STOCK_WHAT,
                        symbol=stock.symbol,
                        short_symbol=stock.symbol.split(".")[0],
                        company_name=stock.name,
                        scheme_id=s_id,
                        raw_query=raw,
                    )

        # When queries: "when to enter TRUALT", "when to watch TRUALT"
        if "when" in lowered or "trigger" in lowered:
            for word in raw.split():
                clean_word = re.sub(r"[^\w]", "", word)
                m = cls.resolve_stock(clean_word)
                if m:
                    stock, s_id = m
                    return ResolvedIntent(
                        intent_type=IntentType.STOCK_WHEN,
                        symbol=stock.symbol,
                        short_symbol=stock.symbol.split(".")[0],
                        company_name=stock.name,
                        scheme_id=s_id,
                        raw_query=raw,
                    )

        # Setup queries: "which stocks have setups", "show setups", "current setups"
        if "setup" in lowered:
            return ResolvedIntent(intent_type=IntentType.SETUPS_LOOKUP, raw_query=raw)

        # Waiting queries: "which stocks are waiting", "show waiting", "what is waiting"
        if "waiting" in lowered or "wait" in lowered:
            return ResolvedIntent(intent_type=IntentType.WAITING_LOOKUP, raw_query=raw)

        # Performance queries: "show performance", "how is the strategy performing"
        if "performance" in lowered or "win rate" in lowered or "expectancy" in lowered:
            return ResolvedIntent(intent_type=IntentType.PERFORMANCE_LOOKUP, raw_query=raw)

        # Benchmark queries: "show benchmark", "nifty comparison", "how does it compare to nifty"
        if "benchmark" in lowered or "nifty" in lowered:
            return ResolvedIntent(intent_type=IntentType.BENCHMARK_LOOKUP, raw_query=raw)

        return ResolvedIntent(intent_type=IntentType.UNKNOWN, raw_query=raw)
