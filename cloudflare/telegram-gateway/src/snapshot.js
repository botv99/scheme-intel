/**
 * Snapshot Retrieval, Validation, and Terminal Card Renderers.
 * Consumes precomputed intelligence from GitHub raw content.
 */

let cachedSnapshot = null;
let lastFetchTime = 0;
const CACHE_TTL_MS = 300 * 1000; // 5 minutes cache

export const SnapshotStatus = {
  READY: "READY",
  STALE: "STALE",
  MISSING: "MISSING",
  INVALID: "INVALID",
};

/**
 * Fetch and validate the latest intelligence snapshot from GitHub raw URL.
 */
export async function getSnapshot(env, forceRefresh = false) {
  const now = Date.now();
  if (!forceRefresh && cachedSnapshot && now - lastFetchTime < CACHE_TTL_MS) {
    return cachedSnapshot;
  }

  const owner = env.GITHUB_OWNER || "botv99";
  const repo = env.GITHUB_REPO || "scheme-intel";
  const branch = env.GITHUB_BRANCH || "main";
  const path = env.SNAPSHOT_PATH || "data/intelligence/latest.json";
  const url = env.SNAPSHOT_URL || `https://raw.githubusercontent.com/${owner}/${repo}/${branch}/${path}`;

  try {
    const headers = { "User-Agent": "Scheme-Intel-Cloudflare-Gateway/1.0" };
    if (env.GITHUB_TOKEN) {
      headers["Authorization"] = `Bearer ${env.GITHUB_TOKEN}`;
    }

    const resp = await fetch(url, { headers });
    if (resp.status === 404) {
      return { status: SnapshotStatus.MISSING, snapshot: null, isStale: false, error: "Snapshot file not found (404)" };
    }
    if (!resp.ok) {
      return { status: SnapshotStatus.MISSING, snapshot: null, isStale: false, error: `HTTP ${resp.status}` };
    }

    const json = await resp.json();

    // Validate expected structure
    if (!json || typeof json !== "object" || !json.snapshot_id || !json.companies) {
      return { status: SnapshotStatus.INVALID, snapshot: null, isStale: false, error: "Snapshot missing required schema fields" };
    }

    // Check freshness: stale if older than 26 hours
    const genTime = new Date(json.generated_at).getTime();
    const ageHours = (now - genTime) / (3600 * 1000);
    const isStale = ageHours > 26;

    const result = {
      status: isStale ? SnapshotStatus.STALE : SnapshotStatus.READY,
      snapshot: json,
      isStale,
      ageHours: Math.round(ageHours * 10) / 10,
    };

    cachedSnapshot = result;
    lastFetchTime = now;
    return result;
  } catch (err) {
    return { status: SnapshotStatus.MISSING, snapshot: null, isStale: false, error: err.message };
  }
}

function staleBanner(isStale, updatedAt) {
  if (isStale) {
    const timeDisplay = updatedAt ? updatedAt.slice(0, 16) : "recent";
    return `⚠️ *DATA NOTE: Snapshot is >26h old (Last update: ${timeDisplay}).*\n\n`;
  }
  return "";
}

