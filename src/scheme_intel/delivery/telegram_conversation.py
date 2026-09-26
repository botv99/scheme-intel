"""
Telegram Conversational Interface (Stage 3).
Provides unified request handling, message chunking, update processing, and long-polling runner.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
import requests

from .telegram_router import TelegramMessageRouter
from .telegram_alerts import chunk_message
from ..notifier import send_telegram
from ..logger import get_logger

logger = get_logger(__name__)

STAGE_3_READY = True


class TelegramConversationHandler:
    """Entry point for handling conversational Telegram queries."""

    def __init__(self, router: Optional[TelegramMessageRouter] = None):
        self.router = router or TelegramMessageRouter()

    def handle_message(
        self,
        text: str,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> str:
        """
        Process user message and return the formatted response.
        Handles message chunking if response exceeds Telegram's 4096 character limit.
        """
        raw_response = self.router.route_message(text, user_id=user_id, chat_id=chat_id)
        chunks = chunk_message(raw_response, max_chars=4000)
        return chunks[0] if chunks else ""

    def process_update(self, update: Dict[str, Any], send_reply: bool = True) -> Optional[str]:
        """Process a raw Telegram update dictionary (from Webhook or getUpdates)."""
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return None

        text = msg.get("text", "").strip()
        if not text:
            return None

        user_info = msg.get("from", {})
        user_id = str(user_info.get("id")) if user_info.get("id") else None
        chat_info = msg.get("chat", {})
        chat_id = str(chat_info.get("id")) if chat_info.get("id") else None

        raw_response = self.router.route_message(text, user_id=user_id, chat_id=chat_id)
        chunks = chunk_message(raw_response, max_chars=4000)

        if send_reply and chat_id and chunks:
            for ch in chunks:
                try:
                    send_telegram(ch, chat_ids=[chat_id], parse_mode="Markdown")
                except Exception as e:
                    logger.error("Failed sending Telegram reply to chat %s: %s", chat_id, e)

        return raw_response

    def run_polling(self, interval_seconds: int = 2, stop_after_runs: Optional[int] = None) -> None:
        """
        Run a simple long-polling loop against Telegram's getUpdates API.
        Useful for continuous execution in local development or standalone containers.
        """
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.warning("TELEGRAM_BOT_TOKEN not configured; polling cannot start.")
            return

        url = f"https://api.telegram.org/bot{token}/getUpdates"
        offset = 0
        runs = 0
        logger.info("Starting Telegram long-polling loop...")

        while True:
            try:
                resp = requests.get(url, params={"offset": offset, "timeout": 20}, timeout=25)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        offset = max(offset, update["update_id"] + 1)
                        self.process_update(update, send_reply=True)
                else:
                    logger.warning("Telegram getUpdates returned HTTP %d", resp.status_code)
            except Exception as e:
                logger.debug("Error in Telegram polling loop: %s", e)

            runs += 1
            if stop_after_runs and runs >= stop_after_runs:
                break
            time.sleep(interval_seconds)


if __name__ == "__main__":
    handler = TelegramConversationHandler()
    print("Scheme-Intel Telegram Conversational Handler ready.")
    handler.run_polling()
