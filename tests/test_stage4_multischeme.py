"""
Stage 4 Test Suite — Multi-Scheme Architecture & Samudra Manthan Implementation.
Verifies complete logical and physical isolation, commercial licensing, session store,
retrieval boundaries, ingestion guards, and dynamic beneficiary discovery.
"""
from __future__ import annotations

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scheme_intel.schemes.registry import SchemeRegistry
from scheme_intel.schemes.models import (
    BeneficiaryRelationshipType,
    CompanyWatchlistStatus,
    CompanySchemeRelationship,
)
from scheme_intel.schemes.samudra_manthan.rules import (
    SamudraRulesEngine,
    DynamicBeneficiaryDiscovery,
)
from scheme_intel.schemes.samudra_manthan.mapping import (
    SAMUDRA_KEYWORDS,
    SAMUDRA_COMPANY_MAPPINGS,
)
from scheme_intel.licensing.models import Customer, Entitlement, SchemeFeature
from scheme_intel.licensing.service import EntitlementService
from scheme_intel.licensing.session import SessionStore
from scheme_intel.ingestion.models import NormalizedSchemeEvent
from scheme_intel.ingestion.coordinator import (
    SchemeIngestionCoordinator,
    SchemeBoundaryViolationError,
)
from scheme_intel.intelligence_memory.models import (
    IntelligenceSnapshot,
    CompanyIntelligence,
    SchemeIntelligence,
)
from scheme_intel.intelligence_memory.store import IntelligenceStore
from scheme_intel.intelligence_memory.retrieval import FastIntelligenceRetriever
from scheme_intel.intelligence_memory.memory_store import SchemeMemoryFactStore
from scheme_intel.delivery.telegram_router import TelegramMessageRouter
from scheme_intel.delivery.request_store import RequestStore
from scheme_intel.research.executor import ResearchExecutor
from scheme_intel.research.queue import ResearchQueue
from scheme_intel.research.models import ResearchJob
import sqlite3
from scheme_intel.intelligence.market_sentiment import MarketSentimentEngine
from scheme_intel.db import SchemeIntelDB
from scheme_intel.storage.migrations import apply_migrations


@pytest.fixture
def temp_db(tmp_path):
    """Provides a fresh SQLite database with all Stage 4 migrations applied."""
    db_file = tmp_path / "test_scheme_intel.db"
    with SchemeIntelDB(db_file) as db:
        pass
    return db_file


@pytest.fixture
def sample_snapshots(tmp_path):
    """Generates isolated Gobardhan and Samudra Manthan snapshots."""
    gobardhan_store = IntelligenceStore(
        snapshot_path=tmp_path / "intelligence" / "gobardhan" / "latest.json"
    )
    samudra_store = IntelligenceStore(
        snapshot_path=tmp_path / "intelligence" / "samudra_manthan" / "latest.json"
    )

    # Gobardhan snapshot
    gobardhan_snap = IntelligenceSnapshot(
        snapshot_id="snap_gobardhan_001",
        generated_at="2026-09-30T10:00:00Z",
        scheme_id="gobardhan",
        companies={
            "TRUALT.NS": CompanyIntelligence(
                symbol="TRUALT.NS",
                short_symbol="TRUALT",
                name="TruAlt Bioenergy",
                scheme_id="gobardhan",
                scheme_name="GOBARdhan",
                price=1350.0,
                status="QUALIFIED_SETUP",
            ),
            "PRAJIND.NS": CompanyIntelligence(
                symbol="PRAJIND.NS",
                short_symbol="PRAJIND",
                name="Praj Industries",
                scheme_id="gobardhan",
                scheme_name="GOBARdhan",
                price=780.0,
                status="WATCH",
            ),
        },
        schemes={
            "gobardhan": SchemeIntelligence(
                scheme_id="gobardhan",
                name="GOBARdhan",
                total_budget="₹10,000 Cr",
            )
        },
        qualified_setups=["TRUALT.NS"],
        waiting_setups=["PRAJIND.NS"],
    )
    gobardhan_store.save(gobardhan_snap)

    # Samudra Manthan snapshot
    samudra_snap = IntelligenceSnapshot(
        snapshot_id="snap_samudra_001",
        generated_at="2026-09-30T10:00:00Z",
        scheme_id="samudra_manthan",
        companies={
            "ONGC.NS": CompanyIntelligence(
                symbol="ONGC.NS",
                short_symbol="ONGC",
                name="Oil and Natural Gas Corporation",
                scheme_id="samudra_manthan",
                scheme_name="Samudra Manthan",
                price=320.0,
                status="QUALIFIED_SETUP",
            ),
            "OIL.NS": CompanyIntelligence(
                symbol="OIL.NS",
                short_symbol="OIL",
                name="Oil India Limited",
                scheme_id="samudra_manthan",
                scheme_name="Samudra Manthan",
                price=650.0,
                status="WATCH",
            ),
        },
        schemes={
            "samudra_manthan": SchemeIntelligence(
                scheme_id="samudra_manthan",
                name="Samudra Manthan",
                total_budget="₹15,000 Cr",
            )
        },
        qualified_setups=["ONGC.NS"],
        waiting_setups=["OIL.NS"],
    )
    samudra_store.save(samudra_snap)

    return {
        "gobardhan_store": gobardhan_store,
        "samudra_store": samudra_store,
        "data_dir": tmp_path,
    }


