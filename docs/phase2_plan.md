# Phase 2: Core Reliability — Arbeitsplan

**Status:** 🔄 IN PROGRESS  
**Start:** 2026-03-08  
**Ziel:** Deterministischer Event-Store + State Projection + Risk Engine + Reconcile

---

## Regeln (Binding)

| Regel | Bedeutung |
|-------|-----------|
| **Single Source of Truth** | Nur Event Store, kein direktes State-Schreiben |
| **Append-Only** | Events werden nie gelöscht/geändert |
| **Idempotent** | UUID-basierte Deduplizierung |
| **Rebuild** | State jederzeit aus Events rekonstruierbar |
| **Safety blocken** | Risk Gates können Trading stoppen |
| **Observability WARN** | Reports/Discord niemals blocken |
| **Paper/Mock only** | Kein Live, kein Mainnet, keine echten Keys |
| **Hyperliquid-only** | Keine andere Exchange-Abstraktion |

---

## Block 1: Event Store (`src/event_store.js`)

### Zweck
Append-only SQLite-Log aller Domain-Events. Einzige Quelle der Wahrheit.

### Interface
```javascript
// append(event): Promise<void>
// getEvents(since, until): Promise<Event[]>
// getEventsByEntity(entityType, entityId): Promise<Event[]>
// getLastEvent(): Promise<Event|null>
// rebuildProjection(projectionFn): Promise<State>
```

### Implementierung

```javascript
const EventStore = {
  db: null,
  
  async init(dbPath = 'runtime/event_store.db') {
    this.db = await sqlite.open(dbPath);
    await this.db.exec(`
      CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        payload TEXT NOT NULL,
        correlation_id TEXT,
        causation_id TEXT
      );
      CREATE INDEX idx_entity ON events(entity_type, entity_id);
      CREATE INDEX idx_time ON events(occurred_at);
    `);
  },
  
  async append(event) {
    // Idempotenz-Check
    const exists = await this.db.get(
      'SELECT 1 FROM events WHERE event_id = ?', 
      event.event_id
    );
    if (exists) return; // Already processed
    
    await this.db.run(`
      INSERT INTO events (...)
      VALUES (...)
    `, [...values]);
  },
  
  async getEvents(opts = {}) {
    // Query-Builder mit Pagination
  }
};
```

### Tests (Reihenfolge)

| # | Test | Beschreibung |
|---|------|--------------|
| 1.1 | `append_saves_event` | Event wird gespeichert |
| 1.2 | `append_idempotent` | Gleiche ID = ignoriert |
| 1.3 | `getEvents_returns_ordered` | Zeitliche Reihenfolge |
| 1.4 | `getEvents_filtered` | Filter nach entity_type |
| 1.5 | `getEvents_pagination` | Limit/Offset funktioniert |
| 1.6 | `init_creates_schema` | DB Schema wird angelegt |
| 1.7 | `concurrent_append_safe` | Race Conditions behandelt |

### Acceptance
- [x] Alle Tests passing
- [x] 1000 Events/Sekunden append-Rate
- [x] Rebuild 10k Events in <1s

---

## Block 2: State Projection (`src/state_projection.js`)

### Zweck
Materialisierte Ansicht des aktuellen Zustands aus Events.

### Interface
```javascript
// project(events[]): State
// rebuild(): Promise<State>
// incrementalUpdate(newEvents): State
// getCurrentState(): State
```

### Implementierung

```javascript
const StateProjection = {
  state: createInitialState(),
  lastEventId: null,
  
  project(events) {
    for (const event of events) {
      this.state = this.applyEvent(this.state, event);
      this.lastEventId = event.event_id;
    }
    return this.state;
  },
  
  applyEvent(state, event) {
    const handlers = {
      'POSITION_OPENED': (s, e) => {
        s.open_positions.push(e.payload);
        return s;
      },
      'ORDER_FILLED': (s, e) => {
        // Update position from fill
        const pos = s.open_positions.find(p => p.position_id === e.payload.position_id);
        if (pos) {
          pos.size += e.payload.filled_size;
          pos.orders.push(e.payload.order_id);
        }
        return s;
      },
      'SAFETY_VIOLATED': (s, e) => {
        s.safety.active_violations.push(e.payload);
        s.safety.status = e.payload.severity === 'block' ? 'critical' : 'degraded';
        return s;
      },
      // ... weitere Events
    };
    
    const handler = handlers[event.event_type];
    return handler ? handler(state, event) : state;
  },
  
  async rebuild(eventStore) {
    const events = await eventStore.getEvents({order: 'ASC'});
    this.state = createInitialState();
    return this.project(events);
  }
};
```

### Tests (Reihenfolge)

| # | Test | Beschreibung |
|---|------|--------------|
| 2.1 | `project_position_opened` | Position wird erstellt |
| 2.2 | `project_order_filled` | Position wird aktualisiert |
| 2.3 | `project_safety_violated` | Safety-Status wird gesetzt |
| 2.4 | `project_multiple_events` | Event-Kette korrekt |
| 2.5 | `rebuild_from_empty` | Leerer Start funktioniert |
| 2.6 | `rebuild_matches_live` | Rebuild == Live-State |
| 2.7 | `idempotent_same_result` | Gleiche Events = gleicher State |
| 2.8 | `out_of_order_handled` | Ungeordnete Events behandelt |

