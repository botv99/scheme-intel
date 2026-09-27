/**
 * Safe Structured Logging and Utility Functions for Cloudflare Worker.
 * Strictly redacts tokens, secrets, and sensitive credentials.
 */

export function generateRequestId() {
  const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const randomSuffix = Math.random().toString(36).substring(2, 8).toUpperCase();
  return `TG-${dateStr}-${randomSuffix}`;
}

export function sanitize(value) {
  if (typeof value !== "string") return value;
  // Redact potential bot tokens (e.g. 123456:ABC-DEF...)
  return value
    .replace(/\b\d{8,11}:[a-zA-Z0-9_-]{35}\b/g, "[REDACTED_BOT_TOKEN]")
    .replace(/\b(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,255}\b/g, "[REDACTED_GITHUB_TOKEN]")
    .replace(/\bBearer\s+[a-zA-Z0-9_.-]+\b/gi, "Bearer [REDACTED]");
}

export function safeLog(level, event, fields = {}) {
  const sanitizedFields = {};
  for (const [k, v] of Object.entries(fields)) {
    const lowerKey = k.toLowerCase();
    if (
      lowerKey.includes("token") ||
      lowerKey.includes("secret") ||
      lowerKey.includes("key") ||
      lowerKey.includes("password") ||
      lowerKey.includes("auth")
    ) {
      sanitizedFields[k] = "[REDACTED]";
    } else if (typeof v === "string") {
      sanitizedFields[k] = sanitize(v);
    } else {
      sanitizedFields[k] = v;
    }
  }

  const logPayload = {
    timestamp: new Date().toISOString(),
    level,
    event,
    ...sanitizedFields,
  };

  const line = `[${level.toUpperCase()}] [${event}] ` +
    Object.entries(sanitizedFields)
      .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`)
      .join(" ");

  if (level === "error") {
    console.error(line);
  } else if (level === "warn") {
    console.warn(line);
  } else {
    console.log(line);
  }

  return logPayload;
}
