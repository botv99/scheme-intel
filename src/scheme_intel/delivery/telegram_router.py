"""
Telegram Message Router and Access Gatekeeper (Stage 3).
Routes incoming Telegram requests across three distinct paths:
1. FAST PATH: Instant (<100ms) answers from precalculated IntelligenceSnapshot. Zero GitHub Actions.
2. WORKFLOW PATH: Complex analytical/comparison queries dispatched to 04-telegram-query.yml.
3. RESEARCH PATH: Asynchronous deep policy research queued to SQLite ResearchQueue.
"""
from __future__ import annotations

import os
import time
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone

from .github_dispatcher import GitHubWorkflowDispatcher
from .request_store import RequestStore, RequestStatus, ExecutionPath, TelegramRequest
from ..intelligence_memory.models import SnapshotHealthStatus
from ..intelligence_memory.resolver import IntentResolver, IntentType, ResolvedIntent
from ..intelligence_memory.retrieval import FastIntelligenceRetriever
from ..intelligence_memory.cards import (
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
    render_start_card,
    render_help_card,
    render_watchlist_card,
    render_stock_prompt_card,
    render_unknown_stock,
    render_unknown_scheme,
    render_snapshot_unavailable,
    render_snapshot_missing,
    render_snapshot_invalid,
    render_health_card,
)
from ..research.queue import ResearchQueue
from ..research.formatter import format_research_acknowledgement
from ..logger import get_logger

logger = get_logger(__name__)


