"""
Unit tests for signals/technical analysis module.
"""
import pytest
from unittest.mock import patch, Mock
from datetime import datetime
import pandas as pd

from scheme_intel.signals import make_setup, _rsi


class TestRSICalculation:
    """Tests for RSI calculation."""
    
    def test_rsi_calculation(self):
        """Test RSI calculation with sample data."""
        # Create sample close prices
        close = pd.Series([100, 102, 101, 103, 105, 104, 106, 108, 107, 109,
                          111, 110, 112, 114, 113, 115, 114, 116, 118, 117])
        
        rsi = _rsi(close, period=14)
        
        assert isinstance(rsi, float)
        assert 0 <= rsi <= 100
    
    def test_rsi_uptrend(self):
        """Test RSI in uptrend (should be high)."""
        # Strong uptrend
        close = pd.Series([100 + i for i in range(20)])
        
        rsi = _rsi(close, period=14)
        
        # RSI should be high (> 70) in strong uptrend
        assert rsi > 70


class TestMakeSetup:
    """Tests for swing setup generation."""
    
    @patch('scheme_intel.signals.yf.Ticker')
    def test_make_setup_qualified(self, mock_ticker):
        """Test generation of QUALIFIED setup."""
        # Mock historical data
        dates = pd.date_range(start='2026-03-01', periods=120)
        mock_data = pd.DataFrame({
            'Open': [450 + i*0.5 for i in range(120)],
            'High': [455 + i*0.5 for i in range(120)],
            'Low': [445 + i*0.5 for i in range(120)],
            'Close': [450 + i*0.5 for i in range(120)],
            'Volume': [1000000] * 120
        }, index=dates)
        
        mock_ticker.return_value.history.return_value = mock_data
        
        setup = make_setup("Praj Industries", "PRAJIND.NS", catalyst_score=90)
        
        assert setup is not None
        assert setup.company == "Praj Industries"
        assert setup.symbol == "PRAJIND.NS"
        assert setup.entry > setup.close
        assert setup.stop < setup.entry
        assert setup.target > setup.entry
    
    @patch('scheme_intel.signals.yf.Ticker')
    def test_make_setup_insufficient_data(self, mock_ticker):
        """Test when insufficient historical data."""
        dates = pd.date_range(start='2026-08-01', periods=30)  # Only 30 days
        mock_data = pd.DataFrame({
            'High': [450] * 30,
            'Low': [445] * 30,
            'Close': [448] * 30,
            'Volume': [1000000] * 30
        }, index=dates)
        
        mock_ticker.return_value.history.return_value = mock_data
        
        setup = make_setup("Praj Industries", "PRAJIND.NS", catalyst_score=90)
        
        assert setup is None
    
    @patch('scheme_intel.signals.yf.Ticker')
    def test_make_setup_watch_status(self, mock_ticker):
        """Test WATCH status when conditions not met."""
        # Create downtrend data (no momentum)
        dates = pd.date_range(start='2026-03-01', periods=120)
        mock_data = pd.DataFrame({
            'High': [550 - i*0.5 for i in range(120)],
            'Low': [540 - i*0.5 for i in range(120)],
            'Close': [545 - i*0.5 for i in range(120)],
            'Volume': [1000000] * 120
        }, index=dates)
        
        mock_ticker.return_value.history.return_value = mock_data
        
        setup = make_setup("Praj Industries", "PRAJIND.NS", catalyst_score=50)
        
        assert setup is not None
        assert setup.status == "WATCH"
