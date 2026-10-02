"""
Deterministic Intent & Entity Resolver for Telegram Terminal Queries (Stage 3).
Resolves user messages into structured intents, execution paths (FAST, WORKFLOW, RESEARCH),
and normalizes company / scheme entities via SchemeRegistry without relying on non-deterministic LLMs.
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


class ExecutionPath(str, Enum):
    FAST = "FAST"
    WORKFLOW = "WORKFLOW"
    RESEARCH = "RESEARCH"


class IntentType(str, Enum):
    START = "START"
    HELP = "HELP"
    HEALTH_CHECK = "HEALTH_CHECK"
    SCHEMES = "SCHEMES"
    SCHEME_LOOKUP = "SCHEME_LOOKUP"
    SWITCH_SCHEME = "SWITCH_SCHEME"
    WATCHLIST = "WATCHLIST"
    STOCK_LOOKUP = "STOCK_LOOKUP"
    STOCK_WHY = "STOCK_WHY"
    STOCK_WHAT = "STOCK_WHAT"
    STOCK_WHEN = "STOCK_WHEN"
    STOCK_WHY_PROMPT = "STOCK_WHY_PROMPT"
    STOCK_WHAT_PROMPT = "STOCK_WHAT_PROMPT"
    STOCK_WHEN_PROMPT = "STOCK_WHEN_PROMPT"
    SETUPS_LOOKUP = "SETUPS_LOOKUP"
    WAITING_LOOKUP = "WAITING_LOOKUP"
    OUTCOMES_LOOKUP = "OUTCOMES_LOOKUP"
    PERFORMANCE_LOOKUP = "PERFORMANCE_LOOKUP"
    BENCHMARK_LOOKUP = "BENCHMARK_LOOKUP"
    RESEARCH_REQUEST = "RESEARCH_REQUEST"
    RESEARCH_PROMPT = "RESEARCH_PROMPT"
    COMPLEX_QUERY = "COMPLEX_QUERY"
    STOCK_PROMPT = "STOCK_PROMPT"
    STOCK_UNKNOWN = "STOCK_UNKNOWN"
    SCHEME_MENU = "SCHEME_MENU"
    INTELLIGENCE_LOOKUP = "INTELLIGENCE_LOOKUP"
    UNKNOWN = "UNKNOWN"


class ResolvedIntent(BaseModel):
    """Normalized intent result with extracted entities and execution path."""
    intent_type: IntentType
    execution_path: ExecutionPath = ExecutionPath.FAST
    symbol: Optional[str] = None           # Canonical symbol e.g., "TRUALT.NS"
    short_symbol: Optional[str] = None     # Base ticker e.g., "TRUALT"
    company_name: Optional[str] = None     # Full company name e.g., "TruAlt Bioenergy"
    scheme_id: Optional[str] = None        # Scheme ID e.g., "gobardhan"
    unresolved_symbol: Optional[str] = None # When user requests an unrecognized stock
    raw_query: str = ""
    normalized_query: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)


GLOBAL_STOCK_ALIASES: Dict[str, Dict[str, Any]] = {
    # GOBARdhan
    "TRUALT": {"symbol": "TRUALT.NS", "short": "TRUALT", "name": "TruAlt Bioenergy", "scheme": "gobardhan"},
    "TRUALT.NS": {"symbol": "TRUALT.NS", "short": "TRUALT", "name": "TruAlt Bioenergy", "scheme": "gobardhan"},
    "TRUALT BIOENERGY": {"symbol": "TRUALT.NS", "short": "TRUALT", "name": "TruAlt Bioenergy", "scheme": "gobardhan"},
    "PRAJ": {"symbol": "PRAJIND.NS", "short": "PRAJIND", "name": "Praj Industries", "scheme": "gobardhan"},
    "PRAJIND": {"symbol": "PRAJIND.NS", "short": "PRAJIND", "name": "Praj Industries", "scheme": "gobardhan"},
    "PRAJIND.NS": {"symbol": "PRAJIND.NS", "short": "PRAJIND", "name": "Praj Industries", "scheme": "gobardhan"},
    "PRAJ INDUSTRIES": {"symbol": "PRAJIND.NS", "short": "PRAJIND", "name": "Praj Industries", "scheme": "gobardhan"},
    "WABAG": {"symbol": "WABAG.NS", "short": "WABAG", "name": "VA Tech Wabag", "scheme": "gobardhan"},
    "WABAG.NS": {"symbol": "WABAG.NS", "short": "WABAG", "name": "VA Tech Wabag", "scheme": "gobardhan"},
    "VA TECH WABAG": {"symbol": "WABAG.NS", "short": "WABAG", "name": "VA Tech Wabag", "scheme": "gobardhan"},
    "ORGANIC": {"symbol": "ORGANICREC.BO", "short": "ORGANICREC", "name": "Organic Recycling Systems", "scheme": "gobardhan"},
    "ORGANICREC": {"symbol": "ORGANICREC.BO", "short": "ORGANICREC", "name": "Organic Recycling Systems", "scheme": "gobardhan"},
    "ORGANICREC.BO": {"symbol": "ORGANICREC.BO", "short": "ORGANICREC", "name": "Organic Recycling Systems", "scheme": "gobardhan"},
    "ORGANIC RECYCLING SYSTEMS": {"symbol": "ORGANICREC.BO", "short": "ORGANICREC", "name": "Organic Recycling Systems", "scheme": "gobardhan"},
    "KIRLPN": {"symbol": "KIRLPNU.NS", "short": "KIRLPNU", "name": "Kirloskar Pneumatic", "scheme": "gobardhan"},
    "KIRLPNU": {"symbol": "KIRLPNU.NS", "short": "KIRLPNU", "name": "Kirloskar Pneumatic", "scheme": "gobardhan"},
    "KIRLPNU.NS": {"symbol": "KIRLPNU.NS", "short": "KIRLPNU", "name": "Kirloskar Pneumatic", "scheme": "gobardhan"},
    "KIRLOSKAR": {"symbol": "KIRLPNU.NS", "short": "KIRLPNU", "name": "Kirloskar Pneumatic", "scheme": "gobardhan"},
    "KIRLOSKAR PNEUMATIC": {"symbol": "KIRLPNU.NS", "short": "KIRLPNU", "name": "Kirloskar Pneumatic", "scheme": "gobardhan"},
    "GAIL": {"symbol": "GAIL.NS", "short": "GAIL", "name": "GAIL (India)", "scheme": "gobardhan"},
    "GAIL.NS": {"symbol": "GAIL.NS", "short": "GAIL", "name": "GAIL (India)", "scheme": "gobardhan"},
    "GAIL INDIA": {"symbol": "GAIL.NS", "short": "GAIL", "name": "GAIL (India)", "scheme": "gobardhan"},
    "IOC": {"symbol": "IOC.NS", "short": "IOC", "name": "Indian Oil Corporation", "scheme": "gobardhan"},
    "IOCL": {"symbol": "IOC.NS", "short": "IOC", "name": "Indian Oil Corporation", "scheme": "gobardhan"},
    "IOC.NS": {"symbol": "IOC.NS", "short": "IOC", "name": "Indian Oil Corporation", "scheme": "gobardhan"},
    "INDIAN OIL": {"symbol": "IOC.NS", "short": "IOC", "name": "Indian Oil Corporation", "scheme": "gobardhan"},
    "IONEXCHANG": {"symbol": "IONEXCHANG.NS", "short": "IONEXCHANG", "name": "Ion Exchange", "scheme": "gobardhan"},
    "IONEXCHANG.NS": {"symbol": "IONEXCHANG.NS", "short": "IONEXCHANG", "name": "Ion Exchange", "scheme": "gobardhan"},
    "ION EXCHANGE": {"symbol": "IONEXCHANG.NS", "short": "IONEXCHANG", "name": "Ion Exchange", "scheme": "gobardhan"},

    # Samudra Manthan
    "ONGC": {"symbol": "ONGC.NS", "short": "ONGC", "name": "Oil and Natural Gas Corporation", "scheme": "samudra_manthan"},
    "ONGC.NS": {"symbol": "ONGC.NS", "short": "ONGC", "name": "Oil and Natural Gas Corporation", "scheme": "samudra_manthan"},
    "OIL": {"symbol": "OIL.NS", "short": "OIL", "name": "Oil India Limited", "scheme": "samudra_manthan"},
    "OIL.NS": {"symbol": "OIL.NS", "short": "OIL", "name": "Oil India Limited", "scheme": "samudra_manthan"},
    "OIL INDIA": {"symbol": "OIL.NS", "short": "OIL", "name": "Oil India Limited", "scheme": "samudra_manthan"},
    "RELIANCE": {"symbol": "RELIANCE.NS", "short": "RELIANCE", "name": "Reliance Industries", "scheme": "samudra_manthan"},
    "RELIANCE.NS": {"symbol": "RELIANCE.NS", "short": "RELIANCE", "name": "Reliance Industries", "scheme": "samudra_manthan"},
    "RIL": {"symbol": "RELIANCE.NS", "short": "RELIANCE", "name": "Reliance Industries", "scheme": "samudra_manthan"},
    "VEDL": {"symbol": "VEDL.NS", "short": "VEDL", "name": "Vedanta Limited", "scheme": "samudra_manthan"},
    "VEDL.NS": {"symbol": "VEDL.NS", "short": "VEDL", "name": "Vedanta Limited", "scheme": "samudra_manthan"},
    "VEDANTA": {"symbol": "VEDL.NS", "short": "VEDL", "name": "Vedanta Limited", "scheme": "samudra_manthan"},
    "JINDAL DRILLING": {"symbol": "JINDCOT.NS", "short": "JINDCOT", "name": "Jindal Drilling & Industries", "scheme": "samudra_manthan"},
    "JINDCOT": {"symbol": "JINDCOT.NS", "short": "JINDCOT", "name": "Jindal Drilling & Industries", "scheme": "samudra_manthan"},
    "SEAMEC": {"symbol": "SEAMECLTD.NS", "short": "SEAMECLTD", "name": "SEAMEC Limited", "scheme": "samudra_manthan"},
    "DOLPHIN": {"symbol": "DOLPHIN.NS", "short": "DOLPHIN", "name": "Dolphin Offshore Enterprises", "scheme": "samudra_manthan"},
}

STOCK_SLASH_SHORTCUTS: Dict[str, str] = {
    "/trualt": "TRUALT",
    "/praj": "PRAJ",
    "/prajind": "PRAJ",
    "/wabag": "WABAG",
    "/organic": "ORGANIC",
    "/organicrec": "ORGANICREC",
    "/kirloskar": "KIRLOSKAR",
    "/kirlpn": "KIRLPN",
    "/kirlpnu": "KIRLPNU",
    "/gail": "GAIL",
    "/ioc": "IOC",
    "/iocl": "IOC",
    "/ionexchang": "IONEXCHANG",
    "/ongc": "ONGC",
    "/oil": "OIL",
    "/reliance": "RELIANCE",
    "/ril": "RELIANCE",
    "/vedl": "VEDL",
    "/vedanta": "VEDL",
    "/jindcot": "JINDCOT",
    "/seamec": "SEAMEC",
    "/dolphin": "DOLPHIN",
}


class IntentResolver:
    """Deterministic parser, stock alias resolver, and execution path router."""

    @classmethod
    def resolve_stock(cls, text: str) -> Optional[Tuple[SchemeStock, str]]:
        """Resolve a string token to a SchemeStock and its scheme_id."""
        if not text:
            return None
        token = text.strip().upper()
        token_norm = re.sub(r"\s+", " ", token)
        token_clean = re.sub(r"[^\w\.]", "", token)

        # 1. Direct dictionary match
        if token_norm in GLOBAL_STOCK_ALIASES:
            meta = GLOBAL_STOCK_ALIASES[token_norm]
            stock = SchemeStock(
                name=meta["name"],
                symbol=meta["symbol"],
                aliases=[meta["short"]],
                screener_id=meta["short"],
                sectors=["Bio-Energy"],
                rationale="Watchlist company mapped to scheme.",
            )
            return stock, meta["scheme"]

        if token_clean in GLOBAL_STOCK_ALIASES:
            meta = GLOBAL_STOCK_ALIASES[token_clean]
            stock = SchemeStock(
                name=meta["name"],
                symbol=meta["symbol"],
                aliases=[meta["short"]],
                screener_id=meta["short"],
                sectors=["Bio-Energy"],
                rationale="Watchlist company mapped to scheme.",
            )
            return stock, meta["scheme"]

        # 2. SchemeRegistry search
        for scheme in SchemeRegistry.list_schemes():
            for stock in scheme.watchlist:
                sym_upper = stock.symbol.upper()
                short_upper = sym_upper.split(".")[0]

                if token_clean in (sym_upper, short_upper, short_upper.replace("-", "_")):
                    return stock, scheme.id

                if stock.screener_id and token_clean == stock.screener_id.upper():
                    return stock, scheme.id

                if token_norm == stock.name.upper() or token_clean == re.sub(r"[^\w\.]", "", stock.name.upper()):
                    return stock, scheme.id
                for alias in stock.aliases:
                    if token_norm == alias.upper() or token_clean == re.sub(r"[^\w\.]", "", alias.upper()):
                        return stock, scheme.id

        return None

    @classmethod
    def resolve_scheme(cls, text: str) -> Optional[SchemeConfig]:
        """Resolve scheme name or ID to SchemeConfig for short tokens (<= 3 words)."""
        token = text.strip().lower()
        if not token:
            return None
        token_clean = re.sub(r"[^\w\s]", "", token).strip()

        for scheme in SchemeRegistry.list_schemes():
            if token_clean in (scheme.id.lower(), scheme.name.lower()):
                return scheme
            # Only match partial for short tokens (<= 3 words)
            if len(token_clean.split()) <= 3 and (scheme.id.lower() in token_clean or token_clean in scheme.id.lower()):
                return scheme
        return None

    @classmethod
    def find_all_stocks_in_text(cls, text: str) -> List[Tuple[SchemeStock, str]]:
        """Find all distinct stocks mentioned in natural language text."""
        if not text:
            return []
        found: Dict[str, Tuple[SchemeStock, str]] = {}
        text_upper = f" {text.upper()} "

        # Check multi-word aliases
        for alias_key in GLOBAL_STOCK_ALIASES.keys():
            if f" {alias_key} " in text_upper:
                res = cls.resolve_stock(alias_key)
                if res:
                    stock, s_id = res
                    found[stock.symbol] = (stock, s_id)

        # Check individual words
        for word in text.split():
            clean_word = re.sub(r"[^\w\.]", "", word)
            if clean_word:
                m = cls.resolve_stock(clean_word)
                if m:
                    found[m[0].symbol] = m

        return list(found.values())

    @classmethod
    def find_stock_in_text(cls, text: str) -> Optional[Tuple[SchemeStock, str]]:
        """Scan a natural language sentence for the primary stock."""
        all_stocks = cls.find_all_stocks_in_text(text)
        return all_stocks[0] if all_stocks else None

    @classmethod
    def normalize_query(cls, text: str) -> str:
        """Create normalized query string for deduplication and logging."""
        lowered = text.lower().strip()
        return re.sub(r"\s+", " ", lowered)

    @classmethod
    def is_complex_query(cls, text: str) -> bool:
        """
        Determine if query represents a complex analytical or comparison question
        requiring the 04-telegram-query GitHub Actions workflow.
        """
        lowered = text.lower().strip()

        # Multi-stock comparison questions: "Compare TRUALT and PRAJ"
        stocks_found = cls.find_all_stocks_in_text(text)
        if len(stocks_found) >= 2:
            return True

        complex_phrases = [
            "compare",
            "strongest catalyst",
            "strongest catalysts",
            "underperforming",
            "outperforming",
            "what changed in",
            "which companies have",
            "which gobardhan companies",
            "affected companies",
            "policy change",
            "catalyst this week",
            "catalysts this week",
            "rank",
            "ranking",
            "correlation",
            "versus",
            " vs ",
        ]
        for phrase in complex_phrases:
            if phrase in lowered:
                return True

        # If it specifically mentions exactly 1 stock without complex phrases, it is a fast stock query
        if len(stocks_found) == 1:
            return False

        # General questions with >= 5 words that are not simple fast queries
        words = text.split()
        if len(words) >= 5 and ("?" in text or any(q in lowered for q in ("which", "why", "how", "what", "who", "where"))):
            simple_exclusions = [
                "what are today's setups",
                "what are the setups",
                "which stocks are waiting",
                "how is gobardhan doing",
                "what about trualt",
                "tell me about trualt",
                "what is happening with trualt",
                "why is trualt interesting",
                "when to enter trualt",
            ]
            if not any(exc in lowered for exc in simple_exclusions):
                return True

        return False

    @classmethod
    def resolve(cls, message: str, active_scheme: Optional[str] = None) -> ResolvedIntent:
        """
        Parse user Telegram message into a ResolvedIntent with execution_path:
        - FAST: Answered instantly (<100ms) from local snapshot. Zero GitHub Actions.
        - WORKFLOW: Complex analytical query routed to 04-telegram-query.yml via repository_dispatch.
        - RESEARCH: Explicit deep research routed to persistent ResearchQueue.
        """
        raw = (message or "").strip()
        normalized = cls.normalize_query(raw)
        effective_scheme = (active_scheme or "gobardhan").strip().lower()

        if not raw:
            return ResolvedIntent(
                intent_type=IntentType.UNKNOWN,
                execution_path=ExecutionPath.FAST,
                scheme_id=effective_scheme,
                raw_query=raw,
                normalized_query=normalized,
            )

        # ====================================================
        # 0. Telegram Button Callbacks & Scheme Routing
        # ====================================================
        if raw.startswith("scheme_select:"):
            target_scheme = raw.split(":", 1)[1].strip().lower()
            return ResolvedIntent(
                intent_type=IntentType.SWITCH_SCHEME,
                execution_path=ExecutionPath.FAST,
                scheme_id=target_scheme,
                raw_query=raw,
                normalized_query=normalized,
                parameters={"target_scheme": target_scheme},
            )

        if raw.startswith("scheme_action:"):
            parts = raw.split(":")
            action = parts[1].strip().lower() if len(parts) > 1 else ""
            action_scheme = parts[2].strip().lower() if len(parts) > 2 else effective_scheme
            if action == "watchlist":
                return ResolvedIntent(intent_type=IntentType.WATCHLIST, execution_path=ExecutionPath.FAST, scheme_id=action_scheme, raw_query=raw, normalized_query=normalized)
            if action in ("trades", "setups"):
                return ResolvedIntent(intent_type=IntentType.SETUPS_LOOKUP, execution_path=ExecutionPath.FAST, scheme_id=action_scheme, raw_query=raw, normalized_query=normalized)
            if action == "research":
                return ResolvedIntent(intent_type=IntentType.RESEARCH_PROMPT, execution_path=ExecutionPath.FAST, scheme_id=action_scheme, raw_query=raw, normalized_query=normalized)
            if action in ("intelligence", "news"):
                return ResolvedIntent(intent_type=IntentType.INTELLIGENCE_LOOKUP, execution_path=ExecutionPath.FAST, scheme_id=action_scheme, raw_query=raw, normalized_query=normalized)
            if action in ("snapshot", "scheme"):
                return ResolvedIntent(intent_type=IntentType.SCHEME_LOOKUP, execution_path=ExecutionPath.FAST, scheme_id=action_scheme, raw_query=raw, normalized_query=normalized)
            if action in ("switch_scheme", "switch", "schemes"):
                return ResolvedIntent(intent_type=IntentType.SCHEMES, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)
            if action in ("menu", "back"):
                return ResolvedIntent(intent_type=IntentType.SCHEME_MENU, execution_path=ExecutionPath.FAST, scheme_id=action_scheme, raw_query=raw, normalized_query=normalized)

        parts = raw.split(maxsplit=1)
        first_token = parts[0].lower().split("@")[0]
        remainder = parts[1].strip() if len(parts) > 1 else ""

        # ====================================================
        # 1. Explicit Slash Commands (FAST & RESEARCH)
        # ====================================================
        if first_token.startswith("/"):
            # Stock shortcuts: /trualt, /praj, /ongc, etc.
            if first_token in STOCK_SLASH_SHORTCUTS:
                alias_key = STOCK_SLASH_SHORTCUTS[first_token]
                stock_match = cls.resolve_stock(alias_key)
                if stock_match:
                    stock, s_id = stock_match
                    return ResolvedIntent(
                        intent_type=IntentType.STOCK_LOOKUP,
                        execution_path=ExecutionPath.FAST,
                        symbol=stock.symbol,
                        short_symbol=stock.symbol.split(".")[0],
                        company_name=stock.name,
                        scheme_id=s_id,
                        raw_query=raw,
                        normalized_query=normalized,
                    )

            if first_token in ("/start",):
                return ResolvedIntent(intent_type=IntentType.START, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)

            if first_token in ("/menu",):
                return ResolvedIntent(intent_type=IntentType.SCHEME_MENU, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)

            if first_token in ("/help",):
                return ResolvedIntent(intent_type=IntentType.HELP, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)

            if first_token in ("/health", "/status"):
                return ResolvedIntent(intent_type=IntentType.HEALTH_CHECK, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)

            if first_token in ("/switch",):
                target = remainder.strip().lower()
                target_scheme = target
                scheme = cls.resolve_scheme(target) if target else None
                if scheme:
                    target_scheme = scheme.id
                return ResolvedIntent(
                    intent_type=IntentType.SWITCH_SCHEME,
                    execution_path=ExecutionPath.FAST,
                    scheme_id=target_scheme,
                    raw_query=raw,
                    normalized_query=normalized,
                    parameters={"target_scheme": target_scheme},
                )

            if first_token in ("/schemes",):
                return ResolvedIntent(intent_type=IntentType.SCHEMES, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)

            if first_token in ("/watchlist",):
                target_scheme = effective_scheme
                if remainder:
                    scheme = cls.resolve_scheme(remainder)
                    if scheme:
                        target_scheme = scheme.id
                return ResolvedIntent(
                    intent_type=IntentType.WATCHLIST,
                    execution_path=ExecutionPath.FAST,
                    scheme_id=target_scheme,
                    raw_query=raw,
                    normalized_query=normalized,
                )

            if first_token in ("/scheme", "/snapshot"):
                scheme_target = remainder or effective_scheme
                scheme = cls.resolve_scheme(scheme_target)
                return ResolvedIntent(
                    intent_type=IntentType.SCHEME_LOOKUP,
                    execution_path=ExecutionPath.FAST,
                    scheme_id=scheme.id if scheme else scheme_target,
                    raw_query=raw,
                    normalized_query=normalized,
                )

            if first_token in ("/intelligence", "/news"):
                return ResolvedIntent(
                    intent_type=IntentType.INTELLIGENCE_LOOKUP,
                    execution_path=ExecutionPath.FAST,
                    scheme_id=effective_scheme,
                    raw_query=raw,
                    normalized_query=normalized,
                )

            if first_token in ("/setups", "/trades"):
                return ResolvedIntent(
                    intent_type=IntentType.SETUPS_LOOKUP,
                    execution_path=ExecutionPath.FAST,
                    scheme_id=effective_scheme,
                    raw_query=raw,
                    normalized_query=normalized,
                )

            if first_token in ("/waiting",):
                return ResolvedIntent(
                    intent_type=IntentType.WAITING_LOOKUP,
                    execution_path=ExecutionPath.FAST,
                    scheme_id=effective_scheme,
                    raw_query=raw,
                    normalized_query=normalized,
                )

            if first_token in ("/outcomes",):
                return ResolvedIntent(
                    intent_type=IntentType.OUTCOMES_LOOKUP,
                    execution_path=ExecutionPath.FAST,
                    scheme_id=effective_scheme,
                    raw_query=raw,
                    normalized_query=normalized,
                )

            if first_token in ("/performance",):
                return ResolvedIntent(
                    intent_type=IntentType.PERFORMANCE_LOOKUP,
                    execution_path=ExecutionPath.FAST,
                    scheme_id=effective_scheme,
                    raw_query=raw,
                    normalized_query=normalized,
                )

            if first_token in ("/benchmark",):
                return ResolvedIntent(
                    intent_type=IntentType.BENCHMARK_LOOKUP,
                    execution_path=ExecutionPath.FAST,
                    scheme_id=effective_scheme,
                    raw_query=raw,
                    normalized_query=normalized,
                )

            if first_token in ("/research",):
                if not remainder:
                    return ResolvedIntent(
                        intent_type=IntentType.RESEARCH_PROMPT,
                        execution_path=ExecutionPath.FAST,
                        scheme_id=effective_scheme,
                        raw_query=raw,
                        normalized_query=normalized,
                    )
                question = remainder
                scheme_id = effective_scheme
                for s in SchemeRegistry.list_schemes():
                    if s.id.lower() in question.lower() or s.name.lower() in question.lower():
                        scheme_id = s.id
                        break
                return ResolvedIntent(
                    intent_type=IntentType.RESEARCH_REQUEST,
                    execution_path=ExecutionPath.RESEARCH,
                    scheme_id=scheme_id,
                    raw_query=raw,
                    normalized_query=normalized,
                    parameters={"question": question},
                )

            if first_token in ("/why",):
                if not remainder:
                    return ResolvedIntent(intent_type=IntentType.STOCK_WHY_PROMPT, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)
                match = cls.find_stock_in_text(remainder)
                if match:
                    stock, s_id = match
                    return ResolvedIntent(intent_type=IntentType.STOCK_WHY, execution_path=ExecutionPath.FAST, symbol=stock.symbol, short_symbol=stock.symbol.split(".")[0], company_name=stock.name, scheme_id=s_id, raw_query=raw, normalized_query=normalized)
                return ResolvedIntent(intent_type=IntentType.STOCK_WHY, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized, parameters={"unresolved_symbol": remainder})

            if first_token in ("/what",):
                if not remainder:
                    return ResolvedIntent(intent_type=IntentType.STOCK_WHAT_PROMPT, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)
                rem_lower = remainder.lower()
                if "setup" in rem_lower:
                    return ResolvedIntent(intent_type=IntentType.SETUPS_LOOKUP, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)
                if "waiting" in rem_lower or "wait" in rem_lower:
                    return ResolvedIntent(intent_type=IntentType.WAITING_LOOKUP, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)
                if "performance" in rem_lower:
                    return ResolvedIntent(intent_type=IntentType.PERFORMANCE_LOOKUP, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)
                if "benchmark" in rem_lower or "nifty" in rem_lower:
                    return ResolvedIntent(intent_type=IntentType.BENCHMARK_LOOKUP, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)
                match = cls.find_stock_in_text(remainder)
                if match:
                    stock, s_id = match
                    return ResolvedIntent(intent_type=IntentType.STOCK_WHAT, execution_path=ExecutionPath.FAST, symbol=stock.symbol, short_symbol=stock.symbol.split(".")[0], company_name=stock.name, scheme_id=s_id, raw_query=raw, normalized_query=normalized)
                return ResolvedIntent(intent_type=IntentType.STOCK_WHAT, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized, parameters={"unresolved_symbol": remainder})

            if first_token in ("/when",):
                if not remainder:
                    return ResolvedIntent(intent_type=IntentType.STOCK_WHEN_PROMPT, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)
                match = cls.find_stock_in_text(remainder)
                if match:
                    stock, s_id = match
                    return ResolvedIntent(intent_type=IntentType.STOCK_WHEN, execution_path=ExecutionPath.FAST, symbol=stock.symbol, short_symbol=stock.symbol.split(".")[0], company_name=stock.name, scheme_id=s_id, raw_query=raw, normalized_query=normalized)
                return ResolvedIntent(intent_type=IntentType.STOCK_WHEN, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized, parameters={"unresolved_symbol": remainder})

            if first_token in ("/stock",):
                if not remainder:
                    return ResolvedIntent(intent_type=IntentType.STOCK_PROMPT, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)
                match = cls.resolve_stock(remainder) or cls.find_stock_in_text(remainder)
                if match:
                    stock, s_id = match
                    return ResolvedIntent(
                        intent_type=IntentType.STOCK_LOOKUP,
                        execution_path=ExecutionPath.FAST,
                        symbol=stock.symbol,
                        short_symbol=stock.symbol.split(".")[0],
                        company_name=stock.name,
                        scheme_id=s_id,
                        raw_query=raw,
                        normalized_query=normalized,
                    )
                return ResolvedIntent(
                    intent_type=IntentType.STOCK_LOOKUP,
                    execution_path=ExecutionPath.FAST,
                    symbol=remainder.strip().upper(),
                    short_symbol=remainder.strip().upper(),
                    unresolved_symbol=remainder.strip().upper(),
                    raw_query=raw,
                    normalized_query=normalized,
                    parameters={"unresolved_symbol": remainder.strip().upper()},
                )

        # ====================================================
        # 2. Path B: Complex Analytical Query Detection (WORKFLOW)
        # ====================================================
        if cls.is_complex_query(raw):
            stocks = cls.find_all_stocks_in_text(raw)
            primary_stock = stocks[0][0].symbol if stocks else None
            return ResolvedIntent(
                intent_type=IntentType.COMPLEX_QUERY,
                execution_path=ExecutionPath.WORKFLOW,
                symbol=primary_stock,
                scheme_id="gobardhan",
                raw_query=raw,
                normalized_query=normalized,
                parameters={"stocks_mentioned": [s[0].symbol for s in stocks]},
            )

        # ====================================================
        # 3. Direct Watchlist Shorthand (e.g. "TRUALT", "PRAJIND")
        # ====================================================
        stock_match = cls.resolve_stock(raw)
        if stock_match:
            stock, s_id = stock_match
            return ResolvedIntent(
                intent_type=IntentType.STOCK_LOOKUP,
                execution_path=ExecutionPath.FAST,
                symbol=stock.symbol,
                short_symbol=stock.symbol.split(".")[0],
                company_name=stock.name,
                scheme_id=s_id,
                raw_query=raw,
                normalized_query=normalized,
            )

        scheme_match = cls.resolve_scheme(raw)
        if scheme_match:
            return ResolvedIntent(
                intent_type=IntentType.SCHEME_LOOKUP,
                execution_path=ExecutionPath.FAST,
                scheme_id=scheme_match.id,
                raw_query=raw,
                normalized_query=normalized,
            )

        # ====================================================
        # 4. Natural Language Fast Lookups
        # ====================================================
        lowered = normalized

        # Words without slash & Button Clicks
        clean_action = re.sub(r"[^\w\s]", "", lowered).strip()
        if clean_action in ("menu", "back", "main menu"):
            return ResolvedIntent(intent_type=IntentType.SCHEME_MENU, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)
        if clean_action in ("switch scheme", "switch schemes"):
            return ResolvedIntent(intent_type=IntentType.SCHEMES, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)
        if clean_action in ("intelligence", "news"):
            return ResolvedIntent(intent_type=IntentType.INTELLIGENCE_LOOKUP, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)
        if clean_action in ("research",):
            return ResolvedIntent(intent_type=IntentType.RESEARCH_PROMPT, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)
        if clean_action in ("snapshot", "scheme snapshot"):
            return ResolvedIntent(intent_type=IntentType.SCHEME_LOOKUP, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)
        if clean_action in ("watchlist", "view watchlist"):
            return ResolvedIntent(intent_type=IntentType.WATCHLIST, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)
        if clean_action in ("trades", "trade", "setups", "setup"):
            return ResolvedIntent(intent_type=IntentType.SETUPS_LOOKUP, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)

        if first_token in ("start",):
            return ResolvedIntent(intent_type=IntentType.START, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)
        if first_token in ("help",):
            return ResolvedIntent(intent_type=IntentType.HELP, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)
        if first_token in ("why",) and not remainder:
            return ResolvedIntent(intent_type=IntentType.STOCK_WHY_PROMPT, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)
        if first_token in ("what",) and not remainder:
            return ResolvedIntent(intent_type=IntentType.STOCK_WHAT_PROMPT, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)
        if first_token in ("when",) and not remainder:
            return ResolvedIntent(intent_type=IntentType.STOCK_WHEN_PROMPT, execution_path=ExecutionPath.FAST, raw_query=raw, normalized_query=normalized)

        # Check single stock in natural language first
        stock_in_sentence = cls.find_stock_in_text(raw)
        if stock_in_sentence:
            stock, s_id = stock_in_sentence
            if "why" in lowered:
                return ResolvedIntent(
                    intent_type=IntentType.STOCK_WHY,
                    execution_path=ExecutionPath.FAST,
                    symbol=stock.symbol,
                    short_symbol=stock.symbol.split(".")[0],
                    company_name=stock.name,
                    scheme_id=s_id,
                    raw_query=raw,
                    normalized_query=normalized,
                )
            if "when" in lowered or "entry" in lowered or "trigger" in lowered:
                return ResolvedIntent(
                    intent_type=IntentType.STOCK_WHEN,
                    execution_path=ExecutionPath.FAST,
                    symbol=stock.symbol,
                    short_symbol=stock.symbol.split(".")[0],
                    company_name=stock.name,
                    scheme_id=s_id,
                    raw_query=raw,
                    normalized_query=normalized,
                )
            if "what" in lowered or "about" in lowered or "happening" in lowered or "happened" in lowered or "news" in lowered:
                return ResolvedIntent(
                    intent_type=IntentType.STOCK_WHAT,
                    execution_path=ExecutionPath.FAST,
                    symbol=stock.symbol,
                    short_symbol=stock.symbol.split(".")[0],
                    company_name=stock.name,
                    scheme_id=s_id,
                    raw_query=raw,
                    normalized_query=normalized,
                )
            return ResolvedIntent(
                intent_type=IntentType.STOCK_LOOKUP,
                execution_path=ExecutionPath.FAST,
                symbol=stock.symbol,
                short_symbol=stock.symbol.split(".")[0],
                company_name=stock.name,
                scheme_id=s_id,
                raw_query=raw,
                normalized_query=normalized,
            )

        if "setup" in lowered or "trade" in lowered:
            return ResolvedIntent(intent_type=IntentType.SETUPS_LOOKUP, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)

        if "waiting" in lowered or "wait" in lowered:
            return ResolvedIntent(intent_type=IntentType.WAITING_LOOKUP, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)

        if "performance" in lowered or "win rate" in lowered or "expectancy" in lowered:
            return ResolvedIntent(intent_type=IntentType.PERFORMANCE_LOOKUP, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)

        if "benchmark" in lowered or "nifty" in lowered:
            return ResolvedIntent(intent_type=IntentType.BENCHMARK_LOOKUP, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)

        if "schemes" in lowered or "list schemes" in lowered:
            return ResolvedIntent(intent_type=IntentType.SCHEMES, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)

        if "watchlist" in lowered:
            return ResolvedIntent(intent_type=IntentType.WATCHLIST, execution_path=ExecutionPath.FAST, scheme_id=effective_scheme, raw_query=raw, normalized_query=normalized)

        for s in SchemeRegistry.list_schemes():
            if s.id.lower() in lowered or s.name.lower() in lowered:
                return ResolvedIntent(intent_type=IntentType.SCHEME_LOOKUP, execution_path=ExecutionPath.FAST, scheme_id=s.id, raw_query=raw, normalized_query=normalized)

        # Fallback question -> WORKFLOW
        if "?" in raw or any(q in lowered for q in ("who", "where", "how", "tell me", "explain", "analyze")):
            return ResolvedIntent(
                intent_type=IntentType.COMPLEX_QUERY,
                execution_path=ExecutionPath.WORKFLOW,
                scheme_id=effective_scheme,
                raw_query=raw,
                normalized_query=normalized,
            )

        # Default fallback unknown query
        return ResolvedIntent(
            intent_type=IntentType.UNKNOWN,
            execution_path=ExecutionPath.FAST,
            raw_query=raw,
            normalized_query=normalized,
        )
