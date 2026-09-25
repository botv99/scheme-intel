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

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_version: str = "v1beta",
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        # Default to Google ListModels-confirmed production Flash model
        self.model = model or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
        self.api_version = api_version

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.2,
    ) -> ProviderResponse:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY is required for GeminiProvider")

        model_name = self.model
        if model_name.startswith("models/"):
            model_name = model_name[7:]

        url = f"https://generativelanguage.googleapis.com/{self.api_version}/models/{model_name}:generateContent?key={self.api_key}"

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

            parts = candidates[0].get("content", {}).get("parts", [])
            part_text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p)
            if not part_text and parts and isinstance(parts[0], dict):
                part_text = parts[0].get("text", "")

            raw_json = None
            if schema or "{" in part_text:
                try:
                    clean = part_text.strip()
                    if "```json" in clean:
                        clean = clean.split("```json", 1)[1].split("```", 1)[0].strip()
                    elif "```" in clean:
                        clean = clean.split("```", 1)[1].split("```", 1)[0].strip()
                    elif "{" in clean and "}" in clean:
                        s_idx = clean.find("{")
                        e_idx = clean.rfind("}")
                        if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
                            clean = clean[s_idx : e_idx + 1]
                    raw_json = json.loads(clean.strip())
                except json.JSONDecodeError:
                    pass

            tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)
            logger.info("Gemini live API (%s) generated response: %d tokens used", model_name, tokens)

            return ProviderResponse(
                content=part_text,
                raw_json=raw_json,
                model=model_name,
                tokens_used=tokens,
            )
        except Exception as exc:
            resp_obj = getattr(exc, "response", None)
            err_text = ""
            if resp_obj is not None:
                try:
                    err_json = resp_obj.json()
                    err_text = err_json.get("error", {}).get("message", resp_obj.text)
                except Exception:
                    err_text = resp_obj.text
            if self.api_key:
                err_text = err_text.replace(self.api_key, "***")
            logger.error("Gemini API generation failed (%s): %s", exc, err_text)
            raise
