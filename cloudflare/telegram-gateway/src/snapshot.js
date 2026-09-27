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

export function parseDateOnly(dateInput) {
  if (!dateInput) return null;
  if (typeof dateInput === "string") {
    const match = dateInput.trim().match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!match) return null;
    const year = parseInt(match[1], 10);
    const month = parseInt(match[2], 10) - 1;
    const day = parseInt(match[3], 10);
    const d = new Date(Date.UTC(year, month, day));
    if (isNaN(d.getTime())) return null;
    return d;
  }
  if (dateInput instanceof Date) {
    if (isNaN(dateInput.getTime())) return null;
    return new Date(Date.UTC(dateInput.getUTCFullYear(), dateInput.getUTCMonth(), dateInput.getUTCDate()));
  }
  return null;
}

export function isRecentNews(item, currentDate = new Date()) {
  if (!item || typeof item !== "object") return false;
  const rawDate = item.date || item.published_at || item.publishedAt;
  if (!rawDate || typeof rawDate !== "string") return false;

  const itemDate = parseDateOnly(rawDate);
  const refDate = parseDateOnly(currentDate);

  if (!itemDate || !refDate) return false;

  const msPerDay = 24 * 60 * 60 * 1000;
  const diffDays = Math.round((refDate.getTime() - itemDate.getTime()) / msPerDay);

  // Allowed: today (0) or yesterday (1).
  // Rejected: future (diffDays < 0), older than yesterday (diffDays > 1).
  return diffDays === 0 || diffDays === 1;
}

