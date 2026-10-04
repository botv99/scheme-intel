/**
 * Comprehensive Test Suite for Scheme Intel:
 * Payment + Authorization + Entitlement System (Cloudflare Worker + Supabase).
 * Verifies all 20 test specifications from Section 20.
 */

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";

import worker from "../src/index.js";
import { resetMockStore, getMockStore } from "../src/supabase.js";
import { generateAccessKey, activateAccessKey, hashAccessKey, revokeAccessKey } from "../src/keys.js";
import { getTelegramAuth, checkSchemeAccess, filterSnapshotForUser, getStockScheme } from "../src/authorization.js";
import { grantEntitlement, revokeEntitlement, getUserEntitlements } from "../src/entitlements.js";
import { createPaymentOrder, findOrder, completeOrderAndGrantEntitlements, OrderStatus } from "../src/orders.js";
import { RazorpayProvider } from "../src/payments/razorpay.js";
import { handlePaymentWebhook } from "../src/payments/webhook.js";
import { handleAdminCommand } from "../src/admin.js";

// Helper to construct test environment
function makeTestEnv(overrides = {}) {
  const store = getMockStore();
  return {
    TELEGRAM_BOT_TOKEN: "mock_bot_token_123",
    TELEGRAM_WEBHOOK_SECRET: "mock_webhook_secret_xyz",
    RAZORPAY_KEY_ID: "rzp_test_12345",
    RAZORPAY_KEY_SECRET: "rzp_test_secret_67890",
    RAZORPAY_WEBHOOK_SECRET: "rzp_webhook_secret_abc",
    ADMIN_USER_IDS: "admin_user_1,platform_admin_999",
    GITHUB_OWNER: "botv99",
    GITHUB_REPO: "scheme-intel",
    GITHUB_BRANCH: "main",
    SNAPSHOT_PATH: "data/intelligence/latest.json",
    __MOCK_SUPABASE__: true,
    __MOCK_STORE__: store,
    MOCK_PAYMENTS: "true",
    ...overrides,
  };
}

// Sample snapshot containing both Gobardhan and Samudra Manthan data
function makeTestSnapshot() {
  return {
    snapshot_id: "SNAP-TEST-20261004",
    generated_at: new Date().toISOString(),
    total_companies_monitored: 4,
    companies: {
      "TRUALT.NS": {
        symbol: "TRUALT.NS",
        short_symbol: "TRUALT",
        name: "TruAlt Bioenergy",
        scheme_id: "gobardhan",
        price: 450.0,
        change_pct: 2.5,
        status: "QUALIFIED_SETUP",
        archetype: "Breakout",
      },
      "PRAJIND.NS": {
        symbol: "PRAJIND.NS",
        short_symbol: "PRAJIND",
        name: "Praj Industries",
        scheme_id: "gobardhan",
        price: 560.0,
        change_pct: 1.2,
        status: "QUALIFIED_SETUP",
        archetype: "Pullback",
      },
      "ONGC.NS": {
        symbol: "ONGC.NS",
        short_symbol: "ONGC",
        name: "Oil and Natural Gas Corporation",
        scheme_id: "samudra_manthan",
        price: 265.0,
        change_pct: 1.8,
        status: "QUALIFIED_SETUP",
        archetype: "DeepValue",
      },
      "OIL.NS": {
        symbol: "OIL.NS",
        short_symbol: "OIL",
        name: "Oil India Limited",
        scheme_id: "samudra_manthan",
        price: 435.0,
        change_pct: 0.5,
        status: "WAIT",
        archetype: "Momentum",
      },
    },
    schemes: {
      gobardhan: { name: "GOBARdhan", scheme_id: "gobardhan" },
      samudra_manthan: { name: "Samudra Manthan", scheme_id: "samudra_manthan" },
    },
    qualified_setups: ["TRUALT.NS", "PRAJIND.NS", "ONGC.NS"],
    waiting_setups: ["OIL.NS"],
  };
}

