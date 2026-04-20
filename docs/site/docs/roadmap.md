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

### Ergebnis
| | Unfiltered | ADX+EMA Filter |
|---|---|---|
| Pass Rate | 12% | **75%** (CL≤12) |
| Avg Drawdown | 22.7% | **14.1%** |
| Max Consec. Losses | 9.9 | **6.5** |

### Entscheidungen
- **Foundry FROZEN** — keine Strategieänderungen während Paper Trading
- **ATR-Filter getestet und abgelehnt** — ADX+EMA bleibt Gold Standard
- **KI als Signalgeber = YES** (V2+), KI als Richter = NO

---

## ⭐ Phase 8: Paper Trading — IN PROGRESS

**Ziel:** Beweisen dass die Strategie unter Echtbedingungen funktioniert.

### 8.1: Executor V1 ✅ COMPLETE

7 Module gebaut, Integration getestet, 12 Bugs gefixt, Discord Commands, Process Manager.

### 8.2: Paper Trading — Phase 1 (14 Tage) 🟢

| Task | Beschreibung | Status |
|------|-------------|--------|
| Hyperliquid Testnet | API Wallet autorisiert, $999 Balance | ✅ |
| Embed-Formatierung | Components v2 Container mit Farbaccent | ✅ |
| !kill / !resume | Discord Commands für Guard-Override | ✅ |
| Process Manager | Auto-start, restart on crash | ✅ |
| Paper Engine gestartet | 6 Assets, 100€ Total, Testnet WS | ✅ |
| **Test Suite** | **82 Tests (75 Unit + 7 E2E), 100% Grün** | ✅ |
| 14-Day Paper Run | Echtzeit Signal-Validierung | 🔵 Running |

**Start:** 2026-04-20 | **Capital:** 100€ Total (~16.67€/Asset) | **Mode:** PAPER ONLY

### 8.3: Test Suite — ✅ COMPLETE

**82 Tests, Commit 68e4f8e, `pytest tests/ -v`**

| Test-File | # | Was geprüft wird |
|------------|---|------------------|
| `test_state_manager` | 14 | Position lifecycle, Equity, BUG 2 Regr., Accounting-Invariante |
| `test_risk_guard` | 9 | State Machine, BUG 4 Regr., CL-Tracker, DD Kill |
| `test_signal_generator` | 17 | Entry/Exit-Logik, Indikatoren, Parameter-Konsistenz |
| `test_discord_reporter` | 18 | BUG 3 Regr. (6 Assets), Format-Funktionen, Farben |
| `test_paper_engine` | 11 | BUG 1+2 Regr., Position Sizing, Multi-Trade Accounting |
| `test_e2e_system` | 7 | Full Pipeline: Candle→Signal→Guard→Entry→Exit→Equity |

**Workflow für neue Bugs:**
1. Bug finden → fixen
2. Test schreiben der den Bug **vor** dem Fix reproduziert (sollte FAILen)
3. Fix anwenden → Test muss PASSen
4. `pytest tests/ -v` → alles grün = sicher
5. Commit mit Bug-Referenz

**Bekannte Lücken (nur Paper Trading deckt das ab):**
- Multi-Asset Concurrent / SQLite Race Conditions
- Crash Mid-Trade / Restart Recovery
- Echte WebSocket-Formate
- CommandListener + Discord Polling
- Edge Cases mit echten Marktdaten

### 8.5: Monitor V1 — NEXT

| Task | Beschreibung | Status |
|------|-------------|--------|
| Equity-per-Bar DB | Stündlicher Portfolio-Wert in state.db | ⬜ |
| Live Dashboard | pecz.pages.dev/monitor (MkDocs) | ⬜ |
| Daily Report | Discord Embed um 21:00 Berlin | ⬜ |
| Alerting | DD>15%, Guard-State Change, Equity ATH | ⬜ |

### 8.6: Economics — FRAMEWORK DONE

| Report | Status |
|--------|--------|
| Monthly PnL Projection | ✅ |
| Infra Costs (40€/mo) | ✅ |
| Break-even Analysis (107€/asset) | ✅ |
| Actual Numbers | ⬜ (nach 14 Tagen) |

### 8.7: Testnet API Trading — Phase 2 (14 Tage) ⬜

| Task | Beschreibung | Status |
|------|-------------|--------|
| Order Executor Module | Echte Orders an Hyperliquid Testnet API | ⬜ |
| Position Verification | Trades sichtbar auf app.hyperliquid-testnet.xyz | ⬜ |
| API Error Handling | Timeouts, Partial Fills, Rate Limits | ⬜ |
| Kill-Switch via API | Position schließen per !kill Command | ⬜ |
| API Integration Tests | Eigene Test-Suite für Order-Flow | ⬜ |

**Voraussetzung:** Phase 1 (Paper Trading) bestanden.

### Success Criteria (ADR-006, Updated)

**Phase 1 — Paper (14 Tage):**
- ≥10 Trades | ≤25% DD | Accounting-Invariante ✅ | ≥95% Execution | ≥14 Tage

**Phase 2 — Testnet API (14 Tage):**
- ≥5 Orders platziert | 0% API-Fehler | Position sichtbar | Kill-Switch via API | ≥14 Tage

**Gate:** Phase 2 nur starten wenn Phase 1 alle Kriterien erfüllt.

---

## ⬜ Phase 9: Final Gate — PENDING

**Ziel:** Endgültige Go/No-Go Entscheidung für Live Trading.

| # | Item | Status |
|---|------|--------|
| 1 | Alle Phasen 0-8 abgeschlossen | ⬜ |
| 2 | Paper Trading Success Criteria erfüllt | ⬜ |
| 3 | Economics positiv | ⬜ |
| 4 | Security Audit | ⬜ |
| 5 | Manuelle Freigabe (Dave) | ⬜ |

---

## ⬜ Phase 10: V2 Strategy — PLANNED

**Voraussetzung:** Phase 9 bestanden. Kein V2 ohne bewiesene V1-Pipeline.

### V2 Design Principles
- **Regime-Erkennung als Herzstück** — Trend/Range/Crash → Trade nicht in Range
- **Volatility-Parity** — Risiko pro Trade konstant, nicht Kapital
- **Sentiment als Kill-Switch** — Score 0-100, JSON-Mode, Fail-safe=ignore
- **On-Chain als Regime-Filter** — Exchange Netflow 7-14d, nicht Whale-Tracking
- **Kein Indikatoren-Salat** — bessere Regeln, nicht mehr Indikatoren

---

## 🚫 Was wir NICHT machen

- Keine Gate-Relaxation (Thresholds bleiben)
- Keine Strategie-Änderungen während Paper Trading
- Kein KI-Richter (nur KI-Signalgeber in V2+)
- Kein Live Trading ohne Paper Trading Proof
- Kein Phase-Skipping