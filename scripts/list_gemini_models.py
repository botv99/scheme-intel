"""Diagnostic script to query Google Gemini ListModels API."""
import os
import requests
import json

def main():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: No GEMINI_API_KEY or GOOGLE_API_KEY found in environment.")
        return

    for version in ["v1beta", "v1"]:
        url = f"https://generativelanguage.googleapis.com/{version}/models?key={api_key}"
        try:
            resp = requests.get(url, timeout=20)
            print(f"=== ListModels [{version}] Status: {resp.status_code} ===")
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                print(f"Found {len(models)} models for {version}:")
                flash_supported = []
                for m in models:
                    name = m.get("name", "")
                    methods = m.get("supportedGenerationMethods", [])
                    disp = m.get("displayName", "")
                    print(f"  - {name} ({disp}): methods={methods}")
                    if "generateContent" in methods and "flash" in name.lower():
                        flash_supported.append(name)
                print(f"Flash models supporting generateContent for {version}: {flash_supported}")
            else:
                err_msg = resp.text
                if api_key in err_msg:
                    err_msg = err_msg.replace(api_key, "***")
                print(f"ListModels [{version}] failed: {err_msg}")
        except Exception as e:
            print(f"ListModels [{version}] exception: {e}")

    # Test direct generateContent on gemini-3.8-flash
    print("\n=== Testing gemini-3.8-flash generateContent live ===")
    test_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={api_key}"
    try:
        test_resp = requests.post(
            test_url,
            json={"contents": [{"parts": [{"text": "Reply with ONLY: LIVE_GEMINI_OK"}]}]},
            timeout=15,
        )
        print(f"gemini-3.8-flash HTTP status: {test_resp.status_code}")
        if test_resp.status_code == 200:
            res_text = test_resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            print(f"gemini-3.8-flash response text: {res_text.strip()}")
        else:
            print(f"gemini-3.8-flash test error: {test_resp.text}")
    except Exception as exc:
        print(f"gemini-3.8-flash test exception: {exc}")

if __name__ == "__main__":
    main()
