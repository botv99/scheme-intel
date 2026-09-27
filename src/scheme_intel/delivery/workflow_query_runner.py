"""
Workflow Query Runner for GitHub Actions 04-telegram-query.yml (Stage 3).
Executes complex analytical queries inside GitHub Actions and delivers the answer
strictly and exclusively to the originating Telegram chat_id (NO BROADCAST).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

from .query_engine import ComplexQueryEngine
from .request_store import RequestStore, RequestStatus, ExecutionPath
from ..intelligence_memory.retrieval import FastIntelligenceRetriever
from ..notifier import send_telegram
from ..logger import get_logger

logger = get_logger(__name__)


def process_workflow_query(
    payload: Dict[str, Any],
    request_store: Optional[RequestStore] = None,
    retriever: Optional[FastIntelligenceRetriever] = None,
    query_engine: Optional[ComplexQueryEngine] = None,
) -> bool:
    """
    Process a complex query triggered via GitHub Actions repository_dispatch.
    Dispatches answer strictly to client_payload["chat_id"].
    """
    request_id = payload.get("request_id")
    chat_id = payload.get("chat_id")
    query = payload.get("query") or payload.get("raw_query", "")
    scheme_id = payload.get("scheme_id", "gobardhan")
    symbol = payload.get("symbol")
    workflow_run_id = os.getenv("GITHUB_RUN_ID", "local")

    logger.info(
        "[WORKFLOW RUNNER] Starting query processing: request_id=%s, chat_id=%s, run_id=%s",
        request_id,
        chat_id,
        workflow_run_id,
    )

    # 1. Strict Validation
    if not request_id or not str(request_id).strip():
        logger.error("[WORKFLOW RUNNER] Missing or empty 'request_id' in payload.")
        return False

    raw_chat = str(chat_id).strip() if chat_id is not None else ""
    if not raw_chat or raw_chat.lower() == "default":
        fallback_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if fallback_chat and fallback_chat.lower() != "default":
            logger.warning(
                "[WORKFLOW RUNNER] Received 'default' or empty chat_id; falling back to TELEGRAM_CHAT_ID=%s",
                fallback_chat,
            )
            target_chat_id = fallback_chat
        else:
            logger.error(
                "[WORKFLOW RUNNER] Missing or 'default' chat_id and no valid TELEGRAM_CHAT_ID fallback."
            )
            return False
    else:
        target_chat_id = raw_chat

    if not query or not str(query).strip():
        logger.error("[WORKFLOW RUNNER] Missing query text in payload for request %s.", request_id)
        return False

    # 2. Idempotency Check
    store = request_store or RequestStore()
    existing_req = store.get_request(request_id)
    if existing_req and existing_req.status == RequestStatus.COMPLETED:
        logger.info(
            "[WORKFLOW RUNNER] Request %s already completed at %s. Skipping duplicate dispatch.",
            request_id,
            existing_req.response_sent_at,
        )
        return True

    if existing_req is None:
        store.log_request(
            raw_query=query,
            user_id=payload.get("user_id"),
            chat_id=target_chat_id,
            username=payload.get("username"),
            normalized_query=payload.get("normalized_query", ""),
            resolved_intent=payload.get("intent", "COMPLEX_QUERY"),
            execution_path=ExecutionPath.WORKFLOW,
            request_id=request_id,
        )

    # Mark as PROCESSING
    store.update_status(
        request_id=request_id,
        status=RequestStatus.PROCESSING,
        workflow_run_id=workflow_run_id,
    )

    try:
        # 3. Load latest validated snapshot
        retr = retriever or FastIntelligenceRetriever(auto_build_if_missing=False)
        status, snapshot, status_msg = retr.get_status()

        if not snapshot:
            err_msg = f"Intelligence snapshot unavailable: {status_msg}"
            logger.error("[WORKFLOW RUNNER] %s", err_msg)
            failure_reply = (
                f"⚠️ *Analysis Unavailable*\n\n"
                f"*Request ID:* `{request_id}`\n\n"
                f"The intelligence memory snapshot is currently unavailable. Please try again after the next scheduled scan."
            )
            send_telegram(failure_reply, chat_ids=[target_chat_id], parse_mode="Markdown", request_id=request_id)
            store.mark_failed(request_id=request_id, error_msg=err_msg, workflow_run_id=workflow_run_id)
            return False

        # 4. Synthesize Answer
        engine = query_engine or ComplexQueryEngine()
        answer = engine.process_query(
            query=query,
            snapshot=snapshot,
            scheme_id=scheme_id,
            target_symbol=symbol,
        )

        # 5. Format Curated Terminal Card
        response_card = (
            f"💡 *Scheme-Intel Analysis*\n\n"
            f"*Query:* {query}\n"
            f"*Request ID:* `{request_id}`\n\n"
            f"{answer}\n\n"
            f"_Delivered to your terminal • Run #{workflow_run_id}_"
        )

        # 6. Deliver Answer STRICTLY to Original chat_id
        logger.info(
            "[WORKFLOW RUNNER] Dispatching personalized response ONLY to chat_id=%s (never broadcast).",
            target_chat_id,
        )
        try:
            success = send_telegram(
                response_card,
                chat_ids=[target_chat_id],
                parse_mode="Markdown",
                request_id=request_id,
            )
        except Exception as send_err:
            logger.warning("[WORKFLOW RUNNER] Markdown delivery failed (%s). Retrying as plain text...", send_err)
            try:
                success = send_telegram(
                    response_card,
                    chat_ids=[target_chat_id],
                    parse_mode=None,
                    request_id=request_id,
                )
            except Exception as retry_err:
                logger.error("[WORKFLOW RUNNER] Plain-text delivery also failed: %s", retry_err)
                success = False

        if success:
            store.mark_completed(
                request_id=request_id,
                response_text=response_card,
                workflow_run_id=workflow_run_id,
            )
            logger.info("[WORKFLOW RUNNER] Successfully delivered query response for request %s.", request_id)
            return True
        else:
            store.mark_failed(
                request_id=request_id,
                error_msg="Telegram API failed to deliver response to chat",
                workflow_run_id=workflow_run_id,
            )
            return False

    except Exception as e:
        logger.exception("[WORKFLOW RUNNER] Unhandled exception processing request %s: %s", request_id, e)
        error_notice = (
            f"⚠️ *Scheme-Intel Processing Error*\n\n"
            f"*Request ID:* `{request_id}`\n\n"
            f"An unexpected error occurred while analyzing your query. Please try asking with a specific company or command."
        )
        try:
            send_telegram(error_notice, chat_ids=[target_chat_id], parse_mode="Markdown", request_id=request_id)
        except Exception as notify_err:
            logger.error("[WORKFLOW RUNNER] Failed sending error notification: %s", notify_err)

        store.mark_failed(
            request_id=request_id,
            error_msg=str(e),
            workflow_run_id=workflow_run_id,
        )
        return False


def main():
    parser = argparse.ArgumentParser(description="Scheme-Intel Workflow Query Runner")
    parser.add_argument("--request-id", help="Telegram Request ID")
    parser.add_argument("--chat-id", help="Originating Telegram chat_id")
    parser.add_argument("--query", help="User natural language query")
    parser.add_argument("--user-id", help="Optional User ID")
    parser.add_argument("--scheme-id", default="gobardhan", help="Scheme ID")
    args = parser.parse_args()

    # Priority 1: CLIENT_PAYLOAD environment variable (from repository_dispatch)
    payload = {}
    client_payload_env = os.getenv("CLIENT_PAYLOAD")
    if client_payload_env and client_payload_env.strip() and client_payload_env.strip() != "null":
        try:
            parsed = json.loads(client_payload_env)
            if isinstance(parsed, dict):
                payload = parsed
        except Exception as e:
            logger.error("Failed parsing CLIENT_PAYLOAD JSON: %s", e)

    # Priority 2: CLI arguments or workflow_dispatch INPUT_* env vars
    if not payload.get("request_id"):
        payload["request_id"] = args.request_id or os.getenv("INPUT_REQUEST_ID")
    if not payload.get("chat_id"):
        payload["chat_id"] = args.chat_id or os.getenv("INPUT_CHAT_ID")
    if not payload.get("query"):
        payload["query"] = args.query or os.getenv("INPUT_QUERY")
    if not payload.get("user_id"):
        payload["user_id"] = args.user_id or os.getenv("INPUT_USER_ID")
    if not payload.get("scheme_id"):
        payload["scheme_id"] = args.scheme_id or os.getenv("INPUT_SCHEME_ID", "gobardhan")

    success = process_workflow_query(payload)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
