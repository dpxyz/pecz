# MASTERPLAN: Forward V5 Phasen 0-9
## Professional Trading System Architecture

**Status:** Phase 0 Complete | Phase 1-4 CODE Complete | Phase 5 CODE Complete | Phase 6 IN PROGRESS  
**Platform:** Hyperliquid  
**Mode:** Paper/Mock only (Live BLOCKED until Phase 9)  
**Strategy Lab:** MANDATORY before any Live discussion

---

## Executive Summary

| Phase | Name | Deliverable | Live? |
|-------|------|-------------|-------|
| 0 | Freeze & Archive | Legacy system archived | **BLOCKED** |
| 1 | Skeleton + ADRs | Directory structure, decisions | **BLOCKED** |
| 2 | Core Reliability | Event store, state projection, tests | **BLOCKED** |
| 3 | Observability | Reports, health, logs | **BLOCKED** |
| 4 | System Boundaries | Safety/Observability separation | **BLOCKED** |
| 5 | Operations | systemd, CLI, incident response | **BLOCKED** |
| 6 | Test Strategy | Unit, integration, simulation | **BLOCKED** |
| 7 | **Strategy Lab** ⭐ | Backtests, Walk-forward, Scorecards | **BLOCKED** |
| 8 | Economics | PnL projections, cost analysis | **BLOCKED** |
| 9 | Review & Gate | Final validation, sign-off required | **BLOCKED** |

**→ ERST DANN:** Manuelle Live-Freigabe durch Nutzer

---

## Phase 0: Freeze & Archive ✅ COMPLETE

### Ziele
- Altes System (R4c) einfrieren
- Archiv für spätere Analyse
- Clean slate für V5

### Deliverables
- [x] Old services stopped
- [x] `incident_bundles/` archived
- [x] `runtime/` backed up
- [x] Read-only mode enforced

### Status: ✅ DONE

---

## Phase 1: Skeleton + Architecture ✅ IN PROGRESS

### Ziele
- Directory structure
- Architecture Decision Records
- systemd units
- Control CLI skeleton

### Deliverables

```
forward_v5/
├── docs/
│   ├── ADR-001-target-architecture.md     ✅
│   ├── ADR-002-hyperliquid-integration.md  ✅
│   ├── ADR-003-state-model.md             📋
│   ├── ADR-004-risk-controls.md           📋
│   ├── MASTERPLAN_PHASES_1-9.md           ✅
│   └── HYPERLIQUID_MIGRATION_FIXES.md     ✅
├── src/
│   ├── core_engine.js (skeleton)          📋
│   ├── state_projection.js (skeleton)   📋
│   ├── event_store.js (skeleton)          📋
│   └── index.js                           📋
├── config/
│   ├── systemd/forward-v5.service         📋
│   └── m6_paper_canary.env                📋
└── tests/
    └── skeleton.test.js                   📋
```

### Definition of Done
- [ ] Alle ADRs geschrieben + approved
- [ ] Directory structure angelegt
- [ ] systemd units definiert
- [ ] Skeleton tests passing

### Status: 🔄 IN PROGRESS

---

## Phase 2: Core Reliability ⬜ PENDING

### Ziele
- Deterministischer Event Store
- State Projection
- Risk Engine
- Reconcile Logic

### Deliverables

| Modul | Zweck | Tests |
|-------|-------|-------|
| `src/event_store.js` | Append-only events | ✅ Unit |
| `src/state_projection.js` | Rebuild state from events | ✅ Unit |
| `src/risk_engine.js` | Pre-trade validation | ✅ Unit |
| `src/reconcile.js` | Position sync (mock) | ✅ Unit |

### Key Features
- **Single Writer:** Nur core_engine schreibt
- **Replay:** State rebuild from events
- **Idempotency:** UUIDs für alles
- **Timeouts:** Überall

### Definition of Done
- [ ] Event Store: append-only, queryable
- [ ] State Projection: rebuild from zero
- [ ] Risk Engine: alle Pre-Trade checks
- [ ] Unit Tests: > 80% coverage

