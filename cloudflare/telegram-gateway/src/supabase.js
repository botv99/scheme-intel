/**
 * Supabase PostgREST Client for Cloudflare Workers.
 * Zero-dependency, lightweight HTTP client with query builder and in-memory mock support.
 */

import { safeLog } from "./utils.js";

class PostgrestQueryBuilder {
  constructor(client, table) {
    this.client = client;
    this.table = table;
    this.method = "GET";
    this.body = null;
    this.headers = {};
    this.params = new URLSearchParams();
    this.isSingle = false;
    this.isMaybeSingle = false;
  }

  select(columns = "*") {
    this.method = "GET";
    this.params.set("select", columns);
    return this;
  }

  insert(values, options = {}) {
    this.method = "POST";
    this.body = values;
    this.headers["Prefer"] = options.upsert
      ? `resolution=merge-duplicates,return=representation`
      : "return=representation";
    return this;
  }

  upsert(values, options = {}) {
    this.method = "POST";
    this.body = values;
    const resolution = options.ignoreDuplicates ? "ignore-duplicates" : "merge-duplicates";
    let prefer = `resolution=${resolution},return=representation`;
    if (options.onConflict) {
      this.params.set("on_conflict", options.onConflict);
    }
    this.headers["Prefer"] = prefer;
    return this;
  }

  update(values) {
    this.method = "PATCH";
    this.body = values;
    this.headers["Prefer"] = "return=representation";
    return this;
  }

  delete() {
    this.method = "DELETE";
    this.headers["Prefer"] = "return=representation";
    return this;
  }

  eq(column, value) {
    this.params.append(column, `eq.${value}`);
    return this;
  }

  neq(column, value) {
    this.params.append(column, `neq.${value}`);
    return this;
  }

  gt(column, value) {
    this.params.append(column, `gt.${value}`);
    return this;
  }

  gte(column, value) {
    this.params.append(column, `gte.${value}`);
    return this;
  }

  lt(column, value) {
    this.params.append(column, `lt.${value}`);
    return this;
  }

  lte(column, value) {
    this.params.append(column, `lte.${value}`);
    return this;
  }

  in(column, values) {
    const list = Array.isArray(values) ? values.join(",") : values;
    this.params.append(column, `in.(${list})`);
    return this;
  }

  order(column, options = {}) {
    const dir = options.ascending ? "asc" : "desc";
    this.params.set("order", `${column}.${dir}`);
    return this;
  }

  limit(count) {
    this.params.set("limit", String(count));
    return this;
  }

  single() {
    this.isSingle = true;
    this.headers["Accept"] = "application/vnd.pgrst.object+json";
    return this;
  }

  maybeSingle() {
    this.isMaybeSingle = true;
    return this;
  }

  async execute() {
    // Check if in mock / test memory mode
    if (this.client.mockStore) {
      return this.client.mockStore.handleQuery(this);
    }

    if (!this.client.url || !this.client.serviceRoleKey) {
      return { data: null, error: new Error("Supabase credentials not configured in environment") };
    }

    const endpoint = `${this.client.url}/rest/v1/${this.table}?${this.params.toString()}`;
    const reqHeaders = {
      "apikey": this.client.serviceRoleKey,
      "Authorization": `Bearer ${this.client.serviceRoleKey}`,
      "Content-Type": "application/json",
      ...this.headers,
    };

    try {
      const response = await fetch(endpoint, {
        method: this.method,
        headers: reqHeaders,
        body: this.body ? JSON.stringify(this.body) : undefined,
      });

      if (!response.ok) {
        let errBody;
        try {
          errBody = await response.json();
        } catch {
          errBody = await response.text();
        }
        return { data: null, error: errBody, status: response.status };
      }

      const text = await response.text();
      let data = text ? JSON.parse(text) : null;

      if (this.isMaybeSingle) {
        if (Array.isArray(data)) {
          data = data.length > 0 ? data[0] : null;
        }
      }

      return { data, error: null, status: response.status };
    } catch (err) {
      safeLog("error", "supabase_http_error", { table: this.table, error: err.message });
      return { data: null, error: err };
    }
  }

  then(resolve, reject) {
    return this.execute().then(resolve, reject);
  }
}

/**
 * In-memory Mock Store for local tests and deterministic verification.
 */
