# Scheme Intel

A comprehensive evidence-led monitor and analytics platform for India's GOBARdhan / compressed-biogas ecosystem. It scans official sources, flags material policy and contract catalysts, maps them to a stock watchlist, tracks historical performance, and sends concise Telegram alerts.

## Features

### Core Pipeline
- Scans official sources: PIB, GOBARdhan, MNRE, Jal Shakti, NSE/BSE
- Detects material catalysts (fund releases, cabinet approvals, tenders, contracts)
- Generates swing setups with technical analysis (SMA 20/50/200, RSI, MACD, volume breakout)
- Sends Telegram alerts with catalyst details and trade setups

### Technical Analysis (Phase 4)
- **SMA 20/50/200** — trend alignment
- **RSI(14)** — momentum filter
- **Volume breakout** — 1.5× trailing average confirmation
- **MACD(12,26,9)** — histogram filter
- **Weekly multi-timeframe** — 10-week SMA trend
- **200-day DMA** — long-term trend from Screener chart API

### Data & Analytics (Phase 2)
- **SQLite database** — historical tracking of runs, catalysts, setups, trades
- **Trade tracker CLI** — record, close, and analyze trades
- **Performance analytics** — win rate, ROI, per-symbol breakdown
- **Catalyst effectiveness** — win rate by catalyst score bucket

### Source Reliability (Phase 3)
- **Source credibility scoring** — persistent success/error rates across runs
- **Cross-source corroboration** — same story from multiple sources boosts confidence
- **Sentiment analysis** — keyword-based positive/negative financial lexicon
- **Combined confidence score** — source reliability × corroboration × sentiment

### Earnings & Analyst Tracking (Phase 8)
- **Quarterly results** — revenue, profit, EPS, YoY growth from NSE/Screener
- **Analyst ratings** — broker research, target prices, BUY/SELL/HOLD
- **Concall transcripts** — investor call discovery from Google News
- **Digest generation** — grouped by company, Telegram-formatted

### Source Expansion (Phase 5)
- **Sector-specific RSS** — renewable energy, oil & gas, water infra, government policy
- **BSE corporate actions** — dividends, bonuses, splits
- **Economic indicators** — RBI rates, commodity prices
- **Source health monitoring** — real-time status of all data sources

## Quick Start

```bash
# Clone and setup
git clone https://github.com/botv99/scheme-intel.git
cd scheme-intel
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Set environment
$env:PYTHONPATH = "src"

# Run the full pipeline
python -m scheme_intel.main

# Run with Telegram alerts
$env:TELEGRAM_BOT_TOKEN = "your-token"
$env:TELEGRAM_CHAT_ID = "your-chat-id"
python -m scheme_intel.main --send
```

## CLI Commands

### Main Pipeline
```bash
PYTHONPATH=src python -m scheme_intel.main              # scan only
PYTHONPATH=src python -m scheme_intel.main --send       # scan + Telegram alert
```

### Data Ingestion
```bash
PYTHONPATH=src python -m scheme_intel.ingest             # full run
PYTHONPATH=src python -m scheme_intel.ingest --days-back 14
```

### Trade Tracker
```bash
PYTHONPATH=src python -m scheme_intel.tracker record --company "TruAlt" --symbol TRUALT.NS --entry 220 --stop 200 --target 260
PYTHONPATH=src python -m scheme_intel.tracker close --trade-id 1 --exit 245.50 --outcome WIN
PYTHONPATH=src python -m scheme_intel.tracker status
PYTHONPATH=src python -m scheme_intel.tracker dashboard
PYTHONPATH=src python -m scheme_intel.tracker open
```

### Source Health Check
```bash
PYTHONPATH=src python -c "from scheme_intel.sources_expanded import check_source_health; [print(f'{s.name}: {s.status}') for s in check_source_health()]"
```

### Earnings & Analyst Digest
```bash
PYTHONPATH=src python -c "
from scheme_intel.earnings import EarningsTracker
from scheme_intel.config import load_config
config = load_config()
tracker = EarningsTracker()
tracker.refresh(config['stocks'])
digest = tracker.generate_digest(config['stocks'])
print(tracker.format_digest_telegram(digest))
"
```

