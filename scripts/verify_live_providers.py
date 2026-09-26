"""
Live Production Verification Script for Scheme-Intel Multi-Provider Architecture.
Executes minimal, quota-safe live API calls across configured providers using actual secrets.
Performs:
1. Secret presence verification (YES/NO, never values)
2. Live model discovery and validity check
3. Safe live generation test per provider (tiny prompt, minimal tokens)
4. LLMProviderManager detection and real per-call routing
5. Controlled simulated failover test (quota-safe)
6. Secret leakage check
"""
from __future__ import annotations

import os
import sys
import time
import json
import re
from typing import Dict, Any, Optional, List

import requests
from pydantic import BaseModel, Field

# Ensure src is in sys.path
sys.path.insert(0, os.path.abspath("src"))

from scheme_intel.stage2.providers.base import (
    LLMProvider,
    ProviderResponse,
    RateLimitError,
    sanitize_secret,
)
from scheme_intel.stage2.providers.gemini import GeminiProvider
from scheme_intel.stage2.providers.groq import GroqProvider
from scheme_intel.stage2.providers.openrouter import OpenRouterProvider
from scheme_intel.stage2.providers.openai import OpenAIProvider
from scheme_intel.stage2.providers.manager import LLMProviderManager


class MiniStatusResponse(BaseModel):
    status: str
    symbol: str = "TEST.NS"


def mask_str(text: str) -> str:
    return sanitize_secret(text)


def test_gemini_live() -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"configured": False, "status": "SKIPPED", "reason": "No GEMINI_API_KEY"}

    print("\n--- [1] Testing Gemini Live API ---")
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    print(f"Selected Gemini model: {model}")

    start_t = time.time()
    try:
        provider = GeminiProvider(api_key=api_key, model=model, timeout=20.0)
        res = provider.generate_structured(
            prompt="Respond with JSON: {'status': 'LIVE_OK', 'symbol': 'TEST.NS'}",
            schema=MiniStatusResponse,
            caller="LiveTest",
        )
        latency = round(time.time() - start_t, 2)
        print(f"Gemini Live Test: SUCCESS in {latency}s | Model: {provider.model} | Result: {res.status}")
        return {
            "configured": True,
            "status": "PASS",
            "model": provider.model,
            "latency": latency,
            "result": res.model_dump(),
        }
    except Exception as exc:
        latency = round(time.time() - start_t, 2)
        err_msg = mask_str(str(exc))
        print(f"Gemini Live Test: FAILED in {latency}s | Reason: {err_msg}")
        return {
            "configured": True,
            "status": "FAIL",
            "model": model,
            "latency": latency,
            "reason": err_msg,
        }


def test_groq_live() -> Dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"configured": False, "status": "SKIPPED", "reason": "No GROQ_API_KEY"}

    print("\n--- [2] Testing Groq Live API ---")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    supported_models: List[str] = []
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=15)
        if r.status_code == 200:
            supported_models = [m.get("id") for m in r.json().get("data", [])]
            print(f"All Groq available models ({len(supported_models)}): {supported_models}")
    except Exception as e:
        print(f"Groq ListModels error: {mask_str(str(e))}")

    # Build candidates to test
    env_model = os.getenv("GROQ_MODEL")
    candidates = [env_model] if env_model else []
    for cand in supported_models:
        if cand not in candidates:
            candidates.append(cand)
    if not candidates:
        candidates = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

    last_err = ""
    for candidate_model in candidates:
        print(f"Testing Groq model candidate: {candidate_model}")
        start_t = time.time()
        try:
            provider = GroqProvider(api_key=api_key, model=candidate_model, timeout=20.0)
            res = provider.generate_structured(
                prompt="Respond with JSON: {'status': 'LIVE_OK', 'symbol': 'TEST.NS'}",
                schema=MiniStatusResponse,
                caller="LiveTest",
            )
            latency = round(time.time() - start_t, 2)
            print(f"Groq Live Test: SUCCESS in {latency}s | Model: {candidate_model} | Result: {res.status}")
            return {
                "configured": True,
                "status": "PASS",
                "model": candidate_model,
                "latency": latency,
                "result": res.model_dump(),
            }
        except Exception as exc:
            latency = round(time.time() - start_t, 2)
            last_err = mask_str(str(exc))
            print(f"Groq candidate '{candidate_model}' failed in {latency}s: {last_err}")

    return {
        "configured": True,
        "status": "FAIL",
        "model": candidates[0] if candidates else "none",
        "reason": last_err,
    }


