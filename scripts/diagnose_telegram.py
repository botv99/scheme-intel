"""
Safe Diagnostic Tool for Scheme-Intel Telegram Gateway (Stage 3).
Performs getMe, getWebhookInfo, and getUpdates inspections without exposing tokens.

Usage:
  python scripts/diagnose_telegram.py
"""
from __future__ import annotations

import os
import sys
import requests


def run_diagnostics():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    print("=" * 60)
    print("SCHEME-INTEL TELEGRAM GATEWAY LIVE DIAGNOSTIC")
    print("=" * 60)

    if not token:
        print("[!] TELEGRAM_BOT_TOKEN is NOT set in current environment.")
        print("   To run live diagnostics locally:")
        print("   $env:TELEGRAM_BOT_TOKEN=\"<your-token>\"  (PowerShell)")
        print("   export TELEGRAM_BOT_TOKEN=\"<your-token>\" (Bash)")
        print("=" * 60)
        return False

    masked_token = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "***"
    print(f"[*] Bot Token: Configured ({masked_token}, length={len(token)})")

    # 1. getMe
    print("\n[1/3] Testing getMe...")
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        if resp.status_code == 200 and resp.json().get("ok"):
            me = resp.json().get("result", {})
            print("  [OK] Bot Token is VALID.")
            print(f"  * Bot ID: {me.get('id')}")
            print(f"  * First Name: {me.get('first_name')}")
            print(f"  * Username: @{me.get('username')}")
            print(f"  * Can Join Groups: {me.get('can_join_groups')}")
            print(f"  * Supports Inline Queries: {me.get('supports_inline_queries')}")
        else:
            print(f"  [ERROR] getMe failed: HTTP {resp.status_code} - {resp.text[:150]}")
            return False
    except Exception as e:
        print(f"  [ERROR] getMe network error: {e}")
        return False

    # 2. getWebhookInfo
    print("\n[2/3] Testing getWebhookInfo...")
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=10)
        if resp.status_code == 200 and resp.json().get("ok"):
            wh = resp.json().get("result", {})
            wh_url = wh.get("url", "")
            if wh_url:
                print(f"  [!] ACTIVE WEBHOOK CONFLICT: '{wh_url}'")
                print("     Long-polling cannot receive updates while a webhook is set.")
                print(f"     Pending update count: {wh.get('pending_update_count', 0)}")
                print("     To clear: https://api.telegram.org/bot<TOKEN>/deleteWebhook")
            else:
                print("  [OK] Webhook status: CLEAN (Compatible with getUpdates long-polling).")
                print(f"  * Pending update count: {wh.get('pending_update_count', 0)}")
        else:
            print(f"  [!] getWebhookInfo returned HTTP {resp.status_code}")
    except Exception as e:
        print(f"  [!] getWebhookInfo error: {e}")

    # 3. getUpdates
    print("\n[3/3] Testing getUpdates...")
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"limit": 5}, timeout=15)
        if resp.status_code == 200 and resp.json().get("ok"):
            updates = resp.json().get("result", [])
            print(f"  [OK] getUpdates succeeded. Retrieved {len(updates)} pending updates.")
            for u in updates:
                u_id = u.get("update_id")
                msg = u.get("message") or u.get("edited_message") or u.get("callback_query", {})
                chat_id = msg.get("chat", {}).get("id") or msg.get("message", {}).get("chat", {}).get("id")
                user = msg.get("from", {}).get("username") or msg.get("from", {}).get("id")
                txt = msg.get("text") or msg.get("data") or "<media/event>"
                print(f"    - Update #{u_id}: chat_id={chat_id}, user={user}, query='{str(txt)[:35]}'")
        else:
            print(f"  [!] getUpdates returned HTTP {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        print(f"  [!] getUpdates error: {e}")

    print("\n" + "=" * 60)
    print("LIVE DIAGNOSTIC COMPLETE")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = run_diagnostics()
    sys.exit(0 if success else 1)
