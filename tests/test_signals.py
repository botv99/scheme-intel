"""
Unit tests for signals/technical analysis module.
"""
import pytest
from unittest.mock import patch, Mock
from datetime import datetime
import pandas as pd

from scheme_intel.signals import make_setup, _rsi, _macd, _weekly_trend


def _rows_qualified() -> list[dict]:
    """Synthetic 125-bar series that satisfies every technical filter.

    A gently rising base, then alternating up/down days, closed by a +9% volume
    spike breakout on a Friday. Trusted to produce a QUALIFIED setup (RSI ~70,
    volume ~3x trailing average, positive MACD histogram, weekly trend UP).
    """
    dts = pd.bdate_range(end="2026-09-11", periods=125)
    rows = []
    price = 100.0
    for i in range(len(dts)):
        if i < 70:
            price = 100 + i * 0.35 + (i % 3) * 0.1
        else:
            price = price * (1.045 if i % 2 == 0 else 0.975)
            price = max(price, 130.0)
        if i == len(dts) - 1:
            price = price * 1.09
        rows.append({
            "date": dts[i].strftime("%Y-%m-%d"),
            "open": round(price * 0.995, 2),
            "high": round(price * (1.012 if i % 2 == 0 else 1.005), 2),
            "low": round(price * (0.988 if i % 2 == 0 else 0.995), 2),
            "close": round(price, 2),
            "volume": 3_200_000 if i == len(dts) - 1 else 1_000_000 + (i % 5) * 12_000,
        })
    return rows


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


class TestMakeSetupFromHistory:
    """Tests for swing setup generation from injected OHLC history."""

    @staticmethod
    def _rows() -> list[dict]:
        rows = []
        for i in range(120):
            base = 450 + i * 0.5
            rows.append({
                "date": f"2026-0{1 + i // 28}-{(i % 28) + 1:02d}",
                "Open": base,
                "High": base + 5,
                "Low": base - 5,
                "Close": base,
                "Volume": 1000000,
            })
        return rows

    @patch('scheme_intel.signals.yf.Ticker')
    def test_make_setup_uses_injected_history(self, mock_ticker):
        """Provided history must be used without any live yfinance call."""
        setup = make_setup("Praj Industries", "PRAJIND.NS", catalyst_score=90, history=self._rows())

        mock_ticker.assert_not_called()
        assert setup is not None
        assert setup.company == "Praj Industries"
        assert setup.entry > setup.close
        assert setup.stop < setup.entry
        assert setup.target > setup.entry

    @patch('scheme_intel.signals.yf.Ticker')
    def test_make_setup_insufficient_injected_history(self, mock_ticker):
        """Short injected history must yield no setup and skip yfinance."""
        setup = make_setup("Praj Industries", "PRAJIND.NS", catalyst_score=90, history=self._rows()[-30:])

        mock_ticker.assert_not_called()
        assert setup is None


