"""
Enhanced sources module with error handling and source reliability tracking.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup

from .models import Article
from .logger import get_logger
from .exceptions import SourceAccessError, DataParseError

logger = get_logger(__name__)


def _date(value: str | None) -> datetime | None:
    """Parse date string to datetime object."""
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except (TypeError, ValueError) as e:
        logger.debug(f"Failed to parse date '{value}': {e}")
        return None


def fetch_rss(name: str, url: str, timeout: int = 25) -> list[Article]:
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
    try:
        logger.info(f"Fetching RSS from {name}: {url}")
        feed = feedparser.parse(url)
        
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


def scan_page(name: str, url: str, aliases: list[str], timeout: int = 25) -> list[Article]:
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
        
        response = requests.get(
            url, 
            timeout=timeout, 
            headers={"User-Agent": "scheme-intel/0.2"}
        )
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
