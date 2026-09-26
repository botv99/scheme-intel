# Scheme-Intel Architecture Audit Report
**Date:** 2026-09-26  
**Stage:** 2.5 — Repository Architecture Cleanup + Nifty Benchmark Integration  
**Status:** Approved for Implementation

---

## 1. Executive Summary

This architecture audit evaluates the Scheme-Intel codebase to transition the repository from a stage-by-stage prototype into a professional, modular, multi-scheme intelligence platform. 

The refactoring achieves four critical objectives:
1. **Scheme-Independence**: Decouples government scheme specifics (GOBARdhan sources, keywords, watchlist) from downstream intelligence engines, introducing a unified `SchemeRegistry`.
2. **Nifty 50 Benchmark Engine**: Integrates an authoritative benchmark tracking and comparison layer into `PerformanceAnalytics` with strict zero-lookahead leakage guarantees.
3. **Domain-Driven Directory Organization**: Reorganizes codebase into clean functional modules (`schemes/`, `market/`, `intelligence/`, `ai/`, `strategy/`, `outcomes/`, `analytics/`, `storage/`, `delivery/`, `pipeline/`).
4. **Stage 3 Preparedness**: Structures `delivery/` to host both outward alert broadcasts and the future Telegram conversational retrieval bot without further architectural overhaul.
5. **Strict Backward Compatibility**: Preserves all existing import paths, public API surfaces, database records, and trading strategy logic (100% of the 376 existing tests remain passing).

---

## 2. Current vs. Target Architecture

### Current Structure:
```text
src/scheme_intel/
├── (Root level: Stage 1 legacy modules)
│   ├── analytics.py, catalyst.py, config.py, consolidated.py, db.py, earnings.py
│   ├── ingest.py, logger.py, main.py, models.py, notifier.py, pipeline.py
│   ├── reliability.py, signals.py, sources.py, sources_expanded.py, tracker.py
│   ├── trade_call.py, watchlist_alerts.py
├── ingestion/
│   ├── exchanges.py, media.py, models.py, price.py
└── stage2/
    ├── calendar.py, candidate.py, debate.py, impact.py, market.py, models.py
    ├── news.py, performance.py, pipeline.py, risk.py, scanner.py, storage.py
    ├── telegram.py, tracker.py, waiting.py
    ├── agents/ (bull.py, bear.py, arbitrator.py, base.py)
    └── providers/ (base.py, manager.py, gemini.py, groq.py, openrouter.py, openai.py, mock.py)
```

### Target Architecture:
```text
src/scheme_intel/
├── core/
│   ├── config.py             # Global settings and environment loader
│   ├── logger.py             # Centralized structured logger
│   └── exceptions.py         # Domain error hierarchy
├── schemes/
│   ├── registry.py           # Multi-scheme discovery & registration
│   ├── models.py             # SchemeConfig, SchemeDefinition contracts
│   └── gobardhan/            # GOBARdhan implementation (active)
│       ├── config.py         # Policy scheme metadata & parameters
│       ├── sources.py        # PIB, MNRE, Jal Shakti, GOBARdhan feeds
│       ├── watchlist.py      # Bio-energy & water treatment stocks
│       └── mapping.py        # Company to scheme keyword mappings
├── ingestion/
│   ├── base.py               # Ingestion contracts & session management
│   ├── price.py              # Screener / Yahoo Finance collector
│   ├── media.py              # Press release & news crawler
│   ├── exchanges.py          # BSE / NSE corporate announcements
│   └── models.py             # Ingestion data containers
├── market/
│   ├── calendar.py           # Indian market sessions, trading hours & holidays
│   ├── technicals.py         # Technical indicator computation (SMA, RSI, ATR, MACD)
│   ├── engine.py             # MarketDataEngine & snapshot assembly
│   └── benchmark.py          # NIFTY 50 collector, validator & persistence
├── intelligence/
│   ├── catalysts.py          # Policy catalyst extraction & scoring
│   ├── news.py               # News categorization & stock matching
│   └── impact.py             # Catalyst impact & priced-in evaluation
├── ai/
│   ├── providers/            # Multi-provider routing (Gemini, Groq, OpenRouter, OpenAI)
│   ├── agents/               # BullAgent, BearAgent, ArbitratorAgent
│   └── debate.py             # Dual-agent adversarial debate orchestrator
├── strategy/
│   ├── archetypes.py         # Breakout, Pullback, Momentum, Event-Driven models
│   ├── candidate.py          # Candidate setup detection & scoring
│   ├── risk.py               # Hard mathematical risk engine & veto logic
│   ├── waiting.py            # Actionable trigger condition generator
│   └── scanner.py            # Watchlist scanner & stock card builder
├── outcomes/
│   ├── models.py             # SetupOutcome & execution event contracts
│   └── tracker.py            # OutcomeTracker: entry, MFE/MAE, T1/SL, expiry
├── analytics/
│   ├── performance.py        # PerformanceAnalytics engine & metrics
│   ├── benchmark.py          # Nifty excess return & relative performance
│   └── reports.py            # JSON, Markdown, and Telegram reporting
├── storage/
│   ├── database.py           # SQLite repository manager & foreign keys
│   ├── models.py             # Persistent table models & schemas
│   └── migrations.py         # Schema migrations (benchmark_prices, ai_provider)
├── delivery/
│   ├── telegram_alerts.py    # Multi-section daily report dispatcher
│   └── telegram_cards.py     # Telegram formatting and visual cards
└── pipeline/
    ├── daily.py              # Stage2Pipeline daily orchestration
    └── unified.py            # Main CLI runner coordinating Stage 1 + Stage 2
```

