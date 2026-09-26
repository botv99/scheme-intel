"""Abstract base class and contracts for LLM Providers in Stage 2."""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""

    def __init__(
        self,
        message: str,
        provider: str = "",
        status_code: Optional[int] = None,
        retry_after: Optional[float] = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retry_after = retry_after


class RateLimitError(LLMProviderError):
    """HTTP 429 or quota exceeded."""
    pass


class ModelNotFoundError(LLMProviderError):
    """HTTP 404 or model not found / obsolete."""
    pass


class ProviderTimeoutError(LLMProviderError):
    """HTTP request timeout."""
    pass


class ServerError(LLMProviderError):
    """HTTP 5xx server error."""
    pass


class AllProvidersExhaustedError(LLMProviderError):
    """Raised when every configured provider fails."""
    pass


def sanitize_secret(text: str, secret: Optional[str] = None) -> str:
    """Mask any sensitive credentials, tokens, or query keys from text and logs."""
    if not text:
        return ""
    if secret and len(secret) > 3:
        text = text.replace(secret, "***")
    for key in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "TELEGRAM_BOT_TOKEN",
    ):
        val = os.getenv(key)
        if val and len(val) > 4:
            text = text.replace(val, "***")
    # Mask Bearer tokens
    text = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]{8,}", "Bearer ***", text)
    # Mask key= query parameters in URLs
    text = re.sub(r"key=[A-Za-z0-9_\-]{8,}", "key=***", text)
    return text


@dataclass
class ProviderResponse:
    content: str
    raw_json: Optional[dict] = None
    model: str = ""
    tokens_used: int = 0
    provider: str = ""
    latency_s: float = 0.0


class LLMProvider(ABC):
    """Abstract interface for LLM inference providers."""

    name: str = "base"

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.2,
        caller: str = "",
    ) -> ProviderResponse:
        """Generate text or structured response from LLM."""
        pass

    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: str = "",
        temperature: float = 0.2,
        caller: str = "",
    ) -> T:
        """Generate and validate output directly into a Pydantic model."""
        response = self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            schema=schema,
            temperature=temperature,
            caller=caller,
        )
        if response.raw_json is not None:
            return schema.model_validate(response.raw_json)

        # Fallback to parsing JSON from content string
        clean = response.content.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        data = json.loads(clean)
        return schema.model_validate(data)
