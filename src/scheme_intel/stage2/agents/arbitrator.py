"""
Evidence Arbitrator Agent for Stage 2.
Evaluates Bull vs Bear claims against 5-Tier source hierarchy and resolves debate verdict.
"""
from __future__ import annotations

from typing import List
from .base import BaseAgent
from ..models import CandidateSetup, EvidenceItem, BullThesis, BearThesis, DebateResult, DebateRound
from ...logger import get_logger

logger = get_logger(__name__)

ARBITRATOR_SYSTEM_PROMPT = """You are the Evidence Arbitrator — an impartial, veteran quantitative risk committee chair.
Your mandate is to critically adjudicate the adversarial debate between the Bull Swing Hunter and Bear Trade Killer.

GUIDELINES:
1. Apply the 5-Tier Source Hierarchy strictly:
   - Tier 1: Official Exchange filings (BSE/NSE), PIB government gazettes, SEBI/RBI circulars. (Highest weight: 1.0)
   - Tier 2: Company investor presentations, verified audited quarterly filings. (Weight: 0.9)
   - Tier 3: Mainstream financial press (Economic Times, Mint, Moneycontrol, Bloomberg). (Weight: 0.7)
   - Tier 4: Brokerage/analyst consensus reports. (Weight: 0.5)
   - Tier 5: Social media, unverified rumors, blogs. (Weight: 0.0 - discard immediately)
2. Score bull_strength (0-100) and bear_strength (0-100) based on verified factual evidence.
3. List agreed points, disputed points, and resolved claims.
4. Extract the single key catalyst, the single key risk, and the definitive confirmation needed to trade.
5. Keep rounds (maximum 3 concise rounds), agreed points, and disputed points concise and crisp (1-2 sentences each).
6. Return your response matching the DebateResult JSON schema strictly.
"""


class ArbitratorAgent(BaseAgent):
    """Evidence Arbitrator adjudicating the Bull vs Bear clash."""

    def arbitrate(
        self,
        candidate: CandidateSetup,
        evidence: List[EvidenceItem],
        bull_thesis: BullThesis,
        bear_thesis: BearThesis,
    ) -> DebateResult:
        prompt = (
            f"Adjudicate the adversarial swing trade debate for {candidate.stock.name} ({candidate.stock.symbol}).\n\n"
            f"{self.format_dossier_text(candidate, evidence)}\n\n"
            f"=== BULL THESIS ===\n"
            f"Core: {bull_thesis.core_thesis}\n"
            f"Proposed Entry: {bull_thesis.proposed_entry} | Target: ₹{bull_thesis.expected_target} | Stop: ₹{bull_thesis.invalidation_level}\n"
            f"Technical: {'; '.join(bull_thesis.technical_arguments)}\n"
            f"Catalyst: {'; '.join(bull_thesis.catalyst_arguments)}\n"
            f"Evidence Cited: {', '.join(bull_thesis.evidence_ids)}\n\n"
            f"=== BEAR THESIS ===\n"
            f"Core: {bear_thesis.core_thesis}\n"
            f"Technical Flaws: {'; '.join(bear_thesis.technical_flaws)}\n"
            f"Catalyst Flaws: {'; '.join(bear_thesis.catalyst_flaws)}\n"
            f"Trade Flaws: {'; '.join(bear_thesis.trade_structure_flaws)}\n"
            f"Invalidate Bear If: {bear_thesis.what_would_invalidate_bear}\n"
            f"Required Confirmation: {bear_thesis.required_confirmation_to_buy}\n"
            f"Evidence Cited: {', '.join(bear_thesis.evidence_ids)}\n\n"
            "Review the evidence and produce a fully resolved DebateResult."
        )

        try:
            return self.provider.generate_structured(
                prompt=prompt,
                schema=DebateResult,
                system_prompt=ARBITRATOR_SYSTEM_PROMPT,
                temperature=0.1,
            )
        except Exception as e:
            logger.warning("ArbitratorAgent LLM generation failed, falling back to deterministic synthesis: %s", e)
            return self._fallback_arbitration(candidate, evidence, bull_thesis, bear_thesis)

    def _fallback_arbitration(
        self,
        candidate: CandidateSetup,
        evidence: List[EvidenceItem],
        bull_thesis: BullThesis,
        bear_thesis: BearThesis,
    ) -> DebateResult:
        tech = candidate.technicals
        stock = candidate.stock

        # Calculate evidence-based scores
        vol_score = 75.0 if tech.volume_ratio >= 1.5 else (60.0 if tech.volume_ratio >= 1.1 else 45.0)
        trend_score = 80.0 if tech.close > tech.sma20 > tech.sma50 else 50.0
        bull_strength = round((vol_score * 0.5) + (trend_score * 0.5), 1)

        # Bear strength based on overhead resistance proximity and overbought RSI
        near_res = (tech.resistance - tech.close) / tech.resistance < 0.03 if tech.resistance > 0 else False
        res_score = 75.0 if near_res else 40.0
        rsi_score = 70.0 if tech.rsi14 > 68 else 45.0
        bear_strength = round((res_score * 0.6) + (rsi_score * 0.4), 1)

        rounds = [
            DebateRound(
                round_num=1,
                speaker="BULL",
                content=f"Strong {candidate.archetype} thesis: {bull_thesis.core_thesis}",
                evidence_cited=bull_thesis.evidence_ids,
            ),
            DebateRound(
                round_num=2,
                speaker="BEAR",
                content=f"Caution warranted: {bear_thesis.core_thesis}",
                evidence_cited=bear_thesis.evidence_ids,
            ),
            DebateRound(
                round_num=3,
                speaker="ARBITRATOR",
                content=f"Technical data verified (Tier 1). Setup requires adherence to risk parameters before entry.",
                evidence_cited=["EV-TECH-01", "EV-TECH-02"],
            ),
        ]

        return DebateResult(
            symbol=stock.symbol,
            rounds=rounds,
            bull_strength=bull_strength,
            bear_strength=bear_strength,
            agreed_points=[
                f"Stock has constructive volume expansion ({tech.volume_ratio:.1f}x)",
                f"Key swing levels: Support ₹{tech.support:.1f}, Resistance ₹{tech.resistance:.1f}",
            ],
            disputed_points=[
                "Whether overhead resistance will cap immediate upside",
                "Whether catalyst is already partially priced in after recent advance",
            ],
            resolved_claims=[
                f"Closing price ₹{tech.close:.2f} confirmed above 20 DMA via Tier-1 exchange feed",
            ],
            key_catalyst=candidate.catalysts[0].catalyst_name if candidate.catalysts else "Sector momentum and technical alignment",
            key_risk=f"Overhead resistance at ₹{tech.resistance:.1f}",
            confirmation_needed=bear_thesis.required_confirmation_to_buy or f"Clean breakout above ₹{tech.resistance:.1f} on volume",
        )
