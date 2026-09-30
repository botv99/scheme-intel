# Scheme-Intel Forward Performance & Validation Report

**Generated At:** 2026-09-30T12:51:11.359461+00:00 UTC
**Data Period:** 2026-09-24 → 2026-10-01
**Data Sufficiency Status:** `INSUFFICIENT_SAMPLE` — *Insufficient sample (4 completed trades; minimum 30 required for statistical validity)*
**Strategy Validation Status:** `INSUFFICIENT DATA`

---

## 1. Setup Lifecycle Sample
- **Total Setups Recorded:** 28
- **Qualified Setups:** 6
- **Waiting Setups:** 13
- **Rejected Setups (Hard Risk Veto / No Trade):** 9
- **Triggered Entries:** 7
- **Untriggered Setups:** 21 *(never counted as losses)*
- **Currently Active (Open) Trades:** 3
- **Completed Trades:** 4
- **Expired Positions:** 4

---

## 2. Outcome Statistics
- **Completed Triggered Trades:** 4
- **Target 1 Hits (Wins):** 0
- **Stop Loss Hits (Losses):** 0
- **Expired at Max Age:** 4
- **Win Rate:** 0.0% *(wins / completed trades)*
- **Loss Rate:** 0.0%
- **Expiry Rate:** 100.0%

---

## 3. Return & P&L Metrics
- **Average Realized P&L:** +0.00%
- **Median Realized P&L:** +0.00%
- **Cumulative Realized P&L:** +0.00%
- **Average Winning Trade:** N/A
- **Average Losing Trade:** N/A
- **Largest Winner:** +0.00%
- **Largest Loser:** +0.00%
- **Profit Factor:** 0.0 *(gross profits / gross losses)*
- **Expectancy:** N/A per triggered trade
- **Standard Deviation of Returns:** 0.00%

---

## 4. MFE & MAE Excursions
- **Average MFE (Max Favorable Excursion):** +0.71%
- **Median MFE:** +0.52%
- **Maximum MFE Observed:** +1.33%
- **Average MAE (Max Adverse Excursion):** -2.34%
- **Median MAE:** -1.30%
- **Maximum Adverse Excursion (Worst Dip):** -4.88%

### Excursion Distributions
| MFE Bucket | Trades | MAE Bucket | Trades |
| :--- | :--- | :--- | :--- |
| <0% | 0 | 0 to -1% | 3 |
| 0–2% | 7 | -1 to -3% | 1 |
| 2–5% | 0 | -3 to -5% | 3 |
| 5–10% | 0 | <-5% | 0 |
| >10% | 0 |  |  |

---

## 5. Holding Period Analytics
- **Overall Holding Period:** Avg 5 days | Median 5.0 days (Min 5.0 days - Max 5.0 days)
- **Winning Trades:** Avg N/A
- **Losing Trades:** Avg N/A
- **Expired Trades:** Avg 5 days

---

## 6. Breakdown by Archetype
| Archetype | Setups | Trig | Comp | Win Rate | Avg P&L | Expectancy | PF | Avg MFE | Avg MAE | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 3 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| Breakout Anticipation | 6 | 6 | 4 | 0.0% | +0.00% | +0.00% | N/A | +0.8% | -2.5% | `INSUFFICIENT_SAMPLE` |
| Unspecified | 19 | 1 | 0 | N/A | N/A | N/A | N/A | +0.1% | -1.3% | `INSUFFICIENT_SAMPLE` |

---

## 7. Breakdown by Stock Symbol
| Symbol | Setups | Trig | Comp | Win Rate | Avg P&L | Expectancy | Avg MFE | Avg MAE | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| GAIL.NS | 4 | 1 | 0 | N/A | N/A | N/A | +0.1% | -1.3% | `INSUFFICIENT_SAMPLE` |
| IOC.NS | 4 | 3 | 2 | 0.0% | +0.00% | +0.00% | +1.1% | -0.3% | `INSUFFICIENT_SAMPLE` |
| KIRLPNU.NS | 4 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| ORGANICREC.BO | 4 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| PRAJIND.NS | 4 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| TRUALT.NS | 4 | 3 | 2 | 0.0% | +0.00% | +0.00% | +0.5% | -4.8% | `INSUFFICIENT_SAMPLE` |
| WABAG.NS | 4 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |

