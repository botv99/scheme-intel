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

| Variable | Description | Required | Example |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token | For notifications | `123456789:ABCdefGHIjklMNOpqr` |
| `TELEGRAM_CHAT_ID` | Comma-separated Telegram Chat / Channel IDs | For notifications | `-100123456789,-100987654321` |
| `GEMINI_API_KEY` | Google Gemini API Key | Optional | `AIzaSy...` |
| `GEMINI_MODEL` | Gemini Model identifier | Optional (default: `gemini-3.8-flash`) | `gemini-3.8-flash` |
| `GROQ_API_KEY` | Groq API Key | Optional | `gsk_...` |
| `GROQ_MODEL` | Groq Model identifier | Optional (default: `llama-3.3-70b-versatile`) | `llama-3.3-70b-versatile` |
| `OPENROUTER_API_KEY` | OpenRouter Gateway API Key | Optional | `sk-or-v1-...` |
| `OPENROUTER_MODEL` | OpenRouter Model identifier | Optional (default: `meta-llama/llama-3.3-70b-instruct:free`) | `meta-llama/llama-3.3-70b-instruct:free` |
| `OPENAI_API_KEY` | OpenAI API Key | Optional | `sk-proj-...` |
| `OPENAI_MODEL` | OpenAI Model identifier | Optional (default: `gpt-4o-mini`) | `gpt-4o-mini` |
| `LLM_PROVIDER_ORDER` | Priority router order | Optional (default: `groq,openrouter,gemini,openai`) | `groq,openrouter,gemini,openai` |
| `PYTHONPATH` | Python import path | Optional (defaults to `src`) | `src` |

---

## Multi-Provider LLM Architecture (Stage 2)

Scheme-Intel uses a provider-agnostic, failover-based LLM architecture:
- Detects configured API keys dynamically (missing keys are skipped).
- Routes adversarial debate calls per-request across providers in priority order.
- Automatically handles 429 quota/rate limits with cooldown and failover to the next provider.
- Preserves deterministic synthesis as the ultimate safety net if all providers fail.

