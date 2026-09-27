"""
Enhanced notifier module with multi-chat support, alert levels,
deduplication via SQLite, and retry handling.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests

from .db import SchemeIntelDB
from .logger import get_logger
from .exceptions import TelegramError
from .core.http import mask_telegram_token

logger = get_logger(__name__)

# Alert Levels
LEVEL_INFO = "INFO"
LEVEL_QUALIFIED = "QUALIFIED"
LEVEL_CRITICAL = "CRITICAL"


def send_telegram(
    message: str,
    chat_ids: Optional[list[str]] = None,
    max_retries: int = 3,
    parse_mode: Optional[str] = "HTML",
    reply_markup: Optional[dict] = None,
    request_id: Optional[str] = None,
) -> bool:
    """
    Send message to one or more Telegram chats with retry capability.

    Args:
        message: Message text to send
        chat_ids: List of chat IDs (if None, uses TELEGRAM_CHAT_ID env var)
        max_retries: Number of retry attempts on failure
        parse_mode: HTML or Markdown
        reply_markup: Optional Telegram inline or reply keyboard dictionary
        request_id: Optional tracking request ID for structured logging

    Returns:
        True if sent successfully, False otherwise

    Raises:
        TelegramError: If Telegram API call fails after all retries
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not configured - skipping Telegram send")
        return False

    # Parse chat IDs from env var if not provided
    if chat_ids is None:
        chat_id_env = os.getenv("TELEGRAM_CHAT_ID", "")
        if not chat_id_env:
            logger.warning("TELEGRAM_CHAT_ID not configured - skipping Telegram send")
            return False
        chat_ids = [cid.strip() for cid in chat_id_env.split(",") if cid.strip()]

    if not chat_ids:
        logger.warning("No valid chat IDs provided")
        return False

    success_count = 0

    for chat_id in chat_ids:
        sent = False
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.debug("Sending Telegram message to chat %s (attempt %d/%d)", chat_id, attempt, max_retries)

                payload: dict[str, Any] = {
                    "chat_id": chat_id,
                    "text": message,
                    "disable_web_page_preview": True,
                }
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                if reply_markup:
                    payload["reply_markup"] = reply_markup

                response = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json=payload,
                    timeout=20,
                )

                # Check if Telegram returned an entity parse error (HTTP 400)
                if response.status_code == 400 and parse_mode:
                    try:
                        err_data = response.json()
                        err_desc = err_data.get("description", "")
                    except Exception:
                        err_desc = response.text
                    if "can't parse entities" in err_desc.lower() or "entity" in err_desc.lower():
                        logger.warning(
                            "[TELEGRAM] Entity parse error with parse_mode='%s' (%s). Retrying as plain text...",
                            parse_mode,
                            err_desc,
                        )
                        payload.pop("parse_mode", None)
                        response = requests.post(
                            f"https://api.telegram.org/bot{token}/sendMessage",
                            json=payload,
                            timeout=20,
                        )

                response.raise_for_status()

                # Validate response JSON body
                try:
                    res_json = response.json()
                    if not res_json.get("ok", True):
                        err_msg = res_json.get("description", "Unknown Telegram rejection")
                        raise TelegramError(f"Telegram API rejected message: {err_msg}")
                except ValueError:
                    pass

                success_count += 1
                sent = True
                logger.info(
                    "[TELEGRAM SEND] request_id=%s chat_id=%s success=true len=%d",
                    request_id or "NONE",
                    chat_id,
                    len(message),
                )
                break

            except requests.RequestException as e:
                last_exc = e
                clean_err = mask_telegram_token(str(e), token)[:150]
                logger.warning("Attempt %d failed sending to %s: %s", attempt, chat_id, clean_err)
                if attempt < max_retries:
                    time.sleep(0.5 * (2 ** (attempt - 1)))
            except TelegramError as e:
                last_exc = e
                clean_err = mask_telegram_token(str(e), token)
                logger.warning("Attempt %d Telegram rejection for %s: %s", attempt, chat_id, clean_err)
                if attempt < max_retries:
                    time.sleep(0.5 * (2 ** (attempt - 1)))

        if not sent:
            clean_last_exc = mask_telegram_token(str(last_exc), token)
            logger.error(
                "[TELEGRAM SEND] request_id=%s chat_id=%s success=false after %d attempts: %s",
                request_id or "NONE",
                chat_id,
                max_retries,
                clean_last_exc,
            )
            raise TelegramError(f"Failed to send Telegram message: {clean_last_exc}")

    return success_count == len(chat_ids)


def send_alert(
    message: str,
    alert_key: Optional[str] = None,
    level: str = LEVEL_INFO,
    db: Optional[SchemeIntelDB] = None,
    chat_ids: Optional[list[str]] = None,
    max_retries: int = 3,
) -> bool:
    """
    Send an alert with level tagging and stateful deduplication via SQLite.
    If alert_key was already sent, sending is skipped.
    """
    # 1. Deduplication check
    if alert_key and db:
        if db.is_alert_sent(alert_key):
            logger.info("Duplicate alert suppressed for key: %s", alert_key)
            return True

    # 2. Add header tag based on level
    header = ""
    if level == LEVEL_CRITICAL:
        header = "🚨 <b>[CRITICAL CATALYST]</b>\n"
    elif level == LEVEL_QUALIFIED:
        header = "🎯 <b>[QUALIFIED SETUP]</b>\n"

    final_msg = f"{header}{message}" if header and not message.startswith("🚨") and not message.startswith("🎯") else message

    # 3. Dispatch
    sent = send_telegram(final_msg, chat_ids=chat_ids, max_retries=max_retries)

    # 4. Record state
    if sent and alert_key and db:
        chat_id_label = ",".join(chat_ids) if chat_ids else os.getenv("TELEGRAM_CHAT_ID", "")
        db.record_alert(alert_key=alert_key, level=level, message=message, chat_id=chat_id_label)

    return sent


def validate_telegram_config() -> bool:
    """
    Validate that Telegram configuration is properly set.

    Returns:
        True if configuration is valid, False otherwise
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        logger.info("Telegram configuration validated")
        return True

    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is not set")
    if not chat_id:
        logger.warning("TELEGRAM_CHAT_ID is not set")

    return False


def format_daily_digest(
    date_str: str,
    catalysts: list[dict],
    setups: list[dict],
    summary: str = "",
) -> str:
    """Format daily pipeline activity into a concise Telegram summary message."""
    lines = [
        f"🌾 <b>Scheme-Intel Daily Briefing — {date_str}</b>",
        f"<i>GOBARdhan / SATAT / Bio-Energy Intelligence</i>",
        "",
    ]
    if summary:
        lines.append(f"📌 {summary}")
        lines.append("")

    lines.append(f"📊 <b>Catalysts Detected:</b> {len(catalysts)}")
    for c in catalysts[:5]:
        headline = c.get("headline") or c.get("title", "")
        score = c.get("score", 0)
        lines.append(f"• [{score}/100] {headline[:75]}")

    lines.append("")
    lines.append(f"🎯 <b>Swing Setups Generated:</b> {len(setups)}")
    qualified = [s for s in setups if s.get("status") == "QUALIFIED"]
    lines.append(f"• Qualified: {len(qualified)} | Watchlist: {len(setups) - len(qualified)}")

    for s in qualified[:3]:
        lines.append(f"  👉 <b>{s['company']}</b> ({s['symbol']}): Entry ₹{s['entry']}, Target ₹{s['target']}, SL ₹{s['stop']}")

    lines.append("")
    lines.append("⚠️ <i>Automated scan. Not financial advice. Always verify filings.</i>")
    return "\n".join(lines)
