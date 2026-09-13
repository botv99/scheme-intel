# Scheme Intel

An evidence-led monitor for India's GOBARdhan / compressed-biogas ecosystem. It scans configured official sources, flags material policy and contract catalysts, maps them to a stock watchlist, and can send a concise Telegram alert.

## What it does

- Tracks GOBARdhan, CBG/Bio-CNG, SATAT and related official-sector language, CPPP tenders, and configured NSE/BSE corporate-disclosure pages.
- Treats fund releases, cabinet approvals, pricing/blending changes, tenders, awards and commissioning as ranked catalysts.
- Keeps an editable stock watchlist in `config/watchlist.yaml`.
- Creates a **research setup** only when a material catalyst exists and the stock confirms trend/momentum. Entry is a 20-day-high breakout; the stop is two ATRs (with a 6% floor) and the first target is 2R.
- Sends Telegram only if both secrets are configured.

## Important limits

This is a research and alerting tool, not investment advice. It cannot predict a 10–15% move, guarantee performance, or execute trades. Verify every source, liquidity, corporate disclosure and position size before acting.

## Run locally

```bash
python -m venv .venv
.venv\\Scripts\\activate  # Windows
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m scheme_intel.main
```

## Ingestion layer

Collects daily market data for the watchlist and saves it to `data/ingested.json`:

```bash
python -m scheme_intel.ingest            # full run
python -m scheme_intel.ingest --days-back 14
```

- **Screener.in** – per-stock price snapshot: close, volume, % change, 52-week high/low, market cap and locally-computed RSI-14, plus a 6-month OHLC history from Yahoo Finance.
- **NSE / BSE** – bulk (and block) deals plus tender/contract announcements.
- **Mint / Financial Express / Moneycontrol** – news mentioning watchlist companies.

The main pipeline (`python -m scheme_intel.main`) consumes the snapshot as its shared data source: ingested news and exchange announcements feed catalyst detection, fresh ingested OHLC history feeds swing setups, and ingestion source errors are merged into the report. When the snapshot is older than 26 hours (or missing), setups fall back to live prices while the rest of the pipeline still runs standalone.

Source endpoints are best-effort: NSE/BSE JSON APIs can block datacenter IPs, so failures are recorded in the snapshot instead of stopping the run. Unlisted stocks (`symbol: null`) are news-monitored only. The GitHub Action runs weekdays at 6:30 PM IST and commits the snapshot.

## Telegram setup

Create a bot with BotFather, start a chat with it, then add these **GitHub Actions secrets** in `Settings → Secrets and variables → Actions`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Never put either value in the repository or `watchlist.yaml`. With secrets set, run the workflow manually from the **Actions** tab to test it.

## Schedule

The GitHub Action runs Monday–Friday at **6:00 PM India Standard Time** (12:30 UTC), after the regular NSE/BSE cash-market close. GitHub schedules are best-effort and can start a few minutes late. It scans the configured sources, retrieves price data for symbols with a listed ticker, saves a research snapshot, and sends only material alerts when Telegram secrets exist.

## Add a company

Add a record under `stocks` in `config/watchlist.yaml`. Use the correct Yahoo Finance symbol (for NSE, normally `SYMBOL.NS`); leave `symbol: null` when the company is unlisted, because it can still be news-monitored but cannot receive a price setup.

## Sources and review workflow

The first source set is intentionally official: MoPNG/PIB, GOBARdhan, MNRE and Jal Shakti. Add source-specific RSS feeds or tender endpoints only after confirming they are stable and allowed. Every alert carries its source URL so it can be reviewed before any investment decision.