### Status: ⬜ PENDING

---

## Phase 3: Observability ⬜ PENDING

### Ziele
- Discord reports
- Health heartbeats
- Structured logs
- Rebuild-state command

### Deliverables

| Modul | Zweck | Blocking? |
|-------|-------|-----------|
| `src/report_service.js` | Discord/status | NO |
| `src/health.js` | Heartbeats, checks | NO |
| `src/logger.js` | Structured logging | NO |
| `commands/rebuild_state.js` | Rebuild projection | N/A |

### Key Features
- Non-blocking: Discord down = WARN, nicht BLOCK
- Heartbeats mit Timestamp
- Structured logs (JSON)

### Definition of Done
- [ ] Reports funktionieren (auch wenn Discord down)
- [ ] Health checks mit Freshness
- [ ] Rebuild command getestet

### Status: ⬜ PENDING

---

## Phase 4: System Boundaries ⬜ PENDING

### Ziele
- Safety vs Observability Trennung
- Klare Fail-Modes
- Incident Response Plan

### Deliverables

```
docs/
├── safety_boundary.md
├── observability_boundary.md
└── incident_response.md
```

### Boundaries

| Domain | Examples | Fail Mode |
|--------|------------|-----------|
| **SAFETY** | sizing, reconcile, watchdog | **BLOCK** |
| | leverage, unmanaged position | **BLOCK** |
| **OBSERVABILITY** | discord, reports | **WARN** |
| | scheduler, health | **RETRY** |

### Definition of Done
- [ ] Safety checks identifiziert
- [ ] Observability checks identifiziert
- [ ] Incident Response documented

### Status: ⬜ PENDING

---

## Phase 5: Operations ⬜ PENDING

### Ziele
- systemd services
- Control API/CLI
- Logging, Rotation
- Keine manuellen Edits

### Deliverables

| Komponente | Beschreibung |
|------------|--------------|
| `systemd/forward-v5.service` | Main service |
| `systemd/forward-v5-report.service` | Report worker |
| `commands/start.js` | Start service |
| `commands/stop.js` | Stop service |
| `commands/pause.js` | Pause execution |
| `commands/resume.js` | Resume after review |
| `commands/status.js` | Current status |
| `commands/reconcile.js` | Force reconcile |

### Configuration
```ini
[Service]
Type=simple
Restart=on-failure
RestartSec=5
StartLimitBurst=3
StartLimitIntervalSec=60
```

### Definition of Done
- [x] Code Complete: Systemd units definiert
- [x] Code Complete: Alle Commands funktionieren
- [x] Code Complete: Health Dashboard + Alert Engine
- [ ] Ops Pending: Systemd units getestet auf VPS (5.1 - benötigt SSH)
- [ ] Ops Pending: Systemd Actions (5.2 - wartet auf 5.1)

### Status: ✅ CODE COMPLETE (5.1/5.2 ops pending)

---

## Phase 6: Test Strategy 🔄 IN PROGRESS

### Aktueller Stand (April 2026)

| Bereich | Status | Notizen |
|---------|--------|---------|
| Unit Tests | 🔄 Partial | event_store, risk_engine, state_projection, reconcile |
| Integration Tests | 🔄 Started | Alert Engine Tests (Phase 6 Step 1) |
| Acceptance Gates | 🔄 Started | G5: Discord Failover ✅ Complete |
| Simulation | ⬜ Pending | 1h Smoke, 24h Stability |

### Acceptance Gates
| Gate | Kriterium | Status |
|------|-----------|--------|
| G1 | Zero unmanaged positions | 🔄 Nächster Step |
| G2 | Projection parity (rebuild == live) | ⬜ Pending |
| G3 | Recovery from restart | ⬜ Pending |
| G4 | No duplicated trade IDs | ⬜ Pending |
| G5 | Report failures don't affect trading | ✅ Complete (acceptance_g5_discord_failover.test.js) |

### Deliverables

