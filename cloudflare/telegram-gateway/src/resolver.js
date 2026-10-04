/**
 * Deterministic Intent & Entity Resolver for Cloudflare Telegram Gateway.
 * Fully compatible with Python IntentResolver in src/scheme_intel/intelligence_memory/resolver.py.
 */

export const ExecutionPath = {
  FAST: "FAST",
  WORKFLOW: "WORKFLOW",
  RESEARCH: "RESEARCH",
};

export const IntentType = {
  START: "START",
  HELP: "HELP",
  HEALTH_CHECK: "HEALTH_CHECK",
  SCHEMES: "SCHEMES",
  SCHEME_LOOKUP: "SCHEME_LOOKUP",
  WATCHLIST: "WATCHLIST",
  STOCK_LOOKUP: "STOCK_LOOKUP",
  STOCK_WHY: "STOCK_WHY",
  STOCK_WHAT: "STOCK_WHAT",
  STOCK_WHEN: "STOCK_WHEN",
  STOCK_WHY_PROMPT: "STOCK_WHY_PROMPT",
  STOCK_WHAT_PROMPT: "STOCK_WHAT_PROMPT",
  STOCK_WHEN_PROMPT: "STOCK_WHEN_PROMPT",
  SETUPS_LOOKUP: "SETUPS_LOOKUP",
  WAITING_LOOKUP: "WAITING_LOOKUP",
  PERFORMANCE_LOOKUP: "PERFORMANCE_LOOKUP",
  BENCHMARK_LOOKUP: "BENCHMARK_LOOKUP",
  RESEARCH_REQUEST: "RESEARCH_REQUEST",
  RESEARCH_PROMPT: "RESEARCH_PROMPT",
  INTELLIGENCE_LOOKUP: "INTELLIGENCE_LOOKUP",
  SWITCH_SCHEME: "SWITCH_SCHEME",
  SCHEME_MENU: "SCHEME_MENU",
  COMPLEX_QUERY: "COMPLEX_QUERY",
  STOCK_PROMPT: "STOCK_PROMPT",
  STOCK_UNKNOWN: "STOCK_UNKNOWN",
  ACTIVATE_KEY: "ACTIVATE_KEY",
  ENTER_KEY_PROMPT: "ENTER_KEY_PROMPT",
  PURCHASE_MENU: "PURCHASE_MENU",
  BUY_PRODUCT: "BUY_PRODUCT",
  BUY_SCHEME: "BUY_SCHEME",
  CHECK_ORDER: "CHECK_ORDER",
  AVAILABLE_SCHEMES: "AVAILABLE_SCHEMES",
  MY_ACCESS: "MY_ACCESS",
  ADMIN: "ADMIN",
  UNKNOWN: "UNKNOWN",
};

