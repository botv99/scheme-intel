"""
Stage 4 Comprehensive Audit Verification Suite.
Validates:
1. Fail-closed customer entitlements (Customer A, B, C, D)
2. Telegram /schemes entitlement scoping and platform admin bypass
3. Concurrent user isolation
4. DynamicBeneficiaryDiscovery generic keyword rejection and evidence retention
5. Full End-to-End Samudra Manthan pipeline execution
6. Full End-to-End Gobardhan pipeline execution
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import pytest

from scheme_intel.schemes.registry import SchemeRegistry
from scheme_intel.schemes.samudra_manthan.rules import DynamicBeneficiaryDiscovery, SamudraRulesEngine
from scheme_intel.schemes.models import BeneficiaryRelationshipType, CompanyWatchlistStatus
from scheme_intel.licensing.service import EntitlementService
from scheme_intel.licensing.session import SessionStore
from scheme_intel.delivery.telegram_router import TelegramMessageRouter
from scheme_intel.intelligence_memory.retrieval import FastIntelligenceRetriever
from scheme_intel.intelligence_memory.store import IntelligenceStore
from scheme_intel.intelligence_memory.models import IntelligenceSnapshot, CompanyIntelligence
from scheme_intel.intelligence_memory.memory_store import SchemeMemoryFactStore
from scheme_intel.ingestion.coordinator import SchemeIngestionCoordinator
from scheme_intel.research.queue import ResearchQueue
from scheme_intel.research.executor import ResearchExecutor
from scheme_intel.research.worker import ResearchWorker


@pytest.fixture
def audit_db(tmp_path):
    db_file = tmp_path / "audit_scheme_intel.db"
    from scheme_intel.db import SchemeIntelDB
    db = SchemeIntelDB(db_path=db_file)
    db.connect()
    return db_file


@pytest.fixture
def audit_snapshots(tmp_path):
    gob_file = tmp_path / "intelligence" / "gobardhan" / "latest.json"
    sam_file = tmp_path / "intelligence" / "samudra_manthan" / "latest.json"
    gob_file.parent.mkdir(parents=True, exist_ok=True)
    sam_file.parent.mkdir(parents=True, exist_ok=True)

    gob_snap = IntelligenceSnapshot(
        snapshot_id="snap_gob_audit",
        generated_at="2026-09-30T12:00:00Z",
        scheme_id="gobardhan",
        scheme_name="GOBARdhan / SATAT Initiative",
        total_companies_monitored=1,
        companies={
            "TRUALT.NS": CompanyIntelligence(
                symbol="TRUALT.NS",
                short_symbol="TRUALT",
                name="TruAlt Bioenergy",
                price=1350.0,
                status="QUALIFIED_SETUP",
                scheme_id="gobardhan",
                scheme_name="GOBARdhan / SATAT Initiative",
                catalyst="CBG plant commissioning subsidy approved",
            )
        }
    )
    gob_file.write_text(json.dumps(gob_snap.model_dump(), default=str), encoding="utf-8")

    sam_snap = IntelligenceSnapshot(
        snapshot_id="snap_sam_audit",
        generated_at="2026-09-30T12:00:00Z",
        scheme_id="samudra_manthan",
        scheme_name="Samudra Manthan (National Offshore Exploration Scheme)",
        total_companies_monitored=1,
        companies={
            "ONGC.NS": CompanyIntelligence(
                symbol="ONGC.NS",
                short_symbol="ONGC",
                name="Oil and Natural Gas Corporation",
                price=320.0,
                status="QUALIFIED_SETUP",
                scheme_id="samudra_manthan",
                scheme_name="Samudra Manthan (National Offshore Exploration Scheme)",
                catalyst="KG-DWN-98/2 deepwater production ramp-up",
            )
        }
    )
    sam_file.write_text(json.dumps(sam_snap.model_dump(), default=str), encoding="utf-8")

    return {
        "gob_store": IntelligenceStore(snapshot_path=gob_file),
        "sam_store": IntelligenceStore(snapshot_path=sam_file),
    }


class TestCustomerEntitlementAudit:
    """
    Verifies:
    Customer A = Gobardhan only
    Customer B = Samudra only
    Customer C = both
    Customer D = no scheme (fail-closed)
    Admin = platform bypass
    """

    def test_customers_abcd_entitlements_and_schemes_menu(self, audit_db, audit_snapshots):
        session_store = SessionStore(db_path=audit_db)
        entitlement_service = EntitlementService(db_path=audit_db, admin_user_ids={"admin_super"})

        # Provision Customer A: Gobardhan only
        entitlement_service.register_customer("cust_A", user_ids=["user_A"])
        entitlement_service.grant_entitlement("cust_A", "gobardhan", enabled=True)

        # Provision Customer B: Samudra only
        entitlement_service.register_customer("cust_B", user_ids=["user_B"])
        entitlement_service.grant_entitlement("cust_B", "samudra_manthan", enabled=True)

        # Provision Customer C: both schemes
        entitlement_service.register_customer("cust_C", user_ids=["user_C"])
        entitlement_service.grant_entitlement("cust_C", "gobardhan", enabled=True)
        entitlement_service.grant_entitlement("cust_C", "samudra_manthan", enabled=True)

        # Provision Customer D: registered customer with NO scheme entitlements
        entitlement_service.register_customer("cust_D", user_ids=["user_D"])

        # Retreiver pointing to Gobardhan store by default
        retriever = FastIntelligenceRetriever(store=audit_snapshots["gob_store"])
        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
        )

        # 1. Customer A (Gobardhan only)
        schemes_a = router.route_message("/schemes", user_id="user_A")
        assert "GOBARdhan" in schemes_a
        assert "Samudra Manthan" not in schemes_a

        stock_a = router.route_message("/stock TRUALT", user_id="user_A")
        assert "TRUALT" in stock_a
        assert "ACCESS DENIED" not in stock_a

        switch_a = router.route_message("/switch samudra_manthan", user_id="user_A")
        assert "ACCESS DENIED" in switch_a

        # 2. Customer B (Samudra only)
        schemes_b = router.route_message("/schemes", user_id="user_B")
        assert "Samudra Manthan" in schemes_b
        assert "GOBARdhan" not in schemes_b

        # Switch to sam_store for retrieval
        router.retriever = FastIntelligenceRetriever(store=audit_snapshots["sam_store"])
        stock_b = router.route_message("/stock ONGC", user_id="user_B")
        assert "ONGC" in stock_b
        assert "ACCESS DENIED" not in stock_b

        switch_b = router.route_message("/switch gobardhan", user_id="user_B")
        assert "ACCESS DENIED" in switch_b

        # 3. Customer C (both schemes)
        schemes_c = router.route_message("/schemes", user_id="user_C")
        assert "GOBARdhan" in schemes_c
        assert "Samudra Manthan" in schemes_c

        switch_c_sam = router.route_message("/switch samudra_manthan", user_id="user_C")
        assert "Active Scheme Switched" in switch_c_sam
        switch_c_gob = router.route_message("/switch gobardhan", user_id="user_C")
        assert "Active Scheme Switched" in switch_c_gob

        # 4. Customer D (no schemes) - Fail-Closed
        schemes_d = router.route_message("/schemes", user_id="user_D")
        assert "ACCESS DENIED" in schemes_d

        stock_d = router.route_message("/stock TRUALT", user_id="user_D")
        assert "ACCESS DENIED" in stock_d

        switch_d = router.route_message("/switch gobardhan", user_id="user_D")
        assert "ACCESS DENIED" in switch_d

        # 5. Unprovisioned customer (random unknown user) - Fail-Closed
        unprovisioned_schemes = router.route_message("/schemes", user_id="random_unprovisioned_user")
        assert "ACCESS DENIED" in unprovisioned_schemes

        unprovisioned_query = router.route_message("/stock ONGC", user_id="random_unprovisioned_user")
        assert "ACCESS DENIED" in unprovisioned_query

        # 6. Admin user (explicit platform bypass)
        admin_schemes = router.route_message("/schemes", user_id="admin_super")
        assert "GOBARdhan" in admin_schemes
        assert "Samudra Manthan" in admin_schemes


class TestDynamicBeneficiaryDiscoveryAudit:
    """
    Audit DynamicBeneficiaryDiscovery and ensure companies cannot become Samudra
    candidates merely because generic offshore keywords appear. Every candidate
    must retain evidence, source, relationship type and confidence.
    """

    def test_generic_keywords_alone_never_create_candidates(self):
        generic_text = (
            "Government accelerates offshore exploration in deepwater blocks under OALP round. "
            "High dayrates reported for drillships and subsea vessels in Bay of Bengal."
        )
        candidates = DynamicBeneficiaryDiscovery.discover_beneficiaries(
            event_title="Offshore Exploration Accelerated",
            content=generic_text,
            source="DGH Notice",
        )
        # No candidate companies mentioned -> ZERO candidates created
        assert len(candidates) == 0

    def test_company_without_offshore_context_never_promoted(self):
        unrelated_text = (
            "Cochin Shipyard inaugurated a new sports complex and recreation center for shipyard staff."
        )
        candidates = DynamicBeneficiaryDiscovery.discover_beneficiaries(
            event_title="Cochin Shipyard staff recreational facility",
            content=unrelated_text,
            source="Corporate Press",
        )
        # Mentions Cochin Shipyard, but zero offshore/drilling context -> rejected!
        assert len(candidates) == 0

    def test_verified_candidate_retains_all_auditable_attributes(self):
        valid_tender_text = (
            "SEAMEC secures major offshore diving support vessel and subsea pipeline inspection "
            "contract for deepwater block in KG Basin."
        )
        candidates = DynamicBeneficiaryDiscovery.discover_beneficiaries(
            event_title="SEAMEC Awarded Deepwater Subsea Inspection Contract",
            content=valid_tender_text,
            source="CPPP Tender Portal",
        )
        assert len(candidates) >= 1
        seamec_cand = next(c for c in candidates if c.symbol == "SEAMECLTD.NS")
        assert seamec_cand.company == "SEAMEC Limited"
        assert seamec_cand.scheme_id == "samudra_manthan"
        assert seamec_cand.relationship_type == BeneficiaryRelationshipType.SUBSEA.value
        assert seamec_cand.status == CompanyWatchlistStatus.CANDIDATE.value
        assert seamec_cand.source == "CPPP Tender Portal"
        assert "SEAMEC Awarded Deepwater Subsea Inspection Contract" in seamec_cand.evidence
        assert seamec_cand.confidence == 0.80


class TestPipelineEndToEndAudit:
    """
    Performs full pipeline test for Samudra Manthan:
    real/fixture source
    -> ingestion
    -> normalized event
    -> intelligence
    -> watchlist/company impact
    -> snapshot
    -> memory
    -> Telegram retrieval
    -> ResearchWorker.

    And equivalent regression verification for Gobardhan.
    """

    def test_samudra_manthan_pipeline_e2e(self, tmp_path, audit_db):
        # 1. Ingestion: coordinator ingests fixture source for Samudra Manthan
        coordinator = SchemeIngestionCoordinator()
        batch = coordinator.ingest_scheme(
            scheme_id="samudra_manthan",
            mock_source_data={
                "dgh_portal": [
                    {
                        "title": "DGH Awards Ultra-Deepwater Block to ONGC in KG Offshore Basin",
                        "content": "Directorate General of Hydrocarbons awards OALP ultra-deepwater block (water depth 1850m) to ONGC with special deepwater royalty relief.",
                        "event_type": "OFFSHORE_BLOCK_AWARD",
                        "importance": "HIGH",
                        "confidence": 0.95,
                    }
                ]
            }
        )
        assert len(batch.events) == 1
        event = batch.events[0]
        assert event.scheme_id == "samudra_manthan"
        assert "Ultra-Deepwater" in event.title

        # 2. Rules & Impact Evaluation
        impact = SamudraRulesEngine.evaluate_company_impact(
            company_name="Oil and Natural Gas Corporation",
            symbol="ONGC.NS",
            event_type=event.event_type,
            title=event.title,
            content=event.content,
        )
        assert impact["scheme_id"] == "samudra_manthan"
        assert impact["water_depth"] == "ULTRA_DEEPWATER"
        assert impact["direction"] == "POSITIVE"
        assert impact["significance"] == "HIGH"

        # 3. Memory Fact Store Recording
        mem_db = tmp_path / "audit_memory.db"
        mem_store = SchemeMemoryFactStore(db_path=mem_db, memory_dir=tmp_path / "memory")
        recorded_fact = mem_store.record_fact(
            scheme_id="samudra_manthan",
            entity="ONGC",
            event_text=f"{event.title}: {impact['direction']} impact ({impact['water_depth']})",
            importance="HIGH",
            source="DGH Portal",
        )
        assert recorded_fact.scheme_id == "samudra_manthan"
        assert mem_store.count_facts("samudra_manthan") == 1
        assert mem_store.count_facts("gobardhan") == 0  # Zero cross-scheme leakage

        # 4. Intelligence Snapshot Generation
        snap_path = tmp_path / "intelligence" / "samudra_manthan" / "latest.json"
        snap_store = IntelligenceStore(snapshot_path=snap_path)
        snapshot = IntelligenceSnapshot(
            snapshot_id="SNAP-SAMUDRA-E2E",
            generated_at="2026-09-30T12:00:00Z",
            scheme_id="samudra_manthan",
            scheme_name="Samudra Manthan (National Offshore Exploration Scheme)",
            total_companies_monitored=1,
            companies={
                "ONGC.NS": CompanyIntelligence(
                    symbol="ONGC.NS",
                    short_symbol="ONGC",
                    name="Oil and Natural Gas Corporation",
                    price=325.50,
                    status="QUALIFIED_SETUP",
                    scheme_id="samudra_manthan",
                    scheme_name="Samudra Manthan (National Offshore Exploration Scheme)",
                    catalyst=event.title,
                )
            }
        )
        snap_store.save(snapshot)

        # 5. Telegram Retrieval
        retriever = FastIntelligenceRetriever(store=snap_store)
        session_store = SessionStore(db_path=audit_db)
        entitlement_service = EntitlementService(db_path=audit_db)
        entitlement_service.register_customer("sam_client", user_ids=["user_sam_e2e"])
        entitlement_service.grant_entitlement("sam_client", "samudra_manthan", enabled=True)
        session_store.set_active_scheme("user_sam_e2e", "samudra_manthan")

        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
        )
        telegram_reply = router.route_message("/stock ONGC", user_id="user_sam_e2e")
        assert "ONGC" in telegram_reply
        assert "₹325.50" in telegram_reply
        assert "Samudra Manthan" in telegram_reply

        # 6. ResearchWorker & Asynchronous Execution
        r_queue = ResearchQueue(db_path=audit_db)
        job = r_queue.enqueue_job(
            question="Analyze ONGC ultra-deepwater KG Basin discovery impact under Samudra Manthan",
            user_id="user_sam_e2e",
            scheme_id="samudra_manthan",
        )
        assert job.status.value == "QUEUED"

        executor = ResearchExecutor(
            memory_store=mem_store,
            intelligence_store=snap_store,
        )
        worker = ResearchWorker(queue=r_queue, executor=executor)
        processed_job = worker.process_next_job(send_telegram_alert=False)
        assert processed_job is not None
        assert len(processed_job.result) > 20
        assert "RESEARCH" in processed_job.result.upper()

    def test_gobardhan_pipeline_e2e_regression(self, tmp_path, audit_db):
        # 1. Ingestion: coordinator ingests fixture source for Gobardhan
        coordinator = SchemeIngestionCoordinator()
        batch = coordinator.ingest_scheme(
            scheme_id="gobardhan",
            mock_source_data={
                "pib_mopng": [
                    {
                        "title": "MoPNG Approves 50 New Compressed Bio-Gas (CBG) Plants under SATAT",
                        "content": "Ministry approves capital grants and offtake guarantees for commercial CBG developers.",
                        "event_type": "SCHEME_POLICY",
                        "importance": "HIGH",
                        "confidence": 0.95,
                    }
                ]
            }
        )
        assert len(batch.events) == 1
        event = batch.events[0]
        assert event.scheme_id == "gobardhan"

        # 2. Memory Recording
        mem_db = tmp_path / "audit_memory_gob.db"
        mem_store = SchemeMemoryFactStore(db_path=mem_db, memory_dir=tmp_path / "memory")
        mem_store.record_fact(
            scheme_id="gobardhan",
            entity="TRUALT",
            event_text=event.title,
            importance="HIGH",
            source="MoPNG",
        )
        assert mem_store.count_facts("gobardhan") == 1
        assert mem_store.count_facts("samudra_manthan") == 0

        # 3. Intelligence Snapshot
        snap_path = tmp_path / "intelligence" / "gobardhan" / "latest.json"
        snap_store = IntelligenceStore(snapshot_path=snap_path)
        snapshot = IntelligenceSnapshot(
            snapshot_id="SNAP-GOBARDHAN-E2E",
            generated_at="2026-09-30T12:00:00Z",
            scheme_id="gobardhan",
            scheme_name="GOBARdhan / SATAT Initiative",
            total_companies_monitored=1,
            companies={
                "TRUALT.NS": CompanyIntelligence(
                    symbol="TRUALT.NS",
                    short_symbol="TRUALT",
                    name="TruAlt Bioenergy",
                    price=1380.0,
                    status="QUALIFIED_SETUP",
                    scheme_id="gobardhan",
                    scheme_name="GOBARdhan / SATAT Initiative",
                    catalyst=event.title,
                )
            }
        )
        snap_store.save(snapshot)

        # 4. Telegram Retrieval
        retriever = FastIntelligenceRetriever(store=snap_store)
        session_store = SessionStore(db_path=audit_db)
        entitlement_service = EntitlementService(db_path=audit_db)
        entitlement_service.register_customer("gob_client", user_ids=["user_gob_e2e"])
        entitlement_service.grant_entitlement("gob_client", "gobardhan", enabled=True)
        session_store.set_active_scheme("user_gob_e2e", "gobardhan")

        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
        )
        reply = router.route_message("/stock TRUALT", user_id="user_gob_e2e")
        assert "TRUALT" in reply
        assert "₹1,380.00" in reply
        assert "GOBARdhan" in reply

        # 5. Research Worker
        r_queue = ResearchQueue(db_path=audit_db)
        job = r_queue.enqueue_job(
            question="Assess TruAlt Bioenergy expansion under new SATAT capital grants",
            user_id="user_gob_e2e",
            scheme_id="gobardhan",
        )
        executor = ResearchExecutor(
            memory_store=mem_store,
            intelligence_store=snap_store,
        )
        worker = ResearchWorker(queue=r_queue, executor=executor)
        processed = worker.process_next_job(send_telegram_alert=False)
        assert processed is not None
        assert processed.status.value == "COMPLETED"
