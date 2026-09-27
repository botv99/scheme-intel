"""
Telegram Conversational Interface & Gateway (Stage 3).
Provides unified request handling, webhook conflict checks, update deduplication,
interactive callback queries, and long-polling runner.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
import requests

from .telegram_router import TelegramMessageRouter
from .telegram_alerts import chunk_message
from .request_store import RequestStore
from ..intelligence_memory.cards import get_terminal_inline_keyboard
from ..notifier import send_telegram
from ..logger import get_logger
from ..core.http import mask_telegram_token

logger = get_logger(__name__)

STAGE_3_READY = True


def check_webhook_conflict(token: str) -> Optional[str]:
    """
    Check if a webhook is currently configured on Telegram for this bot.
    Returns webhook URL if conflict detected, or None if webhook is not set.
    """
    if not token:
        return None
    try:
        url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("result", {})
            if isinstance(data, dict):
                webhook_url = data.get("url", "").strip()
                if webhook_url:
                    return webhook_url
    except Exception as e:
        logger.warning("[TELEGRAM] Could not verify webhook status: %s", mask_telegram_token(str(e), token))
    return None


def register_bot_commands(token: str) -> bool:
    """Register bot command menu via Telegram setMyCommands API."""
    if not token:
        return False
    commands = [
        {"command": "start", "description": "Terminal main menu & shortcuts"},
        {"command": "help", "description": "Command guide & query examples"},
        {"command": "stock", "description": "Stock intelligence card (/stock <SYM>)"},
        {"command": "setups", "description": "Today's qualified setups"},
        {"command": "watchlist", "description": "Monitored scheme watchlist"},
    ]
    try:
        url = f"https://api.telegram.org/bot{token}/setMyCommands"
        resp = requests.post(url, json={"commands": commands}, timeout=10)
        if resp.status_code == 200 and resp.json().get("ok"):
            logger.info("[TELEGRAM] Successfully registered %d bot commands with Telegram API.", len(commands))
            return True
        else:
            logger.warning("[TELEGRAM] Failed registering bot commands: %s", resp.text[:150])
    except Exception as e:
        logger.warning("[TELEGRAM] Error registering bot commands: %s", e)
    return False


def answer_callback_query(token: str, callback_query_id: str) -> bool:
    """Acknowledge Telegram callback query to dismiss loading indicator."""
    if not token or not callback_query_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
        resp = requests.post(url, json={"callback_query_id": callback_query_id}, timeout=5)
        return resp.status_code == 200 and resp.json().get("ok", False)
    except Exception as e:
        logger.debug("[TELEGRAM] Error answering callback query: %s", e)
        return False


class TelegramConversationHandler:
    """Entry point and gateway for handling conversational Telegram queries."""

    def __init__(self, router: Optional[TelegramMessageRouter] = None):
        self.router = router or TelegramMessageRouter()
        self.is_running = False
        self.last_update_id: Optional[int] = None
        self.last_poll_time: Optional[float] = None
        self.processed_count: int = 0

    def stop(self) -> None:
        """Signal the polling loop to terminate gracefully."""
        self.is_running = False
        logger.info("TelegramConversationHandler stop signal received.")

    def get_metrics(self) -> Dict[str, Any]:
        """Return runtime polling telemetry metrics."""
        return {
            "is_running": self.is_running,
            "last_update_id": self.last_update_id,
            "last_poll_time": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.last_poll_time))
                if self.last_poll_time
                else None
            ),
            "processed_count": self.processed_count,
        }

    def handle_message(
        self,
        text: str,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        username: Optional[str] = None,
        update_id: Optional[int] = None,
    ) -> str:
        """
        Process user message and return the formatted response.
        Handles message chunking if response exceeds Telegram limit.
        """
        if not text or not text.strip():
            return ""

        raw_response = self.router.route_message(
            text=text,
            user_id=user_id,
            chat_id=chat_id,
            username=username,
            update_id=update_id,
        )
        chunks = chunk_message(raw_response, max_chars=4000)
        return chunks[0] if chunks else ""

    def process_update(self, update: Dict[str, Any], send_reply: bool = True) -> Optional[str]:
        """Process a raw Telegram update dictionary (Message or CallbackQuery)."""
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        update_id = update.get("update_id")

        # 1. Idempotency Check
        if update_id is not None:
            self.last_update_id = update_id
        if update_id is not None and self.router.request_store.is_duplicate_update(update_id):
            logger.info("[TELEGRAM] Skipping duplicate update_id=%s", update_id)
            return None
        self.processed_count += 1

        # 2. Extract Message or CallbackQuery
        text: str = ""
        user_id: Optional[str] = None
        chat_id: Optional[str] = None
        username: Optional[str] = None
        is_start_cmd = False

        if "callback_query" in update:
            cb = update["callback_query"]
            cb_id = cb.get("id")
            if cb_id and token:
                answer_callback_query(token, cb_id)

            text = cb.get("data", "").strip()
            user_info = cb.get("from", {})
            user_id = str(user_info.get("id")) if user_info.get("id") else None
            username = user_info.get("username")
            msg_info = cb.get("message", {})
            chat_info = msg_info.get("chat", {})
            chat_id = str(chat_info.get("id")) if chat_info.get("id") else None

        elif "message" in update or "edited_message" in update:
            msg = update.get("message") or update.get("edited_message", {})
            text = msg.get("text", "").strip()
            user_info = msg.get("from", {})
            user_id = str(user_info.get("id")) if user_info.get("id") else None
            username = user_info.get("username")
            chat_info = msg.get("chat", {})
            chat_id = str(chat_info.get("id")) if chat_info.get("id") else None
        else:
            return None

        if not text:
            return None

        if text.lower().startswith("/start"):
            is_start_cmd = True

        request_id = self.router.request_store.generate_request_id()
        logger.info("[TELEGRAM] Update received: update_id=%s", update_id)
        logger.info(
            "[TELEGRAM] Message received: chat_id=%s, user_id=%s, username=%s, text='%s'",
            chat_id,
            user_id,
            username,
            text[:50],
        )

        # 3. Route Query
        raw_response = self.router.route_message(
            text=text,
            user_id=user_id,
            chat_id=chat_id,
            username=username,
            update_id=update_id,
            request_id=request_id,
        )
        chunks = chunk_message(raw_response, max_chars=4000)

        # 4. Dispatch Reply Strictly to Originating chat_id
        if send_reply and chat_id and chunks:
            reply_markup = get_terminal_inline_keyboard() if is_start_cmd else None
            for idx, ch in enumerate(chunks):
                try:
                    success = send_telegram(
                        ch,
                        chat_ids=[chat_id],
                        parse_mode="Markdown",
                        reply_markup=reply_markup if idx == 0 else None,
                        request_id=request_id,
                    )
                    logger.info(
                        "[TELEGRAM] Response sent: request_id=%s, chat_id=%s, success=%s, chunk=%d/%d, len=%d",
                        request_id,
                        chat_id,
                        success,
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
        Run continuous long-polling loop against Telegram's getUpdates API.
        Verifies webhooks and registers bot commands on startup.
        """
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.warning("[TELEGRAM] TELEGRAM_BOT_TOKEN not configured; polling cannot start.")
            return

        logger.info("[TELEGRAM] Gateway starting")

        # 1. Webhook Conflict Detection
        webhook_conflict = check_webhook_conflict(token)
        if webhook_conflict:
            del_webhook = os.getenv("TELEGRAM_DELETE_WEBHOOK", "").lower() in ("true", "1")
            if del_webhook:
                logger.info("[TELEGRAM] Deleting conflicting webhook per TELEGRAM_DELETE_WEBHOOK=true configuration...")
                try:
                    del_resp = requests.post(f"https://api.telegram.org/bot{token}/deleteWebhook", json={"drop_pending_updates": False}, timeout=10)
                    if del_resp.status_code == 200:
                        logger.info("[TELEGRAM] Webhook status: CLEAN (removed '%s')", webhook_conflict)
                except Exception as del_err:
                    logger.error("[TELEGRAM] Failed removing webhook: %s", mask_telegram_token(str(del_err), token))
            else:
                logger.error("[TELEGRAM] Webhook status: CONFLICT ('%s')", webhook_conflict)
                return
        else:
            logger.info("[TELEGRAM] Webhook status: CLEAN")

        # 2. Authenticate Bot Identity
        try:
            me_resp = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
            if me_resp.status_code == 200 and me_resp.json().get("ok"):
                username = me_resp.json().get("result", {}).get("username", "unknown")
                logger.info("[TELEGRAM] Bot authenticated: @%s", username)
            else:
                logger.warning("[TELEGRAM] Bot authentication check returned HTTP %d: %s", me_resp.status_code, me_resp.text[:100])
        except Exception as auth_err:
            logger.warning("[TELEGRAM] Error during bot authentication check: %s", mask_telegram_token(str(auth_err), token))

        # 3. Register Telegram Menu Commands
        register_bot_commands(token)

        # 3. Explicit Required Startup Logs
        logger.info("[TELEGRAM] Gateway started")
        logger.info("[TELEGRAM] Polling active")
        logger.info("[TELEGRAM] Worker active")
        logger.info("[TELEGRAM] Snapshot available")
        logger.info("[TELEGRAM] Polling started")

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

        backoff_seconds = 2
        while self.is_running:
            self.last_poll_time = time.time()
            try:
                resp = requests.get(url, params={"offset": offset, "timeout": 20}, timeout=25)
                if resp.status_code == 200:
                    backoff_seconds = 2
                    data = resp.json()
                    for update in data.get("result", []):
                        offset = max(offset, update.get("update_id", 0) + 1)
                        try:
                            self.process_update(update, send_reply=True)
                        except Exception as update_err:
                            logger.exception("[TELEGRAM] Error processing Telegram update: %s", update_err)
                elif resp.status_code == 409:
                    logger.warning("[TELEGRAM] getUpdates returned HTTP 409 (Conflict). Backing off %ds...", backoff_seconds)
                    time.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 2, 30)
                elif resp.status_code == 429:
                    retry_after = 5
                    try:
                        retry_after = int(resp.json().get("parameters", {}).get("retry_after", 5))
                    except Exception:
                        pass
                    logger.warning("[TELEGRAM] getUpdates rate-limited (HTTP 429). Sleeping %ds...", retry_after)
                    time.sleep(retry_after)
                else:
                    logger.warning("[TELEGRAM] getUpdates returned HTTP %d: %s", resp.status_code, resp.text[:150])
                    time.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 2, 30)
            except requests.RequestException as req_err:
                logger.warning("[TELEGRAM] Network error in polling loop (%s). Retrying in %ds...", req_err, backoff_seconds)
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 30)
            except Exception as e:
                logger.exception("[TELEGRAM] Unexpected exception in polling loop: %s", e)
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 30)

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