export const GLOBAL_STOCK_ALIASES = {
  // Gobardhan stocks
  "TRUALT": { symbol: "TRUALT.NS", short: "TRUALT", name: "TruAlt Bioenergy", scheme: "gobardhan" },
  "TRUALT.NS": { symbol: "TRUALT.NS", short: "TRUALT", name: "TruAlt Bioenergy", scheme: "gobardhan" },
  "TRUALT BIOENERGY": { symbol: "TRUALT.NS", short: "TRUALT", name: "TruAlt Bioenergy", scheme: "gobardhan" },
  "PRAJ": { symbol: "PRAJIND.NS", short: "PRAJIND", name: "Praj Industries", scheme: "gobardhan" },
  "PRAJIND": { symbol: "PRAJIND.NS", short: "PRAJIND", name: "Praj Industries", scheme: "gobardhan" },
  "PRAJIND.NS": { symbol: "PRAJIND.NS", short: "PRAJIND", name: "Praj Industries", scheme: "gobardhan" },
  "PRAJ INDUSTRIES": { symbol: "PRAJIND.NS", short: "PRAJIND", name: "Praj Industries", scheme: "gobardhan" },
  "WABAG": { symbol: "WABAG.NS", short: "WABAG", name: "VA Tech Wabag", scheme: "gobardhan" },
  "WABAG.NS": { symbol: "WABAG.NS", short: "WABAG", name: "VA Tech Wabag", scheme: "gobardhan" },
  "VA TECH WABAG": { symbol: "WABAG.NS", short: "WABAG", name: "VA Tech Wabag", scheme: "gobardhan" },
  "ORGANIC": { symbol: "ORGANICREC.BO", short: "ORGANICREC", name: "Organic Recycling Systems", scheme: "gobardhan" },
  "ORGANICREC": { symbol: "ORGANICREC.BO", short: "ORGANICREC", name: "Organic Recycling Systems", scheme: "gobardhan" },
  "ORGANICREC.BO": { symbol: "ORGANICREC.BO", short: "ORGANICREC", name: "Organic Recycling Systems", scheme: "gobardhan" },
  "ORGANIC RECYCLING SYSTEMS": { symbol: "ORGANICREC.BO", short: "ORGANICREC", name: "Organic Recycling Systems", scheme: "gobardhan" },
  "KIRLPN": { symbol: "KIRLPNU.NS", short: "KIRLPNU", name: "Kirloskar Pneumatic", scheme: "gobardhan" },
  "KIRLPNU": { symbol: "KIRLPNU.NS", short: "KIRLPNU", name: "Kirloskar Pneumatic", scheme: "gobardhan" },
  "KIRLPNU.NS": { symbol: "KIRLPNU.NS", short: "KIRLPNU", name: "Kirloskar Pneumatic", scheme: "gobardhan" },
  "KIRLOSKAR": { symbol: "KIRLPNU.NS", short: "KIRLPNU", name: "Kirloskar Pneumatic", scheme: "gobardhan" },
  "KIRLOSKAR PNEUMATIC": { symbol: "KIRLPNU.NS", short: "KIRLPNU", name: "Kirloskar Pneumatic", scheme: "gobardhan" },
  "GAIL": { symbol: "GAIL.NS", short: "GAIL", name: "GAIL (India)", scheme: "gobardhan" },
  "GAIL.NS": { symbol: "GAIL.NS", short: "GAIL", name: "GAIL (India)", scheme: "gobardhan" },
  "GAIL INDIA": { symbol: "GAIL.NS", short: "GAIL", name: "GAIL (India)", scheme: "gobardhan" },
  "IOC": { symbol: "IOC.NS", short: "IOC", name: "Indian Oil Corporation", scheme: "gobardhan" },
  "IOCL": { symbol: "IOC.NS", short: "IOC", name: "Indian Oil Corporation", scheme: "gobardhan" },
  "IOC.NS": { symbol: "IOC.NS", short: "IOC", name: "Indian Oil Corporation", scheme: "gobardhan" },
  "INDIAN OIL": { symbol: "IOC.NS", short: "IOC", name: "Indian Oil Corporation", scheme: "gobardhan" },
  "IONEXCHANG": { symbol: "IONEXCHANG.NS", short: "IONEXCHANG", name: "Ion Exchange", scheme: "gobardhan" },
  "IONEXCHANG.NS": { symbol: "IONEXCHANG.NS", short: "IONEXCHANG", name: "Ion Exchange", scheme: "gobardhan" },
  "ION EXCHANGE": { symbol: "IONEXCHANG.NS", short: "IONEXCHANG", name: "Ion Exchange", scheme: "gobardhan" },

  // Samudra Manthan stocks
  "ONGC": { symbol: "ONGC.NS", short: "ONGC", name: "Oil and Natural Gas Corporation", scheme: "samudra_manthan" },
  "ONGC.NS": { symbol: "ONGC.NS", short: "ONGC", name: "Oil and Natural Gas Corporation", scheme: "samudra_manthan" },
  "OIL": { symbol: "OIL.NS", short: "OIL", name: "Oil India Limited", scheme: "samudra_manthan" },
  "OIL.NS": { symbol: "OIL.NS", short: "OIL", name: "Oil India Limited", scheme: "samudra_manthan" },
  "OIL INDIA": { symbol: "OIL.NS", short: "OIL", name: "Oil India Limited", scheme: "samudra_manthan" },
  "RELIANCE": { symbol: "RELIANCE.NS", short: "RELIANCE", name: "Reliance Industries", scheme: "samudra_manthan" },
  "RIL": { symbol: "RELIANCE.NS", short: "RELIANCE", name: "Reliance Industries", scheme: "samudra_manthan" },
  "VEDANTA": { symbol: "VEDL.NS", short: "VEDL", name: "Vedanta Limited", scheme: "samudra_manthan" },
  "VEDL": { symbol: "VEDL.NS", short: "VEDL", name: "Vedanta Limited", scheme: "samudra_manthan" },
  "DEEPIND": { symbol: "DEEPINDS.NS", short: "DEEPINDS", name: "Deep Industries", scheme: "samudra_manthan" },
  "DEEP ENERGY": { symbol: "DEEPENR.NS", short: "DEEPENR", name: "Deep Energy Resources", scheme: "samudra_manthan" },
  "DOLPHIN": { symbol: "DOLPHINOFF.BO", short: "DOLPHINOFF", name: "Dolphin Offshore Enterprises", scheme: "samudra_manthan" },
  "ALPHAGEO": { symbol: "ALPHAGEO.NS", short: "ALPHAGEO", name: "Alphageo (India)", scheme: "samudra_manthan" },
  "ASIAN OIL": { symbol: "ASIANENE.NS", short: "ASIANENE", name: "Asian Energy Services", scheme: "samudra_manthan" },
  "HOEC": { symbol: "HINDOILEXP.NS", short: "HINDOILEXP", name: "Hindustan Oil Exploration Company", scheme: "samudra_manthan" },
};

