/**
 * Razorpay Payment Provider for Scheme Intel.
 * Implements Razorpay payment link creation and Web Crypto HMAC-SHA256 signature verification.
 */

import { PaymentProvider } from "./index.js";
import { safeLog } from "../utils.js";

export class RazorpayProvider extends PaymentProvider {
  constructor() {
    super("razorpay");
  }

  /**
   * Create Razorpay Payment Link.
   */
  async createPayment({ orderCode, amount, currency = "INR", product, user, env }) {
    const keyId = env.RAZORPAY_KEY_ID;
    const keySecret = env.RAZORPAY_KEY_SECRET;

    // In test/mock mode if keys not set
    if (!keyId || !keySecret || env.MOCK_PAYMENTS === "true" || env.__MOCK_PAYMENTS__) {
      safeLog("info", "mock_razorpay_payment_link_created", { orderCode, amount });
      return {
        providerOrderId: `plink_mock_${orderCode}`,
        paymentUrl: `https://rzp.io/l/mock_${orderCode}`,
        amount,
        currency,
      };
    }

    const amountInPaise = Math.round(Number(amount) * 100);
    const authHeader = "Basic " + btoa(`${keyId}:${keySecret}`);

    const payload = {
      amount: amountInPaise,
      currency: currency || "INR",
      description: `Scheme Intel: ${product.name}`,
      reference_id: orderCode,
      notes: {
        order_code: orderCode,
        user_id: user.id,
        telegram_user_id: String(user.telegram_user_id),
        product_code: product.product_code,
      },
    };

    try {
      const response = await fetch("https://api.razorpay.com/v1/payment_links", {
        method: "POST",
        headers: {
          "Authorization": authHeader,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();
      if (!response.ok) {
        safeLog("error", "razorpay_api_error", { status: response.status, data });
        throw new Error(`Razorpay API error: ${data.error?.description || response.statusText}`);
      }

      return {
        providerOrderId: data.id,
        paymentUrl: data.short_url || data.url,
        amount,
        currency,
      };
    } catch (err) {
      safeLog("error", "razorpay_create_payment_failed", { error: err.message });
      throw err;
    }
  }

  /**
   * Verify Razorpay Webhook Signature using Web Crypto HMAC-SHA256.
   */
  async verifyWebhookSignature({ rawBody, signature, secret }) {
    if (!rawBody || !signature || !secret) {
      return false;
    }

    try {
      const encoder = new TextEncoder();
      const key = await crypto.subtle.importKey(
        "raw",
        encoder.encode(secret),
        { name: "HMAC", hash: "SHA-256" },
        false,
        ["sign"]
      );

      const signatureBuffer = await crypto.subtle.sign(
        "HMAC",
        key,
        encoder.encode(rawBody)
      );

      const computedHex = Array.from(new Uint8Array(signatureBuffer))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");

      // Constant-time comparison
      const sigClean = signature.trim().toLowerCase();
      if (computedHex.length !== sigClean.length) {
        return false;
      }

      let match = 0;
      for (let i = 0; i < computedHex.length; i++) {
        match |= computedHex.charCodeAt(i) ^ sigClean.charCodeAt(i);
      }
      return match === 0;
    } catch (err) {
      safeLog("error", "razorpay_signature_verify_error", { error: err.message });
      return false;
    }
  }

  /**
   * Parse Razorpay webhook payload into standard structure.
   */
  parseWebhookPayload(payload) {
    if (!payload || typeof payload !== "object") {
      return { eventType: "unknown", eventId: `evt_${Date.now()}`, isPaid: false };
    }

    const eventType = payload.event || "unknown";
    const eventId = payload.event_id || payload.id || `evt_${Date.now()}`;
    const paymentEntity = payload.payload?.payment?.entity || {};
    const linkEntity = payload.payload?.payment_link?.entity || {};
    const orderEntity = payload.payload?.order?.entity || {};

    const providerPaymentId = paymentEntity.id || null;
    const providerOrderId = linkEntity.id || orderEntity.id || paymentEntity.order_id || null;

    const orderCode =
      linkEntity.reference_id ||
      paymentEntity.notes?.order_code ||
      orderEntity.notes?.order_code ||
      paymentEntity.notes?.orderCode ||
      null;

    const isPaid =
      eventType === "payment_link.paid" ||
      eventType === "order.paid" ||
      eventType === "payment.captured";

    const isFailed = eventType === "payment.failed";
    const isRefunded = eventType === "refund.processed" || eventType === "refund.created";

    const amountInPaise = paymentEntity.amount || linkEntity.amount || orderEntity.amount || 0;
    const amount = amountInPaise ? amountInPaise / 100 : 0;

    return {
      eventType,
      eventId,
      providerOrderId,
      providerPaymentId,
      orderCode,
      isPaid,
      isFailed,
      isRefunded,
      amount,
      raw: payload,
    };
  }
}
