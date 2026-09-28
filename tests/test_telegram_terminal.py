"""
Comprehensive tests for Stage 3 Telegram Curated Terminal, Intent Resolution,
API Resilience, Snapshot Synchronization, and Real Component Health Reporting.
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
from scheme_intel.intelligence_memory.retrieval import FastIntelligenceRetriever
from scheme_intel.intelligence_memory.resolver import IntentResolver, IntentType
from scheme_intel.intelligence_memory.syncer import SnapshotSyncer
from scheme_intel.research.queue import ResearchQueue
from scheme_intel.research.models import ResearchStatus
from scheme_intel.delivery.telegram_router import TelegramMessageRouter
from scheme_intel.delivery.telegram_conversation import TelegramConversationHandler
from scheme_intel.delivery.request_store import RequestStore
from scheme_intel.delivery.service import SchemeIntelService, get_system_health
from scheme_intel.notifier import send_telegram
from scheme_intel.exceptions import TelegramError


@pytest.fixture
def terminal_snapshot() -> IntelligenceSnapshot:
    now_utc = datetime.now(timezone.utc).isoformat()
    return IntelligenceSnapshot(
        snapshot_id="SNAP-TERMINAL-TEST",
        generated_at=now_utc,
        pipeline_run_id="2026-09-27",
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
            "TRUALT": CompanyIntelligence(
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
            ),
            "PRAJIND": CompanyIntelligence(
                symbol="PRAJIND.NS",
                short_symbol="PRAJIND",
                name="Praj Industries",
                scheme_id="gobardhan",
                scheme_name="GOBARdhan",
                relevance="High",
                mapping_rationale="Premier 1G/2G biofuel technology provider.",
                latest_development="Order win for 2G ethanol bio-refinery.",
                catalyst="2G Bio-refinery Contract",
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
            ),
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


@pytest.fixture
def terminal_handler(tmp_path: Path, terminal_snapshot: IntelligenceSnapshot) -> TelegramConversationHandler:
    snap_path = tmp_path / "latest.json"
    store = IntelligenceStore(snapshot_path=snap_path)
    store.save(terminal_snapshot)

    retriever = FastIntelligenceRetriever(store=store, auto_build_if_missing=False)
    q_path = tmp_path / "test_terminal.db"
    queue = ResearchQueue(db_path=q_path)
    req_store = RequestStore(db_path=str(tmp_path / "test_reqs.db"))
    router = TelegramMessageRouter(retriever=retriever, research_queue=queue, request_store=req_store)
    return TelegramConversationHandler(router=router)


# ---------------------------------------------------------------------------
# 1. RAW MESSAGE NEVER ECHOED & CURATED CARD INTEGRITY
# ---------------------------------------------------------------------------

class TestRawMessageNeverEchoed:
    def test_stock_query_returns_curated_card_never_echo(self, terminal_handler: TelegramConversationHandler):
        # Shorthand "TRUALT"
        resp = terminal_handler.handle_message("TRUALT")
        assert resp != "TRUALT"
        assert "TRUALT" in resp
        assert "TruAlt Bioenergy" in resp
        assert "QUALIFIED_SETUP" in resp
        assert "₹441.90" in resp

    def test_unknown_query_returns_curated_guide_never_echo(self, terminal_handler: TelegramConversationHandler):
        # 1. Unmapped short keyword returns curated command menu
        resp_menu = terminal_handler.handle_message("foobarxyz")
        assert resp_menu != "foobarxyz"
        assert "SCHEME-INTEL" in resp_menu
        assert "/research <question>" in resp_menu

        # 2. General complex question routes to workflow acknowledgement
        random_input = "Can you help me with an arbitrary financial question?"
        resp_question = terminal_handler.handle_message(random_input)
        assert resp_question != random_input
        assert ("Request received" in resp_question or "SCHEME-INTEL" in resp_question)

    def test_empty_or_whitespace_input_handled_gracefully(self, terminal_handler: TelegramConversationHandler):
        assert terminal_handler.handle_message("") == ""
        assert terminal_handler.handle_message("   ") == ""


# ---------------------------------------------------------------------------
# 2. INTENT RESOLUTION & CURATED QUERY MATRIX
# ---------------------------------------------------------------------------

class TestCuratedQueryMatrix:
    def test_all_standard_query_types(self, terminal_handler: TelegramConversationHandler):
        matrix = [
            ("TRUALT", ["TRUALT", "TruAlt Bioenergy", "QUALIFIED_SETUP"]),
            ("/stock TRUALT", ["TRUALT", "TruAlt Bioenergy"]),
            ("/stock@SchemeIntelBot TRUALT", ["TRUALT", "TruAlt Bioenergy"]),
            ("why TRUALT", ["WHY TRUALT?", "Leading CBG producer"]),
            ("/why TRUALT", ["WHY TRUALT?"]),
            ("why is trualt interesting", ["WHY TRUALT?"]),
            ("what TRUALT", ["WHAT'S HAPPENING — TRUALT"]),
            ("/what TRUALT", ["WHAT'S HAPPENING — TRUALT"]),
            ("what is happening with TRUALT", ["WHAT'S HAPPENING — TRUALT"]),
            ("what about trualt", ["WHAT'S HAPPENING — TRUALT"]),
            ("tell me about trualt", ["WHAT'S HAPPENING — TRUALT"]),
            ("when TRUALT", ["WHEN TO WATCH — TRUALT"]),
            ("/when TRUALT", ["WHEN TO WATCH — TRUALT"]),
            ("when to enter TRUALT", ["WHEN TO WATCH — TRUALT", "₹441.90"]),
            ("/setups", ["QUALIFIED SETUPS", "TRUALT"]),
            ("what are today's setups", ["QUALIFIED SETUPS", "TRUALT"]),
            ("/waiting", ["WAITING SETUPS", "PRAJIND"]),
            ("which stocks are waiting", ["WAITING SETUPS", "PRAJIND"]),
            ("/schemes", ["SUPPORTED POLICY SCHEMES", "gobardhan"]),
            ("/scheme gobardhan", ["GOBARDHAN", "Galvanizing Organic"]),
            ("how is gobardhan doing", ["GOBARDHAN"]),
            ("/performance", ["FORWARD PERFORMANCE", "INSUFFICIENT_SAMPLE"]),
            ("/benchmark", ["NIFTY 50 BENCHMARK", "UNAVAILABLE"]),
            ("/help", ["SCHEME-INTEL TERMINAL", "FAST INTELLIGENCE"]),
            ("/start", ["SCHEME-INTEL TERMINAL", "Intelligence Terminal"]),
        ]

        for query, expected_substrings in matrix:
            response = terminal_handler.handle_message(query)
            assert response != query, f"Raw query was echoed for: '{query}'"
            for sub in expected_substrings:
                assert sub in response, f"Substring '{sub}' missing in response for query: '{query}'"


# ---------------------------------------------------------------------------
# 3. AUTHORIZATION BEHAVIOR
# ---------------------------------------------------------------------------

class TestAuthorizationGatekeeper:
    def test_unauthorized_user_message(self, tmp_path: Path, terminal_snapshot: IntelligenceSnapshot):
        snap_path = tmp_path / "latest.json"
        store = IntelligenceStore(snapshot_path=snap_path)
        store.save(terminal_snapshot)

        retriever = FastIntelligenceRetriever(store=store, auto_build_if_missing=False)
        router = TelegramMessageRouter(
            retriever=retriever,
            allowed_user_ids={"999", "888"},
        )
        handler = TelegramConversationHandler(router=router)

        # Blocked user
        resp = handler.handle_message("TRUALT", user_id="123")
        assert "⛔ This Telegram account/chat is not authorized to use Scheme-Intel." in resp

        # Allowed user
        resp_allowed = handler.handle_message("TRUALT", user_id="999")
        assert "TRUALT" in resp_allowed
        assert "TruAlt Bioenergy" in resp_allowed


# ---------------------------------------------------------------------------
# 4. TELEGRAM API RESILIENCE & PARSE ERROR FALLBACK
# ---------------------------------------------------------------------------

class TestTelegramApiResilience:
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "mock_token", "TELEGRAM_CHAT_ID": "12345"})
    def test_entity_parse_failure_fallback_to_plain_text(self):
        """When Telegram returns HTTP 400 'can't parse entities', it automatically retries with plain text."""
        with patch("scheme_intel.notifier.requests.post") as mock_post:
            resp_400 = MagicMock()
            resp_400.status_code = 400
            resp_400.json.return_value = {"ok": False, "description": "Bad Request: can't parse entities"}

            resp_200 = MagicMock()
            resp_200.status_code = 200
            resp_200.json.return_value = {"ok": True}

            mock_post.side_effect = [resp_400, resp_200]

            success = send_telegram("Unclosed *markdown _entity", chat_ids=["12345"], parse_mode="Markdown")
            assert success is True
            assert mock_post.call_count == 2
            # Second call should not have parse_mode in payload
            second_call_payload = mock_post.call_args_list[1][1]["json"]
            assert "parse_mode" not in second_call_payload