---

## 3. What Moves, Renames, and Stays

### A. What Stays Unchanged (Behaviorally):
- **Trading strategy scoring logic, thresholds, and weights**: Zero changes.
- **Risk management rules** (R:R $\ge 1.5$, stop distance veto, position sizing): Zero changes.
- **Bull / Bear / Arbitrator debate prompts and consensus logic**: Zero changes.
- **AI provider failover hierarchy and cooldowns**: Zero changes.
- **Watchlist members**: Zero changes.

### B. What Moves / Reorganizes:
- **`src/scheme_intel/stage2/providers/`** $\rightarrow$ **`src/scheme_intel/ai/providers/`**
- **`src/scheme_intel/stage2/agents/`** $\rightarrow$ **`src/scheme_intel/ai/agents/`**
- **`src/scheme_intel/stage2/debate.py`** $\rightarrow$ **`src/scheme_intel/ai/debate.py`**
- **`src/scheme_intel/stage2/risk.py`** $\rightarrow$ **`src/scheme_intel/strategy/risk.py`**
- **`src/scheme_intel/stage2/candidate.py`** $\rightarrow$ **`src/scheme_intel/strategy/candidate.py`**
- **`src/scheme_intel/stage2/tracker.py`** $\rightarrow$ **`src/scheme_intel/outcomes/tracker.py`**
- **`src/scheme_intel/stage2/performance.py`** $\rightarrow$ **`src/scheme_intel/analytics/performance.py`**
- **`src/scheme_intel/stage2/calendar.py`** $\rightarrow$ **`src/scheme_intel/market/calendar.py`**
- **`src/scheme_intel/stage2/telegram.py`** $\rightarrow$ **`src/scheme_intel/delivery/telegram_alerts.py`**

### C. Backward-Compatibility Shims:
- To guarantee that any external invocation or existing test (e.g. `tests/test_stage2.py`, `tests/test_tracker.py`, `tests/test_performance.py`) continues to work without failing, the original module files in `stage2/` and `src/scheme_intel/` will re-export all moved classes and functions via clean forwarding aliases.

---

## 4. Multi-Scheme Architecture Plan

### Scheme Registry & SchemeConfig:
- Each scheme defines:
  - `scheme_id`: Unique identifier (`gobardhan`, and reserved `samudra_manthan`).
  - `name`: Formal name (e.g., `"GOBARdhan / Bio-CBG Scheme"`).
  - `description`: Scope and policy objectives.
  - `ministries`: Relevant government bodies.
  - `sources`: Scheme-specific RSS feeds and portals.
  - `watchlist`: Stock symbols and companies targeted.
  - `keywords`: Domain keyword taxonomy for policy scoring.
  - `company_mappings`: Entity resolution mapping announcements to stocks.
- Downstream intelligence engines (Market data, Bull/Bear AI debate, Risk engine, OutcomeTracker, PerformanceAnalytics) accept `scheme_id` and remain strictly scheme-agnostic.

---

## 5. Nifty Benchmark Integration Plan

1. **Benchmark Data Collection**:
   - Collector: `market/benchmark.py` fetches `^NSEI` via `yfinance` with fallback to local price cache.
   - Storage: SQLite table `benchmark_prices` (`benchmark_id`, `date`, `open`, `high`, `low`, `close`, `volume`, `source`, `created_at`, `PRIMARY KEY(benchmark_id, date)`).
   - Migration: Auto-created in `storage/database.py` with `CREATE TABLE IF NOT EXISTS benchmark_prices`.
2. **Performance Analytics Comparison**:
   - For each completed trade with valid benchmark data on `entry_date` and `exit_date`:
     - $\text{Benchmark Return} = \frac{\text{Close}_{\text{exit}} - \text{Close}_{\text{entry}}}{\text{Close}_{\text{entry}}} \times 100$
     - $\text{Excess Return} = \text{Strategy Realized Return} - \text{Benchmark Return}$
   - Aggregate metrics: average benchmark return, average excess return, median excess return, cumulative excess return.
3. **Data-Sufficiency & Leakage Guards**:
   - If 0 completed trades: `Benchmark comparison: UNAVAILABLE — 0 completed trades`.
   - If benchmark data missing: `Benchmark: UNAVAILABLE — benchmark data missing`.
   - Zero lookahead leakage: benchmark calculations only access dates on or after trade execution.

---

## 6. Execution Plan & Risk Control

1. **Step 1**: Implement `schemes/` subsystem with `SchemeRegistry`, `SchemeConfig`, and `gobardhan` package.
2. **Step 2**: Implement `market/benchmark.py` and database schema migration for `benchmark_prices`.
3. **Step 3**: Reorganize domain modules (`market/`, `intelligence/`, `ai/`, `strategy/`, `outcomes/`, `analytics/`, `storage/`, `delivery/`, `pipeline/`).
4. **Step 4**: Provide backward-compatibility forwarding layers in `stage2/` and root modules.
5. **Step 5**: Integrate benchmark comparisons into `PerformanceAnalytics` and reports.
6. **Step 6**: Add unit and regression tests for benchmark and scheme registry.
7. **Step 7**: Verify all 376 existing tests + new tests pass.
8. **Step 8**: Run production workflow and verify end-to-end.
