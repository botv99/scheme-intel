# Stage 2 Test Execution Report

**Execution Timestamp**: 2026-09-23T21:47:34+05:30
**Environment**: Windows 11, Python 3.12.10, pytest 9.1.1
**Working Directory**: `C:\Users\sreej\.gemini\antigravity\scratch\scheme-intel`

---

## 1. Test Summary

| Metric | Result |
|--------|--------|
| **Total Tests Collected** | **336** |
| **Total Tests Passed** | **336** |
| **Failed** | **0** |
| **Errors** | **0** |
| **Skipped / Deselected** | **0** |
| **Total Execution Time** | **32.30 seconds** |
| **Success Rate** | **100.0%** |

---

## 2. Test Suite Breakdown

### Stage 1 Baseline Regression Suite (295 Tests — 100% Passing)

| Test Module | Tests | Status | Purpose |
|-------------|:-----:|:------:|---------|
| `tests/test_analytics.py` | 13 | PASS | Historical analytics, win/loss ratios, trade summaries |
| `tests/test_catalyst.py` | 5 | PASS | Catalyst detection, scoring & extraction |
| `tests/test_consolidated.py` | 8 | PASS | Consolidated pipeline flow |
| `tests/test_db.py` | 19 | PASS | SQLite database runs, setups, catalysts & tracking |
| `tests/test_earnings.py` | 42 | PASS | Earnings, concall transcripts, analyst call tracking |
| `tests/test_ingestion.py` | 21 | PASS | Screener, BSE/NSE, media feed ingestion |
| `tests/test_main.py` | 5 | PASS | CLI main entrypoint |
| `tests/test_models.py` | 3 | PASS | Core models & validation |
| `tests/test_notifier.py` | 11 | PASS | Telegram notification formatting & sending |
| `tests/test_pipeline.py` | 9 | PASS | Stage 1 preparation pipeline |
| `tests/test_reliability.py` | 33 | PASS | Source reliability tracking & tier adjustments |
| `tests/test_signals.py` | 20 | PASS | Technical signal generation & indicator validation |
| `tests/test_sources.py` | 11 | PASS | Source fetching & scraping |
| `tests/test_sources_expanded.py` | 29 | PASS | Expanded sources (PIB, ministries, portals) |
| `tests/test_stage1_comprehensive.py` | 19 | PASS | End-to-end Stage 1 system verification |
| `tests/test_trade_call.py` | 32 | PASS | Trade call evaluation & risk scoring |
| `tests/test_watchlist_alerts.py` | 15 | PASS | Alert delivery and throttling |
| **Stage 1 Subtotal** | **295** | **PASS** | **Verified untouched baseline** |

### Stage 2 Comprehensive Suite (32 Tests — 100% Passing)

