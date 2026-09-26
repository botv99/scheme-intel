"""
Delivery Subsystem.
Covers daily Telegram alert dispatches and future conversational interfaces.
"""
from .telegram_alerts import dispatch_daily_report, chunk_message
from .telegram_cards import TelegramCardBuilder, build_full_telegram_report

__all__ = [
    "dispatch_daily_report",
    "chunk_message",
    "TelegramCardBuilder",
    "build_full_telegram_report",
]
