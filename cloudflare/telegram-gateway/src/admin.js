/**
 * Administrator Management Interface for Scheme Intel.
 * Provides privileged commands: key generation, user management, entitlement grant/revocation.
 */

import { getSupabaseClient } from "./supabase.js";
import { generateAccessKey, revokeAccessKey } from "./keys.js";
import { grantEntitlement, revokeEntitlement, getAllSchemes } from "./entitlements.js";
import { getUserByTelegramId, recordAuditEvent } from "./users.js";
import { isPlatformAdmin } from "./authorization.js";
import { safeLog } from "./utils.js";

/**
 * Handle /admin commands securely.
 */
export async function handleAdminCommand(text, userId, chatId, env) {
  const isAdmin = isPlatformAdmin(userId, chatId, env);
  if (!isAdmin) {
    safeLog("warn", "admin_command_unauthorized_attempt", { userId, chatId, text });
    return {
      replyText: "🔒 *Access Restricted*\n\nYou do not have administrator privileges.",
      replyMarkup: null,
    };
  }

  const parts = (text || "").trim().split(/\s+/);
  const subCmd = (parts[1] || "").toLowerCase();

  const client = getSupabaseClient(env);

  // 1. /admin
  if (!subCmd || subCmd === "help") {
    return {
      replyText:
        `👑 *SCHEME INTEL — ADMIN CONSOLE*\n\n` +
        `Available administrator commands:\n\n` +
        `• \`/admin users\` — View recent users & status\n` +
        `• \`/admin keys\` — View active authorization keys\n` +
        `• \`/admin payments\` — View recent orders & payments\n` +
        `• \`/admin schemes\` — List registered schemes\n` +
        `• \`/admin genkey <scheme> [days] [max_uses]\` — Generate secure access key\n` +
        `• \`/admin revoke <key_prefix>\` — Revoke access key\n` +
        `• \`/admin grant <user_id> <scheme> [days]\` — Grant scheme to Telegram user\n` +
        `• \`/admin revokegrant <user_id> <scheme>\` — Revoke scheme from Telegram user`,
      replyMarkup: null,
    };
  }

  // 2. /admin users
  if (subCmd === "users") {
    const { data: users, error } = await client
      .from("users")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(10);

    if (error || !users || users.length === 0) {
      return { replyText: "👥 *Admin: Users*\n\nNo user records found in database.", replyMarkup: null };
    }

    const lines = users.map((u) => {
      const name = u.username ? `@${u.username}` : (u.first_name || "User");
      const statusIcon = u.status === "ACTIVE" ? "🟢" : "🔒";
      return `${statusIcon} \`${u.telegram_user_id}\` (${name}) — *${u.status}*`;
    });

    return {
      replyText: `👥 *Admin: Recent Users (${users.length})*\n\n${lines.join("\n")}`,
      replyMarkup: null,
    };
  }

  // 3. /admin keys
  if (subCmd === "keys") {
    const { data: keys, error } = await client
      .from("access_keys")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(10);

    if (error || !keys || keys.length === 0) {
      return { replyText: "🔑 *Admin: Keys*\n\nNo access keys found in database.", replyMarkup: null };
    }

    const lines = keys.map((k) => {
      const statusIcon = k.status === "ACTIVE" ? "🟢" : "⚪";
      return `${statusIcon} \`${k.key_prefix}-****\` — Uses: ${k.used_count}/${k.max_uses} — Status: *${k.status}*`;
    });

    return {
      replyText: `🔑 *Admin: Access Keys (${keys.length})*\n\n${lines.join("\n")}`,
      replyMarkup: null,
    };
  }

  // 4. /admin payments
  if (subCmd === "payments") {
    const { data: orders, error } = await client
      .from("orders")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(10);

    if (error || !orders || orders.length === 0) {
      return { replyText: "💳 *Admin: Payments*\n\nNo payment orders found.", replyMarkup: null };
    }

    const lines = orders.map((o) => {
      const statusIcon = o.status === "PAID" ? "✅" : (o.status === "PENDING" ? "⏳" : "❌");
      return `${statusIcon} \`${o.order_code}\` — ₹${o.amount} — *${o.status}* (${o.provider})`;
    });

    return {
      replyText: `💳 *Admin: Recent Orders (${orders.length})*\n\n${lines.join("\n")}`,
      replyMarkup: null,
    };
  }

  // 5. /admin schemes
  if (subCmd === "schemes") {
    const schemes = await getAllSchemes(env);
    const lines = schemes.map((s) => `• *${s.name}* (\`${s.scheme_id}\`) — Status: ${s.status}`);
    return {
      replyText: `📋 *Admin: Configured Schemes*\n\n${lines.join("\n")}`,
      replyMarkup: null,
    };
  }

  // 6. /admin genkey <scheme_id> [days] [max_uses]
  if (subCmd === "genkey") {
    const schemeId = (parts[2] || "gobardhan").trim().toLowerCase();
    const days = parseInt(parts[3], 10) || 365;
    const maxUses = parseInt(parts[4], 10) || 1;

    const prefix = schemeId === "all" ? "ALL" : schemeId.slice(0, 3).toUpperCase();
    const schemeIds = schemeId === "all" ? ["gobardhan", "samudra_manthan"] : [schemeId];

    try {
      const generated = await generateAccessKey(env, {
        prefix,
        schemeIds,
        durationDays: days,
        maxUses,
        createdBy: `admin_${userId}`,
      });

      return {
        replyText:
          `🔑 *NEW AUTHORIZATION KEY GENERATED*\n\n` +
          `Key: \`${generated.plaintextKey}\`\n\n` +
          `• *Schemes:* ${schemeIds.join(", ")}\n` +
          `• *Validity:* ${days} days\n` +
          `• *Max Uses:* ${maxUses}\n` +
          `• *Prefix:* \`${generated.keyPrefix}\`\n\n` +
          `⚠️ _Store this key safely. The plaintext key is never displayed again._`,
        replyMarkup: null,
      };
    } catch (err) {
      return { replyText: `❌ Failed to generate key: ${err.message}`, replyMarkup: null };
    }
  }

  // 7. /admin revoke <key_prefix>
  if (subCmd === "revoke") {
    const keyPrefix = (parts[2] || "").trim().toUpperCase();
    if (!keyPrefix) {
      return { replyText: "⚠️ Usage: `/admin revoke <KEY_PREFIX>` (e.g. `/admin revoke GOB-7K4P`)", replyMarkup: null };
    }
    const success = await revokeAccessKey(env, keyPrefix);
    return {
      replyText: success ? `✅ Key \`${keyPrefix}\` has been revoked.` : `❌ Key \`${keyPrefix}\` not found or could not be revoked.`,
      replyMarkup: null,
    };
  }

  // 8. /admin grant <telegram_user_id> <scheme_id> [days]
  if (subCmd === "grant") {
    const targetUserId = parts[2];
    const schemeId = (parts[3] || "gobardhan").trim().toLowerCase();
    const days = parseInt(parts[4], 10) || 365;

    if (!targetUserId) {
      return { replyText: "⚠️ Usage: `/admin grant <TELEGRAM_USER_ID> <SCHEME_ID> [DAYS]`", replyMarkup: null };
    }

    const user = await getUserByTelegramId(env, targetUserId);
    if (!user) {
      return { replyText: `❌ User with Telegram ID \`${targetUserId}\` not found in database.`, replyMarkup: null };
    }

    try {
      const granted = await grantEntitlement(env, {
        userId: user.id,
        schemeId,
        source: "ADMIN",
        durationDays: days,
        telegramUserId: targetUserId,
      });

      return {
        replyText:
          `✅ *ENTITLEMENT GRANTED*\n\n` +
          `• User: \`${targetUserId}\`\n` +
          `• Scheme: *${schemeId}*\n` +
          `• Duration: ${days} days\n` +
          `• Expiry: \`${granted.expires_at || "Ongoing"}\``,
        replyMarkup: null,
      };
    } catch (err) {
      return { replyText: `❌ Error granting entitlement: ${err.message}`, replyMarkup: null };
    }
  }

  // 9. /admin revokegrant <telegram_user_id> <scheme_id>
  if (subCmd === "revokegrant") {
    const targetUserId = parts[2];
    const schemeId = (parts[3] || "gobardhan").trim().toLowerCase();

    if (!targetUserId) {
      return { replyText: "⚠️ Usage: `/admin revokegrant <TELEGRAM_USER_ID> <SCHEME_ID>`", replyMarkup: null };
    }

    const user = await getUserByTelegramId(env, targetUserId);
    if (!user) {
      return { replyText: `❌ User with Telegram ID \`${targetUserId}\` not found in database.`, replyMarkup: null };
    }

    const success = await revokeEntitlement(env, {
      userId: user.id,
      schemeId,
      reason: `admin_revoke_by_${userId}`,
      telegramUserId: targetUserId,
    });

    return {
      replyText: success
        ? `✅ Revoked scheme *${schemeId}* from user \`${targetUserId}\`.`
        : `❌ Failed to revoke scheme from user.`,
      replyMarkup: null,
    };
  }

  return {
    replyText: `⚠️ Unknown admin command: \`${subCmd}\`\n\nUse \`/admin help\` for options.`,
    replyMarkup: null,
  };
}