export class MockSupabaseStore {
  constructor() {
    this.tables = {
      users: [],
      schemes: [
        { id: "s-1", scheme_id: "gobardhan", name: "GOBARdhan", description: "National Circular Bioenergy Scheme", status: "ACTIVE" },
        { id: "s-2", scheme_id: "samudra_manthan", name: "Samudra Manthan", description: "Deepwater & Ultra-Deepwater E&P Mission", status: "ACTIVE" },
        { id: "s-3", scheme_id: "green_hydrogen", name: "Green Hydrogen", description: "National Green Hydrogen Mission", status: "COMING_SOON" },
        { id: "s-4", scheme_id: "solar_mission", name: "Solar Mission", description: "PM Surya Ghar & Solar Mission", status: "COMING_SOON" },
      ],
      access_keys: [],
      key_entitlements: [],
      user_scheme_entitlements: [],
      products: [
        { id: "p-1", product_code: "GOBARDHAN_MONTHLY", name: "GOBARdhan — Monthly", price_inr: 499, duration_days: 30, schemes: ["gobardhan"], status: "ACTIVE" },
        { id: "p-2", product_code: "GOBARDHAN_YEARLY", name: "GOBARdhan — Yearly", price_inr: 4999, duration_days: 365, schemes: ["gobardhan"], status: "ACTIVE" },
        { id: "p-3", product_code: "SAMUDRA_MONTHLY", name: "Samudra Manthan — Monthly", price_inr: 499, duration_days: 30, schemes: ["samudra_manthan"], status: "ACTIVE" },
        { id: "p-4", product_code: "SAMUDRA_YEARLY", name: "Samudra Manthan — Yearly", price_inr: 4999, duration_days: 365, schemes: ["samudra_manthan"], status: "ACTIVE" },
        { id: "p-5", product_code: "ALL_ACCESS_MONTHLY", name: "All Access — Monthly", price_inr: 799, duration_days: 30, schemes: ["gobardhan", "samudra_manthan"], status: "ACTIVE" },
        { id: "p-6", product_code: "ALL_ACCESS_YEARLY", name: "All Access — Yearly", price_inr: 7999, duration_days: 365, schemes: ["gobardhan", "samudra_manthan"], status: "ACTIVE" },
      ],
      orders: [],
      payment_events: [],
      audit_events: [],
    };
  }

