"""
Regression Test Suite for Scheme Isolation and Watchlist Deduplication.
Verifies:
Test A: Watchlist deduplication (no duplicates, PRAJIND appears once).
Test B: Gobardhan scheme isolation (contains only Gobardhan stocks, 0 Samudra stocks).
Test C: Samudra Manthan scheme isolation (contains only Samudra stocks, 0 Gobardhan stocks).
Test D: Callback overrides stale session (gobardhan -> samudra_manthan callback routes to Samudra and updates session).
Test E: Reverse callback overrides stale session (samudra_manthan -> gobardhan callback routes to Gobardhan and updates session).
Test F: Research isolation (Samudra research prompt and queueing uses samudra_manthan scheme).
Test G: No hard-coded Gobardhan in query engine (Samudra query produces dynamic Samudra header and stocks).
Test H: Malformed setup handling (undefined, NaN rejected; clean fallback rendered).
Test I: Legacy snapshot with duplicate aliases loaded into retriever returns clean, unique stocks.
Test J: Commercial entitlement gate strictly enforces callback target scheme.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scheme_intel.intelligence_memory.models import (
    IntelligenceSnapshot,
    CompanyIntelligence,
    SchemeIntelligence,
    SnapshotHealthStatus,
)
from scheme_intel.intelligence_memory.retrieval import (
    FastIntelligenceRetriever,
    is_valid_qualified_setup,
)
from scheme_intel.intelligence_memory.cards import (
    render_watchlist_card,
    render_setups_card,
)
from scheme_intel.intelligence_memory.resolver import IntentResolver, IntentType
from scheme_intel.delivery.telegram_router import TelegramMessageRouter, RouterResponse
from scheme_intel.delivery.query_engine import ComplexQueryEngine, get_companies_for_scheme
from scheme_intel.research.queue import ResearchQueue
from scheme_intel.licensing.session import SessionStore
from scheme_intel.licensing.service import EntitlementService
from scheme_intel.schemes.registry import SchemeRegistry


# ---------------------------------------------------------------------------
# FIXTURES & HELPERS
# ---------------------------------------------------------------------------

def make_retriever_with_snapshot(snap: IntelligenceSnapshot) -> FastIntelligenceRetriever:
    mock_store = MagicMock()
    mock_store.snapshot_path = Path("/mock/test/latest.json")
    mock_store.load.return_value = snap
    mock_store.load_latest.return_value = snap
    mock_store.load_with_status.return_value = (SnapshotHealthStatus.READY, snap, "OK")
    return FastIntelligenceRetriever(store=mock_store)


@pytest.fixture
def isolated_snapshot() -> IntelligenceSnapshot:
    """Snapshot containing distinct Gobardhan and Samudra Manthan companies."""
    now_utc = datetime.now(timezone.utc).isoformat()

    praj = CompanyIntelligence(
        symbol="PRAJIND.NS",
        short_symbol="PRAJIND",
        name="Praj Industries",
        scheme_id="gobardhan",
        scheme_name="GOBARdhan / SATAT Initiative",
        status="QUALIFIED_SETUP",
        archetype="Breakout",
        price=550.0,
        change_pct=1.5,
        trigger_price=555.0,
        stop_loss=530.0,
        target=600.0,
        score=82.0,
        updated_at=now_utc,
    )
    trualt = CompanyIntelligence(
        symbol="TRUALT.NS",
        short_symbol="TRUALT",
        name="TruAlt Bioenergy",
        scheme_id="gobardhan",
        scheme_name="GOBARdhan / SATAT Initiative",
        status="WAIT",
        archetype="Pullback",
        price=120.0,
        change_pct=-0.5,
        trigger_price=125.0,
        stop_loss=115.0,
        target=140.0,
        score=75.0,
        updated_at=now_utc,
    )
    ongc = CompanyIntelligence(
        symbol="ONGC.NS",
        short_symbol="ONGC",
        name="Oil and Natural Gas Corporation",
        scheme_id="samudra_manthan",
        scheme_name="Samudra Manthan",
        status="QUALIFIED_SETUP",
        archetype="DeepValue",
        price=260.0,
        change_pct=2.1,
        trigger_price=262.0,
        stop_loss=250.0,
        target=290.0,
        score=88.0,
        updated_at=now_utc,
    )
    oil = CompanyIntelligence(
        symbol="OIL.NS",
        short_symbol="OIL",
        name="Oil India Limited",
        scheme_id="samudra_manthan",
        scheme_name="Samudra Manthan",
        status="WAIT",
        archetype="Momentum",
        price=430.0,
        change_pct=0.8,
        trigger_price=435.0,
        stop_loss=415.0,
        target=480.0,
        score=79.0,
        updated_at=now_utc,
    )

    gob_scheme = SchemeIntelligence(
        scheme_id="gobardhan",
        name="GOBARdhan / SATAT Initiative",
        description="Bio-CNG and CBG policy initiatives",
        watchlist_count=2,
        qualified_setups_count=1,
        waiting_count=1,
        key_developments=["SATAT Phase 2 allocation approved"],
    )
    sam_scheme = SchemeIntelligence(
        scheme_id="samudra_manthan",
        name="Samudra Manthan",
        description="Deepwater & Ultra-Deepwater E&P Mission",
        watchlist_count=2,
        qualified_setups_count=1,
        waiting_count=1,
        key_developments=["OALP Round IX bidding opened"],
    )

    return IntelligenceSnapshot(
        snapshot_id="SNAP-TEST-ISOLATION",
        generated_at=now_utc,
        scheme_id="multi",
        scheme_name="Multi-Scheme Unified",
        total_companies_monitored=4,
        companies={
            "PRAJIND.NS": praj,
            "TRUALT.NS": trualt,
            "ONGC.NS": ongc,
            "OIL.NS": oil,
        },
        schemes={
            "gobardhan": gob_scheme,
            "samudra_manthan": sam_scheme,
        },
        qualified_setups=["PRAJIND.NS", "ONGC.NS"],
        waiting_setups=["TRUALT.NS", "OIL.NS"],
    )


@pytest.fixture
def legacy_duplicate_snapshot() -> IntelligenceSnapshot:
    """Snapshot simulating legacy storage where company records were inserted under both full and short symbol."""
    now_utc = datetime.now(timezone.utc).isoformat()
    praj = CompanyIntelligence(
        symbol="PRAJIND.NS",
        short_symbol="PRAJIND",
        name="Praj Industries",
        scheme_id="gobardhan",
        scheme_name="GOBARdhan / SATAT Initiative",
        status="QUALIFIED_SETUP",
        archetype="Breakout",
        price=550.0,
        trigger_price=555.0,
        stop_loss=530.0,
        target=600.0,
        score=82.0,
        updated_at=now_utc,
    )
    ongc = CompanyIntelligence(
        symbol="ONGC.NS",
        short_symbol="ONGC",
        name="Oil and Natural Gas Corporation",
        scheme_id="samudra_manthan",
        scheme_name="Samudra Manthan",
        status="QUALIFIED_SETUP",
        archetype="DeepValue",
        price=260.0,
        trigger_price=262.0,
        stop_loss=250.0,
        target=290.0,
        score=88.0,
        updated_at=now_utc,
    )

    return IntelligenceSnapshot(
        snapshot_id="SNAP-LEGACY-DUP",
        generated_at=now_utc,
        scheme_id="multi",
        scheme_name="Multi-Scheme Unified",
        total_companies_monitored=4,
        companies={
            "PRAJIND.NS": praj,
            "PRAJIND": praj,  # duplicate alias record
            "ONGC.NS": ongc,
            "ONGC": ongc,      # duplicate alias record
        },
        qualified_setups=["PRAJIND.NS", "PRAJIND", "ONGC.NS", "ONGC"],
        waiting_setups=["PRAJIND.NS", "PRAJIND"],
    )


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

def test_a_watchlist_deduplication(legacy_duplicate_snapshot):
    """Test A: Ensure duplicate company records (e.g. PRAJIND.NS and PRAJIND) are deduplicated."""
    retriever = make_retriever_with_snapshot(legacy_duplicate_snapshot)

    watchlist = retriever.get_watchlist("gobardhan")
    assert len(watchlist) == 1, f"Expected 1 company for gobardhan, got {len(watchlist)}"
    assert watchlist[0].symbol == "PRAJIND.NS"

    rendered = render_watchlist_card(watchlist, scheme_name="GOBARdhan")
    # PRAJIND must appear as a bullet point exactly once
    assert rendered.count("• *PRAJIND*") == 1


def test_b_gobardhan_scheme_isolation(isolated_snapshot):
    """Test B: Gobardhan watchlist must contain ONLY Gobardhan stocks, never Samudra stocks."""
    retriever = make_retriever_with_snapshot(isolated_snapshot)

    watchlist = retriever.get_watchlist("gobardhan")
    symbols = [c.symbol for c in watchlist]

    assert "PRAJIND.NS" in symbols
    assert "TRUALT.NS" in symbols
    assert "ONGC.NS" not in symbols
    assert "OIL.NS" not in symbols

    rendered = render_watchlist_card(watchlist, scheme_name="GOBARdhan")
    assert "PRAJIND" in rendered
    assert "TRUALT" in rendered
    assert "ONGC" not in rendered
    assert "OIL" not in rendered


def test_c_samudra_manthan_scheme_isolation(isolated_snapshot):
    """Test C: Samudra Manthan watchlist must contain ONLY Samudra stocks, never Gobardhan stocks."""
    retriever = make_retriever_with_snapshot(isolated_snapshot)

    watchlist = retriever.get_watchlist("samudra_manthan")
    symbols = [c.symbol for c in watchlist]

    assert "ONGC.NS" in symbols
    assert "OIL.NS" in symbols
    assert "PRAJIND.NS" not in symbols
    assert "TRUALT.NS" not in symbols

    rendered = render_watchlist_card(watchlist, scheme_name="Samudra Manthan")
    assert "ONGC" in rendered
    assert "OIL" in rendered
    assert "PRAJIND" not in rendered
    assert "TRUALT" not in rendered


def test_d_callback_overrides_stale_session_gobardhan_to_samudra(isolated_snapshot, tmp_path):
    """Test D: scheme_action:watchlist:samudra_manthan overrides active_scheme=gobardhan and aligns session."""
    retriever = make_retriever_with_snapshot(isolated_snapshot)

    db_path = tmp_path / "sessions.db"
    session_store = SessionStore(db_path=db_path)
    session_store.set_active_scheme("test_user", "gobardhan")
    assert session_store.get_active_scheme("test_user") == "gobardhan"

    entitlement_service = MagicMock()
    entitlement_service.get_licensed_schemes.return_value = ["gobardhan", "samudra_manthan"]
    entitlement_service.authorize_access.return_value = (True, "Authorized")
    entitlement_service.resolve_customer.return_value = "cust_dual"

    router = TelegramMessageRouter(
        retriever=retriever,
        session_store=session_store,
        entitlement_service=entitlement_service,
    )

    resp = router.route_message("scheme_action:watchlist:samudra_manthan", user_id="test_user")

    # Verify Samudra watchlist is returned
    assert "SAMUDRA MANTHAN" in resp.text
    assert "ONGC" in resp.text
    assert "PRAJIND" not in resp.text

    # Verify session was aligned to samudra_manthan
    assert session_store.get_active_scheme("test_user") == "samudra_manthan"


def test_e_callback_overrides_stale_session_samudra_to_gobardhan(isolated_snapshot, tmp_path):
    """Test E: scheme_action:watchlist:gobardhan overrides active_scheme=samudra_manthan and aligns session."""
    retriever = make_retriever_with_snapshot(isolated_snapshot)

    db_path = tmp_path / "sessions.db"
    session_store = SessionStore(db_path=db_path)
    session_store.set_active_scheme("test_user", "samudra_manthan")
    assert session_store.get_active_scheme("test_user") == "samudra_manthan"

    entitlement_service = MagicMock()
    entitlement_service.get_licensed_schemes.return_value = ["gobardhan", "samudra_manthan"]
    entitlement_service.authorize_access.return_value = (True, "Authorized")
    entitlement_service.resolve_customer.return_value = "cust_dual"

    router = TelegramMessageRouter(
        retriever=retriever,
        session_store=session_store,
        entitlement_service=entitlement_service,
    )

    resp = router.route_message("scheme_action:watchlist:gobardhan", user_id="test_user")

    # Verify Gobardhan watchlist is returned
    assert "GOBARDHAN" in resp.text
    assert "PRAJIND" in resp.text
    assert "ONGC" not in resp.text

    # Verify session was aligned to gobardhan
    assert session_store.get_active_scheme("test_user") == "gobardhan"


def test_f_research_isolation(isolated_snapshot, tmp_path):
    """Test F: Research action for Samudra enqueues job strictly with scheme_id=samudra_manthan."""
    retriever = make_retriever_with_snapshot(isolated_snapshot)

    db_path = tmp_path / "sessions.db"
    session_store = SessionStore(db_path=db_path)
    session_store.set_active_scheme("test_user", "gobardhan")

    research_queue = MagicMock(spec=ResearchQueue)
    mock_job = MagicMock()
    mock_job.job_id = "JOB-TEST-123"
    research_queue.enqueue_job.return_value = mock_job

    entitlement_service = MagicMock()
    entitlement_service.get_licensed_schemes.return_value = ["gobardhan", "samudra_manthan"]
    entitlement_service.authorize_access.return_value = (True, "Authorized")
    entitlement_service.resolve_customer.return_value = "cust_dual"

    router = TelegramMessageRouter(
        retriever=retriever,
        session_store=session_store,
        entitlement_service=entitlement_service,
        research_queue=research_queue,
    )

    # 1. Research prompt
    prompt_resp = router.route_message("scheme_action:research:samudra_manthan", user_id="test_user")
    assert "SAMUDRA MANTHAN" in prompt_resp.text

    # 2. Research submission
    router.route_message("/research What is the OALP Round IX deepwater timeline?", user_id="test_user")
    # Verify the queued job scheme_id was samudra_manthan (since session was aligned)
    assert research_queue.enqueue_job.call_args[1]["scheme_id"] == "samudra_manthan"


def test_g_no_hardcoded_gobardhan_in_query_engine(isolated_snapshot):
    """Test G: Query engine deterministic fallback dynamically adapts to scheme_id."""
    engine = ComplexQueryEngine()
    result = engine._deterministic_fallback(
        query="what is the general scheme status?",
        snapshot=isolated_snapshot,
        scheme_id="samudra_manthan",
    )

    assert "Samudra Manthan" in result
    assert "Policy & Market Intelligence Summary" in result
    assert "Gobardhan Policy & Market Intelligence Summary" not in result
    assert "/ongc" in result.lower()
    assert "/trualt" not in result.lower()


def test_h_malformed_setup_validation():
    """Test H: Setups with NaN, missing numeric fields, or undefined archetype are rejected."""
    # 1. Valid setup passes
    valid_comp = CompanyIntelligence(
        symbol="ONGC.NS",
        short_symbol="ONGC",
        name="Oil and Natural Gas Corporation",
        scheme_id="samudra_manthan",
        scheme_name="Samudra Manthan",
        status="QUALIFIED_SETUP",
        archetype="Swing",
        trigger_price=260.0,
        stop_loss=248.0,
        target=285.0,
        score=85.0,
    )
    assert is_valid_qualified_setup(valid_comp) is True

    # 2. Malformed setup with NaN trigger_price fails
    nan_comp = CompanyIntelligence(
        symbol="BROKEN.NS",
        short_symbol="BROKEN",
        name="Broken Corp",
        scheme_id="samudra_manthan",
        scheme_name="Samudra Manthan",
        status="QUALIFIED_SETUP",
        archetype="Swing",
        trigger_price=float("nan"),
        stop_loss=248.0,
        target=285.0,
        score=85.0,
    )
    assert is_valid_qualified_setup(nan_comp) is False

    # 3. Malformed setup with None / undefined archetype fails
    undefined_comp = CompanyIntelligence(
        symbol="UNDEF.NS",
        short_symbol="UNDEF",
        name="Undefined Corp",
        scheme_id="samudra_manthan",
        scheme_name="Samudra Manthan",
        status="QUALIFIED_SETUP",
        archetype="undefined",
        trigger_price=100.0,
        stop_loss=90.0,
        target=120.0,
        score=70.0,
    )
    assert is_valid_qualified_setup(undefined_comp) is False

    # 4. render_setups_card rejects malformed setups and renders clean fallback
    rendered = render_setups_card([nan_comp, undefined_comp])
    assert "No qualified setups in the latest completed intelligence cycle." in rendered
    assert "undefined" not in rendered.lower()
    assert "nan" not in rendered.lower()
    assert "N/A/100" not in rendered


def test_i_legacy_snapshot_with_duplicate_aliases(legacy_duplicate_snapshot):
    """Test I: Legacy snapshot loaded into retriever deduplicates companies across watchlist, qualified, and waiting."""
    retriever = make_retriever_with_snapshot(legacy_duplicate_snapshot)

    # 1. Watchlist deduplication
    wl = retriever.get_watchlist("gobardhan")
    assert len(wl) == 1
    assert wl[0].symbol == "PRAJIND.NS"

    # 2. Qualified setups deduplication
    qs = retriever.get_qualified_setups("gobardhan")
    assert len(qs) == 1
    assert qs[0].symbol == "PRAJIND.NS"

    # 3. Waiting setups deduplication
    ws = retriever.get_waiting_setups("gobardhan")
    assert len(ws) == 1
    assert ws[0].symbol == "PRAJIND.NS"


def test_j_entitlement_gate_enforces_callback_scheme(isolated_snapshot, tmp_path):
    """Test J: Commercial entitlement gate checks target_scheme from callback, not stale active_scheme."""
    retriever = make_retriever_with_snapshot(isolated_snapshot)

    db_path = tmp_path / "sessions.db"
    session_store = SessionStore(db_path=db_path)
    session_store.set_active_scheme("user_gob_only", "gobardhan")

    entitlement_service = MagicMock()
    # User is licensed ONLY for gobardhan
    entitlement_service.get_licensed_schemes.return_value = ["gobardhan"]

    def auth_side_effect(scheme_id, **kwargs):
        if scheme_id == "gobardhan":
            return True, "Authorized"
        return False, f"License required for {scheme_id}"

    entitlement_service.authorize_access.side_effect = auth_side_effect

    router = TelegramMessageRouter(
        retriever=retriever,
        session_store=session_store,
        entitlement_service=entitlement_service,
    )

    # User attempts to access Samudra Manthan via callback
    resp = router.route_message("scheme_action:watchlist:samudra_manthan", user_id="user_gob_only")

    # Must be denied
    assert "ACCESS DENIED" in resp.text
    assert "samudra_manthan" in resp.text
    # Session must remain gobardhan
    assert session_store.get_active_scheme("user_gob_only") == "gobardhan"
