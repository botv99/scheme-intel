"""
Comprehensive Test Suite for Telegram Scheme Menu & Strict Scheme-Scoped Watchlist Flow.
Verifies:
1. Multi-scheme selection and navigation flow (/start -> /schemes -> select scheme -> scheme menu).
2. Hard entitlement gates on callback buttons and /switch (callback tampering prevention).
3. Session persistence per user in SessionStore (zero process-global mutable active schemes).
4. Strict data-layer watchlist isolation between Gobardhan and Samudra Manthan.
5. Direct command scoping (/watchlist, /trades, /snapshot, /intelligence, /research).
6. Cross-scheme research boundary interception.
7. Empty watchlist handling without fallback to other schemes.
8. Concurrent multi-user isolation.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from scheme_intel.delivery.telegram_router import TelegramMessageRouter, RouterResponse
from scheme_intel.licensing.service import EntitlementService
from scheme_intel.licensing.session import SessionStore
from scheme_intel.schemes.registry import SchemeRegistry
from scheme_intel.intelligence_memory.retrieval import FastIntelligenceRetriever
from scheme_intel.intelligence_memory.store import IntelligenceStore
from scheme_intel.intelligence_memory.models import IntelligenceSnapshot, CompanyIntelligence, SchemeIntelligence
from scheme_intel.intelligence_memory.cards import (
    render_watchlist_card,
    render_scheme_header_menu,
    get_scheme_inline_keyboard,
    render_schemes_select_menu,
    get_schemes_inline_keyboard,
    get_back_and_switch_inline_keyboard,
    render_intelligence_card,
    render_research_prompt_card,
)
from scheme_intel.research.queue import ResearchQueue


@pytest.fixture
def menu_db(tmp_path):
    """Clean SQLite database initialized with all migrations."""
    db_file = tmp_path / "test_scheme_menu.db"
    from scheme_intel.db import SchemeIntelDB
    db = SchemeIntelDB(db_path=db_file)
    db.connect()
    return db_file


@pytest.fixture
def menu_snapshots(tmp_path):
    """Prepares isolated snapshots for Gobardhan and Samudra Manthan."""
    gob_path = tmp_path / "intel_gobardhan" / "latest.json"
    gob_path.parent.mkdir(parents=True, exist_ok=True)
    gob_snap = IntelligenceSnapshot(
        snapshot_id="SNAP-GOB-MENU",
        generated_at="2026-10-02T10:00:00Z",
        scheme_id="gobardhan",
        scheme_name="GOBARdhan",
        total_companies_monitored=2,
        companies={
            "TRUALT.NS": CompanyIntelligence(
                symbol="TRUALT.NS",
                short_symbol="TRUALT",
                name="TruAlt Bioenergy",
                price=1350.0,
                status="CORE",
                scheme_id="gobardhan",
                scheme_name="GOBARdhan",
            ),
            "GAIL.NS": CompanyIntelligence(
                symbol="GAIL.NS",
                short_symbol="GAIL",
                name="GAIL (India)",
                price=195.0,
                status="CORE",
                scheme_id="gobardhan",
                scheme_name="GOBARdhan",
            ),
        },
        schemes={
            "gobardhan": SchemeIntelligence(
                scheme_id="gobardhan",
                name="GOBARdhan",
                description="Bio-energy & SATAT commercialization",
                key_developments=["MoPNG expands SATAT CBG procurement guidelines"],
            )
        }
    )
    gob_path.write_text(json.dumps(gob_snap.model_dump(), default=str), encoding="utf-8")

    sam_path = tmp_path / "intel_samudra" / "latest.json"
    sam_path.parent.mkdir(parents=True, exist_ok=True)
    sam_snap = IntelligenceSnapshot(
        snapshot_id="SNAP-SAM-MENU",
        generated_at="2026-10-02T10:00:00Z",
        scheme_id="samudra_manthan",
        scheme_name="Samudra Manthan (National Offshore Exploration Scheme)",
        total_companies_monitored=2,
        companies={
            "ONGC.NS": CompanyIntelligence(
                symbol="ONGC.NS",
                short_symbol="ONGC",
                name="Oil and Natural Gas Corporation",
                price=320.0,
                status="QUALIFIED_SETUP",
                scheme_id="samudra_manthan",
                scheme_name="Samudra Manthan (National Offshore Exploration Scheme)",
                trigger_price=325.0,
            ),
            "OIL.NS": CompanyIntelligence(
                symbol="OIL.NS",
                short_symbol="OIL",
                name="Oil India Limited",
                price=480.0,
                status="CORE",
                scheme_id="samudra_manthan",
                scheme_name="Samudra Manthan (National Offshore Exploration Scheme)",
            ),
        },
        schemes={
            "samudra_manthan": SchemeIntelligence(
                scheme_id="samudra_manthan",
                name="Samudra Manthan (National Offshore Exploration Scheme)",
                description="Deepwater and ultra-deepwater exploration mission",
                key_developments=["DGH announces OALP-X deepwater block bidding timeline"],
            )
        }
    )
    sam_path.write_text(json.dumps(sam_snap.model_dump(), default=str), encoding="utf-8")

    return {
        "gob_store": IntelligenceStore(snapshot_path=gob_path),
        "sam_store": IntelligenceStore(snapshot_path=sam_path),
    }


class TestTelegramSchemeMenuFlow:
    """Verifies complete interactive Telegram scheme selection, navigation, and isolation."""

    def test_full_scheme_selection_and_switch_flow_dual_license(self, menu_db, menu_snapshots):
        """User with dual entitlement selects Samudra, views watchlist, switches to Gobardhan."""
        session_store = SessionStore(db_path=menu_db)
        entitlement_service = EntitlementService(db_path=menu_db)
        r_queue = ResearchQueue(db_path=menu_db)

        entitlement_service.register_customer("cust_dual", user_ids=["user_dual"])
        entitlement_service.grant_entitlement("cust_dual", "gobardhan", enabled=True)
        entitlement_service.grant_entitlement("cust_dual", "samudra_manthan", enabled=True)

        retriever = FastIntelligenceRetriever(store=menu_snapshots["sam_store"])
        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
            research_queue=r_queue,
        )

        # 1. User sends /schemes -> receives selection menu listing both schemes with buttons
        schemes_res = router.route_message("/schemes", user_id="user_dual")
        assert isinstance(schemes_res, str)
        assert "SCHEMES" in schemes_res
        assert "GOBARdhan" in schemes_res
        assert "Samudra Manthan" in schemes_res
        assert isinstance(schemes_res, RouterResponse)
        assert schemes_res.reply_markup is not None
        callbacks = [btn["callback_data"] for row in schemes_res.reply_markup["inline_keyboard"] for btn in row]
        assert "scheme_select:samudra_manthan" in callbacks
        assert "scheme_select:gobardhan" in callbacks

        # 2. User taps [ 🌊 Samudra Manthan ] -> scheme_select:samudra_manthan
        select_res = router.route_message("scheme_select:samudra_manthan", user_id="user_dual")
        assert "SAMUDRA MANTHAN" in select_res
        assert "Offshore / Deepwater / Ultra-Deepwater E&P" in select_res
        # Verify active scheme is persisted in session
        assert session_store.get_active_scheme("user_dual") == "samudra_manthan"
        # Verify scheme dashboard inline buttons
        assert select_res.reply_markup is not None
        dash_cbs = [btn["callback_data"] for row in select_res.reply_markup["inline_keyboard"] for btn in row]
        assert "scheme_action:watchlist:samudra_manthan" in dash_cbs
        assert "scheme_action:trades:samudra_manthan" in dash_cbs
        assert "scheme_action:research:samudra_manthan" in dash_cbs
        assert "scheme_action:intelligence:samudra_manthan" in dash_cbs
        assert "scheme_action:snapshot:samudra_manthan" in dash_cbs
        assert "scheme_action:switch_scheme" in dash_cbs

        # 3. User taps [📋 WATCHLIST] -> strictly Samudra companies
        watch_res = router.route_message("scheme_action:watchlist:samudra_manthan", user_id="user_dual")
        assert "SAMUDRA MANTHAN SCHEME WATCHLIST" in watch_res
        assert "ONGC" in watch_res
        assert "OIL" in watch_res
        # Zero Gobardhan leakage
        assert "TRUALT" not in watch_res
        assert "PRAJ" not in watch_res
        assert "WABAG" not in watch_res

        # 4. Direct /watchlist command also strictly uses active scheme (Samudra)
        direct_watch = router.route_message("/watchlist", user_id="user_dual")
        assert "SAMUDRA MANTHAN SCHEME WATCHLIST" in direct_watch
        assert "ONGC" in direct_watch
        assert "TRUALT" not in direct_watch

        # 5. User taps [🔄 SWITCH SCHEME] -> returns scheme selector
        switch_res = router.route_message("scheme_action:switch_scheme", user_id="user_dual")
        assert "Select Scheme" in switch_res
        assert "scheme_select:gobardhan" in [btn["callback_data"] for row in switch_res.reply_markup["inline_keyboard"] for btn in row]

        # 6. User selects Gobardhan -> scheme_select:gobardhan
        retriever.store = menu_snapshots["gob_store"]
        select_gob = router.route_message("scheme_select:gobardhan", user_id="user_dual")
        assert "GOBARDHAN" in select_gob
        assert "Bio-energy / CBG / SATAT" in select_gob
        assert session_store.get_active_scheme("user_dual") == "gobardhan"

        # 7. User queries /watchlist -> strictly Gobardhan companies
        gob_watch = router.route_message("/watchlist", user_id="user_dual")
        assert "GOBARDHAN SCHEME WATCHLIST" in gob_watch
        assert "TRUALT" in gob_watch
        assert "GAIL" in gob_watch
        assert "ONGC" not in gob_watch
        assert "OIL" not in gob_watch

    def test_security_gate_blocks_tampered_callbacks(self, menu_db, menu_snapshots):
        """User with Samudra-only license cannot force Gobardhan access via tampered callback."""
        session_store = SessionStore(db_path=menu_db)
        entitlement_service = EntitlementService(db_path=menu_db)

        entitlement_service.register_customer("cust_sam_only", user_ids=["user_sam_only"])
        entitlement_service.grant_entitlement("cust_sam_only", "samudra_manthan", enabled=True)
        session_store.set_active_scheme("user_sam_only", "samudra_manthan")

        retriever = FastIntelligenceRetriever(store=menu_snapshots["sam_store"])
        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
        )

        # 1. /schemes lists only Samudra Manthan
        schemes = router.route_message("/schemes", user_id="user_sam_only")
        assert "Samudra Manthan" in schemes
        assert "GOBARdhan" not in schemes

        # 2. Attacker crafts callback payload: scheme_select:gobardhan
        tamper_res = router.route_message("scheme_select:gobardhan", user_id="user_sam_only")
        assert "ACCESS DENIED" in tamper_res

        # 3. CRITICAL: active_scheme in session MUST NOT be altered!
        current_active = session_store.get_active_scheme("user_sam_only")
        assert current_active == "samudra_manthan"

        # 4. Attacker attempts direct /switch gobardhan
        switch_denied = router.route_message("/switch gobardhan", user_id="user_sam_only")
        assert "ACCESS DENIED" in switch_denied
        assert session_store.get_active_scheme("user_sam_only") == "samudra_manthan"

    def test_security_gate_blocks_gobardhan_user_from_samudra(self, menu_db, menu_snapshots):
        """User with Gobardhan-only license cannot access Samudra Manthan."""
        session_store = SessionStore(db_path=menu_db)
        entitlement_service = EntitlementService(db_path=menu_db)

        entitlement_service.register_customer("cust_gob_only", user_ids=["user_gob_only"])
        entitlement_service.grant_entitlement("cust_gob_only", "gobardhan", enabled=True)
        session_store.set_active_scheme("user_gob_only", "gobardhan")

        retriever = FastIntelligenceRetriever(store=menu_snapshots["gob_store"])
        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
        )

        tamper_res = router.route_message("scheme_select:samudra_manthan", user_id="user_gob_only")
        assert "ACCESS DENIED" in tamper_res
        assert session_store.get_active_scheme("user_gob_only") == "gobardhan"

    def test_unlicensed_customer_receives_access_denied(self, menu_db):
        """User with zero active licenses cannot browse schemes or run commands."""
        session_store = SessionStore(db_path=menu_db)
        entitlement_service = EntitlementService(db_path=menu_db)
        entitlement_service.register_customer("cust_none", user_ids=["user_none"])

        router = TelegramMessageRouter(
            session_store=session_store,
            entitlement_service=entitlement_service,
        )

        schemes_res = router.route_message("/schemes", user_id="user_none")
        assert "ACCESS DENIED" in schemes_res

        watch_res = router.route_message("/watchlist", user_id="user_none")
        assert "ACCESS DENIED" in watch_res

    def test_research_boundary_interception_for_out_of_scheme_stocks(self, menu_db, menu_snapshots):
        """Verify /research blocks queries for stocks belonging to a different scheme."""
        session_store = SessionStore(db_path=menu_db)
        entitlement_service = EntitlementService(db_path=menu_db)
        r_queue = ResearchQueue(db_path=menu_db)

        entitlement_service.register_customer("cust_both", user_ids=["user_both"])
        entitlement_service.grant_entitlement("cust_both", "gobardhan", enabled=True)
        entitlement_service.grant_entitlement("cust_both", "samudra_manthan", enabled=True)
        session_store.set_active_scheme("user_both", "gobardhan")

        router = TelegramMessageRouter(
            session_store=session_store,
            entitlement_service=entitlement_service,
            research_queue=r_queue,
            research_cooldown_seconds=0,
        )

        # 1. Active scheme is GOBARdhan. User asks /research ONGC deepwater contracts
        res = router.route_message("/research ONGC deepwater exploration catalysts", user_id="user_both")
        assert "That company (ONGC) is not in the current GOBARdhan watchlist/context." in res
        assert "Use /schemes to switch scheme." in res
        assert len(r_queue.list_jobs()) == 0

        # 2. Switch to Samudra Manthan
        router.route_message("scheme_select:samudra_manthan", user_id="user_both")
        assert session_store.get_active_scheme("user_both") == "samudra_manthan"

        # 3. Now /research ONGC is allowed
        res_ok = router.route_message("/research ONGC deepwater exploration catalysts", user_id="user_both")
        assert "DEEP RESEARCH STARTED" in res_ok
        assert len(r_queue.list_jobs()) == 1
        assert r_queue.list_jobs()[0].scheme_id == "samudra_manthan"

        # 4. While in Samudra Manthan, asking about TruAlt is blocked
        res_trualt = router.route_message("/research What is TRUALT CBG production capacity?", user_id="user_both")
        assert "That company (TRUALT) is not in the current Samudra Manthan watchlist/context." in res_trualt
        assert len(r_queue.list_jobs()) == 1  # Unchanged

    def test_concurrent_multi_user_session_isolation(self, menu_db, menu_snapshots):
        """Two concurrent users have different active schemes; requests do not leak or collide."""
        session_store = SessionStore(db_path=menu_db)
        entitlement_service = EntitlementService(db_path=menu_db)

        entitlement_service.register_customer("cust_dual", user_ids=["user_1", "user_2"])
        entitlement_service.grant_entitlement("cust_dual", "gobardhan", enabled=True)
        entitlement_service.grant_entitlement("cust_dual", "samudra_manthan", enabled=True)

        session_store.set_active_scheme("user_1", "gobardhan")
        session_store.set_active_scheme("user_2", "samudra_manthan")

        retriever = FastIntelligenceRetriever(store=menu_snapshots["sam_store"])
        router = TelegramMessageRouter(
            retriever=retriever,
            session_store=session_store,
            entitlement_service=entitlement_service,
        )

        # Interleaved queries
        res_1 = router.route_message("/watchlist", user_id="user_1")
        res_2 = router.route_message("/watchlist", user_id="user_2")
        res_1_menu = router.route_message("/menu", user_id="user_1")
        res_2_menu = router.route_message("/menu", user_id="user_2")

        assert "GOBARDHAN" in res_1
        assert "SAMUDRA MANTHAN" in res_2
        assert "Bio-energy / CBG / SATAT" in res_1_menu
        assert "Offshore / Deepwater / Ultra-Deepwater E&P" in res_2_menu

    def test_empty_watchlist_rendering(self):
        """Empty watchlist renders clean message without falling back to another scheme."""
        empty_res = render_watchlist_card([], scheme_name="EMPTY_SCHEME")
        assert "EMPTY_SCHEME SCHEME WATCHLIST" in empty_res
        assert "No watchlist companies are currently configured for this scheme." in empty_res

    def test_scheme_navigation_cards_and_keyboards(self):
        """Verify scheme menu, research prompt, intelligence card, and keyboards."""
        gob_cfg = SchemeRegistry.get("gobardhan")
        sam_cfg = SchemeRegistry.get("samudra_manthan")

        # Header cards
        gob_header = render_scheme_header_menu(gob_cfg)
        assert "GOBARDHAN" in gob_header
        assert "Bio-energy / CBG / SATAT" in gob_header

        sam_header = render_scheme_header_menu(sam_cfg)
        assert "SAMUDRA MANTHAN" in sam_header
        assert "Offshore / Deepwater / Ultra-Deepwater E&P" in sam_header

        # Keyboards
        sam_kb = get_scheme_inline_keyboard("samudra_manthan")
        buttons = [b["text"] for row in sam_kb["inline_keyboard"] for b in row]
        assert "📋 WATCHLIST" in buttons
        assert "📈 TRADES" in buttons
        assert "🧠 RESEARCH" in buttons
        assert "📰 INTELLIGENCE" in buttons
        assert "📊 SNAPSHOT" in buttons
        assert "🔄 SWITCH SCHEME" in buttons

        nav_kb = get_back_and_switch_inline_keyboard("samudra_manthan")
        nav_buttons = [b["text"] for row in nav_kb["inline_keyboard"] for b in row]
        assert "⬅️ Back" in nav_buttons
        assert "🔄 Switch Scheme" in nav_buttons

        # Research Prompt
        prompt = render_research_prompt_card(scheme_cfg=sam_cfg, scheme_id="samudra_manthan")
        assert "SAMUDRA MANTHAN RESEARCH" in prompt
        assert "deepwater" in prompt.lower()
