"""Comprehensive End-to-End Pipeline Tests for Samudra Manthan (Stage 4B -> 4C -> 4D).

Verifies the complete execution sequence:
1. Ingestion: Source fixtures -> Adapters -> Parsers -> Normalizers -> Deduplication.
2. Rule Execution: Samudra rule engine -> Water depth classification -> Relationship graph.
3. Candidate Promotion: Candidate promotion criteria -> Promoted vs unpromoted entities.
4. Memory & Snapshot: Memory fact store -> IntelligenceSnapshotBuilder with Quality Gate.
5. Cross-Scheme Isolation: Samudra vs Gobardhan separation with zero contamination.
6. Entitlements & Access Control: Allowed customers vs Unauthorized customers (fail-closed).
7. Research Pathway: Scheme research executor operates on scheme facts without cross-scheme leakage.
8. Fault Isolation: Unreachable / failing source does not crash pipeline.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.scheme_intel.schemes.registry import SchemeRegistry
from src.scheme_intel.ingestion.coordinator import SchemeIngestionCoordinator
from src.scheme_intel.ingestion.models import NormalizedSchemeEvent
from src.scheme_intel.intelligence_memory.builder import IntelligenceSnapshotBuilder
from src.scheme_intel.intelligence_memory.store import SchemeMemoryFactStore
from src.scheme_intel.licensing.service import EntitlementService
from src.scheme_intel.research.queue import ResearchQueue
from src.scheme_intel.research.executor import ResearchExecutor
from src.scheme_intel.research.worker import ResearchWorker
from src.scheme_intel.schemes.samudra_manthan.relevance import SamudraRelevanceFilter
from src.scheme_intel.schemes.samudra_manthan.rules import (
    evaluate_candidate_promotion,
    build_relationship_graph_node,
    discover_from_normalized_event,
    OFFSHORE_CANDIDATE_REGISTRY,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "samudra"


@pytest.fixture
def mock_samudra_sources_response():
    """Mock HTTP responses for Samudra sources using local test fixtures."""
    fixtures = {
        "dghindia.gov.in": (FIXTURES_DIR / "dgh_fixture.html").read_text(encoding="utf-8"),
        "mopng": (FIXTURES_DIR / "pib_mopng_fixture.xml").read_text(encoding="utf-8"),
        "energy": (FIXTURES_DIR / "pib_energy_fixture.xml").read_text(encoding="utf-8"),
        "pmindia.gov.in": (FIXTURES_DIR / "pmo_fixture.html").read_text(encoding="utf-8"),
        "eprocure.gov.in": (FIXTURES_DIR / "cppp_fixture.html").read_text(encoding="utf-8"),
        "ongcindia.com": (FIXTURES_DIR / "ongc_fixture.html").read_text(encoding="utf-8"),
        "oil-india.com": (FIXTURES_DIR / "oil_india_fixture.html").read_text(encoding="utf-8"),
        "ril.com": (FIXTURES_DIR / "ril_fixture.html").read_text(encoding="utf-8"),
        "vedantalimited.com": (FIXTURES_DIR / "vedanta_fixture.html").read_text(encoding="utf-8"),
        "nseindia.com": (FIXTURES_DIR / "nse_filings_fixture.json").read_text(encoding="utf-8"),
        "bseindia.com": (FIXTURES_DIR / "bse_announcements_fixture.json").read_text(encoding="utf-8"),
    }

    def _get_mock(url, *args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        for domain, content in fixtures.items():
            if domain in url:
                mock_resp.text = content
                if content.strip().startswith("{"):
                    mock_resp.json.return_value = json.loads(content)
                return mock_resp
        mock_resp.text = "<html><body>No data</body></html>"
        mock_resp.json.return_value = {}
        return mock_resp

    return _get_mock


class TestSamudraPipelineE2E:
    """Full End-to-End Pipeline test for Samudra Manthan."""

    def test_full_samudra_manthan_lifecycle(self, mock_samudra_sources_response):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            fact_store = SchemeMemoryFactStore(
                db_path=tmp_path / "memory.db",
                memory_dir=tmp_path / "memory",
            )

            # 1. Ingestion: Coordinator runs for samudra_manthan
            coordinator = SchemeIngestionCoordinator()
            with patch("requests.get", side_effect=mock_samudra_sources_response):
                batch = coordinator.run_ingestion(scheme_id="samudra_manthan")

            # Verify batch ingestion results
            assert batch is not None
            assert batch.scheme_id == "samudra_manthan"
            assert len(batch.raw_documents) > 0
            assert len(batch.normalized_events) > 0
            assert len(batch.source_health_records) > 0

            # Verify all events belong strictly to samudra_manthan
            for ev in batch.normalized_events:
                assert ev.scheme_id == "samudra_manthan"
                # Strict check: zero Gobardhan content
                assert "gobardhan" not in ev.title.lower()
                assert "compressed biogas" not in ev.title.lower()

            # 2. Rule & Relationship Processing
            discovered_candidates = []
            relationship_graph = []
            for ev in batch.normalized_events:
                node = build_relationship_graph_node(ev)
                if node.get("companies"):
                    relationship_graph.append(node)
                discovered = discover_from_normalized_event(ev)
                discovered_candidates.extend(discovered)

            assert len(relationship_graph) > 0

            # Candidate promotion evaluation
            deep_promoted = evaluate_candidate_promotion("DEEP INDUSTRIES", batch.normalized_events)
            assert deep_promoted is True  # Received ONGC charter contract in NSE fixture

            alphageo_promoted = evaluate_candidate_promotion("ALPHAGEO", batch.normalized_events)
            assert alphageo_promoted is True  # Received Oil India seismic survey in BSE fixture

            # 3. Memory Fact Ingestion
            for ev in batch.normalized_events:
                fact_store.ingest_event(
                    scheme_id="samudra_manthan",
                    event_id=ev.event_id,
                    fact_type="event",
                    title=ev.title,
                    content=ev.content,
                    confidence=ev.confidence,
                    importance=ev.importance,
                    metadata={
                        "companies": ev.companies,
                        "projects": ev.projects,
                        "contracts": ev.contracts,
                        "water_depth": ev.water_depth,
                        "relevance_reason": ev.relevance_reason,
                    }
                )

            facts = fact_store.query_facts(scheme_id="samudra_manthan")
            assert len(facts) == len(batch.normalized_events)

            # 4. Intelligence Snapshot Builder & Quality Gate
            builder = IntelligenceSnapshotBuilder(fact_store=fact_store)
            snapshot = builder.build(scheme_id="samudra_manthan")

            assert snapshot is not None
            assert snapshot.scheme_id == "samudra_manthan" or "samudra_manthan" in snapshot.scheme_ids
            assert snapshot.quality_gate_status != "DEGRADED"
            assert "samudra_manthan" in snapshot.schemes
            sam_intel = snapshot.schemes["samudra_manthan"]
            assert len(sam_intel.active_beneficiaries) > 0

            # 5. Customer Entitlements & Access Control (Fail-Closed)
            entitlements = EntitlementService(db_path=tmp_path / "entitlements.db")
            entitlements.register_customer(customer_id="cust_deepwater_corp", name="Deepwater Corp")
            entitlements.grant_entitlement(
                customer_id="cust_deepwater_corp",
                scheme_id="samudra_manthan",
                enabled=True,
                tier="enterprise",
            )

            entitlements.register_customer(customer_id="cust_biogas_user", name="Biogas User")
            entitlements.grant_entitlement(
                customer_id="cust_biogas_user",
                scheme_id="gobardhan",
                enabled=True,
                tier="enterprise",
            )

            # Customer with samudra_manthan entitlement can access
            assert entitlements.has_scheme_access(customer_id="cust_deepwater_corp", scheme_id="samudra_manthan") is True
            # Customer without samudra_manthan entitlement is denied
            assert entitlements.has_scheme_access(customer_id="cust_biogas_user", scheme_id="samudra_manthan") is False

            # 6. Research Pathway & Isolation
            queue = ResearchQueue(db_path=tmp_path / "research.db")
            executor = ResearchExecutor(memory_store=fact_store)
            worker = ResearchWorker(queue=queue, executor=executor)

            job = queue.enqueue_job(
                question="What are the latest ultra-deepwater exploration tenders and discoveries in KG Basin?",
                scheme_id="samudra_manthan",
                user_id="cust_deepwater_corp",
            )
            processed_job = worker.process_next_job(send_telegram_alert=False)

            assert processed_job is not None
            assert processed_job.status.value in ("COMPLETED", "completed")
            assert processed_job.result_text is not None
            res_text = processed_job.result_text.lower()
            assert "gobardhan" not in res_text
            assert "biogas" not in res_text


class TestCrossSchemeContaminationZeroTolerance:
    """Verifies that Gobardhan and Samudra Manthan pipelines are completely isolated."""

    def test_zero_cross_scheme_leakage(self, mock_samudra_sources_response):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            fact_store = SchemeMemoryFactStore(
                db_path=tmp_path / "memory.db",
                memory_dir=tmp_path / "memory",
            )

            # Ingest Samudra events
            coordinator = SchemeIngestionCoordinator()
            with patch("requests.get", side_effect=mock_samudra_sources_response):
                samudra_batch = coordinator.run_ingestion(scheme_id="samudra_manthan")

            for ev in samudra_batch.normalized_events:
                fact_store.ingest_event(
                    scheme_id="samudra_manthan",
                    event_id=ev.event_id,
                    fact_type="event",
                    title=ev.title,
                    content=ev.content,
                    confidence=ev.confidence,
                )

            # Ingest simulated Gobardhan event
            fact_store.ingest_event(
                scheme_id="gobardhan",
                event_id="gobardhan-sample-01",
                fact_type="event",
                title="Ministry of Jal Shakti approves 15 new CBG plants in Uttar Pradesh",
                content="Subsidy under Gobardhan scheme released.",
                confidence=0.95,
            )

            # Build snapshots
            builder = IntelligenceSnapshotBuilder(fact_store=fact_store)
            samudra_snapshot = builder.build(scheme_id="samudra_manthan")
            gobardhan_snapshot = builder.build(scheme_id="gobardhan")

            # Samudra snapshot must contain ZERO Gobardhan facts
            samudra_facts_text = json.dumps(samudra_snapshot.to_dict()).lower()
            assert "jal shakti" not in samudra_facts_text
            assert "cbg" not in samudra_facts_text
            assert "gobardhan-sample-01" not in samudra_facts_text

            # Gobardhan snapshot must contain ZERO Samudra facts
            gobardhan_facts_text = json.dumps(gobardhan_snapshot.to_dict()).lower()
            assert "deepwater" not in gobardhan_facts_text
            assert "oalp round" not in gobardhan_facts_text
            assert "kg-dwn-98/2" not in gobardhan_facts_text
            assert len(gobardhan_snapshot.schemes["gobardhan"].oalp_developments) == 0
            assert len(gobardhan_snapshot.schemes["gobardhan"].offshore_activity) == 0


class TestSourceFaultIsolation:
    """Verifies that failure of a single source adapter never crashes the entire ingestion run."""

    def test_single_source_failure_does_not_abort_pipeline(self):
        def _failing_get(url, *args, **kwargs):
            if "dghindia" in url:
                raise ConnectionError("DGH portal down with 502 Bad Gateway")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.ok = True
            mock_resp.text = (FIXTURES_DIR / "pib_mopng_fixture.xml").read_text(encoding="utf-8")
            return mock_resp

        coordinator = SchemeIngestionCoordinator()
        with patch("requests.get", side_effect=_failing_get):
            batch = coordinator.run_ingestion(scheme_id="samudra_manthan")

            # Pipeline must not raise exception and must succeed with other sources
            assert batch is not None
            assert len(batch.normalized_events) > 0

            # DGH should be logged as error in source health records
            dgh_health = next((r for r in batch.source_health_records if r.source_id == "dgh_portal"), None)
            assert dgh_health is not None
            assert dgh_health.status in ("error", "degraded", "blocked", "failed", "FAILED")
