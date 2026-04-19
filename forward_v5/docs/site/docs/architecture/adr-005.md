# Foundry V1 — Baseline Strategy Spec (Gold Standard)

**Committed:** 2026-04-19  
**Status:** APPROVED for Paper/Forward Testing  
**Source:** Regime-Filter Validation (8 Assets × 2 Periods × 5 Filter Variants)

## Strategy: MACD Momentum + ADX+EMA Regime Filter

### Entry Condition
```
macd_hist > 0 AND close > ema_50 AND ema_50 > ema_200 AND adx_14 > 20
```

### Exit Conditions
| Parameter | Value |
|-----------|-------|
| Trailing Stop | 2.0% |
| Stop Loss | 2.5% |
| Max Hold | 48 bars (48h on 1h timeframe) |

### Indicators
| Indicator | Params |
|-----------|--------|
| MACD | fast=12, slow=26, signal=9 |
| EMA 50 | period=50 |
| EMA 200 | period=200 |
| ADX | period=14 |

### Regime Filter Logic
- **EMA50 > EMA200**: Bull trend confirmed (no longs in bear phases)
- **ADX > 20**: Genuine trend strength (no range chop)
- **MACD hist > 0**: Momentum confirmation

## Gate Thresholds (v0.3 — UNCHANGED, NO RELAXATION)

| Gate | Threshold |
|------|-----------|
| Min Return | ≥ 1% |
| Min Profit Factor | ≥ 1.05 |
| Max Drawdown | ≤ 20% |
| Max Consecutive Losses | ≤ 8 |
| Min Trades | ≥ 20 |
| Min Sharpe | ≥ 0.1 |

## Validation Results

### Baseline (ADX+EMA) — 8 Assets × 2 Periods = 16 Tests

| Asset | Period | Trades | Return | PF | DD% | Win% | CL | Sharpe | Gate |
|-------|--------|--------|--------|------|------|------|----|--------|------|
| BTCUSDT | 2024_full | 181 | +30.7% | 1.398 | 14.5% | 40.9% | 7 | 9.57 | ✅ |
| BTCUSDT | 2025_q1 | 31 | -3.4% | 0.786 | 12.4% | 22.6% | 11 | -6.95 | ❌ |
| ETHUSDT | 2024_full | 185 | +27.2% | 1.328 | 11.0% | 39.5% | 8 | 9.13 | ✅ |
| ETHUSDT | 2025_q1 | 28 | +4.0% | 1.303 | 6.9% | 42.9% | 5 | 8.01 | ✅ |
| SOLUSDT | 2024_full | 200 | +26.1% | 1.197 | 25.7% | 38.0% | 9 | 5.99 | ❌ |
| SOLUSDT | 2025_q1 | 36 | +0.1% | 1.004 | 14.0% | 38.9% | 6 | 0.14 | ❌ |
| DOGEUSDT | 2024_full | 279 | +149.5% | 1.695 | 21.6% | 44.1% | 9 | 16.44 | ❌ |
| DOGEUSDT | 2025_q1 | 21 | -4.5% | 0.783 | 6.9% | 47.6% | 3 | -9.32 | ❌ |
| AVAXUSDT | 2024_full | 218 | +59.5% | 1.354 | 14.4% | 41.7% | 6 | 9.66 | ✅ |
| AVAXUSDT | 2025_q1 | 25 | +11.9% | 1.775 | 8.4% | 40.0% | 7 | 19.09 | ✅ |
| LINKUSDT | 2024_full | 227 | +83.2% | 1.593 | 15.1% | 44.5% | 5 | 15.10 | ✅ |
| LINKUSDT | 2025_q1 | 53 | -10.8% | 0.717 | 17.1% | 43.4% | 4 | -12.52 | ❌ |
| XRPUSDT | 2024_full | 245 | +90.0% | 1.573 | 20.3% | 43.3% | 8 | 12.04 | ❌ |
| XRPUSDT | 2025_q1 | 50 | +11.7% | 1.329 | 12.5% | 40.0% | 4 | 8.70 | ✅ |
| ADAUSDT | 2024_full | 201 | +105.0% | 1.846 | 14.1% | 45.3% | 8 | 18.49 | ✅ |
| ADAUSDT | 2025_q1 | 29 | -6.6% | 0.791 | 11.3% | 34.5% | 4 | -8.25 | ❌ |

**Pass Rate: 8/16 (50%)**
**Avg Return: +35.9% | Avg DD: 14.1% | Avg CL: 6.5**

### ATR Filter Comparison (NO IMPROVEMENT)

| Variant | Pass | Avg Return | Avg DD | Avg CL |
|---------|------|------------|--------|--------|
| **BASELINE (ADX+EMA)** | **50%** | **+35.9%** | 14.1% | 6.5 |
| ATR_EXPANSION | 44% | +26.4% | 10.4% | 6.4 |
| ATR_TIGHT | 50% | +21.1% | 10.7% | 5.8 |
| EMA_ONLY | 25% | +46.9% | 13.6% | 6.6 |

**Decision: ADX+EMA remains baseline. ATR adds complexity without improving pass rate.**

## Fee Structure
- **Exchange:** Hyperliquid Perps DEX
- **Maker Fee:** 0.01% + 1bp
- **Start Capital:** 100€
- **Leverage:** 1x (conservative for V1)

## What Changed Since Last Commit
- ATR regime filter tested → no improvement over ADX+EMA
- ADR-005: Three-Layer Architecture (Foundry → Executor → Monitor)
- News/Macro Risk Layer defined (KI als Signalgeber, nicht als Richter)
- Gate thresholds UNCHANGED, NO relaxation