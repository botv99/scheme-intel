"""
HTTP infrastructure utilities.
Provides resilient sessions with automatic retries and exponential backoff,
as well as credential masking for network endpoints.
"""
from __future__ import annotations

import re
from typing import Any, Optional, cast

import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

DEFAULT_RETRY_STATUSES = (429, 500, 502, 503, 504)


def create_retry_session(
    retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: tuple[int, ...] = DEFAULT_RETRY_STATUSES,
    headers: Optional[dict[str, str]] = None,
) -> requests.Session:
    """
    Create a requests.Session with urllib3 Retry adapter mounted.
    Automatically retries on transient connection errors, timeouts,
    and HTTP 429 / 5xx server errors with exponential backoff.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=cast(Any, retry_strategy))
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    if headers:
        session.headers.update(headers)
    return session


def mask_telegram_token(text: str, token: Optional[str] = None) -> str:
    """
    Mask Telegram bot token from URL paths, logs, or error strings.
    Replaces /bot<digits>:<token_secret>/ with /bot***:***.
    """
    if not text:
        return ""
    if token and len(token) > 5:
        text = text.replace(token, "***")
    # Matches Telegram bot URLs such as /bot123456789:ABCdefGh-IJKlmNo/
    text = re.sub(r"/bot\d+:[A-Za-z0-9_-]+", "/bot***:***", text)
    text = re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot***:***", text)
    return text
