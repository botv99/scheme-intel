# Scheme-Intel: Cloudflare Worker Telegram Gateway

Always-on, 24/7 serverless Telegram Conversational Gateway for Scheme-Intel.

Replaces the need for:
- ❌ Persistent Cloud VMs (Oracle / GCP / AWS)
- ❌ Docker daemons running 24/7
- ❌ Your local PC or laptop staying turned on
- ❌ Continuous Python polling processes (`getUpdates`)

---

## Architecture

```
                  ┌────────────────────────┐
                  │       Telegram         │
                  └───────────┬────────────┘
                              │ HTTPS Webhook (POST /telegram)
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
                │                            │
                ▼                            ▼
      Immediate Telegram reply       04-telegram-query.yml
                                             │
                                             ▼
                                       AI Analysis & Cards
                                             │
                                             ▼
                                    Telegram original chat
```

- **FAST Path (<100ms)**: Stock queries (`/gail`, `Praj`, `TRUALT`, `/why trualt`, `/setups`, `/watchlist`, etc.) are resolved directly in Cloudflare Worker using the precomputed intelligence snapshot (`data/intelligence/latest.json`) from GitHub.
- **WORKFLOW Path**: Multi-company comparisons (`Compare TRUALT and PRAJ`), catalyst questions, and deep natural language queries trigger GitHub Actions `04-telegram-query.yml` via `repository_dispatch`. The worker immediately sends an acknowledgement to the user and finishes in milliseconds.
- **Strict Personalization**: Responses are delivered exclusively to the requesting user's `chat_id`.

---

## 1. Prerequisites

1. A [Cloudflare Account](https://dash.cloudflare.com/) (100% Free tier includes 100,000 requests/day).
2. [Node.js](https://nodejs.org/) (v18+) and `npm` installed.
3. Your Telegram Bot Token from `@BotFather`.
4. A GitHub Personal Access Token (classic with `repo` scope, or fine-grained with `Actions: write`) so the Worker can trigger `04-telegram-query.yml`.

---

## 2. Quick Deploy (3 Simple Commands)

From your terminal:

```bash
cd cloudflare/telegram-gateway
npm install
npx wrangler login
npx wrangler deploy
```

Wrangler will output your live Worker URL, for example:
`https://scheme-intel-telegram-gateway.<your-subdomain>.workers.dev`

---

## 3. Configure Secrets in Cloudflare

Set the 3 required secrets using Wrangler (never commit secrets to Git):

```bash
# 1. Telegram Bot Token
npx wrangler secret put TELEGRAM_BOT_TOKEN
# (Paste your token when prompted)

# 2. Webhook Secret Token (choose a strong random alphanumeric string)
npx wrangler secret put TELEGRAM_WEBHOOK_SECRET
# (e.g. MySecretToken987654321)

# 3. GitHub Personal Access Token
npx wrangler secret put GITHUB_TOKEN
# (Paste your GitHub PAT)
```

Optional access control (if you want to restrict bot usage to your personal user/chat ID):
```bash
npx wrangler secret put TELEGRAM_ALLOWED_USER_IDS
# (e.g. 5917850553)
```

---

## 4. Register the Webhook with Telegram

Run the automated registration script:

```bash
node scripts/setup-webhook.js \
  --url https://scheme-intel-telegram-gateway.<your-subdomain>.workers.dev \
  --token <YOUR_TELEGRAM_BOT_TOKEN> \
  --secret <YOUR_TELEGRAM_WEBHOOK_SECRET>
```

This script:
1. Calls `setWebhook` with your Worker HTTPS URL and secret token.
2. Verifies the webhook status using `getWebhookInfo`.
3. Registers the 19 interactive bot commands with Telegram (`setMyCommands`).

---

## 5. Live Verification

Open Telegram and send messages to your bot:

| Test Case | Message | Expected Behavior |
| :--- | :--- | :--- |
| **Fast Stock Card** | `/gail` or `GAIL` | Instant response with technical state, price, status, and setups (<100ms). |
| **Fast Policy Thesis** | `/why trualt` | Instant response detailing TruAlt's GOBARdhan policy relevance. |
| **Natural Shorthand** | `Praj` | Instant card for Praj Industries. |
| **Daily Setups** | `/setups` | Instant list of today's qualified swing setups. |
| **Complex Reasoning** | `Compare TRUALT and PRAJ` | Instant acknowledgement message, followed by GitHub Actions run `04-telegram-query.yml` dispatching full comparative AI analysis back to your chat. |

---

## 6. Local Development & Testing

Run the Worker locally with live reload:

```bash
npm run dev
```

Inspect health check:
```bash
curl http://localhost:8787/health
```

---

## 7. Rollback Procedure

If you ever wish to disable the Cloudflare Worker webhook and revert to local polling or the VM gateway:

1. Delete the webhook on Telegram:
   ```bash
   curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/deleteWebhook"
   ```
2. Start the local or VM polling service:
   ```bash
   python -m scheme_intel.delivery.service --mode all
   ```
