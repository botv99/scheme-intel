"""
Base Agent class for Stage 2 Adversarial Debate agents.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
from ..models import CandidateSetup, EvidenceItem, TechnicalSnapshot, CatalystImpact
from ..providers.base import LLMProvider


class BaseAgent:
    """Base class providing common utilities for debate agents."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def format_evidence_dossier(self, candidate: CandidateSetup) -> List[EvidenceItem]:
        """Convert candidate technicals and catalysts into indexed evidence items."""
        items: List[EvidenceItem] = []
        tech = candidate.technicals

        # Technical evidence
        items.append(EvidenceItem(
            evidence_id="EV-TECH-01",
            claim=f"Closing price is ₹{tech.close:.2f} (Day change: {tech.day_change_pct:+.2f}%)",
            source="Market Data (NSE/BSE)",
            source_tier=1,
            relevance="Direct",
            verified=True,
            confidence_weight=1.0,
        ))
        items.append(EvidenceItem(
            evidence_id="EV-TECH-02",
            claim=f"Volume ratio is {tech.volume_ratio:.2f}x 20-day average volume",
            source="Market Data (NSE/BSE)",
            source_tier=1,
            relevance="Direct",
            verified=True,
            confidence_weight=1.0,
        ))
        items.append(EvidenceItem(
            evidence_id="EV-TECH-03",
            claim=f"Trend indicators: 20 DMA ₹{tech.sma20:.1f}, 50 DMA ₹{tech.sma50:.1f}, RSI-14 {tech.rsi14:.1f}",
            source="Technical Engine",
            source_tier=2,
            relevance="Direct",
            verified=True,
            confidence_weight=0.95,
        ))
        items.append(EvidenceItem(
            evidence_id="EV-TECH-04",
            claim=f"Key Levels: Support ₹{tech.support:.1f}, Resistance ₹{tech.resistance:.1f}, 20d High ₹{tech.high_20d:.1f}",
            source="Technical Engine",
            source_tier=2,
            relevance="Direct",
            verified=True,
            confidence_weight=0.90,
        ))

        # Catalyst evidence
        for idx, cat in enumerate(candidate.catalysts[:4], start=1):
            tier = 1 if cat.certainty == "High" else (2 if cat.certainty == "Medium" else 3)
            items.append(EvidenceItem(
                evidence_id=f"EV-CAT-{idx:02d}",
                claim=f"Catalyst: {cat.catalyst_name} (Beneficiary: {cat.beneficiary_type}, Strength: {cat.strength}/100, Fresh: {cat.is_fresh})",
                source=f"News Engine ({cat.certainty} certainty)",
                source_tier=tier,
                relevance=cat.beneficiary_type,
                verified=True,
                confidence_weight=0.9 if cat.certainty == "High" else 0.7,
            ))

        return items

    def format_dossier_text(self, candidate: CandidateSetup, evidence: List[EvidenceItem]) -> str:
        """Format candidate details and evidence list into prompt text."""
        tech = candidate.technicals
        stock = candidate.stock
        lines = [
            f"=== STOCK INFORMATION ===",
            f"Symbol: {stock.symbol}",
            f"Company: {stock.name}",
            f"Sectors: {', '.join(stock.sectors)}",
            f"Archetype Identified: {candidate.archetype} (Deterministic Score: {candidate.score}/100)",
            f"Rationale: {candidate.rationale}",
            "",
            f"=== TECHNICAL SNAPSHOT ===",
            f"Close: ₹{tech.close:.2f} | 20 DMA: ₹{tech.sma20:.1f} | 50 DMA: ₹{tech.sma50:.1f}",
            f"RSI-14: {tech.rsi14:.1f} | Volume Ratio: {tech.volume_ratio:.2f}x | Volatility Regime: {tech.volatility_regime}",
            f"Support: ₹{tech.support:.1f} | Resistance: ₹{tech.resistance:.1f} | 20d High: ₹{tech.high_20d:.1f}",
            f"Performance: 5d: {tech.performance_5d:+.1f}%, 20d: {tech.performance_20d:+.1f}%",
            "",
            f"=== EVIDENCE ITEMS ===",
        ]
        for ev in evidence:
            lines.append(f"[{ev.evidence_id}] (Tier {ev.source_tier}) {ev.claim}")
        return "\n".join(lines)
