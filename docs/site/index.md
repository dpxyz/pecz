---
title: Mission Control
---

# Forward V5 Mission Control

**Platform:** Hyperliquid | **Mode:** Paper/Mock | **Live:** ⛔ BLOCKED

---

## 🚦 System Status

| Bereich | Status |
|---------|--------|
| Live Trading | ⛔ **BLOCKED** until Phase 9 + sign-off |
| Paper Trading | ✅ **ALLOWED** |
| Mainnet | ⛔ **DISABLED** |
| Aktuelle Phase | **Phase 2** — Core Reliability 🔄 |

---

## 📊 Phasenplan 0–9

```
PHASE 0  ✅ Complete ........ Freeze & Archive
PHASE 1  ✅ Complete ........ Skeleton & ADRs
PHASE 2  🔄 In Progress ..... Core Reliability
PHASE 3  ⬜ Pending ......... Observability
PHASE 4  ⬜ Pending ......... System Boundaries
PHASE 5  ⬜ Pending ......... Operations
PHASE 6  ⬜ Pending ......... Test Strategy
PHASE 7  ⭐ MANDATORY ....... Strategy Lab ← BLOCKS LIVE!
PHASE 8  ⬜ Pending ......... Economics
PHASE 9  ⬜ Pending ......... Review & Gate
                              ↓
                      Manuelle Live-Freigabe
```

| Phase | Name | Status | Blocker |
|-------|------|--------|---------|
| 0 | Freeze & Archive | ✅ Complete | — |
| 1 | Skeleton & ADRs | ✅ **COMPLETE** | — |
| 2 | Core Reliability | 🔄 **STARTED** | Phase 1 |
| 3 | Observability | ⬜ Pending | Phase 2 |
| 4 | System Boundaries | ⬜ Pending | Phase 3 |
| 5 | Operations | ⬜ Pending | Phase 4 |
| 6 | Test Strategy | ⬜ Pending | Phase 5 |
| 7 | **Strategy Lab** ⭐ | ⬜ Pending | Phase 6 |
| 8 | Economics | ⬜ Pending | Phase 7 |
| 9 | Review & Gate | ⬜ Pending | Phase 8 |

---

## 🎯 Phase 2 — Core Reliability Aufgaben

1. **Event Store**
   - [ ] `src/event_store.js` — Append-only events
   - Owner: @assistant

2. **State Projection**
   - [ ] `src/state_projection.js` — Rebuild from events
   - Owner: @assistant

3. **Risk Engine**
   - [ ] `src/risk_engine.js` — Pre-trade validation
   - Owner: @assistant

4. **Reconcile**
   - [ ] `src/reconcile.js` — Position sync
   - Owner: @assistant

---

## 🚧 Offene Blocker

| ID | Blocker | Status | Owner |
|----|---------|--------|-------|
| ~~B1~~ | ~~ADR-003/004 incomplete~~ | ✅ **RESOLVED** | @assistant |
| B2 | Systemd templates needed | ⬜ Pending | @assistant |
| B3 | Strategy Lab not started | ⏳ Phase 7 | @user |

---

## 📂 Weitere Dokumentation

| Bereich | Link |
|---------|------|
| **Test Reports** | [test-reports.md](test-reports.md) |
| **Architecture** | [architecture/](architecture/) |
| **Runbooks** | [runbooks/](runbooks/) |
| **Strategy Lab** | [strategy-lab/](strategy-lab/) |
| **M6 Paper Canary** | [milestones/m6.md](milestones/m6.md) |
| **Economics** | [economics.md](economics.md) |
| **Changelog** | [changelog.md](changelog.md) |

---

*Last updated: 2026-03-08 11:19 UTC*
