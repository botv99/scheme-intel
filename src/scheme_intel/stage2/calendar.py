"""
Indian Equity Market Calendar & Timing Engine for Stage 2.
Enforces the 16:30 IST after-market execution window and calculates
the authoritative NEXT TRADING SESSION (skipping weekends and NSE holidays).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Set, Optional, Tuple
from zoneinfo import ZoneInfo
from pydantic import BaseModel
from ..logger import get_logger

logger = get_logger(__name__)

# Indian Standard Time
IST = ZoneInfo("Asia/Kolkata")

# NSE / BSE Market Timing
MARKET_CLOSE_TIME = time(15, 30)  # 3:30 PM IST
OFFICIAL_ANALYSIS_START_TIME = time(16, 30)  # 4:30 PM IST

# Indian Stock Exchange (NSE/BSE) Trading Holidays (2024, 2025, 2026)
NSE_HOLIDAYS: Set[date] = {
    # 2024
    date(2024, 1, 26),   # Republic Day
    date(2024, 3, 8),    # Mahashivratri
    date(2024, 3, 25),   # Holi
    date(2024, 3, 29),   # Good Friday
    date(2024, 4, 11),   # Id-Ul-Fitr
    date(2024, 4, 17),   # Ram Navami
    date(2024, 5, 1),    # Maharashtra Day
    date(2024, 6, 17),   # Bakri Id
    date(2024, 7, 17),   # Muharram
    date(2024, 8, 15),   # Independence Day
    date(2024, 10, 2),   # Mahatma Gandhi Jayanti
    date(2024, 11, 1),   # Diwali Laxmi Pujan
    date(2024, 11, 15),  # Gurunanak Jayanti
    date(2024, 12, 25),  # Christmas
    # 2025
    date(2025, 1, 26),   # Republic Day
    date(2025, 2, 26),   # Mahashivratri
    date(2025, 3, 14),   # Holi
    date(2025, 3, 31),   # Id-Ul-Fitr
    date(2025, 4, 10),   # Mahavir Jayanti
    date(2025, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 1),    # Maharashtra Day
    date(2025, 8, 15),   # Independence Day
    date(2025, 8, 27),   # Ganesh Chaturthi
    date(2025, 10, 2),   # Mahatma Gandhi Jayanti
    date(2025, 10, 21),  # Diwali Laxmi Pujan
    date(2025, 10, 22),  # Diwali Balipratipada
    date(2025, 11, 5),   # Gurunanak Jayanti
    date(2025, 12, 25),  # Christmas
    # 2026
    date(2026, 1, 26),   # Republic Day
    date(2026, 2, 17),   # Mahashivratri
    date(2026, 3, 4),    # Holi
    date(2026, 3, 20),   # Id-Ul-Fitr
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 5, 28),   # Bakri Id
    date(2026, 6, 26),   # Muharram
    date(2026, 8, 15),   # Independence Day
    date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra
    date(2026, 11, 8),   # Diwali Laxmi Pujan
    date(2026, 11, 24),  # Gurunanak Jayanti
    date(2026, 12, 25),  # Christmas
}


class MarketSessionInfo(BaseModel):
    analysis_date: str                     # e.g. "2026-09-23"
    market_close_timestamp: str            # e.g. "2026-09-23T15:30:00+05:30"
    setup_date: str                        # e.g. "2026-09-24" (or next Monday if Friday)
    next_trading_session: str              # Formatted session name
    is_trading_day: bool                   # True if analysis_date was an active market day
    is_after_market_close: bool            # True if executed >= 15:30 IST
    is_official_run_window: bool           # True if executed >= 16:30 IST


def is_trading_day(d: date) -> bool:
    """Returns True if date is a weekday (Mon-Fri) and not an NSE holiday."""
    if d.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    return d not in NSE_HOLIDAYS


def get_next_trading_day(start_date: date | str) -> date:
    """
    Compute the next active trading day skipping weekends and NSE holidays.
    Never assumes tomorrow is simply +1 calendar day.
    """
    if isinstance(start_date, str):
        curr = date.fromisoformat(start_date)
    else:
        curr = start_date

    next_day = curr + timedelta(days=1)
    while not is_trading_day(next_day):
        next_day += timedelta(days=1)
    return next_day


def get_market_session_info(now_dt: Optional[datetime] = None) -> MarketSessionInfo:
    """
    Evaluate current time in IST to determine authoritative session metadata:
    - analysis_date: Date of the completed market session
    - market_close_timestamp: 15:30 IST for the completed session
    - setup_date: Next active trading day
    - next_trading_session: Descriptive next session label
    """
    if now_dt is None:
        now_ist = datetime.now(IST)
    elif now_dt.tzinfo is None:
        now_ist = now_dt.replace(tzinfo=IST)
    else:
        now_ist = now_dt.astimezone(IST)

    current_date = now_ist.date()
    current_time = now_ist.time()

    is_today_trading = is_trading_day(current_date)
    is_after_close = current_time >= MARKET_CLOSE_TIME
    is_official_window = current_time >= OFFICIAL_ANALYSIS_START_TIME

    # If it's a trading day and after close, analysis_date is today.
    # If it's a weekend or holiday, analysis_date is the most recent trading day.
    if is_today_trading and is_after_close:
        analysis_date = current_date
    elif is_today_trading and not is_after_close:
        # Before market close, completed session is the PREVIOUS trading day
        prev = current_date - timedelta(days=1)
        while not is_trading_day(prev):
            prev -= timedelta(days=1)
        analysis_date = prev
    else:
        # Weekend or holiday: find most recent trading day
        prev = current_date - timedelta(days=1)
        while not is_trading_day(prev):
            prev -= timedelta(days=1)
        analysis_date = prev

    next_session_date = get_next_trading_day(analysis_date)
    market_close_dt = datetime.combine(analysis_date, MARKET_CLOSE_TIME, tzinfo=IST)

    day_name = next_session_date.strftime("%A")
    formatted_next = f"{next_session_date.strftime('%d %b %Y')} ({day_name})"

    return MarketSessionInfo(
        analysis_date=analysis_date.isoformat(),
        market_close_timestamp=market_close_dt.isoformat(),
        setup_date=next_session_date.isoformat(),
        next_trading_session=formatted_next,
        is_trading_day=is_today_trading,
        is_after_market_close=is_after_close,
        is_official_run_window=is_official_window,
    )
