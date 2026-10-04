"""
Tests for Scheme Intel Payment + Authorization + Entitlement Subsystem (Stage 4 / Phase 12).
Verifies Supabase schema migration integrity, Cloudflare Worker module contracts,
workflow runner entitlement filtering, and runs the Node.js test suite.
"""
from pathlib import Path
import json
import re
import subprocess
import pytest

REPO_ROOT = Path(__file__).parent.parent
CF_DIR = REPO_ROOT / "cloudflare" / "telegram-gateway"
MIGRATION_PATH = REPO_ROOT / "supabase" / "migrations" / "20261004_scheme_intel_auth_payment_system.sql"


def test_supabase_migration_integrity():
    """Verify Supabase migration defines all 9 required tables, constraints, and seed data."""
    assert MIGRATION_PATH.exists(), "Supabase migration file must exist"
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    # 1. Required tables
    required_tables = [
        "users",
        "schemes",
        "access_keys",
        "key_entitlements",
        "user_scheme_entitlements",
        "products",
        "orders",
        "payment_events",
        "audit_events",
    ]
    for table in required_tables:
        pattern = rf"CREATE TABLE IF NOT EXISTS {table}\b"
        assert re.search(pattern, sql, re.IGNORECASE), f"Table '{table}' must be created in migration"

    # 2. Critical columns and security features
    assert "telegram_user_id" in sql
    assert "key_hash" in sql
    assert "key_prefix" in sql
    assert "order_code" in sql
    assert "provider_order_id" in sql
    assert "signature_valid" in sql
    assert "ROW LEVEL SECURITY" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql

    # 3. Seed data
    assert "gobardhan" in sql
    assert "samudra_manthan" in sql
    assert "GOBARDHAN_MONTHLY" in sql
    assert "SAMUDRA_MONTHLY" in sql
    assert "ALL_ACCESS_MONTHLY" in sql
    assert "499" in sql
    assert "799" in sql


def test_cloudflare_worker_commercial_modules():
    """Verify all commercial modules exist in cloudflare/telegram-gateway/src/."""
    expected_modules = [
        "auth.js",
        "authorization.js",
        "users.js",
        "entitlements.js",
        "keys.js",
        "orders.js",
        "admin.js",
        "supabase.js",
        "snapshot.js",
        "resolver.js",
        "index.js",
        "payments/index.js",
        "payments/razorpay.js",
        "payments/telegram-stars.js",
        "payments/webhook.js",
    ]
    for rel_path in expected_modules:
        p = CF_DIR / "src" / rel_path
        assert p.exists(), f"Module {rel_path} must exist in Cloudflare Worker src/"
        content = p.read_text(encoding="utf-8")
        assert len(content) > 100, f"Module {rel_path} must not be empty"


def test_authorization_middleware_exports():
    """Verify authorization middleware exports required methods."""
    auth_js = (CF_DIR / "src" / "authorization.js").read_text(encoding="utf-8")
    assert "getTelegramAuth" in auth_js
    assert "checkSchemeAccess" in auth_js
    assert "filterSnapshotForUser" in auth_js
    assert "getStockScheme" in auth_js


def test_keys_module_security_guarantee():
    """Verify keys module never stores plaintext keys and computes SHA-256 hashes."""
    keys_js = (CF_DIR / "src" / "keys.js").read_text(encoding="utf-8")
    assert "crypto.subtle.digest" in keys_js
    assert "SHA-256" in keys_js
    assert "hashAccessKey" in keys_js
    assert "activateAccessKey" in keys_js


def test_payment_webhook_hmac_and_idempotency():
    """Verify payment webhook verifies HMAC signature and uses event_id for idempotency."""
    webhook_js = (CF_DIR / "src" / "payments" / "webhook.js").read_text(encoding="utf-8")
    assert "verifyWebhookSignature" in webhook_js
    assert "payment_events" in webhook_js
    assert "event_id" in webhook_js
    assert "completeOrderAndGrantEntitlements" in webhook_js


