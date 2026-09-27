/**
 * Telegram Bot API Client for Cloudflare Worker.
 * Handles sendMessage with automatic Markdown fallback, webhook management, and commands.
 */
import { safeLog } from "./utils.js";

const TELEGRAM_API_BASE = "https://api.telegram.org";

export const BOT_COMMANDS = [
  { command: "start", description: "Terminal main menu & shortcuts" },
  { command: "help", description: "Command guide & query examples" },
  { command: "stock", description: "Stock intelligence card (/stock <SYM>)" },
  { command: "setups", description: "Today's qualified setups" },
  { command: "watchlist", description: "Monitored watchlist stocks" },
  { command: "research", description: "Deep policy research (/research <Q>)" },
];

/**
 * Send a message to Telegram with automatic Markdown fallback on parsing errors.
 */
export async function sendMessage(botToken, chatId, text, options = {}) {
  if (!botToken || !chatId || !text) {
    safeLog("error", "telegram_send_invalid_params", { hasToken: !!botToken, chatId });
    return { success: false, error: "Missing botToken, chatId, or text" };
  }

  const url = `${TELEGRAM_API_BASE}/bot${botToken}/sendMessage`;
  const parseMode = options.parseMode !== undefined ? options.parseMode : "Markdown";

  const payload = {
    chat_id: String(chatId),
    text: text.slice(0, 4000), // Telegram max message limit safe truncation
    ...(parseMode ? { parse_mode: parseMode } : {}),
    ...(options.replyMarkup ? { reply_markup: options.replyMarkup } : {}),
  };

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await resp.json();

    if (resp.ok && data.ok) {
      safeLog("info", "telegram_send_success", {
        chatId: String(chatId),
        requestId: options.requestId,
        len: text.length,
      });
      return { success: true, messageId: data.result?.message_id };
    }

    // If Markdown parse error (HTTP 400 with "can't parse entities"), retry with plain text
    const description = data.description || "";
    if (resp.status === 400 && parseMode && description.toLowerCase().includes("parse")) {
      safeLog("warn", "telegram_send_markdown_fallback", {
        chatId: String(chatId),
        requestId: options.requestId,
        error: description,
      });

      const fallbackPayload = {
        chat_id: String(chatId),
        text: text.slice(0, 4000),
        ...(options.replyMarkup ? { reply_markup: options.replyMarkup } : {}),
      };

      const retryResp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fallbackPayload),
      });
      const retryData = await retryResp.json();

      if (retryResp.ok && retryData.ok) {
        return { success: true, messageId: retryData.result?.message_id };
      }
    }

    safeLog("error", "telegram_send_failed", {
      chatId: String(chatId),
      requestId: options.requestId,
      status: resp.status,
      description,
    });
    return { success: false, status: resp.status, error: description };
  } catch (err) {
    safeLog("error", "telegram_network_error", {
      chatId: String(chatId),
      requestId: options.requestId,
      error: err.message,
    });
    return { success: false, error: err.message };
  }
}

/**
 * Answer callback query to dismiss loading indicator on Telegram client.
 */
export async function answerCallbackQuery(botToken, callbackQueryId) {
  if (!botToken || !callbackQueryId) return false;
  try {
    const url = `${TELEGRAM_API_BASE}/bot${botToken}/answerCallbackQuery`;
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ callback_query_id: callbackQueryId }),
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Configure Telegram Webhook with secret token.
 */
export async function setWebhook(botToken, webhookUrl, secretToken) {
  const url = `${TELEGRAM_API_BASE}/bot${botToken}/setWebhook`;
  const body = {
    url: webhookUrl,
    allowed_updates: ["message", "callback_query"],
    drop_pending_updates: false,
    ...(secretToken ? { secret_token: secretToken } : {}),
  };

  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return resp.json();
}

/**
 * Delete configured Telegram Webhook.
 */
export async function deleteWebhook(botToken, dropPendingUpdates = false) {
  const url = `${TELEGRAM_API_BASE}/bot${botToken}/deleteWebhook`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ drop_pending_updates: dropPendingUpdates }),
  });
  return resp.json();
}

/**
 * Register bot commands menu with Telegram.
 */
export async function setMyCommands(botToken, commands = BOT_COMMANDS) {
  const url = `${TELEGRAM_API_BASE}/bot${botToken}/setMyCommands`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ commands }),
  });
  return resp.json();
}

/**
 * Fetch current webhook configuration status from Telegram.
 */
export async function getWebhookInfo(botToken) {
  const url = `${TELEGRAM_API_BASE}/bot${botToken}/getWebhookInfo`;
  const resp = await fetch(url);
  return resp.json();
}