class TelegramMessageRouter:
    """Routes incoming Telegram messages to fast memory cards, workflow dispatch, or async research."""

    def __init__(
        self,
        retriever: Optional[FastIntelligenceRetriever] = None,
        research_queue: Optional[ResearchQueue] = None,
        request_store: Optional[RequestStore] = None,
        dispatcher: Optional[GitHubWorkflowDispatcher] = None,
        allowed_user_ids: Optional[Set[str]] = None,
        allowed_chat_ids: Optional[Set[str]] = None,
        research_cooldown_seconds: int = 60,
    ):
        self.retriever = retriever or FastIntelligenceRetriever(auto_build_if_missing=False)
        self.research_queue = research_queue or ResearchQueue()
        self.request_store = request_store or RequestStore()
        self.dispatcher = dispatcher or GitHubWorkflowDispatcher()
        self.research_cooldown_seconds = research_cooldown_seconds

        # User security filters
        self.allowed_user_ids = allowed_user_ids
        if self.allowed_user_ids is None:
            env_users = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
            if env_users:
                self.allowed_user_ids = {u.strip() for u in env_users.split(",") if u.strip()}

        self.allowed_chat_ids = allowed_chat_ids
        if self.allowed_chat_ids is None:
            env_chats = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
            if env_chats:
                self.allowed_chat_ids = {c.strip() for c in env_chats.split(",") if c.strip()}

        # Rate limiting state: user_id -> timestamp of last research request
        self._user_last_research: Dict[str, float] = {}

    def is_authorized(self, user_id: Optional[str] = None, chat_id: Optional[str] = None) -> bool:
        """Check if incoming user/chat is allowed to query the terminal."""
        if self.allowed_user_ids:
            if not user_id or str(user_id) not in self.allowed_user_ids:
                return False
        if self.allowed_chat_ids:
            if not chat_id or str(chat_id) not in self.allowed_chat_ids:
                return False
        return True

    def route_message(
        self,
        text: str,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        request_id: Optional[str] = None,
        username: Optional[str] = None,
        update_id: Optional[int] = None,
    ) -> str:
        """
        Process incoming user text and return the immediate Telegram reply.
        Logs every request before processing.
        Branches across FAST, WORKFLOW, and RESEARCH execution paths.
        """
        raw_text = (text or "").strip()
        effective_req_id = request_id or self.request_store.generate_request_id()

        # 1. Authorization check
        if not self.is_authorized(user_id=user_id, chat_id=chat_id):
            logger.warning("[TELEGRAM] Blocked unauthorized query from user_id=%s, chat_id=%s", user_id, chat_id)
            self.request_store.log_request(
                raw_query=raw_text,
                user_id=user_id,
                chat_id=chat_id,
                username=username,
                update_id=update_id,
                request_id=effective_req_id,
                resolved_intent="UNAUTHORIZED",
                execution_path=ExecutionPath.FAST,
            )
            self.request_store.mark_failed(effective_req_id, "Unauthorized user/chat")
            return "⛔ This Telegram account/chat is not authorized to use Scheme-Intel. (Unauthorized)"

        # 2. Intent & Execution Path Resolution
        intent: ResolvedIntent = IntentResolver.resolve(raw_text)

        # 3. Persistent Request Logging BEFORE Processing
        self.request_store.log_request(
            raw_query=raw_text,
            user_id=user_id,
            chat_id=chat_id,
            username=username,
            update_id=update_id,
            normalized_query=intent.normalized_query,
            resolved_intent=intent.intent_type.value,
            execution_path=intent.execution_path,
            request_id=effective_req_id,
        )

        # 4. Route Message by Execution Path
        if intent.execution_path == ExecutionPath.RESEARCH or intent.intent_type == IntentType.RESEARCH_REQUEST:
            return self._handle_research(intent, user_id=user_id, chat_id=chat_id, request_id=effective_req_id)

        if intent.execution_path == ExecutionPath.WORKFLOW or intent.intent_type == IntentType.COMPLEX_QUERY:
            return self._handle_workflow_query(intent, user_id=user_id, chat_id=chat_id, request_id=effective_req_id)

        # Default: Path A (FAST)
        response = self._handle_fast_query(intent)
        self.request_store.mark_completed(effective_req_id, response)
        return response

    def _handle_workflow_query(
        self,
        intent: ResolvedIntent,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> str:
        """
        Handle Path B (Complex / Natural Language query):
        1. Logs request and marks as ROUTED.
        2. Dispatches repository_dispatch to trigger 04-telegram-query.yml.
        3. Returns immediate acknowledgement sent strictly to original chat_id.
        """
        req_id = request_id or self.request_store.generate_request_id()
        target_chat = str(chat_id or user_id or "default")

        logger.info(
            "[TELEGRAM ROUTER] Routing complex query to GitHub Workflow: request_id=%s, chat_id=%s, query='%s'",
            req_id,
            target_chat,
            intent.raw_query[:50],
        )

        # Update status to ROUTED
        self.request_store.update_status(
            request_id=req_id,
            status=RequestStatus.ROUTED,
            resolved_intent=intent.intent_type.value,
            execution_path=ExecutionPath.WORKFLOW,
        )

        # Trigger GitHub Actions repository_dispatch
        dispatch_res = self.dispatcher.dispatch_query(
            request_id=req_id,
            chat_id=target_chat,
            query=intent.raw_query,
            user_id=user_id,
            normalized_query=intent.normalized_query,
            intent=intent.intent_type.value,
            scheme_id=intent.scheme_id,
            symbol=intent.symbol,
        )

        if not dispatch_res.get("success"):
            logger.warning(
                "[TELEGRAM ROUTER] Workflow dispatch reported: %s",
                dispatch_res.get("error", "Unknown dispatch issue"),
            )

        # Immediate acknowledgement returned ONLY to originating chat
        return (
            "🔎 *Request received.*\n\n"
            f"*Request ID:* `{req_id}`\n\n"
            "I'm processing this against the latest Scheme-Intel intelligence."
        )

    def _handle_research(
        self,
        intent: ResolvedIntent,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> str:
        """Enqueue asynchronous research task and return immediate acknowledgement."""
        question = intent.parameters.get("question", "").strip()
        if not question:
            return "⚠️ Please provide a research question.\nExample: `/research What changed in Gobardhan policy this month?`"

        # Rate limit check for research requests
        uid = str(user_id or chat_id or "default")
        now = time.time()
        last_req = self._user_last_research.get(uid, 0.0)
        if (now - last_req) < self.research_cooldown_seconds:
            wait_s = int(self.research_cooldown_seconds - (now - last_req))
            return f"⏳ *Research Rate Limit Reached.*\nPlease wait {wait_s}s before submitting another research request."

        self._user_last_research[uid] = now

        # Enqueue job in persistent storage
        scheme_id = intent.scheme_id or "gobardhan"
        job = self.research_queue.enqueue_job(
            question=question,
            user_id=str(user_id) if user_id else None,
            chat_id=str(chat_id) if chat_id else None,
            scheme_id=scheme_id,
        )

        if request_id:
            self.request_store.update_status(
                request_id=request_id,
                status=RequestStatus.ROUTED,
                resolved_intent=intent.intent_type.value,
                execution_path=ExecutionPath.RESEARCH,
            )

        return format_research_acknowledgement(job.job_id, question=question)

    def _handle_fast_query(self, intent: ResolvedIntent) -> str:
        """Execute fast, structured memory retrieval from loaded snapshot (<100ms)."""
        status, snapshot, status_msg = self.retriever.get_status()

        if intent.intent_type == IntentType.START:
            return render_start_card()

        if intent.intent_type == IntentType.HELP:
            return render_help_card()

        if intent.intent_type == IntentType.STOCK_WHY_PROMPT:
            return render_stock_prompt_card("/why")

        if intent.intent_type == IntentType.STOCK_WHAT_PROMPT:
            return render_stock_prompt_card("/what")

        if intent.intent_type == IntentType.STOCK_WHEN_PROMPT:
            return render_stock_prompt_card("/when")

        if intent.intent_type == IntentType.HEALTH_CHECK:
            pending_jobs = len(self.research_queue.list_jobs(status="QUEUED"))
            running_jobs = len(self.research_queue.list_jobs(status="RUNNING"))
            return render_health_card(
                telegram_status="OK",
                snapshot_status=status.value,
                snapshot_age=snapshot.get_age_display() if snapshot else "N/A",
                queue_status="OK",
                worker_status="ACTIVE",
                active_jobs=pending_jobs + running_jobs,
            )

        if status == SnapshotHealthStatus.MISSING or not snapshot:
            return render_snapshot_missing()

        if status == SnapshotHealthStatus.INVALID:
            return render_snapshot_invalid(status_msg)

        is_stale = (status == SnapshotHealthStatus.STALE)

        if intent.intent_type == IntentType.WATCHLIST:
            return render_watchlist_card(snapshot.companies, is_stale=is_stale)

        if intent.intent_type == IntentType.SCHEMES:
            schemes = self.retriever.list_schemes()
            return render_schemes_list_card(schemes)

        if intent.intent_type == IntentType.SCHEME_LOOKUP:
            scheme_id = intent.scheme_id or "gobardhan"
            scheme = self.retriever.get_scheme(scheme_id)
            if not scheme:
                return render_unknown_scheme(scheme_id)
            return render_scheme_card(scheme, is_stale=is_stale)

        if intent.intent_type in (IntentType.STOCK_LOOKUP, IntentType.STOCK_WHY, IntentType.STOCK_WHAT, IntentType.STOCK_WHEN):
            target_symbol = intent.symbol or intent.parameters.get("unresolved_symbol", "")
            comp = self.retriever.get_company(target_symbol)
            if not comp:
                return render_unknown_stock(target_symbol or "query")

            if intent.intent_type == IntentType.STOCK_WHY:
                return render_why_card(comp, is_stale=is_stale)
            elif intent.intent_type == IntentType.STOCK_WHAT:
                return render_what_card(comp, is_stale=is_stale)
            elif intent.intent_type == IntentType.STOCK_WHEN:
                return render_when_card(comp, is_stale=is_stale)
            else:
                return render_stock_card(comp, is_stale=is_stale)

        if intent.intent_type == IntentType.SETUPS_LOOKUP:
            setups = self.retriever.get_qualified_setups()
            return render_setups_card(setups, is_stale=is_stale, updated_str=snapshot.generated_at)

        if intent.intent_type == IntentType.WAITING_LOOKUP:
            waiting = self.retriever.get_waiting_setups()
            return render_waiting_card(waiting, is_stale=is_stale)

        if intent.intent_type == IntentType.OUTCOMES_LOOKUP or intent.intent_type == IntentType.PERFORMANCE_LOOKUP:
            perf = self.retriever.get_performance()
            return render_performance_card(perf, is_stale=is_stale)

        if intent.intent_type == IntentType.BENCHMARK_LOOKUP:
            bench = self.retriever.get_benchmark()
            return render_benchmark_card(bench, is_stale=is_stale)

        # Default fallback for unmapped queries - NEVER echo user input
        return render_help_card()
