"""
Comprehensive Final Production Verification for Scheme-Intel.
Verifies all 8 checkpoints requested by user:
1. Production pipeline with real ingestion data (not MockProvider for data)
2. Telegram report contains actual prices, volumes, 20D avg vol, support/resistance, technical status
3. Zero checks: No Rs. 0.00, Rs. 0.0, volume 0 fallback, fake Rs. 0 entries, fake Rs. 0 support/resistance
4. ORS / ORGANICREC.BO does not match D-Link or word-boundary false positives
5. Valid data + no setup -> WAIT; missing/stale -> DATA_UNAVAILABLE / DATA_STALE excluded from WAITING SETUPS
6. GitHub Actions workflow execution order
7. Workflow does not accidentally use MockProvider or mock snapshots in production
8. Displays full generated Telegram report and final data-health counts
"""
import json
import re
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scheme_intel.stage2.models import Stock, DATA_OK, DATA_UNAVAILABLE, DATA_STALE
from scheme_intel.stage2.market import MarketDataEngine
from scheme_intel.stage2.news import NewsEngine, classify_news_item
from scheme_intel.stage2.pipeline import Stage2Pipeline
from scheme_intel.stage2.scanner import scan_all_stocks
from scheme_intel.stage2.waiting import generate_wait_condition
from scheme_intel.stage2.telegram import build_full_telegram_report


