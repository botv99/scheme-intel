# Scheme-Intel Forward Performance & Validation Report

**Generated At:** 2026-09-26T15:16:30.613125+00:00 UTC
**Data Period:** 2026-09-28 → 2026-09-28
**Data Sufficiency Status:** `INSUFFICIENT_SAMPLE` — *Insufficient sample (0 completed trades; minimum 30 required for statistical validity)*
**Strategy Validation Status:** `INSUFFICIENT DATA`

---

## 1. Setup Lifecycle Sample
- **Total Setups Recorded:** 7
- **Qualified Setups:** 1
- **Waiting Setups:** 3
- **Rejected Setups (Hard Risk Veto / No Trade):** 3
- **Triggered Entries:** 0
- **Untriggered Setups:** 7 *(never counted as losses)*
- **Currently Active (Open) Trades:** 0
- **Completed Trades:** 0
- **Expired Positions:** 0

---

## 2. Outcome Statistics
- **Completed Triggered Trades:** 0
- **Target 1 Hits (Wins):** 0
- **Stop Loss Hits (Losses):** 0
- **Expired at Max Age:** 0
- **Win Rate:** N/A *(wins / completed trades)*
- **Loss Rate:** N/A
- **Expiry Rate:** N/A

---

## 3. Return & P&L Metrics
- **Average Realized P&L:** N/A
- **Median Realized P&L:** N/A
- **Cumulative Realized P&L:** +0.00%
- **Average Winning Trade:** N/A
- **Average Losing Trade:** N/A
- **Largest Winner:** N/A
- **Largest Loser:** N/A
- **Profit Factor:** N/A *(gross profits / gross losses)*
- **Expectancy:** N/A per triggered trade
- **Standard Deviation of Returns:** N/A

---

## 4. MFE & MAE Excursions
- **Average MFE (Max Favorable Excursion):** N/A
- **Median MFE:** N/A
- **Maximum MFE Observed:** N/A
- **Average MAE (Max Adverse Excursion):** N/A
- **Median MAE:** N/A
- **Maximum Adverse Excursion (Worst Dip):** N/A

### Excursion Distributions
| MFE Bucket | Trades | MAE Bucket | Trades |
| :--- | :--- | :--- | :--- |
| <0% | 0 | 0 to -1% | 0 |
| 0–2% | 0 | -1 to -3% | 0 |
| 2–5% | 0 | -3 to -5% | 0 |
| 5–10% | 0 | <-5% | 0 |
| >10% | 0 |  |  |

---

## 5. Holding Period Analytics
- **Overall Holding Period:** Avg N/A | Median N/A (Min N/A - Max N/A)
- **Winning Trades:** Avg N/A
- **Losing Trades:** Avg N/A
- **Expired Trades:** Avg N/A

---

## 6. Breakdown by Archetype
| Archetype | Setups | Trig | Comp | Win Rate | Avg P&L | Expectancy | PF | Avg MFE | Avg MAE | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 1 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| Breakout Anticipation | 2 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| Unspecified | 4 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |

---

## 7. Breakdown by Stock Symbol
| Symbol | Setups | Trig | Comp | Win Rate | Avg P&L | Expectancy | Avg MFE | Avg MAE | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| GAIL.NS | 1 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| IOC.NS | 1 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| KIRLPNU.NS | 1 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| ORGANICREC.BO | 1 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| PRAJIND.NS | 1 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| TRUALT.NS | 1 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| WABAG.NS | 1 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |

---

## 8. Breakdown by AI Provider
*(Observational measurement only. Does not imply causation.)*
| Provider | Setups | Trig | Comp | Win Rate | Avg P&L | Expectancy | Avg MFE | Avg MAE | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Deterministic Fallback | 4 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| Groq | 2 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| Groq → Openrouter failover | 1 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |

---

## 9. Score-Band Analysis
| Candidate Score Band | Setups | Triggered | Completed | Win Rate | Avg P&L | Expectancy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 0–20 | 0 | 0 | 0 | N/A | N/A | N/A |
| 21–40 | 0 | 0 | 0 | N/A | N/A | N/A |
| 41–60 | 0 | 0 | 0 | N/A | N/A | N/A |
| 61–80 | 2 | 0 | 0 | N/A | N/A | N/A |
| 81–100 | 1 | 0 | 0 | N/A | N/A | N/A |

---

## 10. Walk-Forward & Out-of-Sample Validation
### Rolling Forward Windows
| Window Name | Trades | Start Date | End Date | Win Rate | Avg P&L | Expectancy | PF | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Rolling 20 Trades | 0 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| Rolling 50 Trades | 0 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| Rolling 100 Trades | 0 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |

---

## 11. Baseline Benchmark Comparison
- **Status:** `Benchmark unavailable`
- **Details:** Broader index (Nifty 50 / Equal-Weight Watchlist) historical intraday feed not stored locally in database

---

## 12. Data Integrity Checks
- **Audit Status:** `PASS`
- **Checks Performed:** 10
- **Issues Detected:** 0
- ✅ Zero schema violations, orphan records, or date inversions detected.