/**
 * Centralized Authorization & Server-Side Entitlement Gate.
 * Enforces scheme-level isolation, user locking, and snapshot filtering.
 */

import { getOrCreateUser } from "./users.js";
import { getUserEntitlements, isSchemeAuthorized } from "./entitlements.js";
import { GLOBAL_STOCK_ALIASES, resolveStock } from "./resolver.js";
import { safeLog } from "./utils.js";

/**
 * Check if user is configured as platform administrator in environment.
 */
export function isPlatformAdmin(userId, chatId, env = {}) {
  const adminIdsStr = env.ADMIN_USER_IDS || env.PLATFORM_ADMIN_IDS || "";
  if (!adminIdsStr.trim()) return false;

  const adminIds = adminIdsStr
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  const uidMatch = userId ? adminIds.includes(String(userId)) : false;
  const cidMatch = chatId ? adminIds.includes(String(chatId)) : false;
  return uidMatch || cidMatch;
}

/**
 * Resolve full authorization profile for a Telegram user from database entitlements.
 */
export async function getTelegramAuth(env, { userId, chatId = null, username = null, firstName = null }) {
  const strUserId = String(userId || "");
  const isAdmin = isPlatformAdmin(strUserId, chatId, env);

  // Get or register user in Supabase
  const user = await getOrCreateUser(env, {
    telegramUserId: strUserId,
    telegramChatId: chatId,
    username,
    firstName,
  });

  // Fetch active scheme entitlements from database
  const entitlements = await getUserEntitlements(env, user.id);

  let allowedSchemes = [];
  if (isAdmin) {
    // Admins have access to all schemes
    allowedSchemes = ["gobardhan", "samudra_manthan", "green_hydrogen", "solar_mission"];
  } else {
    allowedSchemes = entitlements.map((e) => e.scheme_id.trim().toLowerCase());
  }

  const isAuthorized = isAdmin || allowedSchemes.length > 0;
  const isLocked = !isAuthorized;

  // Active scheme determination: must be one of allowedSchemes
  let activeScheme = user.last_selected_scheme || "gobardhan";
  if (!allowedSchemes.includes(activeScheme) && allowedSchemes.length > 0) {
    activeScheme = allowedSchemes[0];
  }

  return {
    user,
    isAdmin,
    isAuthorized,
    isLocked,
    allowedSchemes,
    entitlements,
    activeScheme,
  };
}

/**
 * Check whether a target scheme is accessible for this user.
 */
export function checkSchemeAccess(authContext, targetSchemeId) {
  if (!targetSchemeId) return false;
  if (authContext.isAdmin) return true;
  const normTarget = targetSchemeId.trim().toLowerCase();
  return authContext.allowedSchemes.includes(normTarget);
}

/**
 * Determine the scheme that a stock symbol belongs to.
 */
export function getStockScheme(symbol, snapshot = null) {
  if (!symbol) return null;
  const normSym = symbol.trim().toUpperCase();

  // 1. Check from snapshot if available
  if (snapshot && snapshot.companies) {
    for (const comp of Object.values(snapshot.companies)) {
      if (
        comp.symbol?.toUpperCase() === normSym ||
        comp.short_symbol?.toUpperCase() === normSym ||
        comp.name?.toUpperCase() === normSym
      ) {
        if (comp.scheme_id) return comp.scheme_id.toLowerCase();
      }
    }
  }

  // 2. Check from global aliases table
  const alias = GLOBAL_STOCK_ALIASES[normSym] || resolveStock(normSym);
  if (alias && alias.scheme) {
    return alias.scheme.toLowerCase();
  }

  return null;
}

/**
 * Mandatory Server-Side Snapshot Filtering.
 * Strips all unauthorized companies, setups, catalysts, and benchmarks
 * BEFORE data reaches the user or AI context.
 */
export function filterSnapshotForUser(snapshot, allowedSchemeIds, isAdmin = false) {
  if (!snapshot || typeof snapshot !== "object") return null;
  if (isAdmin) {
    return JSON.parse(JSON.stringify(snapshot)); // Admins receive full snapshot
  }

  const allowedSet = new Set((allowedSchemeIds || []).map((s) => s.trim().toLowerCase()));

  // Filter companies
  const filteredCompanies = {};
  if (snapshot.companies) {
    for (const [key, comp] of Object.entries(snapshot.companies)) {
      const compScheme = (comp.scheme_id || getStockScheme(comp.symbol, snapshot) || "gobardhan").toLowerCase();
      if (allowedSet.has(compScheme)) {
        filteredCompanies[key] = { ...comp };
      }
    }
  }

  // Filter qualified setups (symbols must be in filteredCompanies)
  const filteredQualified = (snapshot.qualified_setups || []).filter((sym) => {
    const comp = snapshot.companies?.[sym] || Object.values(snapshot.companies || {}).find((c) => c.symbol === sym || c.short_symbol === sym);
    if (!comp) return false;
    const sId = (comp.scheme_id || getStockScheme(sym, snapshot) || "gobardhan").toLowerCase();
    return allowedSet.has(sId);
  });

  // Filter waiting setups
  const filteredWaiting = (snapshot.waiting_setups || []).filter((sym) => {
    const comp = snapshot.companies?.[sym] || Object.values(snapshot.companies || {}).find((c) => c.symbol === sym || c.short_symbol === sym);
    if (!comp) return false;
    const sId = (comp.scheme_id || getStockScheme(sym, snapshot) || "gobardhan").toLowerCase();
    return allowedSet.has(sId);
  });

  // Filter schemes object
  const filteredSchemes = {};
  if (snapshot.schemes) {
    for (const [sKey, sObj] of Object.entries(snapshot.schemes)) {
      if (allowedSet.has(sKey.toLowerCase())) {
        filteredSchemes[sKey] = { ...sObj };
      }
    }
  }

  // Filter performance and benchmarks
  const filteredPerf = (snapshot.performance || []).filter((p) => !p.scheme_id || allowedSet.has(p.scheme_id.toLowerCase()));
  const filteredBench = (snapshot.benchmark || []).filter((b) => !b.scheme_id || allowedSet.has(b.scheme_id.toLowerCase()));

  return {
    ...snapshot,
    companies: filteredCompanies,
    qualified_setups: filteredQualified,
    waiting_setups: filteredWaiting,
    schemes: filteredSchemes,
    performance: filteredPerf,
    benchmark: filteredBench,
    total_companies_monitored: Object.keys(filteredCompanies).length,
  };
}
