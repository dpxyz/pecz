# V10 Strategy Specification — Funding-First

**Status:** DRAFT  
**Date:** 2026-04-30  
**Author:** Pecz + Dave  
**Principle:** "Truth from data, tests, and gates" — every step has a kill criterion.

---

## 1. Core Hypothesis

**H1:** Extreme negative Funding Rate (Shorts overcrowded) predicts price increases within 4-24h with measurable edge over random entry.

**H1-null:** Funding Rate has no predictive power (correlation < 0.05 with forward returns).

**Current evidence:** Walk-Forward on 60 days shows +0.43% per trade vs random (6/6 assets profitable). **But: 60 days is thin, costs not deducted, regime not tested.**

---

## 2. Known Costs (NOT yet deducted from backtest)

| Cost | Amount | Impact |
|------|--------|--------|
| Hyperliquid Maker Fee | 0.02% per trade | 0.04% round-trip |
| Hyperliquid Taker Fee | 0.05% per trade | 0.10% round-trip (worst case) |
| Slippage (estimated) | 0.02-0.05% per trade | Market orders on liquid pairs |
| **Funding Payment** | **0.01-0.05% per 8h** | **This is the hidden cost!** |

### The Funding Payment Problem

When we go Long while Funding Rate is negative (Shorts pay Longs), we **receive** funding. That's a bonus.
When we go Long while Funding Rate is low but still positive, we **pay** funding. That's a cost.

**Net effect:** If average Funding during hold is -0.03% per 8h and we hold 24h → we **receive** ~0.09%.  
If average Funding is +0.01% per 8h → we **pay** ~0.03%.

This must be modeled in the backtest. **The signal IS the cost basis.**

---

## 3. Risk Constraints

| Constraint | Value | Reason |
|-----------|-------|--------|
| Max correlated positions | 2 | V2 Design Principle 12 |
| Max DD per trade | 3% SL | Same as V1 |
| Max portfolio DD | 8% per hour (Global Equity Stop) | V2 Design Principle 10 |
| Min trades per WF window | 2 | WF-Gate V8.1 standard |
| WF windows | 10 | V9 standard |
| Data history minimum | 6 months | Statistical significance |

---

## 4. Regime Dependency

**Open question:** Does the Funding edge work equally in bull and bear markets?

Our 60-day test period (Mar-Apr 2026) is likely one regime. We need:
- 1+ year of data to cover multiple regimes
- Per-regime analysis: does edge survive bear markets?
- Kill criterion: edge only in one regime = overfitted → Stop

---

## 5. Data Source Consistency

| Source | Resolution | History | Use |
|--------|-----------|---------|-----|
| Hyperliquid Funding | 1h | ~90 days | Live trading signal |
| Binance Funding | 8h | 1+ year | Long-term backtest |
| Binance OI | 1h | 30 days | Correlation check only |
| Binance Taker | 1h | 30 days | Correlation check only |

**Problem:** HL 1h ≠ Binance 8h. Different exchanges, different frequencies, different participant bases.

**Solution:** 
- Backtest on **Binance 8h** data (1+ year) for robustness
- Validate on **Hyperliquid 1h** data (90 days) for live consistency
- If edge exists on both → stronger signal
- If edge only on one → investigate before trusting

---

## 6. V10 Plan (with Kill Criteria)

### Phase 1: Validate the Edge (2 days)

| Step | What | Duration | Kill Criterion |
|------|------|----------|----------------|
| 1a | Load Binance Funding 8h history (1+ year) | 4h | No API access → use alternative |
| 1b | Standalone Funding test on 1 year data (10 WF windows, 6-week each) | 4h | Edge < 0.05% per trade vs random → **Stop** |
| 1c | Slippage + Fees + Funding-payment simulation | 2h | Net edge < 0.3% annualized → **Stop** |
| 1d | Regime analysis (bull/bear/sideways split) | 2h | Edge only in one regime → **investigate** |
| 1e | Funding + Regime/Vol filter combination test | 4h | No improvement over Funding alone → **use Funding alone** |

### Phase 2: Foundry V10 (2 days engineering, 7-14 days running)

| Step | What | Duration | Kill Criterion |
|------|------|----------|----------------|
| 2a | Add `funding_rate`, `oi_change`, `taker_ratio` to DSL Translator | 2h | — |
| 2b | WF-Gate: join Funding data with candles | 2h | — |
| 2c | New Foundry prompts for Funding-based arms | 2h | — |
| 2d | New arms: FUNDING, FUNDING+MR, FUNDING+REGIME | 2h | — |
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
| OOS return per trade | > 0.10% net (after fees) | Walk-Forward |
| Win rate | > 52% | Walk-Forward |
| Avg trades per window | ≥ 2 | Walk-Forward |
| WF robustness | ≥ 40 | Walk-Forward |
| 10-window profitable assets | ≥ 3 of 6 | Walk-Forward |
| Live edge vs backtest | > 50% of backtest edge | Paper Trading |
| Max DD in paper | < 25% | Paper Trading |

---

## 8. What We're NOT Doing

- **NOT** adding 5 more indicators "just in case" (Principle 5: no indicator salad)
- **NOT** building a new engine from scratch (Paper Engine works, just needs Funding feed)
- **NOT** testing every combination of every indicator (Foundry does this systematically)
- **NOT** trusting 60 days of data (extending to 1+ year)
- **NOT** skipping kill criteria (Principle 7: honest Go/No-Go)

---

## 9. Decision Log

| Date | Decision | Reason |
|------|----------|--------|
| 2026-04-30 | V10 = Foundry with Funding data, not manual strategy | Foundry is our motor (Dave), new Kraftstoff (Funding) |
| 2026-04-30 | RSI/BB/EMA NOT as confirmation | 0 Alpha proven, would only add noise |
| 2026-04-30 | Regime/Vol as RISK filter, not alpha source | Regime doesn't predict direction, but may prevent DD |
| 2026-04-30 | Binance 8h for long-term, HL 1h for live | Different sources, need both to validate |
| 2026-04-30 | Funding payment must be modeled in backtest | Hidden cost that can erase edge |