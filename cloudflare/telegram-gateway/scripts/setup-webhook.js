#!/usr/bin/env node
/**
 * Setup Script for Telegram Webhook with Cloudflare Worker.
 *
 * Usage:
 *   node scripts/setup-webhook.js --url https://<your-worker>.<subdomain>.workers.dev --token <BOT_TOKEN> [--secret <SECRET>]
 * Or via environment variables:
 *   TELEGRAM_BOT_TOKEN=... WORKER_URL=... TELEGRAM_WEBHOOK_SECRET=... node scripts/setup-webhook.js
 */

import { setWebhook, getWebhookInfo, setMyCommands, BOT_COMMANDS } from "../src/telegram.js";

function parseArgs() {
  const args = process.argv.slice(2);
  const result = {
    url: process.env.WORKER_URL || "",
    token: process.env.TELEGRAM_BOT_TOKEN || "",
    secret: process.env.TELEGRAM_WEBHOOK_SECRET || "",
  };

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--url" && args[i + 1]) {
      result.url = args[++i];
    } else if (args[i] === "--token" && args[i + 1]) {
      result.token = args[++i];
    } else if (args[i] === "--secret" && args[i + 1]) {
      result.secret = args[++i];
    }
  }
  return result;
}

async function main() {
  const { url, token, secret } = parseArgs();

  console.log("=================================================================");
  console.log("  Scheme-Intel Telegram Webhook Setup for Cloudflare Worker     ");
  console.log("=================================================================");

  if (!token) {
    console.error("❌ Error: Missing Telegram Bot Token.");
    console.error("   Provide via --token <TOKEN> or TELEGRAM_BOT_TOKEN environment variable.");
    process.exit(1);
  }

  if (!url) {
    console.error("❌ Error: Missing Cloudflare Worker HTTPS URL.");
    console.error("   Provide via --url https://<worker>.<subdomain>.workers.dev or WORKER_URL.");
    process.exit(1);
  }

  if (!url.startsWith("https://")) {
    console.error("❌ Error: Webhook URL must use HTTPS protocol.");
    process.exit(1);
  }

  console.log(`[+] Target Webhook URL: ${url}`);
  console.log(`[+] Secret Token: ${secret ? "[CONFIGURED]" : "[NONE]"}`);

  try {
    // 1. Set Webhook
    console.log("[*] Configuring Telegram Webhook via Telegram Bot API...");
    const setRes = await setWebhook(token, url, secret);

    if (setRes.ok) {
      console.log("✅ Webhook configured successfully:", setRes.description);
    } else {
      console.error("❌ Failed setting webhook:", setRes.description);
      process.exit(1);
    }

    // 2. Verify Webhook Info
    console.log("[*] Verifying webhook status with getWebhookInfo...");
    const infoRes = await getWebhookInfo(token);
    if (infoRes.ok) {
      const info = infoRes.result;
      console.log("✅ Verified Webhook Information:");
      console.log(`   • URL: ${info.url}`);
      console.log(`   • Has Custom Certificate: ${info.has_custom_certificate}`);
      console.log(`   • Pending Update Count: ${info.pending_update_count}`);
      if (info.last_error_message) {
        console.warn(`   • Last Error: ${info.last_error_message} (${info.last_error_date})`);
      }
    }

    // 3. Register Commands
    console.log(`[*] Registering ${BOT_COMMANDS.length} core interactive commands with Telegram setMyCommands...`);
    const cmdRes = await setMyCommands(token, BOT_COMMANDS);
    if (cmdRes.ok) {
      console.log(`✅ Successfully registered ${BOT_COMMANDS.length} bot commands!`);
    } else {
      console.warn("⚠️ Failed registering bot commands:", cmdRes.description);
    }

    console.log("=================================================================");
    console.log("  SUCCESS! Telegram Webhook is live on Cloudflare Workers.       ");
    console.log("  You can now interact with your bot on Telegram 24/7.           ");
    console.log("=================================================================");
  } catch (err) {
    console.error("❌ Network or API error during webhook setup:", err.message);
    process.exit(1);
  }
}

main();
