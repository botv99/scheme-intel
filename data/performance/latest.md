# Scheme-Intel Forward Performance & Validation Report

**Generated At:** 2026-10-02T11:54:49.151751+00:00 UTC
**Data Period:** 2026-09-24 → 2026-10-05
**Data Sufficiency Status:** `INSUFFICIENT_SAMPLE` — *Insufficient sample (5 completed trades; minimum 30 required for statistical validity)*
**Strategy Validation Status:** `INSUFFICIENT DATA`

---

## 1. Setup Lifecycle Sample
- **Total Setups Recorded:** 35
- **Qualified Setups:** 6
- **Waiting Setups:** 16
- **Rejected Setups (Hard Risk Veto / No Trade):** 13
- **Triggered Entries:** 9
- **Untriggered Setups:** 26 *(never counted as losses)*
- **Currently Active (Open) Trades:** 4
- **Completed Trades:** 5
- **Expired Positions:** 4

---

## 2. Outcome Statistics
- **Completed Triggered Trades:** 5
- **Target 1 Hits (Wins):** 0
- **Stop Loss Hits (Losses):** 1
- **Expired at Max Age:** 4
- **Win Rate:** 0.0% *(wins / completed trades)*
- **Loss Rate:** 20.0%
- **Expiry Rate:** 80.0%

---

## 3. Return & P&L Metrics
- **Average Realized P&L:** -0.32%
- **Median Realized P&L:** +0.00%
- **Cumulative Realized P&L:** -1.61%
- **Average Winning Trade:** N/A
- **Average Losing Trade:** -1.61%
- **Largest Winner:** +0.00%
- **Largest Loser:** -1.61%
- **Profit Factor:** 0.0 *(gross profits / gross losses)*
- **Expectancy:** N/A per triggered trade
- **Standard Deviation of Returns:** 0.72%

---

## 4. MFE & MAE Excursions
- **Average MFE (Max Favorable Excursion):** +1.21%
- **Median MFE:** +0.85%
- **Maximum MFE Observed:** +5.23%
- **Average MAE (Max Adverse Excursion):** -3.01%
- **Median MAE:** -3.45%
- **Maximum Adverse Excursion (Worst Dip):** -6.02%

### Excursion Distributions
| MFE Bucket | Trades | MAE Bucket | Trades |
| :--- | :--- | :--- | :--- |
| <0% | 0 | 0 to -1% | 2 |
| 0–2% | 8 | -1 to -3% | 2 |
| 2–5% | 0 | -3 to -5% | 4 |
| 5–10% | 1 | <-5% | 1 |
| >10% | 0 |  |  |

---

## 5. Holding Period Analytics
- **Overall Holding Period:** Avg 4.2 days | Median 5 days (Min 1.0 days - Max 5.0 days)
- **Winning Trades:** Avg N/A
- **Losing Trades:** Avg 1 days
- **Expired Trades:** Avg 5 days

---

## 6. Breakdown by Archetype
| Archetype | Setups | Trig | Comp | Win Rate | Avg P&L | Expectancy | PF | Avg MFE | Avg MAE | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 3 | 1 | 0 | N/A | N/A | N/A | N/A | +5.2% | -4.7% | `INSUFFICIENT_SAMPLE` |
| Breakout Anticipation | 5 | 5 | 4 | 0.0% | +0.00% | +0.00% | N/A | +0.8% | -2.3% | `INSUFFICIENT_SAMPLE` |
| Momentum Continuation | 2 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| Pullback | 1 | 1 | 1 | 0.0% | -1.61% | -1.61% | 0.00 | +0.8% | -6.0% | `INSUFFICIENT_SAMPLE` |
| Unspecified | 24 | 2 | 0 | N/A | N/A | N/A | N/A | +0.5% | -2.4% | `INSUFFICIENT_SAMPLE` |

---

## 7. Breakdown by Stock Symbol
| Symbol | Setups | Trig | Comp | Win Rate | Avg P&L | Expectancy | Avg MFE | Avg MAE | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| GAIL.NS | 5 | 2 | 0 | N/A | N/A | N/A | +0.2% | -1.4% | `INSUFFICIENT_SAMPLE` |
| IOC.NS | 5 | 3 | 2 | 0.0% | +0.00% | +0.00% | +1.1% | -1.3% | `INSUFFICIENT_SAMPLE` |
| KIRLPNU.NS | 5 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| ORGANICREC.BO | 5 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| PRAJIND.NS | 5 | 0 | 0 | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| TRUALT.NS | 5 | 3 | 2 | 0.0% | +0.00% | +0.00% | +2.1% | -4.8% | `INSUFFICIENT_SAMPLE` |
| WABAG.NS | 5 | 1 | 1 | 0.0% | -1.61% | -1.61% | +0.8% | -6.0% | `INSUFFICIENT_SAMPLE` |

