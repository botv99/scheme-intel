"""
Unit tests for catalyst classification.
"""
import pytest
from scheme_intel.catalyst import classify
from scheme_intel.models import Article


class TestCatalystClassification:
    """Tests for catalyst classification."""
    
    def test_classify_cabinet_approval(self):
        """Test classification of cabinet approval catalyst."""
        article = Article(
            title="Cabinet approves GOBARdhan fund release for Praj Industries",
            url="https://example.com",
            source="PIB",
            published_at=None,
            summary=""
        )
        
        companies = [
            {"name": "Praj Industries", "aliases": ["Praj"]}
        ]
        
        catalyst = classify(article, companies)
        
        assert catalyst is not None
        assert catalyst.score >= 85
        assert catalyst.companies == ("Praj Industries",)
    
    def test_classify_tender_award(self):
        """Test classification of tender award."""
        article = Article(
            title="GAIL announced CBG tender awarded for ₹50 crore project",
            url="https://example.com",
            source="PIB",
            published_at=None,
            summary=""
        )
        
        companies = [
            {"name": "GAIL", "aliases": ["GAIL India"]}
        ]
        
        catalyst = classify(article, companies)
        
        assert catalyst is not None
        assert catalyst.score >= 80
        assert catalyst.companies == ("GAIL",)
    
    def test_classify_no_match(self):
        """Test when no catalyst is found."""
        article = Article(
            title="Weather update for Delhi",
            url="https://example.com",
            source="Weather.com",
            published_at=None,
            summary="Rainfall expected"
        )
        
        companies = [
            {"name": "Praj Industries", "aliases": ["Praj"]}
        ]
        
        catalyst = classify(article, companies)
        
        assert catalyst is None
    
    def test_classify_multiple_companies(self):
        """Test catalyst with multiple matching companies."""
        article = Article(
            title="Cabinet approves CBG fund release for GAIL and Praj",
            url="https://example.com",
            source="PIB",
            published_at=None,
            summary=""
        )
        
        companies = [
            {"name": "GAIL", "aliases": ["GAIL India"]},
            {"name": "Praj Industries", "aliases": ["Praj"]}
        ]
        
        catalyst = classify(article, companies)
        
        assert catalyst is not None
        assert len(catalyst.companies) == 2
        assert "GAIL" in catalyst.companies
        assert "Praj Industries" in catalyst.companies
    
    def test_classify_contract_award(self):
        """Test contract award classification."""
        article = Article(
            title="Praj Industries receives contract awarded for CBG plant",
            url="https://example.com",
            source="PIB",
            published_at=None,
            summary=""
        )
        
        companies = [
            {"name": "Praj Industries", "aliases": ["Praj"]}
        ]
        
        catalyst = classify(article, companies)
        
        assert catalyst is not None
        assert catalyst.score >= 80
        assert catalyst.companies == ("Praj Industries",)