---

## 8. Breakdown by AI Provider
*(Observational measurement only. Does not imply causation.)*
| Provider | Setups | Trig | Comp | Win Rate | Avg P&L | Expectancy | Avg MFE | Avg MAE | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Deterministic Fallback | 19 | 1 | 0 | N/A | N/A | N/A | +0.1% | -1.3% | `INSUFFICIENT_SAMPLE` |
| Mock | 9 | 6 | 4 | 0.0% | +0.00% | +0.00% | +0.8% | -2.5% | `INSUFFICIENT_SAMPLE` |

---

## 9. Score-Band Analysis
| Candidate Score Band | Setups | Triggered | Completed | Win Rate | Avg P&L | Expectancy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 0–20 | 0 | 0 | 0 | N/A | N/A | N/A |
| 21–40 | 0 | 0 | 0 | N/A | N/A | N/A |
| 41–60 | 0 | 0 | 0 | N/A | N/A | N/A |
| 61–80 | 6 | 3 | 2 | 0.0% | +0.00% | +0.00% |
| 81–100 | 3 | 3 | 2 | 0.0% | +0.00% | +0.00% |

---

## 10. Walk-Forward & Out-of-Sample Validation
### Rolling Forward Windows
| Window Name | Trades | Start Date | End Date | Win Rate | Avg P&L | Expectancy | PF | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Rolling 20 Trades | 4 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| Rolling 50 Trades | 4 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| Rolling 100 Trades | 4 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |

### Out-of-Sample Partition Comparison
- **Chronological Split Date:** 2026-09-29
- **Historical (In-Sample):** 2 trades | Win Rate: N/A% | Avg P&L: N/A% | Exp: N/A%
- **Forward (Out-of-Sample):** 2 trades | Win Rate: N/A% | Avg P&L: N/A% | Exp: N/A% (`INSUFFICIENT_SAMPLE`)

---

## 11. Baseline Benchmark Comparison (NIFTY 50)
- **Status:** `ACTIVE`
- **Trades Evaluated:** 4 / 4
- **Average Strategy Return:** +0.00%
- **Average Benchmark Return (Nifty 50):** +0.00%
- **Average Excess Return (Alpha):** +0.00%
- **Median Excess Return:** +0.00%
- **Cumulative Excess Return:** +0.00%

### Trade-by-Trade Benchmark Comparison
| Setup ID | Symbol | Entry Date | Exit Date | Strategy P&L | Nifty Return | Excess Return |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| SETUP-IOC_NS-20260928 | IOC.NS | 2026-09-28 | 2026-09-30 | +0.00% | +0.00% | +0.00% |
| SETUP-TRUALT_NS-20260928 | TRUALT.NS | 2026-09-28 | 2026-09-30 | +0.00% | +0.00% | +0.00% |
| SETUP-IOC_NS-20260925 | IOC.NS | 2026-09-25 | 2026-09-28 | +0.00% | +0.00% | +0.00% |
| SETUP-TRUALT_NS-20260925 | TRUALT.NS | 2026-09-25 | 2026-09-28 | +0.00% | +0.00% | +0.00% |

---

## 12. Data Integrity Checks
- **Audit Status:** `WARN`
- **Checks Performed:** 10
- **Issues Detected:** 7

**Integrity Warnings:**
- ⚠️ Setup SETUP-TRUALT_NS-20260930: entry_date (2026-09-30) is earlier than setup_date (2026-10-01)
- ⚠️ Setup SETUP-IOC_NS-20260930: entry_date (2026-09-30) is earlier than setup_date (2026-10-01)
- ⚠️ Setup SETUP-TRUALT_NS-20260928: entry_date (2026-09-28) is earlier than setup_date (2026-09-29)
- ⚠️ Setup SETUP-IOC_NS-20260928: entry_date (2026-09-28) is earlier than setup_date (2026-09-29)
- ⚠️ Setup SETUP-TRUALT_NS-20260925: entry_date (2026-09-25) is earlier than setup_date (2026-09-28)
- ⚠️ Setup SETUP-IOC_NS-20260925: entry_date (2026-09-25) is earlier than setup_date (2026-09-28)
- ⚠️ Setup SETUP-GAIL_NS-20260925: entry_date (2026-09-25) is earlier than setup_date (2026-09-28)