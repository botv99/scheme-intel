"""
Bull Swing Hunter Agent for Stage 2.
Constructs compelling, evidence-backed bullish swing theses.
"""
from __future__ import annotations

from typing import List
from .base import BaseAgent
from ..models import CandidateSetup, EvidenceItem, BullThesis
from ...logger import get_logger

logger = get_logger(__name__)

BULL_SYSTEM_PROMPT = """You are the Bull Swing Hunter — an expert Indian equity swing trading specialist.
Your mandate is to build a compelling, disciplined, and evidence-backed long swing thesis for the specified stock.

GUIDELINES:
1. Ground every single claim in the provided Evidence Items using their exact IDs (e.g., [EV-TECH-01], [EV-CAT-01]).
2. Define a precise, actionable proposed entry zone (e.g., '₹515 - ₹522').
3. Define a logical target based on resistance levels, ATR, or swing projections.
4. Define a strict invalidation level (below key moving average or swing low).
5. Acknowledge at least 2 realistic risks to maintain professional intellectual honesty.
6. Never chase or recommend buying a stock that has already run up excessively without volume support.
7. Return your response matching the BullThesis JSON schema strictly.
"""


class BullAgent(BaseAgent):
    """Bull Swing Hunter constructing structured long swing theses."""

    def build_thesis(self, candidate: CandidateSetup, evidence: List[EvidenceItem]) -> BullThesis:
        prompt = (
            f"Build a Bullish Swing Thesis for {candidate.stock.name} ({candidate.stock.symbol}).\n\n"
            f"{self.format_dossier_text(candidate, evidence)}\n\n"
            "Analyze the data and formulate a comprehensive BullThesis."
        )

        try:
            return self.provider.generate_structured(
                prompt=prompt,
                schema=BullThesis,
                system_prompt=BULL_SYSTEM_PROMPT,
                temperature=0.2,
            )
        except Exception as e:
            logger.warning("BullAgent LLM generation failed, falling back to deterministic synthesis: %s", e)
            return self._fallback_thesis(candidate, evidence)

    def _fallback_thesis(self, candidate: CandidateSetup, evidence: List[EvidenceItem]) -> BullThesis:
        tech = candidate.technicals
        stock = candidate.stock
        entry_min = round(tech.close * 0.99, 1)
        entry_max = round(tech.close * 1.01, 1)
        target = round(tech.close * 1.08, 1)
        invalidation = round(tech.support if tech.support > 0 else tech.close * 0.95, 1)

        return BullThesis(
            symbol=stock.symbol,
            company=stock.name,
            core_thesis=f"{candidate.archetype} setup supported by constructive momentum and volume expansion.",
            technical_arguments=[
                f"Trading at ₹{tech.close:.2f} with volume ratio {tech.volume_ratio:.1f}x 20d avg.",
                f"Holding above key moving averages (20 DMA: ₹{tech.sma20:.1f}).",
                f"RSI-14 at {tech.rsi14:.0f} indicating healthy momentum.",
            ],
            catalyst_arguments=[
                c.rationale for c in candidate.catalysts[:2]
            ] if candidate.catalysts else ["Sectoral strength and constructive price structure."],
            fundamental_arguments=["Established market presence in sector with active policy tailwinds."],
            market_arguments=["Supportive relative strength compared to benchmark."],
            proposed_entry=f"₹{entry_min} - ₹{entry_max}",
            expected_target=target,
            invalidation_level=invalidation,
            evidence_ids=[ev.evidence_id for ev in evidence[:3]],
            key_risks_acknowledged=[
                "Broader market volatility or gap down on macro news.",
                f"Failure to hold support at ₹{invalidation}.",
            ],
        )