describe("Scheme Intel — Payment, Authorization & Entitlement System", () => {
  let env;

  beforeEach(() => {
    resetMockStore();
    env = makeTestEnv();
  });

  // -------------------------------------------------------------------------
  // 1. NEW USER & LOCKING TESTS
  // -------------------------------------------------------------------------
  test("1. New user /start returns locked welcome card with unlock buttons", async () => {
    const sentMessages = [];
    const executionCtx = { waitUntil: (p) => Promise.resolve(p) };

    const update = {
      update_id: 1001,
      message: {
        message_id: 501,
        from: { id: 888123, username: "new_trader", first_name: "John" },
        chat: { id: 888123 },
        text: "/start",
      },
    };

    // Mock global fetch for Telegram API call
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (url, opts) => {
      if (typeof url === "string" && url.includes("/sendMessage")) {
        const payload = JSON.parse(opts.body);
        sentMessages.push(payload);
        return new Response(JSON.stringify({ ok: true, result: { message_id: 999 } }), { status: 200 });
      }
      return originalFetch(url, opts);
    };

    try {
      const req = new Request("https://gateway.internal/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Bot-Api-Secret-Token": env.TELEGRAM_WEBHOOK_SECRET,
        },
        body: JSON.stringify(update),
      });

      const res = await worker.fetch(req, env, executionCtx);
      assert.equal(res.status, 200);

      // Verify user record created in locked state
      const auth = await getTelegramAuth(env, { userId: "888123" });
      assert.equal(auth.isLocked, true);
      assert.equal(auth.isAuthorized, false);
      assert.equal(auth.user.status, "LOCKED");

      // Verify Telegram response
      assert.equal(sentMessages.length, 1);
      const msg = sentMessages[0];
      assert.match(msg.text, /Your account is currently locked/i);
      assert.match(msg.text, /Enter an authorization key/i);

      // Verify buttons
      const buttons = msg.reply_markup.inline_keyboard.flat().map((b) => b.text);
      assert.ok(buttons.some((t) => t.includes("Enter Access Key")));
      assert.ok(buttons.some((t) => t.includes("Purchase Access")));
      assert.ok(buttons.some((t) => t.includes("Available Schemes")));
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("2. Locked user cannot access /watchlist, /stock, or protected commands", async () => {
    const sentMessages = [];
    const executionCtx = { waitUntil: (p) => Promise.resolve(p) };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (url, opts) => {
      if (typeof url === "string" && url.includes("/sendMessage")) {
        sentMessages.push(JSON.parse(opts.body));
        return new Response(JSON.stringify({ ok: true, result: { message_id: 999 } }), { status: 200 });
      }
      return originalFetch(url, opts);
    };

    try {
      // Attempt 1: /watchlist
      const reqWatchlist = new Request("https://gateway.internal/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Bot-Api-Secret-Token": env.TELEGRAM_WEBHOOK_SECRET,
        },
        body: JSON.stringify({
          update_id: 1002,
          message: { from: { id: 777001 }, chat: { id: 777001 }, text: "/watchlist" },
        }),
      });
      await worker.fetch(reqWatchlist, env, executionCtx);

      assert.equal(sentMessages.length, 1);
      assert.match(sentMessages[0].text, /Your account is currently locked/i);

      // Attempt 2: /stock TRUALT
      const reqStock = new Request("https://gateway.internal/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Bot-Api-Secret-Token": env.TELEGRAM_WEBHOOK_SECRET,
        },
        body: JSON.stringify({
          update_id: 1003,
          message: { from: { id: 777001 }, chat: { id: 777001 }, text: "/stock TRUALT" },
        }),
      });
      await worker.fetch(reqStock, env, executionCtx);

      assert.equal(sentMessages.length, 2);
      assert.match(sentMessages[1].text, /Your account is currently locked/i);
      // Ensure no stock intelligence was revealed
      assert.ok(!sentMessages[1].text.includes("Breakout"));
      assert.ok(!sentMessages[1].text.includes("450"));
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  // -------------------------------------------------------------------------
  // 2. AUTHORIZATION KEY LIFECYCLE TESTS
  // -------------------------------------------------------------------------
  test("3. Valid authorization key unlocks user and grants scheme entitlements", async () => {
    // Admin creates key for GOBARdhan
    const generated = await generateAccessKey(env, {
      prefix: "GOB",
      schemeIds: ["gobardhan"],
      maxUses: 1,
      durationDays: 365,
      createdBy: "admin_test",
    });

    assert.ok(generated.plaintextKey.startsWith("GOB-"));
    assert.equal(generated.schemes[0], "gobardhan");

    // Plaintext key is NOT stored in database; only hash is stored
    const store = getMockStore();
    const storedKey = store.tables.access_keys.find((k) => k.key_prefix === generated.keyPrefix);
    assert.ok(storedKey);
    assert.equal(storedKey.key_hash, generated.keyHash);
    assert.notEqual(storedKey.key_hash, generated.plaintextKey);

    // User activates key via activateAccessKey
    const actRes = await activateAccessKey(env, {
      telegramUserId: "654321",
      rawKey: generated.plaintextKey,
      telegramChatId: "654321",
      username: "authorized_user",
    });

    assert.equal(actRes.success, true);
    assert.deepEqual(actRes.grantedSchemes, ["gobardhan"]);

    // User account now ACTIVE
    const auth = await getTelegramAuth(env, { userId: "654321" });
    assert.equal(auth.isAuthorized, true);
    assert.equal(auth.isLocked, false);
    assert.ok(auth.allowedSchemes.includes("gobardhan"));

    // Key used_count incremented and status changed to EXPIRED (max_uses reached)
    const updatedKey = store.tables.access_keys.find((k) => k.key_prefix === generated.keyPrefix);
    assert.equal(updatedKey.used_count, 1);
    assert.equal(updatedKey.status, "EXPIRED");
  });

  test("4. Invalid authorization key is rejected with audit logging", async () => {
    const actRes = await activateAccessKey(env, {
      telegramUserId: "999888",
      rawKey: "FAKE-KEY-XXXX-YYYY",
    });

    assert.equal(actRes.success, false);
    assert.equal(actRes.reason, "INVALID_KEY");

    // User remains LOCKED
    const auth = await getTelegramAuth(env, { userId: "999888" });
    assert.equal(auth.isLocked, true);

    // Audit event recorded
    const store = getMockStore();
    const auditLogs = store.tables.audit_events.filter((e) => e.telegram_user_id === "999888");
    assert.ok(auditLogs.some((e) => e.event_type === "KEY_REJECTED"));
  });

  test("5. Expired key is rejected and cannot be activated", async () => {
    const yesterday = new Date(Date.now() - 86400000).toISOString();
    const generated = await generateAccessKey(env, {
      prefix: "EXP",
      schemeIds: ["gobardhan"],
      expiresAt: yesterday,
    });

    const actRes = await activateAccessKey(env, {
      telegramUserId: "111222",
      rawKey: generated.plaintextKey,
    });

    assert.equal(actRes.success, false);
    assert.equal(actRes.reason, "KEY_EXPIRED");
  });

  test("6. Single-use key cannot be reused by another user", async () => {
    const key = await generateAccessKey(env, {
      prefix: "ONE",
      schemeIds: ["gobardhan"],
      maxUses: 1,
    });

    // User 1 activates successfully
    const res1 = await activateAccessKey(env, { telegramUserId: "user_one", rawKey: key.plaintextKey });
    assert.equal(res1.success, true);

    // User 2 attempts to use same key
    const res2 = await activateAccessKey(env, { telegramUserId: "user_two", rawKey: key.plaintextKey });
    assert.equal(res2.success, false);
    assert.equal(res2.reason, "MAX_USES_REACHED");
  });

  // -------------------------------------------------------------------------
  // 3. SCHEME ISOLATION & SERVER-SIDE FILTERING TESTS
  // -------------------------------------------------------------------------
  test("7. Scheme isolation: GOBARdhan user can access TRUALT/PRAJ, denied ONGC", () => {
    const fullSnapshot = makeTestSnapshot();
    const gobOnlySchemes = ["gobardhan"];

    // Mandatory Server-Side Snapshot Filtering
    const filtered = filterSnapshotForUser(fullSnapshot, gobOnlySchemes);

    // Allowed stocks present
    assert.ok(filtered.companies["TRUALT.NS"]);
    assert.ok(filtered.companies["PRAJIND.NS"]);

    // Unauthorized stocks strictly stripped
    assert.equal(filtered.companies["ONGC.NS"], undefined);
    assert.equal(filtered.companies["OIL.NS"], undefined);
    assert.equal(filtered.total_companies_monitored, 2);

    // Setups filtered
    assert.ok(filtered.qualified_setups.includes("TRUALT.NS"));
    assert.ok(filtered.qualified_setups.includes("PRAJIND.NS"));
    assert.ok(!filtered.qualified_setups.includes("ONGC.NS"));
    assert.equal(filtered.waiting_setups.length, 0);

    // Schemes object filtered
    assert.ok(filtered.schemes["gobardhan"]);
    assert.equal(filtered.schemes["samudra_manthan"], undefined);
  });

  test("8. Stock bypass: /stock ONGC by GOBARdhan user returns ACCESS RESTRICTED", async () => {
    // Register user with GOBARdhan entitlement only
    const key = await generateAccessKey(env, { schemeIds: ["gobardhan"] });
    await activateAccessKey(env, { telegramUserId: "gob_user_1", rawKey: key.plaintextKey });

    const sentMessages = [];
    const executionCtx = { waitUntil: (p) => Promise.resolve(p) };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (url, opts) => {
      if (typeof url === "string" && url.includes("/sendMessage")) {
        sentMessages.push(JSON.parse(opts.body));
        return new Response(JSON.stringify({ ok: true, result: { message_id: 101 } }), { status: 200 });
      }
      return originalFetch(url, opts);
    };

    try {
      const req = new Request("https://gateway.internal/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Bot-Api-Secret-Token": env.TELEGRAM_WEBHOOK_SECRET,
        },
        body: JSON.stringify({
          update_id: 2001,
          message: { from: { id: "gob_user_1" }, chat: { id: "gob_user_1" }, text: "/stock ONGC" },
        }),
      });

      await worker.fetch(req, env, executionCtx);

      assert.equal(sentMessages.length, 1);
      const msg = sentMessages[0];
      assert.match(msg.text, /ACCESS RESTRICTED/i);
      assert.match(msg.text, /\*?ONGC\*? belongs to a scheme you are not authorized to access/i);
      assert.match(msg.text, /You can access:\s*🌱 GOBARdhan/i);
      // Confidential oil & gas data must not leak
      assert.ok(!msg.text.includes("DeepValue"));
      assert.ok(!msg.text.includes("265"));
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("9. Callback bypass: scheme_select:samudra_manthan by GOBARdhan user is denied", async () => {
    const key = await generateAccessKey(env, { schemeIds: ["gobardhan"] });
    await activateAccessKey(env, { telegramUserId: "gob_user_2", rawKey: key.plaintextKey });

    const sentMessages = [];
    const executionCtx = { waitUntil: (p) => Promise.resolve(p) };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (url, opts) => {
      if (typeof url === "string" && url.includes("/sendMessage")) {
        sentMessages.push(JSON.parse(opts.body));
        return new Response(JSON.stringify({ ok: true, result: { message_id: 102 } }), { status: 200 });
      }
      return originalFetch(url, opts);
    };

    try {
      const req = new Request("https://gateway.internal/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Bot-Api-Secret-Token": env.TELEGRAM_WEBHOOK_SECRET,
        },
        body: JSON.stringify({
          update_id: 2002,
          callback_query: {
            id: "cb_bypass_1",
            from: { id: "gob_user_2" },
            message: { chat: { id: "gob_user_2" }, message_id: 50 },
            data: "scheme_select:samudra_manthan",
          },
        }),
      });

      await worker.fetch(req, env, executionCtx);

      assert.equal(sentMessages.length, 1);
      const msg = sentMessages[0];
      assert.match(msg.text, /SCHEME LOCKED/i);
      assert.match(msg.text, /You do not have access to this scheme/i);

      // Verify user's active scheme was NOT switched to samudra_manthan
      const auth = await getTelegramAuth(env, { userId: "gob_user_2" });
      assert.equal(auth.activeScheme, "gobardhan");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  // -------------------------------------------------------------------------
  // 4. MULTI-SCHEME ACCESS & REVOCATION TESTS
  // -------------------------------------------------------------------------
  test("10. Multi-scheme user with GOBARdhan and Samudra Manthan can access both", async () => {
    // Generate all-access key
    const allKey = await generateAccessKey(env, {
      prefix: "ALL",
      schemeIds: ["gobardhan", "samudra_manthan"],
    });

    await activateAccessKey(env, { telegramUserId: "dual_trader", rawKey: allKey.plaintextKey });

    const auth = await getTelegramAuth(env, { userId: "dual_trader" });
    assert.equal(checkSchemeAccess(auth, "gobardhan"), true);
    assert.equal(checkSchemeAccess(auth, "samudra_manthan"), true);

    const fullSnapshot = makeTestSnapshot();
    const filtered = filterSnapshotForUser(fullSnapshot, auth.allowedSchemes);

    // Both Gobardhan and Samudra stocks accessible
    assert.ok(filtered.companies["TRUALT.NS"]);
    assert.ok(filtered.companies["ONGC.NS"]);
    assert.equal(filtered.total_companies_monitored, 4);
  });

  test("11. Revocation: Admin revoking scheme immediately terminates access", async () => {
    const key = await generateAccessKey(env, { schemeIds: ["gobardhan", "samudra_manthan"] });
    await activateAccessKey(env, { telegramUserId: "revokable_user", rawKey: key.plaintextKey });

    const authBefore = await getTelegramAuth(env, { userId: "revokable_user" });
    assert.equal(checkSchemeAccess(authBefore, "samudra_manthan"), true);

    // Revoke Samudra Manthan
    await revokeEntitlement(env, {
      userId: authBefore.user.id,
      schemeId: "samudra_manthan",
      reason: "subscription_cancelled",
    });

    // Check immediate status
    const authAfter = await getTelegramAuth(env, { userId: "revokable_user" });
    assert.equal(checkSchemeAccess(authAfter, "samudra_manthan"), false);
    assert.equal(checkSchemeAccess(authAfter, "gobardhan"), true);
  });

  test("12. Entitlement expiry denies access when expires_at < now", async () => {
    const yesterday = new Date(Date.now() - 86400000).toISOString();

    // Create user and grant expired entitlement
    const userAuth = await getTelegramAuth(env, { userId: "expired_user_99" });
    await grantEntitlement(env, {
      userId: userAuth.user.id,
      schemeId: "gobardhan",
      expiresAt: yesterday,
    });

    // User entitlements query ignores expired records
    const entitlements = await getUserEntitlements(env, userAuth.user.id);
    assert.equal(entitlements.length, 0);

    const auth = await getTelegramAuth(env, { userId: "expired_user_99" });
    assert.equal(auth.isAuthorized, false);
    assert.equal(auth.isLocked, true);
  });

  // -------------------------------------------------------------------------
  // 5. PAYMENT SUBSYSTEM TESTS
  // -------------------------------------------------------------------------
  test("13. Payment order creation from database product catalog", async () => {
    const userAuth = await getTelegramAuth(env, { userId: "paying_customer_1" });

    const orderRes = await createPaymentOrder(env, {
      user: userAuth.user,
      productCode: "GOBARDHAN_MONTHLY",
      providerName: "razorpay",
    });

    assert.ok(orderRes.orderCode.startsWith("SI-"));
    assert.equal(orderRes.product.price_inr, 499);
    assert.equal(orderRes.order.status, OrderStatus.CREATED);
    assert.ok(orderRes.paymentUrl);

    // Order stored in DB
    const found = await findOrder(env, { orderCode: orderRes.orderCode });
    assert.ok(found);
    assert.equal(found.amount, 499);
  });

  test("14. Payment webhook with valid HMAC signature activates order and entitlements", async () => {
    const userAuth = await getTelegramAuth(env, {
      userId: "paying_customer_2",
      chatId: "998877",
    });

    // Create order
    const orderRes = await createPaymentOrder(env, {
      user: userAuth.user,
      productCode: "SAMUDRA_MONTHLY",
      providerName: "razorpay",
    });

    // Build Razorpay webhook payload
    const eventId = `evt_test_${Date.now()}`;
    const payload = {
      event: "payment_link.paid",
      event_id: eventId,
      payload: {
        payment_link: {
          entity: {
            id: orderRes.order.provider_order_id,
            reference_id: orderRes.orderCode,
            amount: 49900,
          },
        },
        payment: {
          entity: {
            id: "pay_test_9999",
            amount: 49900,
          },
        },
      },
    };

    const rawBody = JSON.stringify(payload);

    // Compute valid HMAC signature
    const provider = new RazorpayProvider();
    const encoder = new TextEncoder();
    const cryptoKey = await crypto.subtle.importKey(
      "raw",
      encoder.encode(env.RAZORPAY_WEBHOOK_SECRET),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"]
    );
    const sigBuffer = await crypto.subtle.sign("HMAC", cryptoKey, encoder.encode(rawBody));
    const validSignature = Array.from(new Uint8Array(sigBuffer))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");

    // Send to webhook endpoint
    const req = new Request("https://gateway.internal/webhooks/razorpay", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-razorpay-signature": validSignature,
      },
      body: rawBody,
    });

    const executionCtx = { waitUntil: (p) => Promise.resolve(p) };
    const res = await handlePaymentWebhook(req, env, executionCtx);
    assert.equal(res.status, 200);

    // Order status now PAID
    const paidOrder = await findOrder(env, { orderCode: orderRes.orderCode });
    assert.equal(paidOrder.status, OrderStatus.PAID);
    assert.ok(paidOrder.paid_at);

    // User now has active entitlement for Samudra Manthan
    const customerAuth = await getTelegramAuth(env, { userId: "paying_customer_2" });
    assert.equal(customerAuth.isAuthorized, true);
    assert.ok(customerAuth.allowedSchemes.includes("samudra_manthan"));
  });

  test("15. Duplicate payment webhook is handled idempotently without duplicate grant", async () => {
    const userAuth = await getTelegramAuth(env, { userId: "paying_customer_3" });
    const orderRes = await createPaymentOrder(env, {
      user: userAuth.user,
      productCode: "GOBARDHAN_MONTHLY",
    });

    const eventId = `evt_dup_${Date.now()}`;
    const payload = {
      event: "payment_link.paid",
      event_id: eventId,
      payload: {
        payment_link: {
          entity: {
            id: orderRes.order.provider_order_id,
            reference_id: orderRes.orderCode,
            amount: 49900,
          },
        },
      },
    };

    const rawBody = JSON.stringify(payload);
    const encoder = new TextEncoder();
    const cryptoKey = await crypto.subtle.importKey(
      "raw",
      encoder.encode(env.RAZORPAY_WEBHOOK_SECRET),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"]
    );
    const sigBuffer = await crypto.subtle.sign("HMAC", cryptoKey, encoder.encode(rawBody));
    const validSignature = Array.from(new Uint8Array(sigBuffer))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");

    const req1 = new Request("https://gateway.internal/webhooks/razorpay", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-razorpay-signature": validSignature },
      body: rawBody,
    });
    const res1 = await handlePaymentWebhook(req1, env, { waitUntil: () => {} });
    assert.equal(res1.status, 200);

    // Second duplicate request
    const req2 = new Request("https://gateway.internal/webhooks/razorpay", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-razorpay-signature": validSignature },
      body: rawBody,
    });
    const res2 = await handlePaymentWebhook(req2, env, { waitUntil: () => {} });
    assert.equal(res2.status, 200);

    const data2 = await res2.json();
    assert.equal(data2.message, "Event already processed");
  });

  test("16. Forged payment webhook signature is rejected with HTTP 401", async () => {
    const req = new Request("https://gateway.internal/webhooks/razorpay", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-razorpay-signature": "forged_malicious_signature_12345",
      },
      body: JSON.stringify({ event: "order.paid", id: "evt_attack" }),
    });

    const res = await handlePaymentWebhook(req, env, { waitUntil: () => {} });
    assert.equal(res.status, 401);
  });

  // -------------------------------------------------------------------------
  // 6. ADMIN SECURITY & PRIVILEGE TESTS
  // -------------------------------------------------------------------------
  test("17. Non-admin user cannot execute /admin commands", async () => {
    const res = await handleAdminCommand("/admin genkey gobardhan", "regular_user_77", "regular_user_77", env);
    assert.match(res.replyText, /You do not have administrator privileges/i);
  });

  test("18. Admin user can generate keys and grant/revoke entitlements via /admin", async () => {
    // 1. Admin generates key
    const genRes = await handleAdminCommand("/admin genkey samudra_manthan 180 2", "admin_user_1", "admin_user_1", env);
    assert.match(genRes.replyText, /NEW AUTHORIZATION KEY GENERATED/i);
    assert.match(genRes.replyText, /samudra_manthan/i);

    // 2. Admin grants scheme directly to user
    const userAuth = await getTelegramAuth(env, { userId: "target_user_55" });
    const grantRes = await handleAdminCommand("/admin grant target_user_55 gobardhan 90", "admin_user_1", "admin_user_1", env);
    assert.match(grantRes.replyText, /ENTITLEMENT GRANTED/i);

    const authAfterGrant = await getTelegramAuth(env, { userId: "target_user_55" });
    assert.equal(checkSchemeAccess(authAfterGrant, "gobardhan"), true);

    // 3. Admin revokes scheme from user
    const revokeRes = await handleAdminCommand("/admin revokegrant target_user_55 gobardhan", "admin_user_1", "admin_user_1", env);
    assert.match(revokeRes.replyText, /Revoked scheme \*gobardhan\*/i);

    const authAfterRevoke = await getTelegramAuth(env, { userId: "target_user_55" });
    assert.equal(checkSchemeAccess(authAfterRevoke, "gobardhan"), false);
  });
});
