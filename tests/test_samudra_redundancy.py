"""
Unit and Integration Tests for Samudra Manthan Source Redundancy & Cross-Source Corroboration (Stage 4E).

Verifies:
1. Redundancy catalog and 18 information requirements coverage matrix.
2. Alternative news & specialist adapters parse valid items and discard noise.
3. Authority-based confidence tiers (Tier 1: 0.95, Tier 2: 0.92, Tier 3: 0.82, Tier 4: 0.78, Tier 5: 0.65).
4. Cross-source corroboration merges multi-source reports into 1 canonical event with boosted confidence.
5. Duplicate news story suppression (2 news reports -> 1 canonical event, 2 evidence records).
6. Legacy DGH archive handling (preserves historical publication date, source_status='LEGACY').
7. Coordinator redundancy activation when primary source is blocked.
8. Zero Gobardhan cross-scheme regression.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from scheme_intel.schemes.registry import SchemeRegistry
from scheme_intel.schemes.samudra_manthan.redundancy import (
    SAMUDRA_REDUNDANT_CATALOG,
    SAMUDRA_FALLBACK_GROUPS,
    SamudraInformationRequirement,
    SourceAuthorityLevel,
    get_fallback_sources_for_source,
    get_sources_for_information_requirement,
    get_information_coverage_matrix,
)
from scheme_intel.schemes.samudra_manthan.sources import SAMUDRA_SOURCES
from scheme_intel.ingestion.adapters import (
    AdapterRegistry,
    ETEnergyWorldAdapter,
    ReutersEnergyAdapter,
    BusinessStandardEnergyAdapter,
    MintEnergyAdapter,
    OffshoreTechnologyAdapter,
    LegacyDGHArchiveAdapter,
)
from scheme_intel.ingestion.adapters.base import FetchResult, SourceHealthRecord
from scheme_intel.ingestion.corroboration import CrossSourceCorroborator
from scheme_intel.ingestion.coordinator import SchemeIngestionCoordinator
from scheme_intel.ingestion.models import NormalizedSchemeEvent

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "samudra"


# =========================================================================
# 1. Source Redundancy Catalog & Information Coverage Matrix Tests
# =========================================================================

class TestSamudraRedundancyCatalog:
    """Verifies the multi-tier source catalog and coverage matrix."""

    def test_catalog_source_count_and_tiers(self):
        """All 17 primary, exchange, news, specialist, and archive sources registered."""
        assert len(SAMUDRA_REDUNDANT_CATALOG) >= 17
        sources_by_tier = {}
        for src in SAMUDRA_REDUNDANT_CATALOG.values():
            sources_by_tier.setdefault(src.authority_level, []).append(src.source_id)

        assert len(sources_by_tier[SourceAuthorityLevel.TIER1_OFFICIAL]) >= 7
        assert len(sources_by_tier[SourceAuthorityLevel.TIER2_EXCHANGE]) >= 2
        assert len(sources_by_tier[SourceAuthorityLevel.TIER3_FINANCIAL_NEWS]) >= 4
        assert len(sources_by_tier[SourceAuthorityLevel.TIER4_SPECIALIST_MEDIA]) >= 1
        assert len(sources_by_tier[SourceAuthorityLevel.TIER5_LEGACY_ARCHIVE]) >= 1

    def test_all_18_information_requirements_covered(self):
        """All 18 Samudra information requirements must have at least 2 distinct sources."""
        for req in SamudraInformationRequirement:
            sources = get_sources_for_information_requirement(req)
            assert len(sources) >= 2, f"Requirement {req.value} has fewer than 2 sources: {sources}"

    def test_information_coverage_matrix_robustness(self):
        """Coverage matrix must evaluate all requirements as STRONG or ADEQUATE."""
        matrix = get_information_coverage_matrix()
        assert len(matrix) == len(SamudraInformationRequirement)

        ratings = {row["coverage_rating"] for row in matrix.values()}
        assert "VULNERABLE" not in ratings, "No Samudra information requirement should be vulnerable"
        assert "WEAK" not in ratings, "No Samudra information requirement should be weak"
        assert "NO_RELIABLE_SOURCE" not in ratings, "No Samudra information requirement should have critical gaps"
        assert all(r in ("STRONG", "ADEQUATE") for r in ratings)
        assert "STRONG" in ratings

    def test_fallback_sources_for_dgh_and_ongc(self):
        """DGH and ONGC primary sources resolve valid, enabled fallback sources."""
        dgh_fallbacks = get_fallback_sources_for_source("dgh_portal")
        assert len(dgh_fallbacks) >= 2
        dgh_fallback_ids = [f.source_id for f in dgh_fallbacks]
        assert "et_energyworld" in dgh_fallback_ids
        assert "legacy_dgh_archive" in dgh_fallback_ids

        ongc_fallbacks = get_fallback_sources_for_source("ongc_corporate")
        assert len(ongc_fallbacks) >= 2
        ongc_fallback_ids = [f.source_id for f in ongc_fallbacks]
        assert any("filings" in fid or "news" in fid or "oil_india" in fid for fid in ongc_fallback_ids)


# =========================================================================
# 2. Alternative News & Specialist Adapters Parser Tests
# =========================================================================

class TestAlternativeNewsAdapters:
    """Tests parsing and filtering on alternative financial news and specialist media."""

    def test_et_energyworld_adapter_parsing(self):
        """ET EnergyWorld parses RSS XML, extracts ONGC KG-DWN-98/2 and DGH OALP X, rejects petrol prices."""
        xml_content = (FIXTURES_DIR / "et_energy_fixture.xml").read_text(encoding="utf-8")
        adapter = ETEnergyWorldAdapter()
        events = adapter.parse_and_normalize(xml_content, adapter.url)

        # 2 offshore events extracted, petrol prices rejected
        assert len(events) == 2
        titles = [e.title for e in events]
        assert any("ONGC awards deepwater rig charter" in t for t in titles)
        assert any("DGH opens international bidding for OALP Round X" in t for t in titles)
        assert not any("Petrol and diesel" in t for t in titles)

        # Check metadata and authority
        ongc_evt = next(e for e in events if "ONGC" in e.title)
        assert "ONGC" in ongc_evt.companies
        assert "KG-DWN-98/2" in ongc_evt.projects
        assert ongc_evt.water_depth == "ultra_deepwater"
        assert ongc_evt.confidence == 0.82
        assert ongc_evt.evidence[0]["authority_level"] == 3

    def test_reuters_energy_adapter_parsing(self):
        """Reuters Energy parses HTML, extracts Reliance/BP KG-D6 deepwater, rejects telecom auction."""
        html_content = (FIXTURES_DIR / "reuters_energy_fixture.html").read_text(encoding="utf-8")
        adapter = ReutersEnergyAdapter()
        events = adapter.parse_and_normalize(html_content, adapter.url)

        # Extracted deepwater Reliance/BP and Brent crude impact, telecom rejected
        assert len(events) >= 1
        titles = [e.title for e in events]
        assert any("Reliance and BP commission new subsea wells" in t for t in titles)
        assert not any("telecom" in t.lower() for t in titles)

        ril_evt = next(e for e in events if "Reliance" in e.title)
        assert "Reliance Industries" in ril_evt.companies
        assert "KG-D6" in ril_evt.projects
        assert ril_evt.water_depth == "deepwater"

    def test_business_standard_energy_adapter_parsing(self):
        """Business Standard parses RSS XML, extracts L&T EPC order and Oil India Andaman seismic survey."""
        xml_content = (FIXTURES_DIR / "business_standard_fixture.xml").read_text(encoding="utf-8")
        adapter = BusinessStandardEnergyAdapter()
        events = adapter.parse_and_normalize(xml_content, adapter.url)

        assert len(events) == 2
        titles = [e.title for e in events]
        assert any("Larsen & Toubro secures mega offshore EPC order" in t for t in titles)
        assert any("Oil India signs offshore exploration agreement" in t for t in titles)
        assert not any("Automobile" in t for t in titles)

        lt_evt = next(e for e in events if "Larsen & Toubro" in e.title)
        assert "Larsen & Toubro" in lt_evt.companies
        assert "Mumbai High" in lt_evt.projects

    def test_mint_energy_adapter_parsing(self):
        """Mint parses RSS XML, extracts Cabinet ultra-deepwater incentives and Vedanta capex."""
        xml_content = (FIXTURES_DIR / "mint_energy_fixture.xml").read_text(encoding="utf-8")
        adapter = MintEnergyAdapter()
        events = adapter.parse_and_normalize(xml_content, adapter.url)

        assert len(events) == 2
        titles = [e.title for e in events]
        assert any("Cabinet clears enhanced fiscal incentives" in t for t in titles)
        assert any("Vedanta Cairn Oil & Gas" in t for t in titles)
        assert not any("Edtech" in t for t in titles)

        vedanta_evt = next(e for e in events if "Vedanta" in e.title)
        assert "Vedanta (Cairn)" in vedanta_evt.companies
        assert "Ravva" in vedanta_evt.projects

    def test_offshore_technology_adapter_parsing(self):
        """Offshore Technology specialist adapter extracts subsea diving and gas compression, sets Tier 4."""
        xml_content = (FIXTURES_DIR / "offshore_technology_fixture.xml").read_text(encoding="utf-8")
        adapter = OffshoreTechnologyAdapter()
        events = adapter.parse_and_normalize(xml_content, adapter.url)

        assert len(events) == 2
        titles = [e.title for e in events]
        assert any("SEAMEC mobilises diving support vessel" in t for t in titles)
        assert any("Deep Industries secures" in t for t in titles)
        assert not any("North Sea" in t for t in titles)

        seamec_evt = next(e for e in events if "SEAMEC" in e.title)
        assert "SEAMEC" in seamec_evt.companies
        assert seamec_evt.confidence == 0.78
        assert seamec_evt.evidence[0]["authority_level"] == 4

    def test_legacy_dgh_archive_adapter_parsing(self):
        """Legacy DGH Archive adapter parses historical bidding notices, sets is_legacy=True and Tier 5."""
        html_content = (FIXTURES_DIR / "legacy_dgh_archive_fixture.html").read_text(encoding="utf-8")
        adapter = LegacyDGHArchiveAdapter()
        events = adapter.parse_and_normalize(html_content, adapter.url)

        assert len(events) >= 2
        titles = [e.title for e in events]
        assert any("OALP Round VIII" in t for t in titles)

        archive_evt = events[0]
        assert archive_evt.event_type == "HISTORICAL_ARCHIVE"
        assert archive_evt.confidence == 0.65
        assert archive_evt.evidence[0]["is_legacy"] is True
        assert archive_evt.evidence[0]["source_status"] == "LEGACY"
        assert archive_evt.evidence[0]["authority_level"] == 5


# =========================================================================
# 3. Cross-Source Corroboration & Deduplication Engine Tests
# =========================================================================

class TestCrossSourceCorroboration:
    """Verifies multi-source evidence merging and confidence boosting."""

    def test_corroborate_three_sources_into_one_canonical_event(self):
        """3 distinct sources reporting the same ONGC rig charter merge into 1 event with 3 evidence items."""
        evt1 = NormalizedSchemeEvent(
            event_id="EVT-ONGC-001",
            scheme_id="samudra_manthan",
            source_id="ongc_corporate",
            event_type="CONTRACT_AWARD",
            title="ONGC awards deepwater rig charter contract for KG-DWN-98/2",
            content="ONGC awards deepwater drillship contract for 2100m water depth in KG-DWN-98/2 basin.",
            published_at="2026-09-28T09:00:00Z",
            confidence=0.95,
            importance="HIGH",
            companies=["ONGC"],
            projects=["KG-DWN-98/2"],
            contracts=["RIG_CHARTER_2026_01"],
            water_depth="ultra_deepwater",
            evidence=[{"source": "ONGC Corporate Disclosures", "url": "https://ongcindia.com/pr/1", "authority_level": 1}],
        )

        evt2 = NormalizedSchemeEvent(
            event_id="EVT-NSE-002",
            scheme_id="samudra_manthan",
            source_id="nse_energy_filings",
            event_type="DISCLOSURE",
            title="Exchange Disclosure: ONGC awards offshore rig charter in KG-DWN-98/2",
            content="Regulatory disclosure under Reg 30: ONGC issues LOA for deepwater drillship charter hire.",
            published_at="2026-09-28T10:15:00Z",
            confidence=0.92,
            importance="HIGH",
            companies=["ONGC"],
            projects=["KG-DWN-98/2"],
            contracts=["RIG_CHARTER_2026_01"],
            water_depth="deepwater",
            evidence=[{"source": "NSE Energy Filings", "url": "https://nseindia.com/announcements/101", "authority_level": 2}],
        )

        evt3 = NormalizedSchemeEvent(
            event_id="EVT-ET-003",
            scheme_id="samudra_manthan",
            source_id="et_energyworld",
            event_type="NEWS_REPORT",
            title="ONGC awards deepwater rig charter contract worth Rs 1450 crore for KG-DWN-98/2",
            content="News report on ONGC deepwater drillship charter in KG basin.",
            published_at="2026-09-28T11:30:00Z",
            confidence=0.82,
            importance="MEDIUM",
            companies=["ONGC"],
            projects=["KG-DWN-98/2"],
            contracts=["RIG_CHARTER_2026_01"],
            water_depth="ultra_deepwater",
            evidence=[{"source": "The Economic Times EnergyWorld", "url": "https://energy.economictimes.indiatimes.com/news/1", "authority_level": 3}],
        )

        corroborated = CrossSourceCorroborator.corroborate_and_deduplicate([evt1, evt2, evt3])

        # Exactly 1 consolidated event returned
        assert len(corroborated) == 1
        canon_event = corroborated[0]

        # Canonical ID derived
        assert canon_event.event_id.startswith("CANON-")

        # Lead event from highest authority (ONGC Corporate = Tier 1)
        assert canon_event.source_id == "ongc_corporate"

        # Evidence records aggregated from all 3 sources
        assert len(canon_event.evidence) == 3
        evidence_sources = [ev["source"] for ev in canon_event.evidence]
        assert "ONGC Corporate Disclosures" in evidence_sources
        assert "NSE Energy Filings" in evidence_sources
        assert "The Economic Times EnergyWorld" in evidence_sources

        # Boosted confidence: base 0.95 + 2 * 0.05 = 0.99
        assert canon_event.confidence >= 0.99
        assert canon_event.importance == "HIGH"
        assert "ONGC" in canon_event.companies
        assert "KG-DWN-98/2" in canon_event.projects

    def test_duplicate_news_suppression(self):
        """2 distinct news feeds reporting the same OALP Round X bidding announcement consolidate into 1 event."""
        news1 = NormalizedSchemeEvent(
            event_id="EVT-MINT-01",
            scheme_id="samudra_manthan",
            source_id="mint_energy",
            event_type="NEWS_REPORT",
            title="DGH launches OALP Round X bidding for 28 offshore exploration blocks",
            content="DGH opens bidding for 28 offshore and deepwater blocks under OALP Round X.",
            published_at="2026-09-27T10:00:00Z",
            confidence=0.82,
            evidence=[{"source": "Mint Energy", "url": "https://livemint.com/oalp-1", "authority_level": 3}],
        )

        news2 = NormalizedSchemeEvent(
            event_id="EVT-ET-02",
            scheme_id="samudra_manthan",
            source_id="et_energyworld",
            event_type="NEWS_REPORT",
            title="DGH opens international bidding for OALP Round X offering 28 offshore blocks",
            content="Directorate General of Hydrocarbons initiates OALP Round X tender.",
            published_at="2026-09-27T12:00:00Z",
            confidence=0.82,
            evidence=[{"source": "The Economic Times EnergyWorld", "url": "https://energy.economictimes.indiatimes.com/oalp-2", "authority_level": 3}],
        )

        results = CrossSourceCorroborator.corroborate_and_deduplicate([news1, news2])

        # Exactly 1 event, 2 evidence sources, confidence boosted from 0.82 to 0.87
        assert len(results) == 1
        assert len(results[0].evidence) == 2
        assert results[0].confidence == pytest.approx(0.87, abs=0.01)

    def test_historical_archive_event_tagged(self):
        """Events older than 180 days or from legacy archive are tagged as HISTORICAL_ARCHIVE."""
        legacy_evt = NormalizedSchemeEvent(
            event_id="EVT-LEGACY-01",
            scheme_id="samudra_manthan",
            source_id="legacy_dgh_archive",
            event_type="NEWS_REPORT",
            title="Historical Notice: OALP Round VIII guidelines",
            content="Historical DGH guidelines from 2024.",
            published_at="2024-03-15T00:00:00Z",
            confidence=0.65,
            evidence=[{"source": "DGH Archive", "url": "https://dghindia.gov.in/arc/1", "is_legacy": True}],
        )

        results = CrossSourceCorroborator.corroborate_and_deduplicate([legacy_evt])
        assert len(results) == 1
        assert results[0].event_type == "HISTORICAL_ARCHIVE"
        assert results[0].published_at.startswith("2024-03-15")


# =========================================================================
# 4. Coordinator Redundancy & Gobardhan Isolation Tests
# =========================================================================

class TestCoordinatorRedundancyIntegration:
    """Verifies that the coordinator activates fallbacks when a primary source fails."""

    def test_coordinator_activates_fallback_on_blocked_primary(self):
        """When DGH portal reports BLOCKED (Cloudflare 403), coordinator activates fallback group."""
        coordinator = SchemeIngestionCoordinator(timeout=5)

        # Mock DGH adapter to return BLOCKED
        blocked_health = SourceHealthRecord(
            source_id="dgh_portal",
            status="BLOCKED",
            parser_status="BLOCKED",
            reason="Cloudflare 403 Forbidden",
        )

        with patch("scheme_intel.ingestion.adapters.dgh.DGHAdapter.ingest", return_value=([], blocked_health)):
            # Also mock network fetching for others to avoid live HTTP calls in unit tests
            with patch("requests.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.text = "<html><body>Offshore News</body></html>"
                mock_get.return_value = mock_resp

                with patch("scheme_intel.sources.fetch_rss", return_value=[]):
                    batch = coordinator.ingest_scheme("samudra_manthan")

        # DGH is recorded as BLOCKED
        assert batch.source_health.get("dgh_portal") == "BLOCKED"

        # Fallback mechanism is populated on health record
        dgh_rec = next((r for r in batch.source_health_records if r.source_id == "dgh_portal"), None)
        assert dgh_rec is not None
        assert dgh_rec.fallback is not None
        assert "et_energyworld" in dgh_rec.fallback

    def test_gobardhan_isolation_unaffected_by_samudra_redundancy(self):
        """Gobardhan ingestion must remain 100% isolated with zero Samudra/offshore contamination."""
        coordinator = SchemeIngestionCoordinator(timeout=5)

        mock_gobardhan_data = {
            "pib_mopng": [
                {
                    "scheme_id": "gobardhan",
                    "title": "MoPNG announces 50 new compressed biogas (CBG) plants under SATAT",
                    "content": "SATAT CBG infrastructure expansion across Punjab and Haryana.",
                    "companies": ["Praj Industries"],
                    "importance": "HIGH",
                }
            ]
        }

        batch = coordinator.ingest_scheme("gobardhan", mock_source_data=mock_gobardhan_data)
        assert batch.scheme_id == "gobardhan"
        assert len(batch.events) == 1
        evt = batch.events[0]
        assert evt.scheme_id == "gobardhan"
        assert "Praj Industries" in evt.companies

        # Verify absolutely no Samudra entities or deepwater tags in Gobardhan event
        assert evt.water_depth is None
        assert "ONGC" not in evt.companies
        assert "KG-DWN-98/2" not in evt.projects