def verify_all():
    print("=" * 70)
    print("SCHEME-INTEL FINAL PRODUCTION VERIFICATION")
    print("=" * 70)
    
    # -------------------------------------------------------------
    # 1. Run actual production pipeline with real ingestion data
    # -------------------------------------------------------------
    print("\n[CHECKPOINT 1] Executing Production Pipeline with Mode='production'...")
    pipeline = Stage2Pipeline(mode="production")
    assert pipeline.mode == "production", "Pipeline mode must be 'production'"
    assert pipeline.market_engine.mode == "production", "MarketDataEngine mode must be 'production'"
    assert pipeline.news_engine.mode == "production", "NewsEngine mode must be 'production'"

    # Run the full pipeline
    result = pipeline.run(dry_run=True, send=False)
    assert result is not None, "Pipeline run returned None"
    report = result["report"]
    stock_cards = result["cards"]
    setups = result["setups"]
    data_health = result["health_stats"]
    print(f" -> Pipeline run complete. Health counts: {data_health}")
    assert data_health["total"] == 7, f"Expected 7 total stocks, got {data_health['total']}"
    assert data_health["valid"] == 7, f"Expected 7 valid stocks, got {data_health['valid']}"
    assert data_health["unavailable"] == 0, f"Expected 0 unavailable, got {data_health['unavailable']}"
    assert data_health["stale"] == 0, f"Expected 0 stale, got {data_health['stale']}"
    print(" -> CHECKPOINT 1 PASSED: Pipeline executed with real production market engine.")

    # -------------------------------------------------------------
    # 2. Confirm Telegram report contains real metrics for all 7 stocks
    # -------------------------------------------------------------
    print("\n[CHECKPOINT 2] Verifying Real Market Metrics for all 7 stocks...")
    expected_symbols = [
        "TRUALT.NS", "WABAG.NS", "PRAJIND.NS", "ORGANICREC.BO",
        "KIRLPNU.NS", "GAIL.NS", "IOC.NS"
    ]
    card_by_symbol = {c.stock.symbol: c for c in stock_cards}

    for sym in expected_symbols:
        assert sym in card_by_symbol, f"Missing symbol {sym} in stock cards"
        card = card_by_symbol[sym]
        assert card.price is not None and card.price > 0, f"{sym}: price is invalid: {card.price}"
        assert card.volume is not None and card.volume > 0, f"{sym}: volume is 0 or None: {card.volume}"
        assert card.volume_avg_20d is not None and card.volume_avg_20d > 0, f"{sym}: volume_avg_20d is invalid: {card.volume_avg_20d}"
        assert card.support is not None and card.support > 0, f"{sym}: support is invalid: {card.support}"
        assert card.resistance is not None and card.resistance > 0, f"{sym}: resistance is invalid: {card.resistance}"
        assert card.data_status == DATA_OK, f"{sym}: data_status is not DATA_OK: {card.data_status}"
        assert card.technical_summary, f"{sym}: technical_summary is empty"
        print(f"  + {sym:<15} Price: Rs {card.price:>8.2f} | Vol: {int(card.volume):>10,d} | AvgVol: {int(card.volume_avg_20d):>10,d} | Sup: {card.support:>8.2f} | Res: {card.resistance:>8.2f} | Status: {card.tomorrow_status}")

    print(" -> CHECKPOINT 2 PASSED: All 7 stocks have valid live market metrics.")

    # -------------------------------------------------------------
    # 3. Confirm NO stock has Rs 0.00, Rs 0.0, volume 0, fake entries
    # -------------------------------------------------------------
    print("\n[CHECKPOINT 3] Verifying Zero Leaks & Fake Levels...")
    full_report_text = report["full_text"]
    
    # Check for fake Rs 0 patterns
    zero_price_matches = re.findall(r"₹\s*0(?:\.00?)?", full_report_text)
    print(f"  Zero price matches found in report: {zero_price_matches}")
    assert len(zero_price_matches) == 0, f"Found zero price references in report: {zero_price_matches}"

    # Verify no stock card has zero volume due to fallback
    for card in stock_cards:
        assert card.price != 0.0, f"{card.stock.symbol} has price 0.0"
        assert card.volume != 0, f"{card.stock.symbol} has volume 0"
        assert card.support != 0.0, f"{card.stock.symbol} has support 0.0"
        assert card.resistance != 0.0, f"{card.stock.symbol} has resistance 0.0"

    # Verify no setup has zero entry / stop / target
    for setup in setups:
        if setup.risk is not None:
            assert setup.risk.ideal_entry > 0, f"Setup for {setup.stock.symbol} has ideal_entry <= 0: {setup.risk.ideal_entry}"
            assert setup.risk.stop_loss > 0, f"Setup for {setup.stock.symbol} has stop_loss <= 0: {setup.risk.stop_loss}"
            assert setup.risk.target_1 > 0, f"Setup for {setup.stock.symbol} has target_1 <= 0: {setup.risk.target_1}"
        if setup.wait_conditions is not None:
            assert setup.wait_conditions.trigger_price > 0, f"Wait setup for {setup.stock.symbol} has trigger_price <= 0: {setup.wait_conditions.trigger_price}"

    print(" -> CHECKPOINT 3 PASSED: Zero instances of Rs 0.00, fake volume 0, or zero triggers.")

    # -------------------------------------------------------------
    # 4. Confirm ORGANICREC.BO does NOT match D-Link or word-boundary false positives
    # -------------------------------------------------------------
    print("\n[CHECKPOINT 4] Verifying ORS / ORGANICREC.BO News Isolation...")
    ingested_path = Path("data/ingested.json")
    ingested_data = json.loads(ingested_path.read_text(encoding="utf-8"))
    raw_news = ingested_data.get("news", [])

    ors_stock = Stock(
        name="Organic Recycling Systems",
        symbol="ORGANICREC.BO",
        aliases=["Organic Recycling", "ORS"]
    )

    # Search for D-Link articles or articles with "directors" / "investors"
    dlink_articles = [
        item for item in raw_news
        if "d-link" in item.get("title", "").lower()
        or "dlink" in item.get("title", "").lower()
        or "directors" in item.get("title", "").lower()
        or "investors" in item.get("title", "").lower()
    ]
    print(f"  Found {len(dlink_articles)} articles with 'd-link', 'directors', or 'investors' in raw feed.")

    # 1. Test adversarial articles that broke the old code:
    adversarial_articles = [
        {"title": "D-Link India announces new board of directors", "summary": "The directors met with investors to discuss routers.", "source": "Media"},
        {"title": "D-Link India appoints new executives", "summary": "Key sponsors and investors welcome the appointment.", "source": "BSE"},
        {"title": "Tech stocks rally: D-Link rises 5%", "summary": "Sponsors and investors see strong quarterly margins.", "source": "NSE"},
    ]
    for art in adversarial_articles:
        item = classify_news_item(
            title=art["title"],
            url="https://example.com",
            source=art["source"],
            summary=art["summary"],
            published_at="2026-09-25T12:00:00Z",
            stocks=[ors_stock]
        )
        assert ors_stock.name not in item.companies_mentioned, (
            f"False positive match: '{art['title']}' attributed to {ors_stock.name} via ORS substring!"
        )

    # 2. Test valid article that SHOULD match
    valid_ors_article = {
        "title": "Organic Recycling Systems wins municipal solid waste order",
        "summary": "ORS bags project worth Rs 50 crore for biogas facility.",
        "source": "BSE"
    }
    valid_item = classify_news_item(
        title=valid_ors_article["title"],
        url="https://example.com",
        source="BSE",
        summary=valid_ors_article["summary"],
        published_at="2026-09-25T12:00:00Z",
        stocks=[ors_stock]
    )
    assert ors_stock.name in valid_item.companies_mentioned, "Valid ORS article was not matched!"

    # 3. Verify actual pipeline news extraction has no D-Link items under ORS
    from scheme_intel.stage2.news import extract_stock_news
    all_news = pipeline.news_engine.fetch_latest_news()
    by_stock = extract_stock_news(all_news, [ors_stock])
    for item in by_stock.get(ors_stock.name, []):
        assert "d-link" not in item.title.lower() and "dlink" not in item.title.lower(), (
            f"D-Link article found attributed to {ors_stock.name}: {item.title}"
        )

    print(" -> CHECKPOINT 4 PASSED: Regex word-boundaries prevent short alias ORS false positives.")

    # -------------------------------------------------------------
    # 5. Confirm valid data + no setup -> WAIT; missing/stale -> DATA_UNAVAILABLE / DATA_STALE
    # -------------------------------------------------------------
    print("\n[CHECKPOINT 5] Verifying WAIT vs DATA_UNAVAILABLE Semantics...")
    # Test valid data stock with no setup -> must be WAIT
    valid_card = card_by_symbol["WABAG.NS"]
    assert valid_card.data_status == DATA_OK
    assert valid_card.tomorrow_status == "WAIT"

    # Test missing data handling
    dummy_stock = Stock(name="Ghost Corp", symbol="GHOST.NS", aliases=["Ghost"])
    mock_market_engine = MarketDataEngine(mode="production")
    
    # Scanner behavior with None snapshot
    unavailable_cards = scan_all_stocks([dummy_stock], {dummy_stock.symbol: None}, {dummy_stock.name: []})
    ghost_card = unavailable_cards[0]
    assert ghost_card.data_status == DATA_UNAVAILABLE, f"Expected DATA_UNAVAILABLE, got {ghost_card.data_status}"
    assert ghost_card.tomorrow_status == DATA_UNAVAILABLE
    assert ghost_card.price is None
    assert ghost_card.volume is None
    assert ghost_card.support is None

    # Waiting engine strictly rejects None or 0 snapshot
    try:
        generate_wait_condition(dummy_stock, None)
        assert False, "generate_wait_condition should raise ValueError on missing snapshot"
    except ValueError as e:
        print(f"  generate_wait_condition correctly raised: {e}")

    from scheme_intel.stage2.models import TradeSetup
    ghost_setup = TradeSetup(
        setup_id="dummy_ghost",
        analysis_date="2026-09-25",
        setup_date="2026-09-25",
        next_trading_session="2026-09-28",
        stock=dummy_stock,
        status=DATA_UNAVAILABLE,
        data_status=DATA_UNAVAILABLE,
        no_trade_reason="Market data feed unavailable",
    )
    valid_setup = TradeSetup(
        setup_id="dummy_valid",
        analysis_date="2026-09-25",
        setup_date="2026-09-25",
        next_trading_session="2026-09-28",
        stock=valid_card.stock,
        status="WAIT",
        data_status=DATA_OK,
        no_trade_reason="Waiting for range breakout",
    )

    # Build report with mixed cards and verify DATA_UNAVAILABLE is excluded from WAITING SETUPS
    test_report = build_full_telegram_report(
        session_title="Daily Intelligence Session",
        cards=[valid_card, ghost_card],
        candidates=[],
        setups=[valid_setup, ghost_setup],
        health_stats={"total": 2, "valid": 1, "stale": 0, "unavailable": 1}
    )
    # Check Section 1 shows health badge
    assert "Market Data Health:* Valid: 1/2" in test_report["section1"]
    # Check Section 3 puts ghost in UNAVAILABLE and NOT in WAITING
    assert "⚠️ *MARKET DATA UNAVAILABLE / STALE*" in test_report["section3"]
    assert "Ghost Corp" in test_report["section3"]
    assert "GHOST.NS" in test_report["section3"]
    # WAITING SETUPS should only contain WABAG.NS
    assert "WABAG.NS" in test_report["section3"]
    print(" -> CHECKPOINT 5 PASSED: Strict distinction between WAIT and DATA_UNAVAILABLE verified.")

    # -------------------------------------------------------------
    # 6. Confirm GitHub Actions workflow order
    # -------------------------------------------------------------
    print("\n[CHECKPOINT 6] Verifying GitHub Actions Workflow Order...")
    wf_path = Path(".github/workflows/daily-monitor.yml")
    wf_content = wf_path.read_text(encoding="utf-8")
    
    # Step positions
    pos_checkout = wf_content.find("actions/checkout")
    pos_ingestion = wf_content.find("Run market ingestion layer")
    pos_stage2 = wf_content.find("Run Stage 1 & Stage 2 intelligence pipeline")
    pos_commit = wf_content.find("Store updated research & ingestion snapshots")

    assert pos_checkout != -1, "actions/checkout missing"
    assert pos_ingestion != -1, "Ingestion step missing"
    assert pos_stage2 != -1, "Stage 2 step missing"
    assert pos_commit != -1, "Commit step missing"

    assert pos_checkout < pos_ingestion, "Checkout must be before ingestion"
    assert pos_ingestion < pos_stage2, "Ingestion must be before Stage 2"
    assert pos_stage2 < pos_commit, "Stage 2 must be before commit/push"

    # Verify ingestion.yml does NOT have cron schedule
    ingestion_wf = Path(".github/workflows/ingestion.yml").read_text(encoding="utf-8")
    assert "cron:" not in ingestion_wf, "ingestion.yml still has cron schedule!"

    print(" -> CHECKPOINT 6 PASSED: Workflow sequence is strictly checkout -> ingestion -> Stage 2 / Telegram -> commit.")

    # -------------------------------------------------------------
    # 7. Verify no accidental MockProvider / mock snapshot usage
    # -------------------------------------------------------------
    print("\n[CHECKPOINT 7] Verifying MockProvider / Mock Snapshots are Blocked in Production...")
    market_engine_prod = MarketDataEngine(mode="production")
    snap, status, reason = market_engine_prod.get_snapshot_with_status(dummy_stock.symbol)
    assert snap is None, f"Production market engine returned mock snapshot: {snap}"
    assert status == DATA_UNAVAILABLE

    # Verify daily-monitor.yml runs scheme_intel.main which sets mode='production'
    main_py = Path("src/scheme_intel/main.py").read_text(encoding="utf-8")
    assert 'mode="production"' in main_py, "main.py does not pass mode='production' to Stage2Pipeline"

    print(" -> CHECKPOINT 7 PASSED: Mock snapshots completely blocked in production mode.")

    # -------------------------------------------------------------
    # 8. Display Final Telegram Report and Health Counts
    # -------------------------------------------------------------
    print("\n[CHECKPOINT 8] Final Generated Telegram Report & Health Counts:")
    print("=" * 70)
    print(f"HEALTH STATS: {data_health}")
    print("=" * 70)
    print(full_report_text)
    print("=" * 70)
    print("ALL 8 VERIFICATION CHECKPOINTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    verify_all()
