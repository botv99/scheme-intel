"""
Bear Trade Killer Agent for Stage 2.
Identifies fatal flaws, false breakout traps, overhead resistance, and defines wait conditions.
"""
from __future__ import annotations

from typing import List, Optional
from .base import BaseAgent
from ..models import CandidateSetup, EvidenceItem, BullThesis, BearThesis
from ...logger import get_logger

logger = get_logger(__name__)

BEAR_SYSTEM_PROMPT = """You are the Bear Trade Killer — a ruthless risk manager and institutional swing trader.
Your job is to protect capital by finding every reason NOT to take this swing trade.

GUIDELINES:
1. Actively hunt for trade killers: overhead supply zones, declining volume on rallies, overbought RSI, 'buy the rumor / sell the news' traps, macro or sector headwinds, and poor risk-to-reward ratios.
2. Directly refute weak or over-optimistic bull claims citing Evidence IDs.
3. Crucially, define:
   - 'what_would_invalidate_bear': The specific market price action or evidence that would prove you wrong.
   - 'required_confirmation_to_buy': The exact trigger or price confirmation the trader must WAIT for before pulling the trigger (e.g., 'Wait for breakout above ₹530 on >1.5x volume and daily closing confirmation').
4. Keep all flaws and arguments concise and focused (1-2 punchy sentences each).
5. Return your response matching the BearThesis JSON schema strictly.
"""


class BearAgent(BaseAgent):
    """Bear Trade Killer identifying risks, failure points, and wait triggers."""

    def build_thesis(
        self,
        candidate: CandidateSetup,
        evidence: List[EvidenceItem],
        bull_thesis: Optional[BullThesis] = None,
    ) -> BearThesis:
        bull_context = ""
        if bull_thesis:
            bull_context = (
                f"\n=== BULL THESIS PROPOSED ===\n"
                f"Core Thesis: {bull_thesis.core_thesis}\n"
                f"Proposed Entry: {bull_thesis.proposed_entry}\n"
                f"Target: ₹{bull_thesis.expected_target} | Invalidation: ₹{bull_thesis.invalidation_level}\n"
                f"Key Arguments: {'; '.join(bull_thesis.technical_arguments[:2])}\n"
            )

        prompt = (
            f"Critique and stress-test the proposed swing trade for {candidate.stock.name} ({candidate.stock.symbol}).\n\n"
            f"{self.format_dossier_text(candidate, evidence)}\n"
            f"{bull_context}\n\n"
            "Formulate a rigorous BearThesis attacking the trade structure, catalyst durability, and technical vulnerabilities."
        )

        try:
            return self.provider.generate_structured(
                prompt=prompt,
                schema=BearThesis,
                system_prompt=BEAR_SYSTEM_PROMPT,
                temperature=0.2,
            )
        except Exception as e:
            logger.warning("BearAgent LLM generation failed, falling back to deterministic synthesis: %s", e)
            return self._fallback_thesis(candidate, evidence, bull_thesis)

    def _fallback_thesis(
        self,
        candidate: CandidateSetup,
        evidence: List[EvidenceItem],
        bull_thesis: Optional[BullThesis] = None,
    ) -> BearThesis:
        tech = candidate.technicals
        stock = candidate.stock
        res = tech.resistance if tech.resistance > 0 else round(tech.close * 1.04, 1)

        return BearThesis(
            symbol=stock.symbol,
            company=stock.name,
            core_thesis=f"Immediate overhead supply near ₹{res} and lack of multi-day volume persistence creates false breakout risk.",
            technical_flaws=[
                f"Overhead resistance zone at ₹{res} sits directly above current price ₹{tech.close:.2f}.",
                f"RSI-14 at {tech.rsi14:.0f} leaving limited headroom before hitting overbought friction.",
            ],
            catalyst_flaws=[
                "Policy announcements often experience short-term profit booking as initial hype subsides.",
            ],
            fundamental_flaws=[
                "Execution timelines on government scheme tenders are typically 6-18 months, limiting near-term earnings delta.",
            ],
            market_risks=[
                "Broader market volatility and sector rotation could trigger sudden institutional supply.",
            ],
            trade_structure_flaws=[
                f"Risk-to-reward is unfavorable if buying at market without waiting for confirmation above ₹{res}.",
            ],
            what_would_invalidate_bear=f"A decisive daily close above ₹{res} backed by >1.5x average daily volume.",
            required_confirmation_to_buy=f"Wait for price to clear and close above ₹{res} with sustained volume, or buy on a low-volume retest of support ₹{tech.support:.1f}.",
            evidence_ids=[ev.evidence_id for ev in evidence if "EV-TECH" in ev.evidence_id][:2],
        )