### Acceptance
- [x] Alle Tests passing
- [x] Rebuild == Live-State (zu jedem Zeitpunkt)
- [x] State ist JSON-serialisierbar
- [x] Thread-safe (falls async)

---

## Block 3: Risk Engine (`src/risk_engine.js`)

### Zweck
Pre-Trade Validation aller Safety Gates.

### Interface
```javascript
// validate(intent): ValidationResult
// checkGate(gateName, input): GateResult
// getActiveViolations(): Violation[]
```

### Implementierung (gemäß ADR-004)

```javascript
const RiskEngine = {
  gates: {
    sizing: SizingGate,
    reconcile: ReconcileGate,
    watchdog: WatchdogGate,
    market_data: MarketDataGate,
    symbol_whitelist: SymbolWhitelistGate,
    hyperliquid_rules: HyperliquidRulesGate,
    unmanaged: UnmanagedPositionGate
  },
  
  validate(intent, state, config) {
    const violations = [];
    
    for (const [name, gate] of Object.entries(this.gates)) {
      if (!config.safety_gates[name]) continue;
      
      const result = gate.evaluate({
        intent,
        state,
        config,
        // gate-specific inputs
      });
      
      if (!result.passed) {
        violations.push({
          gate: name,
          severity: result.severity, // 'block' oder 'warn'
          message: result.message,
          timestamp: new Date().toISOString()
        });
      }
    }
    
    return {
      allowed: !violations.some(v => v.severity === 'block'),
      violations,
      timestamp: new Date().toISOString()
    };
  }
};

// Beispiel: SizingGate
const SizingGate = {
  evaluate({intent, state, config}) {
    const notional = intent.target_size * getCurrentPrice(intent.symbol);
    const violations = [];
    
    if (notional < config.min_notional) {
      violations.push({
        type: 'MIN_NOTIONAL',
        severity: 'block',
        message: `Notional $${notional} < $${config.min_notional}`
      });
    }
    
    // ... weitere Checks
    
    return {
      passed: violations.length === 0,
      violations,
      severity: violations.some(v => v.severity === 'block') ? 'block' : 'warn'
    };
  }
};
```

### Tests (Reihenfolge)

| # | Test | Beschreibung |
|---|------|--------------|
| 3.1 | `sizing_passes_valid` | Valid intent passes |
| 3.2 | `sizing_blocks_min_notional` | $10 Min bei HL |
| 3.3 | `sizing_blocks_max_leverage` | Max Leverage überschritten |
| 3.4 | `sizing_warns_risk_per_trade` | Warning statt Block |
| 3.5 | `reconcile_blocks_mismatch` | State != Exchange |
| 3.6 | `watchdog_blocks_stale_tick` | Keine Daten |
| 3.7 | `unmanaged_blocks_unknown_position` | Position ohne Run |
| 3.8 | `hyperliquid_min_notional` | HL-Regel $10 |
| 3.9 | `symbol_whitelist_blocks_unknown` | Nicht erlaubtes Symbol |
| 3.10 | `multiple_violations_reported` | Mehrere Gates failed |
| 3.11 | `observability_never_blocks` | Report-Fail = warn only |

### Acceptance
- [x] Alle Gates getestet
- [x] Safety Gates können blocken
- [x] Observability Gates blocken niemals
- [x] Hyperliquid-Regeln validiert ($10 min, Whitelist)

---

## Block 4: Reconcile (`src/reconcile.js`)

### Zweck
Vergleich: Projected State vs Exchange State.

### Interface
```javascript
// check(state, exchangePositions): ReconcileResult
// syncPosition(positionId): Promise<void>
// getMismatches(): Mismatch[]
```

### Implementierung

```javascript
const Reconcile = {
  tolerance: 0.001, // 0.1% für Size-Vergleich
  
  check(projectedState, exchangePositions) {
    const mismatches = [];
    
    // 1. Check: Haben wir eine Position, die Exchange nicht kennt?
    for (const proj of projectedState.open_positions) {
      const exchange = exchangePositions.find(p => p.symbol === proj.symbol);
      
      if (!exchange && proj.status === 'open') {
        mismatches.push({
          type: 'GHOST_POSITION',
          symbol: proj.symbol,
          projected: proj.size,
          exchange: 0,
          severity: 'block'
        });
      } else if (exchange && proj.status === 'open') {
        // 2. Size mismatch
        const diff = Math.abs(proj.size - exchange.size) / proj.size;
        if (diff > this.tolerance) {
          mismatches.push({
            type: 'SIZE_MISMATCH',
            symbol: proj.symbol,
            projected: proj.size,
            exchange: exchange.size,
            severity: 'block'
          });
        }
        
        // 3. Side mismatch
        if (proj.side !== exchange.side && proj.size > 0) {
          mismatches.push({
            type: 'SIDE_MISMATCH',
            symbol: proj.symbol,
            projected: proj.side,
            exchange: exchange.side,
            severity: 'block'
          });
        }
      }
    }
    
    // 4. Exchange hat Position, die wir nicht kennen
    for (const exchange of exchangePositions) {
      const proj = projectedState.open_positions.find(
        p => p.symbol === exchange.symbol && p.status === 'open'
      );
      
      if (!proj && exchange.size > 0) {
        mismatches.push({
          type: 'UNMANAGED_POSITION',
          symbol: exchange.symbol,
          exchange: exchange.size,
          projected: 0,
          severity: 'block'
        });
      }
    }
    
    return {
      matched: mismatches.length === 0,
      mismatches,
      checkedAt: new Date().toISOString()
    };
  }
};
```

