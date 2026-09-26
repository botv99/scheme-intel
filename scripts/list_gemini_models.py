"""Diagnostic script to query and discover available LLM models across configured providers."""
import os
import requests
import json
import re

def mask(text, key=None):
    if not text:
        return ""
    if key and len(key) > 3:
        text = text.replace(key, "***")
    for k in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"]:
        v = os.getenv(k)
        if v and len(v) > 4:
            text = text.replace(v, "***")
    text = re.sub(r'Bearer\s+[A-Za-z0-9_\-\.]{8,}', 'Bearer ***', text)
    text = re.sub(r'key=[A-Za-z0-9_\-]{8,}', 'key=***', text)
    return text

def check_gemini():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("[Gemini] No GEMINI_API_KEY found (optional).")
        return

    print("\n--- Discovering Google Gemini Models ---")
    model_override = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    for version in ["v1beta", "v1"]:
        url = f"https://generativelanguage.googleapis.com/{version}/models?key={api_key}"
        try:
            resp = requests.get(url, timeout=15)
            print(f"=== ListModels [{version}] Status: {resp.status_code} ===")
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                flash_supported = [
                    m.get("name") for m in models
                    if "generateContent" in m.get("supportedGenerationMethods", []) and "flash" in m.get("name", "").lower()
                ]
                print(f"Discovered Flash models ({version}): {flash_supported[:6]}")
            else:
                print(f"ListModels [{version}] response: {mask(resp.text, api_key)}")
        except Exception as e:
            print(f"ListModels [{version}] error: {mask(str(e), api_key)}")

    # Test direct generateContent
    test_model = model_override.replace("models/", "")
    test_url = f"https://generativelanguage.googleapis.com/v1beta/models/{test_model}:generateContent?key={api_key}"
    try:
        test_resp = requests.post(
            test_url,
            json={"contents": [{"parts": [{"text": "Reply with ONLY: LIVE_GEMINI_OK"}]}]},
            timeout=15,
        )
        print(f"[{test_model}] generateContent status: {test_resp.status_code}")
        if test_resp.status_code == 200:
            res_text = test_resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            print(f"[{test_model}] response: {res_text.strip()}")
        else:
            print(f"[{test_model}] test error: {mask(test_resp.text, api_key)}")
    except Exception as exc:
        print(f"[{test_model}] test error: {mask(str(exc), api_key)}")

def check_groq():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("[Groq] No GROQ_API_KEY found (optional).")
        return

    print("\n--- Discovering Groq Models ---")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=15)
        print(f"Groq ListModels status: {resp.status_code}")
        if resp.status_code == 200:
            models = [m.get("id") for m in resp.json().get("data", [])]
            print(f"Discovered Groq models: {models[:6]}")
        else:
            print(f"Groq ListModels error: {mask(resp.text, api_key)}")
    except Exception as exc:
        print(f"Groq test exception: {mask(str(exc), api_key)}")

def check_openrouter():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("[OpenRouter] No OPENROUTER_API_KEY found (optional).")
        return

    print("\n--- Discovering OpenRouter Gateway ---")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=15)
        print(f"OpenRouter ListModels status: {resp.status_code}")
        if resp.status_code == 200:
            free_models = [m.get("id") for m in resp.json().get("data", []) if ":free" in m.get("id", "")]
            print(f"Discovered OpenRouter free models ({len(free_models)} found): {free_models[:5]}")
        else:
            print(f"OpenRouter ListModels error: {mask(resp.text, api_key)}")
    except Exception as exc:
        print(f"OpenRouter test exception: {mask(str(exc), api_key)}")

def check_openai():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[OpenAI] No OPENAI_API_KEY found (optional).")
        return

    print("\n--- Discovering OpenAI Models ---")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = requests.get("https://api.openai.com/v1/models", headers=headers, timeout=15)
        print(f"OpenAI ListModels status: {resp.status_code}")
        if resp.status_code == 200:
            gpt_models = [m.get("id") for m in resp.json().get("data", []) if "gpt" in m.get("id", "")]
            print(f"Discovered OpenAI models: {gpt_models[:5]}")
        else:
            print(f"OpenAI ListModels error: {mask(resp.text, api_key)}")
    except Exception as exc:
        print(f"OpenAI test exception: {mask(str(exc), api_key)}")

def main():
    print("========================================")
    print("Scheme-Intel LLM Provider Discovery Tool")
    print("========================================")
    check_gemini()
    check_groq()
    check_openrouter()
    check_openai()
    print("========================================\n")

if __name__ == "__main__":
    main()