# =========================================================================
# Section 46: Tests 1 to 12 & Architectural Isolation
# =========================================================================

class TestStage4IsolationAndRetrieval:

    def test_1_active_gobardhan_query_gobardhan_stock(self, temp_db, sample_snapshots):
        """1. Active Gobardhan -> query Gobardhan stock -> data returned."""
        session_store = SessionStore(db_path=temp_db)
        entitlement_service = EntitlementService(db_path=temp_db)
        entitlement_service.register_customer("cust_101", user_ids=["user_101"])
        entitlement_service.grant_entitlement("cust_101", "gobardhan", enabled=True)
        retriever = FastIntelligenceRetriever(store=sample_snapshots["gobardhan_store"])
        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
        )

        session_store.set_active_scheme("user_101", "gobardhan")
        reply = router.route_message("/stock TRUALT", user_id="user_101")

        assert "TRUALT" in reply
        assert "TruAlt Bioenergy" in reply
        assert "₹1,350.00" in reply
        assert "GOBARdhan" in reply

    def test_2_active_samudra_query_samudra_stock(self, temp_db, sample_snapshots):
        """2. Active Samudra -> query ONGC -> Samudra data returned."""
        session_store = SessionStore(db_path=temp_db)
        entitlement_service = EntitlementService(db_path=temp_db)
        entitlement_service.register_customer("cust_102", user_ids=["user_102"])
        entitlement_service.grant_entitlement("cust_102", "samudra_manthan", enabled=True)
        retriever = FastIntelligenceRetriever(store=sample_snapshots["samudra_store"])
        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
        )

        session_store.set_active_scheme("user_102", "samudra_manthan")
        reply = router.route_message("/stock ONGC", user_id="user_102")

        assert "ONGC" in reply
        assert "Oil and Natural Gas Corporation" in reply
        assert "₹320.00" in reply
        assert "Samudra Manthan" in reply

    def test_3_active_samudra_query_gobardhan_stock_out_of_universe(self, temp_db, sample_snapshots):
        """3. Active Samudra -> query Praj Industries -> out of universe notice, no Gobardhan research leaked."""
        session_store = SessionStore(db_path=temp_db)
        entitlement_service = EntitlementService(db_path=temp_db)
        entitlement_service.register_customer("cust_103", user_ids=["user_103"])
        entitlement_service.grant_entitlement("cust_103", "samudra_manthan", enabled=True)
        retriever = FastIntelligenceRetriever(store=sample_snapshots["samudra_store"])
        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
        )

        session_store.set_active_scheme("user_103", "samudra_manthan")
        reply = router.route_message("/stock PRAJ", user_id="user_103")

        # Must give out of universe / not found notice
        assert "Stock Not Found" in reply or "not currently in" in reply
        assert "PRAJIND.NS" in reply or "PRAJ" in reply
        # Must NOT leak Gobardhan data (Praj's ₹780 price or bioenergy details)
        assert "₹780.00" not in reply
        assert "Bio-Energy" not in reply

    def test_4_active_gobardhan_query_samudra_stock_out_of_universe(self, temp_db, sample_snapshots):
        """4. Active Gobardhan -> query ONGC -> out of universe notice, no Samudra research leaked."""
        session_store = SessionStore(db_path=temp_db)
        entitlement_service = EntitlementService(db_path=temp_db)
        entitlement_service.register_customer("cust_104", user_ids=["user_104"])
        entitlement_service.grant_entitlement("cust_104", "gobardhan", enabled=True)
        retriever = FastIntelligenceRetriever(store=sample_snapshots["gobardhan_store"])
        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
        )

        session_store.set_active_scheme("user_104", "gobardhan")
        reply = router.route_message("/stock ONGC", user_id="user_104")

        assert "Stock Not Found" in reply or "not currently in" in reply
        assert "₹320.00" not in reply
        assert "Offshore" not in reply

    def test_5_samudra_event_never_in_gobardhan_snapshot(self, sample_snapshots):
        """5. Samudra event / company never in Gobardhan snapshot."""
        gob_snap = sample_snapshots["gobardhan_store"].load()
        assert gob_snap is not None
        assert "ONGC.NS" not in gob_snap.companies
        assert "OIL.NS" not in gob_snap.companies
        assert "RELIANCE.NS" not in gob_snap.companies
        assert "samudra_manthan" not in gob_snap.schemes

    def test_6_gobardhan_event_never_in_samudra_snapshot(self, sample_snapshots):
        """6. Gobardhan event / company never in Samudra snapshot."""
        sam_snap = sample_snapshots["samudra_store"].load()
        assert sam_snap is not None
        assert "TRUALT.NS" not in sam_snap.companies
        assert "PRAJIND.NS" not in sam_snap.companies
        assert "WABAG.NS" not in sam_snap.companies
        assert "gobardhan" not in sam_snap.schemes

    def test_7_8_research_worker_scheme_isolation(self, temp_db, sample_snapshots):
        """7 & 8: ResearchWorker hard boundaries: Gobardhan never queries Samudra and vice-versa."""
        mem_store = SchemeMemoryFactStore(db_path=temp_db)
        # Store facts into each scheme partition
        mem_store.record_fact("gobardhan", "SATAT 5000 plants target established by MoPNG.", source_name="pib")
        mem_store.record_fact("samudra_manthan", "Deepwater KG Basin appraisal well completed by ONGC.", source_name="dgh")

        executor = ResearchExecutor(
            memory_fact_store=mem_store,
            intelligence_store=sample_snapshots["gobardhan_store"],
        )

        # 7. Querying out-of-universe company Praj in Samudra Manthan deep research
        samudra_job = ResearchJob(
            job_id="job_sam_01",
            scheme_id="samudra_manthan",
            question="Analyze Praj Industries participation in Samudra Manthan",
            created_at="2026-09-30T10:00:00Z",
        )
        samudra_res = executor.execute(samudra_job)
        samudra_report = samudra_res[0] if isinstance(samudra_res, tuple) else getattr(samudra_res, "structured_report", str(samudra_res))
        assert "Isolation Notice" in samudra_report
        assert "not currently in the" in samudra_report
        # Zero Gobardhan memory retrieved
        assert "SATAT" not in samudra_report

        # 8. Querying out-of-universe company ONGC in Gobardhan deep research
        gob_job = ResearchJob(
            job_id="job_gob_01",
            scheme_id="gobardhan",
            question="What is ONGC's offshore drilling strategy for Gobardhan?",
            created_at="2026-09-30T10:00:00Z",
        )
        gob_res = executor.execute(gob_job)
        gob_report = gob_res[0] if isinstance(gob_res, tuple) else getattr(gob_res, "structured_report", str(gob_res))
        assert "Isolation Notice" in gob_report
        assert "not currently in the" in gob_report
        # Zero Samudra memory retrieved
        assert "KG Basin" not in gob_report

    def test_9_10_commercial_licensing_authorization(self, temp_db):
        """9 & 10: Unauthorized customer rejected; authorized customer succeeds."""
        service = EntitlementService(db_path=temp_db)
        # Register Customer A with user_109, entitled only to gobardhan
        service.register_customer("cust_a", name="Customer A", user_ids=["user_109"])
        service.grant_entitlement("cust_a", "gobardhan", enabled=True)

        # 9. Customer A requests samudra_manthan -> rejected
        auth_9, reason_9 = service.authorize_access("samudra_manthan", user_id="user_109")
        assert auth_9 is False
        assert "not entitled" in reason_9.lower()

        # 10. Register Customer B with user_110, entitled to samudra_manthan
        service.register_customer("cust_b", name="Customer B", user_ids=["user_110"])
        service.grant_entitlement("cust_b", "samudra_manthan", enabled=True)
        auth_10, reason_10 = service.authorize_access("samudra_manthan", user_id="user_110")
        assert auth_10 is True
        assert "authorized" in reason_10.lower()

    def test_11_12_customer_switch_and_cross_scheme_denial(self, temp_db, sample_snapshots):
        """11 & 12: Gobardhan-only customer cannot switch to Samudra; Samudra-only cannot access Gobardhan."""
        session_store = SessionStore(db_path=temp_db)
        entitlement_service = EntitlementService(db_path=temp_db)
        retriever = FastIntelligenceRetriever(store=sample_snapshots["gobardhan_store"])
        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
        )

        # Customer 1: Entitled only to Gobardhan
        entitlement_service.register_customer("cust_1", user_ids=["user_gob_only"])
        entitlement_service.grant_entitlement("cust_1", "gobardhan", enabled=True)

        # 11. Customer 1 tries /switch samudra_manthan -> BLOCKED
        switch_reply = router.route_message("/switch samudra_manthan", user_id="user_gob_only")
        assert "ACCESS DENIED" in switch_reply
        # Session MUST remain gobardhan
        assert session_store.get_active_scheme("user_gob_only") == "gobardhan"

        # Customer 2: Entitled only to Samudra Manthan
        entitlement_service.register_customer("cust_2", user_ids=["user_sam_only"])
        entitlement_service.grant_entitlement("cust_2", "samudra_manthan", enabled=True)
        session_store.set_active_scheme("user_sam_only", "samudra_manthan")

        # 12. Customer 2 tries to access Gobardhan watchlist or snapshot -> BLOCKED
        gob_reply = router.route_message("/scheme gobardhan", user_id="user_sam_only")
        assert "ACCESS DENIED" in gob_reply

    def test_switch_session_concurrent_users(self, temp_db, sample_snapshots):
        """Concurrent sessions: User A on Samudra does NOT affect User B on Gobardhan."""
        session_store = SessionStore(db_path=temp_db)
        entitlement_service = EntitlementService(db_path=temp_db)
        entitlement_service.register_customer("cust_A", user_ids=["user_A"])
        entitlement_service.grant_entitlement("cust_A", "samudra_manthan", enabled=True)
        entitlement_service.grant_entitlement("cust_A", "gobardhan", enabled=True)
        entitlement_service.register_customer("cust_B", user_ids=["user_B"])
        entitlement_service.grant_entitlement("cust_B", "gobardhan", enabled=True)
        retriever = FastIntelligenceRetriever(store=sample_snapshots["gobardhan_store"])
        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
        )

        # User A switches to Samudra
        router.route_message("/switch samudra_manthan", user_id="user_A")
        assert session_store.get_active_scheme("user_A") == "samudra_manthan"

        # User B remains on Gobardhan
        assert session_store.get_active_scheme("user_B") == "gobardhan"

        # User A watchlist is Samudra Manthan
        sam_retriever = FastIntelligenceRetriever(store=sample_snapshots["samudra_store"])
        router.retriever = sam_retriever
        reply_a = router.route_message("/watchlist", user_id="user_A")
        assert "SAMUDRA MANTHAN" in reply_a
        assert "ONGC" in reply_a

        # User B watchlist is Gobardhan
        gob_retriever = FastIntelligenceRetriever(store=sample_snapshots["gobardhan_store"])
        router.retriever = gob_retriever
        reply_b = router.route_message("/watchlist", user_id="user_B")
        assert "GOBARDHAN" in reply_b
        assert "TRUALT" in reply_b