---

## 8. Breakdown by AI Provider
*(Observational measurement only. Does not imply causation.)*
| Provider | Setups | Trig | Comp | Win Rate | Avg P&L | Expectancy | Avg MFE | Avg MAE | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Deterministic Fallback | 24 | 2 | 0 | N/A | N/A | N/A | +0.5% | -2.4% | `INSUFFICIENT_SAMPLE` |
| Mock | 11 | 7 | 5 | 0.0% | -0.32% | -0.32% | +1.4% | -3.2% | `INSUFFICIENT_SAMPLE` |

---

## 9. Score-Band Analysis
| Candidate Score Band | Setups | Triggered | Completed | Win Rate | Avg P&L | Expectancy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 0–20 | 0 | 0 | 0 | N/A | N/A | N/A |
| 21–40 | 0 | 0 | 0 | N/A | N/A | N/A |
| 41–60 | 0 | 0 | 0 | N/A | N/A | N/A |
| 61–80 | 7 | 3 | 2 | 0.0% | +0.00% | +0.00% |
| 81–100 | 4 | 4 | 3 | 0.0% | -0.54% | -0.54% |

---

## 10. Walk-Forward & Out-of-Sample Validation
### Rolling Forward Windows
| Window Name | Trades | Start Date | End Date | Win Rate | Avg P&L | Expectancy | PF | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Rolling 20 Trades | 5 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| Rolling 50 Trades | 5 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |
| Rolling 100 Trades | 5 | N/A | N/A | N/A | N/A | N/A | N/A | `INSUFFICIENT_SAMPLE` |

### Out-of-Sample Partition Comparison
- **Chronological Split Date:** 2026-09-29
- **Historical (In-Sample):** 2 trades | Win Rate: N/A% | Avg P&L: N/A% | Exp: N/A%
- **Forward (Out-of-Sample):** 3 trades | Win Rate: N/A% | Avg P&L: -0.54% | Exp: -0.54% (`INSUFFICIENT_SAMPLE`)

---

## 11. Baseline Benchmark Comparison (NIFTY 50)
- **Status:** `ACTIVE`
- **Trades Evaluated:** 5 / 5
- **Average Strategy Return:** -0.32%
- **Average Benchmark Return (Nifty 50):** +0.00%
- **Average Excess Return (Alpha):** -0.32%
- **Median Excess Return:** +0.00%
- **Cumulative Excess Return:** -1.61%

### Trade-by-Trade Benchmark Comparison
| Setup ID | Symbol | Entry Date | Exit Date | Strategy P&L | Nifty Return | Excess Return |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| SETUP-WABAG_NS-20260930 | WABAG.NS | 2026-09-30 | 2026-09-30 | -1.61% | +0.00% | -1.61% |
| SETUP-IOC_NS-20260928 | IOC.NS | 2026-09-28 | 2026-09-30 | +0.00% | +0.00% | +0.00% |
| SETUP-TRUALT_NS-20260928 | TRUALT.NS | 2026-09-28 | 2026-09-30 | +0.00% | +0.00% | +0.00% |
| SETUP-IOC_NS-20260925 | IOC.NS | 2026-09-25 | 2026-09-28 | +0.00% | +0.00% | +0.00% |
| SETUP-TRUALT_NS-20260925 | TRUALT.NS | 2026-09-25 | 2026-09-28 | +0.00% | +0.00% | +0.00% |

---

## 12. Data Integrity Checks
- **Audit Status:** `WARN`
- **Checks Performed:** 10
- **Issues Detected:** 9

**Integrity Warnings:**
- ⚠️ Setup SETUP-GAIL_NS-20261001: entry_date (2026-10-01) is earlier than setup_date (2026-10-05)
- ⚠️ Setup SETUP-WABAG_NS-20260930: entry_date (2026-09-30) is earlier than setup_date (2026-10-01)
- ⚠️ Setup SETUP-TRUALT_NS-20260930: entry_date (2026-09-30) is earlier than setup_date (2026-10-01)
- ⚠️ Setup SETUP-IOC_NS-20260930: entry_date (2026-09-30) is earlier than setup_date (2026-10-01)
- ⚠️ Setup SETUP-TRUALT_NS-20260928: entry_date (2026-09-28) is earlier than setup_date (2026-09-29)
- ⚠️ Setup SETUP-IOC_NS-20260928: entry_date (2026-09-28) is earlier than setup_date (2026-09-29)
- ⚠️ Setup SETUP-TRUALT_NS-20260925: entry_date (2026-09-25) is earlier than setup_date (2026-09-28)
- ⚠️ Setup SETUP-IOC_NS-20260925: entry_date (2026-09-25) is earlier than setup_date (2026-09-28)
- ⚠️ Setup SETUP-GAIL_NS-20260925: entry_date (2026-09-25) is earlier than setup_date (2026-09-28)