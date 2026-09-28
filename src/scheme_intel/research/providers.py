"""
Provider Registry and Dynamic Multi-Provider Management for Research Engine.
Supports dynamic registration, environment-driven configuration, and health audits.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

from ..stage2.providers.base import LLMProvider, sanitize_secret
from ..stage2.providers.gemini import GeminiProvider
from ..stage2.providers.groq import GroqProvider
from ..stage2.providers.openai import OpenAIProvider
from ..stage2.providers.openrouter import OpenRouterProvider
from ..stage2.providers.mock import MockProvider
from ..logger import get_logger

logger = get_logger(__name__)

# Conceptual alias for provider abstraction
AIProvider = LLMProvider


class ProviderHealthStatus:
    VERIFIED_LIVE = "VERIFIED_LIVE"
    CONFIGURED_BUT_NOT_VERIFIED = "CONFIGURED_BUT_NOT_VERIFIED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    FAILED = "FAILED"


@dataclass
class ProviderConfig:
    """Metadata and registration spec for an AI inference provider."""
    name: str
    env_key: str
    model_env_key: str
    default_model: str
    provider_class: Type[LLMProvider]
    enabled: bool = True
    description: str = ""


class ProviderRegistry:
    """
    Central registry for AI providers.
    Supports dynamic registration of open-source and proprietary inference APIs.
    """

    def __init__(self):
        self._configs: Dict[str, ProviderConfig] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the baseline providers."""
        self.register(
            ProviderConfig(
                name="groq",
                env_key="GROQ_API_KEY",
                model_env_key="GROQ_MODEL",
                default_model="llama-3.3-70b-versatile",
                provider_class=GroqProvider,
                description="Ultra-fast Llama inference provider via Groq Cloud API",
            )
        )
        self.register(
            ProviderConfig(
                name="gemini",
                env_key="GEMINI_API_KEY",
                model_env_key="GEMINI_MODEL",
                default_model="gemini-2.5-flash",
                provider_class=GeminiProvider,
                description="Google DeepMind Gemini models",
            )
        )
        self.register(
            ProviderConfig(
                name="openai",
                env_key="OPENAI_API_KEY",
                model_env_key="OPENAI_MODEL",
                default_model="gpt-4o-mini",
                provider_class=OpenAIProvider,
                description="OpenAI GPT models",
            )
        )
        self.register(
            ProviderConfig(
                name="openrouter",
                env_key="OPENROUTER_API_KEY",
                model_env_key="OPENROUTER_MODEL",
                default_model="meta-llama/llama-3.3-70b-instruct:free",
                provider_class=OpenRouterProvider,
                description="OpenRouter gateway for diverse open-source and commercial models",
            )
        )

    def register(self, config: ProviderConfig) -> None:
        """Register or override a provider configuration."""
        self._configs[config.name.lower()] = config
        logger.debug("Registered AI Provider: %s (env_key=%s)", config.name, config.env_key)

    def get_config(self, name: str) -> Optional[ProviderConfig]:
        return self._configs.get(name.lower())

    def list_all_configs(self) -> List[ProviderConfig]:
        return list(self._configs.values())

    def is_configured(self, name: str) -> bool:
        """Check if environment variable exists for provider."""
        cfg = self.get_config(name)
        if not cfg or not cfg.enabled:
            return False
        # Special check for Gemini allowing GOOGLE_API_KEY
        if cfg.name == "gemini":
            return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        return bool(os.getenv(cfg.env_key))

    def get_configured_provider_names(self) -> List[str]:
        """Return list of provider names whose API keys are configured in env."""
        return [name for name in self._configs if self.is_configured(name)]

    def get_health_status(self, name: str, verified_live: bool = False) -> str:
        """
        Audit health status of a provider.
        Does NOT claim live validity merely because the environment variable exists.
        """
        if not self.is_configured(name):
            return ProviderHealthStatus.NOT_CONFIGURED
        if verified_live:
            return ProviderHealthStatus.VERIFIED_LIVE
        return ProviderHealthStatus.CONFIGURED_BUT_NOT_VERIFIED

    def create_provider(self, name: str) -> Optional[LLMProvider]:
        """Instantiate an active provider with environment-configured model and credentials."""
        cfg = self.get_config(name)
        if not cfg or not self.is_configured(name):
            return None

        model_name = os.getenv(cfg.model_env_key, cfg.default_model)
        try:
            # Most providers accept api_key and model
            if cfg.name == "gemini":
                key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                return cfg.provider_class(api_key=key, model=model_name)
            else:
                key = os.getenv(cfg.env_key)
                return cfg.provider_class(api_key=key, model=model_name)
        except Exception as e:
            logger.warning("Failed instantiating provider %s: %s", name, sanitize_secret(str(e)))
            return None

    def get_active_providers(self) -> Dict[str, LLMProvider]:
        """Return instantiated map of all configured and enabled providers."""
        active: Dict[str, LLMProvider] = {}
        for name in self.get_configured_provider_names():
            inst = self.create_provider(name)
            if inst:
                active[name] = inst
        return active


# Global registry singleton
default_registry = ProviderRegistry()
