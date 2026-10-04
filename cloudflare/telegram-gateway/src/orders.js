/**
 * Order Management & Product Catalog for Scheme Intel.
 * Resolves trusted pricing and packages from the database, preventing client-side tampering.
 */

import { getSupabaseClient } from "./supabase.js";
import { grantEntitlement } from "./entitlements.js";
import { recordAuditEvent, updateUserStatus, UserStatus } from "./users.js";
import { RazorpayProvider } from "./payments/razorpay.js";
import { TelegramStarsProvider } from "./payments/telegram-stars.js";
import { safeLog } from "./utils.js";

export const OrderStatus = {
  CREATED: "CREATED",
  PENDING: "PENDING",
  PAID: "PAID",
  FAILED: "FAILED",
  REFUNDED: "REFUNDED",
  EXPIRED: "EXPIRED",
};

/**
 * Get active products from database catalog.
 */
export async function getProducts(env) {
  const client = getSupabaseClient(env);
  const { data, error } = await client
    .from("products")
    .select("*")
    .eq("status", "ACTIVE")
    .order("price_inr", { ascending: true });

  if (error || !data || data.length === 0) {
    safeLog("warn", "fetch_products_db_fallback", { error });
    return [
      { id: "p-1", product_code: "GOBARDHAN_MONTHLY", name: "GOBARdhan — Monthly", price_inr: 499, duration_days: 30, schemes: ["gobardhan"], status: "ACTIVE" },
      { id: "p-2", product_code: "GOBARDHAN_YEARLY", name: "GOBARdhan — Yearly", price_inr: 4999, duration_days: 365, schemes: ["gobardhan"], status: "ACTIVE" },
      { id: "p-3", product_code: "SAMUDRA_MONTHLY", name: "Samudra Manthan — Monthly", price_inr: 499, duration_days: 30, schemes: ["samudra_manthan"], status: "ACTIVE" },
      { id: "p-4", product_code: "SAMUDRA_YEARLY", name: "Samudra Manthan — Yearly", price_inr: 4999, duration_days: 365, schemes: ["samudra_manthan"], status: "ACTIVE" },
      { id: "p-5", product_code: "ALL_ACCESS_MONTHLY", name: "All Access — Monthly", price_inr: 799, duration_days: 30, schemes: ["gobardhan", "samudra_manthan"], status: "ACTIVE" },
      { id: "p-6", product_code: "ALL_ACCESS_YEARLY", name: "All Access — Yearly", price_inr: 7999, duration_days: 365, schemes: ["gobardhan", "samudra_manthan"], status: "ACTIVE" },
    ];
  }
  return data;
}

/**
 * Get product by code.
 */
export async function getProductByCode(env, productCode) {
  if (!productCode) return null;
  const client = getSupabaseClient(env);
  const { data } = await client
    .from("products")
    .select("*")
    .eq("product_code", productCode.trim().toUpperCase())
    .maybeSingle();

  if (data) return data;
  const all = await getProducts(env);
  return all.find((p) => p.product_code === productCode.trim().toUpperCase()) || null;
}

/**
 * Generate unique order reference: SI-YYYYMMDD-XXXX
 */
function generateOrderCode() {
  const now = new Date();
  const y = now.getUTCFullYear();
  const m = String(now.getUTCMonth() + 1).padStart(2, "0");
  const d = String(now.getUTCDate()).padStart(2, "0");
  const rand = Math.random().toString(36).substring(2, 6).toUpperCase();
  return `SI-${y}${m}${d}-${rand}`;
}

/**
 * Instantiate appropriate payment provider.
 */
export function getPaymentProviderInstance(providerName = "razorpay") {
  const norm = (providerName || "razorpay").toLowerCase();
  if (norm === "telegram_stars") {
    return new TelegramStarsProvider();
  }
  return new RazorpayProvider();
}

/**
 * Create a new payment order and checkout link.
 */
