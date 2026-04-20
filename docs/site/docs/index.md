---
title: Mission Control
---

# 🎯 Forward V5 — Mission Control

> **Ziel:** Ein trading-fähiges System das beweist, dass es profitabel arbeitet — nicht nur im Backtest, sondern unter echten Bedingungen.

---

## 📍 Aktueller Stand

**Phase 8 ⭐ LIVE** | Paper Engine läuft seit 2026-04-20

| Phase | Status | Was |
|-------|--------|-----|
| 0–6 | ✅ | Grundstruktur bis Test Strategy |
| 7 | ✅ | Strategy Lab — Gold Standard gefunden |
| **8** | **⭐ LIVE** | **Paper Trading läuft** |
| 9 | ⬜ | Final Gate (nach 30+ Tagen) |
| 10 | ⬜ | V2 Strategy (Regime + Volatility-Parity) |

---

## 🟢 Paper Trading Engine — LIVE

**Gestartet:** 2026-04-20 | **Mode:** PAPER ONLY | **Capital:** 100€ Total

| Asset | Leverage | Allocation |
|-------|----------|------------|
| BTC | 1.8x | ~16.67€ |
| ETH | 1.8x | ~16.67€ |
| SOL | 1.5x | ~16.67€ |
| AVAX | 1.0x | ~16.67€ |
| DOGE | 1.5x | ~16.67€ |
| ADA | 1.5x | ~16.67€ |

**Strategy:** MACD+ADX+EMA | **Kill-Switches:** CL≥5, DD>20%, DailyLoss>5%
**Testnet:** Hyperliquid ($999 Balance) | **Reports:** #foundry-reports

---

## 🏆 Strategie: MACD Momentum + ADX+EMA

| Metrik | Unfiltered | **ADX+EMA Filter** |
|--------|-----------|---------------------|
| Pass Rate | 12% | **75% (CL≤12)** |
| Avg Drawdown | 22.7% | **14.1%** |
| Max Consec. Losses | 9.9 | **6.5** |

**Entry:** `macd_hist > 0 AND close > ema_50 AND ema_50 > ema_200 AND adx_14 > 20`
**Exit:** Trailing Stop 2%, SL 2.5%, Max Hold 48 Bars

---

## 🛡️ Guard States

```
RUNNING → SOFT_PAUSE → STOP_NEW → KILL_SWITCH → COOLDOWN → RUNNING
  (ok)    (CL≥5)      (daily>5%)  (DD>20%)      (24h)       (!resume)
```

---

## ⏭️ Nächste Schritte

1. **Monitor V1** — Equity-Kurve per Bar, Dashboard, Daily Report (NOW)
2. **30+ Tage Paper Trading** — läuft autonom
3. **Success Criteria prüfen** — ≥30 Trades, ≤25% DD, ≤10pp Win-Rate
4. **Phase 9: Final Gate** — Go/No-Go Entscheidung
5. **V2 Design** — Regime-Score + Volatility-Parity + Sentiment-Kill-Switch

---

## ⚙️ System

| | |
|---|---|
| **Plattform** | Hyperliquid Perps DEX (Testnet) |
| **Startkapital** | 100€ TOTAL (~16.67€/Asset) |
| **Fees** | 0.01% Maker + 1bp Slippage |
| **Discord** | #foundry-reports (automated) |
| **Commands** | !kill, !resume, !status, !help |
| **Repo** | [github.com/dpxyz/pecz](https://github.com/dpxyz/pecz) |