"""
Financial-media news collector (Mint, Financial Express, Moneycontrol).

Uses RSS feeds where they exist and section-page scans where feeds have been
disabled (Financial Express disabled its RSS in 2025). Only stories that
mention a watchlist company (by name or alias) are kept.
"""
from __future__ import annotations

import re

from ..logger import get_logger
from ..models import Article
from ..sources import deduplicate_articles, fetch_rss, scan_page
from .models import MediaArticle

logger = get_logger(__name__)

DEFAULT_WATCH_WORDS = ["tender", "contract", "order", "award", "LOA"]


def _watch_terms(config: dict) -> tuple[list[str], list[str]]:
    """Return (aliases, sector keywords) used to match news for this watchlist."""
    aliases = list(config.get("scheme", {}).get("aliases", []))
    for stock in config.get("stocks", []):
        aliases.append(stock.get("name", ""))
        aliases.extend(stock.get("aliases", []))
    clean = [a for a in dict.fromkeys(a for a in aliases if a)]
    return clean


def _matches(article: Article, aliases: list[str]) -> list[str]:
    """Return the aliases mentioned in an article title/summary (word-bounded)."""
    text = f"{article.title} {article.summary}"
    found = []
    for alias in aliases:
        if re.search(rf"\b{re.escape(alias)}\b", text, re.IGNORECASE):
            found.append(alias)
    return found


def _media_article(article: Article, aliases: list[str]) -> MediaArticle | None:
    matched = _matches(article, aliases)
    if not matched:
        return None
    return MediaArticle(
        title=article.title,
        url=article.url,
        source=article.source,
        published_at=article.published_at.isoformat() if article.published_at else None,
        matched_stocks=matched,
        summary=article.summary,
    )


def _articles_from_rss(feed_url: str, source_name: str) -> list[Article]:
    """Small wrapper so feed failures surface as exceptions to the caller."""
    logger.info(f"Collecting news from {source_name} RSS: {feed_url}")
    return fetch_rss(source_name, feed_url)


def _articles_from_pages(pages: list[str], source_name: str, aliases: list[str]) -> list[Article]:
    articles: list[Article] = []
    for page in pages:
        logger.info(f"Scanning {source_name} page for watchlist mentions: {page}")
        articles.extend(scan_page(source_name, page, aliases))
    return articles


def collect_news(config: dict) -> tuple[list[dict], list[dict]]:
    """
    Collect news about watchlist stocks from the configured media sources.

    Args:
        config: Loaded watchlist configuration.

    Returns:
        (news_articles, source_errors)
    """
    source_errors: list[dict] = []
    collected: list[Article] = []
    aliases = _watch_terms(config)

    sources = config.get("ingestion", {}).get("news_sources", [])
    if not sources:
        return [], []

    for source in sources:
        name = source.get("name", "Unknown media source")
        try:
            rss_urls = source.get("rss")
            if isinstance(rss_urls, str):
                rss_urls = [rss_urls]
            if rss_urls:
                for rss_url in rss_urls:
                    collected.extend(_articles_from_rss(rss_url, name))
            pages = source.get("pages", [])
            if pages:
                collected.extend(_articles_from_pages(pages, name, aliases))
        except Exception as exc:
            logger.warning(f"Media source '{name}' failed: {str(exc)[:180]}")
            source_errors.append({"source": name, "error": str(exc)[:180]})

    deduped = deduplicate_articles(collected)
    matched = []
    for article in deduped:
        item = _media_article(article, aliases)
        if item:
            matched.append(item.to_dict())

    matched.sort(key=lambda a: a.get("published_at") or "", reverse=True)
    logger.info(f"Media news: {len(deduped)} unique articles, {len(matched)} match watchlist")
    return matched, source_errors