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
  COMPLEX_QUERY: "COMPLEX_QUERY",
  UNKNOWN: "UNKNOWN",
};

export const GLOBAL_STOCK_ALIASES = {
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
};

export function resolveStock(text) {
  if (!text) return null;
  const tokenClean = text.trim().toUpperCase().replace(/[^\w.]/g, "");
  return GLOBAL_STOCK_ALIASES[tokenClean] || null;
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

export function resolveIntent(message) {
  const raw = (message || "").trim();
  const normalized = normalizeQuery(raw);

  if (!raw) {
    return {
      intentType: IntentType.UNKNOWN,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: "gobardhan",
    };
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
          schemeId: "gobardhan",
        };
      case "/help":
        return {
          intentType: IntentType.HELP,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: "gobardhan",
        };
      case "/health":
        return {
          intentType: IntentType.HEALTH_CHECK,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: "gobardhan",
        };
      case "/setups":
        return {
          intentType: IntentType.SETUPS_LOOKUP,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: "gobardhan",
        };
      case "/waiting":
        return {
          intentType: IntentType.WAITING_LOOKUP,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: "gobardhan",
        };
      case "/watchlist":
        return {
          intentType: IntentType.WATCHLIST,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: "gobardhan",
        };
      case "/schemes":
        return {
          intentType: IntentType.SCHEMES,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: "gobardhan",
        };
      case "/scheme":
        return {
          intentType: IntentType.SCHEME_LOOKUP,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: remainder ? remainder.toLowerCase() : "gobardhan",
        };
      case "/performance":
        return {
          intentType: IntentType.PERFORMANCE_LOOKUP,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: "gobardhan",
        };
      case "/benchmark":
        return {
          intentType: IntentType.BENCHMARK_LOOKUP,
          executionPath: ExecutionPath.FAST,
          rawQuery: raw,
          normalizedQuery: normalized,
          schemeId: "gobardhan",
        };
      case "/research":
        return {
          intentType: IntentType.RESEARCH_REQUEST,
          executionPath: ExecutionPath.RESEARCH,
          rawQuery: raw,
          normalizedQuery: normalized,
          question: remainder,
          schemeId: "gobardhan",
        };
      case "/why": {
        const stock = resolveStock(remainder);
        if (!stock) {
          return {
            intentType: IntentType.STOCK_WHY_PROMPT,
            executionPath: ExecutionPath.FAST,
            rawQuery: raw,
            normalizedQuery: normalized,
            schemeId: "gobardhan",
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
            schemeId: "gobardhan",
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
            schemeId: "gobardhan",
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
      schemeId: primaryStock ? primaryStock.scheme : "gobardhan",
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
  if (normalized.includes("setup")) {
    return {
      intentType: IntentType.SETUPS_LOOKUP,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: "gobardhan",
    };
  }
  if (normalized.includes("waiting")) {
    return {
      intentType: IntentType.WAITING_LOOKUP,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: "gobardhan",
    };
  }
  if (normalized.includes("watchlist")) {
    return {
      intentType: IntentType.WATCHLIST,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: "gobardhan",
    };
  }
  if (normalized.includes("performance")) {
    return {
      intentType: IntentType.PERFORMANCE_LOOKUP,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: "gobardhan",
    };
  }
  if (normalized.includes("benchmark")) {
    return {
      intentType: IntentType.BENCHMARK_LOOKUP,
      executionPath: ExecutionPath.FAST,
      rawQuery: raw,
      normalizedQuery: normalized,
      schemeId: "gobardhan",
    };
  }

  // Default: Complex natural language query to WORKFLOW
  return {
    intentType: IntentType.COMPLEX_QUERY,
    executionPath: ExecutionPath.WORKFLOW,
    rawQuery: raw,
    normalizedQuery: normalized,
    schemeId: "gobardhan",
  };
}