| Test Case | Status | Requirement Verified |
|-----------|:------:|----------------------|
| `test_models_stock_and_news` | PASS | Pydantic schema validation for Stock and NewsItem |
| `test_models_technical_snapshot` | PASS | TechnicalSnapshot metrics and indicator fields |
| `test_calendar_trading_day_detection` | PASS | Weekday, weekend (Sat/Sun), and NSE holiday detection |
| `test_calendar_next_trading_day` | PASS | Skips weekends and holidays (e.g. Thu->Fri, Fri->Mon, holiday skip) |
| `test_calendar_market_session_info` | PASS | After-market 16:30 IST window & session metadata |
| `test_market_technical_snapshot_builder` | PASS | OHLCV history -> Moving averages, RSI, ATR, Regimes |
| `test_market_data_engine_defaults` | PASS | MarketDataEngine lookup & deterministic fallback generation |
| `test_news_classification` | PASS | Material event detection, source tiering & company matching |
| `test_news_engine_grouping` | PASS | News grouping by watchlist company |
| `test_catalyst_impact_scoring_direct` | PASS | Direct beneficiary, strength, certainty, freshness |
| `test_catalyst_priced_in_check` | PASS | "Priced in" detection based on prior run-up & overbought RSI |
| `test_candidate_breakout` | PASS | Archetype 1: Breakout setup detection |
| `test_candidate_breakout_anticipation` | PASS | Archetype 2: Breakout Anticipation setup detection |
| `test_candidate_pullback` | PASS | Archetype 3: Pullback setup with confirmed uptrend requirement |
| `test_candidate_momentum_continuation` | PASS | Archetype 4: Momentum Continuation setup detection |
| `test_candidate_event_driven` | PASS | Archetype 5: High-materiality Event-Driven setup detection |
| `test_bull_agent` | PASS | Bull Swing Hunter structured thesis generation & risk acknowledgement |
| `test_bear_agent` | PASS | Bear Trade Killer stress-test, invalidation & required confirmations |
| `test_debate_orchestrator` | PASS | Multi-round adversarial debate orchestration (Bull, Bear, Arbitrator) |
| `test_risk_engine_passing_setup` | PASS | Hard Risk Engine valid setup: SL, T1 (1.8R), T2 (2.8R), T3, sizing |
| `test_invalidation_logic_directionally_consistent` | PASS | Strictly separates technical invalidation (below SL) from breakout failure |
| `test_risk_reward_explicit_calculation` | PASS | Mathematical identity check & transparent R:R basis display |
| `test_entry_zone_strictly_satisfies_minimum_rr` | PASS | Entry zone ceiling capped so worst-case R:R >= 1.50:1 |
| `test_position_sizing_mathematical_limits` | PASS | Verified 1% rupee risk limit and 10% maximum capital allocation |
| `test_risk_engine_stop_distance_veto` | PASS | Mathematical veto: Stop loss > 8% rejected |
| `test_risk_engine_liquidity_veto` | PASS | Mathematical veto: Volume < 20,000 shares rejected |
| `test_risk_engine_inverted_entry_zone_veto` | PASS | Mathematical veto: Compressed / inverted entry zone rejected |
| `test_waiting_engine_generation` | PASS | Setup Waiting Engine generates concrete future trigger blueprints |
| `test_watchlist_full_coverage` | PASS | Scanner guarantees 100% watchlist coverage without silent omissions |
| `test_storage_and_outcome_tracking` | PASS | SQLite persistence for setups, debates, and MFE/MAE outcomes |
| `test_telegram_report_formatting` | PASS | 3-Section Telegram report formatting with explicit NEXT SESSION |
| `test_telegram_empty_catalysts_safe` | PASS | Crash-proof against empty catalyst lists in stock cards |
| `test_production_mode_uses_live_sources_not_mocks` | PASS | Production pipeline enforces live sources and does not mock data |
| `test_full_pipeline_run` | PASS | End-to-end dry-run of complete Stage 2 preparation pipeline |
| `test_entry_trigger_detection` | PASS | OutcomeTracker detects entry trigger occurrence from daily OHLC |
| `test_mfe_mae_and_holding_period_tracking` | PASS | Continuous tracking of MFE %, MAE %, and holding period days |
| `test_target_1_hit_detection` | PASS | Detects Target 1 exit and calculates realized gain % |
| `test_stop_loss_hit_detection` | PASS | Detects Stop Loss exit and calculates realized loss % |
| `test_closed_trade_not_reprocessed` | PASS | Ensures exited setups are never reprocessed or double counted |
| `test_pipeline_dispatch_sends_sections` | PASS | Verifies multi-section Telegram dispatch with chunking |
| `test_main_run_unifies_stage1_and_stage2` | PASS | Verifies main.py unifies Stage 1 ingestion + Stage 2 execution |
| **Stage 2 / Production Subtotal** | **41** | **PASS** | **100% executable and tested** |

---

## 3. Integration Verification

- Command executed: `python -m pytest -q`
- Output: `336 passed in 32.30s`
- Zero regressions against Stage 1 tag `stage1-complete`.
- No mock leaks or dependencies on live external network connections for tests.
