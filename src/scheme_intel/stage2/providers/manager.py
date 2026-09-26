"""
LLM Provider Manager and Automatic Failover Router.
Provides a provider-agnostic, failover-based interface for Stage 2 agents.
"""
from __future__ import annotations

import os
import time
from typing import Optional, Dict, List, Type, Any
from pydantic import BaseModel

from .base import (
    LLMProvider,
    ProviderResponse,
    RateLimitError,
    ModelNotFoundError,
    ProviderTimeoutError,
    ServerError,
    AllProvidersExhaustedError,
    LLMProviderError,
    sanitize_secret,
)
from .gemini import GeminiProvider
from .groq import GroqProvider
from .openrouter import OpenRouterProvider
from .openai import OpenAIProvider
from .mock import MockProvider
from ...logger import get_logger

logger = get_logger(__name__)

DEFAULT_PROVIDER_ORDER = ["groq", "openrouter", "gemini", "openai"]


class LLMProviderManager(LLMProvider):
    """
    Manager and routing proxy across multiple LLM providers.
    Directs calls per-request across available providers and handles 429 quota,
    model 404, timeouts, and 5xx errors with automated cooldown and failover.
    """

    name: str = "manager"

    def __init__(
        self,
        providers: Optional[Dict[str, LLMProvider]] = None,
        provider_order: Optional[List[str]] = None,
        preferred_provider: Optional[str] = None,
        allow_mock_fallback: bool = False,
        default_cooldown_seconds: float = 60.0,
    ):
        self.default_cooldown_seconds = default_cooldown_seconds
        self.allow_mock_fallback = allow_mock_fallback
        self.cooldowns: Dict[str, float] = {}  # provider_name -> unix timestamp when cooldown expires
        self.call_history: List[Dict[str, Any]] = []
        self.last_provider_used: Optional[str] = None
        self.last_failover_occurred: bool = False
        self.last_route_summary: str = ""

        # 1. Initialize or discover providers
        if providers is not None:
            self.providers = providers
        else:
            self.providers = self._discover_configured_providers()

        # 2. Determine active priority order
        env_order_raw = os.getenv("LLM_PROVIDER_ORDER", "")
        if provider_order:
            requested_order = [p.strip().lower() for p in provider_order if p.strip()]
        elif env_order_raw:
            requested_order = [p.strip().lower() for p in env_order_raw.split(",") if p.strip()]
        else:
            requested_order = list(DEFAULT_PROVIDER_ORDER)

        # If user explicitly preferred a provider, move it to front of priority
        if preferred_provider and preferred_provider.lower() not in ("auto", "router", "manager"):
            pref = preferred_provider.lower()
            if pref in requested_order:
                requested_order.remove(pref)
            requested_order.insert(0, pref)

        # Filter down to only configured providers that exist
        self.active_order: List[str] = [
            p for p in requested_order if p in self.providers
        ]

        # Log initialization
        logger.info("LLM Provider Manager initialized")
        if self.active_order:
            available_str = ", ".join(self.providers[p].name.capitalize() for p in self.active_order)
            logger.info("Available providers: %s", available_str)
        else:
            logger.warning("No LLM API keys detected. Available providers: None (deterministic fallback will be used)")

    def _discover_configured_providers(self) -> Dict[str, LLMProvider]:
        """Detect which API keys exist in the environment and instantiate providers."""
        discovered: Dict[str, LLMProvider] = {}

        # Groq
        if os.getenv("GROQ_API_KEY"):
            try:
                discovered["groq"] = GroqProvider()
            except Exception as e:
                logger.warning("Failed to initialize GroqProvider: %s", e)

        # OpenRouter
        if os.getenv("OPENROUTER_API_KEY"):
            try:
                discovered["openrouter"] = OpenRouterProvider()
            except Exception as e:
                logger.warning("Failed to initialize OpenRouterProvider: %s", e)

        # Gemini
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            try:
                discovered["gemini"] = GeminiProvider()
            except Exception as e:
                logger.warning("Failed to initialize GeminiProvider: %s", e)

        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            try:
                discovered["openai"] = OpenAIProvider()
            except Exception as e:
                logger.warning("Failed to initialize OpenAIProvider: %s", e)

        return discovered

    def is_in_cooldown(self, provider_name: str) -> bool:
        """Check if a provider is currently in cooldown."""
        exp = self.cooldowns.get(provider_name, 0.0)
        return time.time() < exp

    def get_remaining_cooldown(self, provider_name: str) -> float:
        """Return remaining cooldown seconds for provider, or 0.0 if active."""
        exp = self.cooldowns.get(provider_name, 0.0)
        return max(0.0, exp - time.time())

    def set_cooldown(self, provider_name: str, duration_seconds: float) -> None:
        """Mark provider as unavailable for duration_seconds."""
        self.cooldowns[provider_name] = time.time() + duration_seconds

    def reset_cooldowns(self) -> None:
        """Clear all provider cooldowns."""
        self.cooldowns.clear()

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.2,
        caller: str = "",
    ) -> ProviderResponse:
        """
        Execute LLM generation with per-request automatic routing and failover.
        Iterates through active providers in priority order, respecting cooldowns.
        """
        caller_name = caller or "LLM"
        attempted_providers: List[str] = []
        failover_events: List[str] = []
        now = time.time()

        for prov_name in self.active_order:
            provider = self.providers.get(prov_name)
            if not provider:
                continue

            display_name = provider.name.capitalize()

            # Check cooldown
            if self.is_in_cooldown(prov_name):
                remaining = self.get_remaining_cooldown(prov_name)
                logger.info("%s → %s → skipped (in cooldown for %.1fs)", caller_name, display_name, remaining)
                continue

            attempted_providers.append(display_name)

            try:
                response = provider.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    schema=schema,
                    temperature=temperature,
                    caller=caller_name,
                )

                # Success
                logger.info("%s → %s → success", caller_name, display_name)
                self.last_provider_used = display_name
                self.last_failover_occurred = len(attempted_providers) > 1

                if len(attempted_providers) > 1:
                    route_summary = f"{attempted_providers[0]} → {display_name} failover"
                else:
                    route_summary = display_name
                self.last_route_summary = route_summary

                self.call_history.append({
                    "caller": caller_name,
                    "provider": display_name,
                    "model": response.model,
                    "status": "success",
                    "tokens": response.tokens_used,
                    "failover": self.last_failover_occurred,
                })

                return response

            except RateLimitError as exc:
                cooldown_dur = exc.retry_after or self.default_cooldown_seconds
                self.set_cooldown(prov_name, cooldown_dur)
                failover_events.append(f"{display_name} 429 quota")
                logger.warning(
                    "%s → %s → 429 quota (cooldown %.0fs, failing over)",
                    caller_name,
                    display_name,
                    cooldown_dur,
                )
                continue

            except ModelNotFoundError as exc:
                # Obsolete model or 404
                failover_events.append(f"{display_name} 404 model")
                logger.warning("%s → %s → 404 model not found (failing over)", caller_name, display_name)
                continue

            except ProviderTimeoutError as exc:
                # Bounded timeout reached
                self.set_cooldown(prov_name, 30.0)  # short cooldown to avoid immediate repeat timeout
                failover_events.append(f"{display_name} timeout")
                logger.warning("%s → %s → timeout (failing over)", caller_name, display_name)
                continue

            except ServerError as exc:
                # 5xx Server Error
                failover_events.append(f"{display_name} 5xx")
                logger.warning("%s → %s → 5xx server error (failing over)", caller_name, display_name)
                continue

            except Exception as exc:
                # Generic provider error
                safe_err = sanitize_secret(str(exc))
                failover_events.append(f"{display_name} error")
                logger.warning("%s → %s → error: %s (failing over)", caller_name, display_name, safe_err)
                continue

        # If all configured active providers failed or were in cooldown
        self.last_provider_used = "Deterministic Fallback"
        self.last_failover_occurred = True
        self.last_route_summary = "Deterministic Fallback"

        logger.warning(
            "All LLM providers failed or exhausted for %s. Failing over to deterministic synthesis.",
            caller_name,
        )

        # If mock fallback is explicitly allowed
        if self.allow_mock_fallback and "mock" in self.providers:
            logger.info("%s → Mock → fallback success", caller_name)
            self.last_provider_used = "Mock"
            return self.providers["mock"].generate(
                prompt=prompt,
                system_prompt=system_prompt,
                schema=schema,
                temperature=temperature,
                caller=caller_name,
            )

        raise AllProvidersExhaustedError(
            f"All active LLM providers ({', '.join(attempted_providers) or 'None'}) failed or exhausted. Failing over to deterministic synthesis.",
            provider=self.name,
        )

    def get_summary(self) -> str:
        """Return summary of last LLM call routing."""
        return self.last_route_summary or "Deterministic Fallback"
