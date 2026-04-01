# Roadmap

## Aktueller Status

**Phase 1: Skeleton & ADRs — ✅ COMPLETE**  
**Phase 2: Core Reliability — ✅ COMPLETE (103 Tests)**  
**Phase 3: Observability — ✅ COMPLETE (68 Tests)**

- Block 1 (Event Store) — ✅ COMPLETE (17/17 Tests)  
- Block 2 (State Projection) — ✅ COMPLETE (19/19 Tests)  
- Block 3 (Risk Engine) — ✅ COMPLETE (39/39 Tests)  
- Block 4 (Reconcile) — ✅ COMPLETE (28/28 Tests)
- Block 3.1 (Logger) — ✅ COMPLETE (14/14 Tests)
- Block 3.2 (Health Service) — ✅ COMPLETE (30/30 Tests)
- Block 3.4 (Rebuild CLI) — ✅ COMPLETE (10/10 Tests)
- Block 3.3 (Report Service) — ✅ COMPLETE (14/14 Tests)

## Phase 5: Operations & Deployment — 🔄 IN PROGRESS (2026-04-01)

### Block 5.0d: Memory Monitoring Fix — ✅ GO
| # | Aufgabe | Status | Owner |
|---|---------|--------|-------|
| 5.0d.1 | Trend-basierte Berechnung entfernt | ✅ Complete | @assistant |
| 5.0d.2 | Absolute Thresholds implementiert | ✅ Complete | @assistant |
| 5.0d.3 | Sustained CRITICAL-Logik | ✅ Complete | @assistant |
| 5.0d.4 | Unit Tests (3 Tests) | ✅ Complete | @assistant |
| 5.0d.5 | 24h Runtime Validation | ✅ **GO** | @assistant |

**Status: ✅ GO — Fix 5.0d READY FOR PRODUCTION**

---

### Block 5.1: Systemd Integration — ✅ CODE COMPLETE / ⏳ HOST VALIDATION PENDING
| # | Aufgabe | Status | Owner |
|---|---------|--------|-------|
| 5.1.1 | Service-File erstellen | ✅ Code Complete | @assistant |
| 5.1.2 | Environment/Overrides | ✅ Code Complete | @assistant |
| 5.1.3 | Timeouts & Restart-Policy | ✅ Code Complete | @assistant |
| 5.1.4 | Security Hardening | ✅ Code Complete | @assistant |
| 5.1.5 | Installation & Tests | ⏳ **HOST TEST PENDING** | @user / @assistant |
| 5.1.6 | Echte systemd-Maschine | ⏳ **DEFERRED** | Offen |

**Code Status:**
- forward_v5.service: ✅ Final v1.1 (validated via systemd-analyze)
- INSTALL.md: ✅ Complete
- TESTPLAN.md: ✅ 12 Tests definiert
- deploy_to_vps.sh: ✅ Ready

**Runtime Status:**
- ⏳ Deployment auf Hostinger VPS pending
- ⏳ Realer systemctl start/stop/restart test offen
- ⏳ journald integration test offen

**Note:** Code ist produktionsreif, aber Host-Test auf echter systemd-Maschine ausstehend (Keine Docker-Workarounds).

---

### Block 5.2: Control CLI — ✅ CORE COMPLETE / ⏳ SYSTEMD DEFERRED

**Scope Split:**
- **Core CLI (5.2a):** Status, Logs, Validate, Config, Edit — ✅ COMPLETE
- **Systemd Actions (5.2b):** Start, Stop, Restart, Journal — ⏳ DEFERRED

| Teil | Aufgabe | Status | Owner | Exit Code |
|------|---------|--------|-------|-----------|
| **5.2a.1** | Core CLI Framework | ✅ Complete | @assistant | 0=success |
| **5.2a.2** | `status` Command | ✅ Complete | @assistant | 0 |
| **5.2a.3** | `logs [-n N]` Command | ✅ Complete | @assistant | 0 |
| **5.2a.4** | `validate` Command | ✅ Complete | @assistant | 0 |
| **5.2a.5** | `config` Command | ✅ Complete | @assistant | 0 |
| **5.2a.6** | `edit` Command | ✅ Complete | @assistant | 0 |
| **5.2a.7** | Exit Codes & stderr/stdout | ✅ Complete | @assistant | 0/1/2 |
| **5.2b.1** | `start` (systemd) | ⏳ **DEFERRED** | @assistant | **2** |
| **5.2b.2** | `stop` (systemd) | ⏳ **DEFERRED** | @assistant | **2** |
| **5.2b.3** | `restart` (systemd) | ⏳ **DEFERRED** | @assistant | **2** |
| **5.2b.4** | `journal` (systemd) | ⏳ **DEFERRED** | @assistant | **2** |

**Exit Code 2 (DEFERRED):**
- Wird zurückgegeben bei systemd-Aktionen im Docker-Environment
- Begründung in stderr: Block 5.1 Host Test pending
- Dokumentation: systemd/BLOCK_5_1_STATUS.md

**Verfügbarkeit:**
- ✅ Core CLI: Sofort nutzbar (kein systemd required)
- ⏳ Systemd Actions: Bei VPS-Deploy automatisch verfügbar

---

### Block 5.3: [Next Phase Name] — 🔄 STARTED

---

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
