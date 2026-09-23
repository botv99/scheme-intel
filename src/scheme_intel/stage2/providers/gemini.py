"""Google Gemini LLM Provider for Stage 2."""
from __future__ import annotations

import json
import os
from typing import Optional, Type
import requests
from pydantic import BaseModel

from .base import LLMProvider, ProviderResponse
from ...logger import get_logger

logger = get_logger(__name__)


class GeminiProvider(LLMProvider):
    """Provider connecting to Google Gemini REST API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = model

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.2,
    ) -> ProviderResponse:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY is required for GeminiProvider")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System Instructions: {system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly follow these instructions."}]})

        req_text = prompt
        if schema:
            req_text += f"\n\nOutput MUST be valid JSON adhering strictly to this schema: {json.dumps(schema.model_json_schema())}"

        contents.append({"role": "user", "parts": [{"text": req_text}]})

        generation_config: dict = {
            "temperature": temperature,
            "maxOutputTokens": 2048,
        }
        if schema:
            generation_config["responseMimeType"] = "application/json"

        payload = {
            "contents": contents,
            "generationConfig": generation_config,
        }

        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates returned from Gemini API")

            part_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            raw_json = None
            if schema or "{" in part_text:
                try:
                    clean = part_text.strip()
                    if clean.startswith("```json"):
                        clean = clean[7:]
                    if clean.endswith("```"):
                        clean = clean[:-3]
                    raw_json = json.loads(clean.strip())
                except json.JSONDecodeError:
                    pass

            return ProviderResponse(
                content=part_text,
                raw_json=raw_json,
                model=self.model,
                tokens_used=data.get("usageMetadata", {}).get("totalTokenCount", 0),
            )
        except Exception as exc:
            logger.error("Gemini API generation failed: %s", exc)
            raise
