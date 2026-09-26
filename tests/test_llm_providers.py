"""
Comprehensive test suite for Stage 2 Multi-Provider LLM Architecture.
Verifies:
- Gemini only, Groq only, OpenRouter only, OpenAI only
- Multiple providers & priority routing
- Missing API keys handling
- Gemini 429 quota -> Groq failover
- Gemini timeout -> Groq failover
- Gemini 404 model -> Groq failover
- Groq 429 -> OpenRouter failover
- All providers unavailable -> deterministic synthesis fallback
- Provider cooldown & Retry-After header handling
- Provider selection & model selection via env vars
- BullAgent / BearAgent / ArbitratorAgent using provider manager
- API keys never appearing in logs / errors
- Per-call dynamic failover routing
"""
import os
import time
import json
import logging
import pytest
from unittest.mock import patch, MagicMock
import requests

from src.scheme_intel.stage2.models import (
    CandidateSetup, Stock, TechnicalSnapshot, CatalystImpact,
    BullThesis, BearThesis, DebateResult, EvidenceItem,
)
from src.scheme_intel.stage2.providers.base import (
    LLMProvider, ProviderResponse, RateLimitError, ModelNotFoundError,
    ProviderTimeoutError, ServerError, AllProvidersExhaustedError,
    LLMProviderError, sanitize_secret,
)
from src.scheme_intel.stage2.providers.gemini import GeminiProvider
from src.scheme_intel.stage2.providers.groq import GroqProvider
from src.scheme_intel.stage2.providers.openrouter import OpenRouterProvider
from src.scheme_intel.stage2.providers.openai import OpenAIProvider
from src.scheme_intel.stage2.providers.mock import MockProvider
from src.scheme_intel.stage2.providers.manager import LLMProviderManager
from src.scheme_intel.stage2.agents.bull import BullAgent
from src.scheme_intel.stage2.agents.bear import BearAgent
from src.scheme_intel.stage2.agents.arbitrator import ArbitratorAgent
from src.scheme_intel.stage2.debate import DebateOrchestrator


@pytest.fixture
def sample_candidate():
    stock = Stock(name="Praj Industries", symbol="PRAJIND.NS", sectors=["Bioenergy"])
    technicals = TechnicalSnapshot(
        close=522.5,
        sma20=510.0,
        sma50=495.0,
        rsi14=62.0,
        volume_ratio=1.8,
        support=505.0,
        resistance=540.0,
        high_20d=535.0,
    )
    catalysts = [
        CatalystImpact(
            company="Praj Industries",
            catalyst_name="GOBARdhan Scheme Allocation",
            beneficiary_type="Direct",
            strength=85,
            certainty="High",
        )
    ]
    return CandidateSetup(
        stock=stock,
        archetype="Breakout",
        score=85,
        rationale="Clear resistance breakout on strong volume",
        technicals=technicals,
        catalysts=catalysts,
    )


# ---------------------------------------------------------------------------
# 1. Gemini Only
# ---------------------------------------------------------------------------
def test_gemini_only():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": '{"symbol": "PRAJIND.NS", "analysis": "bullish"}'}]}}],
        "usageMetadata": {"totalTokenCount": 150},
    }
    with patch("requests.post", return_value=mock_resp):
        provider = GeminiProvider(api_key="test-gemini-key", model="gemini-3.8-flash")
        res = provider.generate("Analyze PRAJIND.NS")
        assert res.provider == "gemini"
        assert res.model == "gemini-3.8-flash"
        assert res.tokens_used == 150
        assert res.raw_json == {"symbol": "PRAJIND.NS", "analysis": "bullish"}


# ---------------------------------------------------------------------------
# 2. Groq Only
# ---------------------------------------------------------------------------
def test_groq_only():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"symbol": "PRAJIND.NS", "status": "groq_ok"}'}}],
        "usage": {"total_tokens": 120},
    }
    with patch("requests.post", return_value=mock_resp):
        provider = GroqProvider(api_key="test-groq-key", model="llama-3.3-70b-versatile")
        res = provider.generate("Analyze PRAJIND.NS")
        assert res.provider == "groq"
        assert res.model == "llama-3.3-70b-versatile"
        assert res.tokens_used == 120
        assert res.raw_json == {"symbol": "PRAJIND.NS", "status": "groq_ok"}


# ---------------------------------------------------------------------------
# 3. OpenRouter Only
# ---------------------------------------------------------------------------
def test_openrouter_only():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"status": "openrouter_ok"}'}}],
        "usage": {"total_tokens": 95},
    }
    with patch("requests.post", return_value=mock_resp):
        provider = OpenRouterProvider(api_key="test-openrouter-key", model="meta-llama/llama-3.3-70b-instruct:free")
        res = provider.generate("Analyze PRAJIND.NS")
        assert res.provider == "openrouter"
        assert res.tokens_used == 95
        assert res.raw_json == {"status": "openrouter_ok"}


