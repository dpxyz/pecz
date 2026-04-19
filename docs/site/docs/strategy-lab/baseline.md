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

> **⚠️ Post-Fix (2026-04-19):** Alle EMAs verwenden jetzt `ewm_mean` statt
> `rolling_mean` (SMA). Dies erzeugt schnellere Signale → mehr Trades,
> geringere DD, aber höhere CL-Werte.

## Exit Conditions

| Parameter | Wert |
|-----------|------|
| Trailing Stop | 2% |
| Stop Loss | 2.5% |
| Max Hold | 48 Bars (48h) |

## Validation Results (Post-EMA Fix)

### 8 Assets × 2 Perioden = 16 Tests

| Asset | 2024 | 2yr | Trades | Return | DD% | CL |
|-------|------|-----|--------|--------|-----|----|
| BTC | ✅ | ❌ CL | 228/444 | +22%/+76% | 11/15 | 8/11 |
| ETH | ❌ CL | ❌ CL | 203/402 | +22%/+37% | 11/15 | 11/15 |
| SOL | ❌ CL | ❌ CL | 230/567 | +36%/+232% | 13/16 | 11/11 |
| DOGE | ❌ CL | ❌ CL+DD | 303/547 | +198%/+237% | 20/23 | 9/13 |
| AVAX | ✅ | ❌ CL | 263/539 | +63%/+208% | 18/19 | 8/11 |
| LINK | ❌ CL | ❌ CL | 258/520 | +81%/+164% | 14/18 | 10/10 |
| XRP | ❌ CL+DD | ❌ CL+DD | 272/515 | +117%/+207% | 28/28 | 12/18 |
| ADA | ❌ CL | ❌ CL | 204/447 | +87%/+198% | 12/18 | 10/10 |

**Pass Rate (CL≤8): 2/16 (12%)** | **Pass Rate (CL≤12): 12/16 (75%)**

### SMA vs EMA Vergleich (BTC 2024)

| Metrik | SMA (alt) | EMA (neu) |
|--------|-----------|-----------|
| Trades | 181 | 228 |
| Return | +30.7% | +22.0% |
| DD | 14.5% | 10.6% |
| Win Rate | 40.9% | 31.6% |
| CL | 7 | 8 |

EMA ist konservativer: mehr Trades, weniger DD, aber niedrigere Win-Rate.
Beide Approaches sind profitabel — EMA ist technisch korrekt.

### CL Sensitivity

| CL Threshold | Pass Rate |
|-------------|-----------|
| CL ≤ 8 | 12% (aktuell) |
| CL ≤ 10 | 44% |
| **CL ≤ 12** | **75% (empfohlen)** |
| CL ≤ 15 | 81% |

**Empfehlung:** CL≤12 für V1 Paper Trading. Trend-Strategien mit 200+ Trades
haben natürlicherweise längere Verlustserien als der CL≤8-Threshold erlaubt.

## Gate Thresholds v0.3

| Gate | Threshold | Anmerkung |
|------|-----------|-----------|
| Min Return | 1% | |
| Profit Factor | ≥ 1.05 | |
| Max Drawdown | ≤ 20% | |
| Max Consecutive Losses | ≤ 8 | ⚠️ Zur Diskussion: CL≤12 → 75% Pass |
| Min Sharpe | ≥ 0.1 | |
| Min Trades | 20 | |

## Platform

| | |
|---|---|
| Exchange | Hyperliquid Perps DEX |
| Fees | 0.01% Maker + 1bp Slippage |
| Startkapital | 100€ |
| Leverage | 1x (V1 konservativ) |

## Audit-Trail

- 2026-04-19: Full Pipeline Audit — 12 Bugs gefixt (4 kritisch)
- 2026-04-19: EMA Fix — `ewm_mean` statt `rolling_mean`
- 2026-04-19: Post-Fix Re-Validation — CL-Sensitivity analysiert