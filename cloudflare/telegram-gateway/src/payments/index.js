/**
 * Payment Provider Abstraction Interface.
 * Allows pluggable payment gateways (Razorpay, Telegram Stars, etc.).
 */

export class PaymentProvider {
  constructor(name) {
    this.name = name;
  }

  /**
   * Create an external payment order or payment link.
   * @param {Object} params
   * @returns {Promise<{ providerOrderId: string, paymentUrl: string, amount: number, currency: string }>}
   */
  async createPayment({ orderCode, amount, currency, product, user, env }) {
    throw new Error("Method createPayment() must be implemented by subclass");
  }

  /**
   * Verify the incoming webhook signature.
   * @param {Object} params
   * @returns {Promise<boolean>}
   */
  async verifyWebhookSignature({ rawBody, signature, secret }) {
    throw new Error("Method verifyWebhookSignature() must be implemented by subclass");
  }

  /**
   * Parse standardized webhook event payload.
   * @param {Object} payload
   * @returns {{ eventType: string, eventId: string, orderCode?: string, providerOrderId?: string, providerPaymentId?: string, isPaid: boolean, amount?: number }}
   */
  parseWebhookPayload(payload) {
    throw new Error("Method parseWebhookPayload() must be implemented by subclass");
  }
}
