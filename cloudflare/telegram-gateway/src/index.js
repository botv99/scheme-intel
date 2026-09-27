/**
 * Scheme-Intel Cloudflare Telegram Gateway (Stage 3).
 * Always-on, serverless Telegram webhook interface.
 * Decouples Telegram conversational delivery from local PCs, VMs, and continuous Python processes.
 */

import { generateRequestId, safeLog } from "./utils.js";
import { validateWebhookSecret, isAuthorized } from "./auth.js";
import { resolveIntent, ExecutionPath, IntentType } from "./resolver.js";
import {
  getSnapshot,
  SnapshotStatus,
  renderStockCard,
  renderWhyCard,
  renderWhatCard,
  renderWhenCard,
  renderSetupsCard,
  renderWaitingCard,
  renderWatchlistCard,
  renderSchemesCard,
  renderPerformanceCard,
  renderBenchmarkCard,
  renderStartMenu,
  renderHelpMenu,
} from "./snapshot.js";
import { sendMessage, answerCallbackQuery, setMyCommands, BOT_COMMANDS } from "./telegram.js";
import { dispatchWorkflow, getGithubToken } from "./github.js";

const VERSION = "1.0.1";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const method = request.method.toUpperCase();

    // 1. Health check endpoints
    if (url.pathname === "/health") {
      const resolvedGithubToken = getGithubToken(env);
      const isGithubConfigured = resolvedGithubToken.length > 0;
      return new Response(
        JSON.stringify({
          status: "ok",
          service: "scheme-intel-telegram-gateway",
          version: VERSION,
          timestamp: new Date().toISOString(),
          diagnostics: {
            github_token_configured: isGithubConfigured,
            telegram_bot_token_configured: Boolean(env?.TELEGRAM_BOT_TOKEN),
            telegram_webhook_secret_configured: Boolean(env?.TELEGRAM_WEBHOOK_SECRET),
            env_keys: Object.keys(env || {}).sort(),
          },
        }, null, 2),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    if (url.pathname === "/register-commands") {
      const botToken = env.TELEGRAM_BOT_TOKEN;
      if (!botToken) {
        return new Response(JSON.stringify({ error: "Missing TELEGRAM_BOT_TOKEN" }), { status: 500, headers: { "Content-Type": "application/json" } });
      }
      const res = await setMyCommands(botToken, BOT_COMMANDS);
      return new Response(
        JSON.stringify({ result: res, registered_commands: BOT_COMMANDS }, null, 2),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }

    if (url.pathname === "/" && method === "GET") {
      return new Response(
        JSON.stringify({
          service: "Scheme-Intel Telegram Conversational Gateway",
          status: "RUNNING",
          version: VERSION,
          runtime: "Cloudflare Workers",
          target_repo: `${env.GITHUB_OWNER || "botv99"}/${env.GITHUB_REPO || "scheme-intel"}`,
        }, null, 2),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // 2. Reject unsupported methods on webhook endpoint
    if (method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // 3. Validate Telegram Webhook Secret Token
    const expectedSecret = env.TELEGRAM_WEBHOOK_SECRET;
    if (!validateWebhookSecret(request, expectedSecret)) {
      safeLog("warn", "webhook_secret_mismatch", { ip: request.headers.get("CF-Connecting-IP") });
      return new Response("Unauthorized", { status: 401 });
    }

    // 4. Parse Telegram Update
    let update;
    try {
      update = await request.json();
    } catch (err) {
      safeLog("error", "invalid_json_body", { error: err.message });
      return new Response("Bad Request: Invalid JSON", { status: 400 });
    }

    // Extract message or callback_query
    const botToken = env.TELEGRAM_BOT_TOKEN;
    let rawText = "";
    let chatId = null;
    let userId = null;
    let username = null;
    let messageId = null;

    if (update.callback_query) {
      const cb = update.callback_query;
      if (cb.id && botToken) {
        ctx.waitUntil(answerCallbackQuery(botToken, cb.id));
      }
      rawText = (cb.data || "").trim();
      userId = cb.from?.id ? String(cb.from.id) : null;
      username = cb.from?.username || null;
      chatId = cb.message?.chat?.id ? String(cb.message.chat.id) : null;
      messageId = cb.message?.message_id || null;
    } else if (update.message || update.edited_message) {
      const msg = update.message || update.edited_message;
      rawText = (msg.text || "").trim();
      userId = msg.from?.id ? String(msg.from.id) : null;
      username = msg.from?.username || null;
      chatId = msg.chat?.id ? String(msg.chat.id) : null;
      messageId = msg.message_id || null;
    } else {
      // Ignore unsupported update types safely (e.g. channel_post, my_chat_member)
      return new Response("OK", { status: 200 });
    }

    if (!rawText || !chatId) {
      return new Response("OK", { status: 200 });
    }

    const requestId = generateRequestId();
    safeLog("info", "telegram_update_received", {
      requestId,
      updateId: update.update_id,
      chatId,
      userId,
      username,
      query: rawText.slice(0, 60),
    });

    // 5. Access Authorization Check
    const isUserAllowed = isAuthorized(
      userId,
      chatId,
      env.TELEGRAM_ALLOWED_USER_IDS,
      env.TELEGRAM_ALLOWED_CHAT_IDS
    );

    if (!isUserAllowed) {
      safeLog("warn", "unauthorized_access_denied", { requestId, userId, chatId });
      if (botToken) {
        ctx.waitUntil(
          sendMessage(
            botToken,
            chatId,
            "🔒 *Access Restricted*\n\nYou are not authorized to use this private terminal.",
            { requestId }
          )
        );
      }
      return new Response("OK", { status: 200 });
    }

    // 6. Resolve Intent & Execution Path
    const resolved = resolveIntent(rawText);
    safeLog("info", "intent_resolved", {
      requestId,
      path: resolved.executionPath,
      intent: resolved.intentType,
      symbol: resolved.symbol,
      schemeId: resolved.schemeId,
    });

    // =========================================================================
    // PATH 1: FAST (<100ms from Precomputed Intelligence Snapshot)
    // =========================================================================
    if (resolved.executionPath === ExecutionPath.FAST) {
      const snapResult = await getSnapshot(env);

      let replyText = "";
      const isStale = snapResult.isStale;
      const snapshot = snapResult.snapshot;

      if (snapResult.status === SnapshotStatus.MISSING || !snapshot) {
        replyText =
          `⚠️ *Scheme-Intel Snapshot Unavailable*\n\n` +
          `The intelligence snapshot is temporarily unavailable.\n` +
          `Please try again shortly after the next scheduled scan.\n\n` +
          `_Request ID:_ \`${requestId}\``;
      } else {
        switch (resolved.intentType) {
          case IntentType.START:
            replyText = renderStartMenu();
            break;
          case IntentType.HELP:
            replyText = renderHelpMenu();
            break;
          case IntentType.HEALTH_CHECK:
            replyText =
              `💚 *System Health: READY*\n\n` +
              `• Gateway: Cloudflare Worker\n` +
              `• Snapshot ID: \`${snapshot.snapshot_id}\`\n` +
              `• Age: ${snapResult.ageHours || 0} hours\n` +
              `• Status: ${isStale ? "⚠️ STALE (>26h)" : "🟢 FRESH"}\n` +
              `• Tracked Stocks: ${Object.keys(snapshot.companies || {}).length}\n` +
              `• Qualified Setups: ${(snapshot.qualified_setups || []).length}`;
            break;
          case IntentType.STOCK_PROMPT:
            replyText = "🏷️ *Query Help: /stock*\n\nPlease specify a stock symbol: e.g. `/stock GAIL` or `/stock TRUALT`";
            break;
          case IntentType.STOCK_LOOKUP: {
            const sym = (resolved.symbol || "").toUpperCase();
            const shortSym = (resolved.shortSymbol || "").toUpperCase();
            const rawTarget = (resolved.rawQuery || "").replace(/^\/stock\s*/i, "").trim().toUpperCase();

            // Match symbol, short_symbol, or company name dynamically from snapshot
            const comp =
              snapshot.companies[sym] ||
              snapshot.companies[shortSym] ||
              Object.values(snapshot.companies).find(
                (c) =>
                  c.symbol?.toUpperCase() === sym ||
                  c.short_symbol?.toUpperCase() === shortSym ||
                  c.name?.toUpperCase() === rawTarget ||
                  (rawTarget.length >= 3 && c.name?.toUpperCase().includes(rawTarget))
              );

            if (comp) {
              replyText = renderStockCard(comp, snapshot, isStale);
            } else {
              replyText =
                `🏷️ *Stock Not Found*\n\n` +
                `\`${resolved.shortSymbol || resolved.symbol || rawTarget || "Stock"}\` is not currently in the active Scheme-Intel watchlist.\n\n` +
                `Use /watchlist to see monitored companies.`;
            }
            break;
          }
          case IntentType.STOCK_WHY: {
            const comp =
              snapshot.companies[resolved.symbol] ||
              snapshot.companies[resolved.shortSymbol];
            replyText = comp
              ? renderWhyCard(comp, isStale)
              : `Stock \`${resolved.shortSymbol || resolved.symbol}\` not found in watchlist.`;
            break;
          }
          case IntentType.STOCK_WHAT: {
            const comp =
              snapshot.companies[resolved.symbol] ||
              snapshot.companies[resolved.shortSymbol];
            replyText = comp
              ? renderWhatCard(comp, isStale)
              : `Stock \`${resolved.shortSymbol || resolved.symbol}\` not found in watchlist.`;
            break;
          }
          case IntentType.STOCK_WHEN: {
            const comp =
              snapshot.companies[resolved.symbol] ||
              snapshot.companies[resolved.shortSymbol];
            replyText = comp
              ? renderWhenCard(comp, isStale)
              : `Stock \`${resolved.shortSymbol || resolved.symbol}\` not found in watchlist.`;
            break;
          }
          case IntentType.STOCK_WHY_PROMPT:
            replyText = "❓ *Query Help: /why*\n\nPlease specify a stock symbol: e.g. `/why trualt` or `/why gail`";
            break;
          case IntentType.STOCK_WHAT_PROMPT:
            replyText = "⚡ *Query Help: /what*\n\nPlease specify a stock symbol: e.g. `/what praj` or `/what trualt`";
            break;
          case IntentType.STOCK_WHEN_PROMPT:
            replyText = "⏱️ *Query Help: /when*\n\nPlease specify a stock symbol: e.g. `/when wabag` or `/when gail`";
            break;
          case IntentType.SETUPS_LOOKUP:
            replyText = renderSetupsCard(snapshot, isStale);
            break;
          case IntentType.WAITING_LOOKUP:
            replyText = renderWaitingCard(snapshot, isStale);
            break;
          case IntentType.WATCHLIST:
            replyText = renderWatchlistCard(snapshot, isStale);
            break;
          case IntentType.SCHEMES:
          case IntentType.SCHEME_LOOKUP:
            replyText = renderSchemesCard(snapshot, isStale);
            break;
          case IntentType.PERFORMANCE_LOOKUP:
            replyText = renderPerformanceCard(snapshot, isStale);
            break;
          case IntentType.BENCHMARK_LOOKUP:
            replyText = renderBenchmarkCard(snapshot, isStale);
            break;
          default:
            replyText = renderStartMenu();
            break;
        }
      }

      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId }));
      }
      return new Response("OK", { status: 200 });
    }

    // =========================================================================
    // PATH 2: WORKFLOW (Event-driven repository_dispatch → 04-telegram-query.yml)
    // =========================================================================
    if (resolved.executionPath === ExecutionPath.WORKFLOW) {
      // 1. Send immediate conversational acknowledgement to user
      const ackMessage =
        `🔎 *Researching your question...*\n\n` +
        `*Request ID:* \`${requestId}\`\n` +
        `*Query:* _${rawText}_\n\n` +
        `I'll send the synthesized analysis directly to this chat when processing completes.`;

      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, ackMessage, { requestId }));
      }

      // 2. Dispatch repository_dispatch event to GitHub Actions
      const owner = env.GITHUB_OWNER || "botv99";
      const repo = env.GITHUB_REPO || "scheme-intel";
      const clientPayload = {
        request_id: requestId,
        user_id: userId,
        chat_id: chatId,
        message_id: messageId,
        raw_query: rawText,
        normalized_query: resolved.normalizedQuery,
        query: rawText,
        intent: resolved.intentType,
        scheme_id: resolved.schemeId || "gobardhan",
        symbol: resolved.symbol || null,
      };

      ctx.waitUntil(
        (async () => {
          const githubToken = getGithubToken(env);
          const dispatchRes = await dispatchWorkflow(
            githubToken,
            owner,
            repo,
            "telegram_query",
            clientPayload
          );

          if (!dispatchRes.success && botToken) {
            const errReply =
              `⚠️ *Could Not Start Analysis*\n\n` +
              `*Request ID:* \`${requestId}\`\n\n` +
              `I encountered an issue triggering the analysis workflow.\n` +
              `_Reason:_ ${dispatchRes.error}`;
            await sendMessage(botToken, chatId, errReply, { requestId });
          }
        })()
      );

      return new Response("OK", { status: 200 });
    }

    // =========================================================================
    // PATH 3: RESEARCH (/research <question>)
    // =========================================================================
    if (resolved.executionPath === ExecutionPath.RESEARCH) {
      const question = resolved.question || rawText.replace(/^\/research\s*/i, "").trim();

      const ackMessage =
        `🔬 *DEEP RESEARCH STARTED*\n\n` +
        `*Request ID:*\n\`${requestId}\`\n\n` +
        `Your research is being analyzed by the Scheme-Intel intelligence engine.\n\n` +
        `This may take a little time.`;

      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, ackMessage, { requestId }));
      }

      const owner = env.GITHUB_OWNER || "botv99";
      const repo = env.GITHUB_REPO || "scheme-intel";
      const clientPayload = {
        request_id: requestId,
        user_id: userId,
        chat_id: chatId,
        message_id: messageId,
        raw_query: rawText,
        normalized_query: resolved.normalizedQuery,
        query: question || rawText,
        intent: "RESEARCH_REQUEST",
        scheme_id: resolved.schemeId || "gobardhan",
        symbol: resolved.symbol || null,
      };

      ctx.waitUntil(
        (async () => {
          const githubToken = getGithubToken(env);
          const dispatchRes = await dispatchWorkflow(
            githubToken,
            owner,
            repo,
            "telegram_query",
            clientPayload
          );

          if (!dispatchRes.success && botToken) {
            const errReply =
              `⚠️ *Could Not Queue Research*\n\n` +
              `*Request ID:* \`${requestId}\`\n\n` +
              `_Reason:_ ${dispatchRes.error}`;
            await sendMessage(botToken, chatId, errReply, { requestId });
          }
        })()
      );

      return new Response("OK", { status: 200 });
    }

    return new Response("OK", { status: 200 });
  },
};
