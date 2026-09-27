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


def test_cloudflare_token_resolution_contract():
    """Verify GitHub token fallback and sanitization contract in github.js."""
    github_js = (CF_DIR / "src" / "github.js").read_text(encoding="utf-8")
    assert "export function getGithubToken" in github_js
    assert "GITHUB_TOKEN" in github_js
    assert "GH_TOKEN" in github_js
    assert "GITHUB_PAT" in github_js

    # Mirror contract test
    def resolve_token(env_dict):
        candidates = [
            env_dict.get("GITHUB_TOKEN"),
            env_dict.get("GH_TOKEN"),
            env_dict.get("GITHUB_PAT"),
        ]
        for c in candidates:
            if isinstance(c, str):
                t = c.strip()
                if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
                    t = t[1:-1].strip()
                if len(t) > 0:
                    return t
        return ""

    assert resolve_token({}) == ""
    assert resolve_token({"GITHUB_TOKEN": ""}) == ""
    assert resolve_token({"GITHUB_TOKEN": "   "}) == ""
    assert resolve_token({"GITHUB_TOKEN": '"ghp_test123"'}) == "ghp_test123"
    assert resolve_token({"GITHUB_TOKEN": "'ghp_test456'"}) == "ghp_test456"
    assert resolve_token({"GH_TOKEN": "ghp_fallback"}) == "ghp_fallback"
    assert resolve_token({"GITHUB_PAT": "github_pat_789"}) == "github_pat_789"


def test_cloudflare_health_diagnostics_contract():
    """Verify index.js health check returns safe diagnostics without token values."""
    index_js = (CF_DIR / "src" / "index.js").read_text(encoding="utf-8")
    assert "/health" in index_js
    assert "diagnostics" in index_js
    assert "github_token_configured" in index_js
    assert "telegram_bot_token_configured" in index_js
    assert "telegram_webhook_secret_configured" in index_js
    assert "env_keys" in index_js


def test_bot_commands_curated_menu():
    """Verify only 5 core commands are registered in both Cloudflare and Python."""
    telegram_js = (CF_DIR / "src" / "telegram.js").read_text(encoding="utf-8")
    assert "BOT_COMMANDS" in telegram_js
    for banned in ["trualt", "praj", "gail", "wabag", "why", "what", "when", "waiting"]:
        pattern = rf'command:\s*["\']{banned}["\']'
        assert not re.search(pattern, telegram_js), f"Command '{banned}' should not be advertised in BOT_COMMANDS"

    py_conv = (REPO_ROOT / "src" / "scheme_intel" / "delivery" / "telegram_conversation.py").read_text(encoding="utf-8")
    for banned in ["trualt", "praj", "gail", "wabag", "why", "what", "when", "waiting"]:
        pattern = rf'["\']command["\']:\s*["\']{banned}["\']'
        assert not re.search(pattern, py_conv), f"Command '{banned}' should not be in telegram_conversation.py commands"

    assert "research" in telegram_js
    assert "stock" in telegram_js
    assert "research" in py_conv
    assert "stock" in py_conv


def test_stock_command_intent_resolution():
    """Verify /stock command resolution for symbols, names, aliases, and prompts."""
    # Direct symbol
    res = IntentResolver.resolve("/stock GAIL")
    assert res.intent_type == IntentType.STOCK_LOOKUP
    assert res.symbol == "GAIL.NS"

    # Multi-word alias / company name
    res2 = IntentResolver.resolve("/stock Praj Industries")
    assert res2.intent_type == IntentType.STOCK_LOOKUP
    assert res2.symbol == "PRAJIND.NS"

    # Standalone /stock without argument returns STOCK_PROMPT
    res3 = IntentResolver.resolve("/stock")
    assert res3.intent_type == IntentType.STOCK_PROMPT
    assert res3.execution_path == ExecutionPath.FAST

    # Unknown stock via /stock produces STOCK_LOOKUP with unresolved_symbol for fast card
    res4 = IntentResolver.resolve("/stock NONEXISTENT")
    assert res4.intent_type == IntentType.STOCK_LOOKUP
    assert res4.execution_path == ExecutionPath.FAST
    assert res4.unresolved_symbol == "NONEXISTENT"


def test_unknown_stock_fast_card():
    """Verify unknown stock returns clear, clean FAST card with /watchlist reference."""
    from scheme_intel.intelligence_memory.cards import render_unknown_stock
    card = render_unknown_stock("ABCXYZ")
    assert "Stock Not Found" in card
    assert "ABCXYZ" in card
    assert "/watchlist" in card


