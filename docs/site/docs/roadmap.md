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

| | Unfiltered | ADX+EMA Filter |
|---|---|---|
| Pass Rate | 12% | **75%** (CL≤12) |
| Avg Drawdown | 22.7% | **14.1%** |
| Max Consec. Losses | 9.9 | **6.5** |

**Entscheidungen:** Foundry FROZEN | ATR abgelehnt | KI als Signalgeber (V2+)

---

## ⭐ Phase 8: Paper Trading — IN PROGRESS

### 8.1: Executor V1 ✅

7 Module, Integrationstest, 12 Bugs gefixt, Discord Commands, Process Manager.

### 8.2: Paper Trading Phase 1 (14 Tage) 🔵 Running

**Start:** 2026-04-20 | **Capital:** 100€ Total | **Mode:** PAPER ONLY | **Assets:** 6

| Kriterium | Target | Aktuell |
|-----------|--------|---------|
| Trades | ≥10 | 0 (Day 1) |
| Drawdown | ≤25% | 0.01% |
| Execution | ≥95% | 100% |
| Dauer | ≥14 Tage | 1/14 |

### 8.3: Test Suite ✅

**83 Tests, 100% Pass**

| Test-File | # | Was geprüft wird |
|------------|---|------------------|
| `test_state_manager` | 14 | Position lifecycle, Equity, Accounting-Invariante |
| `test_risk_guard` | 10 | State Machine, CL-Reset, DD Kill, Daily Loss |
| `test_signal_generator` | 17 | Entry/Exit-Logik, Indikatoren, Parameter |
| `test_discord_reporter` | 18 | 6 Assets in hourly, Format-Funktionen, Farben |
| `test_paper_engine` | 11 | Entry Fee, NET PnL, Position Sizing |
| `test_e2e_system` | 7 | Full Pipeline Candle→Signal→Entry→Exit |

### 8.4: Bug Audits ✅

5 Audit-Runden, 17 Bugs gefunden & gefixt (4 kritisch, 7 medium, 6 low).

### 8.5: Monitor V1 — NEXT ⬜

| Task | Status |
|------|--------|
| Equity-per-Bar in state.db | ⬜ |
| Live Dashboard (pecz.pages.dev/monitor) | ⬜ |
| Daily Discord Report (21:00 Berlin) | ⬜ |
| Alerting (DD>15%, Guard-State Change) | ⬜ |

### 8.6: Economics ✅ Framework

Break-even: 107€/Asset bei 40€/mo Fixkosten. Echte Zahlen nach 14 Tagen.

### 8.7: Paper Trading Phase 2 (14 Tage) ⬜

Echte Testnet-API Orders. Voraussetzung: Phase 1 bestanden.

### Success Criteria (ADR-006)

**Phase 1:** ≥10 Trades | ≤25% DD | Accounting ✅ | ≥95% Execution | 14 Tage
**Phase 2:** ≥5 Orders | 0% API-Fehler | Position sichtbar | Kill-Switch via API | 14 Tage

---

## ⬜ Phase 9: Final Gate

| # | Item | Status |
|---|------|--------|
| 1 | Phase 0-8 abgeschlossen | ⬜ |
| 2 | Paper Trading Kriterien erfüllt | ⬜ |
| 3 | Economics positiv | ⬜ |
| 4 | Security Audit | ⬜ |
| 5 | Manuelle Freigabe (Dave) | ⬜ |

---

## ⬜ Phase 10: V2 Strategy — PLANNED

**Voraussetzung:** Phase 9 bestanden. Kein V2 ohne bewiesene V1-Pipeline.

### V2 Design Principles

1. **Regime-Erkennung als Herzstück** — Trend/Range/Crash → nicht in Range handeln
2. **Volatility-Parity** — Risiko pro Trade konstant, nicht Kapital
3. **Sentiment als Kill-Switch** — Score 0-100, JSON-Mode, nur downsizing
4. **On-Chain als Regime-Filter** — Exchange Netflow 7-14d Aggregation
5. **Kein Indikatoren-Salat** — bessere Regeln, nicht mehr Indikatoren

### Alpha Stack V2 (Priorität)

1. Asset-Ranking (ROC-basiert) — hohe Priorität
2. ADX-based Position Sizing — hohe Priorität
3. 2x Leverage für Blue Chips — mittlere Priorität
4. Limit-Orders statt Market — mittlere Priorität
5. HTF-Alignment — niedrige Priorität
6. ~~ATR-Stops~~ — **abgelehnt** (kein Improvement)
7. ~~Kelly Criterion~~ — **abgelehnt** (instabile Win-Rate)

### V2 Architecture (ADR-005 + ADR-008)

**Sentiment/Macro Risk Layer** (ADR-005, Layer 3):
- KI als Signalgeber: Score 0-100
- Fail-safe: Bei Fehler → ignorieren (nicht handeln ist sicherer)
- Nur Downsizing, nie Upsizing
- JSON-Mode für deterministische Extraktion
- V2+: Sentiment = High Priority für 1h Timeframe

---

## 🚫 Was wir NICHT machen

- Keine Strategie-Änderungen während Paper Trading
- Kein KI-Richter (nur KI-Signalgeber)
- Kein Live Trading ohne Paper Proof
- Keine Gate-Relaxation (Thresholds bleiben)
- Kein Phase-Skipping