# ---------------------------------------------------------------------------
# 5. POLLING OFFSET ADVANCEMENT
# ---------------------------------------------------------------------------

class TestPollingOffsetAdvancement:
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "mock_token"})
    def test_polling_advances_offset(self, terminal_handler: TelegramConversationHandler):
        updates = [
            {"update_id": 101, "message": {"text": "TRUALT", "chat": {"id": 123}, "from": {"id": 456}}},
            {"update_id": 102, "message": {"text": "/setups", "chat": {"id": 123}, "from": {"id": 456}}},
        ]

        with patch("scheme_intel.delivery.telegram_conversation.requests.get") as mock_get, \
             patch("scheme_intel.delivery.telegram_conversation.send_telegram") as mock_send:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"ok": True, "result": updates}
            mock_get.return_value = mock_resp

            # Run polling for 1 iteration
            terminal_handler.run_polling(interval_seconds=0, stop_after_runs=1)

            assert mock_send.call_count == 2
            # Verify the call to getUpdates used initial offset
            get_update_calls = [c for c in mock_get.call_args_list if "params" in c[1]]
            assert len(get_update_calls) >= 1
            first_call_params = get_update_calls[0][1]["params"]
            assert first_call_params["offset"] == 0


# ---------------------------------------------------------------------------
# 6. ASYNC RESEARCH WORKFLOW (NO BLEED INTO FAST PATH)
# ---------------------------------------------------------------------------

