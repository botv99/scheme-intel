/**
 * GitHub API Client for Repository Dispatch.
 * Dispatches complex analytical queries from Cloudflare Worker to GitHub Actions.
 */
import { safeLog } from "./utils.js";

const GITHUB_API_BASE = "https://api.github.com";

/**
 * Trigger GitHub repository_dispatch event for 04-telegram-query.yml.
 * Endpoint: POST /repos/{owner}/{repo}/dispatches
 * Expected response: HTTP 204 No Content on success.
 */
export async function dispatchWorkflow(githubToken, repoOwner, repoName, eventType, clientPayload) {
  if (!githubToken) {
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

  const url = `${GITHUB_API_BASE}/repos/${repoOwner}/${repoName}/dispatches`;

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${githubToken}`,
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Scheme-Intel-Cloudflare-Gateway/1.0",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        event_type: eventType,
        client_payload: clientPayload,
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
