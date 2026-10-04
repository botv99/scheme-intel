/**
 * Scheme-Intel Cloudflare Telegram Gateway.
 * Production-ready Serverless Gateway with Supabase Authorization,
 * Scheme Entitlements, Payment Webhooks, and Multi-Scheme Isolation.
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
  renderSchemesSelectMenu,
  getSchemesInlineKeyboard,
  renderSchemeHeaderMenu,
  getSchemeInlineKeyboard,
  getStartInlineKeyboard,
  getBackAndSwitchKeyboard,
  renderLockedStartMenu,
  getLockedStartKeyboard,
  renderSchemeLockedCard,
  getSchemeLockedKeyboard,
  renderStockRestrictedCard,
  getStockRestrictedKeyboard,
  renderAvailableSchemesMenu,
  getAvailableSchemesKeyboard,
  renderPurchaseMenu,
  getPurchaseKeyboard,
  renderOrderPaymentCard,
  getOrderPaymentKeyboard,
  renderAccessExpiredCard,
  getAccessExpiredKeyboard,
  renderActivationSuccessCard,
  getActivationSuccessKeyboard,
} from "./snapshot.js";
import { sendMessage, answerCallbackQuery, setMyCommands, getMyCommands, BOT_COMMANDS } from "./telegram.js";
import { dispatchWorkflow, getGithubToken } from "./github.js";
import {
  getTelegramAuth,
  checkSchemeAccess,
  getStockScheme,
  filterSnapshotForUser,
  isPlatformAdmin,
} from "./authorization.js";
import { setUserSelectedScheme, recordAuditEvent } from "./users.js";
import { activateAccessKey } from "./keys.js";
import { getAllSchemes } from "./entitlements.js";
import { getProducts, getProductByCode, createPaymentOrder, findOrder } from "./orders.js";
import { handlePaymentWebhook } from "./payments/webhook.js";
import { handleAdminCommand } from "./admin.js";

const VERSION = "2.0.0";

// Short-lived session cache for quick lookup
const userSessionCache = new Map();

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const method = request.method.toUpperCase();

    // 1. Payment Webhook Endpoints
    if (url.pathname === "/webhooks/razorpay" || url.pathname === "/payment/webhook") {
      return handlePaymentWebhook(request, env, ctx);
    }

    // 2. Health check endpoints
    if (url.pathname === "/health") {
      const resolvedGithubToken = getGithubToken(env);
      const isGithubConfigured = resolvedGithubToken.length > 0;
      return new Response(
        JSON.stringify(
          {
            status: "ok",
            service: "scheme-intel-telegram-gateway",
            version: VERSION,
            timestamp: new Date().toISOString(),
            diagnostics: {
              github_token_configured: isGithubConfigured,
              telegram_bot_token_configured: Boolean(env?.TELEGRAM_BOT_TOKEN),
              telegram_webhook_secret_configured: Boolean(env?.TELEGRAM_WEBHOOK_SECRET),
              supabase_configured: Boolean(env?.SUPABASE_URL && (env?.SUPABASE_SERVICE_ROLE_KEY || env?.SUPABASE_KEY)),
              razorpay_configured: Boolean(env?.RAZORPAY_KEY_ID && env?.RAZORPAY_KEY_SECRET),
              razorpay_webhook_secret_configured: Boolean(env?.RAZORPAY_WEBHOOK_SECRET),
              admin_ids_configured: Boolean(env?.ADMIN_USER_IDS || env?.PLATFORM_ADMIN_IDS),
              env_keys: Object.keys(env || {}).sort(),
            },
          },
          null,
          2
        ),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    if (url.pathname === "/register-commands") {
      const botToken = env.TELEGRAM_BOT_TOKEN;
      if (!botToken) {
        return new Response(JSON.stringify({ error: "Missing TELEGRAM_BOT_TOKEN" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }
      const setRes = await setMyCommands(botToken, BOT_COMMANDS);
      const getRes = await getMyCommands(botToken);
      return new Response(
        JSON.stringify(
          { result: setRes, verified_commands: getRes?.result || getRes, registered_commands: BOT_COMMANDS },
          null,
          2
        ),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }

    if (url.pathname === "/verify-commands") {
      const botToken = env.TELEGRAM_BOT_TOKEN;
      if (!botToken) {
        return new Response(JSON.stringify({ error: "Missing TELEGRAM_BOT_TOKEN" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }
      const getRes = await getMyCommands(botToken);
      return new Response(JSON.stringify(getRes, null, 2), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url.pathname === "/" && method === "GET") {
      return new Response(
        JSON.stringify(
          {
            service: "Scheme-Intel Telegram Conversational Gateway",
            status: "RUNNING",
            version: VERSION,
            runtime: "Cloudflare Workers",
            target_repo: `${env.GITHUB_OWNER || "botv99"}/${env.GITHUB_REPO || "scheme-intel"}`,
            auth_model: "Supabase Commercial Entitlements",
          },
          null,
          2
        ),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // 3. Reject unsupported methods on webhook endpoint
    if (method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // 4. Validate Telegram Webhook Secret Token
    const expectedSecret = env.TELEGRAM_WEBHOOK_SECRET;
    if (!validateWebhookSecret(request, expectedSecret)) {
      safeLog("warn", "webhook_secret_mismatch", { ip: request.headers.get("CF-Connecting-IP") });
      return new Response("Unauthorized", { status: 401 });
    }

    // 5. Parse Telegram Update
    let update;
    try {
      update = await request.json();
    } catch (err) {
      safeLog("error", "invalid_json_body", { error: err.message });
      return new Response("Bad Request: Invalid JSON", { status: 400 });
    }

    const botToken = env.TELEGRAM_BOT_TOKEN;
    let rawText = "";
    let chatId = null;
    let userId = null;
    let username = null;
    let firstName = null;
    let messageId = null;

    if (update.callback_query) {
      const cb = update.callback_query;
      if (cb.id && botToken) {
        ctx.waitUntil(answerCallbackQuery(botToken, cb.id));
      }
      rawText = (cb.data || "").trim();
      userId = cb.from?.id ? String(cb.from.id) : null;
      username = cb.from?.username || null;
      firstName = cb.from?.first_name || null;
      chatId = cb.message?.chat?.id ? String(cb.message.chat.id) : null;
      messageId = cb.message?.message_id || null;
    } else if (update.message || update.edited_message) {
      const msg = update.message || update.edited_message;
      rawText = (msg.text || "").trim();
      userId = msg.from?.id ? String(msg.from.id) : null;
      username = msg.from?.username || null;
      firstName = msg.from?.first_name || null;
      chatId = msg.chat?.id ? String(msg.chat.id) : null;
      messageId = msg.message_id || null;
    } else {
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

    // 6. Supabase Authorization & Entitlement Verification
    // Database entitlements are the authoritative source of truth
    let auth = null;
    try {
      auth = await getTelegramAuth(env, { userId, chatId, username, firstName });
    } catch (authErr) {
      safeLog("error", "auth_resolution_error", { error: authErr.message });
      // Fallback auth context in degraded DB state
      auth = {
        user: { id: "offline", telegram_user_id: userId, status: "LOCKED" },
        isAdmin: isPlatformAdmin(userId, chatId, env),
        isAuthorized: isPlatformAdmin(userId, chatId, env),
        isLocked: !isPlatformAdmin(userId, chatId, env),
        allowedSchemes: isPlatformAdmin(userId, chatId, env) ? ["gobardhan", "samudra_manthan"] : [],
        entitlements: [],
        activeScheme: "gobardhan",
      };
    }

    // Determine current active scheme
    const activeScheme = auth.activeScheme || "gobardhan";
    const resolved = resolveIntent(rawText, activeScheme);

    safeLog("info", "intent_resolved", {
      requestId,
      userId,
      isAuthorized: auth.isAuthorized,
      allowedSchemes: auth.allowedSchemes,
      activeScheme,
      path: resolved.executionPath,
      intent: resolved.intentType,
      symbol: resolved.symbol,
    });

    // =========================================================================
    // SECTION A: PUBLIC & NON-SENSITIVE COMMANDS (Always accessible)
    // =========================================================================

    // A1. /admin commands
    if (resolved.intentType === IntentType.ADMIN) {
      const adminRes = await handleAdminCommand(rawText, userId, chatId, env);
      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, adminRes.replyText, { requestId, replyMarkup: adminRes.replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // A2. /help command
    if (resolved.intentType === IntentType.HELP) {
      const replyText = renderHelpMenu();
      const replyMarkup = auth.isLocked ? getLockedStartKeyboard() : getBackAndSwitchKeyboard(activeScheme);
      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // A3. /schemes or Available Schemes Catalog
    if (resolved.intentType === IntentType.SCHEMES || resolved.intentType === IntentType.AVAILABLE_SCHEMES) {
      const allSchemes = await getAllSchemes(env);
      const replyText = renderAvailableSchemesMenu(allSchemes, auth.allowedSchemes);
      const replyMarkup = getAvailableSchemesKeyboard(allSchemes, auth.allowedSchemes);
      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // A4. Enter Key Prompt
    if (resolved.intentType === IntentType.ENTER_KEY_PROMPT) {
      const replyText =
        `🔑 *ENTER AUTHORIZATION KEY*\n\n` +
        `Please reply with your access key:\n\n` +
        `\`/activate <YOUR-KEY>\`\n\n` +
        `Example:\n\`/activate GOB-82KD-19XP\``;
      const replyMarkup = {
        inline_keyboard: [
          [{ text: "🛒 Purchase Access", callback_data: "action:purchase_menu" }],
          [{ text: "← Back", callback_data: "/start" }],
        ],
      };
      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // A5. /activate <key>
    if (resolved.intentType === IntentType.ACTIVATE_KEY) {
      const rawKey = resolved.key || rawText.replace(/^\/activate\s*/i, "").trim();
      const actRes = await activateAccessKey(env, {
        telegramUserId: userId,
        rawKey,
        telegramChatId: chatId,
        username,
        firstName,
      });

      let replyText = "";
      let replyMarkup = null;

      if (actRes.success) {
        replyText = renderActivationSuccessCard(actRes.grantedSchemes, actRes.expiresAt);
        replyMarkup = getActivationSuccessKeyboard(actRes.grantedSchemes);
      } else {
        replyText = `❌ *KEY ACTIVATION FAILED*\n\n${actRes.message}\n\nPlease check your key and try again.`;
        replyMarkup = {
          inline_keyboard: [
            [{ text: "🔑 Try Another Key", callback_data: "action:enter_key" }],
            [{ text: "🛒 Purchase Access", callback_data: "action:purchase_menu" }],
          ],
        };
      }

      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // A6. /purchase or Purchase Menu
    if (resolved.intentType === IntentType.PURCHASE_MENU) {
      const products = await getProducts(env);
      const replyText = renderPurchaseMenu(products);
      const replyMarkup = getPurchaseKeyboard(products);
      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // A7. Buy Product: Create Order & Payment Link
    if (resolved.intentType === IntentType.BUY_PRODUCT) {
      const productCode = resolved.productCode;
      try {
        const orderRes = await createPaymentOrder(env, {
          user: auth.user,
          productCode,
          providerName: "razorpay",
        });

        const replyText = renderOrderPaymentCard(orderRes.order, orderRes.product);
        const replyMarkup = getOrderPaymentKeyboard(orderRes.paymentUrl, orderRes.orderCode);

        if (botToken) {
          ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
        }
      } catch (pErr) {
        const errReply = `⚠️ *Payment Error*\n\nUnable to generate payment link: ${pErr.message}`;
        if (botToken) {
          ctx.waitUntil(sendMessage(botToken, chatId, errReply, { requestId }));
        }
      }
      return new Response("OK", { status: 200 });
    }

    // A8. Buy Scheme: Find products for scheme
    if (resolved.intentType === IntentType.BUY_SCHEME) {
      const sid = (resolved.schemeId || activeScheme).toLowerCase();
      const allProducts = await getProducts(env);
      const matchingProducts = allProducts.filter((p) => (p.schemes || []).includes(sid) || p.product_code.includes("ALL"));
      const replyText = renderPurchaseMenu(matchingProducts.length > 0 ? matchingProducts : allProducts);
      const replyMarkup = getPurchaseKeyboard(matchingProducts.length > 0 ? matchingProducts : allProducts);
      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // A9. Check Order Status
    if (resolved.intentType === IntentType.CHECK_ORDER) {
      const orderCode = resolved.orderCode;
      const order = await findOrder(env, { orderCode });
      let replyText = "";
      let replyMarkup = null;

      if (!order) {
        replyText = `⚠️ *Order Not Found*\n\nNo order record found for \`${orderCode}\`.`;
      } else if (order.status === "PAID") {
        replyText = `✅ *ORDER PAID*\n\nOrder \`${orderCode}\` has been confirmed and your scheme access is active!`;
        replyMarkup = { inline_keyboard: [[{ text: "🌱 Open Terminal", callback_data: "/start" }]] };
      } else {
        replyText =
          `⏳ *ORDER PENDING*\n\n` +
          `Order: \`${orderCode}\`\n` +
          `Status: *${order.status}*\n` +
          `Amount: ₹${order.amount}\n\n` +
          `If you have completed payment, please wait a few seconds and tap Check Status again.`;
        replyMarkup = getOrderPaymentKeyboard(order.metadata?.payment_url, orderCode);
      }

      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // A10. /status or My Access
    if (resolved.intentType === IntentType.MY_ACCESS) {
      let entLines = "";
      if (auth.isAdmin) {
        entLines = "👑 *Administrator (Universal Access)*";
      } else if (auth.entitlements.length === 0) {
        entLines = "🔒 *No active subscriptions.* Account is locked.";
      } else {
        entLines = auth.entitlements
          .map((e) => {
            const exp = e.expires_at ? new Date(e.expires_at).toLocaleDateString("en-GB") : "Ongoing";
            return `• *${e.scheme_id.toUpperCase()}*: Active until ${exp} (Source: ${e.source})`;
          })
          .join("\n");
      }

      const replyText =
        `📋 *MY ACCOUNT & ACCESS*\n\n` +
        `• *Telegram ID:* \`${userId}\`\n` +
        `• *Status:* ${auth.isLocked ? "🔒 LOCKED" : "🟢 ACTIVE"}\n` +
        `• *Active Scheme:* ${activeScheme}\n\n` +
        `*Entitlements:*\n${entLines}`;

      const replyMarkup = auth.isLocked ? getLockedStartKeyboard() : getBackAndSwitchKeyboard(activeScheme);
      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // =========================================================================
    // SECTION B: LOCKED USER GATE
    // =========================================================================
    if (auth.isLocked) {
      safeLog("warn", "locked_user_access_blocked", { userId, chatId, query: rawText });
      await recordAuditEvent(env, {
        userId: auth.user?.id,
        telegramUserId: String(userId),
        eventType: "SCHEME_ACCESS_DENIED",
        metadata: { query: rawText, reason: "ACCOUNT_LOCKED" },
      });

      // Show locked card
      const replyText = renderLockedStartMenu();
      const replyMarkup = getLockedStartKeyboard();
      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // =========================================================================
    // SECTION C: SCHEME-LEVEL AUTHORIZATION & ISOLATION GATES
    // =========================================================================

    // C1. Start Menu for Authorized Users
    if (resolved.intentType === IntentType.START) {
      const replyText = renderStartMenu();
      const replyMarkup = getStartInlineKeyboard(activeScheme);
      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // C2. Scheme Switching (e.g. scheme_select:samudra_manthan)
    if (resolved.intentType === IntentType.SWITCH_SCHEME) {
      const targetScheme = (resolved.targetScheme || resolved.schemeId || "gobardhan").toLowerCase();
      const isAllowed = checkSchemeAccess(auth, targetScheme);

      if (!isAllowed) {
        safeLog("warn", "scheme_switch_unauthorized", { userId, targetScheme });
        await recordAuditEvent(env, {
          userId: auth.user.id,
          telegramUserId: String(userId),
          eventType: "SCHEME_ACCESS_DENIED",
          schemeId: targetScheme,
          metadata: { action: "SWITCH_SCHEME" },
        });

        const replyText = renderSchemeLockedCard(targetScheme);
        const replyMarkup = getSchemeLockedKeyboard(targetScheme);
        if (botToken) {
          ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
        }
        return new Response("OK", { status: 200 });
      }

      // Persist user selected active scheme in database
      await setUserSelectedScheme(env, auth.user.id, targetScheme);
      const replyText = renderSchemeHeaderMenu(targetScheme, true);
      const replyMarkup = getSchemeInlineKeyboard(targetScheme);
      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // C3. Stock Isolation: Verify stock belongs to user's authorized scheme(s)
    const stockQueryIntents = [
      IntentType.STOCK_LOOKUP,
      IntentType.STOCK_WHY,
      IntentType.STOCK_WHAT,
      IntentType.STOCK_WHEN,
    ];

    if (stockQueryIntents.includes(resolved.intentType)) {
      const sym = (resolved.symbol || resolved.shortSymbol || rawText.replace(/^\/stock\s*/i, "")).trim().toUpperCase();
      const stockScheme = getStockScheme(sym);

      if (stockScheme && !checkSchemeAccess(auth, stockScheme)) {
        safeLog("warn", "stock_scheme_access_restricted", { userId, sym, stockScheme });
        await recordAuditEvent(env, {
          userId: auth.user.id,
          telegramUserId: String(userId),
          eventType: "SCHEME_ACCESS_DENIED",
          schemeId: stockScheme,
          metadata: { symbol: sym },
        });

        const replyText = renderStockRestrictedCard(resolved.shortSymbol || resolved.symbol || sym, auth.allowedSchemes);
        const replyMarkup = getStockRestrictedKeyboard();
        if (botToken) {
          ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
        }
        return new Response("OK", { status: 200 });
      }
    }

    // C4. Target Scheme Access Check for Scheme-Specific Actions (menus, watchlists, setups)
    const currentScheme = (resolved.schemeId || activeScheme || "gobardhan").toLowerCase();
    if (!stockQueryIntents.includes(resolved.intentType) && !checkSchemeAccess(auth, currentScheme)) {
      safeLog("warn", "scheme_action_denied", { userId, currentScheme });
      await recordAuditEvent(env, {
        userId: auth.user.id,
        telegramUserId: String(userId),
        eventType: "SCHEME_ACCESS_DENIED",
        schemeId: currentScheme,
        metadata: { intent: resolved.intentType },
      });

      const replyText = renderSchemeLockedCard(currentScheme);
      const replyMarkup = getSchemeLockedKeyboard(currentScheme);
      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // =========================================================================
    // SECTION D: EXECUTION PATHS (With Server-Side Snapshot Filtering)
    // =========================================================================

    // D1. FAST PATH (<100ms from Precomputed Intelligence Snapshot)
    if (resolved.executionPath === ExecutionPath.FAST) {
      const snapResult = await getSnapshot(env);

      let replyText = "";
      let replyMarkup = null;
      const isStale = snapResult.isStale;
      const rawSnapshot = snapResult.snapshot;

      if (snapResult.status === SnapshotStatus.MISSING || !rawSnapshot) {
        replyText =
          `⚠️ *Scheme-Intel Snapshot Unavailable*\n\n` +
          `The intelligence snapshot is temporarily unavailable.\n` +
          `Please try again shortly after the next scheduled scan.\n\n` +
          `_Request ID:_ \`${requestId}\``;
      } else {
        // MANDATORY SERVER-SIDE SNAPSHOT FILTERING
        const snapshot = filterSnapshotForUser(rawSnapshot, auth.allowedSchemes, auth.isAdmin);

        switch (resolved.intentType) {
          case IntentType.SCHEME_MENU:
            replyText = renderSchemeHeaderMenu(currentScheme, false);
            replyMarkup = getSchemeInlineKeyboard(currentScheme);
            break;
          case IntentType.WATCHLIST:
            replyText = renderWatchlistCard(snapshot, currentScheme, isStale);
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          case IntentType.SETUPS_LOOKUP:
            replyText = renderSetupsCard(snapshot, isStale);
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          case IntentType.WAITING_LOOKUP:
            replyText = renderWaitingCard(snapshot, isStale);
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          case IntentType.RESEARCH_PROMPT: {
            const schemeName = currentScheme === "samudra_manthan" ? "Samudra Manthan" : "Gobardhan";
            replyText =
              `🔬 *${schemeName.toUpperCase()} RESEARCH*\n\n` +
              `To submit a deep policy or company investigation, use:\n` +
              `\`/research <your question>\`\n\n` +
              `Example:\n` +
              (currentScheme === "samudra_manthan"
                ? `\`/research Analyze ONGC deepwater block allocations in KG basin\``
                : `\`/research Analyze CBG blending mandate impact on Praj\``);
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          }
          case IntentType.INTELLIGENCE_LOOKUP: {
            if (currentScheme === "samudra_manthan") {
              replyText =
                `📰 *SAMUDRA MANTHAN INTELLIGENCE*\n\n` +
                `• *OALP Round IX:* Deepwater block bids evaluating offshore commitments\n` +
                `• *Crude & Gas Economics:* Offshore breakeven ranges $42-$55/bbl\n` +
                `• *Offshore Rig Activity:* ONGC chartering 3 ultra-deepwater drillships\n` +
                `• *Key Beneficiaries:* ONGC, OIL, Reliance, Deep Industries\n\n` +
                `_Source redundancy enabled via MoPNG, DGH, and exchange disclosures._`;
            } else {
              replyText =
                `📰 *GOBARDHAN INTELLIGENCE*\n\n` +
                `• *SATAT CBG Mandate:* 5,000 CBG plants target under national bio-energy scheme\n` +
                `• *Feedstock Sourcing:* Agricultural crop residue & press-mud linkages active\n` +
                `• *EPC & Technology:* Praj, TruAlt, and Wabag executing regional clusters\n` +
                `• *Offtake Integration:* GAIL & OMCs contracted for priority CBG grid injection\n\n` +
                `_Source redundancy enabled via DDWS Gobardhan Portal and MoPNG._`;
            }
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          }
          case IntentType.HEALTH_CHECK:
            replyText =
              `💚 *System Health: READY*\n\n` +
              `• Gateway: Cloudflare Worker\n` +
              `• Scheme: ${currentScheme === "samudra_manthan" ? "🌊 Samudra Manthan" : "🌱 Gobardhan"}\n` +
              `• Snapshot ID: \`${snapshot.snapshot_id}\`\n` +
              `• Status: ${isStale ? "⚠️ STALE (>26h)" : "🟢 FRESH"}\n` +
              `• Authorized Stocks: ${Object.keys(snapshot.companies || {}).length}\n` +
              `• Qualified Setups: ${(snapshot.qualified_setups || []).length}`;
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          case IntentType.STOCK_PROMPT:
            replyText = "🏷️ *Query Help: /stock*\n\nPlease specify a stock symbol: e.g. `/stock GAIL` or `/stock ONGC`";
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          case IntentType.STOCK_LOOKUP: {
            const sym = (resolved.symbol || "").toUpperCase();
            const shortSym = (resolved.shortSymbol || "").toUpperCase();
            const rawTarget = (resolved.rawQuery || "").replace(/^\/stock\s*/i, "").trim().toUpperCase();

            // Match only from authorized/filtered snapshot companies
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
                `\`${resolved.shortSymbol || resolved.symbol || rawTarget || "Stock"}\` is not in your authorized Scheme-Intel watchlist.\n\n` +
                `Use /watchlist to see monitored companies.`;
            }
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          }
          case IntentType.STOCK_WHY: {
            const comp = snapshot.companies[resolved.symbol] || snapshot.companies[resolved.shortSymbol];
            replyText = comp ? renderWhyCard(comp, isStale) : `Stock \`${resolved.shortSymbol || resolved.symbol}\` not found in authorized watchlist.`;
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          }
          case IntentType.STOCK_WHAT: {
            const comp = snapshot.companies[resolved.symbol] || snapshot.companies[resolved.shortSymbol];
            replyText = comp ? renderWhatCard(comp, isStale) : `Stock \`${resolved.shortSymbol || resolved.symbol}\` not found in authorized watchlist.`;
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          }
          case IntentType.STOCK_WHEN: {
            const comp = snapshot.companies[resolved.symbol] || snapshot.companies[resolved.shortSymbol];
            replyText = comp ? renderWhenCard(comp, isStale) : `Stock \`${resolved.shortSymbol || resolved.symbol}\` not found in authorized watchlist.`;
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          }
          case IntentType.STOCK_WHY_PROMPT:
            replyText = "❓ *Query Help: /why*\n\nPlease specify a stock symbol: e.g. `/why trualt` or `/why ongc`";
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          case IntentType.STOCK_WHAT_PROMPT:
            replyText = "⚡ *Query Help: /what*\n\nPlease specify a stock symbol: e.g. `/what praj` or `/what ongc`";
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          case IntentType.STOCK_WHEN_PROMPT:
            replyText = "⏱️ *Query Help: /when*\n\nPlease specify a stock symbol: e.g. `/when wabag` or `/when ongc`";
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          case IntentType.SCHEME_LOOKUP:
            replyText = renderSchemesCard(snapshot, isStale);
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          case IntentType.PERFORMANCE_LOOKUP:
            replyText = renderPerformanceCard(snapshot, isStale);
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          case IntentType.BENCHMARK_LOOKUP:
            replyText = renderBenchmarkCard(snapshot, isStale);
            replyMarkup = getBackAndSwitchKeyboard(currentScheme);
            break;
          default:
            replyText = renderStartMenu();
            replyMarkup = getStartInlineKeyboard(currentScheme);
            break;
        }
      }

      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, replyText, { requestId, replyMarkup }));
      }
      return new Response("OK", { status: 200 });
    }

    // D2. WORKFLOW PATH (Event-driven repository_dispatch → 04-telegram-query.yml)
    if (resolved.executionPath === ExecutionPath.WORKFLOW) {
      // 1. Send immediate acknowledgement
      const ackMessage =
        `🔎 *Researching your question...*\n\n` +
        `*Request ID:* \`${requestId}\`\n` +
        `*Query:* _${rawText}_\n\n` +
        `I'll send the synthesized analysis directly to this chat when processing completes.`;

      if (botToken) {
        ctx.waitUntil(sendMessage(botToken, chatId, ackMessage, { requestId }));
      }

      // 2. Dispatch repository_dispatch passing authorized schemes for AI context isolation
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
        scheme_id: currentScheme,
        authorized_schemes: auth.allowedSchemes,
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

    // D3. RESEARCH PATH (/research <question>)
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
        scheme_id: currentScheme,
        authorized_schemes: auth.allowedSchemes,
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
