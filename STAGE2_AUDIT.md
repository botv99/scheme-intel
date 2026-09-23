# Stage 2 Audit: Daily Stock Intelligence + Adversarial Swing-Setup System

**Audit Date**: 2026-09-23
**Baseline Commit**: `6caa1d2` (Git Tag: `stage1-complete`)
**Test Suite Status**: **336 passed, 0 failed, 0 errors** (295 Stage 1 baseline + 41 Stage 2/Tracker tests)

---

## 1. Executive Summary

Stage 2 transforms **Scheme Intel** into an authoritative after-market preparation engine running daily after 16:30 IST on completed Indian market session data. It evaluates every watchlist stock without omission, pre-filters candidates into 5 swing archetypes, conducts multi-agent adversarial debates between a Bull Swing Hunter and Bear Trade Killer adjudicated by an Evidence Arbitrator, enforces a non-overridable quantitative Hard Risk Engine veto, generates concrete trigger conditions for waiting setups, and formats a 3-section Telegram report.

---

## 2. Requirement-by-Requirement Verification

| # | Requirement Area | Status | Executable Implementation | Test Verification |
|---|------------------|--------|---------------------------|-------------------|
| 1 | **Stage 1 Baseline Preservation** | **COMPLETE** | Stage 1 code preserved untouched. No existing functionality deleted or weakened. | All 295 Stage 1 tests pass in 21.51s (`test_analytics`, `test_catalyst`, `test_consolidated`, `test_db`, `test_earnings`, `test_ingestion`, `test_main`, `test_models`, `test_notifier`, `test_pipeline`, `test_reliability`, `test_signals`, `test_sources`, `test_sources_expanded`, `test_stage1_comprehensive`, `test_trade_call`, `test_watchlist_alerts`). |
| 2 | **Authoritative After-Market Timing & Session Representation** | **COMPLETE** | `src/scheme_intel/stage2/calendar.py`: Enforces 15:30 IST close, 16:30 IST after-market start, computes `analysis_date`, `market_close_timestamp`, `setup_date`, `next_trading_session`. | `test_calendar_trading_day_detection`, `test_calendar_next_trading_day`, `test_calendar_market_session_info`. |
| 3 | **Next Trading Session Calculation (Weekends & NSE Holidays)** | **COMPLETE** | `src/scheme_intel/stage2/calendar.py`: Contains full 2024-2026 NSE/BSE holiday set, skips weekends (Sat/Sun) and market holidays. Never assumes tomorrow is simply +1 calendar day. | `test_calendar_next_trading_day` (tested Thursday->Friday, Friday->Monday, and pre-holiday skips). |
| 4 | **100% Watchlist Coverage (No Silent Omissions)** | **COMPLETE** | `src/scheme_intel/stage2/scanner.py`: `scan_all_stocks()` guarantees every configured stock receives a Daily Stock Intelligence Card. | `test_watchlist_full_coverage` (verified missing market data stocks still appear with status). |
| 5 | **News Classification & Company Grouping** | **COMPLETE** | `src/scheme_intel/stage2/news.py`: `classify_news_item()`, `extract_stock_news()`, `NewsEngine`. Maps disclosures to watchlist tickers and resolves source tier (1 to 5). | `test_news_classification`, `test_news_engine_grouping`. |
| 6 | **Catalyst Impact Relevance Scoring** | **COMPLETE** | `src/scheme_intel/stage2/impact.py`: `score_catalyst_impact()`, `evaluate_stock_catalysts()`. Evaluates Direct vs Indirect vs Negative, strength (0-100), certainty, freshness, and whether already priced in. | `test_catalyst_impact_scoring_direct`, `test_catalyst_priced_in_check`. |
| 7 | **Technical Snapshot & Market Data Engine** | **COMPLETE** | `src/scheme_intel/stage2/market.py`: `MarketDataEngine`, `build_technical_snapshot()`. Calculates 20d/50d avg volume, volume ratio, relvol, 20/50/100/200 DMAs, EMAs, RSI-14, MACD, ROC-10/21, ATR-14, volatility regimes, Bollinger Bands, ADX, Relative Strength vs NIFTY/sector. | `test_market_technical_snapshot_builder`, `test_market_data_engine_defaults`. |
| 8 | **Deterministic Candidate Pre-Filtering (5 Archetypes)** | **COMPLETE** | `src/scheme_intel/stage2/candidate.py`: Evaluates 1. Breakout, 2. Breakout Anticipation, 3. Pullback, 4. Momentum Continuation, 5. Event-Driven. Requires confirmed trend and volume expansion. | `test_candidate_breakout`, `test_candidate_breakout_anticipation`, `test_candidate_pullback`, `test_candidate_momentum_continuation`, `test_candidate_event_driven`. |
| 9 | **🐂 Bull Swing Hunter Agent** | **COMPLETE** | `src/scheme_intel/stage2/agents/bull.py`: Formulates `BullThesis` citing evidence IDs. Proposes entry zone, target, invalidation, acknowledges at least 2 realistic risks. | `test_bull_agent`. |
| 10 | **🐻 Bear Trade Killer Agent** | **COMPLETE** | `src/scheme_intel/stage2/agents/bear.py`: Formulates `BearThesis` attacking overhead resistance, false breakout risk, and priced-in hype. Outputs `what_would_invalidate_bear` and `required_confirmation_to_buy`. | `test_bear_agent`. |
| 11 | **⚖️ Evidence Arbitrator & Source Hierarchy** | **COMPLETE** | `src/scheme_intel/stage2/agents/arbitrator.py`: Evaluates claims against 5-Tier source hierarchy (Tier 1: BSE/NSE/PIB -> Tier 5: unverified). Scores bull and bear strength, resolves disputed claims. | `test_debate_orchestrator`. |
| 12 | **Multi-Agent Adversarial Debate Orchestration** | **COMPLETE** | `src/scheme_intel/stage2/debate.py`: `DebateOrchestrator` runs structured multi-round debate sequence. | `test_debate_orchestrator`. |
| 13 | **⚡ Deterministic Hard Risk Engine (Non-Overridable Veto)** | **COMPLETE** | `src/scheme_intel/stage2/risk.py`: Mathematical vetoes: R:R < 1.5:1, stop loss > 8%, daily volume < 20,000 shares. Calculates Entry Zone, Ideal Entry, Tomorrow Trigger, SL, T1 (1.8R), T2 (2.8R), T3 (4.2R runner), explicit R:R basis, and mathematical position sizing. | `test_risk_engine_passing_setup`, `test_risk_engine_stop_distance_veto`, `test_risk_engine_liquidity_veto`, `test_risk_reward_explicit_calculation`. |
| 14 | **Directionally Consistent Invalidation & Breakout Failure** | **COMPLETE** | `src/scheme_intel/stage2/risk.py`: Strictly separates technical invalidation (daily close below stop loss ₹SL) from breakout failure conditions (closing back below resistance). Never contradicts trade direction. | `test_invalidation_logic_directionally_consistent`. |
| 15 | **Mathematical Position Sizing & Rupee Risk Caps** | **COMPLETE** | `src/scheme_intel/stage2/risk.py`: Enforces max rupee risk (1% of account = ₹10,000) and max capital deployment (10% = ₹100,000). Calculates share quantity, capital deployed, and maximum loss at stop. | `test_position_sizing_mathematical_limits`. |
| 16 | **Setup Waiting Engine (Concrete Actionable Triggers)** | **COMPLETE** | `src/scheme_intel/stage2/waiting.py`: Never outputs useless "NO TRADE" for promising stocks. Diagnoses `why_not_ready`, exact price confirmation, exact volume confirmation, trigger price, invalidation floor, potential entry. | `test_waiting_engine_generation`. |
| 17 | **State Representation (`QUALIFIED_SETUP`, `WAIT`, `WATCH`, `NO_TRADE`)** | **COMPLETE** | `src/scheme_intel/stage2/models.py`, `pipeline.py`: Explicit four-state model. Trades are NEVER forced. | Verified in `test_full_pipeline_run` and CLI dry-run. |
| 18 | **SQLite Storage & MFE/MAE Tracking** | **COMPLETE** | `src/scheme_intel/stage2/storage.py`: Tables `stage2_setups` and `stage2_outcomes`. Saves setups with debates and risk parameters; tracks entry price, exit price, MFE %, MAE %, realized PnL %. | `test_storage_and_outcome_tracking`. |
| 19 | **Telegram Report (Authoritative 3-Section Format)** | **COMPLETE** | `src/scheme_intel/stage2/telegram.py`: Section 1 (Every stock with price, volume ratio, news, catalyst, technicals, status), Section 2 (Swing Setup Radar), Section 3 (Qualified Setups with complete blueprint, explicit R:R basis, position sizing, invalidation + Waiting Setups with exact triggers + No Trade). | `test_telegram_report_formatting`. |
| 20 | **Live Production vs Mock Data Architecture Separation** | **COMPLETE** | `src/scheme_intel/stage2/market.py`, `news.py`, `pipeline.py`: Explicit `mode="production"` connects directly to Stage 1 price ingestion and database, while `mode="mock"` is strictly isolated for offline testing. | `test_production_mode_uses_live_sources_not_mocks`. |
| 21 | **End-to-End Orchestrator Pipeline** | **COMPLETE** | `src/scheme_intel/stage2/pipeline.py`: Master pipeline with mock provider for offline testing and Gemini/OpenAI providers for live LLM inference. | `test_full_pipeline_run`. |

---

## 3. Audit Verdict

All Stage 2 functional requirements are **100% COMPLETE, EXECUTABLE, AND TESTED**.
No files are unverified skeletons or placeholders.
Stage 1 remains 100% functional and intact.