class TestTechnicalFilters:
    """Volume breakout, MACD filter and weekly multi-timeframe confirmation."""

    @patch('scheme_intel.signals.yf.Ticker')
    def test_qualified_volume_breakout_macd_mtf(self, mock_ticker):
        """Buying signal only qualifies with every filter green."""
        setup = make_setup("Demo", "DEMO.NS", 90, history=_rows_qualified())

        mock_ticker.assert_not_called()
        assert setup is not None and setup.status == "QUALIFIED"
        assert setup.breakout is True
        assert setup.volume_ratio >= 1.5
        assert setup.macd is not None and setup.macd_signal is not None
        assert setup.macd_hist > 0
        assert setup.week_trend == "UP"
        assert setup.prior_high20 < setup.close

    @patch('scheme_intel.signals.yf.Ticker')
    def test_flat_volume_blocks_qualification(self, mock_ticker):
        """A breakout on average volume must not be confirmed."""
        rows = _rows_qualified()
        rows[-1]["volume"] = 1_000_000

        setup = make_setup("Demo", "DEMO.NS", 90, history=rows)

        assert setup is not None and setup.status == "WATCH"
        assert setup.breakout is True
        assert setup.volume_ratio < 1.5

    @patch('scheme_intel.signals.yf.Ticker')
    def test_negative_macd_histogram_blocks_qualification(self, mock_ticker):
        """A bearish MACD crossover blocks qualification even with volume."""
        rows = _rows_qualified()

        with patch('scheme_intel.signals._macd', return_value=(0.1, 0.2, -0.05)):
            setup = make_setup("Demo", "DEMO.NS", 90, history=rows)

        assert setup is not None and setup.status == "WATCH"
        assert setup.volume_ratio >= 1.5

    @patch('scheme_intel.signals.yf.Ticker')
    def test_weekly_downtrend_blocks_qualification(self, mock_ticker):
        """Higher timeframe trend must confirm, not fight, the daily setup."""
        rows = _rows_qualified()

        with patch('scheme_intel.signals._weekly_trend', return_value="DOWN"):
            setup = make_setup("Demo", "DEMO.NS", 90, history=rows)

        assert setup is not None and setup.status == "WATCH"
        assert setup.macd_hist > 0

    @patch('scheme_intel.signals.yf.Ticker')
    def test_lowercase_injected_history_is_normalised(self, mock_ticker):
        """Ingested rows carry lowercase OHLC keys; they must parse correctly."""
        rows = _rows_qualified()

        setup = make_setup("Demo", "DEMO.NS", 90, history=rows)

        mock_ticker.assert_not_called()
        assert setup is not None and setup.status == "QUALIFIED"


class TestMacd:
    def test_macd_insufficient_data(self):
        assert _macd(pd.Series([100.0] * 5)) == (None, None, None)

    def test_macd_uptrend_positive_histogram(self):
        close = pd.Series([100 + i for i in range(60)])
        macd, signal, hist = _macd(close)
        assert macd is not None and macd > 0
        assert hist > 0


class TestWeeklyTrend:
    @staticmethod
    def _frame(closes: list[float], end_day: str = "2026-09-11") -> pd.DataFrame:
        index = pd.bdate_range(end=end_day, periods=len(closes))
        return pd.DataFrame({"Close": closes}, index=index)

    def test_uptrend_is_up(self):
        closes = [100 + i * 0.5 for i in range(130)]
        assert _weekly_trend(self._frame(closes)) == "UP"

    def test_downtrend_is_down(self):
        closes = [300 - i * 0.5 for i in range(130)]
        assert _weekly_trend(self._frame(closes)) == "DOWN"

    def test_too_short_history_is_none(self):
        closes = [100 + i for i in range(30)]
        assert _weekly_trend(self._frame(closes)) is None


class TestDMA200:
    @patch('scheme_intel.signals.yf.Ticker')
    def test_dma200_above_is_not_blocking(self, mock_ticker):
        """A stock trading above its 200-DMA still qualifies."""
        setup = make_setup("Demo", "DEMO.NS", 90, history=_rows_qualified(), dma200=150.0)
        assert setup is not None and setup.status == "QUALIFIED"
        assert setup.dma200 == 150.0

    @patch('scheme_intel.signals.yf.Ticker')
    def test_dma200_below_blocks_qualification(self, mock_ticker):
        """A stock below its 200-DMA must not qualify."""
        setup = make_setup("Demo", "DEMO.NS", 90, history=_rows_qualified(), dma200=400.0)
        assert setup is not None and setup.status == "WATCH"
        assert setup.dma200 == 400.0

    def test_dma200_none_does_not_block(self):
        """When the 200-DMA is unavailable, qualification must not be blocked."""
        setup = make_setup("Demo", "DEMO.NS", 90, history=_rows_qualified(), dma200=None)
        assert setup is not None and setup.status == "QUALIFIED"
        assert setup.dma200 is None