## Configuration

### Watchlist (`config/watchlist.yaml`)
```yaml
stocks:
  - name: TruAlt Bioenergy
    symbol: TRUALT.NS          # Yahoo Finance symbol
    screener_id: TRUALT        # Screener.in company ID
    aliases: [TruAlt, TruAlt Bioenergy]
    thesis: CBG developer and producer...
```

### Settings
```yaml
settings:
  rally_threshold_pct: 10
  rally_window_days: 15
  max_setup_age_days: 5
  risk_per_trade_pct: 1
  minimum_catalyst_score: 60
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ -v --cov=src/scheme_intel --cov-report=term-missing

# Run specific test file
python -m pytest tests/test_signals.py -v
```

**207 tests** across 12 test files covering:
- Catalyst classification
- Technical analysis (RSI, MACD, DMA200, weekly trend)
- Source reliability and sentiment
- Database operations
- Trade analytics
- Earnings tracking
- Watchlist alerts

## Architecture

```
scheme_intel/
├── main.py              # Pipeline entry point
├── pipeline.py          # Core pipeline orchestration
├── catalyst.py          # Catalyst classification & scoring
├── signals.py           # Technical analysis (RSI, MACD, SMA, ATR)
├── sources.py           # RSS, web scraping, deduplication
├── sources_expanded.py  # Sector feeds, BSE actions, economic indicators
├── reliability.py       # Source credibility, corroboration, sentiment
├── notifier.py          # Telegram multi-chat notifications
├── earnings.py          # Earnings, analyst ratings, concall tracker
├── db.py                # SQLite database operations
├── analytics.py         # Performance metrics & dashboard
├── tracker.py           # Trade tracker CLI
├── config.py            # YAML configuration loader
├── models.py            # Data classes (Article, Catalyst, SwingSetup)
├── exceptions.py        # Custom exception hierarchy
├── logger.py            # Structured logging
├── ingestion/           # Daily market data ingestion layer
│   ├── price.py         # Screener.in + Yahoo Finance prices
│   ├── exchanges.py     # NSE/BSE bulk deals & announcements
│   └── media.py         # Financial news collection
└── watchlist_alerts.py  # GOBARdhan stock watchlist Telegram alerts
```

## Data Flow

```
┌─────────────────┐     ┌──────────────┐     ┌────────────────┐
│  Official Sources│────▶│  Ingestion   │────▶│  data/ingested │
│  (PIB, NSE, BSE)│     │  Layer       │     │  .json         │
└─────────────────┘     └──────────────┘     └───────┬────────┘
                                                      │
┌─────────────────┐     ┌──────────────┐     ┌───────▼────────┐
│  Sector RSS Feeds│────▶│  Reliability │────▶│  Pipeline      │
│  (expanded)     │     │  Tracker     │     │  (catalysts +  │
└─────────────────┘     └──────────────┘     │   setups)      │
                                              └───────┬────────┘
┌─────────────────┐     ┌──────────────┐     ┌───────▼────────┐
│  Google News RSS │────▶│  Earnings    │────▶│  Report        │
│  (concalls,     │     │  Tracker     │     │  (latest.json  │
│   analyst)      │     └──────────────┘     │   + SQLite)    │
└─────────────────┘                          └───────┬────────┘
                                                      │
                                              ┌───────▼────────┐
                                              │  Telegram      │
                                              │  Alerts        │
                                              └────────────────┘
```

## GitHub Actions

- **test.yml** — runs on push/PR to main, Python 3.11/3.12, 207 tests
- **daily-monitor.yml** — weekday 6:00 PM IST, full pipeline + snapshot commit
- **watchlist-alert.yml** — weekday 4:00 PM IST, stock watchlist alerts
- **ingestion.yml** — weekday 6:30 PM IST, daily market data ingestion

## Important Limits

This is a research and alerting tool, not investment advice. It cannot predict moves, guarantee performance, or execute trades. Verify every source, liquidity, corporate disclosure and position size before acting.

## License

Private repository. For access, contact the repository owner.