class TestResearchAsyncWorkflow:
    def test_research_returns_immediate_ack(self, terminal_handler: TelegramConversationHandler):
        resp = terminal_handler.handle_message(
            "/research What is the latest Gobardhan subsidy policy?",
            user_id="u1",
            chat_id="c1",
        )
        assert "Research queued" in resp or "DEEP RESEARCH STARTED" in resp
        assert "Request ID" in resp

    def test_fast_path_never_invokes_research(self, terminal_handler: TelegramConversationHandler):
        # A normal stock query must NOT enqueue a research job
        with patch.object(terminal_handler.router.research_queue, "enqueue_job") as mock_enqueue:
            terminal_handler.handle_message("TRUALT")
            mock_enqueue.assert_not_called()


# ---------------------------------------------------------------------------
# 7. SNAPSHOT SYNCHRONIZATION (OPTION A: GITHUB PULL)
# ---------------------------------------------------------------------------

class TestSnapshotSyncer:
    def test_syncer_adopts_newer_remote_snapshot(self, tmp_path: Path, terminal_snapshot: IntelligenceSnapshot):
        local_store = IntelligenceStore(snapshot_path=tmp_path / "local.json")
        # Save local snapshot with older timestamp
        terminal_snapshot.generated_at = "2026-09-25T10:00:00Z"
        terminal_snapshot.snapshot_id = "SNAP-LOCAL-OLD"
        local_store.save(terminal_snapshot)

        # Remote has newer snapshot
        newer_snap = terminal_snapshot.model_copy()
        newer_snap.generated_at = "2026-09-27T10:00:00Z"
        newer_snap.snapshot_id = "SNAP-REMOTE-NEW"

        syncer = SnapshotSyncer(store=local_store, enabled=True)

        with patch("scheme_intel.intelligence_memory.syncer.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = newer_snap.model_dump_json()
            mock_get.return_value = mock_resp

            updated = syncer.sync_once()
            assert updated is True
            assert syncer.last_sync_status == "UPDATED"

            # Check that local store now loads the new snapshot
            status, snap, _ = local_store.load_with_status()
            assert snap.snapshot_id == "SNAP-REMOTE-NEW"

    def test_syncer_ignores_older_remote_snapshot(self, tmp_path: Path, terminal_snapshot: IntelligenceSnapshot):
        local_store = IntelligenceStore(snapshot_path=tmp_path / "local.json")
        terminal_snapshot.generated_at = "2026-09-27T12:00:00Z"
        terminal_snapshot.snapshot_id = "SNAP-LOCAL-NEWEST"
        local_store.save(terminal_snapshot)

        older_snap = terminal_snapshot.model_copy()
        older_snap.generated_at = "2026-09-25T10:00:00Z"
        older_snap.snapshot_id = "SNAP-REMOTE-OLD"

        syncer = SnapshotSyncer(store=local_store, enabled=True)

        with patch("scheme_intel.intelligence_memory.syncer.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = older_snap.model_dump_json()
            mock_get.return_value = mock_resp

            updated = syncer.sync_once()
            assert updated is False
            assert syncer.last_sync_status == "UP_TO_DATE"
            status, snap, _ = local_store.load_with_status()
            assert snap.snapshot_id == "SNAP-LOCAL-NEWEST"


# ---------------------------------------------------------------------------
# 8. REAL COMPONENT HEALTH REPORTING & THREAD LIVENESS
# ---------------------------------------------------------------------------

class TestRealComponentHealthReporting:
    def test_running_service_reports_live_component_states(self):
        service = SchemeIntelService(mode="worker", worker_poll_interval=0.05, sync_snapshot=False)
        thread = threading.Thread(target=service.start, daemon=True)
        thread.start()
        for _ in range(30):
            if service.get_component_status().get("research_worker") == "RUNNING":
                break
            time.sleep(0.05)

        components = service.get_component_status()
        assert components["research_worker"] == "RUNNING"
        assert components["telegram"] == "DISABLED"

        health = get_system_health(service_instance=service)
        assert health["components"]["research_worker"] == "RUNNING"

        service.stop()
        thread.join(timeout=2.0)
        assert service.get_component_status()["research_worker"] == "STOPPED"
