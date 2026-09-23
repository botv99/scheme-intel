# Scheme Intel - Stage 1 (Phases 1–8) Comprehensive Audit

**Date**: 2026-09-23
**Auditor**: Antigravity Agent 1 (Stage 1 Auditor)
**Baseline Test Suite**: 276 items collected — 271 passed, 5 failed (`tests/test_earnings.py`).

---

## Executive Summary

| Phase | Description | Status | Responsible Files | Key Test(s) | Fix Required |
|---|---|---|---|---|---|
| **Phase 1** | Code Quality & Testing | **PARTIAL** | `tests/test_earnings.py`, `pytest.ini`, `requirements.txt`, `.github/workflows/test.yml` | `pytest` test suite | Fix 5 failing earnings tests caused by hardcoded 7-day date window; verify requirements & CI workflows |
| **Phase 2** | Data & Analytics | **PARTIAL** | `src/scheme_intel/db.py`, `analytics.py`, `tracker.py` | `tests/test_db.py`, `tests/test_analytics.py` | Add `historical_prices` table; implement max drawdown, technical setup performance, and daily/weekly/monthly stats |
| **Phase 3** | Source Reliability | **PARTIAL** | `src/scheme_intel/reliability.py`, `models.py` | `tests/test_reliability.py` | Implement Tier 1–5 Source Hierarchy, source timestamping, conflicting source detection, and stale information alerts |
| **Phase 4** | Technical Analysis | **PARTIAL** | `src/scheme_intel/signals.py`, `models.py` | `tests/test_signals.py` | Implement 100/200 DMA, ROC, 50-day high, breakout distance %, ATR %, volatility regime, support/resistance, relative strength vs NIFTY |
| **Phase 5** | Catalyst Intelligence | **PARTIAL** | `src/scheme_intel/catalyst.py`, `models.py`, `db.py` | `tests/test_catalyst.py` | Expand to 19 catalyst classifications; persist rich fields (source tier, event date, duration, segment, scheme, sector) |
| **Phase 6** | Company Intelligence | **PARTIAL** | `src/scheme_intel/earnings.py`, `ingestion/exchanges.py` | `tests/test_earnings.py` | Extract structured intelligence (What changed, Capex, Margins, Guidance) and feed into the Catalyst Engine |
| **Phase 7** | Documentation & Usability | **PARTIAL** | `docs/`, `README.md` | Doc reviews & examples | Create ARCHITECTURE.md, CONFIGURATION.md, DATA_MODEL.md, SOURCES.md, TROUBLESHOOTING.md, CHANGELOG.md; document E2E pipeline & outputs |
| **Phase 8** | Automation & Delivery | **PARTIAL** | `src/scheme_intel/notifier.py`, `.github/workflows/` | `tests/test_notifier.py`, `tests/test_consolidated.py` | Add alert levels (INFO, QUALIFIED, CRITICAL), stateful duplicate alert suppression in DB, retries with backoff, daily digest Telegram action |

---

## Detailed Audit by Phase

### Phase 1 — Code Quality & Testing
- **Project Structure**: Clean layout with `src/scheme_intel`, `tests/`, `config/`, `data/`, `.github/workflows/`. Status: **COMPLETE**.
- **Unit & Integration Tests**: 276 tests collected. 271 passed. Status: **BROKEN (5 test failures in `test_earnings.py`)**.
  - Failures: `test_includes_earnings`, `test_includes_ratings`, `test_includes_concalls`, `test_formats_earnings`, `test_formats_ratings`.
  - Root Cause: `generate_digest()` filters by `cutoff = now - 7 days`. Test fixtures had hardcoded date `"2026-09-10"`, which is > 7 days old relative to runtime date (`2026-09-23`).
  - Fix: Update `generate_digest()` or test fixtures to use dynamic dates relative to `datetime.now(timezone.utc)`.