# ---------------------------------------------------------------------------
# 4. OpenAI Only
# ---------------------------------------------------------------------------
def test_openai_only():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"status": "openai_ok"}'}}],
        "usage": {"total_tokens": 110},
    }
    with patch("requests.post", return_value=mock_resp):
        provider = OpenAIProvider(api_key="test-openai-key", model="gpt-4o-mini")
        res = provider.generate("Analyze PRAJIND.NS")
        assert res.provider == "openai"
        assert res.tokens_used == 110
        assert res.raw_json == {"status": "openai_ok"}


# ---------------------------------------------------------------------------
# 5. Multiple Providers & Priority Order
# ---------------------------------------------------------------------------
def test_multiple_providers_priority_order():
    groq_mock = MagicMock(spec=LLMProvider)
    groq_mock.name = "groq"
    groq_mock.generate.return_value = ProviderResponse(content="groq result", model="llama-3.3", tokens_used=50, provider="groq")

    gemini_mock = MagicMock(spec=LLMProvider)
    gemini_mock.name = "gemini"
    gemini_mock.generate.return_value = ProviderResponse(content="gemini result", model="gemini-3.8-flash", tokens_used=60, provider="gemini")

    manager = LLMProviderManager(
        providers={"groq": groq_mock, "gemini": gemini_mock},
        provider_order=["groq", "gemini"],
    )

    resp = manager.generate("prompt")
    assert resp.provider == "groq"
    assert groq_mock.generate.call_count == 1
    assert gemini_mock.generate.call_count == 0


# ---------------------------------------------------------------------------
# 6. Missing API Keys
# ---------------------------------------------------------------------------
def test_missing_api_keys_handling():
    with patch.dict(os.environ, {
        "GEMINI_API_KEY": "gemini-live-key",
        "GROQ_API_KEY": "",
        "OPENROUTER_API_KEY": "",
        "OPENAI_API_KEY": "",
    }, clear=True):
        manager = LLMProviderManager()
        assert manager.active_order == ["gemini"]
        assert "gemini" in manager.providers
        assert "groq" not in manager.providers


# ---------------------------------------------------------------------------
# 7. Gemini 429 Quota -> Groq Failover
# ---------------------------------------------------------------------------
def test_gemini_429_failover_to_groq():
    gemini = MagicMock(spec=LLMProvider)
    gemini.name = "gemini"
    gemini.generate.side_effect = RateLimitError("Gemini 429 quota reached", provider="gemini", status_code=429, retry_after=60.0)

    groq = MagicMock(spec=LLMProvider)
    groq.name = "groq"
    groq.generate.return_value = ProviderResponse(content="groq success", model="llama-3.3", provider="groq")

    manager = LLMProviderManager(
        providers={"gemini": gemini, "groq": groq},
        provider_order=["gemini", "groq"],
    )

    resp = manager.generate("prompt", caller="BullAgent")
    assert resp.provider == "groq"
    assert manager.is_in_cooldown("gemini")
    assert manager.last_route_summary == "Gemini → Groq failover"


# ---------------------------------------------------------------------------
# 8. Gemini Timeout -> Groq Failover
# ---------------------------------------------------------------------------
def test_gemini_timeout_failover_to_groq():
    gemini = MagicMock(spec=LLMProvider)
    gemini.name = "gemini"
    gemini.generate.side_effect = ProviderTimeoutError("Gemini timeout 30s", provider="gemini")

    groq = MagicMock(spec=LLMProvider)
    groq.name = "groq"
    groq.generate.return_value = ProviderResponse(content="groq success", model="llama-3.3", provider="groq")

    manager = LLMProviderManager(
        providers={"gemini": gemini, "groq": groq},
        provider_order=["gemini", "groq"],
    )

    resp = manager.generate("prompt", caller="BearAgent")
    assert resp.provider == "groq"
    assert manager.last_route_summary == "Gemini → Groq failover"


# ---------------------------------------------------------------------------
# 9. Gemini 404 Model -> Groq Failover
# ---------------------------------------------------------------------------
def test_gemini_404_model_failover_to_groq():
    gemini = MagicMock(spec=LLMProvider)
    gemini.name = "gemini"
    gemini.generate.side_effect = ModelNotFoundError("Model not found", provider="gemini", status_code=404)

    groq = MagicMock(spec=LLMProvider)
    groq.name = "groq"
    groq.generate.return_value = ProviderResponse(content="groq success", model="llama-3.3", provider="groq")

    manager = LLMProviderManager(
        providers={"gemini": gemini, "groq": groq},
        provider_order=["gemini", "groq"],
    )

    resp = manager.generate("prompt", caller="ArbitratorAgent")
    assert resp.provider == "groq"
    assert manager.last_route_summary == "Gemini → Groq failover"


