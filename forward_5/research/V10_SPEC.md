# V10 Strategy Specification — Funding-First

**Status:** PHASE 1 VALIDATED — Phase 1d next  
**Date:** 2026-04-30  
**Author:** Pecz + Dave  
**Principle:** "Truth from data, tests, and gates" — every step has a kill criterion.

---

## 1. Core Hypotheses

**H1 (Long):** Extreme negative Funding Rate (Shorts overcrowded) predicts price increases on volatile alts (DOGE/ADA/AVAX) within 24-48h.

**H2 (Short):** Extreme positive Funding Rate (Longs overcrowded) predicts price decreases on major assets (BTC/ETH/SOL) within 24h.

**H-null:** Funding Rate has no predictive power (correlation < 0.05 with forward returns).

### 1-Year Walk-Forward Evidence (Binance 8h, May 2025 - Apr 2026)

**H1 VALIDATED (conditional):**
| Asset | Long P10 24h (net) | Regime |
|-------|-------------------|--------|
| AVAX | +0.75% | Bull only |
| ADA | +0.75% | Bull only |
| DOGE | +0.63% | Bull only |
| BTC | +0.15% | Marginal |
| ETH | -0.47% | Fail |
| SOL | -1.55% | Fail |

**H2 VALIDATED (strong):**
| Asset | Short P90 24h (net) | Regime |
|-------|---------------------|--------|
| SOL | +1.99% | Bear-biased |
| ETH | +0.78% | Bear-biased |
| BTC | +0.65% | Bear-biased |
| DOGE | -0.46% | Fail |
| ADA | -1.24% | Fail |

**Key insight:** Long works on alts, Short works on majors. Asset-selection is part of the signal.

### Regime Dependency (CRITICAL)

| Quarter | Market | Long P10 | Short P90 |
|---------|--------|----------|-----------|
| Q2 2025 | Bull | +1.47% | No data |
| Q3 2025 | Sideways | +0.06% | +0.85% |
| Q4 2025 | **Bear** | **-0.98%** | **+0.57%** |
| Q1 2026 | Recovery | +0.66% | +0.35% |

**Kill criterion check:** Edge NOT only in one regime → PASS ✅ (but direction depends on regime)

---

## 2. Costs (NOW deducted from backtest)

| Cost | Amount | Notes |
|------|--------|-------|
| Hyperliquid Maker Fee | 0.02% per trade | 0.04% round-trip |
| Hyperliquid Taker Fee | 0.05% per trade | 0.10% round-trip (worst case) |
| Slippage | 0.03% per trade | 0.06% round-trip |
| Funding Payment | -0.001% to -0.03% avg | NEGATIVE = Longs receive from Shorts! |

**Net finding:** Funding payments are negligible or slightly favorable for our direction. The real cost driver is SL rate.

### Stop Loss Analysis

| Asset (Long) | SL Rate (3%) | Problem |
|-------------|-------------|---------|
| BTC | 6.8% | OK |
| ETH | 31.3% | High |
| SOL | 46.6% | **Catastrophic** |
| AVAX | 37.1% | High |
| DOGE | 41.1% | High |
| ADA | 32.9% | High |

**V2 Design already addressed this:** Regime-based SL — 1.5% in Weak, 2.5% in Strong. But 3% may still be too tight for volatile alts. **Phase 1d must test wider SLs (4%, 5%).**

---

## 3. V2 Design Alignment

The 1-year data validates core V2 Design decisions AND reveals gaps:

### ✅ V2 Design Validated
| V2 Principle | Data Evidence |
|-------------|---------------|
| Sentiment = Funding Rate | Edge confirmed on both directions |
| Regime-based Exit | Q4 2025: Long fails, Short works → regime decides direction |
| Sniper at Regime > 70 | Strong regime = Long on alts with conviction |
| No Indicator Salad | Funding alone > Funding + standard indicators |
| Kill-Switch at extreme Funding | P90 Short = strongest edge |

### ⚠️ V2 Design Gaps (revealed by data)
| Gap | What data shows | V2 Update needed |
|-----|-----------------|-----------------|
| **Short as Stufe 2** | Short P90 = strongest edge (5.19% annualized) | **Promote to Stufe 1** |
| **SL fixed at 3%** | SL rate 30-47% on alts | **Regime-based SL: 3% Weak, 5% Strong** |
| **All 6 assets equal** | Long works on alts, Short on majors | **Asset-specific direction** |
| **Funding only Kill-Switch** | Funding IS the entry signal, not just filter | **Funding = primary signal, regime = direction filter** |

---

## 4. Risk Constraints (updated)

| Constraint | Value | Reason |
|-----------|-------|--------|
| Max correlated positions | 2 | V2 Principle 12 |
| SL | 3% Weak regime, 5% Strong regime | V2 regime-based exit (updated from fixed 3%) |
| Max portfolio DD | 8% per hour (Global Equity Stop) | V2 Principle 10 |
| Max position size | 16.67€ (equal weight) | V1 standard |
| Direction selection | Long on alts when funding low, Short on majors when funding high | Asset-specific from data |
| Min trades per WF window | 2 | WF-Gate V8.1 |