```
tests/
├── unit/                          # Existierend
│   ├── event_store.test.js       # ✅
│   ├── state_projection.test.js  # ✅
│   ├── risk_engine.test.js       # ✅
│   └── reconcile.test.js         # ✅
├── integration/                   # NEU
│   ├── alert_engine.integration.test.js     # ✅ (5.3 Integration)
│   └── watchdog_stale_pause.test.js         # ⬜
├── simulation/                    # ⬜
│   ├── 1h_smoke.test.js
│   └── 24h_stability.test.js
└── acceptance/                     # IN PROGRESS
    ├── acceptance_g5_discord_failover.test.js  # ✅
    ├── acceptance_g1_zero_unmanaged.test.js      # 🔄 Next
    ├── projection_parity.test.js                  # ⬜
    └── recovery.test.js                           # ⬜
```
- Simulation
- Acceptance gates

### Deliverables

```
tests/
├── unit/
│   ├── event_store.test.js
│   ├── state_projection.test.js
│   ├── risk_engine.test.js
│   └── reconcile.test.js
├── integration/
│   ├── tick_to_fill.test.js
│   ├── discord_down_no_stop.test.js
│   └── watchdog_stale_pause.test.js
├── simulation/
│   ├── 1h_smoke.test.js
│   └── 24h_stability.test.js
└── acceptance/
    ├── zero_unmanaged.test.js
    ├── projection_parity.test.js
    └── recovery.test.js
```

### Acceptance Gates
| Gate | Kriterium |
|------|-----------|
| G1 | Zero unmanaged positions |
| G2 | Projection parity (rebuild == live) |
| G3 | Recovery from restart |
| G4 | No duplicated trade IDs |
| G5 | Report failures don't affect trading |

### Definition of Done
- [ ] Unit Tests: > 80% coverage
- [ ] Integration Tests: all passing
- [ ] Simulation: 24h stable
- [ ] Acceptance Gates: all PASS

### Status: ⬜ PENDING

---

## Phase 7: STRATEGY LAB ⭐ MANDATORY ⬜ PENDING

### ⚠️ WICHTIG
**Phase 7 ist MANDATORY vor jeder Live-Diskussion.**  
Keine Ausnahmen. Keine Abkürzungen.

### Ziele
- **KEINE** KI direkt über Orders entscheiden lassen
- KI nutzen für:
  1. Hypothesengenerierung
  2. Backtest-Automatisierung
  3. Marktregime-Klassifikation
  4. Anomalie-Erkennung
  5. Postmortem-Zusammenfassungen

### Deliverables

```
research/
├── backtest/
│   ├── backtest_engine.py
│   ├── parameter_sweep.py
│   └── walk_forward.py
├── strategy_lab/
│   ├── rsi_regime_filter.py
│   ├── volatility_filter.py
│   ├── multi_asset_selector.py
│   ├── mean_reversion_panic.py
│   └── trend_pullback.py
└── scorecards/
    ├── template.json
    └── btc_trend_001.json
```

### Strategy Scorecard (Template)

```json
{
  "strategy_id": "btc_trend_001",
  "name": "BTC Trend Pullback",
  "type": "trend_following",
  "hypothesis": "BTC trends tend to continue after shallow pullbacks",
  
  "assets": ["BTC-USD"],
  "timeframe": "1h",
  
  "indicators": {
    "primary": "EMA_20_50",
    "filter": "volatility_regime"
  },
  
  "entry": {
    "condition": "price < EMA20 && trend == UP",
    "max_positions": 1
  },
  
  "exit": {
    "stop_loss": "0.88%",
    "take_profit": "1.76%"
  },
  
  "walk_forward": {
    "train_period": "6M",
    "validation_period": "2M",
    "test_period": "2M"
  },
  
  "results": {
    "total_return": "+22.3%",
    "max_drawdown": "-8.1%",
    "sharpe": 1.85,
    "win_rate": "58%",
    "profit_factor": 2.1
  },
  
  "status": "validated",
  "live_ready": false
}
```

### Definition of Done
- [ ] Mindestens 3 Strategien mit Scorecards
- [ ] Jede Strategie: Walk-forward validated
- [ ] Multi-Asset-Selektor implementiert
- [ ] Regime-Filter getestet

