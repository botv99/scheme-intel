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
        self.is_running = False

    def stop(self) -> None:
        """Signal the polling loop to terminate gracefully."""
        self.is_running = False
        logger.info("TelegramConversationHandler stop signal received.")

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
        if not text or not text.strip():
            return ""

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
        update_id = update.get("update_id")

        logger.info(
            "[TELEGRAM] Update received: update_id=%s, chat_id=%s, user_id=%s, text='%s'",
            update_id,
            chat_id,
            user_id,
            text[:50],
        )

        raw_response = self.router.route_message(text, user_id=user_id, chat_id=chat_id)
        chunks = chunk_message(raw_response, max_chars=4000)
        logger.info(
            "[TELEGRAM] Response generated: update_id=%s, length=%d, chunks=%d",
            update_id,
            len(raw_response),
            len(chunks),
        )

        if send_reply and chat_id and chunks:
            for idx, ch in enumerate(chunks):
                try:
                    success = send_telegram(ch, chat_ids=[chat_id], parse_mode="Markdown")
                    logger.info(
                        "[TELEGRAM] Reply dispatched: success=%s, chat_id=%s, chunk=%d/%d, len=%d",
                        success,
                        chat_id,
                        idx + 1,
                        len(chunks),
                        len(ch),
                    )
                except Exception as e:
                    logger.error("[TELEGRAM] Failed sending Telegram reply to chat %s: %s", chat_id, e)

        return raw_response

    def run_polling(
        self,
        interval_seconds: int = 2,
        stop_after_runs: Optional[int] = None,
        drop_pending_updates: bool = False,
    ) -> None:
        """
        Run a simple long-polling loop against Telegram's getUpdates API.
        Useful for continuous execution in local development or standalone containers.
        """
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.warning("[TELEGRAM] TELEGRAM_BOT_TOKEN not configured; polling cannot start.")
            return

        url = f"https://api.telegram.org/bot{token}/getUpdates"
        offset = 0
        runs = 0
        self.is_running = True

        if drop_pending_updates:
            try:
                flush_resp = requests.get(url, params={"offset": -1}, timeout=10)
                if flush_resp.status_code == 200:
                    for u in flush_resp.json().get("result", []):
                        offset = max(offset, u.get("update_id", 0) + 1)
                logger.info("[TELEGRAM] Dropped pending updates backlog. Starting offset=%s", offset)
            except Exception as flush_err:
                logger.debug("Failed flushing updates backlog: %s", flush_err)

        logger.info("[TELEGRAM] Starting Telegram long-polling loop (offset=%d)...", offset)

        while self.is_running:
            try:
                resp = requests.get(url, params={"offset": offset, "timeout": 20}, timeout=25)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        offset = max(offset, update.get("update_id", 0) + 1)
                        try:
                            self.process_update(update, send_reply=True)
                        except Exception as update_err:
                            logger.error("[TELEGRAM] Error processing Telegram update: %s", update_err)
                else:
                    logger.warning("[TELEGRAM] getUpdates returned HTTP %d", resp.status_code)
            except Exception as e:
                logger.debug("[TELEGRAM] Polling loop exception: %s", e)

            runs += 1
            if stop_after_runs and runs >= stop_after_runs:
                break
            if self.is_running:
                time.sleep(interval_seconds)

        logger.info("[TELEGRAM] Telegram long-polling loop terminated.")


if __name__ == "__main__":
    handler = TelegramConversationHandler()
    print("Scheme-Intel Telegram Conversational Handler ready.")
    handler.run_polling()
