/**
 * Entitlement Service for Scheme Intel.
 * Manages user-scheme entitlements, validation, expiry calculations, and revocation.
 */

import { getSupabaseClient } from "./supabase.js";
import { recordAuditEvent, updateUserStatus, UserStatus } from "./users.js";
import { safeLog } from "./utils.js";

export const EntitlementStatus = {
  ACTIVE: "ACTIVE",
  EXPIRED: "EXPIRED",
  REVOKED: "REVOKED",
};

export const EntitlementSource = {
  KEY: "KEY",
  PAYMENT: "PAYMENT",
  ADMIN: "ADMIN",
};

/**
 * Fetch all registered schemes.
 */
export async function getAllSchemes(env) {
  const client = getSupabaseClient(env);
  const { data, error } = await client.from("schemes").select("*").order("name", { ascending: true });
  if (error) {
    safeLog("error", "fetch_schemes_error", { error });
    return [
      { scheme_id: "gobardhan", name: "GOBARdhan", status: "ACTIVE" },
      { scheme_id: "samudra_manthan", name: "Samudra Manthan", status: "ACTIVE" },
    ];
  }
  return data || [];
}

/**
 * Get active, unexpired scheme entitlements for a user.
 */
export async function getUserEntitlements(env, userId) {
  if (!userId) return [];
  const client = getSupabaseClient(env);
  const now = new Date();

  const { data, error } = await client
    .from("user_scheme_entitlements")
    .select("*")
    .eq("user_id", userId);

  if (error) {
    safeLog("error", "get_user_entitlements_failed", { userId, error: error.message || error });
    return [];
  }

  const active = [];
  for (const ent of data || []) {
    if (ent.status !== EntitlementStatus.ACTIVE) {
      continue;
    }
    if (ent.expires_at) {
      const expDate = new Date(ent.expires_at);
      if (expDate <= now) {
        // Expired entitlement
        continue;
      }
    }
    active.push({
      ...ent,
      scheme_id: ent.scheme_id.trim().toLowerCase(),
    });
  }

  return active;
}

/**
 * Check if a specific scheme is authorized in the user's entitlements list.
 */
export function isSchemeAuthorized(entitlements, schemeId) {
  if (!schemeId || !Array.isArray(entitlements)) return false;
  const target = schemeId.trim().toLowerCase();
  return entitlements.some((e) => e.scheme_id === target);
}

/**
 * Grant or extend a scheme entitlement for a user.
 */
export async function grantEntitlement(
  env,
  { userId, schemeId, source = EntitlementSource.KEY, durationDays = 365, expiresAt = null, telegramUserId = null }
) {
  if (!userId || !schemeId) {
    throw new Error("Missing userId or schemeId");
  }

  const client = getSupabaseClient(env);
  const normSchemeId = schemeId.trim().toLowerCase();
  const now = new Date();

  // Check if user already has an entitlement for this scheme
  const { data: existing } = await client
    .from("user_scheme_entitlements")
    .select("*")
    .eq("user_id", userId)
    .eq("scheme_id", normSchemeId)
    .maybeSingle();

  let finalExpiresAt = null;
  if (expiresAt) {
    finalExpiresAt = new Date(expiresAt).toISOString();
  } else if (durationDays !== null && durationDays !== undefined) {
    let baseTime = now.getTime();
    if (existing && existing.expires_at) {
      const currentExp = new Date(existing.expires_at).getTime();
      if (!isNaN(currentExp)) {
        // Renewal support: Start extension from the greater of now or existing expiry
        baseTime = Math.max(baseTime, currentExp);
      }
    }
    finalExpiresAt = new Date(baseTime + durationDays * 86400 * 1000).toISOString();
  }

  const payload = {
    user_id: userId,
    scheme_id: normSchemeId,
    source,
    status: EntitlementStatus.ACTIVE,
    starts_at: existing?.starts_at || now.toISOString(),
    expires_at: finalExpiresAt,
    updated_at: now.toISOString(),
  };

  const { data: saved, error } = await client
    .from("user_scheme_entitlements")
    .upsert(payload, { onConflict: "user_id,scheme_id" })
    .single();

  if (error) {
    safeLog("error", "grant_entitlement_failed", { userId, schemeId: normSchemeId, error });
    throw new Error(`Failed to grant entitlement: ${JSON.stringify(error)}`);
  }

  // Ensure user account is ACTIVE
  await updateUserStatus(env, userId, UserStatus.ACTIVE);

  // Log audit event
  await recordAuditEvent(env, {
    userId,
    telegramUserId: telegramUserId || "unknown",
    eventType: "ENTITLEMENT_GRANTED",
    schemeId: normSchemeId,
    metadata: { source, durationDays, expiresAt: finalExpiresAt },
  });

  safeLog("info", "entitlement_granted", { userId, schemeId: normSchemeId, expiresAt: finalExpiresAt, source });
  return saved || payload;
}

/**
 * Revoke a scheme entitlement for a user.
 */
export async function revokeEntitlement(
  env,
  { userId, schemeId, reason = "admin_action", telegramUserId = null }
) {
  if (!userId || !schemeId) return false;
  const client = getSupabaseClient(env);
  const normSchemeId = schemeId.trim().toLowerCase();
  const nowIso = new Date().toISOString();

  const { error } = await client
    .from("user_scheme_entitlements")
    .update({ status: EntitlementStatus.REVOKED, updated_at: nowIso })
    .eq("user_id", userId)
    .eq("scheme_id", normSchemeId);

  if (error) {
    safeLog("error", "revoke_entitlement_failed", { userId, schemeId: normSchemeId, error });
    return false;
  }

  await recordAuditEvent(env, {
    userId,
    telegramUserId: telegramUserId || "unknown",
    eventType: "ENTITLEMENT_REVOKED",
    schemeId: normSchemeId,
    metadata: { reason },
  });

  safeLog("info", "entitlement_revoked", { userId, schemeId: normSchemeId, reason });
  return true;
}
