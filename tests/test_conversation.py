"""
Tests for Stage 3: Telegram Conversational Curated Intelligence + Fast Memory Retrieval + Async Research.
Verifies Fast Path (Path A), Deep Research Path (Path B), Intent Resolution,
Persistence, Rate Limiting, and Authorization.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scheme_intel.intelligence_memory.models import (
    IntelligenceSnapshot,
    CompanyIntelligence,
    SchemeIntelligence,
    PerformanceIntelligence,
    BenchmarkIntelligence,
)
from scheme_intel.intelligence_memory.store import IntelligenceStore
from scheme_intel.intelligence_memory.resolver import IntentResolver, ResolvedIntent, IntentType
from scheme_intel.intelligence_memory.retrieval import FastIntelligenceRetriever
from scheme_intel.intelligence_memory.cards import (
    render_stock_card,
    render_why_card,
    render_what_card,
    render_when_card,
    render_scheme_card,
    render_setups_card,
    render_waiting_card,
    render_performance_card,
    render_benchmark_card,
    render_schemes_list_card,
    render_help_card,
    render_unknown_stock,
)
from scheme_intel.intelligence_memory.builder import IntelligenceSnapshotBuilder
from scheme_intel.research.models import ResearchJob, ResearchStatus
from scheme_intel.research.queue import ResearchQueue
from scheme_intel.research.executor import ResearchExecutor
from scheme_intel.research.worker import ResearchWorker
from scheme_intel.delivery.telegram_router import TelegramMessageRouter
from scheme_intel.schemes.registry import SchemeRegistry


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_snapshot() -> IntelligenceSnapshot:
    """Creates a deterministic mock snapshot for testing."""
    now_utc = datetime.now(timezone.utc).isoformat()
    trualt = CompanyIntelligence(
        symbol="TRUALT.NS",
        short_symbol="TRUALT",
        name="TruAlt Bioenergy",
        scheme_id="gobardhan",
        scheme_name="GOBARdhan",
        relevance="High",
        mapping_rationale="Leading CBG producer in India with active SATAT plants.",
        latest_development="Commissioned 100 TPD CBG plant in Karnataka.",
        catalyst="SATAT CBG Expansion (Strength: 90)",
        price=441.90,
        change_pct=3.01,
        volume=185000.0,
        avg_volume=102000.0,
        trend="BULLISH",
        support=410.0,
        resistance=445.0,
        rsi=62.5,
        status="QUALIFIED_SETUP",
        archetype="Breakout Anticipation",
        score=100,
        trigger_price=441.90,
        stop_loss=417.27,
        target=486.23,
        bull_thesis="Strong volume breakout confirmation aligned with SATAT mandates.",
        bear_thesis="Overhead resistance at 445.",
        risk_summary="R:R 1.8:1 | Max Risk 0.56% | Target 486.23",
        waiting_conditions=[],
        next_session="28 Sep 2026",
        ai_provider="groq",
        evidence=[{"source": "NSE", "title": "Plant commissioning disclosure", "date": "2026-09-25"}],
        updated_at=now_utc,
    )
    prajind = CompanyIntelligence(
        symbol="PRAJIND.NS",
        short_symbol="PRAJIND",
        name="Praj Industries",
        scheme_id="gobardhan",
        scheme_name="GOBARdhan",
        relevance="High",
        mapping_rationale="Premier 1G/2G biofuel technology provider.",
        latest_development="Order win for 2G ethanol bio-refinery.",
        catalyst="2G Bio-refinery Contract (Strength: 80)",
        price=520.0,
        change_pct=-0.5,
        volume=80000.0,
        avg_volume=120000.0,
        trend="NEUTRAL",
        support=500.0,
        resistance=540.0,
        rsi=48.0,
        status="WAIT",
        archetype="Pullback",
        score=75,
        trigger_price=535.0,
        stop_loss=495.0,
        target=580.0,
        bull_thesis="Solid order book.",
        bear_thesis="Consolidating below 50 DMA.",
        risk_summary=None,
        waiting_conditions=["Decisive close above 535 with 1.4x volume"],
        next_session="28 Sep 2026",
        ai_provider=None,
        evidence=[],
        updated_at=now_utc,
    )

    snap = IntelligenceSnapshot(
        snapshot_id="SNAP-20260926-TEST",
        generated_at=now_utc,
        pipeline_run_id="2026-09-26",
        scheme_ids=["gobardhan"],
        schemes={
            "gobardhan": SchemeIntelligence(
                scheme_id="gobardhan",
                name="GOBARdhan",
                description="Galvanizing Organic Bio-Agro Resources Dhan",
                watchlist_count=7,
                qualified_setups_count=1,
                waiting_count=1,
                no_trade_count=5,
                data_unavailable_count=0,
                key_developments=["TRUALT: Commissioned 100 TPD CBG plant in Karnataka."],
                important_sources=["PIB MoPNG", "SATAT Portal"],
                last_update=now_utc,
            )
        },
        companies={
            "TRUALT": trualt,
            "TRUALT.NS": trualt,
            "PRAJIND": prajind,
            "PRAJIND.NS": prajind,
        },
        qualified_setups=["TRUALT"],
        waiting_setups=["PRAJIND"],
        performance=PerformanceIntelligence(
            completed_trades=0,
            validation_threshold=30,
            validation_status="INSUFFICIENT_SAMPLE",
            win_rate=None,
            summary_text="0 closed trades. Forward validation requires at least 30 trades.",
            audit_status="PASS",
        ),
        benchmark=BenchmarkIntelligence(
            status="UNAVAILABLE — 0 completed trades",
            benchmark_id="NIFTY50",
            completed_trades=0,
            trades_evaluated=0,
            strategy_return=None,
            benchmark_return=None,
            excess_return=None,
            win_rate_vs_benchmark_pct=None,
            trade_comparisons=[],
            reason="Benchmark evaluation requires at least 1 completed trade.",
        ),
    )
    return snap


@pytest.fixture
def mock_store(tmp_path: Path, sample_snapshot: IntelligenceSnapshot) -> IntelligenceStore:
    path = tmp_path / "latest.json"
    store = IntelligenceStore(snapshot_path=path)
    store.save(sample_snapshot)
    return store


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_research.db"


@pytest.fixture
def test_queue(test_db_path: Path) -> ResearchQueue:
    return ResearchQueue(db_path=test_db_path)


# ---------------------------------------------------------------------------
# 1. INTENT RESOLVER TESTS
# ---------------------------------------------------------------------------

class TestIntentResolver:
    def test_stock_shorthand(self):
        res = IntentResolver.resolve("TRUALT")
        assert res.intent_type == IntentType.STOCK_LOOKUP
        assert res.short_symbol == "TRUALT"

        res_lower = IntentResolver.resolve("trualt")
        assert res_lower.intent_type == IntentType.STOCK_LOOKUP
        assert res_lower.short_symbol == "TRUALT"

    def test_stock_command(self):
        res = IntentResolver.resolve("/stock PRAJIND")
        assert res.intent_type == IntentType.STOCK_LOOKUP
        assert res.short_symbol == "PRAJIND"

    def test_why_what_when_commands(self):
        res_why = IntentResolver.resolve("/why TRUALT")
        assert res_why.intent_type == IntentType.STOCK_WHY
        assert res_why.short_symbol == "TRUALT"

        res_what = IntentResolver.resolve("/what TRUALT")
        assert res_what.intent_type == IntentType.STOCK_WHAT
        assert res_what.short_symbol == "TRUALT"

        res_when = IntentResolver.resolve("/when TRUALT")
        assert res_when.intent_type == IntentType.STOCK_WHEN
        assert res_when.short_symbol == "TRUALT"

    def test_natural_language_queries(self):
        res_why = IntentResolver.resolve("Why is TRUALT in the watchlist?")
        assert res_why.intent_type == IntentType.STOCK_WHY
        assert res_why.short_symbol == "TRUALT"

        res_when = IntentResolver.resolve("When to enter PRAJIND?")
        assert res_when.intent_type == IntentType.STOCK_WHEN
        assert res_when.short_symbol == "PRAJIND"

        res_what = IntentResolver.resolve("What happened to TRUALT?")
        assert res_what.intent_type == IntentType.STOCK_WHAT
        assert res_what.short_symbol == "TRUALT"

    def test_schemes_commands(self):
        res_list = IntentResolver.resolve("/schemes")
        assert res_list.intent_type == IntentType.SCHEMES

        res_scheme = IntentResolver.resolve("/scheme gobardhan")
        assert res_scheme.intent_type == IntentType.SCHEME_LOOKUP
        assert res_scheme.scheme_id == "gobardhan"

    def test_aggregate_status_commands(self):
        assert IntentResolver.resolve("/setups").intent_type == IntentType.SETUPS_LOOKUP
        assert IntentResolver.resolve("/waiting").intent_type == IntentType.WAITING_LOOKUP
        assert IntentResolver.resolve("/performance").intent_type == IntentType.PERFORMANCE_LOOKUP
        assert IntentResolver.resolve("/benchmark").intent_type == IntentType.BENCHMARK_LOOKUP

    def test_research_command(self):
        res = IntentResolver.resolve("/research What are the revised blending targets?")
        assert res.intent_type == IntentType.RESEARCH_REQUEST
        assert "What are the revised blending targets?" in res.parameters.get("question", "")

    def test_help_and_start(self):
        assert IntentResolver.resolve("/start").intent_type == IntentType.START
        assert IntentResolver.resolve("/help").intent_type == IntentType.HELP


# ---------------------------------------------------------------------------
# 2. FAST INTELLIGENCE RETRIEVER & CARDS TESTS
# ---------------------------------------------------------------------------

class TestFastIntelligenceRetrieverAndCards:
    def test_company_retrieval(self, mock_store: IntelligenceStore):
        retriever = FastIntelligenceRetriever(store=mock_store, auto_build_if_missing=False)
        comp = retriever.get_company("TRUALT")
        assert comp is not None
        assert comp.name == "TruAlt Bioenergy"
        assert comp.status == "QUALIFIED_SETUP"

        card = render_stock_card(comp)
        assert "TRUALT" in card
        assert "₹441.90" in card
        assert "Breakout Anticipation" in card

    def test_why_what_when_cards(self, mock_store: IntelligenceStore):
        retriever = FastIntelligenceRetriever(store=mock_store, auto_build_if_missing=False)
        comp = retriever.get_company("TRUALT")
        assert comp is not None

        why_card = render_why_card(comp)
        assert "WHY TRUALT?" in why_card
        assert "Leading CBG producer" in why_card

        what_card = render_what_card(comp)
        assert "WHAT'S HAPPENING — TRUALT" in what_card
        assert "Commissioned 100 TPD CBG plant" in what_card

        when_card = render_when_card(comp)
        assert "WHEN TO WATCH — TRUALT" in when_card
        assert "₹441.90" in when_card

    def test_scheme_cards(self, mock_store: IntelligenceStore):
        retriever = FastIntelligenceRetriever(store=mock_store, auto_build_if_missing=False)
        schemes = retriever.list_schemes()
        assert len(schemes) == 1

        list_card = render_schemes_list_card(schemes)
        assert "SUPPORTED POLICY SCHEMES" in list_card
        assert "gobardhan" in list_card

        scheme_card = render_scheme_card(schemes[0])
        assert "GOBARDHAN" in scheme_card
        assert "Watchlist:" in scheme_card

    def test_setups_and_waiting_cards(self, mock_store: IntelligenceStore):
        retriever = FastIntelligenceRetriever(store=mock_store, auto_build_if_missing=False)
        qualified = retriever.get_qualified_setups()
        assert len(qualified) == 1
        setups_card = render_setups_card(qualified)
        assert "TRUALT" in setups_card

        waiting = retriever.get_waiting_setups()
        assert len(waiting) == 1
        waiting_card = render_waiting_card(waiting)
        assert "PRAJIND" in waiting_card

    def test_performance_and_benchmark_cards(self, mock_store: IntelligenceStore):
        retriever = FastIntelligenceRetriever(store=mock_store, auto_build_if_missing=False)
        perf = retriever.get_performance()
        perf_card = render_performance_card(perf)
        assert "FORWARD PERFORMANCE" in perf_card

        bench = retriever.get_benchmark()
        bench_card = render_benchmark_card(bench)
        assert "NIFTY 50 BENCHMARK" in bench_card

    def test_unknown_stock_handling(self):
        unknown_card = render_unknown_stock("UNKNOWNCO")
        assert "I don't recognize" in unknown_card
        assert "/schemes" in unknown_card

    def test_stale_snapshot_warning(self, tmp_path: Path, sample_snapshot: IntelligenceSnapshot):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        sample_snapshot.generated_at = old_time
        path = tmp_path / "stale.json"
        store = IntelligenceStore(snapshot_path=path)
        store.save(sample_snapshot)

        retriever = FastIntelligenceRetriever(store=store, auto_build_if_missing=False)
        comp = retriever.get_company("TRUALT")
        assert comp is not None

        # Render with is_stale=True
        card = render_stock_card(comp, is_stale=True)
        assert "Snapshot is >26h old" in card


# ---------------------------------------------------------------------------
# 3. RESEARCH QUEUE & PERSISTENCE TESTS
# ---------------------------------------------------------------------------

class TestResearchQueue:
    def test_enqueue_and_get(self, test_queue: ResearchQueue):
        job = test_queue.enqueue_job(
            question="What is the subsidy status for CBG plants?",
            user_id="user_123",
            chat_id="chat_456",
            scheme_id="gobardhan",
        )
        assert job.job_id.startswith("R-")
        assert job.status == ResearchStatus.QUEUED
        assert job.question == "What is the subsidy status for CBG plants?"

        fetched = test_queue.get_job(job.job_id)
        assert fetched is not None
        assert fetched.job_id == job.job_id
        assert fetched.user_id == "user_123"

    def test_claim_next_job(self, test_queue: ResearchQueue):
        j1 = test_queue.enqueue_job("Q1", "u1", "c1")
        j2 = test_queue.enqueue_job("Q2", "u2", "c2")

        claimed = test_queue.claim_next_job()
        assert claimed is not None
        assert claimed.job_id == j1.job_id
        assert claimed.status == ResearchStatus.RUNNING

    def test_mark_completed_and_failed(self, test_queue: ResearchQueue):
        job = test_queue.enqueue_job("Q_Complete", "u1", "c1")
        claimed = test_queue.claim_next_job()
        assert claimed is not None
        test_queue.complete_job(claimed.job_id, "Completed result text", [{"src": "PIB"}])

        c_job = test_queue.get_job(claimed.job_id)
        assert c_job is not None
        assert c_job.status == ResearchStatus.COMPLETED
        assert c_job.result == "Completed result text"
        assert len(c_job.evidence) == 1

        fail_job = test_queue.enqueue_job("Q_Fail", "u1", "c1")
        claimed_fail = test_queue.claim_next_job()
        assert claimed_fail is not None
        test_queue.fail_job(fail_job.job_id, "Network timeout")
        f_job = test_queue.get_job(fail_job.job_id)
        assert f_job is not None
        assert f_job.status == ResearchStatus.FAILED
        assert f_job.error == "Network timeout"

    def test_persistence_across_instances(self, test_db_path: Path):
        q1 = ResearchQueue(db_path=test_db_path)
        job = q1.enqueue_job("Persist Test", "u1", "c1")

        # Reopen with new instance against same SQLite file
        q2 = ResearchQueue(db_path=test_db_path)
        persisted = q2.get_job(job.job_id)
        assert persisted is not None
        assert persisted.question == "Persist Test"


# ---------------------------------------------------------------------------
# 4. TELEGRAM MESSAGE ROUTER TESTS (ROUTING, AUTH, RATE LIMITING)
# ---------------------------------------------------------------------------

class TestTelegramMessageRouter:
    def test_fast_path_routing(self, mock_store: IntelligenceStore, test_queue: ResearchQueue):
        retriever = FastIntelligenceRetriever(store=mock_store, auto_build_if_missing=False)
        router = TelegramMessageRouter(retriever=retriever, research_queue=test_queue)
        resp = router.route_message("TRUALT", user_id="123")
        assert "TRUALT" in resp
        assert "QUALIFIED_SETUP" in resp

    def test_authorization_block(self, mock_store: IntelligenceStore, test_queue: ResearchQueue):
        retriever = FastIntelligenceRetriever(store=mock_store, auto_build_if_missing=False)
        with patch.dict("os.environ", {"TELEGRAM_ALLOWED_USER_IDS": "999,888"}):
            router = TelegramMessageRouter(retriever=retriever, research_queue=test_queue)
            unauth = router.route_message("TRUALT", user_id="123")
            assert "Unauthorized" in unauth

            auth = router.route_message("TRUALT", user_id="999")
            assert "TRUALT" in auth

    def test_research_path_routing(self, mock_store: IntelligenceStore, test_queue: ResearchQueue):
        retriever = FastIntelligenceRetriever(store=mock_store, auto_build_if_missing=False)
        router = TelegramMessageRouter(retriever=retriever, research_queue=test_queue)
        resp = router.route_message("/research What are the revised SATAT targets?", user_id="123", chat_id="456")
        assert "Research request received" in resp
        assert "Research ID:" in resp
        assert "Status:* `QUEUED`" in resp

    def test_research_rate_limiting(self, mock_store: IntelligenceStore, test_queue: ResearchQueue):
        retriever = FastIntelligenceRetriever(store=mock_store, auto_build_if_missing=False)
        router = TelegramMessageRouter(retriever=retriever, research_queue=test_queue, research_cooldown_seconds=60)
        # First request succeeds
        r1 = router.route_message("/research First query", user_id="123")
        assert "QUEUED" in r1

        # Second immediate request hits rate limit
        r2 = router.route_message("/research Second query", user_id="123")
        assert "Rate Limit Reached" in r2

        # Different user is not blocked
        r3 = router.route_message("/research Query from another user", user_id="456")
        assert "QUEUED" in r3


# ---------------------------------------------------------------------------
# 5. RESEARCH EXECUTOR & WORKER TESTS
# ---------------------------------------------------------------------------

class TestResearchWorker:
    def test_executor_deterministic_synthesis(self):
        executor = ResearchExecutor()
        scheme = SchemeRegistry.get_active()
        findings, why, affected = executor._synthesize(
            question="What is the latest CBG procurement policy?",
            scheme=scheme,
            evidence=[{"source": "PIB", "title": "SATAT CBG Procurement Notification", "date": "2026-09-26"}],
        )
        assert len(findings) > 0
        assert "GOBARdhan" in why or "commercial" in why or "procurement" in why

    def test_worker_end_to_end(self, test_queue: ResearchQueue):
        job = test_queue.enqueue_job("Test CBG query", user_id="123", chat_id="456")

        with patch("scheme_intel.research.worker.send_telegram") as mock_send:
            worker = ResearchWorker(queue=test_queue)
            processed = worker.process_next_job(send_telegram_alert=True)
            assert processed is not None
            assert processed.job_id == job.job_id
            assert processed.status == ResearchStatus.COMPLETED

            mock_send.assert_called_once()
            args, kwargs = mock_send.call_args
            assert "RESEARCH COMPLETE" in args[0]
            assert kwargs.get("chat_ids") == ["456"]
