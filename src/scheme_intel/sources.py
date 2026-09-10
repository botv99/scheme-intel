"""
Enhanced sources module with error handling and source reliability tracking.
"""
from __future__ import annotations

import re
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import sleep
from typing import Optional
from urllib.parse import urlparse
from functools import wraps

import feedparser
import requests
from bs4 import BeautifulSoup

from .models import Article
from .logger import get_logger
from .exceptions import SourceAccessError, DataParseError

logger = get_logger(__name__)

# Configuration constants
DEFAULT_TIMEOUT = 25
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 1.0


def retry_on_failure(
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    retry_on_exceptions: tuple[type[Exception], ...] = (SourceAccessError,),
):
    """
    Decorator to retry a function on specified exceptions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        backoff_factor: Base delay between retries (seconds). Delay = backoff_factor * (2 ** attempt).
        retry_on_exceptions: Tuple of exception types that should trigger a retry.

    Returns:
        Decorated function that will retry on the given exceptions.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except retry_on_exceptions as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        delay = backoff_factor * (2 ** attempt)
                        logger.info(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                            f"after {delay}s: {e}"
                        )
                        sleep(delay)
                    else:
                        raise
            # Should not reach here
            raise last_exc
        return wrapper
    return decorator


def validate_url(url: str) -> bool:
    """
    Validate that a string is a well‑formed URL.

    Args:
        url: The URL string to validate.

    Returns:
        True if the URL has a scheme and a network location, False otherwise.
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def _date(value: str | None) -> datetime | None:
    """
    Parse date string to datetime object.

    Supports RFC 2822 (e.g., "Thu, 01 Jan 2026 12:00:00 GMT") and ISO 8601
    (e.g., "2026-01-01T12:00:00Z" or "2026-01-01T12:00:00+00:00").
    Returns None if parsing fails.
    """
    if not value:
        return None
    # Try RFC 2822 format
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    # Try ISO 8601 format
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except ValueError:
        pass
    logger.debug(f"Failed to parse date '{value}'")
    return None


@retry_on_failure()
def fetch_rss(name: str, url: str, timeout: int = DEFAULT_TIMEOUT) -> list[Article]:
    """
    Fetch articles from RSS feed.

    Args:
        name: Source name
        url: RSS feed URL
        timeout: Request timeout in seconds

    Returns:
        List of Article objects

    Raises:
        SourceAccessError: If feed cannot be accessed
        DataParseError: If feed parsing fails
    """
    start = logger.isEnabledFor(logging.INFO) and sleep(0)  # dummy to avoid unused variable warning
    try:
        logger.info(f"Fetching RSS from {name}: {url}")
        feed_start = datetime.now(timezone.utc)
        feed = feedparser.parse(url)
        feed_duration = (datetime.now(timezone.utc) - feed_start).total_seconds()
        logger.debug(f"RSS parse took {feed_duration:.2f}s for {name}")

        if feed.bozo and isinstance(feed.bozo_exception, Exception):
            logger.warning(f"RSS parsing warning for {name}: {feed.bozo_exception}")

        articles = [
            Article(
                entry.get("title", ""),
                entry.get("link", ""),
                name,
                _date(entry.get("published") or entry.get("updated")),
                entry.get("summary", "")
            )
            for entry in feed.entries
        ]

        logger.info(f"Successfully fetched {len(articles)} articles from {name}")
        return articles

    except Exception as e:
        logger.error(f"RSS fetch error for {name}: {str(e)[:200]}")
        raise SourceAccessError(f"Failed to fetch RSS from {name}: {str(e)}")


@retry_on_failure()
def scan_page(name: str, url: str, aliases: list[str], timeout: int = DEFAULT_TIMEOUT) -> list[Article]:
    """
    Scan web page for matching links.

    Args:
        name: Source name
        url: Page URL to scan
        aliases: Keywords to match in link titles
        timeout: Request timeout in seconds

    Returns:
        List of matching Article objects

    Raises:
        SourceAccessError: If page cannot be accessed
        DataParseError: If HTML parsing fails
    """
    try:
        logger.info(f"Scanning page from {name}: {url}")
        request_start = datetime.now(timezone.utc)

        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "scheme-intel/0.2"}
        )
        request_duration = (datetime.now(timezone.utc) - request_start).total_seconds()
        logger.debug(f"HTTP request to {url} took {request_duration:.2f}s")

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        found: list[Article] = []

        for link in soup.find_all("a", href=True):
            title = re.sub(r"\s+", " ", link.get_text(" ", strip=True))
            if title and any(term.lower() in title.lower() for term in aliases):
                found.append(
                    Article(
                        title,
                        requests.compat.urljoin(url, link["href"]),
                        name,
                        None
                    )
                )

        logger.info(f"Found {len(found)} matching articles from {name}")
        return found

    except requests.RequestException as e:
        logger.error(f"HTTP error scanning {name}: {str(e)[:200]}")
        raise SourceAccessError(f"Failed to access {name}: {str(e)}")
    except Exception as e:
        logger.error(f"Parse error scanning {name}: {str(e)[:200]}")
        raise DataParseError(f"Failed to parse {name}: {str(e)}")


def deduplicate_articles(articles: list[Article]) -> list[Article]:
    """
    Remove duplicate articles by URL.

    Args:
        articles: List of articles

    Returns:
        List of unique articles (by URL)
    """
    unique = {article.url: article for article in articles if article.url}
    logger.info(f"Deduplicated articles: {len(articles)} -> {len(unique)}")
    return list(unique.values())
