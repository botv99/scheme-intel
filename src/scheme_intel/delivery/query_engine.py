"""
Complex Query Intelligence Engine for Scheme-Intel (Stage 3).
Answers natural language and multi-stock comparison questions:
- Simple queries: evaluated concisely against validated snapshot facts.
- Research queries: routed to Fresh Multi-Provider Research Orchestrator (snapshot is context, not substitute).
- Graceful degradation: snapshot fallbacks are explicitly labelled with [SNAPSHOT_FALLBACK].
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from ..intelligence_memory.models import IntelligenceSnapshot, CompanyIntelligence
from ..stage2.providers.manager import LLMProviderManager
from ..stage2.providers.base import ProviderResponse
from ..research.classifier import QueryClassifier, QueryType
from ..research.orchestrator import ResearchOrchestrator, ResearchResult
from ..logger import get_logger

logger = get_logger(__name__)


def get_companies_for_scheme(snapshot: IntelligenceSnapshot, scheme_id: Optional[str] = None) -> List[CompanyIntelligence]:
    """Retrieve deduplicated companies strictly isolated for the target scheme."""
    norm_sid = (scheme_id or "").strip().lower()
    comps = []
    seen = set()
    for c in snapshot.companies.values():
        if norm_sid and (getattr(c, "scheme_id", None) or "").lower() != norm_sid:
            continue
        base = (c.symbol or c.short_symbol or "").split(".")[0].upper()
        if not base or base in seen:
            continue
        seen.add(base)
        comps.append(c)
    return comps


class ComplexQueryEngine:
    """Evaluates complex conversational questions with query classification and multi-provider research."""

    def __init__(
        self,
        provider_manager: Optional[LLMProviderManager] = None,
        orchestrator: Optional[ResearchOrchestrator] = None,
    ):
        self.provider_manager = provider_manager or LLMProviderManager()
        self.orchestrator = orchestrator or ResearchOrchestrator(provider_manager=self.provider_manager)

    def process_query(
        self,
        query: str,
        snapshot: IntelligenceSnapshot,
        scheme_id: Optional[str] = "gobardhan",
        target_symbol: Optional[str] = None,
        intent: Optional[str] = None,
        raw_query: Optional[str] = None,
    ) -> str:
        """
        Evaluate conversational query.
        For genuine research queries, triggers fresh multi-provider research with snapshot as background context.
        For simple status/price queries, answers from snapshot facts.
        """
        classification = QueryClassifier.classify(query, intent=intent, raw_query=raw_query)
        effective_scheme = (scheme_id or "gobardhan").strip().lower()

        # 1. Genuine Research Query: Fan out to Research Orchestrator
        if intent == "RESEARCH_REQUEST" or classification in (QueryType.RESEARCH_QUERY, QueryType.DEEP_RESEARCH):
            logger.info("[QUERY ENGINE] Classified as %s (intent=%s): Routing to Research Orchestrator", classification.value, intent)
            res: ResearchResult = self.orchestrator.execute_research(
                query=query,
                scheme_id=effective_scheme,
                snapshot_context=snapshot.model_dump(),
            )
            if res.is_fallback:
                logger.warning("[QUERY ENGINE] Fresh multi-provider research unavailable; returning explicit SNAPSHOT_FALLBACK.")
                deterministic_text = self._deterministic_fallback(query, snapshot, is_fallback=True, scheme_id=effective_scheme)
                return (
                    "⚠️ *[SNAPSHOT_FALLBACK]*\n"
                    "_Fresh multi-provider research unavailable; returning available snapshot intelligence._\n\n"
                    f"{deterministic_text}"
                )
            return res.result_text

        # 2. Simple Query: Snapshot context lookup
        scheme_companies = get_companies_for_scheme(snapshot, scheme_id=effective_scheme)
        context_lines = []
        context_lines.append(f"Scheme ID: {effective_scheme}")
        context_lines.append(f"Snapshot Timestamp: {snapshot.generated_at}")
        context_lines.append(f"Qualified Setups: {', '.join(snapshot.qualified_setups) if snapshot.qualified_setups else 'None'}")
        context_lines.append(f"Waiting Setups: {', '.join(snapshot.waiting_setups) if snapshot.waiting_setups else 'None'}")

        context_lines.append("\nWATCHLIST COMPANIES & STATUS:")
        for comp in scheme_companies:
            sym = comp.symbol or comp.short_symbol
            if comp.price is not None:
                context_lines.append(
                    f"- {sym} ({comp.name}): Price ₹{comp.price:.2f} ({comp.change_pct:+.2f}%), "
                    f"Status: {comp.status}, Setup: {comp.archetype or 'None'} (Score: {comp.score or 'N/A'}), "
                    f"Catalyst: {comp.catalyst or 'None'}, Trend: {comp.trend or 'N/A'}, "
                    f"Target: ₹{comp.target or 'N/A'}, SL: ₹{comp.stop_loss or 'N/A'}"
                )
            if comp.latest_development:
                context_lines.append(f"  Development: {comp.latest_development}")
            if comp.bull_thesis:
                context_lines.append(f"  Bull Thesis: {comp.bull_thesis}")

        context_text = "\n".join(context_lines)

        prompt = (
            "You are Scheme-Intel, an evidence-led government policy and equity market intelligence terminal.\n"
            "Answer the user's specific query concisely based on the provided snapshot facts.\n\n"
            f"=== SNAPSHOT INTELLIGENCE FACTS ===\n{context_text}\n===================================\n\n"
            f"USER QUERY: {query}\n\n"
            "REQUIREMENTS:\n"
            "1. Ground your answer completely in the snapshot data above. Do not hallucinate prices or announcements.\n"
            "2. Keep the response concise, punchy, and formatted with clean Telegram Markdown (*bold*, _italic_, bullet points).\n"
            "3. If data is unavailable in the snapshot, state it clearly.\n"
        )

        try:
            resp: ProviderResponse = self.provider_manager.generate(
                prompt=prompt,
                system_prompt="You are Scheme-Intel, a professional equity intelligence terminal.",
                temperature=0.2,
                caller="complex_query_engine",
            )
            if resp and resp.content and resp.content.strip():
                return resp.content.strip()
        except Exception as e:
            logger.warning("[QUERY ENGINE] LLM generation failed or unavailable (%s). Falling back to deterministic synthesis.", e)

        # 3. Deterministic Fallback Synthesis
        return self._deterministic_fallback(query, snapshot, is_fallback=False, scheme_id=effective_scheme)

    def _deterministic_fallback(
        self,
        query: str,
        snapshot: IntelligenceSnapshot,
        is_fallback: bool = False,
        scheme_id: Optional[str] = "gobardhan",
    ) -> str:
        """Deterministic query synthesizer when no external LLM is reachable."""
        effective_scheme = (scheme_id or "gobardhan").strip().lower()
        scheme_companies = get_companies_for_scheme(snapshot, scheme_id=effective_scheme)
        q_lowered = query.lower()

        # Check for comparison between multiple companies
        matched_companies: List[CompanyIntelligence] = []
        for comp in scheme_companies:
            short = (comp.short_symbol or comp.symbol.split(".")[0]).lower()
            name_parts = comp.name.lower().split()
            if short in q_lowered or any(p in q_lowered for p in name_parts if len(p) > 3):
                if comp not in matched_companies:
                    matched_companies.append(comp)

        if len(matched_companies) >= 2:
            lines = [
                "📊 *Comparative Scheme Analysis*",
                f"Comparing {len(matched_companies)} companies based on latest morning intelligence:",
                "",
            ]
            for comp in matched_companies:
                price_str = f"₹{comp.price:,.2f}" if comp.price is not None else "N/A"
                change_str = f"{comp.change_pct:+.2f}%" if comp.change_pct is not None else "N/A"
                lines.append(f"• *{comp.short_symbol}* ({comp.name}):")
                lines.append(f"  - Price: {price_str} ({change_str}) | Status: `{comp.status}`")
                if comp.catalyst:
                    lines.append(f"  - Catalyst: {comp.catalyst}")
                if comp.archetype:
                    lines.append(f"  - Setup: {comp.archetype} (Score: {comp.score}/100)")
                if comp.target and comp.stop_loss:
                    lines.append(f"  - Levels: Target ₹{comp.target:.2f} | SL ₹{comp.stop_loss:.2f}")
                lines.append("")
            return "\n".join(lines).strip()

        # Strongest catalyst / ranking question
        if "strongest catalyst" in q_lowered or "best" in q_lowered or "rank" in q_lowered or "lead" in q_lowered:
            ranked = sorted(
                scheme_companies,
                key=lambda c: (
                    1 if c.status == "QUALIFIED_SETUP" else (0.5 if c.status == "WAITING" else 0),
                    c.score or 0,
                ),
                reverse=True,
            )
            lines = [
                "🏆 *Strongest Scheme Catalysts & Setups*",
                "Ranked by setup qualification, catalyst strength, and technical momentum:",
                "",
            ]
            for idx, c in enumerate(ranked[:4], 1):
                status_icon = "🟢" if c.status == "QUALIFIED_SETUP" else ("🟡" if c.status == "WAITING" else "⚪")
                lines.append(f"{idx}. {status_icon} *{c.short_symbol}* ({c.name})")
                lines.append(f"   • Status: `{c.status}` | Score: {c.score or 'N/A'}/100")
                if c.catalyst:
                    lines.append(f"   • Catalyst: {c.catalyst}")
                if c.latest_development:
                    lines.append(f"   • Dev: {c.latest_development[:80]}...")
                lines.append("")
            return "\n".join(lines).strip()

        # Underperforming / outperforming
        if "underperforming" in q_lowered or "lag" in q_lowered or "down" in q_lowered:
            laggards = sorted(
                [c for c in scheme_companies if c.change_pct is not None],
                key=lambda c: c.change_pct or 0.0,
            )
            lines = [
                "📉 *Scheme Watchlist Performance Overview*",
                "Relative performance and underperformance diagnostic:",
                "",
            ]
            for c in laggards[:3]:
                lines.append(f"• *{c.short_symbol}*: {c.change_pct:+.2f}% | Trend: {c.trend or 'N/A'}")
                if c.bear_thesis:
                    lines.append(f"  _Bear Factor:_ {c.bear_thesis}")
                lines.append("")
            return "\n".join(lines).strip()

        # General policy / scheme question
        from ..schemes.registry import SchemeRegistry
        scfg = SchemeRegistry.get(effective_scheme)
        scheme_name = scfg.name if scfg else (snapshot.schemes.get(effective_scheme).name if snapshot.schemes.get(effective_scheme) else effective_scheme.title())
        scheme_info = snapshot.schemes.get(effective_scheme)
        lines = [
            f"🏛️ *{scheme_name} Policy & Market Intelligence Summary*",
            "",
            f"• *Covered Watchlist:* {scheme_info.watchlist_count if scheme_info else len(scheme_companies)} stocks",
            f"• *Active Qualified Setups:* {len(snapshot.qualified_setups)}",
            f"• *Waiting Triggers:* {len(snapshot.waiting_setups)}",
            "",
            "*Key Recent Developments:*",
        ]
        devs = scheme_info.key_developments if scheme_info and scheme_info.key_developments else []
        if devs:
            for d in devs[:3]:
                lines.append(f"• {d}")
        else:
            lines.append("• No new official notifications logged in latest scan.")

        sample_stock = "ONGC" if "samudra" in effective_scheme else "TRUALT"
        lines.extend([
            "",
            f"Use `/setups` to view actionable trades, or `/{sample_stock.lower()}` to inspect specific companies.",
        ])
        return "\n".join(lines).strip()