  handleQuery(qb) {
    if (!this.tables[qb.table]) {
      this.tables[qb.table] = [];
    }
    const tableData = this.tables[qb.table];

    // Filter rows based on params
    const filters = [];
    for (const [key, val] of qb.params.entries()) {
      if (key === "select" || key === "order" || key === "limit" || key === "on_conflict") continue;
      if (val.startsWith("eq.")) {
        filters.push({ col: key, op: "eq", val: val.slice(3) });
      } else if (val.startsWith("neq.")) {
        filters.push({ col: key, op: "neq", val: val.slice(4) });
      } else if (val.startsWith("gt.")) {
        filters.push({ col: key, op: "gt", val: val.slice(3) });
      } else if (val.startsWith("gte.")) {
        filters.push({ col: key, op: "gte", val: val.slice(4) });
      } else if (val.startsWith("lt.")) {
        filters.push({ col: key, op: "lt", val: val.slice(3) });
      } else if (val.startsWith("lte.")) {
        filters.push({ col: key, op: "lte", val: val.slice(4) });
      } else if (val.startsWith("in.(") && val.endsWith(")")) {
        const items = val.slice(4, -1).split(",").map((s) => s.trim());
        filters.push({ col: key, op: "in", val: items });
      }
    }

    const matchesFilter = (row) => {
      for (const f of filters) {
        const rowVal = row[f.col] !== undefined && row[f.col] !== null ? String(row[f.col]) : null;
        if (f.op === "eq" && rowVal !== f.val) return false;
        if (f.op === "neq" && rowVal === f.val) return false;
        if (f.op === "in" && !f.val.includes(rowVal)) return false;
        if (f.op === "gt" && !(row[f.col] > f.val)) return false;
        if (f.op === "gte" && !(row[f.col] >= f.val)) return false;
        if (f.op === "lt" && !(row[f.col] < f.val)) return false;
        if (f.op === "lte" && !(row[f.col] <= f.val)) return false;
      }
      return true;
    };

    if (qb.method === "GET") {
      let result = tableData.filter(matchesFilter).map((r) => ({ ...r }));
      const orderParam = qb.params.get("order");
      if (orderParam) {
        const [col, dir] = orderParam.split(".");
        result.sort((a, b) => {
          if (a[col] < b[col]) return dir === "asc" ? -1 : 1;
          if (a[col] > b[col]) return dir === "asc" ? 1 : -1;
          return 0;
        });
      }
      const limitParam = qb.params.get("limit");
      if (limitParam) {
        result = result.slice(0, parseInt(limitParam, 10));
      }
      if (qb.isSingle) {
        if (result.length === 0) return { data: null, error: { message: "No rows found" }, status: 406 };
        return { data: result[0], error: null, status: 200 };
      }
      if (qb.isMaybeSingle) {
        return { data: result.length > 0 ? result[0] : null, error: null, status: 200 };
      }
      return { data: result, error: null, status: 200 };
    }

    if (qb.method === "POST") {
      const items = Array.isArray(qb.body) ? qb.body : [qb.body];
      const inserted = [];
      const onConflictCol = qb.params.get("on_conflict");

      for (const item of items) {
        const nowStr = new Date().toISOString();
        const record = {
          id: item.id || `mock-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          created_at: nowStr,
          updated_at: nowStr,
          ...item,
        };

        if (onConflictCol) {
          const cols = onConflictCol.split(",").map((s) => s.trim());
          const conflictIdx = tableData.findIndex((r) =>
            cols.every((col) => r[col] !== undefined && r[col] === item[col])
          );
          if (conflictIdx >= 0) {
            tableData[conflictIdx] = { ...tableData[conflictIdx], ...item, updated_at: nowStr };
            inserted.push(tableData[conflictIdx]);
            continue;
          }
        }
        tableData.push(record);
        inserted.push(record);
      }
      return {
        data: qb.isSingle ? inserted[0] : (Array.isArray(qb.body) ? inserted : inserted[0]),
        error: null,
        status: 201,
      };
    }

    if (qb.method === "PATCH") {
      const updated = [];
      const nowStr = new Date().toISOString();
      for (let i = 0; i < tableData.length; i++) {
        if (matchesFilter(tableData[i])) {
          tableData[i] = { ...tableData[i], ...qb.body, updated_at: nowStr };
          updated.push({ ...tableData[i] });
        }
      }
      return {
        data: qb.isSingle ? updated[0] || null : (qb.isMaybeSingle ? updated[0] || null : updated),
        error: null,
        status: 200,
      };
    }

    if (qb.method === "DELETE") {
      const deleted = [];
      this.tables[qb.table] = tableData.filter((row) => {
        if (matchesFilter(row)) {
          deleted.push(row);
          return false;
        }
        return true;
      });
      return { data: deleted, error: null, status: 200 };
    }

    return { data: null, error: new Error(`Unsupported method ${qb.method}`) };
  }
}

let activeMockStore = null;

export function getMockStore() {
  if (!activeMockStore) {
    activeMockStore = new MockSupabaseStore();
  }
  return activeMockStore;
}

export function resetMockStore() {
  activeMockStore = new MockSupabaseStore();
  return activeMockStore;
}

export class SupabaseClient {
  constructor(url, serviceRoleKey, options = {}) {
    this.url = (url || "").replace(/\/$/, "");
    this.serviceRoleKey = serviceRoleKey || "";
    this.mockStore = options.mockStore || (options.useMock ? getMockStore() : null);
  }

  from(table) {
    return new PostgrestQueryBuilder(this, table);
  }

  async rpc(fnName, params = {}) {
    if (this.mockStore) {
      return { data: { success: true }, error: null };
    }
    const endpoint = `${this.url}/rest/v1/rpc/${fnName}`;
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: {
          "apikey": this.serviceRoleKey,
          "Authorization": `Bearer ${this.serviceRoleKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(params),
      });
      const data = await res.json();
      return { data, error: res.ok ? null : data };
    } catch (err) {
      return { data: null, error: err };
    }
  }
}

/**
 * Factory to get SupabaseClient from environment.
 * If SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY is absent or in test mode, safely falls back to MockSupabaseStore.
 */
export function getSupabaseClient(env = {}) {
  const url = env.SUPABASE_URL;
  const key = env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_KEY;

  if (env.__MOCK_SUPABASE__ || env.MOCK_SUPABASE === "true" || !url || !key) {
    return new SupabaseClient(url, key, { mockStore: env.__MOCK_STORE__ || getMockStore() });
  }

  return new SupabaseClient(url, key);
}
