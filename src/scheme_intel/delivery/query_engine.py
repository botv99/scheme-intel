"""
Complex Query Intelligence Engine for Scheme-Intel (Stage 3).
Answers natural language and multi-stock comparison questions using
the validated IntelligenceSnapshot and multi-provider LLM failover.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from ..intelligence_memory.models import IntelligenceSnapshot, CompanyIntelligence
from ..stage2.providers.manager import LLMProviderManager
from ..stage2.providers.base import ProviderResponse
from ..logger import get_logger

logger = get_logger(__name__)


class ComplexQueryEngine:
    """Evaluates complex conversational questions against snapshot data."""

    def __init__(self, provider_manager: Optional[LLMProviderManager] = None):
        self.provider_manager = provider_manager or LLMProviderManager()

    def process_query(
        self,
        query: str,
        snapshot: IntelligenceSnapshot,
        scheme_id: Optional[str] = "gobardhan",
        target_symbol: Optional[str] = None,
    ) -> str:
        """
        Evaluate complex natural language query against snapshot facts.
        Uses LLMProviderManager if configured; falls back to deterministic synthesis.
        """
        # 1. Build factual context from snapshot
        context_lines = []
        context_lines.append(f"Scheme ID: {scheme_id or 'gobardhan'}")
        context_lines.append(f"Snapshot Timestamp: {snapshot.generated_at}")
        context_lines.append(f"Qualified Setups: {', '.join(snapshot.qualified_setups) if snapshot.qualified_setups else 'None'}")
        context_lines.append(f"Waiting Setups: {', '.join(snapshot.waiting_setups) if snapshot.waiting_setups else 'None'}")

        context_lines.append("\nWATCHLIST COMPANIES & STATUS:")
        for sym, comp in snapshot.companies.items():
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

        # 2. Check if LLM provider is available
        prompt = (
            "You are Scheme-Intel, an evidence-led government policy and equity market intelligence terminal.\n"
            "Answer the user's specific query concisely based STRICTLY on the provided precomputed snapshot facts.\n\n"
            f"=== SNAPSHOT INTELLIGENCE FACTS ===\n{context_text}\n===================================\n\n"
            f"USER QUERY: {query}\n\n"
            "REQUIREMENTS:\n"
            "1. Ground your answer completely in the snapshot data above. Do not hallucinate prices or announcements.\n"
            "2. If comparing companies, contrast their catalysts, setup status, risk/reward, and policy alignment.\n"
            "3. If asked about strongest catalysts or ranking, highlight companies with active catalysts and qualified setups.\n"
            "4. Keep the response concise, punchy, and formatted with clean Telegram Markdown (*bold*, _italic_, bullet points).\n"
            "5. If data is unavailable in the snapshot, state it clearly.\n"
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
        return self._deterministic_fallback(query, snapshot)

    def _deterministic_fallback(self, query: str, snapshot: IntelligenceSnapshot) -> str:
        """Deterministic query synthesizer when no external LLM is reachable."""
        q_lowered = query.lower()

        # Check for comparison between multiple companies
        matched_companies: List[CompanyIntelligence] = []
        for sym, comp in snapshot.companies.items():
            short = sym.split(".")[0].lower()
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
                snapshot.companies.values(),
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
                [c for c in snapshot.companies.values() if c.change_pct is not None],
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
        scheme_info = snapshot.schemes.get("gobardhan")
        lines = [
            "🏛️ *Gobardhan Policy & Market Intelligence Summary*",
            "",
            f"• *Covered Watchlist:* {scheme_info.watchlist_count if scheme_info else len(snapshot.companies)} stocks",
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

        lines.extend([
            "",
            "Use `/setups` to view actionable trades, or `/trualt` to inspect specific companies.",
        ])
        return "\n".join(lines).strip()