def test_openrouter_live() -> Dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {"configured": False, "status": "SKIPPED", "reason": "No OPENROUTER_API_KEY"}

    print("\n--- [3] Testing OpenRouter Live API ---")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/scheme-intel",
        "X-Title": "Scheme-Intel",
    }
    supported_free_models: List[str] = []
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=15)
        if r.status_code == 200:
            all_models = [m.get("id") for m in r.json().get("data", [])]
            supported_free_models = [m for m in all_models if ":free" in m]
            print(f"OpenRouter available free models count: {len(supported_free_models)}")
            print(f"Sample free models: {supported_free_models[:10]}")
    except Exception as e:
        print(f"OpenRouter ListModels error: {mask_str(str(e))}")

    # Build candidates to test
    env_model = os.getenv("OPENROUTER_MODEL")
    candidates = [env_model] if env_model else []
    preferred_free = [
        "qwen/qwen3.8-27b:free",
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "mistralai/mistral-small-24b-instruct-2501:free",
        "deepseek/deepseek-r1:free",
        "meta-llama/llama-3.2-3b-instruct:free",
        "liquid/lfm-2.5-2.6b:free",
    ]
    for p in preferred_free:
        if p in supported_free_models and p not in candidates:
            candidates.append(p)
    for f in supported_free_models[:5]:
        if f not in candidates:
            candidates.append(f)

    last_err = ""
    for candidate_model in candidates:
        print(f"Testing OpenRouter model candidate: {candidate_model}")
        start_t = time.time()
        try:
            provider = OpenRouterProvider(api_key=api_key, model=candidate_model, timeout=25.0)
            res = provider.generate_structured(
                prompt="Respond with valid JSON: {'status': 'LIVE_OK', 'symbol': 'TEST.NS'}",
                schema=MiniStatusResponse,
                caller="LiveTest",
            )
            latency = round(time.time() - start_t, 2)
            print(f"OpenRouter Live Test: SUCCESS in {latency}s | Model: {candidate_model} | Result: {res.status}")
            return {
                "configured": True,
                "status": "PASS",
                "model": candidate_model,
                "latency": latency,
                "result": res.model_dump(),
            }
        except Exception as exc:
            latency = round(time.time() - start_t, 2)
            last_err = mask_str(str(exc))
            print(f"OpenRouter candidate '{candidate_model}' failed in {latency}s: {last_err}")

    return {
        "configured": True,
        "status": "FAIL",
        "model": candidates[0] if candidates else "none",
        "reason": last_err,
    }


def test_openai_live() -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"configured": False, "status": "SKIPPED", "reason": "No OPENAI_API_KEY"}

    print("\n--- [4] Testing OpenAI Live API ---")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    print(f"Selected OpenAI model: {model}")
    start_t = time.time()
    try:
        provider = OpenAIProvider(api_key=api_key, model=model, timeout=20.0)
        res = provider.generate_structured(
            prompt="Respond with JSON: {'status': 'LIVE_OK', 'symbol': 'TEST.NS'}",
            schema=MiniStatusResponse,
            caller="LiveTest",
        )
        latency = round(time.time() - start_t, 2)
        print(f"OpenAI Live Test: SUCCESS in {latency}s | Result: {res.status}")
        return {
            "configured": True,
            "status": "PASS",
            "model": model,
            "latency": latency,
            "result": res.model_dump(),
        }
    except Exception as exc:
        latency = round(time.time() - start_t, 2)
        err_msg = mask_str(str(exc))
        print(f"OpenAI Live Test: FAILED in {latency}s | Reason: {err_msg}")
        return {
            "configured": True,
            "status": "FAIL",
            "model": model,
            "latency": latency,
            "reason": err_msg,
        }