def test_workflow_runner_entitlement_filtering():
    """Verify workflow_query_runner respects authorized_schemes before AI query processing."""
    from scheme_intel.delivery.workflow_query_runner import process_workflow_query
    from scheme_intel.intelligence_memory.models import IntelligenceSnapshot, CompanyIntelligence, SchemeIntelligence
    from unittest.mock import MagicMock

    now_utc = "2026-10-04T12:00:00Z"
    snapshot = IntelligenceSnapshot(
        snapshot_id="SNAP-RUNNER-TEST",
        generated_at=now_utc,
        scheme_id="multi",
        scheme_name="Multi",
        total_companies_monitored=2,
        companies={
            "TRUALT.NS": CompanyIntelligence(
                symbol="TRUALT.NS",
                short_symbol="TRUALT",
                name="TruAlt Bioenergy",
                scheme_id="gobardhan",
                scheme_name="GOBARdhan",
                price=440.0,
            ),
            "ONGC.NS": CompanyIntelligence(
                symbol="ONGC.NS",
                short_symbol="ONGC",
                name="Oil and Natural Gas Corporation",
                scheme_id="samudra_manthan",
                scheme_name="Samudra Manthan",
                price=260.0,
            ),
        },
        schemes={
            "gobardhan": SchemeIntelligence(scheme_id="gobardhan", name="GOBARdhan"),
            "samudra_manthan": SchemeIntelligence(scheme_id="samudra_manthan", name="Samudra Manthan"),
        },
        qualified_setups=["TRUALT.NS", "ONGC.NS"],
    )

    mock_retriever = MagicMock()
    mock_retriever.get_status.return_value = ("READY", snapshot, "OK")

    mock_engine = MagicMock()
    mock_engine.process_query.return_value = "Mocked query response"

    mock_store = MagicMock()
    mock_store.get_request.return_value = None

    # Test A: User authorized only for Gobardhan attempts query for Samudra Manthan
    payload_unauth = {
        "request_id": "REQ-UNAUTH-001",
        "chat_id": "12345",
        "query": "Status of ONGC",
        "scheme_id": "samudra_manthan",
        "authorized_schemes": ["gobardhan"],
    }
    with MagicMock() as mock_send:
        from unittest.mock import patch
        with patch("scheme_intel.delivery.workflow_query_runner.send_telegram", mock_send):
            result = process_workflow_query(
                payload_unauth,
                request_store=mock_store,
                retriever=mock_retriever,
                query_engine=mock_engine,
            )
            assert result is True
            # Verify engine was NOT called with unauthorized scheme
            mock_engine.process_query.assert_not_called()
            # User received access restriction notice
            assert mock_send.call_count >= 1
            sent_text = mock_send.call_args[0][0]
            assert "ACCESS RESTRICTED" in sent_text

    # Test B: User authorized for Gobardhan queries Gobardhan -> engine receives filtered snapshot
    mock_engine.reset_mock()
    payload_auth = {
        "request_id": "REQ-AUTH-002",
        "chat_id": "12345",
        "query": "Status of TRUALT",
        "scheme_id": "gobardhan",
        "authorized_schemes": ["gobardhan"],
    }
    with patch("scheme_intel.delivery.workflow_query_runner.send_telegram", MagicMock()):
        result_auth = process_workflow_query(
            payload_auth,
            request_store=mock_store,
            retriever=mock_retriever,
            query_engine=mock_engine,
        )
        assert result_auth is True
        mock_engine.process_query.assert_called_once()
        passed_snapshot = mock_engine.process_query.call_args[1]["snapshot"]
        assert "TRUALT.NS" in passed_snapshot.companies
        assert "ONGC.NS" not in passed_snapshot.companies


def test_node_full_test_suite_execution():
    """Execute the Node.js test suite and ensure all 18 test specifications pass."""
    test_file = CF_DIR / "tests" / "auth_entitlement_payment.test.js"
    assert test_file.exists(), "Node test file must exist"

    cmd = ["node", "--test", str(test_file)]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if res.returncode != 0:
        pytest.fail(f"Node.js test suite failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")

    assert "pass 18" in res.stdout or "pass 18" in res.stderr
    assert "fail 0" in res.stdout or "fail 0" in res.stderr
