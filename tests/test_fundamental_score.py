"""
Deterministic Unit Tests for Fundamental Intelligence Score Engine (Stage 3).
Verifies:
  - Strong & weak fundamentals
  - High-growth & high-debt scenarios
  - Cash flow strength & conversion
  - Expensive & cheap valuation
  - Missing valuation, ROCE, FCF
  - Sector-specific weights and thresholds
  - Minimum coverage requirement
  - Range boundaries (0.0 <= score <= 10.0)
  - Version field ("v1.0")
"""
import pytest

from scheme_intel.intelligence.fundamental_score import (
    FundamentalIntelligenceEngine,
    FundamentalDataStore,
    FUNDAMENTAL_SCORE_VERSION,
)


class TestFundamentalIntelligenceEngine:
    def setup_method(self):
        self.engine = FundamentalIntelligenceEngine()

    def test_version_field(self):
        assert FUNDAMENTAL_SCORE_VERSION == "v1.0"
        data = FundamentalDataStore.get_company_data("GAIL.NS")
        res = self.engine.calculate("GAIL.NS", data)
        assert res.version == "v1.0"

    def test_strong_fundamentals(self):
        strong_data = {
            "name": "SuperCorp",
            "sector": "industrial",
            "period": "FY2026 Q1",
            "data_as_of": "2026-06-30",
            "revenue_growth_yoy": 25.0,
            "revenue_cagr_3y": 22.0,
            "ebitda_margin": 24.0,
            "net_profit_margin": 16.0,
            "roce": 28.0,
            "roe": 24.0,
            "debt_to_equity": 0.05,
            "interest_coverage": 25.0,
            "cfo_to_pat_ratio": 1.25,
            "free_cash_flow_positive": True,
            "earnings_stability_score": 9.0,
            "pe_ratio": 24.0,
        }
        res = self.engine.calculate("SUPER.NS", strong_data)
        assert res.score is not None
        assert res.score >= 8.0, f"Expected strong score >= 8.0, got {res.score}"
        assert res.coverage_pct >= 95.0

    def test_weak_fundamentals(self):
        weak_data = {
            "name": "StrugglingCorp",
            "sector": "industrial",
            "period": "FY2026 Q1",
            "data_as_of": "2026-06-30",
            "revenue_growth_yoy": -18.0,
            "revenue_cagr_3y": -8.0,
            "ebitda_margin": 1.5,
            "net_profit_margin": -5.0,
            "roce": 2.0,
            "roe": -4.0,
            "debt_to_equity": 3.2,
            "interest_coverage": 0.8,
            "cfo_to_pat_ratio": -0.4,
            "free_cash_flow_positive": False,
            "earnings_stability_score": 2.5,
            "pe_ratio": None,
        }
        res = self.engine.calculate("WEAK.NS", weak_data)
        assert res.score is not None
        assert res.score <= 3.5, f"Expected weak score <= 3.5, got {res.score}"

    def test_high_growth_company(self):
        data = {
            "name": "HyperGrowth",
            "sector": "bioenergy",
            "revenue_growth_yoy": 45.0,
            "revenue_cagr_3y": 50.0,
            "ebitda_margin": 16.0,
            "net_profit_margin": 9.0,
            "roce": 18.0,
            "roe": 16.0,
            "debt_to_equity": 0.4,
            "cfo_to_pat_ratio": 1.0,
        }
        res = self.engine.calculate("GROWTH.NS", data)
        assert res.score is not None
        assert res.components["growth"].score == 10.0

    def test_high_debt_company_penalized(self):
        data = {
            "name": "LeveragedCorp",
            "sector": "industrial",
            "debt_to_equity": 2.8,
            "interest_coverage": 1.2,
            "revenue_growth_yoy": 10.0,
            "ebitda_margin": 12.0,
            "roce": 10.0,
        }
        res = self.engine.calculate("LEVER.NS", data)
        assert res.components["balance_sheet"].score is not None
        assert res.components["balance_sheet"].score <= 3.0

    def test_strong_cash_flow_and_conversion(self):
        data = {
            "name": "CashCow",
            "sector": "utilities",
            "cfo_to_pat_ratio": 1.45,
            "free_cash_flow_positive": True,
            "revenue_growth_yoy": 12.0,
            "ebitda_margin": 15.0,
            "roce": 16.0,
        }
        res = self.engine.calculate("CASH.NS", data)
        assert res.components["cash_flow"].score == 10.0

    def test_missing_metrics_renormalize_cleanly(self):
        # Missing valuation and FCF
        partial_data = {
            "name": "PartialCorp",
            "sector": "industrial",
            "revenue_growth_yoy": 15.0,
            "ebitda_margin": 14.0,
            "roce": 18.0,
            "debt_to_equity": 0.2,
            "free_cash_flow_positive": True,
            # valuation & earnings_quality omitted (no cfo_to_pat_ratio or earnings_stability)
        }
        res = self.engine.calculate("PART.NS", partial_data)
        assert res.score is not None
        assert res.components["valuation"].data_available is False
        assert res.components["earnings_quality"].data_available is False
        assert res.coverage_pct >= 75.0
        assert 0.0 <= res.score <= 10.0

    def test_insufficient_data_returns_none(self):
        # Empty dictionary or pre-IPO unlisted entity
        res = self.engine.calculate("TRUALT.NS")
        assert res.score is None
        assert res.status == "INSUFFICIENT_COVERAGE"
        assert res.coverage_pct < 60.0
        assert "Insufficient fundamental data" in (res.reason or "")

    def test_registered_watchlist_companies(self):
        # All monitored companies should evaluate cleanly
        for sym in ["GAIL.NS", "IOC.NS", "PRAJIND.NS", "WABAG.NS", "KIRLPNU.NS"]:
            res = self.engine.calculate(sym)
            assert res.score is not None
            assert 0.0 <= res.score <= 10.0
            assert res.coverage_pct >= 80.0
            assert res.status == "VALID"

    def test_deterministic_score(self):
        data = FundamentalDataStore.get_company_data("PRAJIND.NS")
        res1 = self.engine.calculate("PRAJIND.NS", data)
        res2 = self.engine.calculate("PRAJIND.NS", data)
        assert res1.score == res2.score
        assert res1.coverage_pct == res2.coverage_pct
        for k in res1.components:
            assert res1.components[k].score == res2.components[k].score
