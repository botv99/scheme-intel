"""Google Gemini LLM Provider for Stage 2."""
from __future__ import annotations

import json
import os
import time
from typing import Optional, Type
import requests
from pydantic import BaseModel

from .base import (
    LLMProvider,
    ProviderResponse,
    RateLimitError,
    ModelNotFoundError,
    ProviderTimeoutError,
    ServerError,
    LLMProviderError,
    sanitize_secret,
)
from ...logger import get_logger

logger = get_logger(__name__)


class GeminiProvider(LLMProvider):
    """Provider connecting to Google Gemini REST API."""

    name: str = "gemini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_version: str = "v1beta",
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"
        self.api_version = api_version
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.2,
        caller: str = "",
    ) -> ProviderResponse:
        if not self.api_key:
            raise LLMProviderError("GEMINI_API_KEY or GOOGLE_API_KEY is not configured", provider=self.name)

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
            "maxOutputTokens": 8192,
        }
        if schema:
            generation_config["responseMimeType"] = "application/json"

        payload = {
            "contents": contents,
            "generationConfig": generation_config,
        }

        start_t = time.time()
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            msg = sanitize_secret(f"Gemini API request timed out after {self.timeout}s: {exc}", self.api_key)
            raise ProviderTimeoutError(msg, provider=self.name) from exc
        except requests.exceptions.RequestException as exc:
            msg = sanitize_secret(f"Gemini API network error: {exc}", self.api_key)
            raise LLMProviderError(msg, provider=self.name) from exc

        # Handle specific status codes
        if resp.status_code == 429:
            # Rate limit or quota exceeded
            retry_after = None
            ra_hdr = resp.headers.get("Retry-After")
            if ra_hdr:
                try:
                    retry_after = float(ra_hdr)
                except ValueError:
                    retry_after = 60.0
            else:
                retry_after = 60.0

            err_text = self._extract_error_message(resp)
            raise RateLimitError(
                f"Gemini quota/rate limit reached (429): {err_text}",
                provider=self.name,
                status_code=429,
                retry_after=retry_after,
            )

        if resp.status_code == 404:
            err_text = self._extract_error_message(resp)
            raise ModelNotFoundError(
                f"Gemini model not found (404) for '{model_name}': {err_text}",
                provider=self.name,
                status_code=404,
            )

        if 500 <= resp.status_code < 600:
            err_text = self._extract_error_message(resp)
            raise ServerError(
                f"Gemini server error ({resp.status_code}): {err_text}",
                provider=self.name,
                status_code=resp.status_code,
            )

        if resp.status_code != 200:
            err_text = self._extract_error_message(resp)
            raise LLMProviderError(
                f"Gemini API returned status {resp.status_code}: {err_text}",
                provider=self.name,
                status_code=resp.status_code,
            )

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise LLMProviderError("No candidates returned from Gemini API", provider=self.name)

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
        latency = round(time.time() - start_t, 2)

        return ProviderResponse(
            content=part_text,
            raw_json=raw_json,
            model=model_name,
            tokens_used=tokens,
            provider=self.name,
            latency_s=latency,
        )

    def _extract_error_message(self, resp: requests.Response) -> str:
        try:
            err_json = resp.json()
            msg = err_json.get("error", {}).get("message", resp.text)
        except Exception:
            msg = resp.text
        return sanitize_secret(msg, self.api_key)
