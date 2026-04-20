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
| 9 | ⬜ | Final Gate (14+14 Tage) |
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
**Testnet:** Hyperliquid ($999 Balance) | **Reports:** #foundry-reports | **System:** #system

### Quality Assurance

| Was | Status |
|-----|--------|
| **83 Tests** (75 Unit + 7 E2E + 1 Regression) | ✅ 100% Pass |
| **5 Bug Audits** (17 Bugs total, alle gefixt) | ✅ |
| **Accounting Check** (täglich via Housekeeping) | ✅ 5 Invarianten |
| **Pre-Commit Hook** (pytest vor Executor-Commits) | ✅ |
| **4h Summary Reports** (Discord #foundry-reports) | ✅ |

---

## 🏆 Strategie: MACD Momentum + ADX+EMA

| Metrik | Unfiltered | **ADX+EMA Filter** |
|--------|-----------|---------------------|
| Pass Rate | 12% | **75% (CL≤12)** |
| Avg Drawdown | 22.7% | **14.1%** |
| Max Consec. Losses | 9.9 | **6.5** |

**Entry:** `macd_hist > 0 AND close > ema_50 AND ema_50 > ema_200 AND adx_14 > 20`
**Exit:** Trailing Stop 2%, SL 2.5%, Max Hold 48 Bars

Details: [Baseline Strategy](strategy-lab/baseline/) | [ADR-005](architecture/adr-005/) | [ADR-007](architecture/adr-007/)

---

## 🛡️ Guard States

```
RUNNING → SOFT_PAUSE → STOP_NEW → KILL_SWITCH → COOLDOWN → RUNNING
  (ok)    (CL≥5)      (daily>5%)  (DD>20%)      (24h)       (!resume)

SOFT_PAUSE: 24h pause after 5 consecutive losses (CL resets on expiry)
KILL_SWITCH: Force-closes all positions, no new trades
```

Kill-Switches sind non-negotiable und hardcoded.

---

## 🏗️ Executor V1 — Module

| Modul | Status | Beschreibung |
|-------|--------|-------------|
| data_feed | ✅ | Hyperliquid Testnet WebSocket, 1h Candles, SQLite Buffer |
| signal_generator | ✅ | Deterministische MACD+ADX+EMA Logik (Polars) |
| state_manager | ✅ | SQLite State (Position, Equity, Guard, Accounting) |
| risk_guard | ✅ | 5 Guard States, SOFT_PAUSE CL-Reset, KILL Switch force-close |
| paper_engine | ✅ | Orchestrator, Backfill, Slippage, Fees, 4h Reports |
| discord_reporter | ✅ | Components v2 Container mit Farbaccent |
| command_listener | ✅ | !kill, !resume, !status, !help |

Details: [ADR-006](architecture/adr-006/)

---

## ⏭️ Nächste Schritte

1. **Monitor V1** — Equity-Kurve per Bar, Dashboard, Daily Report
2. **14+14 Tage Paper Trading** — Phase 1: Paper, Phase 2: Testnet API
3. **Success Criteria prüfen** — ≥10 Trades, ≤25% DD, Accounting-Invariante
4. **Phase 9: Final Gate** — Go/No-Go Entscheidung
5. **Phase 10: V2 Strategy** — Regime-Score + Volatility-Parity + Sentiment-Kill-Switch

---

## ⚙️ System

| | |
|---|---|
| **Plattform** | Hyperliquid Perps DEX (Testnet) |
| **Startkapital** | 100€ TOTAL (~16.67€/Asset) |
| **Fees** | 0.01% Maker + 1bp Slippage |
| **Discord** | #foundry-reports (trading), #system (housekeeping) |
| **Commands** | !kill, !resume, !status, !help |
| **Tests** | 83 (75 Unit + 7 E2E + 1 Regression) |
| **Accounting** | Daily invariant check via housekeeping |
| **Pre-Commit** | pytest must pass before executor commits |
| **Repo** | [github.com/dpxyz/pecz](https://github.com/dpxyz/pecz) |