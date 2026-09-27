"""
Architectural Verification Tests for Scheme-Intel Stage 3:
Telegram Intelligence Terminal + Event-Driven GitHub Actions Workflow (04-telegram-query.yml).
Verifies:
- Three execution paths: FAST, WORKFLOW, RESEARCH
- Webhook conflict detection
- Request logging & unique request IDs
- Chat isolation & strict non-broadcast guarantee
- Idempotency via update_id and request status
- Stock aliases & shortcuts (/trualt, /praj, /why prompt)
- Bot commands registration
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import requests

from scheme_intel.delivery.request_store import RequestStore, RequestStatus, ExecutionPath, TelegramRequest
from scheme_intel.delivery.github_dispatcher import GitHubWorkflowDispatcher
from scheme_intel.delivery.query_engine import ComplexQueryEngine
from scheme_intel.delivery.workflow_query_runner import process_workflow_query
from scheme_intel.delivery.telegram_router import TelegramMessageRouter
from scheme_intel.delivery.telegram_conversation import (
    TelegramConversationHandler,
    check_webhook_conflict,
    register_bot_commands,
    answer_callback_query,
)
from scheme_intel.intelligence_memory.models import (
    IntelligenceSnapshot,
    CompanyIntelligence,
    SchemeIntelligence,
    PerformanceIntelligence,
    BenchmarkIntelligence,
)
from scheme_intel.intelligence_memory.store import IntelligenceStore
from scheme_intel.intelligence_memory.retrieval import FastIntelligenceRetriever
from scheme_intel.intelligence_memory.resolver import IntentResolver, IntentType
from scheme_intel.research.queue import ResearchQueue


@pytest.fixture
def mock_snapshot() -> IntelligenceSnapshot:
    now_utc = datetime.now(timezone.utc).isoformat()
    return IntelligenceSnapshot(
        snapshot_id="SNAP-ARCH-TEST-001",
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
                key_developments=["SATAT Phase-II revised plant subsidies announced."],
                important_sources=["PIB MoPNG", "SATAT Portal"],
                last_update=now_utc,
            )
        },
        companies={
            "TRUALT.NS": CompanyIntelligence(
                symbol="TRUALT.NS",
                short_symbol="TRUALT",
                name="TruAlt Bioenergy",
                scheme_id="gobardhan",
                scheme_name="GOBARdhan",
                relevance="Core",
                mapping_rationale="Largest CBG producer in India.",
                latest_development="Commissioned 100 TPD CBG plant in Karnataka.",
                catalyst="SATAT CBG Expansion (Strength: 92)",
                price=442.0,
                change_pct=3.1,
                trend="BULLISH",
                support=410.0,
                resistance=445.0,
                rsi=63.0,
                status="QUALIFIED_SETUP",
                archetype="Breakout Anticipation",
                score=95,
                trigger_price=442.0,
                stop_loss=418.0,
                target=488.0,
                bull_thesis="Strong volume expansion on SATAT policy tailwinds.",
                bear_thesis="Resistance at 445.",
                updated_at=now_utc,
            ),
            "PRAJIND.NS": CompanyIntelligence(
                symbol="PRAJIND.NS",
                short_symbol="PRAJIND",
                name="Praj Industries",
                scheme_id="gobardhan",
                scheme_name="GOBARdhan",
                relevance="Core",
                mapping_rationale="Engineering leader in ethanol and CBG plants.",
                latest_development="Secured 2G bio-ethanol technology contract.",
                catalyst="2G Biofuel Mandate (Strength: 85)",
                price=725.0,
                change_pct=-0.5,
                trend="NEUTRAL",
                support=710.0,
                resistance=760.0,
                rsi=48.0,
                status="WAITING",
                archetype="Support Reversal",
                score=78,
                trigger_price=740.0,
                stop_loss=695.0,
                target=815.0,
                bull_thesis="Accumulation near support.",
                bear_thesis="Delayed capital goods order conversion.",
                updated_at=now_utc,
            ),
        },
        qualified_setups=["TRUALT.NS"],
        waiting_setups=["PRAJIND.NS"],
        performance=PerformanceIntelligence(
            completed_trades=0,
            validation_threshold=30,
            win_rate=None,
            average_pnl_pct=None,
            profit_factor=None,
            expectancy=None,
            summary_text="Insufficient sample (0 completed trades)",
            audit_status="PASS",
        ),
        benchmark=BenchmarkIntelligence(
            status="UNAVAILABLE — 0 completed trades",
            nifty_cumulative_return_pct=None,
            strategy_cumulative_return_pct=None,
            excess_return_pct=None,
            alpha=None,
            beta=None,
            correlation=None,
            benchmark_win_rate=None,
            outperformed_benchmark_pct=None,
        ),
    )


@pytest.fixture
def test_env(tmp_path: Path, mock_snapshot: IntelligenceSnapshot):
    snap_path = tmp_path / "latest.json"
    db_path = str(tmp_path / "telegram_requests.db")
    q_db_path = str(tmp_path / "research_queue.db")

    store = IntelligenceStore(snapshot_path=snap_path)
    store.save(mock_snapshot)

    retriever = FastIntelligenceRetriever(store=store, auto_build_if_missing=False)
    req_store = RequestStore(db_path=db_path)
    q_store = ResearchQueue(db_path=q_db_path)
    dispatcher = MagicMock(spec=GitHubWorkflowDispatcher)
    dispatcher.dispatch_query.return_value = {"success": True, "status_code": 204, "request_id": "MOCK-REQ"}

    router = TelegramMessageRouter(
        retriever=retriever,
        research_queue=q_store,
        request_store=req_store,
        dispatcher=dispatcher,
        allowed_user_ids=None,
    )
    handler = TelegramConversationHandler(router=router)
    return {
        "retriever": retriever,
        "req_store": req_store,
        "q_store": q_store,
        "dispatcher": dispatcher,
        "router": router,
        "handler": handler,
        "snapshot": mock_snapshot,
    }


# ===========================================================================
# 1. WEBHOOK CONFLICT DETECTION & STARTUP CHECKS
# ===========================================================================

class TestWebhookConflictDetection:
    def test_webhook_conflict_detected_and_reported(self):
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "ok": True,
                "result": {"url": "https://myapp.com/telegram/webhook"},
            }
            conflict = check_webhook_conflict("mock_token")
            assert conflict == "https://myapp.com/telegram/webhook"

    def test_webhook_clean_when_no_url(self):
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "ok": True,
                "result": {"url": ""},
            }
            conflict = check_webhook_conflict("mock_token")
            assert conflict is None

    def test_run_polling_aborts_on_webhook_conflict(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:TOKEN", "TELEGRAM_DELETE_WEBHOOK": "false"}):
            with patch("scheme_intel.delivery.telegram_conversation.check_webhook_conflict", return_value="https://conflict.com"):
                with patch("requests.get") as mock_poll:
                    handler.run_polling(stop_after_runs=1)
                    # Poll should NOT start when conflict exists
                    mock_poll.assert_not_called()

    def test_bot_commands_registration_called(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            success = register_bot_commands("mock_token")
            assert success is True
            assert mock_post.called
            payload = mock_post.call_args[1]["json"]
            assert any(c["command"] == "stock" for c in payload["commands"])
            assert any(c["command"] == "setups" for c in payload["commands"])


# ===========================================================================
# 2. PERSISTENT REQUEST LOGGING & IDEMPOTENCY
# ===========================================================================

class TestRequestLoggingAndIdempotency:
    def test_request_logging_before_processing(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        req_store: RequestStore = test_env["req_store"]

        resp = handler.handle_message("TRUALT", user_id="111", chat_id="222", username="testuser")
        assert "TRUALT" in resp

        reqs = req_store.list_requests()
        assert len(reqs) == 1
        r = reqs[0]
        assert r.raw_query == "TRUALT"
        assert r.user_id == "111"
        assert r.chat_id == "222"
        assert r.username == "testuser"
        assert r.execution_path == ExecutionPath.FAST
        assert r.status == RequestStatus.COMPLETED
        assert r.request_id.startswith("TG-")
        assert r.response_sent_at is not None

    def test_duplicate_update_id_prevented(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        req_store: RequestStore = test_env["req_store"]

        update = {
            "update_id": 999901,
            "message": {
                "message_id": 10,
                "text": "TRUALT",
                "chat": {"id": 222},
                "from": {"id": 111, "username": "sreej"},
            },
        }

        with patch("scheme_intel.delivery.telegram_conversation.send_telegram", return_value=True) as mock_send:
            # First pass: processes
            res1 = handler.process_update(update, send_reply=True)
            assert res1 is not None
            assert mock_send.call_count >= 1

            # Second pass with same update_id: ignored
            mock_send.reset_mock()
            res2 = handler.process_update(update, send_reply=True)
            assert res2 is None
            mock_send.assert_not_called()


# ===========================================================================
# 3. PATH A: KNOWN FAST QUERIES (ZERO GITHUB ACTIONS)
# ===========================================================================

class TestPathAFastQueries:
    def test_start_menu_renders_shortcuts(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        dispatcher = test_env["dispatcher"]

        resp = handler.handle_message("/start")
        assert "SCHEME-INTEL" in resp
        assert "stock" in resp.lower()
        assert "setups" in resp.lower()
        dispatcher.dispatch_query.assert_not_called()

    def test_why_without_symbol_prompts_user_without_workflow(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        dispatcher = test_env["dispatcher"]

        for cmd in ("/why", "why", "/what", "what", "/when", "when"):
            resp = handler.handle_message(cmd)
            assert "Which stock?" in resp
            assert "TRUALT" in resp
            assert "PRAJ" in resp
            dispatcher.dispatch_query.assert_not_called()

    def test_stock_shortcuts_retrieve_instantly(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        dispatcher = test_env["dispatcher"]

        # Shortcut tests
        assert "TRUALT" in handler.handle_message("/trualt")
        assert "Praj Industries" in handler.handle_message("/praj")
        assert "QUALIFIED SETUPS" in handler.handle_message("/setups")
        assert "WAITING SETUPS" in handler.handle_message("/waiting")
        assert "GOBARDHAN" in handler.handle_message("/watchlist")
        assert "NIFTY 50 BENCHMARK" in handler.handle_message("/benchmark")
        assert "FORWARD PERFORMANCE" in handler.handle_message("/performance")

        # Fast path must NEVER invoke GitHub dispatcher
        dispatcher.dispatch_query.assert_not_called()

    def test_stock_aliases_normalized(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        dispatcher = test_env["dispatcher"]

        for query in ("Praj", "Praj Industries", "PRAJ", "/why TRUALT", "/when TRUALT"):
            resp = handler.handle_message(query)
            assert resp != query
            assert len(resp) > 20
        dispatcher.dispatch_query.assert_not_called()


# ===========================================================================
# 4. PATH B: COMPLEX QUERIES & GITHUB WORKFLOW DISPATCH
# ===========================================================================

class TestPathBComplexQueries:
    @pytest.mark.parametrize(
        "complex_query",
        [
            "Which Gobardhan companies have the strongest catalyst this week?",
            "Why is Praj Industries underperforming despite the scheme?",
            "Compare TRUALT and PRAJ based on current scheme intelligence.",
            "What changed in Gobardhan policy and which watchlist companies are affected?",
        ],
    )
    def test_complex_query_routes_to_workflow(self, test_env, complex_query: str):
        handler: TelegramConversationHandler = test_env["handler"]
        dispatcher = test_env["dispatcher"]
        req_store: RequestStore = test_env["req_store"]

        resp = handler.handle_message(complex_query, user_id="100", chat_id="200")

        # 1. Immediate ACK to user
        assert "🔎 *Request received.*" in resp
        assert "Request ID:" in resp
        assert "I'm processing this against the latest Scheme-Intel intelligence." in resp

        # 2. Triggered 04-telegram-query workflow via repository_dispatch
        assert dispatcher.dispatch_query.called
        call_kwargs = dispatcher.dispatch_query.call_args[1]
        assert call_kwargs["chat_id"] == "200"
        assert call_kwargs["user_id"] == "100"
        assert call_kwargs["query"] == complex_query
        assert call_kwargs["intent"] == "COMPLEX_QUERY"

        # 3. Request Store state is ROUTED with WORKFLOW path
        req = req_store.list_requests()[0]
        assert req.execution_path == ExecutionPath.WORKFLOW
        assert req.status == RequestStatus.ROUTED


# ===========================================================================
# 5. STRICT CHAT ISOLATION & NO BROADCAST (CRITICAL REQUIREMENT)
# ===========================================================================

class TestChatIsolationAndNoBroadcast:
    def test_workflow_runner_dispatches_only_to_originating_chat_id(self, test_env):
        retriever = test_env["retriever"]
        req_store: RequestStore = test_env["req_store"]

        # User A sends complex query
        req_a = req_store.log_request(
            raw_query="Compare TRUALT and PRAJ",
            chat_id="CHAT_USER_A",
            user_id="USER_A",
            execution_path=ExecutionPath.WORKFLOW,
        )

        payload_a = {
            "request_id": req_a.request_id,
            "chat_id": "CHAT_USER_A",
            "user_id": "USER_A",
            "query": "Compare TRUALT and PRAJ",
        }

        with patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "GLOBAL_BROADCAST_CHAT_999"}):
            with patch("scheme_intel.delivery.workflow_query_runner.send_telegram", return_value=True) as mock_send:
                success = process_workflow_query(
                    payload=payload_a,
                    request_store=req_store,
                    retriever=retriever,
                )
                assert success is True

                # ASSERT: Dispatched ONLY to User A's chat_id
                mock_send.assert_called_once()
                sent_kwargs = mock_send.call_args[1]
                assert sent_kwargs["chat_ids"] == ["CHAT_USER_A"]

                # CRITICAL: Broadcast chat ID was NEVER called
                assert "GLOBAL_BROADCAST_CHAT_999" not in sent_kwargs["chat_ids"]
                assert sent_kwargs["request_id"] == req_a.request_id

        # Verify completed in DB
        updated = req_store.get_request(req_a.request_id)
        assert updated.status == RequestStatus.COMPLETED

    def test_user_b_does_not_receive_user_a_response(self, test_env):
        retriever = test_env["retriever"]
        req_store: RequestStore = test_env["req_store"]

        payload = {
            "request_id": "TG-TEST-ISOLATION-01",
            "chat_id": "CHAT_USER_B",
            "user_id": "USER_B",
            "query": "Strongest catalyst",
        }

        with patch("scheme_intel.delivery.workflow_query_runner.send_telegram", return_value=True) as mock_send:
            process_workflow_query(payload=payload, request_store=req_store, retriever=retriever)
            sent_chat_ids = mock_send.call_args[1]["chat_ids"]
            assert "CHAT_USER_B" in sent_chat_ids
            assert "CHAT_USER_A" not in sent_chat_ids

    def test_workflow_idempotency_prevents_duplicate_reply(self, test_env):
        retriever = test_env["retriever"]
        req_store: RequestStore = test_env["req_store"]

        req = req_store.log_request(raw_query="Test query", chat_id="CHAT_123")
        req_store.mark_completed(req.request_id, "Prior response")

        payload = {
            "request_id": req.request_id,
            "chat_id": "CHAT_123",
            "query": "Test query",
        }

        with patch("scheme_intel.delivery.workflow_query_runner.send_telegram") as mock_send:
            success = process_workflow_query(payload=payload, request_store=req_store, retriever=retriever)
            assert success is True
            # Should NOT send again since it's already COMPLETED
            mock_send.assert_not_called()


# ===========================================================================
# 6. PATH C: /research ROUTING
# ===========================================================================

class TestPathCResearchRouting:
    def test_research_command_uses_queue_without_github_workflow(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        dispatcher = test_env["dispatcher"]
        q_store: ResearchQueue = test_env["q_store"]

        resp = handler.handle_message("/research What is the latest SATAT policy?", user_id="111", chat_id="222")

        # 1. Returns research ACK
        assert "Research queued" in resp or "Research request received" in resp

        # 2. Enqueued in SQLite research queue
        jobs = q_store.list_jobs(status="QUEUED")
        assert len(jobs) == 1
        assert jobs[0].question == "What is the latest SATAT policy?"

        # 3. Did NOT trigger 04-telegram-query.yml
        dispatcher.dispatch_query.assert_not_called()


# ===========================================================================
# 7. GATEWAY COMPREHENSIVE VERIFICATION & FAILURE MODES
# ===========================================================================

class TestGatewayComprehensiveLiveVerification:
    def test_gateway_startup_and_getme_success(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "TEST_TOKEN_123"}):
            with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
                mock_get.side_effect = [
                    # 1. getWebhookInfo
                    MagicMock(status_code=200, json=lambda: {"ok": True, "result": {"url": ""}}),
                    # 2. getMe
                    MagicMock(status_code=200, json=lambda: {"ok": True, "result": {"username": "Scheme_intelbot", "id": 123}}),
                    # 3. getUpdates
                    MagicMock(status_code=200, json=lambda: {"ok": True, "result": []}),
                ]
                mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ok": True})

                handler.run_polling(stop_after_runs=1)
                assert mock_get.call_count >= 2

    def test_stale_webhook_removal_with_env_flag(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "TEST_TOKEN_123", "TELEGRAM_DELETE_WEBHOOK": "true"}):
            with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
                mock_get.side_effect = [
                    # 1. getWebhookInfo
                    MagicMock(status_code=200, json=lambda: {"ok": True, "result": {"url": "https://stale-hook.example.com"}}),
                    # 2. getMe
                    MagicMock(status_code=200, json=lambda: {"ok": True, "result": {"username": "TestBot"}}),
                    # 3. getUpdates
                    MagicMock(status_code=200, json=lambda: {"ok": True, "result": []}),
                ]
                mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ok": True})

                handler.run_polling(stop_after_runs=1)
                # Verify deleteWebhook was called
                post_urls = [call[0][0] for call in mock_post.call_args_list]
                assert any("deleteWebhook" in u for u in post_urls)

    def test_specific_commands_and_shortcuts(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        dispatcher = test_env["dispatcher"]

        # /gail
        resp_gail = handler.handle_message("/gail", chat_id="123")
        assert "GAIL" in resp_gail

        # /praj
        resp_praj = handler.handle_message("/praj", chat_id="123")
        assert "PRAJIND" in resp_praj

        # /trualt
        resp_trualt = handler.handle_message("/trualt", chat_id="123")
        assert "TRUALT" in resp_trualt

        # /why trualt
        resp_why = handler.handle_message("/why trualt", chat_id="123")
        assert "WHY TRUALT" in resp_why

        # Natural language 'Praj'
        resp_nl_praj = handler.handle_message("Praj", chat_id="123")
        assert "PRAJIND" in resp_nl_praj

        # None of these trigger GitHub Actions
        dispatcher.dispatch_query.assert_not_called()

    def test_unauthorized_user_blocked_without_crash(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USER_IDS": "ALLOWED_USER_999"}):
            # Recreate router with new allowed user ids
            restricted_router = TelegramMessageRouter(
                retriever=test_env["retriever"],
                request_store=test_env["req_store"],
            )
            handler.router = restricted_router

            resp = handler.handle_message("/gail", user_id="UNAUTHORIZED_USER", chat_id="CHAT_123")
            assert "not authorized" in resp.lower()

    def test_set_my_commands_failure_does_not_abort_gateway(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "TEST_TOKEN_123"}):
            with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
                mock_get.side_effect = [
                    # 1. getWebhookInfo
                    MagicMock(status_code=200, json=lambda: {"ok": True, "result": {"url": ""}}),
                    # 2. getMe
                    MagicMock(status_code=200, json=lambda: {"ok": True, "result": {"username": "TestBot"}}),
                    # 3. getUpdates
                    MagicMock(status_code=200, json=lambda: {"ok": True, "result": [{"update_id": 901, "message": {"text": "/gail", "chat": {"id": 111}}}]}),
                ]
                # setMyCommands fails with 500
                mock_post.return_value = MagicMock(status_code=500, text="Internal Server Error")

                with patch("scheme_intel.delivery.telegram_conversation.send_telegram", return_value=True) as mock_send:
                    handler.run_polling(stop_after_runs=1)
                    # Verify message was still processed despite command menu failure
                    assert mock_send.call_count == 1
                    assert "GAIL" in mock_send.call_args[0][0]

    def test_gateway_retries_after_transient_polling_failure(self, test_env):
        handler: TelegramConversationHandler = test_env["handler"]
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "TEST_TOKEN_123"}):
            with patch("requests.get") as mock_get, patch("requests.post") as mock_post, patch("time.sleep"):
                mock_get.side_effect = [
                    # 1. getWebhookInfo
                    MagicMock(status_code=200, json=lambda: {"ok": True, "result": {"url": ""}}),
                    # 2. getMe
                    MagicMock(status_code=200, json=lambda: {"ok": True, "result": {"username": "TestBot"}}),
                    # 3. getUpdates run 1: connection error
                    requests.exceptions.ConnectionError("Temporary network blip"),
                    # 4. getUpdates run 2: successful response
                    MagicMock(status_code=200, json=lambda: {"ok": True, "result": [{"update_id": 902, "message": {"text": "/praj", "chat": {"id": 222}}}]}),
                ]
                mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ok": True})

                with patch("scheme_intel.delivery.telegram_conversation.send_telegram", return_value=True) as mock_send:
                    handler.run_polling(stop_after_runs=2)
                    assert mock_send.call_count == 1
                    assert "PRAJIND" in mock_send.call_args[0][0]

    def test_gh_auth_token_fallback_in_dispatcher(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("shutil.which", return_value="gh"), patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="gho_mock_token_from_cli\n")
                disp = GitHubWorkflowDispatcher(repository="botv99/scheme-intel")
                assert disp.token == "gho_mock_token_from_cli"