const STOCK_SLASH_SHORTCUTS = {
  "/trualt": "TRUALT",
  "/praj": "PRAJ",
  "/prajind": "PRAJ",
  "/wabag": "WABAG",
  "/organic": "ORGANIC",
  "/organicrec": "ORGANICREC",
  "/kirloskar": "KIRLOSKAR",
  "/kirlpn": "KIRLPN",
  "/kirlpnu": "KIRLPNU",
  "/gail": "GAIL",
  "/ioc": "IOC",
  "/iocl": "IOC",
  "/ionexchang": "IONEXCHANG",
  "/ongc": "ONGC",
  "/oil": "OIL",
  "/reliance": "RELIANCE",
  "/ril": "RELIANCE",
  "/vedanta": "VEDANTA",
  "/vedl": "VEDANTA",
};

export function resolveStock(text) {
  if (!text) return null;
  const raw = text.trim().toUpperCase();
  const normalizedSpaces = raw.replace(/\s+/g, " ");

  // Direct alias match (e.g. "TRUALT", "PRAJ INDUSTRIES")
  if (GLOBAL_STOCK_ALIASES[normalizedSpaces]) {
    return GLOBAL_STOCK_ALIASES[normalizedSpaces];
  }

  // Without punctuation / special chars
  const tokenClean = raw.replace(/[^\w.]/g, "");
  if (GLOBAL_STOCK_ALIASES[tokenClean]) {
    return GLOBAL_STOCK_ALIASES[tokenClean];
  }

  // Match by full company name, symbol, or ticker
  for (const meta of Object.values(GLOBAL_STOCK_ALIASES)) {
    if (
      meta.name.toUpperCase() === normalizedSpaces ||
      meta.symbol.toUpperCase() === tokenClean ||
      meta.short.toUpperCase() === tokenClean
    ) {
      return meta;
    }
  }

  return null;
}

export function findAllStocksInText(text) {
  if (!text) return [];
  const found = new Map();
  const padded = ` ${text.toUpperCase()} `;

  for (const [aliasKey, meta] of Object.entries(GLOBAL_STOCK_ALIASES)) {
    if (padded.includes(` ${aliasKey} `)) {
      found.set(meta.symbol, meta);
    }
  }

  for (const word of text.split(/\s+/)) {
    const cleanWord = word.replace(/[^\w.]/g, "").toUpperCase();
    if (GLOBAL_STOCK_ALIASES[cleanWord]) {
      const meta = GLOBAL_STOCK_ALIASES[cleanWord];
      found.set(meta.symbol, meta);
    }
  }

  return Array.from(found.values());
}

export function normalizeQuery(text) {
  return (text || "").toLowerCase().trim().replace(/\s+/g, " ");
}

