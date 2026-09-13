"""
Source reliability, cross-source corroboration, and sentiment analysis.

Combines three signals into a confidence score for each catalyst:
  1. Source credibility  — historical success rate of the originating source
  2. Cross-source corroboration — same story reported by multiple sources
  3. Sentiment polarity — positive/negative keyword signals in the article
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from .db import SchemeIntelDB
from .logger import get_logger
from .models import Article, Catalyst

logger = get_logger(__name__)

# ------------------------------------------------------------------
# Sentiment lexicon (sector-specific)
# ------------------------------------------------------------------

_POSITIVE_WORDS = frozenset([
    "approved", "approval", "awarded", "award", "commissioned", "commissioning",
    "released", "release", "inaugurated", "launched", "expanded", "expansion",
    "record", "surge", "growth", "profit", "profitable", "increase", "increased",
    "boost", "incentive", "subsidy", "grant", "funding", "investment",
    "partnership", "collaboration", "agreement", "mou", "contract",
    "order", "wins", "breakthrough", "milestone", "upgrade", "outperform",
    "bullish", "rally", "jump", "soar", "strong", "positive",
])

_NEGATIVE_WORDS = frozenset([
    "rejected", "rejection", "revoked", "cancelled", "cancellation",
    "delayed", "delay", "postponed", "suspended", "suspension",
    "defaulter", "default", "loss", "losses", "decline", "declined",
    "drop", "fell", "falling", "weakness", "weak", "negative",
    "penalty", "fine", "violation", "investigation", "scam", "fraud",
    "bankruptcy", "insolvency", "downgrade", "underperform", "bearish",
    "slump", "crash", "risk", "concern", "warning",
])

# ------------------------------------------------------------------
# Cross-source corroboration helpers
# ------------------------------------------------------------------


def _normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(a: str, b: str) -> float:
    """Quick sequence-matcher ratio between two normalised strings."""
    return SequenceMatcher(None, a, b).ratio()


def _articles_match(a: Article, b: Article, threshold: float = 0.72) -> bool:
    """Return True when two articles look like the same story."""
    if a.url and a.url == b.url:
        return True
    na = _normalise(f"{a.title} {a.summary}")
    nb = _normalise(f"{b.title} {b.summary}")
    return _similarity(na, nb) >= threshold


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@dataclass
class SentimentResult:
    positive: int = 0
    negative: int = 0
    net: float = 0.0
    label: str = "neutral"

    def to_dict(self) -> dict:
        return {"positive": self.positive, "negative": self.negative,
                "net": round(self.net, 2), "label": self.label}


@dataclass
class CorroborationGroup:
    """A cluster of articles that refer to the same story."""
    lead: Article
    sources: list[str] = field(default_factory=list)
    count: int = 0
    confidence_boost: float = 0.0

    def to_dict(self) -> dict:
        return {
            "lead_title": self.lead.title,
            "lead_url": self.lead.url,
            "sources": self.sources,
            "count": self.count,
            "confidence_boost": round(self.confidence_boost, 2),
        }


@dataclass
class SourceReliabilityScore:
    name: str
    success_count: int = 0
    error_count: int = 0
    reliability: float = 1.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "reliability": round(self.reliability, 2),
        }


@dataclass
class CatalystConfidence:
    """Final confidence breakdown for a single catalyst."""
    source_reliability: float = 1.0
    corroboration_count: int = 1
    corroboration_boost: float = 0.0
    sentiment: Optional[SentimentResult] = None
    base_score: int = 0
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "source_reliability": round(self.source_reliability, 2),
            "corroboration_count": self.corroboration_count,
            "corroboration_boost": round(self.corroboration_boost, 2),
            "sentiment": self.sentiment.to_dict() if self.sentiment else None,
            "base_score": self.base_score,
            "confidence": round(self.confidence, 2),
        }


# ------------------------------------------------------------------
# Core class
# ------------------------------------------------------------------


class SourceReliabilityTracker:
    """
    Tracks source credibility across runs and computes catalyst confidence
    using source reliability, cross-source corroboration, and sentiment.
    """

    def __init__(self, db: Optional[SchemeIntelDB] = None):
        self.db = db or SchemeIntelDB()
        self._source_cache: dict[str, SourceReliabilityScore] = {}
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = self.db.connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS source_reliability (
                name            TEXT PRIMARY KEY,
                success_count   INTEGER NOT NULL DEFAULT 0,
                error_count     INTEGER NOT NULL DEFAULT 0,
                last_updated    TEXT
            )
        """)
        conn.commit()

    # ------------------------------------------------------------------
    # Source reliability persistence
    # ------------------------------------------------------------------

    def record_success(self, source_name: str) -> None:
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO source_reliability (name, success_count, error_count, last_updated) "
            "VALUES (?, 1, 0, datetime('now')) "
            "ON CONFLICT(name) DO UPDATE SET success_count = success_count + 1, last_updated = datetime('now')",
            (source_name,),
        )
        conn.commit()
        self._source_cache.pop(source_name, None)

    def record_error(self, source_name: str) -> None:
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO source_reliability (name, success_count, error_count, last_updated) "
            "VALUES (?, 0, 1, datetime('now')) "
            "ON CONFLICT(name) DO UPDATE SET error_count = error_count + 1, last_updated = datetime('now')",
            (source_name,),
        )
        conn.commit()
        self._source_cache.pop(source_name, None)

    def get_source_score(self, source_name: str) -> SourceReliabilityScore:
        if source_name in self._source_cache:
            return self._source_cache[source_name]
        conn = self.db.connect()
        row = conn.execute(
            "SELECT success_count, error_count FROM source_reliability WHERE name = ?",
            (source_name,),
        ).fetchone()
        if row:
            total = row["success_count"] + row["error_count"]
            reliability = row["success_count"] / total if total else 1.0
            score = SourceReliabilityScore(source_name, row["success_count"], row["error_count"], reliability)
        else:
            score = SourceReliabilityScore(source_name)
        self._source_cache[source_name] = score
        return score

    def get_all_sources(self) -> list[SourceReliabilityScore]:
        conn = self.db.connect()
        rows = conn.execute("SELECT * FROM source_reliability ORDER BY name").fetchall()
        results = []
        for r in rows:
            total = r["success_count"] + r["error_count"]
            reliability = r["success_count"] / total if total else 1.0
            results.append(SourceReliabilityScore(r["name"], r["success_count"], r["error_count"], reliability))
        return results

    # ------------------------------------------------------------------
    # Sentiment analysis
    # ------------------------------------------------------------------

    @staticmethod
    def analyse_sentiment(text: str) -> SentimentResult:
        """Keyword-based sentiment analysis for financial news."""
        words = set(_normalise(text).split())
        pos = len(words & _POSITIVE_WORDS)
        neg = len(words & _NEGATIVE_WORDS)
        total = pos + neg
        net = (pos - neg) / total if total else 0.0
        if net > 0.2:
            label = "positive"
        elif net < -0.2:
            label = "negative"
        else:
            label = "neutral"
        return SentimentResult(positive=pos, negative=neg, net=net, label=label)

    # ------------------------------------------------------------------
    # Cross-source corroboration
    # ------------------------------------------------------------------

    def find_corroborations(self, articles: list[Article], threshold: float = 0.72) -> list[CorroborationGroup]:
        """
        Group articles that refer to the same story across different sources.
        """
        n = len(articles)
        visited = [False] * n
        groups: list[CorroborationGroup] = []

        for i in range(n):
            if visited[i]:
                continue
            visited[i] = True
            cluster = [articles[i]]
            for j in range(i + 1, n):
                if visited[j]:
                    continue
                if _articles_match(articles[i], articles[j], threshold):
                    visited[j] = True
                    cluster.append(articles[j])

            sources = list({a.source for a in cluster})
            count = len(cluster)
            # Boost: 0 for single source, +0.05 per additional unique source (max +0.25)
            boost = min(0.05 * (len(sources) - 1), 0.25) if len(sources) > 1 else 0.0
            groups.append(CorroborationGroup(
                lead=cluster[0],
                sources=sources,
                count=count,
                confidence_boost=boost,
            ))

        return groups

    # ------------------------------------------------------------------
    # Combined confidence
    # ------------------------------------------------------------------

    def compute_confidence(
        self,
        catalyst: Catalyst,
        all_articles: list[Article],
        threshold: float = 0.72,
    ) -> CatalystConfidence:
        """
        Compute a combined confidence score for a catalyst using:
          1. Source reliability (0.0–1.0)
          2. Cross-source corroboration boost (0–0.25)
          3. Sentiment alignment (±0.1)
        """
        # 1. Source reliability
        source_score = self.get_source_score(catalyst.article.source)
        source_rel = source_score.reliability

        # 2. Corroboration
        groups = self.find_corroborations(all_articles, threshold)
        matching = next(
            (g for g in groups if _articles_match(g.lead, catalyst.article, threshold)),
            None,
        )
        corrob_count = matching.count if matching else 1
        corrob_boost = matching.confidence_boost if matching else 0.0

        # 3. Sentiment
        sentiment_text = f"{catalyst.article.title} {catalyst.article.summary}"
        sentiment = self.analyse_sentiment(sentiment_text)
        # Positive sentiment adds up to +0.1; negative subtracts up to -0.1
        sentiment_adj = sentiment.net * 0.1

        # Combine: base catalyst score * reliability * (1 + corroboration) + sentiment
        base = catalyst.score
        confidence = base * source_rel * (1.0 + corrob_boost) + sentiment_adj
        confidence = max(0.0, min(100.0, confidence))

        return CatalystConfidence(
            source_reliability=source_rel,
            corroboration_count=corrob_count,
            corroboration_boost=corrob_boost,
            sentiment=sentiment,
            base_score=base,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    def score_catalysts(
        self,
        catalysts: list[Catalyst],
        all_articles: list[Article],
        threshold: float = 0.72,
    ) -> list[tuple[Catalyst, CatalystConfidence]]:
        """Score a list of catalysts and return (catalyst, confidence) pairs."""
        results = []
        for cat in catalysts:
            conf = self.compute_confidence(cat, all_articles, threshold)
            results.append((cat, conf))
            logger.info(
                "Catalyst '%s': base=%d, conf=%.1f (src=%.2f, corrob=%d, sent=%s)",
                cat.article.title[:50], cat.score, conf.confidence,
                conf.source_reliability, conf.corroboration_count,
                conf.sentiment.label if conf.sentiment else "n/a",
            )
        return results
