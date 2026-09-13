"""Tests for the source reliability, corroboration, and sentiment module."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.scheme_intel.db import SchemeIntelDB
from src.scheme_intel.models import Article, Catalyst
from src.scheme_intel.reliability import (
    SourceReliabilityTracker,
    SentimentResult,
    CorroborationGroup,
    CatalystConfidence,
    _normalise,
    _similarity,
    _articles_match,
)


def _article(title: str, source: str = "Mint", url: str = "", summary: str = "") -> Article:
    return Article(title=title, url=url or f"https://example.com/{title[:20]}", source=source,
                   published_at=datetime.now(timezone.utc), summary=summary)


def _catalyst(title: str, score: int = 80, source: str = "Mint") -> Catalyst:
    art = _article(title, source)
    return Catalyst(art, score, "test", "test rationale", ("TestCo",))


@pytest.fixture
def db(tmp_path: Path):
    path = tmp_path / "test_rel.db"
    scheme_db = SchemeIntelDB(db_path=path)
    yield scheme_db
    scheme_db.close()


@pytest.fixture
def tracker(db: SchemeIntelDB):
    return SourceReliabilityTracker(db=db)


# ------------------------------------------------------------------
# Normalise / similarity
# ------------------------------------------------------------------


class TestNormalise:
    def test_lowercases(self):
        assert _normalise("HELLO World") == "hello world"

    def test_strips_punctuation(self):
        assert _normalise("Cabinet approved!") == "cabinet approved"

    def test_collapses_whitespace(self):
        assert _normalise("  hello   world  ") == "hello world"


class TestSimilarity:
    def test_identical(self):
        assert _similarity("hello world", "hello world") == 1.0

    def test_similar(self):
        assert _similarity("cabinet approved for CBG", "cabinet approved for cbg scheme") > 0.7

    def test_different(self):
        assert _similarity("hello world", "completely different text") < 0.4


class TestArticlesMatch:
    def test_same_url(self):
        a = _article("Test", url="https://example.com/1")
        b = _article("Other", url="https://example.com/1")
        assert _articles_match(a, b)

    def test_similar_titles(self):
        a = _article("Praj wins CBG contract worth Rs 300 crore", summary="Order from GAIL")
        b = _article("Praj Industries wins CBG contract worth Rs 300 crore", summary="Order from GAIL Ltd")
        assert _articles_match(a, b, threshold=0.70)

    def test_different_articles(self):
        a = _article("Praj wins contract")
        b = _article("IOC reports quarterly results")
        assert not _articles_match(a, b)


# ------------------------------------------------------------------
# Source reliability persistence
# ------------------------------------------------------------------


class TestSourceReliability:
    def test_default_reliability(self, tracker: SourceReliabilityTracker):
        score = tracker.get_source_score("Unknown Source")
        assert score.reliability == 1.0
        assert score.success_count == 0

    def test_record_success(self, tracker: SourceReliabilityTracker):
        tracker.record_success("Mint")
        tracker.record_success("Mint")
        score = tracker.get_source_score("Mint")
        assert score.success_count == 2
        assert score.reliability == 1.0

    def test_record_error(self, tracker: SourceReliabilityTracker):
        tracker.record_error("PIB")
        score = tracker.get_source_score("PIB")
        assert score.error_count == 1
        assert score.reliability == 0.0

    def test_mixed_success_and_error(self, tracker: SourceReliabilityTracker):
        tracker.record_success("Mint")
        tracker.record_success("Mint")
        tracker.record_error("Mint")
        score = tracker.get_source_score("Mint")
        assert score.success_count == 2
        assert score.error_count == 1
        assert score.reliability == pytest.approx(0.67, abs=0.01)

    def test_persists_across_instances(self, db: SchemeIntelDB):
        t1 = SourceReliabilityTracker(db=db)
        t1.record_success("Livemint")
        t1.record_success("Livemint")
        t2 = SourceReliabilityTracker(db=db)
        score = t2.get_source_score("Livemint")
        assert score.success_count == 2

    def test_get_all_sources(self, tracker: SourceReliabilityTracker):
        tracker.record_success("Mint")
        tracker.record_error("PIB")
        all_sources = tracker.get_all_sources()
        assert len(all_sources) == 2
        names = {s.name for s in all_sources}
        assert "Mint" in names
        assert "PIB" in names


# ------------------------------------------------------------------
# Sentiment analysis
# ------------------------------------------------------------------


class TestSentiment:
    def test_positive(self):
        result = SourceReliabilityTracker.analyse_sentiment(
            "Cabinet approves funds released for CBG expansion"
        )
        assert result.positive > 0
        assert result.label == "positive"

    def test_negative(self):
        result = SourceReliabilityTracker.analyse_sentiment(
            "Project delayed due to investigation and penalty warning"
        )
        assert result.negative > 0
        assert result.label == "negative"

    def test_neutral(self):
        result = SourceReliabilityTracker.analyse_sentiment(
            "The company held a meeting today"
        )
        assert result.label == "neutral"

    def test_empty(self):
        result = SourceReliabilityTracker.analyse_sentiment("")
        assert result.label == "neutral"
        assert result.positive == 0
        assert result.negative == 0

    def test_net_calculation(self):
        result = SourceReliabilityTracker.analyse_sentiment("approved growth profit")
        assert result.net > 0
        assert result.positive == 3


# ------------------------------------------------------------------
# Cross-source corroboration
# ------------------------------------------------------------------


class TestCorroboration:
    def test_single_article(self, tracker: SourceReliabilityTracker):
        articles = [_article("Praj wins CBG contract")]
        groups = tracker.find_corroborations(articles)
        assert len(groups) == 1
        assert groups[0].count == 1
        assert groups[0].confidence_boost == 0.0

    def test_corroborated_articles(self, tracker: SourceReliabilityTracker):
        a1 = _article("Praj wins CBG contract from GAIL", source="Mint")
        a2 = _article("Praj Industries wins CBG contract from GAIL", source="ET")
        a3 = _article("Praj awarded CBG contract by GAIL", source="Moneycontrol")
        groups = tracker.find_corroborations([a1, a2, a3], threshold=0.60)
        # All three should be grouped together
        assert len(groups) == 1
        assert groups[0].count == 3
        assert len(groups[0].sources) == 3
        assert groups[0].confidence_boost > 0

    def test_different_stories(self, tracker: SourceReliabilityTracker):
        a1 = _article("Praj wins contract", source="Mint")
        a2 = "IOC quarterly results announced"
        a2_art = _article(a2, source="ET")
        groups = tracker.find_corroborations([a1, a2_art], threshold=0.72)
        assert len(groups) == 2

    def test_same_url_deduplicates(self, tracker: SourceReliabilityTracker):
        a1 = _article("Praj wins", url="https://example.com/1", source="Mint")
        a2 = _article("Praj wins big", url="https://example.com/1", source="ET")
        groups = tracker.find_corroborations([a1, a2])
        assert len(groups) == 1
        assert groups[0].count == 2


# ------------------------------------------------------------------
# Confidence scoring
# ------------------------------------------------------------------


class TestConfidence:
    def test_high_reliability_boosts_confidence(self, tracker: SourceReliabilityTracker):
        # Build up source reliability
        for _ in range(10):
            tracker.record_success("Mint")
        cat = _catalyst("Cabinet approves CBG scheme", score=90, source="Mint")
        articles = [_article("Cabinet approves CBG scheme", source="Mint")]
        conf = tracker.compute_confidence(cat, articles)
        assert conf.source_reliability == 1.0
        assert conf.confidence >= 90.0

    def test_low_reliability_reduces_confidence(self, tracker: SourceReliabilityTracker):
        for _ in range(5):
            tracker.record_error("Unreliable Blog")
        cat = _catalyst("CBG tender awarded", score=80, source="Unreliable Blog")
        articles = [_article("CBG tender awarded", source="Unreliable Blog")]
        conf = tracker.compute_confidence(cat, articles)
        assert conf.source_reliability == 0.0
        assert conf.confidence < 80.0

    def test_corroboration_increases_confidence(self, tracker: SourceReliabilityTracker):
        cat = _catalyst("Praj wins CBG order", score=80, source="Mint")
        articles = [
            _article("Praj wins CBG order", source="Mint"),
            _article("Praj wins CBG order from GAIL", source="ET"),
            _article("Praj awarded CBG contract", source="Moneycontrol"),
        ]
        conf = tracker.compute_confidence(cat, articles, threshold=0.60)
        assert conf.corroboration_count >= 2
        assert conf.corroboration_boost > 0

    def test_positive_sentiment_adds(self, tracker: SourceReliabilityTracker):
        cat = _catalyst("Cabinet approves expansion with growth funding", score=80, source="Mint")
        articles = [_article("Cabinet approves expansion with growth funding", source="Mint")]
        conf = tracker.compute_confidence(cat, articles)
        assert conf.sentiment is not None
        assert conf.sentiment.label == "positive"
        # Positive sentiment should push confidence slightly above base * reliability
        assert conf.confidence > 80.0 * conf.source_reliability

    def test_negative_sentiment_reduces(self, tracker: SourceReliabilityTracker):
        cat = _catalyst("Project delayed loss warning", score=80, source="Mint")
        articles = [_article("Project delayed loss warning", source="Mint")]
        conf = tracker.compute_confidence(cat, articles)
        assert conf.sentiment is not None
        assert conf.sentiment.label == "negative"

    def test_confidence_capped_at_100(self, tracker: SourceReliabilityTracker):
        for _ in range(20):
            tracker.record_success("Mint")
        cat = _catalyst("Cabinet approved funds released", score=95, source="Mint")
        articles = [
            _article("Cabinet approved funds released", source="Mint"),
            _article("Cabinet approved funds released for CBG", source="ET"),
        ]
        conf = tracker.compute_confidence(cat, articles, threshold=0.60)
        assert conf.confidence <= 100.0

    def test_confidence_not_negative(self, tracker: SourceReliabilityTracker):
        for _ in range(10):
            tracker.record_error("BadSource")
        cat = _catalyst("Loss decline crash", score=60, source="BadSource")
        articles = [_article("Loss decline crash", source="BadSource")]
        conf = tracker.compute_confidence(cat, articles)
        assert conf.confidence >= 0.0


# ------------------------------------------------------------------
# Batch scoring
# ------------------------------------------------------------------


class TestBatchScoring:
    def test_scores_multiple(self, tracker: SourceReliabilityTracker):
        cats = [
            _catalyst("Cabinet approves CBG", score=90, source="Mint"),
            _catalyst("Tender awarded to Praj", score=75, source="ET"),
        ]
        articles = [
            _article("Cabinet approves CBG", source="Mint"),
            _article("Tender awarded to Praj", source="ET"),
        ]
        results = tracker.score_catalysts(cats, articles)
        assert len(results) == 2
        assert all(isinstance(conf, CatalystConfidence) for _, conf in results)

    def test_empty_list(self, tracker: SourceReliabilityTracker):
        results = tracker.score_catalysts([], [])
        assert results == []