export function isComplexQuery(text) {
  const lowered = normalizeQuery(text);
  const stocks = findAllStocksInText(text);

  // Multi-stock comparison questions: "Compare TRUALT and PRAJ"
  if (stocks.length >= 2) {
    return true;
  }

  const complexPhrases = [
    "compare",
    "strongest catalyst",
    "strongest catalysts",
    "underperforming",
    "outperforming",
    "what changed in",
    "which companies have",
    "which gobardhan companies",
    "affected companies",
    "policy change",
    "catalyst this week",
    "catalysts this week",
    "rank",
    "ranking",
    "correlation",
    "versus",
    " vs ",
  ];

  for (const phrase of complexPhrases) {
    if (lowered.includes(phrase)) {
      return true;
    }
  }

  // If exactly 1 stock mentioned without complex phrasing, it is a fast stock lookup
  if (stocks.length === 1) {
    return false;
  }

  // General questions with >= 5 words that are not simple fast queries
  const words = text.trim().split(/\s+/);
  if (words.length >= 5 && (text.includes("?") || /^(which|why|how|what|who|where)\b/i.test(lowered))) {
    const simpleExclusions = [
      "what are today's setups",
      "what are the setups",
      "which stocks are waiting",
      "how is gobardhan doing",
      "what about trualt",
      "tell me about trualt",
      "what is happening with trualt",
      "why is trualt interesting",
      "when to enter trualt",
    ];
    if (!simpleExclusions.some((exc) => lowered.includes(exc))) {
      return true;
    }
  }

  return false;
}

