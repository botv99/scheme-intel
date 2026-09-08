"""
Pytest configuration and shared fixtures.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from scheme_intel.models import Article, Catalyst, SwingSetup


@pytest.fixture
def sample_article():
    """Sample article for testing."""
    return Article(
        title="Cabinet approves GOBARdhan fund release of ₹100 crore",
        url="https://example.com/article",
        source="PIB Ministry",
        published_at=None,
        summary="Government approves fund release"
    )


@pytest.fixture
def sample_catalyst(sample_article):
    """Sample catalyst for testing."""
    return Catalyst(
        article=sample_article,
        score=90,
        category="fund release",
        rationale="Detected fund release language",
        companies=("PRAJIND",)
    )


@pytest.fixture
def sample_setup():
    """Sample swing setup for testing."""
    return SwingSetup(
        company="Praj Industries",
        symbol="PRAJIND.NS",
        close=450.0,
        entry=460.0,
        stop=420.0,
        target=500.0,
        rsi14=65.5,
        catalyst_score=90,
        status="QUALIFIED",
        generated_at="2026-09-08T09:00:00Z"
    )


@pytest.fixture
def config_dict():
    """Sample configuration dictionary."""
    return {
        "scheme": {
            "name": "GOBARdhan",
            "aliases": ["GOBARdhan", "CBG"],
            "official_sources": [
                {
                    "name": "PIB Ministry",
                    "url": "https://pib.gov.in"
                }
            ]
        },
        "settings": {
            "rally_threshold_pct": 10,
            "minimum_catalyst_score": 60,
            "max_setup_age_days": 5,
            "risk_per_trade_pct": 1
        },
        "stocks": [
            {
                "name": "Praj Industries",
                "symbol": "PRAJIND.NS",
                "aliases": ["Praj"],
                "thesis": "CBG technology"
            }
        ]
    }
