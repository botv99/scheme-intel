"""
Tests for Stage 3 Operational Runtime, Health Probes, and Concurrency Protections.
Verifies:
- Snapshot health states (READY, STALE, MISSING, INVALID)
- Strict Fast-Path Protection (no auto-build on query)
- Atomic persistence and schema validation
- Concurrency & double-claim prevention in research queue
- Stale running job recovery after worker crash/timeout
- Research worker continuous loop and graceful shutdown
- Unified SchemeIntelService modes, health checks, and HTTP probe
- Telegram malformed update resilience
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from scheme_intel.intelligence_memory.models import (
    IntelligenceSnapshot,
    CompanyIntelligence,
    SchemeIntelligence,
    PerformanceIntelligence,
    BenchmarkIntelligence,
    SnapshotHealthStatus,
)
from scheme_intel.intelligence_memory.store import IntelligenceStore
from scheme_intel.intelligence_memory.retrieval import FastIntelligenceRetriever, IntelligenceRetrieval
from scheme_intel.intelligence_memory.resolver import IntentResolver, IntentType
from scheme_intel.intelligence_memory.cards import (
    render_health_card,
    render_snapshot_missing,
    render_snapshot_invalid,
)
from scheme_intel.research.models import ResearchJob, ResearchStatus
from scheme_intel.research.queue import ResearchQueue
from scheme_intel.research.worker import ResearchWorker
from scheme_intel.delivery.telegram_router import TelegramMessageRouter
from scheme_intel.delivery.telegram_conversation import TelegramConversationHandler
from scheme_intel.delivery.service import SchemeIntelService, get_system_health


@pytest.fixture
def valid_snapshot() -> IntelligenceSnapshot:
    now_utc = datetime.now(timezone.utc).isoformat()
    return IntelligenceSnapshot(
        snapshot_id="SNAP-RUNTIME-TEST",
        generated_at=now_utc,
        pipeline_run_id="2026-09-27",
        scheme_ids=["gobardhan"],
        schemes={
            "gobardhan": SchemeIntelligence(
                scheme_id="gobardhan",
                name="GOBARdhan",
                description="Galvanizing Organic Bio-Agro Resources Dhan",
                watchlist_count=5,
                qualified_setups_count=1,
                waiting_count=1,
                no_trade_count=3,
                data_unavailable_count=0,
                key_developments=["Commissioned CBG Plant"],
                important_sources=["PIB"],
                last_update=now_utc,
            )
        },
        companies={
            "TRUALT": CompanyIntelligence(
                symbol="TRUALT.NS",
                short_symbol="TRUALT",
                name="TruAlt Bioenergy",
                scheme_id="gobardhan",
                scheme_name="GOBARdhan",
                relevance="High",
                mapping_rationale="CBG producer",
                latest_development="New plant",
                catalyst="Expansion",
                price=440.0,
                change_pct=2.5,
                volume=100000.0,
                avg_volume=80000.0,
                trend="BULLISH",
                support=410.0,
                resistance=450.0,
                rsi=60.0,
                status="QUALIFIED_SETUP",
                archetype="Breakout Anticipation",
                score=90,
                trigger_price=440.0,
                stop_loss=415.0,
                target=480.0,
                bull_thesis="Volume breakout",
                bear_thesis="Resistance near 450",
                risk_summary="R:R 1.6",
                waiting_conditions=[],
                next_session="Tomorrow",
                ai_provider="groq",
                evidence=[],
                updated_at=now_utc,
            )
        },
        qualified_setups=["TRUALT"],
        waiting_setups=[],
        performance=PerformanceIntelligence(
            completed_trades=0,
            validation_threshold=30,
            validation_status="INSUFFICIENT_SAMPLE",
            win_rate=None,
            summary_text="No closed trades.",
            audit_status="PASS",
        ),
        benchmark=BenchmarkIntelligence(
            status="UNAVAILABLE",
            benchmark_id="NIFTY50",
            completed_trades=0,
            trades_evaluated=0,
            strategy_return=None,
            benchmark_return=None,
            excess_return=None,
            win_rate_vs_benchmark_pct=None,
            trade_comparisons=[],
            reason="Insufficient trades",
        ),
    )


# ---------------------------------------------------------------------------
# 1. SNAPSHOT HEALTH & ATOMIC VALIDATION TESTS
# ---------------------------------------------------------------------------

class TestSnapshotHealthAndValidation:
    def test_missing_snapshot(self, tmp_path: Path):
        missing_file = tmp_path / "non_existent.json"
        store = IntelligenceStore(snapshot_path=missing_file)
        status, snap, error = store.load_with_status()
        assert snap is None
        assert status == SnapshotHealthStatus.MISSING
        assert error is not None

        retriever = FastIntelligenceRetriever(store=store, auto_build_if_missing=False)
        r_status, r_snap, r_msg = retriever.get_status()
        assert r_status == SnapshotHealthStatus.MISSING

    def test_invalid_corrupted_snapshot(self, tmp_path: Path):
        corrupt_file = tmp_path / "corrupt.json"
        corrupt_file.write_text("{ this is not valid json : [[", encoding="utf-8")

        store = IntelligenceStore(snapshot_path=corrupt_file)
        status, snap, error = store.load_with_status()
        assert snap is None
        assert status == SnapshotHealthStatus.INVALID
        assert "Invalid JSON" in error

        # Test partial JSON missing required fields
        incomplete_file = tmp_path / "incomplete.json"
        incomplete_file.write_text('{"random_key": 123}', encoding="utf-8")
        store_inc = IntelligenceStore(snapshot_path=incomplete_file)
        status_inc, snap_inc, error_inc = store_inc.load_with_status()
        assert snap_inc is None
        assert status_inc == SnapshotHealthStatus.INVALID
        assert "validation error" in error_inc.lower()

    def test_ready_snapshot(self, tmp_path: Path, valid_snapshot: IntelligenceSnapshot):
        snap_file = tmp_path / "latest.json"
        store = IntelligenceStore(snapshot_path=snap_file)
        store.save(valid_snapshot)

        status, snap, msg = store.load_with_status(freshness_threshold_hours=26.0)
        assert snap is not None
        assert status == SnapshotHealthStatus.READY
        assert "Loaded" in msg
        assert snap.get_age_seconds() < 60

    def test_stale_snapshot(self, tmp_path: Path, valid_snapshot: IntelligenceSnapshot):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=28)).isoformat()
        valid_snapshot.generated_at = old_time
        snap_file = tmp_path / "stale.json"
        store = IntelligenceStore(snapshot_path=snap_file)
        store.save(valid_snapshot)

        status, snap, error = store.load_with_status(freshness_threshold_hours=26.0)
        assert snap is not None
        assert status == SnapshotHealthStatus.STALE
        assert snap.is_stale(threshold_hours=26.0) is True

    def test_auto_build_if_missing_false_prevents_pipeline(self, tmp_path: Path):
        missing_file = tmp_path / "does_not_exist.json"
        store = IntelligenceStore(snapshot_path=missing_file)

        with patch("scheme_intel.intelligence_memory.builder.IntelligenceSnapshotBuilder.build_and_save") as mock_build:
            retriever = FastIntelligenceRetriever(store=store, auto_build_if_missing=False)
            res = retriever.get_company("TRUALT")
            assert res is None
            mock_build.assert_not_called()


# ---------------------------------------------------------------------------
# 2. CONCURRENCY & STALE RECOVERY IN RESEARCH QUEUE
# ---------------------------------------------------------------------------

class TestResearchQueueConcurrency:
    def test_no_double_claim_race(self, tmp_path: Path):
        db_path = tmp_path / "race_test.db"
        queue = ResearchQueue(db_path=db_path)
        job = queue.enqueue_job("Who gets this job?", user_id="u1", chat_id="c1")

        claimed_jobs: list[ResearchJob] = []
        lock = threading.Lock()

        def worker_claim():
            q = ResearchQueue(db_path=db_path)
            claimed = q.claim_next_job()
            if claimed:
                with lock:
                    claimed_jobs.append(claimed)

        threads = [threading.Thread(target=worker_claim) for _ in range(5)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        # Exactly 1 thread must have claimed the single queued job
        assert len(claimed_jobs) == 1
        assert claimed_jobs[0].job_id == job.job_id

    def test_stale_running_job_recovery(self, tmp_path: Path):
        db_path = tmp_path / "stale_test.db"
        queue = ResearchQueue(db_path=db_path)
        job = queue.enqueue_job("Hanging research job", user_id="u1", chat_id="c1")

        claimed = queue.claim_next_job()
        assert claimed is not None
        assert claimed.status == ResearchStatus.RUNNING

        # Simulate job having been started 400 seconds ago (exceeding 300s timeout)
        stale_started = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
        with queue._connect() as conn:
            conn.execute("UPDATE research_jobs SET started_at = ? WHERE job_id = ?", (stale_started, job.job_id))
            conn.commit()

        # Run recovery
        recovered_count = queue.recover_stale_running_jobs(timeout_seconds=300.0)
        assert recovered_count == 1

        recovered_job = queue.get_job(job.job_id)
        assert recovered_job.status == ResearchStatus.QUEUED
        assert recovered_job.started_at is None

        # Confirm another worker can now claim it
        reclaimed = queue.claim_next_job()
        assert reclaimed is not None
        assert reclaimed.job_id == job.job_id


# ---------------------------------------------------------------------------
# 3. RESEARCH WORKER CONTINUOUS LOOP & SHUTDOWN
# ---------------------------------------------------------------------------

class TestResearchWorkerLoop:
    def test_worker_run_forever_and_graceful_stop(self, tmp_path: Path):
        db_path = tmp_path / "worker_loop.db"
        queue = ResearchQueue(db_path=db_path)
        job = queue.enqueue_job("Loop test job", user_id="u1", chat_id="c1")

        worker = ResearchWorker(queue=queue)

        worker_thread = threading.Thread(
            target=worker.run_forever,
            kwargs={"poll_interval": 0.05, "stale_recovery_interval": 0.1, "send_telegram_alert": False},
        )
        worker_thread.start()

        # Wait for worker to pick up and process job
        for _ in range(50):
            time.sleep(0.05)
            j = queue.get_job(job.job_id)
            if j and j.status == ResearchStatus.COMPLETED:
                break

        assert queue.get_job(job.job_id).status == ResearchStatus.COMPLETED

        # Signal stop
        worker.stop()
        worker_thread.join(timeout=2.0)
        assert not worker_thread.is_alive()


# ---------------------------------------------------------------------------
# 4. SYSTEM HEALTH SERVICE & HTTP PROBE
# ---------------------------------------------------------------------------

class TestSystemServiceAndHealth:
    def test_get_system_health_clean_state(self, tmp_path: Path, valid_snapshot: IntelligenceSnapshot):
        snap_file = tmp_path / "latest.json"
        store = IntelligenceStore(snapshot_path=snap_file)
        store.save(valid_snapshot)

        with patch("scheme_intel.intelligence_memory.retrieval.DEFAULT_SNAPSHOT_PATH", snap_file):
            health = get_system_health(data_dir=str(tmp_path))
            assert "status" in health
            assert "is_healthy" in health
            assert "intelligence_memory" in health
            assert health["intelligence_memory"]["health_status"] == SnapshotHealthStatus.READY.value

    def test_service_health_command_resolution(self, tmp_path: Path, valid_snapshot: IntelligenceSnapshot):
        snap_file = tmp_path / "latest.json"
        store = IntelligenceStore(snapshot_path=snap_file)
        store.save(valid_snapshot)

        retriever = FastIntelligenceRetriever(store=store, auto_build_if_missing=False)
        router = TelegramMessageRouter(retriever=retriever)

        # /health command
        resp = router.route_message("/health", user_id="123")
        assert "SCHEME-INTEL OPERATIONAL HEALTH" in resp
        assert "Intelligence Snapshot:" in resp

        # /status command
        resp_status = router.route_message("/status", user_id="123")
        assert "SCHEME-INTEL OPERATIONAL HEALTH" in resp_status

    def test_telegram_conversation_malformed_update(self):
        handler = TelegramConversationHandler()
        # Should gracefully return None without raising an exception
        assert handler.process_update({}, send_reply=False) is None
        assert handler.process_update({"message": {}}, send_reply=False) is None
        assert handler.process_update({"message": {"text": ""}}, send_reply=False) is None

    def test_service_start_stop(self):
        service = SchemeIntelService(mode="worker", worker_poll_interval=0.05)
        t = threading.Thread(target=service.start, daemon=True)
        t.start()
        time.sleep(0.1)
        assert service.is_running is True

        service.stop()
        t.join(timeout=2.0)
        assert service.is_running is False
