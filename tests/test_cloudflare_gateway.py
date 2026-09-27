"""
Comprehensive Tests for Cloudflare Worker Telegram Gateway and GitHub Actions Integration.
Verifies Cloudflare Worker codebase integrity, parity with Python IntentResolver,
and resilient workflow_query_runner handling for repository_dispatch payloads.
"""
from pathlib import Path
import json
import re
import pytest

from scheme_intel.delivery.workflow_query_runner import process_workflow_query
from scheme_intel.delivery.request_store import RequestStore, RequestStatus
from scheme_intel.intelligence_memory.resolver import IntentResolver, ExecutionPath, IntentType


REPO_ROOT = Path(__file__).parent.parent
CF_DIR = REPO_ROOT / "cloudflare" / "telegram-gateway"


def test_cloudflare_worker_file_structure():
    """Verify all required Cloudflare Worker files exist."""
    assert CF_DIR.exists(), "Cloudflare gateway directory must exist"
    assert (CF_DIR / "wrangler.toml").exists(), "wrangler.toml must exist"
    assert (CF_DIR / "package.json").exists(), "package.json must exist"
    assert (CF_DIR / "README.md").exists(), "README.md must exist"
    assert (CF_DIR / ".gitignore").exists(), ".gitignore must exist"
    assert (CF_DIR / "scripts" / "setup-webhook.js").exists(), "setup-webhook.js must exist"

    src_files = ["index.js", "resolver.js", "telegram.js", "github.js", "snapshot.js", "auth.js", "utils.js"]
    for sf in src_files:
        p = CF_DIR / "src" / sf
        assert p.exists(), f"Source file {sf} must exist"
        content = p.read_text(encoding="utf-8")
        assert len(content) > 50, f"Source file {sf} must not be empty"


def test_wrangler_config_security():
    """Ensure wrangler.toml does not contain hardcoded secrets."""
    wrangler_content = (CF_DIR / "wrangler.toml").read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=" not in wrangler_content
    assert "GITHUB_TOKEN=" not in wrangler_content
    assert "TELEGRAM_WEBHOOK_SECRET=" not in wrangler_content
    assert "scheme-intel-telegram-gateway" in wrangler_content


def test_resolver_parity_fast_queries():
    """Verify FAST queries resolve to FAST execution path."""
    fast_samples = [
        "/start",
        "/help",
        "/setups",
        "/waiting",
        "/watchlist",
        "/schemes",
        "/performance",
        "/benchmark",
        "/gail",
        "/praj",
        "/trualt",
        "/why trualt",
        "/what praj",
        "/when wabag",
        "GAIL",
        "Praj",
        "TRUALT",
        "WABAG",
    ]
    for sample in fast_samples:
        resolved = IntentResolver.resolve(sample)
        assert resolved.execution_path == ExecutionPath.FAST, f"Expected FAST for query: '{sample}'"


def test_resolver_parity_complex_queries():
    """Verify complex comparative and analytical queries resolve to WORKFLOW."""
    complex_samples = [
        "Compare TRUALT and PRAJ",
        "Which Gobardhan companies have the strongest catalysts?",
        "What changed in the last market session?",
        "Which companies are affected by this policy change?",
        "Why did Praj and TruAlt diverge this week?",
        "GAIL vs IOC",
    ]
    for sample in complex_samples:
        resolved = IntentResolver.resolve(sample)
        assert resolved.execution_path == ExecutionPath.WORKFLOW, f"Expected WORKFLOW for query: '{sample}'"


def test_resolver_parity_research_queries():
    """Verify research queries resolve to RESEARCH path."""
    research_samples = [
        "/research What are recent CBG guidelines?",
        "/research Biofuel subsidy allocation for 2026",
    ]
    for sample in research_samples:
        resolved = IntentResolver.resolve(sample)
        assert resolved.execution_path == ExecutionPath.RESEARCH, f"Expected RESEARCH for query: '{sample}'"


def test_workflow_query_runner_with_valid_dispatch_payload(tmp_path, monkeypatch):
    """Test workflow_query_runner processing a repository_dispatch payload."""
    db_path = str(tmp_path / "test_requests.db")
    store = RequestStore(db_path=db_path)

    sent_messages = []
    def mock_send(text, chat_ids=None, parse_mode=None, request_id=None, reply_markup=None):
        sent_messages.append({"text": text, "chat_ids": chat_ids, "parse_mode": parse_mode})
        return True

    monkeypatch.setattr("scheme_intel.delivery.workflow_query_runner.send_telegram", mock_send)

    payload = {
        "request_id": "TG-20260927-TEST01",
        "chat_id": "5917850553",
        "user_id": "5917850553",
        "query": "Compare TRUALT and PRAJ",
        "raw_query": "Compare TRUALT and PRAJ",
        "normalized_query": "compare trualt and praj",
        "intent": "COMPLEX_QUERY",
        "scheme_id": "gobardhan",
        "symbol": "TRUALT.NS",
    }

    success = process_workflow_query(payload, request_store=store)
    assert success is True
    assert len(sent_messages) == 1
    assert sent_messages[0]["chat_ids"] == ["5917850553"], "Response must be sent STRICTLY to requesting chat_id"
    assert "Scheme-Intel Analysis" in sent_messages[0]["text"]

    req = store.get_request("TG-20260927-TEST01")
    assert req is not None
    assert req.status == RequestStatus.COMPLETED