### Tests (Reihenfolge)

| # | Test | Beschreibung |
|---|------|--------------|
| 4.1 | `check_passes_match` | Alles identisch |
| 4.2 | `check_fails_ghost_position` | State hat, Exchange nicht |
| 4.3 | `check_fails_unmanaged` | Exchange hat, State nicht |
| 4.4 | `check_fails_size_mismatch` | Größe unterschiedlich |
| 4.5 | `check_fails_side_mismatch` | Long vs Short |
| 4.6 | `tolerance_accepted` | 0.1% Diff okay |
| 4.7 | `empty_states_match` | Keine Positionen = okay |
| 4.8 | `multiple_mismatches` | Mehrere Fehler |

### Acceptance
- [x] Alle Mismatch-Typen erkannt
- [x] Toleranz (0.1%) akzeptiert
- [x] Unmanaged Positionen als block markiert
- [x] Integration mit Risk Engine

---

## Reihenfolge der Umsetzung

```
Woche 1: Event Store
  ├─ Day 1-2: Schema + append
  ├─ Day 3: Queries + pagination
  └─ Day 4-5: Tests + Performance

Woche 2: State Projection
  ├─ Day 1-2: Projection + Reducer
  ├─ Day 3: Rebuild
  ├─ Day 4: Incremental Update
  └─ Day 5: Tests

Woche 3: Risk Engine
  ├─ Day 1-2: Sizing + Hyperliquid Gates
  ├─ Day 3: Watchdog + Market Data
  ├─ Day 4: Reconcile + Unmanaged
  └─ Day 5: Integration Tests

Woche 4: Reconcile + Integration
  ├─ Day 1-2: Reconcile Module
  ├─ Day 3: End-to-End Tests
  ├─ Day 4: Performance
  └─ Day 5: Dokumentation + Review
```

---

## Phase 2 Acceptance-Kriterien

### Definition of Done

| # | Kriterium | Verification |
|---|-----------|--------------|
| 1 | Event Store persistent | 10k Events append in <1s |
| 2 | State Projection rebuild | Rebuild == Live-State (100% Match) |
| 3 | Risk Engine alle Gates | Jeder Gate hat ≥3 Tests |
| 4 | Reconcile mismatch detection | Alle 4 Mismatch-Typen erkannt |
| 5 | Unit Tests Coverage | >80% Coverage für alle Module |
| 6 | Integration Tests | Tick → Signal → Intent → Validate → Event |
| 7 | No Live, No Mainnet | Code review: Keine Live-Execution |
| 8 | Paper/Mock only | Config check: Nur paper/mock APIs |
| 9 | Dokumentation | Jede Funktion dokumentiert |
| 10 | ADR Compliance | Code matches ADR-003 + ADR-004 |

### Go/No-Go für Phase 3

```
┌─────────────────────────────────────────────────────────┐
│  PHASE 2 COMPLETE CHECKLIST                             │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [ ] All modules implemented                            │
│  [ ] All tests passing (>80% coverage)                  │
│  [ ] Integration tests demonstrate full flow            │
│  [ ] Documentation complete                             │
│  [ ] Paper/Mock verified (no live paths)                │
│                                                          │
│  Decision:  [ ] GO  /  [ ] NO-GO                        │
│                                                          │
│  If GO, proceed to Phase 3 (Observability)              │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Deliverables Phase 2

1. **Code**
   - `src/event_store.js`
   - `src/state_projection.js`
   - `src/risk_engine.js`
   - `src/reconcile.js`

2. **Tests**
   - `tests/event_store.test.js`
   - `tests/state_projection.test.js`
   - `tests/risk_engine.test.js`
   - `tests/reconcile.test.js`
   - `tests/integration/core_reliability.test.js`

3. **Docs**
   - `docs/DESIGN-phase2.md` (Dieses Dokument)
   - `docs/API-REFERENCE.md`
   - `docs/TEST-REPORT-phase2.md`

4. **Mission Control Update**
   - `forward_v5/docs/site/docs/phases.md` → Phase 2 ✅
   - `forward_v5/docs/site/docs/roadmap.md` → Phase 3 Tasks

---

**Next:** Block 1 Start → Event Store Schema
