"""
AI Subsystem.
Houses multi-provider LLM failover architecture, debate agents, and orchestration.
"""
from ..stage2.providers import (
    LLMProvider,
    ProviderResponse,
    LLMProviderManager,
    get_llm_provider,
    GeminiProvider,
    GroqProvider,
    OpenRouterProvider,
    OpenAIProvider,
    MockProvider,
)
from ..stage2.agents import (
    DebateAgent,
    BullAgent,
    BearAgent,
    ArbitratorAgent,
)
from .debate import DebateOrchestrator

__all__ = [
    "LLMProvider",
    "ProviderResponse",
    "LLMProviderManager",
    "get_llm_provider",
    "GeminiProvider",
    "GroqProvider",
    "OpenRouterProvider",
    "OpenAIProvider",
    "MockProvider",
    "DebateAgent",
    "BullAgent",
    "BearAgent",
    "ArbitratorAgent",
    "DebateOrchestrator",
]
