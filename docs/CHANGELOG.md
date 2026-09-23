# Changelog

All notable changes to Scheme Intel will be documented in this file.

## [Stage 1 Final] - 2026-09-23

### Completed Stage 1 (Phases 1–8 Production Readiness)
- **Phase 1 (Code Quality & Testing)**:
  - Repaired 5 failing earnings tests caused by hardcoded 7-day test date windows.
  - Achieved 100% test pass rate across all 295 test items.
  - Added manual `workflow_dispatch` trigger to GitHub Actions `test.yml`.
- **Phase 2 (Data & Analytics)**:
  - Added persistent `historical_prices` table in SQLite schema with unique constraint and indexing.
  - Implemented Maximum Drawdown (MDD) calculation over sequential closed trades.
  - Added technical setup effectiveness analysis (breakout, RSI zones, MACD histogram).
  - Added daily, weekly, and monthly periodic return summaries.
- **Phase 3 (Source Reliability)**:
  - Established formal 5-Tier Source Hierarchy (Tier 1 Government down to Tier 5 Unverified).
  - Added automated source tier resolution from source names and domains.
  - Implemented stale-information detection (> 72 hours).
  - Implemented conflicting-source detection for opposing sentiment polarities.
  - Created evidence-based multi-source corroboration narratives.
- **Phase 4 (Technical Analysis)**:
  - Expanded indicators: 100 DMA, 200 DMA from series, ROC-10, ROC-21.
  - Added 50-day high and breakout distance %.
  - Added ATR %, volatility regime classification (LOW, NORMAL, HIGH, EXTREME).
  - Added support, resistance, and swing high/low price structure calculations.
  - Added relative strength vs benchmark (NIFTY 50).
- **Phase 5 (Catalyst Intelligence)**:
  - Expanded taxonomy to 19 Stage 1 catalyst classifications.
  - Implemented rich metadata extraction: catalyst type, duration, scheme, sector, business segment, and sentiment.
- **Phase 6 (Company Intelligence)**:
  - Added structured corporate intelligence extractor for Capex, orders, margins, capacity, guidance, and risks.
  - Created bridge feeding corporate disclosures and analyst updates into the central Catalyst Engine.
- **Phase 7 (Documentation & Usability)**:
  - Created complete documentation suite: `ARCHITECTURE.md`, `CONFIGURATION.md`, `DATA_MODEL.md`, `SOURCES.md`, `TROUBLESHOOTING.md`, `CHANGELOG.md`.
  - Updated `README.md` and `docs/TESTING.md`.
- **Phase 8 (Automation & Delivery)**:
  - Implemented alert levels (`INFO`, `QUALIFIED`, `CRITICAL`).
  - Added stateful SQLite-backed duplicate alert suppression (`alert_history`).
  - Added exponential backoff retry logic for Telegram dispatches.
  - Added daily briefing formatting.
