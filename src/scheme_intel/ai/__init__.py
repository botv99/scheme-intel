"""
AI Subsystem.
Houses multi-provider LLM failover architecture, debate agents, and orchestration.
"""
from ..stage2.providers import (
    LLMProvider,
    ProviderResponse,
    LLMProviderManager,
    GeminiProvider,
    GroqProvider,
    OpenRouterProvider,
    OpenAIProvider,
    MockProvider,
)
from ..stage2.pipeline import get_llm_provider
from ..stage2.agents import (
    BullAgent,
    BearAgent,
    ArbitratorAgent,
)
from ..stage2.agents.base import BaseAgent
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
    "BaseAgent",
    "BullAgent",
    "BearAgent",
    "ArbitratorAgent",
    "DebateOrchestrator",
]
