"""
Safe Diagnostic Tool for Scheme-Intel Telegram Gateway (Stage 3).
Performs getMe, getWebhookInfo, getUpdates, and optional sendMessage inspections without exposing tokens.

Usage:
  python scripts/diagnose_telegram.py [--send-test]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
import requests

# Automatically load .env if present
try:
    from scheme_intel.config import load_dotenv
    load_dotenv()
except ImportError:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v


def run_diagnostics(send_test: bool = False) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    print("=" * 60)
    print("SCHEME-INTEL TELEGRAM GATEWAY LIVE DIAGNOSTIC")
    print("=" * 60)

    if not token:
        print("[!] TELEGRAM_BOT_TOKEN is NOT set in current environment.")
        print("   To run live diagnostics locally:")
        print("   $env:TELEGRAM_BOT_TOKEN=\"<your-token>\"  (PowerShell)")
        print("   export TELEGRAM_BOT_TOKEN=\"<your-token>\" (Bash)")
        print("   or place it in a local .env file.")
        print("=" * 60)
        return False

    masked_token = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "***"
    print(f"[*] Bot Token: Configured ({masked_token}, length={len(token)})")

    # 1. getMe
    print("\n[1/5] Testing getMe...")
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
    print("\n[2/5] Testing getWebhookInfo...")
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=10)
        if resp.status_code == 200 and resp.json().get("ok"):
            wh = resp.json().get("result", {})
            wh_url = wh.get("url", "")
            if wh_url:
                print(f"  [!] ACTIVE WEBHOOK CONFLICT: '{wh_url}'")
                print("     Long-polling cannot receive updates while a webhook is set.")
                print(f"     Pending update count: {wh.get('pending_update_count', 0)}")
                del_webhook = os.getenv("TELEGRAM_DELETE_WEBHOOK", "").lower() in ("true", "1")
                if del_webhook:
                    print("     TELEGRAM_DELETE_WEBHOOK=true detected. Deleting webhook...")
                    del_resp = requests.post(f"https://api.telegram.org/bot{token}/deleteWebhook", json={"drop_pending_updates": False}, timeout=10)
                    if del_resp.status_code == 200 and del_resp.json().get("ok"):
                        print("     [OK] Successfully removed active webhook.")
                    else:
                        print(f"     [ERROR] Failed to delete webhook: {del_resp.text}")
                else:
                    print("     To clear automatically, set TELEGRAM_DELETE_WEBHOOK=true")
            else:
                print("  [OK] Webhook status: CLEAN (Compatible with getUpdates long-polling).")
                print(f"  * Pending update count: {wh.get('pending_update_count', 0)}")
        else:
            print(f"  [!] getWebhookInfo returned HTTP {resp.status_code}")
    except Exception as e:
        print(f"  [!] getWebhookInfo error: {e}")

    # 3. getUpdates
    print("\n[3/5] Testing getUpdates...")
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"limit": 10}, timeout=15)
        if resp.status_code == 200 and resp.json().get("ok"):
            updates = resp.json().get("result", [])
            print(f"  [OK] getUpdates succeeded. Retrieved {len(updates)} pending updates.")
            for u in updates:
                u_id = u.get("update_id")
                msg = u.get("message") or u.get("edited_message") or u.get("callback_query", {})
                chat_id = msg.get("chat", {}).get("id") or msg.get("message", {}).get("chat", {}).get("id")
                user = msg.get("from", {}).get("username") or msg.get("from", {}).get("id")
                txt = msg.get("text") or msg.get("data") or "<media/event>"
                print(f"    - Update #{u_id}: chat_id={chat_id}, user={user}, query='{str(txt)[:45]}'")
        else:
            print(f"  [!] getUpdates returned HTTP {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        print(f"  [!] getUpdates error: {e}")

    # 4. setMyCommands verification
    print("\n[4/5] Testing setMyCommands...")
    try:
        from scheme_intel.delivery.telegram_conversation import register_bot_commands
        cmd_ok = register_bot_commands(token)
        if cmd_ok:
            print("  [OK] setMyCommands successfully registered commands with Telegram API.")
        else:
            print("  [!] setMyCommands did not complete successfully.")
    except Exception as e:
        print(f"  [!] setMyCommands error: {e}")

    # 5. Optional sendMessage verification
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if send_test and chat_id:
        print(f"\n[5/5] Testing sendMessage to configured chat_id={chat_id}...")
        try:
            from scheme_intel.notifier import send_telegram
            success = send_telegram(
                message="🤖 *Scheme-Intel Telegram Gateway Diagnostic*\n\nGateway connectivity test successful. Terminal ready for queries.",
                chat_ids=[str(chat_id)],
            )
            if success:
                print("  [OK] Test message sent successfully.")
            else:
                print("  [!] Failed sending test message.")
        except Exception as e:
            print(f"  [ERROR] sendMessage error: {e}")
    else:
        print("\n[5/5] sendMessage test skipped (pass --send-test to verify).")

    print("\n" + "=" * 60)
    print("LIVE DIAGNOSTIC COMPLETE")
    print("=" * 60)
    return True


if __name__ == "__main__":
    send_flag = "--send-test" in sys.argv
    success = run_diagnostics(send_test=send_flag)
    sys.exit(0 if success else 1)