export function renderStockCard(comp, snapshot = null, isStale = false) {
  // Support both (comp, snapshot, isStale) and legacy (comp, isStale)
  if (typeof snapshot === "boolean") {
    isStale = snapshot;
    snapshot = null;
  }

  const banner = staleBanner(isStale, comp.updated_at || snapshot?.generated_at);
  const snapshotDate = snapshot?.generated_at || comp.updated_at || new Date().toISOString();

  // 1. STOCK IDENTITY
  const lines = [
    `${banner}🏷️ *${comp.symbol || comp.short_symbol}*`,
    `_${comp.name}_`,
    "",
    `*Scheme:* ${comp.scheme_name || comp.scheme_id || "GOBARdhan"}`,
    `*Relevance:* ${comp.relevance || "High"}`,
    "",
    // 2. PRICE
    "*PRICE*",
    `Current Price: ${comp.price != null ? `₹${Number(comp.price).toFixed(2)}` : "N/A"}`,
    `Today's Change: ${comp.change_pct != null ? `${comp.change_pct >= 0 ? "+" : ""}${Number(comp.change_pct).toFixed(2)}%` : "N/A"}`,
    "",
    // 3. VOLUME
    "*VOLUME*",
    `Volume: ${comp.volume != null ? Number(comp.volume).toLocaleString("en-IN") : "N/A"}`,
  ];

  let volumeChangeStr = "N/A";
  if (comp.volume != null && comp.avg_volume != null && comp.avg_volume > 0) {
    const vChange = ((comp.volume - comp.avg_volume) / comp.avg_volume) * 100;
    volumeChangeStr = `${vChange >= 0 ? "+" : ""}${vChange.toFixed(1)}% vs 20D avg`;
  }
  lines.push(`Volume Change: ${volumeChangeStr}`);

  // 4. FUNDAMENTAL SCORE
  lines.push("", "*FUNDAMENTAL SCORE*");
  const fundVal = comp.fundamental_intelligence_score != null ? comp.fundamental_intelligence_score : comp.fundamental_score;
  if (fundVal != null) {
    const covStr = comp.fundamental_score_coverage != null ? ` | Coverage: ${Math.round(comp.fundamental_score_coverage)}%` : "";
    const asOfStr = comp.fundamental_score_data_as_of ? ` | As of: ${comp.fundamental_score_data_as_of}` : "";
    lines.push(`Fundamental Score: ${Number(fundVal).toFixed(1)}/10${covStr}${asOfStr}`);
    if (comp.fundamental_score_components && typeof comp.fundamental_score_components === "object") {
      const parts = [];
      for (const k of ["growth", "profitability", "balance_sheet", "cash_flow"]) {
        const item = comp.fundamental_score_components[k];
        if (item && item.score != null) {
          const label = k.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
          parts.push(`${label}: ${Number(item.score).toFixed(1)}`);
        }
      }
      if (parts.length > 0) {
        lines.push(`• ${parts.join(" | ")}`);
      }
    }
  } else {
    lines.push("Fundamental Score: N/A\nReason: Fundamental scoring not available in current snapshot.");
  }

  // 5. TECHNICAL / INTELLIGENCE SCORE
  lines.push("", "*TECHNICAL INTELLIGENCE*");
  const techVal = comp.technical_intelligence_score != null ? comp.technical_intelligence_score : (comp.score != null ? comp.score / 10 : null);
  if (techVal != null) {
    const covStr = comp.technical_score_coverage != null ? ` | Coverage: ${Math.round(comp.technical_score_coverage)}%` : "";
    const asOfStr = comp.technical_score_data_as_of ? ` | As of: ${comp.technical_score_data_as_of}` : "";
    lines.push(`Technical / Intel Score: ${Number(techVal).toFixed(1)}/10${covStr}${asOfStr}`);
    if (comp.technical_score_components && typeof comp.technical_score_components === "object") {
      const parts = [];
      for (const k of ["trend", "momentum", "structure", "volume"]) {
        const item = comp.technical_score_components[k];
        if (item && item.score != null) {
          const label = k.charAt(0).toUpperCase() + k.slice(1);
          parts.push(`${label}: ${Number(item.score).toFixed(1)}`);
        }
      }
      if (parts.length > 0) {
        lines.push(`• ${parts.join(" | ")}`);
      }
    }
  } else {
    lines.push("Technical / Intel Score: N/A");
  }

  // 6. TODAY'S CATALYST
  lines.push("", "*TODAY'S CATALYST*");
  let catalystRendered = false;
  if (comp.catalysts && Array.isArray(comp.catalysts) && comp.catalysts.length > 0) {
    for (const c of comp.catalysts) {
      lines.push(`• ${typeof c === "string" ? c : c.catalyst_name || c.headline || ""}`);
    }
    catalystRendered = true;
  } else if (comp.catalyst) {
    lines.push(`• ${comp.catalyst}`);
    catalystRendered = true;
  } else if (comp.latest_development && comp.status !== "NO_TRADE") {
    lines.push(`• ${comp.latest_development}`);
    catalystRendered = true;
  }
  if (!catalystRendered) {
    lines.push("No major catalyst detected in the latest scan.");
  }

  // 7. NEWS
  lines.push("", "*NEWS*");
  const allNews = comp.evidence || comp.news || [];
  const recentNews = allNews.filter((item) => isRecentNews(item, snapshotDate)).slice(0, 5);
  if (recentNews.length > 0) {
    for (const n of recentNews) {
      const headline = n.title || n.headline || "News Update";
      const source = n.source ? ` — _${n.source}_` : "";
      const link = n.url ? `\n  ${n.url}` : "";
      lines.push(`• ${headline}${source}${link}`);
    }
  } else {
    lines.push("No relevant news from today/yesterday.");
  }

  // 8. TRADE SETUP STATUS
  lines.push("", "*TRADE SETUP*", `Status: \`${comp.status || "NO_TRADE"}\``);
  if (comp.status === "QUALIFIED_SETUP" || comp.status === "WAIT") {
    if (comp.archetype) lines.push(`• Archetype: ${comp.archetype}`);
    if (comp.score != null) lines.push(`• Score: ${comp.score}/100`);
    if (comp.trigger_price != null) lines.push(`• Trigger: ₹${Number(comp.trigger_price).toFixed(2)}`);
    if (comp.stop_loss != null) lines.push(`• Stop Loss: ₹${Number(comp.stop_loss).toFixed(2)}`);
    if (comp.target != null) lines.push(`• Target: ₹${Number(comp.target).toFixed(2)}`);
  }

  // 9. DATA TIMESTAMP
  const updatedStr = comp.updated_at ? comp.updated_at.slice(0, 16).replace("T", " ") + " UTC" : "N/A";
  const snapId = snapshot?.snapshot_id || comp.snapshot_id || "N/A";
  const statusStr = isStale ? "⚠️ STALE (>26h)" : "🟢 FRESH";
  lines.push(
    "",
    "---",
    `• Updated: ${updatedStr}`,
    `• Snapshot: \`${snapId}\``,
    `• Data Status: ${statusStr}`
  );

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

  lines.push("", "_Use /stock <symbol> (e.g. /stock GAIL) to view the stock intelligence card._");
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
    `🚀 *Scheme-Intel Terminal*\n\n` +
    `*Quick Commands:*\n` +
    `• /stock <symbol> — Full stock intelligence card\n` +
    `• /setups — Today's qualified setups\n` +
    `• /watchlist — Monitored stocks\n` +
    `• /research <question> — Deep policy research\n` +
    `• /help — Command guide`
  );
}

export function renderHelpMenu() {
  return (
    `📖 *Scheme-Intel Terminal Commands*\n\n` +
    `*Quick Commands:*\n` +
    `• \`/stock <symbol>\` — Full stock intelligence card (e.g. \`/stock GAIL\`, \`/stock TRUALT\`)\n` +
    `• \`/setups\` — Today's qualified swing trade setups\n` +
    `• \`/watchlist\` — Monitored scheme watchlist stocks\n` +
    `• \`/help\` — Command guide\n\n` +
    `*Deep Research & Analysis:*\n` +
    `• \`/research <question>\` — Asynchronous deep policy research\n` +
    `• Natural language questions (e.g. _Compare TRUALT and PRAJ_)`
  );
}