export function renderStockCard(comp, isStale = false) {
  const banner = staleBanner(isStale, comp.updated_at);
  const priceStr = comp.price != null ? `₹${Number(comp.price).toFixed(2)}` : "N/A";
  const changeStr = comp.change_pct != null ? `${comp.change_pct >= 0 ? "+" : ""}${Number(comp.change_pct).toFixed(2)}%` : "N/A";

  const lines = [
    `${banner}🏷️ *${comp.short_symbol || comp.symbol}*`,
    `_${comp.name}_`,
    "",
    `*Scheme:* ${comp.scheme_name || comp.scheme_id || "GOBARdhan"}`,
    `*Relevance:* ${comp.relevance || "High"}`,
    "",
    "*PRICE*",
    `${priceStr} (${changeStr})`,
  ];

  if (comp.trend || comp.support || comp.resistance || comp.rsi) {
    lines.push(
      "",
      "*TECHNICAL STATE*",
      `• Trend: ${comp.trend || "N/A"}`,
      comp.support ? `• Support: ₹${Number(comp.support).toFixed(2)}` : "• Support: N/A",
      comp.resistance ? `• Resistance: ₹${Number(comp.resistance).toFixed(2)}` : "• Resistance: N/A",
      comp.rsi ? `• RSI (14): ${Number(comp.rsi).toFixed(1)}` : "• RSI (14): N/A"
    );
  }

  lines.push("", `*CURRENT STATUS:* \`${comp.status || "NO_TRADE"}\``);

  if (comp.archetype) {
    lines.push(
      "",
      "*SETUP*",
      `• Archetype: ${comp.archetype}`,
      `• Score: ${comp.score != null ? comp.score : "N/A"}/100`,
      comp.trigger_price ? `• Trigger: ₹${Number(comp.trigger_price).toFixed(2)}` : "• Trigger: N/A",
      comp.stop_loss ? `• Stop Loss: ₹${Number(comp.stop_loss).toFixed(2)}` : "• Stop Loss: N/A",
      comp.target ? `• Target 1: ₹${Number(comp.target).toFixed(2)}` : "• Target 1: N/A"
    );
  }

  if (comp.bull_thesis || comp.bear_thesis) {
    lines.push(
      "",
      "*AI VIEW*",
      `• Bull: ${comp.bull_thesis ? (comp.bull_thesis.length > 140 ? comp.bull_thesis.slice(0, 140) + "..." : comp.bull_thesis) : "N/A"}`,
      `• Bear: ${comp.bear_thesis ? (comp.bear_thesis.length > 140 ? comp.bear_thesis.slice(0, 140) + "..." : comp.bear_thesis) : "N/A"}`
    );
  }

  if (comp.risk_summary) {
    lines.push("", `*RISK:* ${comp.risk_summary}`);
  }

  if (comp.waiting_conditions && comp.waiting_conditions.length > 0) {
    lines.push("", "*WAITING CONDITIONS*");
    for (const wc of comp.waiting_conditions.slice(0, 3)) {
      lines.push(`• ${wc}`);
    }
  }

  if (comp.updated_at) {
    lines.push("", `_Updated: ${comp.updated_at.slice(0, 16)} UTC_`);
  }

  return lines.join("\n");
}

export function renderWhyCard(comp, isStale = false) {
  const banner = staleBanner(isStale, comp.updated_at);
  const lines = [
    `${banner}❓ *WHY: ${comp.short_symbol || comp.symbol}*`,
    `_${comp.name}_`,
    "",
    `*Scheme:* ${comp.scheme_name || comp.scheme_id || "GOBARdhan"}`,
    `*Relevance:* ${comp.relevance || "High"}`,
    "",
    "*POLICY RATIONALE*",
    comp.mapping_rationale || "Company is directly positioned within government scheme implementation.",
  ];

  if (comp.latest_development || comp.catalyst) {
    lines.push("", "*LATEST CATALYST*", comp.latest_development || comp.catalyst);
  }

  return lines.join("\n");
}

export function renderWhatCard(comp, isStale = false) {
  const banner = staleBanner(isStale, comp.updated_at);
  const priceStr = comp.price != null ? `₹${Number(comp.price).toFixed(2)}` : "N/A";
  const changeStr = comp.change_pct != null ? `${comp.change_pct >= 0 ? "+" : ""}${Number(comp.change_pct).toFixed(2)}%` : "N/A";

  const lines = [
    `${banner}⚡ *WHAT: ${comp.short_symbol || comp.symbol}*`,
    `_${comp.name}_`,
    "",
    `*Status:* \`${comp.status || "NO_TRADE"}\` | *Price:* ${priceStr} (${changeStr})`,
    "",
    "*DEVELOPMENTS & CATALYSTS*",
    comp.latest_development || comp.catalyst || "No new major policy announcements in the latest scan.",
  ];

  if (comp.bull_thesis) {
    lines.push("", "*BULL CASE*", comp.bull_thesis);
  }
  if (comp.bear_thesis) {
    lines.push("", "*BEAR RISKS*", comp.bear_thesis);
  }

  return lines.join("\n");
}