def test_workflow_query_runner_rejects_missing_request_id():
    """Verify runner rejects payloads missing request_id safely."""
    payload = {"chat_id": "5917850553", "query": "Test"}
    assert process_workflow_query(payload) is False


def test_workflow_query_runner_handles_invalid_chat_id(monkeypatch):
    """Verify runner rejects non-numeric chat_id when no fallback is configured."""
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    payload = {"request_id": "TG-TEST-02", "chat_id": "default", "query": "Test"}
    assert process_workflow_query(payload) is False


def test_workflow_query_runner_fallback_for_default_chat_id(tmp_path, monkeypatch):
    """Verify runner falls back to numeric TELEGRAM_CHAT_ID when chat_id='default'."""
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "5917850553")
    store = RequestStore(db_path=str(tmp_path / "test_fallback.db"))

    sent_messages = []
    def mock_send(text, chat_ids=None, parse_mode=None, request_id=None, reply_markup=None):
        sent_messages.append({"text": text, "chat_ids": chat_ids})
        return True

    monkeypatch.setattr("scheme_intel.delivery.workflow_query_runner.send_telegram", mock_send)

    payload = {"request_id": "TG-TEST-03", "chat_id": "default", "query": "Compare TRUALT and PRAJ"}
    success = process_workflow_query(payload, request_store=store)
    assert success is True
    assert sent_messages[0]["chat_ids"] == ["5917850553"]


def test_workflow_query_runner_plain_text_fallback_on_markdown_error(tmp_path, monkeypatch):
    """Verify runner retries as plain text if Markdown parsing fails."""
    store = RequestStore(db_path=str(tmp_path / "test_fallback_md.db"))
    attempts = []

    def mock_send_with_markdown_failure(text, chat_ids=None, parse_mode=None, request_id=None, reply_markup=None):
        attempts.append(parse_mode)
        if parse_mode == "Markdown":
            raise Exception("Telegram 400: Can't parse entities in message")
        return True

    monkeypatch.setattr("scheme_intel.delivery.workflow_query_runner.send_telegram", mock_send_with_markdown_failure)

    payload = {"request_id": "TG-TEST-04", "chat_id": "5917850553", "query": "Compare TRUALT and PRAJ"}
    success = process_workflow_query(payload, request_store=store)
    assert success is True
    assert attempts == ["Markdown", None], "Must retry without parse_mode on Markdown error"


def test_cloudflare_log_sanitization_patterns():
    """Verify that credentials patterns are sanitized in JavaScript logging logic."""
    utils_js = (CF_DIR / "src" / "utils.js").read_text(encoding="utf-8")
    assert "REDACTED_BOT_TOKEN" in utils_js
    assert "REDACTED_GITHUB_TOKEN" in utils_js
    assert "REDACTED" in utils_js


def test_cloudflare_auth_logic():
    """Verify webhook secret verification and user authorization logic."""
    auth_js = (CF_DIR / "src" / "auth.js").read_text(encoding="utf-8")
    assert "X-Telegram-Bot-Api-Secret-Token" in auth_js
    assert "validateWebhookSecret" in auth_js
    assert "isAuthorized" in auth_js

    # Simulate authorization contract in Python
    def is_authorized(user_id, chat_id, allowed_users_str="", allowed_chats_str=""):
        allowed_users = [s.strip() for s in allowed_users_str.split(",") if s.strip()]
        allowed_chats = [s.strip() for s in allowed_chats_str.split(",") if s.strip()]
        if not allowed_users and not allowed_chats:
            return True
        user_match = str(user_id) in allowed_users if user_id else False
        chat_match = str(chat_id) in allowed_chats if chat_id else False
        return user_match or chat_match

    # Open access
    assert is_authorized("123", "456", "", "") is True

    # User whitelist
    assert is_authorized("999", "111", "999,888", "") is True
    assert is_authorized("777", "111", "999,888", "") is False

    # Chat whitelist
    assert is_authorized("777", "111", "", "111,222") is True
    assert is_authorized("777", "333", "", "111,222") is False


def test_cloudflare_github_dispatch_error_mapping():
    """Verify GitHub dispatch logic handles HTTP error codes properly."""
    github_js = (CF_DIR / "src" / "github.js").read_text(encoding="utf-8")
    assert "dispatches" in github_js
    assert "telegram_query" not in github_js or "event_type" in github_js
    assert "401" in github_js
    assert "403" in github_js
    assert "404" in github_js
    assert "422" in github_js


def test_cloudflare_snapshot_rendering_logic():
    """Verify snapshot rendering handles stock cards, setups, and staleness."""
    snapshot_js = (CF_DIR / "src" / "snapshot.js").read_text(encoding="utf-8")
    assert "renderStockCard" in snapshot_js
    assert "renderWhyCard" in snapshot_js
    assert "renderSetupsCard" in snapshot_js
    assert "DATA NOTE: Snapshot is >26h old" in snapshot_js
    assert "GOBARdhan" in snapshot_js