# =========================================================================
# Ingestion, Rules & Dynamic Beneficiary Discovery
# =========================================================================

class TestIngestionAndSamudraRules:

    def test_ingestion_coordinator_boundary_violation(self):
        """SchemeIngestionCoordinator strictly prevents cross-scheme event assignment."""
        coordinator = SchemeIngestionCoordinator()

        # Gobardhan event trying to be ingested under samudra_manthan scheme
        cross_event = NormalizedSchemeEvent(
            event_id="evt_001",
            scheme_id="gobardhan",
            title="Biogas plant subsidy released under SATAT",
            content="Gobardhan scheme plant commissioned in Punjab.",
            source_id="pib_gobardhan",
            published_at="2026-09-30T09:00:00Z",
        )

        with pytest.raises(SchemeBoundaryViolationError) as exc_info:
            coordinator.ingest_event(cross_event, target_scheme_id="samudra_manthan")
        assert "boundary violation" in str(exc_info.value).lower()

    def test_dynamic_beneficiary_discovery(self):
        """Verify dynamic discovery engine classifies beneficiary relationships."""
        discovery = DynamicBeneficiaryDiscovery()

        content = (
            "DGH India announces ONGC awarded 3 deepwater blocks in KG-DWN offshore basin. "
            "Seamec Limited contracted for offshore diving support vessels and subsea inspection."
        )

        relationships = discovery.discover_beneficiaries(
            event_title="Deepwater Block Award & Support Contract",
            content=content,
            source="dgh_official",
        )

        assert len(relationships) >= 2
        symbols_found = {r.company_symbol for r in relationships}
        assert "ONGC.NS" in symbols_found
        assert "SEAMECLTD.NS" in symbols_found

        # ONGC should be classified as operator or block holder
        ongc_rel = next(r for r in relationships if r.company_symbol == "ONGC.NS")
        assert ongc_rel.relationship_type in (
            BeneficiaryRelationshipType.DIRECT_OPERATOR,
            BeneficiaryRelationshipType.BLOCK_HOLDER,
            BeneficiaryRelationshipType.DEEPWATER_EXPLORER,
        )
        assert ongc_rel.status == CompanyWatchlistStatus.CORE

        # Seamec should be subsea / diving / offshore engineering
        seamec_rel = next(r for r in relationships if r.company_symbol == "SEAMECLTD.NS")
        assert seamec_rel.relationship_type in (
            BeneficiaryRelationshipType.SUBSEA,
            BeneficiaryRelationshipType.OFFSHORE_ENGINEERING,
            BeneficiaryRelationshipType.DRILLING_CONTRACTOR,
        )

    def test_samudra_rules_engine_water_depths(self):
        """Verify water depth classification rules."""
        rules = SamudraRulesEngine()

        assert rules.classify_water_depth(150.0) == "SHALLOW"
        assert rules.classify_water_depth(400.0) == "DEEPWATER"
        assert rules.classify_water_depth(1200.0) == "DEEPWATER"
        assert rules.classify_water_depth(1800.0) == "ULTRA_DEEPWATER"

    def test_samudra_market_sentiment_transmission(self):
        """Verify offshore exploration transmission channels (Brent, dayrates, USD/INR)."""
        engine = MarketSentimentEngine()

        analysis = engine.analyze_scheme_transmission(
            scheme_id="samudra_manthan",
            macro_inputs={
                "brent_crude_usd": 85.50,
                "deepwater_dayrate_usd": 420000,
                "usd_inr": 86.20,
            },
        )

        assert analysis["scheme_id"] == "samudra_manthan"
        assert "transmission_channels" in analysis
        channels = analysis["transmission_channels"]
        assert any("Brent Crude" in ch["factor"] or "Oil Price" in ch["factor"] for ch in channels)
        assert any("Dayrate" in ch["factor"] or "Rig Rate" in ch["factor"] for ch in channels)
        assert any("USD/INR" in ch["factor"] or "Exchange Rate" in ch["factor"] for ch in channels)

    def test_database_migrations_multi_scheme(self, temp_db):
        """Verify multi-scheme tables and columns exist in SQLite database."""
        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            # Check scheme_id in catalysts
            cur = conn.execute("PRAGMA table_info(catalysts);")
            catalyst_cols = [r["name"] for r in cur.fetchall()]
            assert "scheme_id" in catalyst_cols

            # Check scheme_id in setups
            cur = conn.execute("PRAGMA table_info(setups);")
            setup_cols = [r["name"] for r in cur.fetchall()]
            assert "scheme_id" in setup_cols

            # Check new tables exist
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r["name"] for r in cur.fetchall()]
            assert "telegram_sessions" in tables
            assert "entitlements" in tables
            assert "company_scheme_relationships" in tables
            assert "scheme_memory_events" in tables
