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

## Validation Results

### 8 Assets × 2 Perioden = 16 Tests

| Asset | 2024 | 2025Q1 | Notes |
|-------|------|--------|-------|
| BTC | ✅ | ✅ | Stabil |
| ETH | ❌ | ✅ | 2024 schwer, 2025 besser |
| SOL | ✅ | ❌ | Hohe Vol, ADX filtert zu aggressiv |
| DOGE | ✅ | ❌ | Meme-Regime-Shift |
| AVAX | ❌ | ✅ | Stark mit Filter |
| LINK | ✅ | ❌ | Regime-abhängig |
| XRP | ✅ | ✅ | Stabil |
| ADA | ❌ | ❌ | Unprofitabel |

**Pass Rate: 8/16 (50%)**

### Filter-Vergleich

| Filter | Pass | Return | DD | CL |
|--------|------|--------|----|----|
| Unfiltered | 12% | +53.4% | 22.7% | 9.9 |
| **ADX+EMA** | **50%** | **+35.9%** | **14.1%** | **6.5** |
| ATR Expansion | 44% | +26.4% | 10.4% | — |
| ATR Tight | 50% | +21.1% | 10.7% | — |

ATR wurde getestet und abgelehnt — ADX+EMA bleibt Gold Standard.

## Gate Thresholds v0.3 (UNCHANGED)

| Gate | Threshold |
|------|-----------|
| Min Return | 1% |
| Profit Factor | ≥ 1.05 |
| Max Drawdown | ≤ 20% |
| Max Consecutive Losses | ≤ 8 |
| Min Sharpe | ≥ 0.1 |
| Min Trades | 20 |

## Platform

| | |
|---|---|
| Exchange | Hyperliquid Perps DEX |
| Fees | 0.01% Maker + 1bp Slippage |
| Startkapital | 100€ |
| Leverage | 1x (V1 konservativ) |