from __future__ import annotations

import os

import requests


def send_telegram(message: str) -> bool:
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True}, timeout=20)
    response.raise_for_status()
    return True


