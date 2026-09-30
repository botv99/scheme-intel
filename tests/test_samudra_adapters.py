"""Unit and parser tests for Samudra Manthan source adapters and relevance engine.

Verifies:
1. All adapters parse structured content from HTML, XML, and JSON fixtures.
2. Relevance filtering rejects off-topic announcements (retail, telecom, fertilizer, bio-gas).
3. Strict water depth classification: shallow (<400m), deepwater (400-1500m), ultra-deepwater (>1500m), UNKNOWN when unspecified.
4. Malformed, empty, or duplicate records are handled gracefully without exceptions.
5. AdapterRegistry resolves correct adapter instances for Samudra Manthan.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.scheme_intel.ingestion.adapters import AdapterRegistry
from src.scheme_intel.ingestion.adapters.base import FetchResult, RawExtractedRecord, SourceHealthRecord
from src.scheme_intel.ingestion.adapters.cppp import CPPPAdapter
from src.scheme_intel.ingestion.adapters.dgh import DGHAdapter
from src.scheme_intel.ingestion.adapters.exchanges import BSEAnnouncementAdapter, NSEFilingAdapter
from src.scheme_intel.ingestion.adapters.oil_india import OilIndiaAdapter
from src.scheme_intel.ingestion.adapters.ongc import ONGCAdapter
from src.scheme_intel.ingestion.adapters.pib import PIBMoPNGAdapter, PIBNationalEnergyAdapter
from src.scheme_intel.ingestion.adapters.pmo import PMOAdapter
from src.scheme_intel.ingestion.adapters.ril import RILAdapter
from src.scheme_intel.ingestion.adapters.vedanta import VedantaAdapter
from src.scheme_intel.schemes.samudra_manthan.entities import classify_water_depth_strict
from src.scheme_intel.schemes.samudra_manthan.relevance import SamudraRelevanceCategory, SamudraRelevanceFilter
from src.scheme_intel.schemes.samudra_manthan.rules import (
    evaluate_candidate_promotion,
    build_relationship_graph_node,
    discover_from_normalized_event,
    OFFSHORE_CANDIDATE_REGISTRY,
)
from src.scheme_intel.ingestion.models import NormalizedSchemeEvent

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "samudra"


# ---------------------------------------------------------------------------
# Test DGH Adapter
# ---------------------------------------------------------------------------

class TestDGHAdapter:
    def test_parse_valid_fixture(self):
        fixture_path = FIXTURES_DIR / "dgh_fixture.html"
        html = fixture_path.read_text(encoding="utf-8")
        adapter = DGHAdapter()

        events = adapter.parse_and_normalize(html, "https://dghindia.gov.in/notices")
        assert len(events) >= 3

        # Check OALP-X event
        oalp_event = next((e for e in events if "OALP" in e.title), None)
        assert oalp_event is not None
        assert oalp_event.scheme_id == "samudra_manthan"
        assert oalp_event.water_depth.lower() in ("ultra_deepwater", "deepwater")
        assert oalp_event.importance.lower() in ("critical", "high")

        # Check Discovery event
        disc_event = next((e for e in events if "KG-DWN-98/2" in e.title), None)
        assert disc_event is not None
        assert "KG-DWN-98/2" in disc_event.projects

        # Non-offshore holiday notice should be filtered
        holiday_event = next((e for e in events if "holiday" in e.title.lower()), None)
        assert holiday_event is None

    def test_spa_detection(self):
        spa_html = "<!DOCTYPE html><html><head></head><body><app-root></app-root><script src='runtime.js'></script></body></html>"
        adapter = DGHAdapter()
        assert adapter.is_spa_detected(spa_html) is True

    def test_empty_and_malformed_html(self):
        adapter = DGHAdapter()
        assert adapter.parse_and_normalize("", "https://dghindia.gov.in") == []
        assert adapter.parse_and_normalize("<not_html>broken", "https://dghindia.gov.in") == []


# ---------------------------------------------------------------------------
# Test PIB Adapters
# ---------------------------------------------------------------------------

class TestPIBAdapters:
    def test_pib_mopng_parse_fixture(self):
        fixture_path = FIXTURES_DIR / "pib_mopng_fixture.xml"
        xml_content = fixture_path.read_text(encoding="utf-8")
        adapter = PIBMoPNGAdapter()

        events = adapter.parse_and_normalize(xml_content, "https://pib.gov.in/mopng")
        assert len(events) >= 3

        # Ujjwala LPG should be filtered out
        ujjwala = next((e for e in events if "Ujjwala" in e.title), None)
        assert ujjwala is None

        # Deepwater mission approved
        deepwater = next((e for e in events if "Deepwater" in e.title), None)
        assert deepwater is not None
        assert deepwater.importance.lower() in ("critical", "high")

    def test_pib_national_energy_parse_fixture(self):
        fixture_path = FIXTURES_DIR / "pib_energy_fixture.xml"
        xml_content = fixture_path.read_text(encoding="utf-8")
        adapter = PIBNationalEnergyAdapter()

        events = adapter.parse_and_normalize(xml_content, "https://pib.gov.in/energy")
        assert len(events) >= 1

        # Andaman offshore seismic should be captured
        andaman = next((e for e in events if "Andaman" in e.title), None)
        assert andaman is not None

        # Hydrogen mission should be filtered out
        h2 = next((e for e in events if "Hydrogen" in e.title), None)
        assert h2 is None

    def test_malformed_xml_handling(self):
        adapter = PIBMoPNGAdapter()
        assert adapter.parse_and_normalize("<broken><xml", "https://pib.gov.in") == []


# ---------------------------------------------------------------------------
# Test PMO Adapter
# ---------------------------------------------------------------------------

class TestPMOAdapter:
    def test_parse_valid_fixture(self):
        fixture_path = FIXTURES_DIR / "pmo_fixture.html"
        html = fixture_path.read_text(encoding="utf-8")
        adapter = PMOAdapter()

        events = adapter.parse_and_normalize(html, "https://www.pmindia.gov.in/en/news-updates/")
        assert len(events) == 1

        ev = events[0]
        assert "Samudra Manthan" in ev.title or "deepwater" in ev.title.lower()
        assert ev.importance.lower() in ("critical", "high")
        assert "deepwater" in ev.relevance_reason.lower() or "samudra" in ev.relevance_reason.lower()

    def test_malformed_html(self):
        adapter = PMOAdapter()
        assert adapter.parse_and_normalize("<div>no news description here</div>", "https://pmo.gov.in") == []


# ---------------------------------------------------------------------------
# Test CPPP Adapter
# ---------------------------------------------------------------------------

class TestCPPPAdapter:
    def test_parse_valid_fixture(self):
        fixture_path = FIXTURES_DIR / "cppp_fixture.html"
        html = fixture_path.read_text(encoding="utf-8")
        adapter = CPPPAdapter()

        events = adapter.parse_and_normalize(html, "https://eprocure.gov.in/cppp/latestactivetendersnew")
        assert len(events) == 2  # Drillship and Andaman seismic; refinery piping excluded

        # Drillship tender check
        drillship = next((e for e in events if "Drillship" in e.title), None)
        assert drillship is not None
        assert "ONGC/DW/2026/044" in drillship.contracts
        assert drillship.water_depth.lower() == "ultra_deepwater"  # 3000m rated

        # Andaman survey tender check
        seismic = next((e for e in events if "Seismic" in e.title), None)
        assert seismic is not None
        assert "OIL/OFFSHORE/SEIS/2026/012" in seismic.contracts

    def test_malformed_table(self):
        adapter = CPPPAdapter()
        assert adapter.parse_and_normalize("<table><tr><td>bad</td></tr></table>", "https://eprocure.gov.in") == []


# ---------------------------------------------------------------------------
# Test Corporate Adapters (ONGC, OIL, RIL, Vedanta)
# ---------------------------------------------------------------------------

class TestCorporateAdapters:
    def test_ongc_adapter(self):
        fixture_path = FIXTURES_DIR / "ongc_fixture.html"
        html = fixture_path.read_text(encoding="utf-8")
        adapter = ONGCAdapter()

        events = adapter.parse_and_normalize(html, "https://ongcindia.com/web/eng/media/press-release")
        assert len(events) == 1
        assert "KG-DWN-98/2" in events[0].title
        assert any("ongc" in c.lower() for c in events[0].companies)
        assert events[0].water_depth.lower() == "deepwater"

    def test_oil_india_adapter(self):
        fixture_path = FIXTURES_DIR / "oil_india_fixture.html"
        html = fixture_path.read_text(encoding="utf-8")
        adapter = OilIndiaAdapter()

        events = adapter.parse_and_normalize(html, "https://www.oil-india.com/press-release")
        assert len(events) == 1
        assert "Andaman" in events[0].title
        assert any("oil india" in c.lower() for c in events[0].companies)
        assert any("alphageo" in c.lower() for c in events[0].companies)

    def test_ril_adapter(self):
        fixture_path = FIXTURES_DIR / "ril_fixture.html"
        html = fixture_path.read_text(encoding="utf-8")
        adapter = RILAdapter()

        events = adapter.parse_and_normalize(html, "https://www.ril.com/news-media/press-releases")
        assert len(events) == 1
        assert "KG D6" in events[0].title or "MJ" in events[0].title
        assert any("reliance" in c.lower() for c in events[0].companies)
        # Retail expansion should be filtered
        assert not any("Retail" in e.title for e in events)

    def test_vedanta_adapter(self):
        fixture_path = FIXTURES_DIR / "vedanta_fixture.html"
        html = fixture_path.read_text(encoding="utf-8")
        adapter = VedantaAdapter()

        events = adapter.parse_and_normalize(html, "https://www.vedantalimited.com/eng/investor-relations")
        assert len(events) == 1
        assert "Ravva" in events[0].title
        # Zinc announcement filtered out
        assert not any("Zinc" in e.title for e in events)


# ---------------------------------------------------------------------------
# Test Exchange Filings Adapters (NSE, BSE)
# ---------------------------------------------------------------------------

class TestExchangeAdapters:
    def test_nse_adapter(self):
        fixture_path = FIXTURES_DIR / "nse_filings_fixture.json"
        json_str = fixture_path.read_text(encoding="utf-8")
        adapter = NSEFilingAdapter()

        events = adapter.parse_and_normalize(json_str, "https://www.nseindia.com/api/corporate-announcements")
        assert len(events) == 2  # Deep Industries and L&T; TCS excluded

        deep_event = next((e for e in events if "Deep Industries" in e.title), None)
        assert deep_event is not None
        assert "DEEP INDUSTRIES" in [c.upper() for c in deep_event.companies] or "DEEPINDS" in deep_event.companies

        lt_event = next((e for e in events if "Larsen & Toubro" in e.title), None)
        assert lt_event is not None
        assert "LT" in lt_event.companies or "Larsen & Toubro" in lt_event.companies or "L&T" in lt_event.companies

    def test_bse_adapter(self):
        fixture_path = FIXTURES_DIR / "bse_announcements_fixture.json"
        json_str = fixture_path.read_text(encoding="utf-8")
        adapter = BSEAnnouncementAdapter()

        events = adapter.parse_and_normalize(json_str, "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData")
        assert len(events) == 2  # Alphageo and GE Shipping; TCS excluded

        alphageo_event = next((e for e in events if "Alphageo" in e.title), None)
        assert alphageo_event is not None

        gesco_event = next((e for e in events if "Great Eastern" in e.title or "GE Shipping" in e.title), None)
        assert gesco_event is not None


# ---------------------------------------------------------------------------
# Test Relevance Engine and Water Depth Strict Classification
# ---------------------------------------------------------------------------

class TestRelevanceEngine:
    def test_relevance_classification(self):
        filter_engine = SamudraRelevanceFilter()

        # OALP and Deepwater
        res1 = filter_engine.evaluate(
            "Notice Inviting Bids under Open Acreage Licensing Programme (OALP) Bid Round X offering deepwater blocks",
            ""
        )
        assert res1.is_relevant is True
        assert res1.category in (SamudraRelevanceCategory.OALP, SamudraRelevanceCategory.DEEPWATER)
        assert res1.importance in ("critical", "high")

        # Seismic Marine
        res2 = filter_engine.evaluate(
            "Oil India awards 3D marine seismic survey contract in Andaman basin",
            ""
        )
        assert res2.is_relevant is True
        assert res2.category in (SamudraRelevanceCategory.SEISMIC, SamudraRelevanceCategory.MARINE)

        # Off-topic biogas / fertilizer / consumer retail
        res3 = filter_engine.evaluate(
            "Subsidies granted for rural compressed biogas plant under Gobardhan scheme",
            ""
        )
        assert res3.is_relevant is False

        res4 = filter_engine.evaluate(
            "Smartphone sales jump during festive season e-commerce campaign",
            ""
        )
        assert res4.is_relevant is False

    def test_water_depth_strict(self):
        # Explicit depth < 400m
        assert classify_water_depth_strict("shallow water depth of 120m in Mumbai High") == "shallow"
        assert classify_water_depth_strict("water depth 350 meters") == "shallow"

        # Explicit depth 400m - 1500m
        assert classify_water_depth_strict("operating in water depths of 850m in KG basin") == "deepwater"
        assert classify_water_depth_strict("depth of 1200 meters") == "deepwater"

        # Explicit depth > 1500m
        assert classify_water_depth_strict("ultra deepwater well in 2400m water depth") == "ultra_deepwater"
        assert classify_water_depth_strict("ultra-deepwater block in 1800 meters") == "ultra_deepwater"

        # Explicit keyword without meter number
        assert classify_water_depth_strict("ultra-deepwater exploration block") == "ultra_deepwater"
        assert classify_water_depth_strict("deepwater drilling campaign") == "deepwater"
        assert classify_water_depth_strict("shallow water platform") == "shallow"

        # Rule: Never infer deepwater from bare "offshore" without depth specification!
        assert classify_water_depth_strict("offshore exploration activities announced") == "unknown"
        assert classify_water_depth_strict("marine vessel support contract") == "unknown"


# ---------------------------------------------------------------------------
# Test Candidate Promotion Controls and Relationship Discovery
# ---------------------------------------------------------------------------

class TestCandidatePromotionAndDiscovery:
    def test_promotion_controls(self):
        # Candidate without verified contract or tender award -> NOT PROMOTED
        ev_generic = NormalizedSchemeEvent(
            event_id="evt-gen-01",
            scheme_id="samudra_manthan",
            source_id="news",
            external_id="gen-01",
            title="Deep Industries mentioned in oil sector overview article",
            content="General discussion of energy markets.",
            relevance_reason="general",
            companies=["Deep Industries"],
        )
        assert evaluate_candidate_promotion("DEEP INDUSTRIES", [ev_generic]) is False

        # Candidate with verified contract award / tender -> PROMOTED
        ev_verified = NormalizedSchemeEvent(
            event_id="evt-ver-01",
            scheme_id="samudra_manthan",
            source_id="nse",
            external_id="nse-01",
            title="Deep Industries awarded Rs 185 Cr charter hire contract by ONGC for offshore support vessel",
            content="Contract awarded for 3 years offshore charter.",
            relevance_reason="offshore_contract",
            companies=["Deep Industries", "ONGC"],
            contracts=["ONGC-CHARTER-2026"],
        )
        assert evaluate_candidate_promotion("DEEP INDUSTRIES", [ev_verified]) is True

    def test_relationship_graph_node_building(self):
        ev = NormalizedSchemeEvent(
            event_id="evt-cppp-01",
            scheme_id="samudra_manthan",
            source_id="cppp",
            external_id="cppp-01",
            title="ONGC tenders ultra-deepwater drillship charter for KG-DWN-98/2",
            content="Tender closing Oct 2026.",
            relevance_reason="deepwater",
            water_depth="ultra_deepwater",
            companies=["ONGC"],
            projects=["KG-DWN-98/2"],
            contracts=["ONGC/DW/2026/044"],
        )
        node = build_relationship_graph_node(ev)
        assert node["companies"] == ["ONGC"]
        assert node["projects"] == ["KG-DWN-98/2"]
        assert node["contracts"] == ["ONGC/DW/2026/044"]
        assert node["water_depth"] == "ultra_deepwater"

    def test_discover_from_normalized_event(self):
        ev = NormalizedSchemeEvent(
            event_id="evt-bse-01",
            scheme_id="samudra_manthan",
            source_id="bse",
            external_id="bse-01",
            title="Alphageo bags 3D marine seismic contract in Andaman basin",
            content="Contract awarded by Oil India.",
            relevance_reason="seismic",
            companies=["Alphageo", "Oil India"],
        )
        discovered = discover_from_normalized_event(ev)
        assert len(discovered) > 0
        candidate_names = [c["name"].upper() for c in discovered]
        assert any("ALPHAGEO" in name for name in candidate_names)


# ---------------------------------------------------------------------------
# Test Adapter Registry
# ---------------------------------------------------------------------------

class TestAdapterRegistry:
    def test_registry_resolution(self):
        dgh = AdapterRegistry.get_adapter("samudra_manthan", "dgh_portal")
        assert isinstance(dgh, DGHAdapter)

        pib_mopng = AdapterRegistry.get_adapter("samudra_manthan", "pib_mopng_samudra")
        assert isinstance(pib_mopng, PIBMoPNGAdapter)

        pib_energy = AdapterRegistry.get_adapter("samudra_manthan", "pib_national_energy")
        assert isinstance(pib_energy, PIBNationalEnergyAdapter)

        pmo = AdapterRegistry.get_adapter("samudra_manthan", "pmo_releases")
        assert isinstance(pmo, PMOAdapter)

        cppp = AdapterRegistry.get_adapter("samudra_manthan", "cppp_hydrocarbons")
        assert isinstance(cppp, CPPPAdapter)

        ongc = AdapterRegistry.get_adapter("samudra_manthan", "ongc_corporate")
        assert isinstance(ongc, ONGCAdapter)

        oil = AdapterRegistry.get_adapter("samudra_manthan", "oil_india_corporate")
        assert isinstance(oil, OilIndiaAdapter)

        ril = AdapterRegistry.get_adapter("samudra_manthan", "ril_investor_updates")
        assert isinstance(ril, RILAdapter)

        vedanta = AdapterRegistry.get_adapter("samudra_manthan", "vedanta_corporate")
        assert isinstance(vedanta, VedantaAdapter)

        nse = AdapterRegistry.get_adapter("samudra_manthan", "nse_energy_filings")
        assert isinstance(nse, NSEFilingAdapter)

        bse = AdapterRegistry.get_adapter("samudra_manthan", "bse_energy_announcements")
        assert isinstance(bse, BSEAnnouncementAdapter)
