"""Mock LLM Provider for offline deterministic testing and CI."""
from __future__ import annotations

import json
from typing import Optional, Type, Any
from pydantic import BaseModel

from .base import LLMProvider, ProviderResponse


class MockProvider(LLMProvider):
    """
    Deterministic provider that generates schema-compliant mock responses
    without requiring external API connectivity.
    """

    name: str = "mock"

    def __init__(self, fixed_responses: Optional[dict[str, Any]] = None):
        self.fixed_responses = fixed_responses or {}
        self.call_history: list[dict] = []

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.2,
        caller: str = "",
    ) -> ProviderResponse:
        self.call_history.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "schema": schema.__name__ if schema else None,
        })

        # Return preset if matched
        for key, res in self.fixed_responses.items():
            if key in prompt:
                if isinstance(res, BaseModel):
                    return ProviderResponse(content=res.model_dump_json(), raw_json=res.model_dump(), model="mock")
                if isinstance(res, dict):
                    return ProviderResponse(content=json.dumps(res), raw_json=res, model="mock")
                return ProviderResponse(content=str(res), model="mock")

        # Dynamic mock generation if schema is provided
        if schema:
            data = self._generate_default_for_schema(schema, prompt)
            return ProviderResponse(content=json.dumps(data), raw_json=data, model="mock")

        return ProviderResponse(content="Mock analysis response.", model="mock")

    def _generate_default_for_schema(self, schema: Type[BaseModel], prompt: str) -> dict:
        name = schema.__name__
        if "BullThesis" in name:
            return {
                "symbol": "PRAJIND.NS",
                "company": "Praj Industries",
                "core_thesis": "Strong momentum breakout confirmed by CBG government scheme and 1.8x volume expansion.",
                "technical_arguments": ["Price above 20 and 50 DMA", "RSI at 62 indicates strong momentum without exhaustion", "Volume ratio at 1.8x average confirms institutional demand"],
                "catalyst_arguments": ["National Bioenergy fund release announced today", "Direct beneficiary with 65% market share in ethanol plants"],
                "fundamental_arguments": ["Robust order book of ₹3,400 Cr", "Stable operating margins at 11.5%"],
                "market_arguments": ["NIFTY Energy index outperforming broader market"],
                "proposed_entry": "₹515 - ₹520",
                "expected_target": 575.0,
                "invalidation_level": 490.0,
                "evidence_ids": ["EV-01", "EV-02"],
                "key_risks_acknowledged": ["Raw material steel price volatility", "Execution delays on distillery tenders"],
            }
        elif "BearThesis" in name:
            return {
                "symbol": "PRAJIND.NS",
                "company": "Praj Industries",
                "core_thesis": "Approaching major overhead resistance with potential false breakout risk.",
                "technical_flaws": ["Major resistance zone at ₹530 within 2.5%", "Daily MACD histogram displaying minor divergence"],
                "catalyst_flaws": ["CBG subsidy was already highlighted in previous cabinet briefing 2 weeks ago"],
                "fundamental_flaws": ["Q1 EBITDA margins contracted 60 bps YoY"],
                "market_risks": ["Broader midcap index showing distribution signs"],
                "trade_structure_flaws": ["Risk/reward ratio requires a very tight stop loss below ₹490"],
                "what_would_invalidate_bear": "Decisive daily close above ₹530 with volume exceeding 2.0x average.",
                "required_confirmation_to_buy": "Wait for breakout above ₹530 and successful retest of ₹520 as support.",
                "evidence_ids": ["EV-03"],
            }
        elif "DebateResult" in name:
            return {
                "symbol": "PRAJIND.NS",
                "rounds": [
                    {"round_num": 1, "speaker": "BULL", "content": "Breakout confirmed by GOBARdhan policy.", "evidence_cited": ["EV-01"]},
                    {"round_num": 2, "speaker": "BEAR", "content": "Resistance at ₹530 is too close for safe swing.", "evidence_cited": ["EV-03"]},
                    {"round_num": 3, "speaker": "ARBITRATOR", "content": "Tier 1 disclosure verified, but resistance confirmed on daily chart.", "evidence_cited": ["EV-01", "EV-03"]},
                ],
                "bull_strength": 75.0,
                "bear_strength": 65.0,
                "agreed_points": ["Company is fundamentally sound", "Volume today was notably higher than average"],
                "disputed_points": ["Whether policy is fully priced in", "Whether ₹530 resistance will hold"],
                "resolved_claims": ["Order win is verified by Tier 1 NSE filing"],
                "key_catalyst": "GOBARdhan funding release",
                "key_risk": "Overhead resistance at ₹530",
                "confirmation_needed": "Daily close above ₹530 with >1.5x volume",
            }
        elif "RiskAssessment" in name:
            return {
                "passed": True,
                "veto_reason": None,
                "entry_min": 515.0,
                "entry_max": 520.0,
                "ideal_entry": 518.0,
                "trigger_condition": "Break ₹530 + volume >1.5x",
                "stop_loss": 492.0,
                "target_1": 560.0,
                "target_2": 585.0,
                "target_3": 610.0,
                "expected_holding_period": "5–15 sessions",
                "risk_reward_ratio": 1.62,
                "position_size_pct": 5.0,
                "risk_per_share": 26.0,
                "volume_to_watch": ">1.5x 20D average",
                "max_portfolio_risk_pct": 1.0,
            }
        # Generic fallback
        return {}
