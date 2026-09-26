"""
Delivery Subsystem.
Covers daily Telegram alert dispatches and future conversational interfaces.
"""
from .telegram_alerts import dispatch_daily_report, chunk_message
from .telegram_cards import build_full_telegram_report
from .telegram_router import TelegramMessageRouter
from .telegram_conversation import TelegramConversationHandler

__all__ = [
    "dispatch_daily_report",
    "chunk_message",
    "build_full_telegram_report",
    "TelegramMessageRouter",
    "TelegramConversationHandler",
    "SchemeIntelService",
    "get_system_health",
]


def __getattr__(name: str):
    if name in ("SchemeIntelService", "get_system_health"):
        from .service import SchemeIntelService, get_system_health
        return {"SchemeIntelService": SchemeIntelService, "get_system_health": get_system_health}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
