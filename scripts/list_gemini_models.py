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

if __name__ == "__main__":
    main()
