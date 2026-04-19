---
title: Economics
---

# 💰 Phase 8.3: Economics

> Berechnet nach Paper Trading. Wenn die Success Criteria erfüllt sind.

---

## Framework

### Cost Structure

| Position | Monthly (€) | Notes |
|----------|-------------|-------|
| VPS Hostinger | ~10 | Current |
| API/Data | 0 | Hyperliquid API free |
| Monitoring | 0 | Self-hosted |
| **Total** | **~10** | |

### Revenue Model

| Parameter | Value | Source |
|-----------|-------|--------|
| Start Capital | 100€ | ADR-006 |
| Expected Monthly Return | TBD | Paper Trading |
| Fee Structure | 0.01% maker + 1bp | Hyperliquid |
| Leverage | 1x (V1) | Conservative |

### Break-Even Analysis

```
Break-even trades/month = Infra Costs / Expected Profit per Trade
```

| Scenario | Trades/Month | Avg Profit/Trade | Monthly PnL | vs. Costs |
|----------|-------------|-------------------|-------------|-----------|
| Pessimistic | 5 | +0.5% | +2.50€ | ❌ -7.50€ |
| Baseline | 10 | +1.0% | +10.00€ | ✅ ±0€ |
| Optimistic | 15 | +1.5% | +22.50€ | ✅ +12.50€ |

### Risk-Adjusted Returns

| Metric | Target | Actual |
|--------|--------|--------|
| Sharpe Ratio | ≥ 0.5 | TBD |
| Sortino Ratio | ≥ 0.8 | TBD |
| Calmar Ratio | ≥ 0.5 | TBD |
| Max Drawdown | ≤ 25% | TBD |

---

## Decision Matrix

| Paper Result | Action |
|-------------|--------|
| Monthly PnL > Infra | → Phase 9 (Final Gate) |
| Monthly PnL ≈ Infra | → Optimize strategy or increase capital |
| Monthly PnL < Infra | → No-Go for live, review strategy |

---

*Wird ausgefüllt sobald Paper Trading abgeschlossen ist (≥30 Tage, ≥30 Trades).*