export function resolveIntent(message, activeScheme = "gobardhan") {
  const raw = (message || "").trim();
  const normalized = normalizeQuery(raw);
  const effectiveScheme = (activeScheme || "gobardhan").trim().toLowerCase();

  if (!raw) {
    return {
      intentType: IntentType.UNKNOWN,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: effectiveScheme,
    };
  }

  // 0. Telegram Button Callbacks & Scheme Routing
  if (raw.startsWith("scheme_select:")) {
    const targetScheme = raw.split(":", 2)[1].trim().toLowerCase();
    return {
      intentType: IntentType.SWITCH_SCHEME,
      executionPath: ExecutionPath.FAST,
      schemeId: targetScheme,
      targetScheme,
      rawQuery: raw,
      normalizedQuery: normalized,
    };
  }

  if (raw.startsWith("scheme_action:")) {
    const parts = raw.split(":");
    const action = parts[1] ? parts[1].trim().toLowerCase() : "";
    const actionScheme = parts[2] ? parts[2].trim().toLowerCase() : effectiveScheme;
    if (action === "watchlist") {
      return { intentType: IntentType.WATCHLIST, executionPath: ExecutionPath.FAST, schemeId: actionScheme, rawQuery: raw, normalizedQuery: normalized };
    }
    if (action === "trades" || action === "setups") {
      return { intentType: IntentType.SETUPS_LOOKUP, executionPath: ExecutionPath.FAST, schemeId: actionScheme, rawQuery: raw, normalizedQuery: normalized };
    }
    if (action === "research") {
      return { intentType: IntentType.RESEARCH_PROMPT, executionPath: ExecutionPath.FAST, schemeId: actionScheme, rawQuery: raw, normalizedQuery: normalized };
    }
    if (action === "intelligence" || action === "news") {
      return { intentType: IntentType.INTELLIGENCE_LOOKUP, executionPath: ExecutionPath.FAST, schemeId: actionScheme, rawQuery: raw, normalizedQuery: normalized };
    }
    if (action === "snapshot" || action === "scheme") {
      return { intentType: IntentType.SCHEME_LOOKUP, executionPath: ExecutionPath.FAST, schemeId: actionScheme, rawQuery: raw, normalizedQuery: normalized };
    }
    if (action === "switch_scheme" || action === "switch" || action === "schemes") {
      return { intentType: IntentType.SCHEMES, executionPath: ExecutionPath.FAST, schemeId: effectiveScheme, rawQuery: raw, normalizedQuery: normalized };
    }
    if (action === "menu" || action === "back") {
      return { intentType: IntentType.SCHEME_MENU, executionPath: ExecutionPath.FAST, schemeId: actionScheme, rawQuery: raw, normalizedQuery: normalized };
    }
  }

  // Commercial Action Callbacks
  if (raw === "action:enter_key") {
    return { intentType: IntentType.ENTER_KEY_PROMPT, executionPath: ExecutionPath.FAST, rawQuery: raw, normalizedQuery: normalized, schemeId: effectiveScheme };
  }
  if (raw === "action:available_schemes" || raw === "available_schemes") {
    return { intentType: IntentType.AVAILABLE_SCHEMES, executionPath: ExecutionPath.FAST, rawQuery: raw, normalizedQuery: normalized, schemeId: effectiveScheme };
  }
  if (raw === "action:purchase_menu" || raw === "purchase_menu") {
    return { intentType: IntentType.PURCHASE_MENU, executionPath: ExecutionPath.FAST, rawQuery: raw, normalizedQuery: normalized, schemeId: effectiveScheme };
  }
  if (raw.startsWith("action:buy_scheme:")) {
    const sid = raw.split(":")[2] || effectiveScheme;
    return { intentType: IntentType.BUY_SCHEME, executionPath: ExecutionPath.FAST, schemeId: sid, targetScheme: sid, rawQuery: raw, normalizedQuery: normalized };
  }
  if (raw.startsWith("action:buy_product:")) {
    const pCode = raw.split(":")[2] || "";
    return { intentType: IntentType.BUY_PRODUCT, executionPath: ExecutionPath.FAST, productCode: pCode, rawQuery: raw, normalizedQuery: normalized, schemeId: effectiveScheme };
  }
  if (raw.startsWith("action:check_order:")) {
    const oCode = raw.split(":")[2] || "";
    return { intentType: IntentType.CHECK_ORDER, executionPath: ExecutionPath.FAST, orderCode: oCode, rawQuery: raw, normalizedQuery: normalized, schemeId: effectiveScheme };
  }
  if (raw === "my_access") {
    return { intentType: IntentType.MY_ACCESS, executionPath: ExecutionPath.FAST, rawQuery: raw, normalizedQuery: normalized, schemeId: effectiveScheme };
  }

  const parts = raw.split(/\s+/);
  const firstToken = parts[0].toLowerCase().split("@")[0];
  const remainder = raw.slice(parts[0].length).trim();

  // 1. Explicit Slash Shortcuts
  if (firstToken.startsWith("/")) {
    if (STOCK_SLASH_SHORTCUTS[firstToken]) {
      const meta = GLOBAL_STOCK_ALIASES[STOCK_SLASH_SHORTCUTS[firstToken]];
      return {
        intentType: IntentType.STOCK_LOOKUP,
        executionPath: ExecutionPath.FAST,
        symbol: meta.symbol,
        shortSymbol: meta.short,
        companyName: meta.name,
        schemeId: meta.scheme,
        rawQuery: raw,
        normalizedQuery: normalized,
      };
    }

    switch (firstToken) {
      case "/start":
        return {
          intentType: IntentType.START,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/activate":
        return {
          intentType: IntentType.ACTIVATE_KEY,
          executionPath: ExecutionPath.FAST,
          key: remainder,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/purchase":
        return {
          intentType: IntentType.PURCHASE_MENU,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/status":
      case "/access":
        return {
          intentType: IntentType.MY_ACCESS,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/admin":
        return {
          intentType: IntentType.ADMIN,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/help":
        return {
          intentType: IntentType.HELP,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/health":
        return {
          intentType: IntentType.HEALTH_CHECK,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/stock": {
        if (!remainder) {
          return {
            intentType: IntentType.STOCK_PROMPT,
            executionPath: ExecutionPath.FAST,
            rawQuery: raw,
            normalizedQuery: normalized,
            schemeId: effectiveScheme,
          };
        }
        const stock = resolveStock(remainder);
        if (stock) {
          return {
            intentType: IntentType.STOCK_LOOKUP,
            executionPath: ExecutionPath.FAST,
            symbol: stock.symbol,
            shortSymbol: stock.short,
            companyName: stock.name,
            schemeId: stock.scheme,
            rawQuery: raw,
            normalizedQuery: normalized,
          };
        }
        // Unknown stock - still FAST path!
        return {
          intentType: IntentType.STOCK_LOOKUP,
          executionPath: ExecutionPath.FAST,
          symbol: remainder.trim().toUpperCase(),
          shortSymbol: remainder.trim().toUpperCase(),
          schemeId: effectiveScheme,
          rawQuery: raw,
          normalizedQuery: normalized,
          isUnknownCandidate: true,
        };
      }
      case "/setups":
        return {
          intentType: IntentType.SETUPS_LOOKUP,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/waiting":
        return {
          intentType: IntentType.WAITING_LOOKUP,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/watchlist":
        return {
          intentType: IntentType.WATCHLIST,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/schemes":
        return {
          intentType: IntentType.SCHEMES,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/menu":
        return {
          intentType: IntentType.SCHEME_MENU,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/switch": {
        const target = remainder ? remainder.toLowerCase().replace(/[^a-z0-9_]/g, "") : "";
        if (target === "gobardhan" || target === "samudra_manthan" || target === "samudra") {
          const canonical = target === "samudra" ? "samudra_manthan" : target;
          return {
            intentType: IntentType.SWITCH_SCHEME,
            executionPath: ExecutionPath.FAST,
            schemeId: canonical,
            targetScheme: canonical,
            rawQuery: raw,
            normalizedQuery: normalized,
          };
        }
        return {
          intentType: IntentType.SCHEMES,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      }
      case "/scheme": {
        const reqScheme = remainder ? remainder.toLowerCase().trim() : effectiveScheme;
        const canonical = reqScheme === "samudra" ? "samudra_manthan" : reqScheme;
        return {
          intentType: IntentType.SCHEME_LOOKUP,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: canonical || effectiveScheme,
        };
      }
      case "/performance":
        return {
          intentType: IntentType.PERFORMANCE_LOOKUP,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/benchmark":
        return {
          intentType: IntentType.BENCHMARK_LOOKUP,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: effectiveScheme,
        };
      case "/research":
        return {
          intentType: IntentType.RESEARCH_REQUEST,
          executionPath: ExecutionPath.RESEARCH,
          rawQuery: raw,
          normalizedQuery: normalized,
          question: remainder,
          schemeId: effectiveScheme,
        };
      case "/why": {
        const stock = resolveStock(remainder);
        if (!stock) {
          return {
            intentType: IntentType.STOCK_WHY_PROMPT,
            executionPath: ExecutionPath.FAST,
            rawQuery: raw,
            normalizedQuery: normalized,
            schemeId: effectiveScheme,
          };
        }
        return {
          intentType: IntentType.STOCK_WHY,
          executionPath: ExecutionPath.FAST,
          symbol: stock.symbol,
          shortSymbol: stock.short,
          companyName: stock.name,
          schemeId: stock.scheme,
          rawQuery: raw,
          normalizedQuery: normalized,
        };
      }
      case "/what": {
        const stock = resolveStock(remainder);
        if (!stock) {
          return {
            intentType: IntentType.STOCK_WHAT_PROMPT,
            executionPath: ExecutionPath.FAST,
            rawQuery: raw,
            normalizedQuery: normalized,
            schemeId: effectiveScheme,
          };
        }
        return {
          intentType: IntentType.STOCK_WHAT,
          executionPath: ExecutionPath.FAST,
          symbol: stock.symbol,
          shortSymbol: stock.short,
          companyName: stock.name,
          schemeId: stock.scheme,
          rawQuery: raw,
          normalizedQuery: normalized,
        };
      }
      case "/when": {
        const stock = resolveStock(remainder);
        if (!stock) {
          return {
            intentType: IntentType.STOCK_WHEN_PROMPT,
            executionPath: ExecutionPath.FAST,
            rawQuery: raw,
            normalizedQuery: normalized,
            schemeId: effectiveScheme,
          };
        }
        return {
          intentType: IntentType.STOCK_WHEN,
          executionPath: ExecutionPath.FAST,
          symbol: stock.symbol,
          shortSymbol: stock.short,
          companyName: stock.name,
          schemeId: stock.scheme,
          rawQuery: raw,
          normalizedQuery: normalized,
        };
      }
    }
  }

  // 2. Direct stock symbol shorthand: "GAIL", "Praj", "TRUALT"
  const directStock = resolveStock(raw);
  if (directStock) {
    return {
      intentType: IntentType.STOCK_LOOKUP,
      executionPath: ExecutionPath.FAST,
      symbol: directStock.symbol,
      shortSymbol: directStock.short,
      companyName: directStock.name,
      schemeId: directStock.scheme,
      rawQuery: raw,
      normalizedQuery: normalized,
    };
  }

  // 3. Complex Query Detection -> WORKFLOW
  if (isComplexQuery(raw)) {
    const stocks = findAllStocksInText(raw);
    const primaryStock = stocks.length > 0 ? stocks[0] : null;
    return {
      intentType: IntentType.COMPLEX_QUERY,
      executionPath: ExecutionPath.WORKFLOW,
      symbol: primaryStock ? primaryStock.symbol : null,
      shortSymbol: primaryStock ? primaryStock.short : null,
      schemeId: primaryStock ? primaryStock.scheme : effectiveScheme,
      rawQuery: raw,
      normalizedQuery: normalized,
    };
  }

  // 4. Natural language why / what / when queries for single stock
  const stocks = findAllStocksInText(raw);
  if (stocks.length === 1) {
    const stock = stocks[0];
    if (/\bwhy\b/i.test(normalized)) {
      return {
        intentType: IntentType.STOCK_WHY,
        executionPath: ExecutionPath.FAST,
        symbol: stock.symbol,
        shortSymbol: stock.short,
        companyName: stock.name,
        schemeId: stock.scheme,
        rawQuery: raw,
        normalizedQuery: normalized,
      };
    }
    if (/\bwhat\b/i.test(normalized)) {
      return {
        intentType: IntentType.STOCK_WHAT,
        executionPath: ExecutionPath.FAST,
        symbol: stock.symbol,
        shortSymbol: stock.short,
        companyName: stock.name,
        schemeId: stock.scheme,
        rawQuery: raw,
        normalizedQuery: normalized,
      };
    }
    if (/\bwhen\b/i.test(normalized)) {
      return {
        intentType: IntentType.STOCK_WHEN,
        executionPath: ExecutionPath.FAST,
        symbol: stock.symbol,
        shortSymbol: stock.short,
        companyName: stock.name,
        schemeId: stock.scheme,
        rawQuery: raw,
        normalizedQuery: normalized,
      };
    }
    return {
      intentType: IntentType.STOCK_LOOKUP,
      executionPath: ExecutionPath.FAST,
      symbol: stock.symbol,
      shortSymbol: stock.short,
      companyName: stock.name,
      schemeId: stock.scheme,
      rawQuery: raw,
      normalizedQuery: normalized,
    };
  }

  // 5. Keyword fallbacks
  if (normalized.includes("scheme") || normalized.includes("switch")) {
    return {
      intentType: IntentType.SCHEMES,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: effectiveScheme,
    };
  }
  if (normalized === "menu" || normalized.includes("main menu") || normalized.includes("scheme menu")) {
    return {
      intentType: IntentType.SCHEME_MENU,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: effectiveScheme,
    };
  }
  if (normalized.includes("setup") || normalized.includes("trade")) {
    return {
      intentType: IntentType.SETUPS_LOOKUP,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: effectiveScheme,
    };
  }
  if (normalized.includes("waiting")) {
    return {
      intentType: IntentType.WAITING_LOOKUP,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: effectiveScheme,
    };
  }
  if (normalized.includes("watchlist")) {
    return {
      intentType: IntentType.WATCHLIST,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: effectiveScheme,
    };
  }
  if (normalized.includes("performance")) {
    return {
      intentType: IntentType.PERFORMANCE_LOOKUP,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: effectiveScheme,
    };
  }
  if (normalized.includes("benchmark")) {
    return {
      intentType: IntentType.BENCHMARK_LOOKUP,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: effectiveScheme,
    };
  }
  if (normalized.includes("intelligence") || normalized.includes("news")) {
    return {
      intentType: IntentType.INTELLIGENCE_LOOKUP,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: effectiveScheme,
    };
  }
  if (normalized.includes("research")) {
    return {
      intentType: IntentType.RESEARCH_PROMPT,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: effectiveScheme,
    };
  }

  // Default: Complex natural language query to WORKFLOW
  return {
    intentType: IntentType.COMPLEX_QUERY,
    executionPath: ExecutionPath.WORKFLOW,
    rawQuery: raw,
    normalizedQuery: normalized,
    schemeId: effectiveScheme,
  };
}
