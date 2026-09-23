# Scheme Intel — Configuration Guide

## Configuration File: `config/watchlist.yaml`

The watchlist configuration controls target schemes, monitored companies, source feeds, and technical thresholds.

### Complete Example Configuration

```yaml
scheme:
  name: "GOBARdhan / SATAT / Bio-Energy Ecosystem"
  description: "Comprehensive monitor for CBG, Biomass, and Renewable Fuel ecosystem."

stocks:
  - name: "Praj Industries"
    symbol: "PRAJIND.NS"
    aliases: ["Praj", "Praj Ind"]
    screener_id: "PRAJIND"
    sectors: ["Bio-Energy & CBG", "Ethanol & Distilleries"]

  - name: "TruAlt Bioenergy"
    symbol: "TRUALT.NS"
    aliases: ["TruAlt", "TruAlt Bio"]
    screener_id: "TRUALT"
    sectors: ["Bio-Energy & CBG"]

  - name: "GAIL (India)"
    symbol: "GAIL.NS"
    aliases: ["GAIL", "Gas Authority of India"]
    screener_id: "GAIL"
    sectors: ["City Gas Distribution", "Gas Utility & CGD"]

settings:
  minimum_catalyst_score: 60
  stale_threshold_hours: 72
  volume_breakout_multiplier: 1.5
  rsi_lower_bound: 50
  rsi_upper_bound: 70
  atr_multiplier_stop: 2.0
  risk_reward_ratio: 2.0

sources:
  official_rss:
    - name: "PIB Petroleum & Natural Gas"
      url: "https://pib.gov.in/RssMain.aspx?ModId=3&Lang=1"
      tier: 1
    - name: "MNRE Renewable Energy"
      url: "https://mnre.gov.in/feed"
      tier: 1
  media_rss:
    - name: "Economic Times Energy"
      url: "https://economictimes.indiatimes.com/industry/energy/rssfeeds/13358319.cms"
      tier: 3

telegram:
  alert_level: "QUALIFIED"  # Options: INFO, QUALIFIED, CRITICAL
  daily_digest_time_ist: "16:30"
```

---

## Environment Variables

| Variable | Description | Required | Example |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token | For notifications | `123456789:ABCdefGHIjklMNOpqr` |
| `TELEGRAM_CHAT_ID` | Comma-separated Telegram Chat / Channel IDs | For notifications | `-100123456789,-100987654321` |
| `PYTHONPATH` | Python import path | Optional (defaults to `src`) | `src` |