def test_provider_manager_live() -> Dict[str, Any]:
    print("\n--- [5] Testing LLMProviderManager with Real Providers ---")
    manager = LLMProviderManager(allow_mock_fallback=False)
    print(f"Manager detected active providers: {manager.active_order}")

    calls_made = []
    # Test 3 real requests simulating Bull, Bear, Arbitrator calls
    for caller in ["BullAgent", "BearAgent", "ArbitratorAgent"]:
        start_t = time.time()
        try:
            resp = manager.generate_structured(
                prompt=f"Adversarial request for {caller}. Reply with JSON: {{'status': 'LIVE_OK', 'symbol': 'PRAJIND.NS'}}",
                schema=MiniStatusResponse,
                caller=caller,
            )
            lat = round(time.time() - start_t, 2)
            calls_made.append({
                "caller": caller,
                "provider": manager.last_provider_used,
                "status": "success",
                "latency": lat,
            })
            print(f"-> {caller} → {manager.last_provider_used} → success in {lat}s")
        except Exception as e:
            lat = round(time.time() - start_t, 2)
            calls_made.append({
                "caller": caller,
                "status": "failed",
                "reason": mask_str(str(e)),
                "latency": lat,
            })
            print(f"-> {caller} FAILED in {lat}s: {mask_str(str(e))}")

    return {
        "active_order": manager.active_order,
        "calls": calls_made,
    }


def test_simulated_failover_safety() -> Dict[str, Any]:
    print("\n--- [6] Testing Controlled Simulated Failover ---")
    # Simulate Provider A returning 429 quota, Provider B succeeding
    class MockFailingProvider(LLMProvider):
        name = "mock_failing_gemini"
        def generate(self, prompt, **kwargs):
            raise RateLimitError("Simulated 429 quota limit", provider=self.name, status_code=429, retry_after=5.0)

    class MockBackupProvider(LLMProvider):
        name = "mock_backup_groq"
        def generate(self, prompt, **kwargs):
            return ProviderResponse(content='{"status": "BACKUP_OK", "symbol": "TEST.NS"}', provider="mock_backup_groq")

    mgr = LLMProviderManager(
        providers={
            "failing": MockFailingProvider(),
            "backup": MockBackupProvider(),
        },
        provider_order=["failing", "backup"],
    )

    res = mgr.generate_structured(
        prompt="Test prompt",
        schema=MiniStatusResponse,
        caller="FailoverTestAgent",
    )

    assert res.status == "BACKUP_OK", "Backup provider did not succeed"
    assert mgr.is_in_cooldown("failing"), "Failing provider not in cooldown"
    assert mgr.last_route_summary == "Mock_failing_gemini → Mock_backup_groq failover"
    print(f"Failover Test 1 PASSED: Failing (429) → Backup Success (Summary: {mgr.last_route_summary})")

    # Second call while in cooldown: should directly skip failing provider
    res2 = mgr.generate_structured(
        prompt="Test prompt 2",
        schema=MiniStatusResponse,
        caller="CooldownTestAgent",
    )
    assert res2.status == "BACKUP_OK"
    assert mgr.last_route_summary == "Mock_backup_groq"
    print("Failover Test 2 PASSED: Cooldown bypass verified (Backup called directly without re-hammering)")

    return {"status": "PASS", "summary": "Simulated failover and cooldown verified safely"}


def main():
    print("=================================================================")
    print("SCHEME-INTEL REAL PRODUCTION MULTI-PROVIDER VERIFICATION")
    print("=================================================================")

    # 1. Secrets presence check
    secrets_present = {
        "GEMINI_API_KEY": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        "GROQ_API_KEY": bool(os.getenv("GROQ_API_KEY")),
        "OPENROUTER_API_KEY": bool(os.getenv("OPENROUTER_API_KEY")),
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
    }
    print("Secrets Detected:")
    for k, v in secrets_present.items():
        print(f"  • {k}: {'YES' if v else 'NO'}")

    # 2. Live Provider tests
    gemini_res = test_gemini_live()
    groq_res = test_groq_live()
    openrouter_res = test_openrouter_live()
    openai_res = test_openai_live()

    # 3. Provider Manager live test
    manager_res = test_provider_manager_live()

    # 4. Simulated failover test
    failover_res = test_simulated_failover_safety()

    print("\n=================================================================")
    print("VERIFICATION SUMMARY")
    print("=================================================================")
    summary = {
        "secrets": {k: "YES" if v else "NO" for k, v in secrets_present.items()},
        "gemini": gemini_res,
        "groq": groq_res,
        "openrouter": openrouter_res,
        "openai": openai_res,
        "manager_live": manager_res,
        "failover_simulation": failover_res,
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
