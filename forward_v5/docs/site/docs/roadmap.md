# Roadmap

## Aktueller Status

**Phase 1: Skeleton & ADRs — ✅ COMPLETE**  
**Phase 2: Core Reliability — ✅ COMPLETE (103 Tests)**  
**Phase 3: Observability — 🔄 IN PROGRESS**

- Block 1 (Event Store) — ✅ COMPLETE (17/17 Tests)  
- Block 2 (State Projection) — ✅ COMPLETE (19/19 Tests)  
- Block 3 (Risk Engine) — ✅ COMPLETE (39/39 Tests)  
- Block 4 (Reconcile) — ✅ COMPLETE (28/28 Tests)

## Phase 2 COMPLETE (2026-03-08)

### ~~Block 1: Event Store~~ ✅ COMPLETE
| # | Aufgabe | Status | Owner |
|---|---------|--------|-------|
| 1.1 | Schema: events table (SQLite) | ✅ Complete | @assistant |
| 1.2 | `append(event)` mit Idempotenz | ✅ Complete | @assistant |
| 1.3 | `getEvents()` mit Pagination | ✅ Complete | @assistant |
| 1.4 | Performance: sequence ordering | ✅ Complete | @assistant |
| 1.5 | Tests: 17 Unit Tests | ✅ Complete (17/17) | @assistant |

### ~~Block 2: State Projection~~ ✅ COMPLETE
| # | Aufgabe | Status | Owner |
|---|---------|--------|-------|
| 2.1 | Reducer für alle Event-Typen (27 Stück) | ✅ Complete | @assistant |
| 2.2 | `project(events[])` → State | ✅ Complete | @assistant |
| 2.3 | `rebuild()` aus Event Store | ✅ Complete | @assistant |
| 2.4 | Tests: Rebuild == Live | ✅ Complete | @assistant |
| 2.5 | Tests: 19 Unit Tests | ✅ Complete (19/19) | @assistant |

### ~~Block 3: Risk Engine~~ ✅ COMPLETE
| # | Aufgabe | Status | Owner |
|---|---------|--------|-------|
| 3.1 | Sizing Gate (min/max notional) | ✅ Complete | @assistant |
| 3.2 | Hyperliquid Rules ($10 min) | ✅ Complete | @assistant |
| 3.3 | Watchdog Gate (stale tick) | ✅ Complete | @assistant |
| 3.4 | Reconcile Gate (mismatch) | ✅ Complete | @assistant |
| 3.5 | Unmanaged Position Gate | ✅ Complete | @assistant |
| 3.6 | Symbol Whitelist | ✅ Complete | @assistant |
| 3.7 | Tests: 39 Gate-Tests | ✅ Complete (39/39) | @assistant |

### ~~Block 4: Reconcile~~ ✅ COMPLETE
| # | Aufgabe | Status | Owner |
|---|---------|--------|-------|
| 4.1 | Position comparison logic | ✅ Complete (4 detectors) | @assistant |
| 4.2 | Mismatch detection: Ghost, Unmanaged, Size, Side | ✅ Complete | @assistant |
| 4.3 | Severity classification (BLOCK vs WARN) | ✅ Complete | @assistant |
| 4.4 | Integration mit Event Store | ✅ Complete | @assistant |
| 4.5 | Tests: 28 Unit Tests | ✅ Complete (28/28) | @assistant |

### Phase 2 Acceptance
| # | Kriterium | Status |
|---|-----------|--------|
| A1 | Alle Module implementiert | ✅ 4 Blocks complete |
| A2 | Unit Tests >80% Coverage | ✅ 103/103 passing (100%) |
| A3 | Integration Tests passing | ✅ Rebuild == Live State |
| A4 | Rebuild == Live State | ✅ Verified |
| A5 | Paper/Mock only (no live) | ✅ Hyperliquid Paper |
| A6 | Dokumentation complete | ✅ Mission Control |

### Acceptance Gate: COMPLETE ✅
Date: 2026-03-08
Tag: v5-phase2-block4-complete

## Parallel (Phase 1 Nachzügler)
| # | Aufgabe | Status | Owner |
|---|---------|--------|-------|
| P1 | Systemd Templates | ⬜ Optional | @assistant |
| P2 | Control CLI Skeleton | ⬜ Optional | @assistant |

## Timeline

```
Mar 06-07: Phase 1 ✅ COMPLETE
Mar 08-10: Phase 2 🔄 Block 1-2 (Event, Projection)
Mar 11-17: Phase 2 🔄 Block 3 (Risk Engine)
Mar 18-24: Phase 2 🔄 Block 4 (Reconcile) + Acceptance
Mar 25-31: Phase 3-6 (Observability, Boundaries, Operations, Tests)
Apr 01-07: Phase 7 ⭐ (Strategy Lab)
Apr 08-11: Phase 8-9 (Economics, Review)
Apr 12:    ⛔ Manual Sign-off
```

## Abhängigkeiten

```
Event Store ──▶ State Projection ──▶ Risk Engine ──▶ Core Engine
     │                 │                  │
     └────────▶ Reconcile ◀─────────────┘
```

---

*Last updated: 2026-03-08 11:27 UTC*  
*Plan: docs/phase2_plan.md*