---

## 5. Data Source Consistency

| Source | Resolution | History | Status |
|--------|-----------|---------|--------|
| Binance Funding | 8h | 1 year | ✅ Loaded, 6570 records |
| Binance Prices | 8h | 1 year | ✅ Loaded |
| Hyperliquid Funding | 1h | ~90 days | ✅ Loaded, live collector running |
| HL Prices | 1h | ~60 days | ✅ Loaded |

**Cross-validation needed:** Edge must exist on BOTH Binance 8h AND Hyperliquid 1h data. If edge only on one → investigate.

---

## 6. V10 Plan (with Kill Criteria) — Updated

### Phase 1: Validate the Edge ✅ PARTIALLY DONE

| Step | What | Status | Kill Criterion | Result |
|------|------|--------|----------------|--------|
| 1a | Load Binance Funding 8h (1 year) | ✅ Done | No API access | 6570 records, 6 assets |
| 1b | Standalone test on 1 year (10 WF windows) | ✅ Done | Edge < 0.05% | PASS: +0.35% avg edge |
| 1c | Slippage + Fees + Funding payment | ✅ Done | Net < 0.3% annualized | PASS: 5.19% annualized |
| 1d | Regime analysis (bull/bear split) | ✅ Done | Edge only in one regime | PASS: works in both, direction differs |
| 1e | **SL optimization + Regime filter** | 🔲 NEXT | No improvement → use fixed SL | — |
| 1f | **Cross-validate on HL 1h data** | 🔲 Pending | Edge disappears on HL → investigate | — |
| 1g | **Funding + Regime combination test** | 🔲 Pending | No improvement → Funding alone | — |

### Phase 2: Foundry V10 (2 days engineering, 7-14 days running)

| Step | What | Duration | Kill Criterion |
|------|------|----------|----------------|
| 2a | Add `funding_rate`, `oi_change` to DSL Translator | 2h | — |
| 2b | WF-Gate: join Funding data with candles | 2h | — |
| 2c | New Foundry prompts for Funding-based arms | 2h | — |
| 2d | Arms: FUNDING-LONG (alts), FUNDING-SHORT (majors), FUNDING+REGIME | 2h | — |
| 2e | Foundry V10 runs (daily cron) | 7-14 days | 0 WF-passed after 5 runs → **Stop** |

### Phase 3: Paper Engine (2 days)

| Step | What | Duration | Kill Criterion |
|------|------|----------|----------------|
| 3a | Integrate Funding data feed into Paper Engine | 4h | — |
| 3b | Best V10 strategy into Paper Engine | 4h | — |
| 3c | Live validation 14 days | 14 days | DD > 25% or edge disappears → **Stop** |

---

## 7. Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| OOS return per trade | > 0.10% net (after fees+SL) | Walk-Forward |
| Win rate | > 52% | Walk-Forward |
| Avg trades per window | ≥ 2 | Walk-Forward |
| WF robustness | ≥ 40 | Walk-Forward |
| Direction accuracy | Long on alts, Short on majors | Per-asset analysis |
| Live edge vs backtest | > 50% of backtest edge | Paper Trading |
| Max DD in paper | < 25% | Paper Trading |

---

## 8. What We're NOT Doing

- NOT adding 5 more indicators (Principle 5)
- NOT building a new engine (Paper Engine works)
- NOT trusting 60 days of data (validated on 1 year ✅)
- NOT treating all assets equal (data shows alts ≠ majors)
- NOT using fixed 3% SL (regime-based per V2 Design)
- NOT skipping kill criteria (Principle 7)

---

## 9. Decision Log

| Date | Decision | Reason |
|------|----------|--------|
| 2026-04-30 | V10 = Foundry with Funding data | Foundry is our motor (Dave) |
| 2026-04-30 | RSI/BB/EMA NOT as confirmation | 0 Alpha proven |
| 2026-04-30 | Regime/Vol as RISK filter | Regime decides direction, not entry |
| 2026-04-30 | Binance 8h for backtest, HL 1h for live | Cross-validation needed |
| 2026-04-30 | Funding payment modeled as cost | Negligible or favorable |
| 2026-04-30 | **Short promoted to Stufe 1** | Short P90 = strongest edge (5.19% annualized) |
| 2026-04-30 | **Asset-specific direction** | Long on alts (AVAX/DOGE/ADA), Short on majors (BTC/ETH/SOL) |
| 2026-04-30 | **SL regime-based: 3% Weak, 5% Strong** | 30-47% SL rate too high on alts with fixed 3% |
| 2026-04-30 | **48h hold may be better** | Long P10 48h net +0.28% vs 24h +0.04% |