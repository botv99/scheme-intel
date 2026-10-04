/**
 * User Identity and Profile Management for Scheme Intel.
 * Maps Telegram users to Supabase entities and tracks status (LOCKED / ACTIVE).
 */

import { getSupabaseClient } from "./supabase.js";
import { safeLog } from "./utils.js";

export const UserStatus = {
  LOCKED: "LOCKED",
  ACTIVE: "ACTIVE",
  SUSPENDED: "SUSPENDED",
};

/**
 * Record an immutable audit log entry in Supabase.
 */
export async function recordAuditEvent(env, { userId = null, telegramUserId, eventType, schemeId = null, metadata = {} }) {
  if (!telegramUserId || !eventType) return;
  const client = getSupabaseClient(env);
  try {
    await client.from("audit_events").insert({
      user_id: userId,
      telegram_user_id: String(telegramUserId),
      event_type: eventType,
      scheme_id: schemeId,
      metadata,
      created_at: new Date().toISOString(),
    });
  } catch (err) {
    safeLog("error", "audit_event_record_failed", { eventType, error: err.message });
  }
}

/**
 * Retrieve or create a Telegram user record in Supabase.
 * New users default to LOCKED status.
 */
export async function getOrCreateUser(env, { telegramUserId, telegramChatId = null, username = null, firstName = null }) {
  if (!telegramUserId) {
    throw new Error("Missing telegramUserId");
  }

  const client = getSupabaseClient(env);
  const strUserId = String(telegramUserId);
  const nowIso = new Date().toISOString();

  // 1. Check existing user
  const { data: existing, error } = await client
    .from("users")
    .select("*")
    .eq("telegram_user_id", strUserId)
    .maybeSingle();

  if (error && error.message) {
    safeLog("warn", "user_lookup_error", { telegramUserId: strUserId, error: error.message });
  }

  if (existing) {
    // Update profile metadata & last_seen_at
    const updates = {
      last_seen_at: nowIso,
      updated_at: nowIso,
    };
    if (telegramChatId) updates.telegram_chat_id = String(telegramChatId);
    if (username) updates.username = username;
    if (firstName) updates.first_name = firstName;

    const { data: updated } = await client
      .from("users")
      .update(updates)
      .eq("id", existing.id)
      .maybeSingle();

    return updated || { ...existing, ...updates };
  }

  // 2. Create new user with LOCKED status
  const newUser = {
    telegram_user_id: strUserId,
    telegram_chat_id: telegramChatId ? String(telegramChatId) : null,
    username: username || null,
    first_name: firstName || null,
    status: UserStatus.LOCKED,
    last_selected_scheme: "gobardhan",
    created_at: nowIso,
    updated_at: nowIso,
    last_seen_at: nowIso,
  };

  const { data: created, error: insertErr } = await client
    .from("users")
    .insert(newUser)
    .single();

  if (insertErr) {
    safeLog("error", "user_create_failed", { telegramUserId: strUserId, error: insertErr.message || insertErr });
    return newUser;
  }

  const finalUser = created || newUser;
  await recordAuditEvent(env, {
    userId: finalUser.id,
    telegramUserId: strUserId,
    eventType: "USER_CREATED",
    metadata: { username, firstName },
  });

  safeLog("info", "new_user_registered", { userId: finalUser.id, telegramUserId: strUserId });
  return finalUser;
}

/**
 * Fetch user by Telegram ID.
 */
export async function getUserByTelegramId(env, telegramUserId) {
  if (!telegramUserId) return null;
  const client = getSupabaseClient(env);
  const { data } = await client
    .from("users")
    .select("*")
    .eq("telegram_user_id", String(telegramUserId))
    .maybeSingle();
  return data;
}

/**
 * Update user status.
 */
export async function updateUserStatus(env, userId, status) {
  const client = getSupabaseClient(env);
  const { data } = await client
    .from("users")
    .update({ status, updated_at: new Date().toISOString() })
    .eq("id", userId)
    .maybeSingle();
  return data;
}

/**
 * Persist user's last selected active scheme.
 */
export async function setUserSelectedScheme(env, userId, schemeId) {
  if (!userId || !schemeId) return;
  const client = getSupabaseClient(env);
  await client
    .from("users")
    .update({ last_selected_scheme: schemeId.trim().toLowerCase(), updated_at: new Date().toISOString() })
    .eq("id", userId);
}