### Status: ⬜ PENDING (BLOCKER für Live)

---

## Phase 8: Economics ⬜ PENDING

### Ziele
- Profitabilität prüfen
- Infrastructure costs
- Break-even analysis

### Deliverables

| Report | Inhalt |
|--------|--------|
| Monthly PnL Projection | Expected return |
| Infra Cost Estimate | Server, API, etc. |
| Break-even Gap | Trades/day needed |
| Risk-adjusted Returns | Sharpe, Sortino |

### Economic Warning

```
Wenn: projected_monthly_pnl < infra_cost
Dann: ECONOMIC_WARNING in Reports
Aber: KEIN Trading-Stop (nur Info)
```

### Definition of Done
- [ ] Alle Reports implementiert
- [ ] Break-even berechnet
- [ ] Warnings funktionieren

### Status: ⬜ PENDING

---

## Phase 9: Review & Gate ⬜ PENDING

### Ziele
- Final validation
- Manuelle Freigabe
- Go/No-Go Entscheidung

### Deliverables

```
docs/
├── phase_9_review_checklist.md
├── go_no_go_decision.md
└── sign_off_form.md
```

### Review Checklist

| # | Item | Owner | Status |
|---|------|-------|--------|
| 1 | All Phases 0-8 Complete | System | [ ] |
| 2 | All Tests Passing | QA | [ ] |
| 3 | Strategy Lab Complete | Research | [ ] |
| 4 | Economics Positive | Analyst | [ ] |
| 5 | Security Audit Passed | Security | [ ] |
| 6 | On-Call Schedule Ready | Ops | [ ] |
| 7 | Rollback Tested | Dev | [ ] |
| 8 | Manual Sign-off | User | [ ] |

### Go/No-Go Form

```
╔══════════════════════════════════════════════════════════════╗
║  LIVE TRADING GO/NO-GO DECISION                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                                ║
║  Date: _______________                                        ║
║                                                                ║
║  I confirm that:                                              ║
║  [ ] All Phases 0-9 are complete                              ║
║  [ ] All tests passing                                        ║
║  [ ] Strategy Lab validated                                   ║
║  [ ] Economics checked                                        ║
║  [ ] Security reviewed                                        ║
║                                                                ║
║  Decision:  [ ] GO    [ ] NO-GO                               ║
║                                                                ║
║  If GO, I enable:                                             ║
║  [ ] ENABLE_EXECUTION_LIVE=true                               ║
║  [ ] MAINNET_TRADING_ALLOWED=true                             ║
║                                                                ║
║  Signature: _________________                                   ║
║                                                                ║
╚══════════════════════════════════════════════════════════════╝
```

### Definition of Done
- [ ] Checklist complete
- [ ] Sign-off obtained
- [ ] Live mode enabled (manual only)

### Status: ⬜ PENDING

---

## Current Status Summary

| Phase | Status | Blocking? |
|-------|--------|-----------|
| 0 | ✅ Complete | No |
| 1 | 🔄 In Progress | No |
| 2 | ⬜ Pending | Yes |
| 3 | ⬜ Pending | Yes |
| 4 | ⬜ Pending | Yes |
| 5 | ⬜ Pending | Yes |
| 6 | ⬜ Pending | Yes |
| 7 | ⬜ Pending | **BLOCKS LIVE** |
| 8 | ⬜ Pending | Yes |
| 9 | ⬜ Pending | **BLOCKS LIVE** |

---

## Next Actions

1. **Phase 1**: Complete ADRs + Skeleton
2. **Phase 2**: Build Core Reliability
3. **Phase 3-6**: Observability, Boundaries, Operations, Tests
4. **Phase 7**: Strategy Lab (MANDATORY)
5. **Phase 8-9**: Economics + Gate

**→ ERST DANN**: Manuelle Live-Freigabe

---

**Document Version:** 1.0  
**Last Updated:** 2026-03-06  
**Status:** Phase 1 in Progress
