# Scheme Intel — Source Feeds & Reliability Hierarchy

## 5-Tier Source Reliability Hierarchy

```text
Tier 1: Government / Regulator / Exchange (Weight: 1.15)
  ├── Press Information Bureau (PIB)
  ├── GOBARdhan Unified Registration Portal
  ├── Ministry of New and Renewable Energy (MNRE)
  ├── Ministry of Jal Shakti (DDWS)
  ├── Central Public Procurement Portal (CPPP)
  ├── National Stock Exchange of India (NSE)
  └── Bombay Stock Exchange (BSE)

Tier 2: Company Official Disclosure / Investor Relations (Weight: 1.10)
  ├── Corporate Regulatory Announcements (Listing Regulation 30)
  ├── Investor Presentations & Annual Reports
  ├── Earnings Releases & Press Disclosures
  └── Investor Conference Call Transcripts

Tier 3: Established Financial Publications (Weight: 1.00)
  ├── The Economic Times (Energy, Policy)
  ├── LiveMint (Industry & Markets)
  ├── Business Standard (Commodities & Economy)
  ├── Financial Express (Infrastructure)
  └── Reuters India / Bloomberg

Tier 4: Analyst & Research Sources (Weight: 0.90)
  ├── Scripbox Broker Research Feeds
  ├── ICICI Direct / HDFC Securities Reports
  └── Sectoral Consensus Ratings

Tier 5: Social Media / Unverified Portals (Weight: 0.70)
  └── Community forums, general blogs, and unverified news.
```

---

## Source Resilience & Error Handling

- **Datacenter IP Filtering**: Indian exchanges (NSE/BSE) often enforce Cloudflare/Akamai bot detection on datacenter IP blocks. Ingestion paths treat exchange JSON endpoints as best-effort, falling back to public CSV archives (e.g. `archives.nseindia.com/content/equities/bulk.csv`).
- **Retries & Backoff**: Feed access utilizes exponential backoff retries with session connection caching.
- **Circuit Breaker & Fallback Snapshot**: If live feeds fail or time out, `data/ingested.json` acts as an offline snapshot.
- **Stale Protection**: Any news items older than 72 hours are flagged as stale, reducing their confidence multiplier.
