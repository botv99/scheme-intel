/**
 * GitHub API Client for Repository Dispatch.
 * Dispatches complex analytical queries from Cloudflare Worker to GitHub Actions.
 */
import { safeLog } from "./utils.js";

const GITHUB_API_BASE = "https://api.github.com";

/**
 * Resolves a GitHub token safely from various potential environment bindings.
 * Supports GITHUB_TOKEN, GH_TOKEN, GITHUB_PAT, and global bindings,
 * handling whitespace, quotes, and newlines safely without leaking secrets.
 */
export function getGithubToken(env) {
  const candidates = [
    env?.GITHUB_TOKEN,
    env?.GH_TOKEN,
    env?.GITHUB_PAT,
    typeof GITHUB_TOKEN !== "undefined" ? GITHUB_TOKEN : null,
  ];
  for (const c of candidates) {
    if (typeof c === "string") {
      let t = c.trim();
      if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'"))) {
        t = t.slice(1, -1).trim();
      }
      if (t.length > 0) {
        return t;
      }
    }
  }
  return "";
}

/**
 * Trigger GitHub repository_dispatch event for 04-telegram-query.yml.
 * Endpoint: POST /repos/{owner}/{repo}/dispatches
 * Expected response: HTTP 204 No Content on success.
 */
export async function dispatchWorkflow(githubToken, repoOwner, repoName, eventType, clientPayload) {
  let token = typeof githubToken === "string" ? githubToken.trim() : "";
  if ((token.startsWith('"') && token.endsWith('"')) || (token.startsWith("'") && token.endsWith("'"))) {
    token = token.slice(1, -1).trim();
  }

  if (!token) {
    safeLog("error", "github_dispatch_missing_token", {
      repoOwner,
      repoName,
      requestId: clientPayload?.request_id,
    });
    return {
      success: false,
      status: 401,
      error: "GITHUB_TOKEN is not configured on Cloudflare Worker",
    };
  }

  // GitHub repository_dispatch enforces a hard limit of at most 10 properties in client_payload
  const sanitizedPayload = { ...(clientPayload || {}) };
  const keys = Object.keys(sanitizedPayload);
  if (keys.length > 10) {
    const lowPriorityKeys = ["message_id", "normalized_query", "raw_query", "username", "first_name"];
    for (const k of lowPriorityKeys) {
      if (Object.keys(sanitizedPayload).length <= 10) break;
      delete sanitizedPayload[k];
    }
  }

  const url = `${GITHUB_API_BASE}/repos/${repoOwner}/${repoName}/dispatches`;

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Scheme-Intel-Cloudflare-Gateway/1.0",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        event_type: eventType,
        client_payload: sanitizedPayload,
      }),
    });

    if (resp.status === 204) {
      safeLog("info", "github_dispatch_success", {
        repoOwner,
        repoName,
        eventType,
        requestId: clientPayload?.request_id,
        chatId: clientPayload?.chat_id,
      });
      return { success: true, status: 204 };
    }

    let errorDetail = "";
    try {
      const errJson = await resp.json();
      errorDetail = errJson.message || JSON.stringify(errJson);
    } catch {
      errorDetail = await resp.text();
    }

    let userFriendlyError = "GitHub Actions dispatch failed";
    if (resp.status === 401) {
      userFriendlyError = "GitHub Token invalid or expired";
    } else if (resp.status === 403) {
      userFriendlyError = "GitHub Token lacks permissions for repository_dispatch (requires repo / Actions:write)";
    } else if (resp.status === 404) {
      userFriendlyError = `Repository ${repoOwner}/${repoName} not found or token has no access`;
    } else if (resp.status === 422) {
      userFriendlyError = `Malformed dispatch payload: ${errorDetail}`;
    }

    safeLog("error", "github_dispatch_failed", {
      status: resp.status,
      error: errorDetail,
      requestId: clientPayload?.request_id,
      repo: `${repoOwner}/${repoName}`,
    });

    return {
      success: false,
      status: resp.status,
      error: userFriendlyError,
    };
  } catch (err) {
    safeLog("error", "github_network_error", {
      error: err.message,
      requestId: clientPayload?.request_id,
    });
    return {
      success: false,
      status: 500,
      error: `Network error connecting to GitHub: ${err.message}`,
    };
  }
}
