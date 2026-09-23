# Scheme Intel — Troubleshooting Guide

## Common Issues & Resolutions

### 1. Ingestion Failures from Datacenter IPs
- **Symptom**: `403 Forbidden` or `Expecting value: line 2 column 1` when querying NSE/BSE corporate announcement endpoints.
- **Cause**: Cloudflare / CDN IP blocking of GitHub Actions and AWS/GCP datacenter IP ranges.
- **Resolution**:
  - The pipeline automatically falls back to `data/ingested.json` and records the error under `source_errors` without terminating.
  - To refresh prices offline, run `python -m scheme_intel.ingest` from a local desktop IP and push `data/ingested.json`.

### 2. Missing Telegram Notifications
- **Symptom**: Pipeline logs `TELEGRAM_BOT_TOKEN not configured - skipping Telegram send`.
- **Resolution**:
  - Export `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as environment variables:
    ```bash
    export TELEGRAM_BOT_TOKEN="your_bot_token"
    export TELEGRAM_CHAT_ID="-100123456789"
    ```
  - For GitHub Actions, configure repository secrets under **Settings > Secrets and variables > Actions**.

### 3. Duplicate Alerts Suppressed
- **Symptom**: Running the pipeline twice sends alerts on the first run, but skips the second.
- **Resolution**:
  - This is expected behavior. The Phase 8 stateful deduplication table (`alert_history`) in `data/scheme_intel.db` logs unique alert keys and prevents spamming.
  - To force resending, delete `data/scheme_intel.db` or clear the table: `sqlite3 data/scheme_intel.db "DELETE FROM alert_history;"`.

### 4. Zero Setups Generated
- **Symptom**: Pipeline completes with `0 setups generated`.
- **Cause**: Setups only generate when a material catalyst (score >= 60) matches a monitored watchlist company and passes technical momentum filters.
- **Resolution**:
  - Review `config/watchlist.yaml` to verify company aliases and ticker symbols.
  - Check `data/latest.json` to inspect discovered catalysts and their scores.
