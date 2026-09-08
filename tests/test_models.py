"""
Unit tests for data models.
"""
from datetime import datetime, timezone
import pytest

from scheme_intel.models import Article, Catalyst, SwingSetup, SourceQuality, AnalysisReport, now_utc


class TestModels:
    """Tests for data models."""

    def test_article_creation(self):
        """Test creating Article with and without sentiment."""
        art = Article(
            title="Test Announcement",
            url="https://example.com/1",
            source="PIB",
            published_at=None,
            summary="Test Summary",
            sentiment=0.75
        )
        assert art.title == "Test Announcement"
        assert art.sentiment == 0.75

    def test_source_quality_reliability(self):
        """Test SourceQuality reliability score calculation."""
        sq = SourceQuality(name="PIB", url="https://pib.gov.in", success_count=8, error_count=2)
        assert sq.reliability_score == 0.8
        
        sq_empty = SourceQuality(name="New Source", url="https://example.com")
        assert sq_empty.reliability_score == 1.0

        d = sq.to_dict()
        assert d["name"] == "PIB"
        assert d["reliability_score"] == 0.8

    def test_analysis_report(self):
        """Test AnalysisReport serialization."""
        report = AnalysisReport(
            generated_at=now_utc().isoformat(),
            catalysts=[{"title": "Test Catalyst", "score": 90}],
            setups=[{"company": "Praj", "status": "QUALIFIED"}],
            source_errors=[],
            summary="1 catalyst found"
        )
        report_dict = report.to_dict()
        assert report_dict["summary"] == "1 catalyst found"
        assert len(report_dict["catalysts"]) == 1
        assert len(report_dict["setups"]) == 1