- **Structured Logging & Error Handling**: Custom hierarchy in `exceptions.py` (`SchemeIntelError`, `ConfigurationError`, etc.) and `logger.py`. Status: **COMPLETE**.
- **Configuration Validation**: `src/scheme_intel/config.py` validates `watchlist.yaml`. Status: **COMPLETE**.
- **GitHub Actions Test Workflow**: `.github/workflows/test.yml` exists. Status: **COMPLETE**.
- **Secrets Management**: Verified environment variable access (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`); no hardcoded tokens found. Status: **COMPLETE**.

---

### Phase 2 — Data & Analytics
- **Historical Catalyst Storage**: `catalysts` table in `db.py` exists, but lacks rich fields (tier, sentiment, segment, scheme, confidence, duration). Status: **PARTIAL**.
- **Historical Stock-Price Data**: Price history was only stored in JSON snapshots (`data/ingested.json`). Missing persistent `historical_prices` table in SQLite schema. Status: **MISSING**.
- **Historical Setups & Trade Tracking**: `setups` and `trades` tables exist with entry/exit/SL/target/pnl tracking. Status: **COMPLETE**.
- **Performance Analytics**:
  - Win/loss stats, win rate, average win/loss %, best/worst trade: Implemented in `analytics.py`. Status: **COMPLETE**.
  - Maximum Drawdown (MDD): Calculation missing from `analytics.py`. Status: **MISSING**.
  - Technical Setup Performance Breakdown: Breakdown by technical indicator criteria missing. Status: **MISSING**.
  - Daily/Weekly/Monthly Periodic Stats: Periodic return & trade count tracking missing. Status: **MISSING**.

---

### Phase 3 — Source Reliability
- **Source Hierarchy (Tiers 1–5)**:
  - Required:
    - Tier 1: Government / regulator / exchange (PIB, GOBARdhan, MNRE, Jal Shakti, NSE, BSE)
    - Tier 2: Company official disclosure / investor relations
    - Tier 3: Established financial publications (ET, Mint, Business Standard, Reuters)
    - Tier 4: Analyst / research sources (Scripbox, brokerages)
    - Tier 5: Social media / unverified sources
  - Current: Not codified into the data structures or scoring algorithms. Status: **MISSING**.
- **Source Metrics**: Timestamp, URL, publication date, source type, success/error rates. Status: **PARTIAL**.
- **Corroboration & Deduplication**: Fuzzy text similarity and multi-source clustering exist in `reliability.py`. Status: **COMPLETE**.
- **Conflicting Source Detection**: Detecting contradictory headlines or sentiments on the same entity/story. Status: **MISSING**.
- **Stale Information Detection**: Tagging articles older than configurable threshold (e.g. 72h) as stale. Status: **MISSING**.

---

### Phase 4 — Technical Analysis
- **Trend Engine**:
  - 20 DMA & 50 DMA: Implemented. Status: **COMPLETE**.
  - 100 DMA & 200 DMA: Calculated directly from series data. Status: **PARTIAL** (200 DMA was external-only).
- **Momentum Engine**:
  - RSI(14) & MACD(12, 26, 9): Implemented. Status: **COMPLETE**.
  - Rate of Change (ROC-10, ROC-21): Status: **MISSING**.
- **Breakout Engine**:
  - 20-day high & Volume Breakout (1.5x avg): Implemented. Status: **COMPLETE**.
  - 50-day high & Breakout Distance (% above resistance): Status: **MISSING**.
- **Volatility Engine**:
  - ATR(14): Implemented. Status: **COMPLETE**.
  - ATR % (ATR / Close * 100) & Volatility Regime (Low/Normal/High/Extreme): Status: **MISSING**.
- **Price Structure**:
  - Support & Resistance pivot levels, recent swing high/low points: Status: **MISSING**.
- **Relative Strength**:
  - Stock vs NIFTY / Sector Benchmark: Status: **MISSING**.
- **Multi-timeframe**:
  - Daily + Weekly alignment checks: Status: **PARTIAL** (basic 10-week SMA, needs full multi-timeframe check).

---

### Phase 5 — Catalyst Intelligence
- **Catalyst Classifications**:
  - Required 19 types: Government policy, Scheme announcement, Cabinet approval, Tender, Order win, Capacity expansion, Plant commissioning, Subsidy, Pricing change, Regulatory change, JV / partnership, Capex, Acquisition, Results, Management commentary, Investor presentation, Earnings call, Analyst report, Industry development.
  - Current: Only ~13 basic keywords in `catalyst.py`. Status: **PARTIAL**.
- **Catalyst Metadata Storage**:
  - Fields required: `company`, `catalyst_type`, `headline`, `summary`, `source`, `source_tier`, `published_at`, `event_date`, `confidence`, `positive/negative/neutral`, `expected_duration`, `affected_business_segment`, `related_scheme`, `related_sector`.
  - Current: Limited to `(article, score, category, rationale, companies)`. Status: **PARTIAL**.

---

### Phase 6 — Company Intelligence
- **Corporate Ingestion**:
  - NSE / BSE corporate announcements & bulk deals: Implemented in `ingestion/exchanges.py`. Status: **COMPLETE**.
  - Earnings, analyst ratings, and concall discovery: Implemented in `earnings.py`. Status: **COMPLETE**.
- **Structured Dimension Extraction**:
  - Required: Extraction of What changed?, Why does it matter?, Segment affected, Management guidance, Capex, Orders, Margins, Capacity, Risks, Forward-looking statements, Scheme exposure.
  - Current: Only raw headline/snippet string matching. Status: **PARTIAL**.
- **Catalyst Pipeline Integration**:
  - Company intelligence feeds directly into Catalyst Engine: Currently isolated in `earnings.py` instead of feeding `catalyst.py` & `pipeline.py`. Status: **PARTIAL**.

---

### Phase 7 — Documentation & Usability
- **Required Documentation Suite**:
  - `README.md`: Exists, needs updating with full pipeline architecture. Status: **PARTIAL**.
  - `docs/ARCHITECTURE.md`: Status: **MISSING**.
  - `docs/CONFIGURATION.md`: Status: **MISSING**.
  - `docs/DATA_MODEL.md`: Status: **MISSING**.
  - `docs/SOURCES.md`: Status: **MISSING**.
  - `docs/TESTING.md`: Exists. Status: **COMPLETE**.
  - `docs/TROUBLESHOOTING.md`: Status: **MISSING**.
  - `docs/CHANGELOG.md`: Status: **MISSING**.
- **Pipeline Flow & Examples**: Document complete sequence `Sources → Ingestion → Normalization → Catalyst detection → Stock mapping → Technical analysis → Setup generation → Risk checks → Telegram` with sample outputs. Status: **MISSING**.

---

### Phase 8 — Automation & Delivery
- **GitHub Actions Workflows**:
  - `daily-monitor.yml`, `ingestion.yml`, `consolidated-alert.yml`, `test.yml` exist. Status: **COMPLETE**.
- **Telegram Delivery & Notifications**:
  - Multi-chat support: Implemented in `notifier.py`. Status: **COMPLETE**.
  - Alert levels (`INFO`, `QUALIFIED`, `CRITICAL`): Status: **MISSING**.
  - Stateful duplicate alert prevention in SQLite: Status: **MISSING**.
  - Retry logic with backoff: Status: **MISSING**.
  - Daily digest message builder: Status: **PARTIAL**.
