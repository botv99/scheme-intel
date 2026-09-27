# Scheme-Intel: Telegram Production Architecture

This document defines the production operational architecture for Scheme-Intel's Telegram Conversational Intelligence Terminal using **Cloudflare Workers** as the always-on serverless gateway and **GitHub Actions** as the compute/reasoning layer.

---

## 1. High-Level Architecture

```
                    ┌────────────────────────┐
                    │     TELEGRAM USER      │
                    └───────────┬────────────┘
                                │ HTTPS Webhook
                                ▼
                    ┌────────────────────────┐
                    │   Cloudflare Worker    │
                    │   Telegram Gateway     │
                    └───────────┬────────────┘
                                │
                  ┌─────────────┴──────────────┐
                  │                            │
             KNOWN QUERY                  COMPLEX QUERY
                  │                            │
                  ▼                            ▼
        Intelligence Snapshot        GitHub repository_dispatch
        (data/intelligence/latest.json)        │
                  │                            ▼
                  │                  04-telegram-query.yml
                  │                            │
                  │                            ▼
                  │                      AI / Analysis
                  │                            │
                  ▼                            ▼
        Immediate Telegram reply    Personalized Telegram reply
                  │                            │
                  └─────────────┬──────────────┘
                                ▼
                    Strictly to Original chat_id
```

---

## 2. Component Roles & Responsibility Separation

| Component | Technology | Primary Role | Availability / Hosting |
| :--- | :--- | :--- | :--- |
| **Conversational Gateway** | Cloudflare Worker | Webhook receiver, Telegram secret validation, fast path resolver, snapshot renderer, event dispatcher. | 24/7 Serverless (Free tier, global edge, <10ms cold start). |
| **Compute & Intelligence Engine** | GitHub Actions | Heavy strategy computation: ingestion, technical analysis, AI Bull/Bear debate, trade setup generation, outcome tracking, performance analytics. | Ephemeral execution (runs on daily schedule or `repository_dispatch`). |
| **Memory Cache** | GitHub Raw Content | Precomputed `data/intelligence/latest.json` containing validated company theses, setups, prices, and catalysts. | Static JSON edge delivery with 5-minute caching. |
| **Local PC / Laptop** | Your Computer | Code development, testing, and git operations. | **NOT required for bot operation. Can be powered off.** |

---

## 3. Operational Paths

### Path 1: FAST (<100ms)
- **Triggers**:
  - Direct stock commands: `/gail`, `/praj`, `/trualt`, `/wabag`, `/organic`, `/kirloskar`, `/ioc`
  - Shorthand tickers: `GAIL`, `Praj`, `TRUALT`
  - Explanatory commands: `/why trualt`, `/what praj`, `/when gail`
  - System views: `/setups`, `/waiting`, `/watchlist`, `/schemes`, `/performance`, `/benchmark`
  - Navigation: `/start`, `/help`
- **Execution**: The Cloudflare Worker fetches and validates `data/intelligence/latest.json` from the repository, formats the curated Markdown card, and sends the response to Telegram immediately.
- **Cost / Overhead**: Zero GitHub Actions compute used. Zero AI tokens consumed.

### Path 2: WORKFLOW (Event-Driven GitHub Actions)
- **Triggers**:
  - Comparative questions: `Compare TRUALT and PRAJ`
  - Market catalyst questions: `Which Gobardhan companies have the strongest catalysts?`
  - Deep natural language questions: `Why did Praj and TruAlt diverge this week?`
- **Execution**:
  1. The Cloudflare Worker generates a unique `request_id` (e.g. `TG-20260927-XXXX`).
  2. Sends an immediate acknowledgement to the user:
     ```text
     🔎 Researching your question...
     Request: TG-20260927-XXXX
     I'll send the synthesized analysis directly to this chat when processing completes.
     ```
  3. Triggers GitHub Actions via `POST /repos/botv99/scheme-intel/dispatches` with `event_type: "telegram_query"`.
  4. GitHub Actions workflow `04-telegram-query.yml` boots, loads `workflow_query_runner.py`, runs the multi-provider LLM engine (Groq → OpenRouter → Gemini failover), formats the analysis card, and delivers the answer directly to the original `chat_id`.

### Path 3: RESEARCH (Deep Policy Investigation)
- **Triggers**: `/research <topic or question>`
- **Execution**: Dispatches `telegram_query` with intent `RESEARCH_REQUEST` to GitHub Actions for structured policy research. Delivers findings to the originating chat.

---

## 4. Security & Isolation Guarantee

1. **Telegram Webhook Secret**:
   Every incoming webhook request is validated against the `X-Telegram-Bot-Api-Secret-Token` header. Unauthorized or spoofed HTTP requests are rejected with HTTP 401.
2. **Strict User / Chat Isolation**:
   Responses are routed strictly to the incoming `chat_id`. The system never broadcasts private user queries or replies to public channels.
3. **Optional Whitelist**:
   Environment variables `TELEGRAM_ALLOWED_USER_IDS` and `TELEGRAM_ALLOWED_CHAT_IDS` restrict bot usage if private single-user access is desired.
4. **Zero Secrets in Logs or Repository**:
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, and `GITHUB_TOKEN` are stored exclusively in Cloudflare Worker secrets.
   - Structured logs redact any credential fields.

---

## 5. Status of Legacy VM / Docker Files

The following files are retained strictly for **local development and emergency rollback**:
- `Dockerfile`
- `docker-compose.yml`
- `deploy/oracle/*`
- `deploy/scheme-intel.service`
- `src/scheme_intel/delivery/service.py`
- `src/scheme_intel/delivery/telegram_conversation.py`

They are **no longer required for production operation**.
