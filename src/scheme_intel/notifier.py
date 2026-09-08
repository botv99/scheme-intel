"""
Enhanced notifier module with multi-chat support and error handling.
"""
from __future__ import annotations

import os
from typing import Optional

import requests

from .logger import get_logger
from .exceptions import TelegramError

logger = get_logger(__name__)


def send_telegram(message: str, chat_ids: Optional[list[str]] = None) -> bool:
    """
    Send message to one or more Telegram chats.
    
    Args:
        message: Message text to send
        chat_ids: List of chat IDs (if None, uses TELEGRAM_CHAT_ID env var)
        
    Returns:
        True if sent successfully, False otherwise
        
    Raises:
        TelegramError: If Telegram API call fails
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
        # Support comma-separated chat IDs
        chat_ids = [cid.strip() for cid in chat_id_env.split(",") if cid.strip()]
    
    if not chat_ids:
        logger.warning("No valid chat IDs provided")
        return False
    
    success_count = 0
    
    for chat_id in chat_ids:
        try:
            logger.debug(f"Sending Telegram message to chat {chat_id}")
            
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "disable_web_page_preview": True
                },
                timeout=20
            )
            
            response.raise_for_status()
            success_count += 1
            logger.info(f"Successfully sent message to chat {chat_id}")
            
        except requests.RequestException as e:
            logger.error(f"Failed to send message to chat {chat_id}: {str(e)[:200]}")
            raise TelegramError(f"Failed to send Telegram message: {str(e)}")
    
    return success_count == len(chat_ids)


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
