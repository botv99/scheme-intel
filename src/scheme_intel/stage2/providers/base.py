"""Abstract base class for LLM Providers in Stage 2."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class ProviderResponse:
    content: str
    raw_json: Optional[dict] = None
    model: str = ""
    tokens_used: int = 0


class LLMProvider(ABC):
    """Abstract interface for LLM inference providers."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.2,
    ) -> ProviderResponse:
        """Generate text or structured response from LLM."""
        pass

    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: str = "",
        temperature: float = 0.2,
    ) -> T:
        """Generate and validate output directly into a Pydantic model."""
        response = self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            schema=schema,
            temperature=temperature,
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
