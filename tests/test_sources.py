"""
Unit tests for sources module.
"""
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from requests.exceptions import Timeout, ConnectionError

import pytest

# Ensure 'src' is discoverable by editor language server and pytest
_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from scheme_intel.sources import (
    fetch_rss, scan_page, deduplicate_articles, _date
)
from scheme_intel.exceptions import SourceAccessError, DataParseError
from scheme_intel.models import Article


class TestFetchRss:
    """Tests for RSS feed fetching."""
    
    def test_fetch_rss_success(self):
        """Test successful RSS fetch."""
        with patch('scheme_intel.sources.feedparser.parse') as mock_parse:
            mock_entry = {
                'title': 'GOBARdhan Fund Release',
                'link': 'https://example.com/article',
                'published': 'Thu, 01 Jan 2026 12:00:00 GMT',
                'summary': 'Fund release announcement'
            }
            mock_parse.return_value.entries = [mock_entry]
            mock_parse.return_value.bozo = False
            
            articles = fetch_rss("Test Source", "https://feed.example.com")
            
            assert len(articles) == 1
            assert articles[0].title == 'GOBARdhan Fund Release'
            assert articles[0].source == "Test Source"
    
    def test_fetch_rss_empty_feed(self):
        """Test RSS feed with no entries."""
        with patch('scheme_intel.sources.feedparser.parse') as mock_parse:
            mock_parse.return_value.entries = []
            mock_parse.return_value.bozo = False
            
            articles = fetch_rss("Test Source", "https://feed.example.com")
            
            assert len(articles) == 0
    
    def test_fetch_rss_malformed_feed(self):
        """Test handling of malformed RSS feed."""
        with patch('scheme_intel.sources.feedparser.parse') as mock_parse:
            mock_parse.return_value.bozo = True
            mock_parse.return_value.bozo_exception = ValueError("Invalid XML")
            mock_parse.return_value.entries = []
            
            articles = fetch_rss("Test Source", "https://feed.example.com")
            
            assert len(articles) == 0


class TestScanPage:
    """Tests for page scanning."""
    
    def test_scan_page_success(self):
        """Test successful page scan."""
        with patch('scheme_intel.sources.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.text = '''
                <html>
                    <a href="/news/1">Cabinet approves GOBARdhan scheme</a>
                    <a href="/news/2">Unrelated news</a>
                    <a href="/news/3">CBG offtake announced</a>
                </html>
            '''
            mock_get.return_value = mock_response
            
            articles = scan_page(
                "Test Source",
                "https://example.com",
                ["GOBARdhan", "CBG"]
            )
            
            assert len(articles) == 2
            assert any("GOBARdhan" in a.title for a in articles)
            assert any("CBG" in a.title for a in articles)

    def test_scan_page_word_boundary_isolation(self):
        """Test that short aliases like 'ORS' do not match substrings like 'directors'."""
        with patch('scheme_intel.sources.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.text = '''
                <html>
                    <a href="/news/1">Board of directors meeting scheduled</a>
                    <a href="/news/2">ORS bags new circular bioenergy contract</a>
                </html>
            '''
            mock_get.return_value = mock_response

            articles = scan_page(
                "Test Source",
                "https://example.com",
                ["ORS"]
            )

            assert len(articles) == 1
            assert "directors" not in articles[0].title
            assert "ORS bags" in articles[0].title
    
    def test_scan_page_connection_error(self):
        """Test handling of connection error."""
        with patch('scheme_intel.sources.requests.get') as mock_get:
            mock_get.side_effect = ConnectionError("Network unreachable")
            
            with pytest.raises(SourceAccessError):
                scan_page("Test Source", "https://example.com", ["CBG"])
    
    def test_scan_page_timeout(self):
        """Test handling of request timeout."""
        with patch('scheme_intel.sources.requests.get') as mock_get:
            mock_get.side_effect = Timeout("Request timeout")
            
            with pytest.raises(SourceAccessError):
                scan_page("Test Source", "https://example.com", ["CBG"])


class TestDeduplicateArticles:
    """Tests for article deduplication."""
    
    def test_deduplicate_removes_duplicates(self):
        """Test that duplicates are removed."""
        articles = [
            Article("Title 1", "https://example.com/1", "Source", None),
            Article("Title 1", "https://example.com/1", "Source", None),  # duplicate
            Article("Title 2", "https://example.com/2", "Source", None),
        ]
        
        deduplicated = deduplicate_articles(articles)
        
        assert len(deduplicated) == 2
    
    def test_deduplicate_preserves_unique(self):
        """Test that unique articles are preserved."""
        articles = [
            Article("Title 1", "https://example.com/1", "Source", None),
            Article("Title 2", "https://example.com/2", "Source", None),
            Article("Title 3", "https://example.com/3", "Source", None),
        ]
        
        deduplicated = deduplicate_articles(articles)
        
        assert len(deduplicated) == 3


class TestDateParsing:
    """Tests for date parsing."""
    
    def test_parse_valid_date(self):
        """Test parsing valid RFC 2822 date."""
        result = _date("Thu, 01 Jan 2026 12:00:00 GMT")
        assert result is not None
        assert result.year == 2026
    
    def test_parse_none_returns_none(self):
        """Test that None input returns None."""
        result = _date(None)
        assert result is None
    
    def test_parse_invalid_date(self):
        """Test that invalid date returns None."""
        result = _date("invalid-date-string")
        assert result is None

    def test_parse_iso8601_with_z(self):
        """Test parsing ISO 8601 date with Z suffix."""
        result = _date("2026-09-25T12:00:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 9
        assert result.day == 25
