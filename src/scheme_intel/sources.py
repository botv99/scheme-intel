from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests
from bs4 import BeautifulSoup

from .models import Article


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def fetch_rss(name: str, url: str) -> list[Article]:
    feed = feedparser.parse(url)
    return [
        Article(entry.get("title", ""), entry.get("link", ""), name,
                _date(entry.get("published") or entry.get("updated")), entry.get("summary", ""))
        for entry in feed.entries
    ]


def scan_page(name: str, url: str, aliases: list[str]) -> list[Article]:
    """Lightweight fallback for official pages without RSS; returns matching links only."""
    response = requests.get(url, timeout=25, headers={"User-Agent": "scheme-intel/0.1"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    found: list[Article] = []
    for link in soup.find_all("a", href=True):
        title = re.sub(r"\s+", " ", link.get_text(" ", strip=True))
        if title and any(term.lower() in title.lower() for term in aliases):
            found.append(Article(title, requests.compat.urljoin(url, link["href"]), name, None))
    return found


