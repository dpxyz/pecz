---
title: Roadmap
---

# 🗺️ Roadmap — Forward V5

> Jede Phase muss vollständig abgeschlossen sein bevor die nächste beginnt. Keine Ausnahmen.

---

## ✅ Phase 0–6: Foundation COMPLETE

| Phase | Name | Ergebnis |
|-------|------|----------|
| 0 | Freeze & Archive | Alte Systeme eingefroren |
| 1 | Skeleton | Grundstruktur, ADRs |
| 2 | Core | 103 Tests, Projektions-Engine |
| 3 | Observability | Monitoring, Logging |
| 4 | Boundaries | Error Handling, Circuit Breaker |
| 5 | Operations | systemd, CLI, Health Dashboard |
| 6 | Test Strategy | 24h Stability Test PASSED |

---

## ✅ Phase 7: Strategy Lab — COMPLETE

**Ziel:** Mindestens eine robuste, validierte Strategie für Paper Trading finden.

### Was wurde gemacht
- Backtest Engine v2 (Polars, Walk-Forward, vectorized)
- DSL Translator (8 Indikatoren, Condition Parser, kein eval/exec)
- 6 Strategie-Typen über 3 Assets × 5 Zeiträume validiert (90 Tests)
- Regime-Filter Breakthrough: ADX+EMA verdoppelt Pass-Rate (12%→50%)
- ATR-Filter getestet und abgelehnt
- Gold Standard identifiziert: **MACD Momentum + ADX+EMA**

### Ergebnis
| | Unfiltered | ADX+EMA Filter |
|---|---|---|
| Pass Rate | 12% | **50%** |
| Avg Drawdown | 22.7% | **14.1%** |
| Max Consec. Losses | 9.9 | **6.5** |

### Entscheidungen
- **Keine weitere Gate-Relaxation** — Thresholds bleiben wie sie sind
- **Keine weiteren Filter-Tests** — ATR getestet, abgelehnt
- **KI als Signalgeber = YES** (ADR-005 V2+), KI als Richter = NO
- **Ziel-Shift:** Besserer Backtest → Strategie unter Echtzeit beweisen

---

## ⭐ Phase 8: Paper Trading + Economics — IN PROGRESS

**Ziel:** Beweisen dass die Strategie unter echten Bedingungen funktioniert.

### 8.1: Executor V1 ✅ BUILD COMPLETE

| Modul | Beschreibung | Status |
|-------|-------------|--------|
| data_feed.py | Hyperliquid WebSocket, 1h Candles, SQLite | ✅ |
| signal_generator.py | MACD+ADX+EMA, deterministic | ✅ |
| state_manager.py | Position, Equity, Guard State (SQLite) | ✅ |
| risk_guard.py | 5 Guard States, hardcoded thresholds | ✅ |
| paper_engine.py | Orchestrator, Backfill, Slippage, Fees | ✅ |
| discord_reporter.py | #foundry-reports, OpenClaw message tool | ✅ |
| test_integration.py | 376 Trades auf BTC+ETH 2024 | ✅ |

### 8.2: Paper Trading Setup — TODO

| Task | Beschreibung | Status |
|------|-------------|--------|
| Embed-Formatierung | Farbige Discord Reports (Components v2) | ✅ |
| `!kill` / `!resume` | Discord Commands für Guard-Override | ✅ |
| Process Manager | Auto-start, restart on crash (5/5min) | ✅ |
| systemd Unit | Für später (non-Docker) | ✅ |
| Hyperliquid Testnet | Testnet-Setup, API Keys | ⬜ |
| 30+ Day Run | Echtzeit Paper Trading | ⬜ |

### Success Criteria (ADR-006)
- ≥30 Trades
- ≤25% Drawdown
- ≤10pp Win-Rate Deviation vs. Backtest
- ≥30 Tage Laufzeit
- ≥95% Signal Execution Rate
- ≤60s Kill-Switch Response

### 8.3: Economics — NACH Paper Trading

| Report | Inhalt |
|--------|--------|
| Monthly PnL Projection | Erwarteter Return bei 100€ |
| Infra Costs | Server, API, Monitoring |
| Break-even Analysis | Trades/Tag für Profitabilität |
| Risk-adjusted Returns | Sharpe, Sortino, Calmar |

---

## ⬜ Phase 9: Final Gate — PENDING

**Ziel:** Endgültige Go/No-Go Entscheidung für Live Trading.

### Checklist

| # | Item | Status |
|---|------|--------|
| 1 | Alle Phasen 0-8 abgeschlossen | ⬜ |
| 2 | Paper Trading Success Criteria erfüllt | ⬜ |
| 3 | Economics positiv | ⬜ |
| 4 | Security Audit | ⬜ |
| 5 | On-Call Setup | ⬜ |
| 6 | Rollback getestet | ⬜ |
| 7 | **Manuelle Freigabe (Dave)** | ⬜ |

### Go/No-Go

```
╔══════════════════════════════════════════════╗
║  LIVE TRADING GO/NO-GO                       ║
║                                               ║
║  Decision:  [ ] GO    [ ] NO-GO              ║
║                                               ║
║  If GO:                                       ║
║  [ ] ENABLE_EXECUTION_LIVE=true              ║
║  [ ] MAINNET_TRADING_ALLOWED=true            ║
║                                               ║
║  Signature: ___________  Date: __________     ║
╚══════════════════════════════════════════════╝
```

---

## 🚫 Was wir NICHT machen

- Keine Gate-Relaxation (Thresholds bleiben)
- Keine weiteren Filter-Tests (ATR abgelehnt)
- Kein KI-Richter (nur KI-Signalgeber in V2+)
- Kein Live Trading ohne Paper Trading Proof
- Kein Phase-Skipping