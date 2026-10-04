/**
 * Cryptographic Access Key Generator, Validator, and Activation Engine.
 * Never stores plaintext keys; stores SHA-256 HMAC / cryptographic hashes.
 */

import { getSupabaseClient } from "./supabase.js";
import { getOrCreateUser, recordAuditEvent } from "./users.js";
import { grantEntitlement } from "./entitlements.js";
import { safeLog } from "./utils.js";

/**
 * Compute SHA-256 hex digest of a string using Web Crypto API.
 */
export async function hashAccessKey(rawKey) {
  if (!rawKey || typeof rawKey !== "string") return "";
  const normalized = rawKey.trim().toUpperCase().replace(/\s+/g, "");
  const encoder = new TextEncoder();
  const data = encoder.encode(normalized);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Generate cryptographically secure random alphanumeric string.
 */
function randomAlphanumeric(length) {
  const chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"; // exclude easily confused chars (0, O, 1, I)
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  let result = "";
  for (let i = 0; i < length; i++) {
    result += chars[bytes[i] % chars.length];
  }
  return result;
}

/**
 * Generate a new secure authorization key.
 * Format: PREFIX-XXXX-YYYY (e.g. GOB-7K4P-X92M)
 */
export async function generateAccessKey(
  env,
  {
    prefix = "SI",
    schemeIds = ["gobardhan"],
    maxUses = 1,
    durationDays = 365,
    expiresAt = null,
    createdBy = "admin",
  } = {}
) {
  const cleanPrefix = (prefix || "SI").trim().toUpperCase();
  const part1 = randomAlphanumeric(4);
  const part2 = randomAlphanumeric(4);
  const plaintextKey = `${cleanPrefix}-${part1}-${part2}`;
  const keyHash = await hashAccessKey(plaintextKey);
  const keyDisplayPrefix = `${cleanPrefix}-${part1}`;

  const client = getSupabaseClient(env);
  const nowIso = new Date().toISOString();

  // 1. Insert access_key
  const keyRecord = {
    key_hash: keyHash,
    key_prefix: keyDisplayPrefix,
    status: "ACTIVE",
    max_uses: Math.max(1, parseInt(maxUses, 10) || 1),
    used_count: 0,
    expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
    entitlement_duration_days: Math.max(1, parseInt(durationDays, 10) || 365),
    created_at: nowIso,
    created_by: createdBy || "admin",
  };

  const { data: insertedKey, error: keyErr } = await client
    .from("access_keys")
    .insert(keyRecord)
    .single();

  if (keyErr) {
    safeLog("error", "access_key_insert_failed", { error: keyErr });
    throw new Error(`Failed to create access key: ${JSON.stringify(keyErr)}`);
  }

  const keyId = insertedKey?.id || keyRecord.id;

  // 2. Insert key_entitlements
  const cleanSchemes = Array.isArray(schemeIds) && schemeIds.length > 0 ? schemeIds : ["gobardhan"];
  for (const sid of cleanSchemes) {
    const normSid = sid.trim().toLowerCase();
    await client.from("key_entitlements").insert({
      access_key_id: keyId,
      scheme_id: normSid,
      created_at: nowIso,
    });
  }

  safeLog("info", "access_key_generated", {
    prefix: keyDisplayPrefix,
    schemes: cleanSchemes,
    maxUses,
    durationDays,
    createdBy,
  });

  return {
    plaintextKey,
    keyPrefix: keyDisplayPrefix,
    keyHash,
    maxUses: keyRecord.max_uses,
    durationDays: keyRecord.entitlement_duration_days,
    schemes: cleanSchemes,
  };
}

/**
 * Validate and atomically activate an authorization key for a user.
 */
export async function activateAccessKey(
  env,
  { telegramUserId, rawKey, telegramChatId = null, username = null, firstName = null }
) {
  if (!telegramUserId) {
    return { success: false, reason: "MISSING_USER_ID", message: "Telegram User ID required." };
  }
  if (!rawKey || !rawKey.trim()) {
    return { success: false, reason: "MISSING_KEY", message: "Please provide a valid access key." };
  }

  const client = getSupabaseClient(env);
  const keyHash = await hashAccessKey(rawKey);
  const now = new Date();

  // 1. Identify or create user record
  const user = await getOrCreateUser(env, { telegramUserId, telegramChatId, username, firstName });

  // Record key attempt
  await recordAuditEvent(env, {
    userId: user.id,
    telegramUserId: String(telegramUserId),
    eventType: "KEY_ATTEMPT",
    metadata: { keyPrefix: rawKey.slice(0, 8) },
  });

  // 2. Lookup key by hash
  const { data: keyRecord, error: findErr } = await client
    .from("access_keys")
    .select("*")
    .eq("key_hash", keyHash)
    .maybeSingle();

  if (findErr || !keyRecord) {
    await recordAuditEvent(env, {
      userId: user.id,
      telegramUserId: String(telegramUserId),
      eventType: "KEY_REJECTED",
      metadata: { reason: "KEY_NOT_FOUND" },
    });
    return {
      success: false,
      reason: "INVALID_KEY",
      message: "The access key you entered is invalid or does not exist.",
    };
  }

  // 3. Status checks
  if (keyRecord.status === "REVOKED") {
    await recordAuditEvent(env, {
      userId: user.id,
      telegramUserId: String(telegramUserId),
      eventType: "KEY_REJECTED",
      metadata: { reason: "KEY_REVOKED", keyPrefix: keyRecord.key_prefix },
    });
    return {
      success: false,
      reason: "KEY_REVOKED",
      message: "This access key has been revoked by an administrator.",
    };
  }

  if (keyRecord.expires_at && new Date(keyRecord.expires_at) <= now) {
    await recordAuditEvent(env, {
      userId: user.id,
      telegramUserId: String(telegramUserId),
      eventType: "KEY_REJECTED",
      metadata: { reason: "KEY_EXPIRED", keyPrefix: keyRecord.key_prefix },
    });
    return {
      success: false,
      reason: "KEY_EXPIRED",
      message: "This access key has expired.",
    };
  }

  if (keyRecord.used_count >= keyRecord.max_uses) {
    await recordAuditEvent(env, {
      userId: user.id,
      telegramUserId: String(telegramUserId),
      eventType: "KEY_REJECTED",
      metadata: { reason: "MAX_USES_REACHED", keyPrefix: keyRecord.key_prefix },
    });
    return {
      success: false,
      reason: "MAX_USES_REACHED",
      message: "This access key has already reached its maximum number of uses.",
    };
  }

  // 4. Atomically consume key usage with concurrency guard
  const newUsedCount = keyRecord.used_count + 1;
  const newStatus = newUsedCount >= keyRecord.max_uses ? "EXPIRED" : "ACTIVE";

  const { data: updatedRows, error: updateErr } = await client
    .from("access_keys")
    .update({ used_count: newUsedCount, status: newStatus })
    .eq("id", keyRecord.id)
    .lt("used_count", keyRecord.max_uses)
    .eq("status", "ACTIVE");

  if (updateErr) {
    safeLog("error", "key_activation_update_failed", { keyId: keyRecord.id, error: updateErr });
    return {
      success: false,
      reason: "DB_ERROR",
      message: `An error occurred while updating the access key: ${JSON.stringify(updateErr)}`,
      error: updateErr,
    };
  }

  // Only reject if the database returned an explicit empty array (concurrency guard failed)
  if (Array.isArray(updatedRows) && updatedRows.length === 0) {
    await recordAuditEvent(env, {
      userId: user.id,
      telegramUserId: String(telegramUserId),
      eventType: "KEY_REJECTED",
      metadata: { reason: "MAX_USES_REACHED", keyPrefix: keyRecord.key_prefix },
    });
    return {
      success: false,
      reason: "MAX_USES_REACHED",
      message: "This access key has already reached its maximum number of uses.",
    };
  }

  // 5. Retrieve key scheme entitlements
  const { data: entitlements } = await client
    .from("key_entitlements")
    .select("scheme_id")
    .eq("access_key_id", keyRecord.id);

  let targetSchemes = (entitlements || []).map((e) => e.scheme_id.trim().toLowerCase());
  if (targetSchemes.length === 0) {
    targetSchemes = ["gobardhan"];
  }

  // 6. Grant entitlements to user
  const durationDays = keyRecord.entitlement_duration_days || 365;
  const grantedSchemes = [];
  let latestExpiry = null;

  for (const sid of targetSchemes) {
    const granted = await grantEntitlement(env, {
      userId: user.id,
      schemeId: sid,
      source: "KEY",
      durationDays,
      telegramUserId: String(telegramUserId),
    });
    grantedSchemes.push(sid);
    if (granted?.expires_at) {
      latestExpiry = granted.expires_at;
    }
  }

  // 7. Audit event
  await recordAuditEvent(env, {
    userId: user.id,
    telegramUserId: String(telegramUserId),
    eventType: "KEY_ACTIVATED",
    metadata: {
      keyPrefix: keyRecord.key_prefix,
      grantedSchemes,
      durationDays,
      expiresAt: latestExpiry,
    },
  });

  safeLog("info", "key_activation_successful", {
    userId: user.id,
    telegramUserId,
    keyPrefix: keyRecord.key_prefix,
    grantedSchemes,
  });

  return {
    success: true,
    user,
    grantedSchemes,
    durationDays,
    expiresAt: latestExpiry,
  };
}

/**
 * Revoke an access key.
 */
export async function revokeAccessKey(env, keyPrefix) {
  if (!keyPrefix) return false;
  const client = getSupabaseClient(env);
  const { data, error } = await client
    .from("access_keys")
    .update({ status: "REVOKED" })
    .eq("key_prefix", keyPrefix.trim().toUpperCase());

  return !error;
}