# ---------------------------------------------------------------------------
# 10. Groq 429 -> OpenRouter Failover
# ---------------------------------------------------------------------------
def test_groq_429_failover_to_openrouter():
    groq = MagicMock(spec=LLMProvider)
    groq.name = "groq"
    groq.generate.side_effect = RateLimitError("Groq 429 limit", provider="groq", status_code=429, retry_after=45.0)

    openrouter = MagicMock(spec=LLMProvider)
    openrouter.name = "openrouter"
    openrouter.generate.return_value = ProviderResponse(content="openrouter success", model="free-model", provider="openrouter")

    manager = LLMProviderManager(
        providers={"groq": groq, "openrouter": openrouter},
        provider_order=["groq", "openrouter"],
    )

    resp = manager.generate("prompt", caller="BullAgent")
    assert resp.provider == "openrouter"
    assert manager.is_in_cooldown("groq")


# ---------------------------------------------------------------------------
# 11. All Providers Unavailable -> Deterministic Synthesis Fallback
# ---------------------------------------------------------------------------
def test_all_providers_unavailable_deterministic_fallback(sample_candidate):
    gemini = MagicMock(spec=LLMProvider)
    gemini.name = "gemini"
    gemini.generate.side_effect = RateLimitError("429", provider="gemini")

    groq = MagicMock(spec=LLMProvider)
    groq.name = "groq"
    groq.generate.side_effect = RateLimitError("429", provider="groq")

    manager = LLMProviderManager(
        providers={"gemini": gemini, "groq": groq},
        provider_order=["gemini", "groq"],
    )

    # Calling generate directly raises AllProvidersExhaustedError
    with pytest.raises(AllProvidersExhaustedError):
        manager.generate("prompt")

    # When BullAgent calls manager, it catches the error and executes deterministic synthesis fallback
    bull_agent = BullAgent(manager)
    evidence = [EvidenceItem(evidence_id="EV-01", claim="Test evidence", source="NSE", source_tier=1)]
    thesis = bull_agent.build_thesis(sample_candidate, evidence)

    assert isinstance(thesis, BullThesis)
    assert thesis.symbol == sample_candidate.stock.symbol
    assert thesis.expected_target > sample_candidate.technicals.close
    assert len(thesis.technical_arguments) > 0


# ---------------------------------------------------------------------------
# 12. Provider Cooldown Handling
# ---------------------------------------------------------------------------
def test_provider_cooldown():
    gemini = MagicMock(spec=LLMProvider)
    gemini.name = "gemini"
    gemini.generate.side_effect = RateLimitError("429", provider="gemini", retry_after=10.0)

    groq = MagicMock(spec=LLMProvider)
    groq.name = "groq"
    groq.generate.return_value = ProviderResponse(content="groq", provider="groq")

    manager = LLMProviderManager(
        providers={"gemini": gemini, "groq": groq},
        provider_order=["gemini", "groq"],
    )

    # First call: Gemini fails with 429, fails over to Groq
    manager.generate("call 1")
    assert gemini.generate.call_count == 1
    assert groq.generate.call_count == 1
    assert manager.is_in_cooldown("gemini")

    # Second call: Gemini is in cooldown, manager skips Gemini immediately and goes to Groq directly
    manager.generate("call 2")
    assert gemini.generate.call_count == 1  # Not called again!
    assert groq.generate.call_count == 2


# ---------------------------------------------------------------------------
# 13. Retry-After Header Handling
# ---------------------------------------------------------------------------
def test_retry_after_header_handling():
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "120"}
    mock_resp.json.return_value = {"error": {"message": "Quota exceeded"}}
    mock_resp.text = "Quota exceeded"

    with patch("requests.post", return_value=mock_resp):
        provider = GeminiProvider(api_key="key")
        with pytest.raises(RateLimitError) as exc_info:
            provider.generate("prompt")
        assert exc_info.value.retry_after == 120.0


# ---------------------------------------------------------------------------
# 14. Provider Selection & Order via Environment Variable
# ---------------------------------------------------------------------------
def test_provider_selection_via_env():
    groq = MagicMock(spec=LLMProvider)
    groq.name = "groq"
    openrouter = MagicMock(spec=LLMProvider)
    openrouter.name = "openrouter"
    openai = MagicMock(spec=LLMProvider)
    openai.name = "openai"

    providers = {"groq": groq, "openrouter": openrouter, "openai": openai}

    with patch.dict(os.environ, {"LLM_PROVIDER_ORDER": "openai,groq,openrouter"}):
        manager = LLMProviderManager(providers=providers)
        assert manager.active_order == ["openai", "groq", "openrouter"]


