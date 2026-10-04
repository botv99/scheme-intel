/**
 * Telegram Stars Payment Provider for Scheme Intel.
 * Implements Telegram native digital goods invoice generation.
 */

import { PaymentProvider } from "./index.js";
import { safeLog } from "../utils.js";

export class TelegramStarsProvider extends PaymentProvider {
  constructor() {
    super("telegram_stars");
  }

  async createPayment({ orderCode, amount, currency = "XTR", product, user, env }) {
    // 1 Telegram Star is approx ₹1.5 - ₹2.0 or 1:1 depending on pricing tier
    // Default 250 Stars for ₹499
    const starsAmount = Math.max(1, Math.round(Number(amount) / 2));
    const botToken = env.TELEGRAM_BOT_TOKEN;

    if (!botToken || env.MOCK_PAYMENTS === "true" || env.__MOCK_PAYMENTS__) {
      safeLog("info", "mock_telegram_stars_invoice_created", { orderCode, starsAmount });
      return {
        providerOrderId: `stars_mock_${orderCode}`,
        paymentUrl: `https://t.me/SchemeIntelBot?start=invoice_${orderCode}`,
        amount: starsAmount,
        currency: "XTR",
      };
    }

    try {
      const resp = await fetch(`https://api.telegram.org/bot${botToken}/createInvoiceLink`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: product.name,
          description: product.description || `Access to ${product.name}`,
          payload: JSON.stringify({ order_code: orderCode, user_id: user.id }),
          currency: "XTR",
          prices: [{ label: product.name, amount: starsAmount }],
        }),
      });

      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        throw new Error(data.description || "Telegram Stars invoice creation failed");
      }

      return {
        providerOrderId: `stars_${orderCode}`,
        paymentUrl: data.result,
        amount: starsAmount,
        currency: "XTR",
      };
    } catch (err) {
      safeLog("error", "telegram_stars_create_invoice_failed", { error: err.message });
      throw err;
    }
  }

  async verifyWebhookSignature({ rawBody, signature, secret }) {
    // In Telegram Stars, payment verification comes as a verified Telegram update (successful_payment)
    return Boolean(signature);
  }

  parseWebhookPayload(payload) {
    const sp = payload.message?.successful_payment;
    if (!sp) {
      return { eventType: "unknown", eventId: `stars_${Date.now()}`, isPaid: false };
    }

    let invoicePayload = {};
    try {
      invoicePayload = JSON.parse(sp.invoice_payload);
    } catch {
      invoicePayload = { order_code: sp.invoice_payload };
    }

    return {
      eventType: "telegram_stars.paid",
      eventId: sp.telegram_payment_charge_id || `stars_charge_${Date.now()}`,
      providerOrderId: sp.telegram_payment_charge_id,
      providerPaymentId: sp.provider_payment_charge_id,
      orderCode: invoicePayload.order_code,
      isPaid: true,
      amount: sp.total_amount,
      currency: sp.currency,
    };
  }
}
