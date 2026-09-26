"""OpenRouter LLM Provider for Stage 2 with fallback model recovery and universal JSON parsing."""
from __future__ import annotations

import json
import os
import time
from typing import Optional, Type, List
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

DEFAULT_OPENROUTER_FALLBACKS = [
    "qwen/qwen3.8-27b:free",
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-24b-instruct-2501:free",
    "deepseek/deepseek-r1:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "liquid/lfm-2.5-2.6b:free",
]


class OpenRouterProvider(LLMProvider):
    """Provider connecting to OpenRouter multi-model gateway API."""

    name: str = "openrouter"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("OPENROUTER_MODEL") or "qwen/qwen3.8-27b:free"
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
            raise LLMProviderError("OPENROUTER_API_KEY is not configured", provider=self.name)

        models_to_try: List[str] = [self.model]
        for fb in DEFAULT_OPENROUTER_FALLBACKS:
            if fb not in models_to_try:
                models_to_try.append(fb)

        last_exc: Optional[Exception] = None
        for current_model in models_to_try:
            try:
                return self._generate_with_model(
                    current_model, prompt, system_prompt, schema, temperature, caller
                )
            except (ModelNotFoundError, LLMProviderError) as exc:
                if isinstance(exc, RateLimitError):
                    raise
                logger.info("OpenRouter model '%s' error (%s), trying alternate model...", current_model, exc)
                last_exc = exc
                continue
            except Exception:
                raise

        if last_exc:
            raise last_exc
        raise LLMProviderError(f"All OpenRouter models exhausted ({models_to_try})", provider=self.name)

    def _generate_with_model(
        self,
        model_name: str,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.2,
        caller: str = "",
    ) -> ProviderResponse:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/scheme-intel",
            "X-Title": "Scheme-Intel",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_content = prompt
        if schema:
            user_content += f"\n\nOutput MUST be valid JSON adhering strictly to this schema: {json.dumps(schema.model_json_schema())}"

        messages.append({"role": "user", "content": user_content})

        # Do NOT force response_format by default on OpenRouter free tier because many endpoints reject it with HTTP 400
        payload: dict = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
        }

        start_t = time.time()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            msg = sanitize_secret(f"OpenRouter API request timed out after {self.timeout}s: {exc}", self.api_key)
            raise ProviderTimeoutError(msg, provider=self.name) from exc
        except requests.exceptions.RequestException as exc:
            msg = sanitize_secret(f"OpenRouter API network error: {exc}", self.api_key)
            raise LLMProviderError(msg, provider=self.name) from exc

        if resp.status_code == 429:
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
                f"OpenRouter quota/rate limit reached (429): {err_text}",
                provider=self.name,
                status_code=429,
                retry_after=retry_after,
            )

        if resp.status_code == 404:
            err_text = self._extract_error_message(resp)
            raise ModelNotFoundError(
                f"OpenRouter model '{model_name}' not found (404): {err_text}",
                provider=self.name,
                status_code=404,
            )

        if 500 <= resp.status_code < 600:
            err_text = self._extract_error_message(resp)
            raise ServerError(
                f"OpenRouter server error ({resp.status_code}): {err_text}",
                provider=self.name,
                status_code=resp.status_code,
            )

        if resp.status_code != 200:
            err_text = self._extract_error_message(resp)
            raise LLMProviderError(
                f"OpenRouter API returned status {resp.status_code}: {err_text}",
                provider=self.name,
                status_code=resp.status_code,
            )

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise LLMProviderError("No choices returned from OpenRouter API", provider=self.name)

        content = choices[0].get("message", {}).get("content", "")
        raw_json = None
        if schema or "{" in content:
            try:
                clean = content.strip()
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

        tokens = data.get("usage", {}).get("total_tokens", 0)
        latency = round(time.time() - start_t, 2)
        self.model = model_name  # Update to working model

        return ProviderResponse(
            content=content,
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
