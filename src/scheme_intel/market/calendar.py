"""
Indian Market Trading Calendar and Session Determination.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Optional
from pydantic import BaseModel

IST_OFFSET = timezone(timedelta(hours=5, minutes=30))

NSE_HOLIDAYS_2026 = {
    "2026-01-26", "2026-02-17", "2026-03-03", "2026-03-20",
    "2026-03-24", "2026-04-03", "2026-04-14", "2026-05-01",
    "2026-05-28", "2026-06-17", "2026-07-27", "2026-08-15",
    "2026-09-04", "2026-10-02", "2026-10-20", "2026-11-08",
    "2026-11-24", "2026-12-25",
}

MARKET_CLOSE_TIME = time(15, 30)
ANALYSIS_WINDOW_START = time(15, 30)
ANALYSIS_WINDOW_END = time(18, 0)


class MarketSessionInfo(BaseModel):
    analysis_date: str
    market_close_timestamp: str
    setup_date: str
    next_trading_session: str
    is_trading_day: bool
    is_after_market_close: bool
    is_official_run_window: bool


def is_trading_day(dt: datetime) -> bool:
    if dt.weekday() in (5, 6):
        return False
    date_str = dt.strftime("%Y-%m-%d")
    return date_str not in NSE_HOLIDAYS_2026


def get_next_trading_session(after_date: datetime) -> datetime:
    cur = after_date + timedelta(days=1)
    while not is_trading_day(cur):
        cur += timedelta(days=1)
    return cur


def get_market_session_info(now_utc: Optional[datetime] = None) -> MarketSessionInfo:
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST_OFFSET)
    today = now_ist.date()
    today_dt = datetime(today.year, today.month, today.day, tzinfo=IST_OFFSET)
    is_today_trading = is_trading_day(today_dt)
    market_close = datetime.combine(today, MARKET_CLOSE_TIME).replace(tzinfo=IST_OFFSET)
    window_start = datetime.combine(today, ANALYSIS_WINDOW_START).replace(tzinfo=IST_OFFSET)
    window_end = datetime.combine(today, ANALYSIS_WINDOW_END).replace(tzinfo=IST_OFFSET)

    is_after_close = now_ist >= market_close
    is_official_window = window_start <= now_ist <= window_end

    if is_today_trading:
        if is_after_close:
            analysis_date = today_dt
            market_close_ts = market_close.isoformat()
            next_session_dt = get_next_trading_session(today_dt)
            setup_date = next_session_dt
        else:
            prev_session = today_dt - timedelta(days=1)
            while not is_trading_day(prev_session):
                prev_session -= timedelta(days=1)
            analysis_date = prev_session
            market_close_ts = datetime.combine(prev_session.date(), MARKET_CLOSE_TIME).replace(tzinfo=IST_OFFSET).isoformat()
            setup_date = today_dt
            next_session_dt = today_dt
    else:
        prev_session = today_dt - timedelta(days=1)
        while not is_trading_day(prev_session):
            prev_session -= timedelta(days=1)
        analysis_date = prev_session
        market_close_ts = datetime.combine(prev_session.date(), MARKET_CLOSE_TIME).replace(tzinfo=IST_OFFSET).isoformat()
        next_session_dt = get_next_trading_session(today_dt)
        setup_date = next_session_dt

    return MarketSessionInfo(
        analysis_date=analysis_date.strftime("%Y-%m-%d"),
        market_close_timestamp=market_close_ts,
        setup_date=setup_date.strftime("%Y-%m-%d"),
        next_trading_session=next_session_dt.strftime("%Y-%m-%d"),
        is_trading_day=is_today_trading,
        is_after_market_close=is_after_close,
        is_official_run_window=is_official_window,
    )