export async function createPaymentOrder(env, { user, productCode, providerName = "razorpay" }) {
  if (!user || !user.id) {
    throw new Error("Missing valid user");
  }

  const product = await getProductByCode(env, productCode);
  if (!product) {
    throw new Error(`Product not found: ${productCode}`);
  }

  const orderCode = generateOrderCode();
  const provider = getPaymentProviderInstance(providerName);

  // Create payment via provider
  const paymentRes = await provider.createPayment({
    orderCode,
    amount: product.price_inr,
    currency: "INR",
    product,
    user,
    env,
  });

  const client = getSupabaseClient(env);
  const nowIso = new Date().toISOString();

  const orderRecord = {
    order_code: orderCode,
    user_id: user.id,
    product_id: product.id,
    provider: provider.name,
    provider_order_id: paymentRes.providerOrderId,
    amount: product.price_inr,
    currency: "INR",
    status: OrderStatus.CREATED,
    metadata: {
      product_code: product.product_code,
      product_name: product.name,
      duration_days: product.duration_days,
      schemes: product.schemes,
      payment_url: paymentRes.paymentUrl,
    },
    created_at: nowIso,
    updated_at: nowIso,
  };

  const { data: savedOrder, error } = await client
    .from("orders")
    .insert(orderRecord)
    .single();

  if (error) {
    safeLog("error", "create_order_db_failed", { orderCode, error });
  }

  await recordAuditEvent(env, {
    userId: user.id,
    telegramUserId: String(user.telegram_user_id),
    eventType: "PAYMENT_CREATED",
    metadata: {
      orderCode,
      amount: product.price_inr,
      productCode: product.product_code,
      provider: provider.name,
    },
  });

  return {
    order: savedOrder || orderRecord,
    product,
    paymentUrl: paymentRes.paymentUrl,
    orderCode,
  };
}

/**
 * Find order by code, provider_order_id, or ID.
 */
export async function findOrder(env, { orderCode, providerOrderId, orderId }) {
  const client = getSupabaseClient(env);
  if (orderCode) {
    const { data } = await client.from("orders").select("*").eq("order_code", orderCode).maybeSingle();
    if (data) return data;
  }
  if (providerOrderId) {
    const { data } = await client.from("orders").select("*").eq("provider_order_id", providerOrderId).maybeSingle();
    if (data) return data;
  }
  if (orderId) {
    const { data } = await client.from("orders").select("*").eq("id", orderId).maybeSingle();
    if (data) return data;
  }
  return null;
}

/**
 * Complete order, transition state to PAID, and activate entitlements automatically.
 */
export async function completeOrderAndGrantEntitlements(
  env,
  { order, providerPaymentId = null, eventId = null }
) {
  if (!order || !order.id) return { success: false, reason: "INVALID_ORDER" };

  // Guard against duplicate entitlement activation
  if (order.status === OrderStatus.PAID) {
    safeLog("info", "order_already_paid", { orderCode: order.order_code });
    return { success: true, alreadyPaid: true };
  }

  const client = getSupabaseClient(env);
  const nowIso = new Date().toISOString();

  // 1. Mark order PAID
  await client
    .from("orders")
    .update({
      status: OrderStatus.PAID,
      paid_at: nowIso,
      provider_payment_id: providerPaymentId || order.provider_payment_id,
      updated_at: nowIso,
    })
    .eq("id", order.id);

  // 2. Fetch product details
  let product = null;
  if (order.product_id) {
    const { data: p } = await client.from("products").select("*").eq("id", order.product_id).maybeSingle();
    product = p;
  }
  if (!product && order.metadata?.product_code) {
    product = await getProductByCode(env, order.metadata.product_code);
  }

  const schemes = product?.schemes || order.metadata?.schemes || ["gobardhan"];
  const durationDays = product?.duration_days || order.metadata?.duration_days || 30;

  // 3. Grant entitlements for all schemes in product
  const grantedSchemes = [];
  let latestExpiry = null;

  for (const sid of schemes) {
    const granted = await grantEntitlement(env, {
      userId: order.user_id,
      schemeId: sid,
      source: "PAYMENT",
      durationDays,
    });
    grantedSchemes.push(sid);
    if (granted?.expires_at) {
      latestExpiry = granted.expires_at;
    }
  }

  // 4. Ensure user is marked ACTIVE
  await updateUserStatus(env, order.user_id, UserStatus.ACTIVE);

  // 5. Audit log
  await recordAuditEvent(env, {
    userId: order.user_id,
    telegramUserId: "system",
    eventType: "PAYMENT_VERIFIED",
    metadata: {
      orderCode: order.order_code,
      eventId,
      providerPaymentId,
      grantedSchemes,
      durationDays,
      expiresAt: latestExpiry,
    },
  });

  safeLog("info", "order_completed_and_entitlements_granted", {
    orderCode: order.order_code,
    userId: order.user_id,
    grantedSchemes,
    expiresAt: latestExpiry,
  });

  return {
    success: true,
    grantedSchemes,
    durationDays,
    expiresAt: latestExpiry,
    orderCode: order.order_code,
  };
}
