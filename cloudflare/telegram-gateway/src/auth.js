/**
 * Webhook Authentication & Access Control for Cloudflare Worker.
 */

/**
 * Validate Telegram's X-Telegram-Bot-Api-Secret-Token header.
 * Official Telegram documentation: https://core.telegram.org/bots/api#setwebhook
 */
export function validateWebhookSecret(request, expectedSecret) {
  if (!expectedSecret || typeof expectedSecret !== "string" || !expectedSecret.trim()) {
    // If no secret configured in Worker environment, pass validation (open mode)
    return true;
  }

  const incomingSecret = request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "";
  // Constant-time length and character check
  if (incomingSecret.length !== expectedSecret.length) {
    return false;
  }

  let match = 0;
  for (let i = 0; i < expectedSecret.length; i++) {
    match |= incomingSecret.charCodeAt(i) ^ expectedSecret.charCodeAt(i);
  }
  return match === 0;
}

/**
 * Check if the user ID or chat ID is authorized based on environment configuration.
 * If no whitelist is specified, all users can interact.
 */
export function isAuthorized(userId, chatId, allowedUsersStr = "", allowedChatsStr = "") {
  const allowedUsers = (allowedUsersStr || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  const allowedChats = (allowedChatsStr || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  // If no restrictions are configured, allow all
  if (allowedUsers.length === 0 && allowedChats.length === 0) {
    return true;
  }

  const userMatch = userId ? allowedUsers.includes(String(userId)) : false;
  const chatMatch = chatId ? allowedChats.includes(String(chatId)) : false;

  return userMatch || chatMatch;
}
