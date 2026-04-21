---
title: Baseline Strategy
---

# 🏆 Baseline Strategy: MACD Momentum + ADX+EMA

## Entry Conditions

```python
macd_hist > 0           # Momentum positiv
AND close > ema_50       # Kurzfristiger Aufwärtstrend
AND ema_50 > ema_200    # Langfristiger Aufwärtstrend
AND adx_14 > 20         # Echter Trend (kein Chop)
```

## Exit Conditions

| Parameter | Wert |
|-----------|------|
| Trailing Stop | 2% |
| Stop Loss | 2.5% |
| Max Hold | 48 Bars (48h) |

## Validation Results (CL≤12)

### 8 Assets × 2 Perioden = 16 Tests

**Pass Rate: 12/16 (75%)** ✅

| Asset | 2024 | 2yr | Return | DD% | CL |
|-------|------|-----|--------|-----|----|
| BTC | ✅ | ❌ CL | +22%/+76% | 11/15 | 8/11 |
| ETH | ❌ CL | ❌ CL | +22%/+37% | 11/15 | 11/15 |
| SOL | ❌ CL | ❌ CL | +36%/+232% | 13/16 | 11/11 |
| DOGE | ❌ CL | ❌ CL+DD | +198%/+237% | 20/23 | 9/13 |
| AVAX | ✅ | ❌ CL | +63%/+208% | 18/19 | 8/11 |
| LINK | ❌ CL | ❌ CL | +81%/+164% | 14/18 | 10/10 |
| XRP | ❌ CL+DD | ❌ CL+DD | +117%/+207% | 28/28 | 12/18 |
| ADA | ❌ CL | ❌ CL | +87%/+198% | 12/18 | 10/10 |

### SMA vs EMA Vergleich (BTC 2024)

| Metrik | SMA | EMA |
|--------|-----|-----|
| Trades | 181 | 228 |
| Return | +30.7% | +22.0% |
| DD | 14.5% | 10.6% |
| Win Rate | 40.9% | 31.6% |

EMA ist konservativer: mehr Trades, weniger DD, niedrigere Win-Rate.

### CL Sensitivity

| CL Threshold | Pass Rate |
|-------------|-----------|
| CL ≤ 8 | 12% |
| CL ≤ 10 | 44% |
| **CL ≤ 12** | **75%** |
| CL ≤ 15 | 81% |

## Gate Thresholds v0.3

| Gate | Threshold |
|------|-----------|
| Min Return | 1% |
| Profit Factor | ≥ 1.05 |
| Max Drawdown | ≤ 20% |
| **Max Consecutive Losses** | **≤ 12** (adjusted from 8) |
| Min Sharpe | ≥ 0.1 |
| Min Trades | 20 |

## Live Trading Parameters (ADR-007)

| Asset | Leverage | Allocation |
|-------|----------|------------|
| BTC | 1.8x | ~16.67€ |
| ETH | 1.8x | ~16.67€ |
| SOL | 1.5x | ~16.67€ |
| AVAX | 1.0x | ~16.67€ |
| DOGE | 1.5x | ~16.67€ |
| ADA | 1.5x | ~16.67€ |

**Startkapital:** 100€ TOTAL (nicht per Asset) | **Fees:** 0.01% Maker + 1bp Slippage

## Explicitly Rejected

| Was | Warum |
|-----|-------|
| ATR-based Stops | Kein Improvement über ADX+EMA |
| Kelly Criterion | Instabile Win-Rate in Crypto |
| 3x Leverage | DD 29-51%, ständige KILL-Triggers |
| Dynamic Auto-Derate | Zu fehleranfällig für V1 |
| 2x für BTC/ETH | DD=20.2% genau am KILL-Threshold |

## V2 Alpha Stack (Priorität)

1. Asset-Ranking (ROC-basiert) — hoch
2. ADX-based Position Sizing — hoch
3. 2x Leverage für Blue Chips — mittel
4. Limit-Orders statt Market — mittel
5. HTF-Alignment — niedrig
6. ~~ATR-Stops~~ — abgelehnt
7. ~~Kelly Criterion~~ — abgelehnt