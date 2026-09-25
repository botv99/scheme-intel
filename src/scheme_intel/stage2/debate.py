"""
Adversarial Debate Orchestrator for Stage 2.
Coordinates Bull, Bear, and Evidence Arbitrator agents through a structured debate sequence.
"""
from __future__ import annotations

from typing import Tuple, List, Optional
from .models import CandidateSetup, BullThesis, BearThesis, DebateResult, EvidenceItem
from .providers.base import LLMProvider
from .agents.base import BaseAgent
from .agents.bull import BullAgent
from .agents.bear import BearAgent
from .agents.arbitrator import ArbitratorAgent
from ..logger import get_logger

logger = get_logger(__name__)


class DebateOrchestrator:
    """Orchestrates multi-agent adversarial debate on candidate setups."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.bull_agent = BullAgent(provider)
        self.bear_agent = BearAgent(provider)
        self.arbitrator_agent = ArbitratorAgent(provider)
        self.base_agent = BaseAgent(provider)

    def run_debate(
        self,
        candidate: CandidateSetup,
        external_evidence: Optional[List[EvidenceItem]] = None,
    ) -> Tuple[BullThesis, BearThesis, DebateResult]:
        """
        Execute full debate workflow:
        1. Compile evidence dossier
        2. Bull Hunter formulates BullThesis
        3. Bear Trade Killer stress-tests with BearThesis
        4. Evidence Arbitrator renders DebateResult
        """
        logger.info("Starting adversarial debate for %s (%s)", candidate.stock.name, candidate.archetype)

        # 1. Evidence Dossier
        evidence = self.base_agent.format_evidence_dossier(candidate)
        if external_evidence:
            evidence.extend(external_evidence)

        # 2. Bull Thesis
        bull_thesis = self.bull_agent.build_thesis(candidate, evidence)
        logger.info("Bull thesis generated for %s (Target: Rs. %s)", candidate.stock.symbol, bull_thesis.expected_target)

        import time
        time.sleep(1.5)

        # 3. Bear Thesis
        bear_thesis = self.bear_agent.build_thesis(candidate, evidence, bull_thesis)
        logger.info("Bear thesis generated for %s (Invalidation: %s)", candidate.stock.symbol, bear_thesis.what_would_invalidate_bear[:40])

        time.sleep(1.5)

        # 4. Arbitration
        debate_result = self.arbitrator_agent.arbitrate(candidate, evidence, bull_thesis, bear_thesis)
        logger.info(
            "Debate adjudicated for %s: Bull %.1f vs Bear %.1f",
            candidate.stock.symbol,
            debate_result.bull_strength,
            debate_result.bear_strength,
        )

        return bull_thesis, bear_thesis, debate_result