export function renderWhenCard(comp, isStale = false) {
  const banner = staleBanner(isStale, comp.updated_at);
  const lines = [
    `${banner}⏱️ *WHEN: ${comp.short_symbol || comp.symbol}*`,
    `_${comp.name}_`,
    "",
    `*Current Status:* \`${comp.status || "NO_TRADE"}\``,
  ];

  if (comp.status === "QUALIFIED") {
    lines.push(
      "",
      "🟢 *ACTIONABLE TODAY*",
      `• Trigger Price: ₹${comp.trigger_price != null ? Number(comp.trigger_price).toFixed(2) : "N/A"}`,
      `• Stop Loss: ₹${comp.stop_loss != null ? Number(comp.stop_loss).toFixed(2) : "N/A"}`,
      `• Target 1: ₹${comp.target != null ? Number(comp.target).toFixed(2) : "N/A"}`
    );
  } else if (comp.status === "WAITING") {
    lines.push(
      "",
      "⏳ *TRIGGER CONDITIONS*",
      `• Key Level: ₹${comp.trigger_price != null ? Number(comp.trigger_price).toFixed(2) : "Watch support/resistance"}`
    );
    if (comp.waiting_conditions && comp.waiting_conditions.length > 0) {
      for (const wc of comp.waiting_conditions) {
        lines.push(`• ${wc}`);
      }
    }
  } else {
    lines.push(
      "",
      "🔴 *NO IMMEDIATE SETUP*",
      "Criteria for breakout or continuation not currently met. Awaiting structural catalyst or technical confirmation."
    );
  }

  return lines.join("\n");
}

export function renderSetupsCard(snapshot, isStale = false) {
  const banner = staleBanner(isStale, snapshot.generated_at);
  const setups = snapshot.qualified_setups || [];

  if (setups.length === 0) {
    return (
      `${banner}📊 *Scheme-Intel Daily Qualified Setups*\n\n` +
      `No setups qualified today across supported schemes.\n\n` +
      `_Risk gates strictly enforced (Market regime, volume, score threshold)._`
    );
  }

  const lines = [
    `${banner}📊 *Today's Qualified Setups* (${setups.length})`,
    "",
  ];

  for (const s of setups) {
    lines.push(
      `🎯 *${s.short_symbol || s.symbol}* (${s.archetype || "Swing"})`,
      `• Trigger: ₹${Number(s.trigger_price).toFixed(2)} | SL: ₹${Number(s.stop_loss).toFixed(2)} | T1: ₹${Number(s.target).toFixed(2)}`,
      `• Score: ${s.score || "N/A"}/100 | R:R: ${s.rr || "1:2+"}`,
      ""
    );
  }

  return lines.join("\n");
}

export function renderWaitingCard(snapshot, isStale = false) {
  const banner = staleBanner(isStale, snapshot.generated_at);
  const waiting = snapshot.waiting_setups || [];

  if (waiting.length === 0) {
    return (
      `${banner}⏳ *Scheme-Intel Waiting Setups*\n\n` +
      `No candidate setups are currently awaiting trigger conditions.`
    );
  }

  const lines = [
    `${banner}⏳ *Setups Waiting For Trigger* (${waiting.length})`,
    "",
  ];

  for (const w of waiting) {
    lines.push(
      `• *${w.short_symbol || w.symbol}*: Level ₹${w.trigger_price != null ? Number(w.trigger_price).toFixed(2) : "Watch"}`,
      w.condition ? `  _${w.condition}_` : ""
    );
  }

  return lines.join("\n");
}

export function renderWatchlistCard(snapshot, isStale = false) {
  const banner = staleBanner(isStale, snapshot.generated_at);
  const companies = Object.values(snapshot.companies || {})
    .filter((c, idx, arr) => arr.findIndex((x) => x.symbol === c.symbol) === idx);

  const lines = [
    `${banner}📋 *GOBARdhan Policy Watchlist* (${companies.length} stocks)`,
    "",
  ];

  for (const c of companies) {
    const priceStr = c.price != null ? `₹${Number(c.price).toFixed(2)}` : "N/A";
    const statusStr = c.status ? `\`${c.status}\`` : "`TRACKING`";
    lines.push(`• *${c.short_symbol || c.symbol}* — ${c.name}: ${priceStr} (${statusStr})`);
  }

  lines.push("", "_Type symbol (e.g. /gail or GAIL) for detailed analysis._");
  return lines.join("\n");
}