# ---------------------------------------------------------------------------
# 15. Model Selection via Environment Variables
# ---------------------------------------------------------------------------
def test_model_selection_via_env():
    with patch.dict(os.environ, {
        "GEMINI_MODEL": "gemini-2.5-flash",
        "GROQ_MODEL": "llama-3.1-8b-instant",
        "OPENROUTER_MODEL": "deepseek/deepseek-chat",
        "OPENAI_MODEL": "gpt-4o",
    }):
        gemini = GeminiProvider(api_key="k")
        groq = GroqProvider(api_key="k")
        openrouter = OpenRouterProvider(api_key="k")
        openai = OpenAIProvider(api_key="k")

        assert gemini.model == "gemini-2.5-flash"
        assert groq.model == "llama-3.1-8b-instant"
        assert openrouter.model == "deepseek/deepseek-chat"
        assert openai.model == "gpt-4o"


# ---------------------------------------------------------------------------
# 16. Bull / Bear / Arbitrator Multi-Agent Role Preservation
# ---------------------------------------------------------------------------
def test_bull_bear_arbitrator_with_provider_manager(sample_candidate):
    mock_provider = MockProvider()
    manager = LLMProviderManager(
        providers={"mock": mock_provider},
        provider_order=["mock"],
    )

    orchestrator = DebateOrchestrator(manager)
    bull, bear, debate = orchestrator.run_debate(sample_candidate)

    assert isinstance(bull, BullThesis)
    assert isinstance(bear, BearThesis)
    assert isinstance(debate, DebateResult)
    assert debate.provider == "Mock"
    assert debate.bull_strength > 0
    assert debate.bear_strength > 0
    assert len(debate.rounds) == 3


# ---------------------------------------------------------------------------
# 17. API Keys Never Appear in Logs or Sanitized Strings
# ---------------------------------------------------------------------------
def test_api_keys_never_appear_in_logs():
    secret_gemini = "AIzaSySecretGeminiKey12345"
    secret_groq = "gsk_SecretGroqKey67890abcdef"
    secret_openrouter = "sk-or-v1-SecretOpenRouterKey99999"

    with patch.dict(os.environ, {
        "GEMINI_API_KEY": secret_gemini,
        "GROQ_API_KEY": secret_groq,
        "OPENROUTER_API_KEY": secret_openrouter,
    }):
        leak_str = f"Error calling url https://generativelanguage.googleapis.com/v1beta/models?key={secret_gemini} with Bearer {secret_groq} and {secret_openrouter}"
        sanitized = sanitize_secret(leak_str)

        assert secret_gemini not in sanitized
        assert secret_groq not in sanitized
        assert secret_openrouter not in sanitized
        assert "***" in sanitized


# ---------------------------------------------------------------------------
# 18. Per-Call Failover Decision
# ---------------------------------------------------------------------------
def test_per_call_dynamic_failover():
    call_count = {"gemini": 0, "groq": 0}

    def gemini_gen(prompt, **kwargs):
        call_count["gemini"] += 1
        if call_count["gemini"] == 2:
            raise RateLimitError("Gemini 429 quota reached", provider="gemini", retry_after=1.0)
        return ProviderResponse(content=f"gemini call {call_count['gemini']}", provider="gemini")

    def groq_gen(prompt, **kwargs):
        call_count["groq"] += 1
        return ProviderResponse(content=f"groq call {call_count['groq']}", provider="groq")

    gemini = MagicMock(spec=LLMProvider)
    gemini.name = "gemini"
    gemini.generate.side_effect = gemini_gen

    groq = MagicMock(spec=LLMProvider)
    groq.name = "groq"
    groq.generate.side_effect = groq_gen

    manager = LLMProviderManager(
        providers={"gemini": gemini, "groq": groq},
        provider_order=["gemini", "groq"],
    )

    # Call 1: Gemini succeeds
    r1 = manager.generate("call 1", caller="BullAgent")
    assert r1.provider == "gemini"
    assert call_count["gemini"] == 1
    assert call_count["groq"] == 0

    # Call 2: Gemini hits 429 -> fails over to Groq
    r2 = manager.generate("call 2", caller="BearAgent")
    assert r2.provider == "groq"
    assert call_count["gemini"] == 2
    assert call_count["groq"] == 1
    assert manager.is_in_cooldown("gemini")

    # Call 3: Gemini is in cooldown -> directly routes to Groq without calling Gemini
    r3 = manager.generate("call 3", caller="ArbitratorAgent")
    assert r3.provider == "groq"
    assert call_count["gemini"] == 2
    assert call_count["groq"] == 2

    # After cooldown expires:
    time.sleep(1.1)
    assert not manager.is_in_cooldown("gemini")

    # Call 4: Gemini is attempted again and succeeds
    r4 = manager.generate("call 4", caller="BullAgent")
    assert r4.provider == "gemini"
    assert call_count["gemini"] == 3
    assert call_count["groq"] == 2