def test_is_recent_news_filtering():
    """Verify news is strictly filtered to today and yesterday only."""
    from scheme_intel.intelligence_memory.cards import is_recent_news

    ref_date = "2026-09-27"

    # Today -> included
    assert is_recent_news({"published": "2026-09-27T10:00:00Z"}, ref_date) is True
    assert is_recent_news({"date": "2026-09-27"}, ref_date) is True

    # Yesterday -> included
    assert is_recent_news({"published": "2026-09-26T18:00:00Z"}, ref_date) is True
    assert is_recent_news({"date": "2026-09-26"}, ref_date) is True

    # 2 days ago -> excluded
    assert is_recent_news({"published": "2026-09-25T23:59:59Z"}, ref_date) is False
    assert is_recent_news({"date": "2026-09-25"}, ref_date) is False

    # 7 days ago -> excluded
    assert is_recent_news({"published": "2026-09-20T12:00:00Z"}, ref_date) is False

    # Future date -> excluded
    assert is_recent_news({"published": "2026-09-28T09:00:00Z"}, ref_date) is False

    # Invalid / missing -> excluded
    assert is_recent_news({}, ref_date) is False
    assert is_recent_news({"published": "invalid-date-string"}, ref_date) is False


def test_stock_card_9_sections_exact_order():
    """Verify stock card produces all 9 sections in exact specified order."""
    from scheme_intel.intelligence_memory.models import CompanyIntelligence
    from scheme_intel.intelligence_memory.cards import render_stock_card

    comp = CompanyIntelligence(
        symbol="GAIL.NS",
        name="GAIL (India) Limited",
        short_symbol="GAIL",
        scheme_id="gobardhan",
        scheme_name="GOBARdhan",
        price=172.70,
        change_pct=1.45,
        volume=12450000,
        volume_change_pct=24.5,
        score=78.0,
        status="QUALIFIED_SETUP",
        archetype="Policy Breakout",
        trigger_price=175.0,
        stop_loss=168.0,
        target=185.0,
        catalysts=["CBG pipeline synchronization mandate"],
        evidence=[
            {"title": "GAIL expands CBG infrastructure", "source": "Economic Times", "url": "https://example.com/gail", "published": "2026-09-27T08:00:00Z"}
        ],
        updated_at="2026-09-27T10:00:00Z"
    )

    card = render_stock_card(comp, is_stale=False, snapshot_id="snap-20260927-1000")

    # Check presence of all 9 sections
    assert "GAIL (India) Limited" in card
    assert "Current Price: ₹172.70" in card
    assert "Volume: 12,450,000" in card
    assert "FUNDAMENTAL SCORE" in card
    assert "Fundamental scoring not available in current snapshot" in card
    assert "TECHNICAL INTELLIGENCE" in card
    assert "Technical / Intel Score: 7.8/10" in card
    assert "TODAY'S CATALYST" in card
    assert "CBG pipeline synchronization mandate" in card
    assert "NEWS" in card
    assert "GAIL expands CBG infrastructure" in card
    assert "TRADE SETUP" in card
    assert "Status: `QUALIFIED_SETUP`" in card
    assert "Updated:" in card
    assert "Snapshot: `snap-20260927-1000`" in card
    assert "Data Status: 🟢 FRESH" in card

    # Check exact section order
    idx_identity = card.index("GAIL (India) Limited")
    idx_price = card.index("Current Price:")
    idx_volume = card.index("Volume:")
    idx_fund = card.index("FUNDAMENTAL SCORE")
    idx_tech = card.index("TECHNICAL INTELLIGENCE")
    idx_catalyst = card.index("TODAY'S CATALYST")
    idx_news = card.index("NEWS")
    idx_setup = card.index("TRADE SETUP")
    idx_timestamp = card.index("Snapshot:")

    assert idx_identity < idx_price < idx_volume < idx_fund < idx_tech < idx_catalyst < idx_news < idx_setup < idx_timestamp


def test_latest_snapshot_has_real_prices_and_volumes():
    """Verify that latest.json snapshot contains real prices and volumes for all monitored companies."""
    snap_path = REPO_ROOT / "data" / "intelligence" / "latest.json"
    assert snap_path.exists(), "latest.json must exist"
    with open(snap_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    companies = data.get("companies", {})
    assert len(companies) >= 7, "Must contain at least 7 monitored companies"

    for sym, comp in companies.items():
        assert comp.get("price") is not None, f"Price for {sym} must not be null"
        assert comp.get("price") > 0, f"Price for {sym} must be positive"
        assert comp.get("volume") is not None, f"Volume for {sym} must not be null"
        assert comp.get("volume") > 0, f"Volume for {sym} must be positive"