export function renderSchemesCard(snapshot, isStale = false) {
  const banner = staleBanner(isStale, snapshot.generated_at);
  const schemes = snapshot.schemes || {};

  const lines = [
    `${banner}🏛️ *Supported Government Schemes*`,
    "",
  ];

  for (const [sId, s] of Object.entries(schemes)) {
    lines.push(
      `• *${s.name}* (\`${sId}\`)`,
      `  _${s.description}_`,
      `  Watchlist: ${s.watchlist_count} companies | Setups: ${s.qualified_setups_count}`,
      ""
    );
  }

  lines.push("_Use /scheme <id> to inspect a specific policy scheme._");
  return lines.join("\n");
}

export function renderPerformanceCard(snapshot, isStale = false) {
  const banner = staleBanner(isStale, snapshot.generated_at);
  const p = snapshot.performance || {};

  return (
    `${banner}📈 *Forward Performance Analytics*\n\n` +
    `• Sample Status: \`${p.sample_status || "INITIALIZING"}\`\n` +
    `• Total Setups Tracked: ${p.total_setups != null ? p.total_setups : "N/A"}\n` +
    `• Realized Win Rate: ${p.win_rate != null ? p.win_rate + "%" : "N/A (insufficient completed sample)"}\n` +
    `• Profit Factor: ${p.profit_factor != null ? p.profit_factor : "N/A"}\n` +
    `• Average MFE: ${p.avg_mfe != null ? "+" + p.avg_mfe + "%" : "N/A"}\n` +
    `• Average MAE: ${p.avg_mae != null ? p.avg_mae + "%" : "N/A"}\n\n` +
    `_Updated daily via automated forward outcome tracking._`
  );
}

export function renderBenchmarkCard(snapshot, isStale = false) {
  const banner = staleBanner(isStale, snapshot.generated_at);
  const b = snapshot.benchmark || {};

  return (
    `${banner}🎯 *Benchmark Performance (vs Nifty 50)*\n\n` +
    `• Nifty 50 Trend: ${b.nifty_trend || "Neutral"}\n` +
    `• Strategy Alpha: ${b.alpha != null ? b.alpha + "%" : "N/A"}\n` +
    `• Beta vs Nifty: ${b.beta != null ? b.beta : "1.00"}\n` +
    `• Correlation: ${b.correlation != null ? b.correlation : "Low"}\n\n` +
    `_Performance is benchmarked against Nifty 50 index swings._`
  );
}

export function renderStartMenu() {
  return (
    `🚀 *Scheme-Intel Terminal Gateway*\n\n` +
    `Welcome! Instant conversational intelligence on Government Scheme beneficiaries.\n\n` +
    `*Quick Commands:*\n` +
    `• /setups — Today's qualified swing trade setups\n` +
    `• /waiting — Setups waiting for trigger level\n` +
    `• /watchlist — Monitored GOBARdhan companies\n` +
    `• /schemes — Supported government schemes\n` +
    `• /performance — Forward analytics & win rate\n` +
    `• /benchmark — Nifty 50 benchmark comparison\n\n` +
    `*Stock Cards:*\n` +
    `Type symbol directly: \`GAIL\`, \`Praj\`, \`TRUALT\`\n` +
    `Or slash shortcut: \`/gail\`, \`/praj\`, \`/trualt\`, \`/why trualt\``
  );
}

export function renderHelpMenu() {
  return (
    `📖 *Scheme-Intel Terminal Commands*\n\n` +
    `*Stock Analysis:*\n` +
    `• \`/gail\` or \`GAIL\` — Full intelligence card\n` +
    `• \`/why trualt\` — Policy relevance rationale\n` +
    `• \`/what praj\` — Current catalysts & technical state\n` +
    `• \`/when wabag\` — Actionable levels & trigger conditions\n\n` +
    `*System Views:*\n` +
    `• \`/setups\` — Today's qualified trade setups\n` +
    `• \`/waiting\` — Setups waiting for trigger\n` +
    `• \`/watchlist\` — All scheme stocks & prices\n` +
    `• \`/schemes\` — Supported policy frameworks\n` +
    `• \`/performance\` — Forward trade analytics\n\n` +
    `*Deep Complex Queries:*\n` +
    `Ask any comparative or multi-company question:\n` +
    `• _Compare TRUALT and PRAJ_\n` +
    `• _Which Gobardhan companies have the strongest catalysts?_\n` +
    `• \`/research <question>\` for asynchronous deep research.`
  );
}
