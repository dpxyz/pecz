---
title: Phases
---

# 📋 Phasen — Forward V5

## ✅ Phase 0: Freeze & Archive

Alte Systeme eingefroren, Repo aufgeräumt.

## ✅ Phase 1: Skeleton

Grundstruktur, Projekt-Setup, erste ADRs.

## ✅ Phase 2: Core

103 Tests, Projektions-Engine, Basis-Infrastruktur.

## ✅ Phase 3: Observability

Monitoring, Logging, Metriken.

## ✅ Phase 4: Boundaries

Error Handling, Circuit Breaker, Guard Rails.

## ✅ Phase 5: Operations

systemd, CLI, Health Dashboard, Deployment.

## ✅ Phase 6: Test Strategy

24h Stability Test PASSED. Grundlage für Strategy Lab.

## ✅ Phase 7: Strategy Lab

| Was | Ergebnis |
|-----|----------|
| Broad Validation | 8 Assets × 2 Perioden = 16 Tests/Filter |
| Multi-Strategy | 6 Strategien × 3 Assets × 5 Perioden = 90 Tests |
| Regime-Filter | ADX+EMA verdoppelt Pass Rate (12% → 50%) |
| ATR-Filter | Getestet, abgelehnt (kein Improvement) |
| Gold Standard | **MACD+ADX+EMA, CL≤12, 75% Pass Rate** |

**Key ADRs:** ADR-005 (Three-Layer), ADR-006 (Paper Trading), ADR-007 (Leverage Tiers)

## ⭐ Phase 8: Paper Trading — IN PROGRESS

### 8.1 Executor V1 ✅

7 Module gebaut, Integration getestet, 12 Bugs gefixt.

### 8.2 Paper Trading Phase 1 🔵 Running

- **Start:** 2026-04-20
- **Capital:** 100€ Total, 6 Assets, ADR-007 Leverage Tiers
- **Testnet:** Hyperliquid ($999 Balance)
- **Criteria:** ≥10 Trades, ≤25% DD, ≥95% Execution, 14 Tage

### 8.3 Test Suite ✅

**297 Tests, 81% Coverage, 0 Static Issues**

4-Layer Hardening Protocol COMPLETE:
- Schicht 1: pytest-cov → Coverage-Lücken identifiziert
- Schicht 2: ruff + mypy → 0 Issues
- Schicht 3: hypothesis → 15 Property Tests
- Schicht 4: Fault Injection → 21 Tests

| Modul | Coverage |
|-------|----------|
| accounting_check | 94% |
| state_manager | 83% |
| signal_generator | 81% |
| risk_guard | 69% |
| paper_engine | 61% |
| command_listener | 56% |
| data_feed | 48% |
| discord_reporter | 48% |
| watchdog_v2 | 46% |

Täglicher Accounting-Check über Housekeeping.
Pre-Commit Hook: pytest MUSS grün sein.

### 8.4 Bug Audits ✅

6 Audit-Runden, 17 Bugs gefunden & gefixt (4 kritisch, 7 medium, 6 low).
Plus Deep Audit Round 6: 10 weitere Bugs, 27 neue Tests.

### 8.5 Monitor V1 ⬜ NEXT

Equity-per-Bar DB, Live Dashboard, Daily Report, Alerting.

### 8.6 Economics ✅

Framework steht, echte Zahlen nach 14 Tagen.

### 8.7 Paper Trading Phase 2 ⬜

Echte Testnet-API Orders. Voraussetzung: Phase 1 bestanden.

## ⬜ Phase 9: Final Gate

Go/No-Go Entscheidung. Alle Kriterien aus Phase 8 müssen erfüllt sein.

## ⬜ Phase 10: V2 Strategy

Regime-Erkennung + Volatility-Parity + Sentiment-Kill-Switch.
Siehe [V2 Design](v2-design.md) — ADR-008 wird nach Paper Trading geschrieben.