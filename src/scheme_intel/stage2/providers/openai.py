"""OpenAI LLM Provider for Stage 2."""
from __future__ import annotations

import json
import os
from typing import Optional, Type
import requests
from pydantic import BaseModel

from .base import LLMProvider, ProviderResponse
from ...logger import get_logger

logger = get_logger(__name__)


class OpenAIProvider(LLMProvider):
    """Provider connecting to OpenAI Chat Completions API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.2,
    ) -> ProviderResponse:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIProvider")

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if schema:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]
            content = choice["message"]["content"]
            raw_json = None
            if schema:
                try:
                    raw_json = json.loads(content)
                except json.JSONDecodeError:
                    pass

            return ProviderResponse(
                content=content,
                raw_json=raw_json,
                model=self.model,
                tokens_used=data.get("usage", {}).get("total_tokens", 0),
            )
        except Exception as exc:
            logger.error("OpenAI API generation failed: %s", exc)
            raise
