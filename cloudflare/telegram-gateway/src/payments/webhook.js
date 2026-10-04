/**
 * Webhook Handler for Payment Gateways.
 * Validates cryptographic signatures, guarantees event idempotency,
 * updates order state machine, and activates customer entitlements.
 */

import { getSupabaseClient } from "../supabase.js";
import { RazorpayProvider } from "./razorpay.js";
import { findOrder, completeOrderAndGrantEntitlements, OrderStatus } from "../orders.js";
import { revokeEntitlement } from "../entitlements.js";
import { sendMessage } from "../telegram.js";
import { recordAuditEvent } from "../users.js";
import { safeLog } from "../utils.js";

/**
 * Handle incoming payment provider webhooks (e.g. POST /webhooks/razorpay).
 */
export async function handlePaymentWebhook(request, env, ctx) {
  const method = request.method.toUpperCase();
  if (method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  const rawBody = await request.text();
  const signature = request.headers.get("x-razorpay-signature") || "";
  const secret = env.RAZORPAY_WEBHOOK_SECRET || "";

  const provider = new RazorpayProvider();

  // 1. Signature Verification
  // If webhook secret configured, strictly verify HMAC
  if (secret) {
    const isValid = await provider.verifyWebhookSignature({
      rawBody,
      signature,
      secret,
    });

    if (!isValid) {
      safeLog("warn", "payment_webhook_signature_invalid", {
        hasSignature: Boolean(signature),
        ip: request.headers.get("CF-Connecting-IP"),
      });
      await recordAuditEvent(env, {
        telegramUserId: "system",
        eventType: "PAYMENT_SIGNATURE_INVALID",
        metadata: { ip: request.headers.get("CF-Connecting-IP") },
      });
      return new Response(JSON.stringify({ error: "Invalid webhook signature" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }
  }

  // 2. Parse payload
  let payload;
  try {
    payload = JSON.parse(rawBody);
  } catch (err) {
    safeLog("error", "payment_webhook_invalid_json", { error: err.message });
    return new Response(JSON.stringify({ error: "Invalid JSON" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const parsed = provider.parseWebhookPayload(payload);
  const client = getSupabaseClient(env);
  const nowIso = new Date().toISOString();

  // 3. Idempotency Check: prevent duplicate event processing
  const { data: existingEvent } = await client
    .from("payment_events")
    .select("*")
    .eq("event_id", parsed.eventId)
    .maybeSingle();

  if (existingEvent && existingEvent.processed) {
    safeLog("info", "payment_webhook_duplicate_ignored", { eventId: parsed.eventId });
    return new Response(
      JSON.stringify({ status: "ok", message: "Event already processed" }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  }

  // Record raw event
  if (!existingEvent) {
    await client.from("payment_events").insert({
      provider: "razorpay",
      event_id: parsed.eventId,
      event_type: parsed.eventType,
      payload,
      signature_valid: true,
      processed: false,
      created_at: nowIso,
    });
  }

  // 4. State Machine Execution
  try {
    if (parsed.isPaid) {
      const order = await findOrder(env, {
        orderCode: parsed.orderCode,
        providerOrderId: parsed.providerOrderId,
      });

      if (!order) {
        safeLog("warn", "payment_webhook_order_not_found", {
          orderCode: parsed.orderCode,
          providerOrderId: parsed.providerOrderId,
        });
      } else {
        const result = await completeOrderAndGrantEntitlements(env, {
          order,
          providerPaymentId: parsed.providerPaymentId,
          eventId: parsed.eventId,
        });

        // Notify user on Telegram
        const botToken = env.TELEGRAM_BOT_TOKEN;
        if (botToken && order.user_id) {
          const { data: user } = await client.from("users").select("*").eq("id", order.user_id).maybeSingle();
          if (user && user.telegram_chat_id) {
            const expText = result.expiresAt
              ? new Date(result.expiresAt).toLocaleDateString("en-GB", { day: "2-digit", month: "long", year: "numeric" })
              : "Ongoing";

            const schemeNames = (result.grantedSchemes || ["gobardhan"])
              .map((s) => (s === "samudra_manthan" ? "🌊 Samudra Manthan" : "🌱 GOBARdhan"))
              .join("\n");

            const primaryScheme = result.grantedSchemes?.[0] || "gobardhan";
            const btnTitle = primaryScheme === "samudra_manthan" ? "🌊 Open Samudra Manthan" : "🌱 Open GOBARdhan";

            const confirmationMessage =
              `✅ *PAYMENT SUCCESSFUL*\n\n` +
              `Your subscription is now active for:\n\n` +
              `${schemeNames}\n\n` +
              `*Expires:*\n${expText}\n\n` +
              `*Order:* \`${order.order_code}\``;

            const keyboard = {
              inline_keyboard: [
                [{ text: btnTitle, callback_data: `scheme_select:${primaryScheme}` }],
                [{ text: "📋 My Access & Status", callback_data: "my_access" }],
              ],
            };

            const sendPromise = sendMessage(botToken, user.telegram_chat_id, confirmationMessage, {
              replyMarkup: keyboard,
            });
            if (ctx && typeof ctx.waitUntil === "function") {
              ctx.waitUntil(sendPromise);
            } else {
              await sendPromise;
            }
          }
        }
      }
    } else if (parsed.isFailed) {
      const order = await findOrder(env, {
        orderCode: parsed.orderCode,
        providerOrderId: parsed.providerOrderId,
      });
      if (order && order.status !== OrderStatus.PAID) {
        await client.from("orders").update({ status: OrderStatus.FAILED, updated_at: nowIso }).eq("id", order.id);
        await recordAuditEvent(env, {
          userId: order.user_id,
          telegramUserId: "system",
          eventType: "PAYMENT_FAILED",
          metadata: { orderCode: order.order_code, eventId: parsed.eventId },
        });
      }
    } else if (parsed.isRefunded) {
      const order = await findOrder(env, {
        orderCode: parsed.orderCode,
        providerOrderId: parsed.providerOrderId,
      });
      if (order) {
        await client.from("orders").update({ status: OrderStatus.REFUNDED, updated_at: nowIso }).eq("id", order.id);
        await recordAuditEvent(env, {
          userId: order.user_id,
          telegramUserId: "system",
          eventType: "PAYMENT_REFUNDED",
          metadata: { orderCode: order.order_code, eventId: parsed.eventId },
        });

        // Revoke scheme entitlements granted by this order without deleting history
        const schemesToRevoke = order.metadata?.schemes || [];
        for (const schemeId of schemesToRevoke) {
          await revokeEntitlement(env, {
            userId: order.user_id,
            schemeId,
            reason: `refund_order_${order.order_code}`,
            telegramUserId: "system",
          });
        }
      }
    } else if (parsed.eventType === "payment_link.expired" || parsed.eventType === "order.expired") {
      const order = await findOrder(env, {
        orderCode: parsed.orderCode,
        providerOrderId: parsed.providerOrderId,
      });
      if (order && order.status === OrderStatus.CREATED) {
        await client.from("orders").update({ status: OrderStatus.EXPIRED, updated_at: nowIso }).eq("id", order.id);
        await recordAuditEvent(env, {
          userId: order.user_id,
          telegramUserId: "system",
          eventType: "ORDER_EXPIRED",
          metadata: { orderCode: order.order_code, eventId: parsed.eventId },
        });
      }
    }

    // Mark event processed
    await client
      .from("payment_events")
      .update({ processed: true })
      .eq("event_id", parsed.eventId);

    return new Response(JSON.stringify({ status: "success", eventId: parsed.eventId }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    safeLog("error", "payment_webhook_processing_error", { eventId: parsed.eventId, error: err.message });
    await client
      .from("payment_events")
      .update({ processing_error: err.message })
      .eq("event_id", parsed.eventId);

    return new Response(JSON.stringify({ error: "Webhook processing error" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}
