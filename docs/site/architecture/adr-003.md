# ADR-003: State Model

**Status:** Accepted  
**Date:** 2026-03-08  
**Deciders:** Assistant + User  

## Context

Das State Model definiert die Datenstrukturen, Events und Projektionsregeln für Forward V5. Alle State-Änderungen erfolgen ausschließlich über das Event Store – direktes Schreiben in State-Dateien ist verboten.

## Decision

### 1. Entities

#### 1.1 Run (Trading Session)
```typescript
interface Run {
  run_id: string;           // UUID, z.B. "FT_2026_03D_R5a"
  started_at: string;       // ISO 8601
  ended_at: string | null;  // null = aktiv
  symbol: string;           // z.B. "BTC-USD"
  timeframe: string;        // z.B. "1h"
  mode: "paper" | "mock" | "live";  // Live erst ab Phase 9
  config_version: string;   // Ref zur aktiven Config
}
```

#### 1.2 Position
```typescript
interface Position {
  position_id: string;      // UUID
  run_id: string;           // Referenz
  symbol: string;
  side: "long" | "short";
  entry_price: number;      // Durchschnitt bei Multiple Entries
  size: number;             // Anzahl Kontrakte
  realized_pnl: number;     // Bereits realisierter PnL
  unrealized_pnl: number;   // Aktueller unrealisierter PnL
  opened_at: string;
  closed_at: string | null;
  status: "open" | "closed" | "liquidated";
  orders: string[];         // Referenzen zu Order-IDs
}
```

#### 1.3 Order
```typescript
interface Order {
  order_id: string;         // Exchange-Order-ID oder UUID für Intents
  position_id: string;      // Referenz
  symbol: string;
  side: "buy" | "sell";
  type: "market" | "limit";
  size: number;
  price: number | null;     // null für Market Orders
  status: "created" | "sent" | "pending" | "filled" | "partial" | "canceled" | "rejected";
  filled_size: number;
  avg_fill_price: number | null;
  created_at: string;
  updated_at: string | null;
  exchange_response: object | null;  // Roher Exchange-Response
}
```

#### 1.4 Signal (Strategy-Output)
```typescript
interface Signal {
  signal_id: string;        // UUID
  run_id: string;
  timestamp: string;        // Wann Signal generiert
  tick_timestamp: string;   // Referenz zum auslösenden Tick
  symbol: string;
  action: "enter_long" | "enter_short" | "exit" | "none";
  confidence: number;       // 0.0 - 1.0
  metadata: object;         // Strategie-spezifische Daten
  strategy_id: string;      // z.B. "rsi_regime_filter_v1"
}
```

#### 1.5 Intent (Interner Order-Vorschlag)
```typescript
interface Intent {
  intent_id: string;        // UUID
  signal_id: string;        // Referenz
  run_id: string;
  timestamp: string;
  symbol: string;
  action: "open_long" | "open_short" | "close_position" | "adjust_size";
  target_size: number;     // Gewünschte Position-Size
  target_price: number | null;  // null = Market Order
  reason: string;          // Menschenlesbare Begründung
  risk_check_passed: boolean;   // Vorab-Check Ergebnis
}
```

#### 1.6 Event (Event Store Entry)
```typescript
interface Event {
  event_id: string;         // UUID (Lexikographisch sortierbar, z.B. ULID)
  event_type: EventType;    // Siehe unten
  occurred_at: string;      // ISO 8601
  entity_type: string;      // "run" | "position" | "order" | "signal" | "intent" | "health" | "config"
  entity_id: string;        // Referenz zur betroffenen Entity
  payload: object;          // Event-spezifische Daten
  correlation_id: string;   // Für Tracing (z.B. Signal → Intent → Order)
  causation_id: string | null;  // Vorheriges Event in Chain
}

type EventType =
  // Run Lifecycle
  | "RUN_STARTED" | "RUN_PAUSED" | "RUN_RESUMED" | "RUN_ENDED"
  // Signals
  | "SIGNAL_GENERATED" | "SIGNAL_REJECTED"
  // Intents
  | "INTENT_CREATED" | "INTENT_VALIDATED" | "INTENT_REJECTED"
  // Orders
  | "ORDER_CREATED" | "ORDER_SENT" | "ORDER_ACK" | "ORDER_FILLED" | "ORDER_PARTIAL_FILL"
  | "ORDER_CANCELED" | "ORDER_REJECTED" | "ORDER_ERROR"
  // Positions
  | "POSITION_OPENED" | "POSITION_SIZE_CHANGED" | "POSITION_CLOSED" | "POSITION_LIQUIDATED"
  // Health
  | "HEALTH_CHECK_PASSED" | "HEALTH_CHECK_FAILED"
  // Config
  | "CONFIG_LOADED" | "CONFIG_CHANGED"
  // Safety/Observability
  | "SAFETY_VIOLATED" | "SAFETY_RESOLVED"
  | "OBSERVABILITY_WARN" | "OBSERVABILITY_RESOLVED";
```

#### 1.7 Health (System-Health Snapshot)
```typescript
interface Health {
  health_id: string;        // UUID
  run_id: string;
  timestamp: string;
  safety_status: "healthy" | "degraded" | "critical";
  observability_status: "healthy" | "degraded" | "offline";
  checks: HealthCheck[];
  last_tick_at: string | null;     // Wann letzter Tick empfangen
  last_report_at: string | null;   // Wann letzter Report gesendet
}

interface HealthCheck {
  check_name: string;
  status: "pass" | "fail" | "warn";
  message: string | null;
  checked_at: string;
}
```

#### 1.8 Config (Laufzeit-Konfiguration)
```typescript
interface Config {
  config_id: string;      // UUID oder Versions-Tag
  loaded_at: string;
  active: boolean;          // Nur eine Config aktiv
  // Trading-Parameter
  symbol: string;
  timeframe: string;
  strategy_id: string;
  // Risk-Parameter
  max_position_size: number;
  max_leverage: number;
  risk_per_trade: number;   // % des Kapitals
  min_notional: number;     // HL: min $10
  max_notional: number;
  // Safety-Gates
  safety_gates: {
    sizing: boolean;
    reconcile: boolean;
    watchdog: boolean;
    market_data_freshness: boolean;
  };
  // Observability
  discord_webhook: string | null;
  report_interval_minutes: number;
}
```

---

### 2. Projection-Inhalt: "Aktueller State"

Die State-Projection ist das **materialisierte Ergebnis** aller Events. Sie ist **rekonstruierbar** und **keine** Quelle der Wahrheit.

#### 2.1 Garantierte Felder im State

```typescript
interface CurrentState {
  // Meta
  projection_version: string;   // ADR-Version
  projected_at: string;         // Timestamp der Projektion
  last_event_id: string;        // Bis zu diesem Event aktuell

  // Run
  current_run: Run | null;

  // Trading
  open_positions: Position[];
  pending_orders: Order[];
  recent_signals: Signal[];     // Letzte N Signale (z.B. 100)
  recent_intents: Intent[];     // Letzte N Intents

  // Health
  current_health: Health | null;

  // Config
  active_config: Config | null;

  // Aggregates
  stats: {
    total_trades_today: number;
    total_pnl_today: number;
    max_drawdown_today: number;
    uptime_seconds: number;
  };

  // Safety/Observability-Status
  safety: {
    overall_status: "healthy" | "degraded" | "critical";
    active_violations: string[];   // Liste der aktiven SAFETY_VIOLATED Events
    last_violation_at: string | null;
  };

  observability: {
    overall_status: "healthy" | "degraded" | "offline";
    active_warnings: string[];     // Liste aktiver OBSERVABILITY_WARN Events
    last_report_attempt_at: string | null;
    last_successful_report_at: string | null;
  };
}
```

#### 2.2 Nicht im State (keine Quelle der Wahrheit)

- Kein "next_trade_id" – wird aus Events berechnet
- Kein "balance" – wird bei Bedarf gefetcht
- Keine historischen Daten (nur via Event Store)

---

### 3. Quelle der Wahrheit

**EINZIGE Quelle der Wahrheit:** Das Event Store (SQLite/Append-only)

```
┌─────────────────────────────────────────────────────────────┐
│                     EVENT STORE                             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐       │
│  │  Event #1   │ → │  Event #2   │ → │  Event #3   │ → ... │
│  │  RUN_STARTED│   │SIGNAL_GEN   │   │INTENT_VALID │       │
│  └─────────────┘   └─────────────┘   └─────────────┘       │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Query / Replay
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  STATE PROJECTION                           │
│  (in-memory oder SQLite, rekonstruierbar jederzeit)         │
└─────────────────────────────────────────────────────────────┘
```

**Regeln:**
1. Nur `core_engine` schreibt Events
2. Alle anderen Komponenten lesen nur Projection
3. State-Dateien sind Cache, keine Quelle
4. Bei Unstimmigkeit: Event Store gewinnt

---

### 4. Rebuild-Regeln

#### 4.1 Deterministische Projektion

State = Fold(Events, InitialState, Reducer)

```javascript
// Pseudo-Code
function rebuildState(events) {
  let state = createInitialState();
  
  for (const event of events.sort(byOccurredAt)) {
    state = applyEvent(state, event);
    state.last_event_id = event.event_id;
  }
  
  return state;
}

function applyEvent(state, event) {
  switch (event.event_type) {
    case "POSITION_OPENED":
      state.open_positions.push(event.payload);
      break;
    case "ORDER_FILLED":
      updatePositionFromFill(state, event.payload);
      break;
    case "SAFETY_VIOLATED":
      state.safety.active_violations.push(event.payload.violation_type);
      state.safety.overall_status = "critical";
      break;
    case "SAFETY_RESOLVED":
      removeViolation(state.safety, event.payload.violation_type);
      break;
    // ... weitere Reducer
  }
  return state;
}
```

#### 4.2 Idempotenz

- Jedes Event hat UUID (`event_id`)
- Reducer prüft: `if (alreadyProcessed(event_id)) return state;`
- Duplikate werden ignoriert

#### 4.3 Ordering

- Events sind strikt nach `occurred_at` geordnet
- Bei gleichem Timestamp: `event_id` (ULID) als Tiebreaker
- Out-of-order Events werden in Queue bis Lücke geschlossen

#### 4.4 Partial Rebuild

```javascript
// Nicht alles von vorne notwendig
function incrementalRebuild(state, newEvents) {
  for (const event of newEvents) {
    if (event.event_id > state.last_event_id) {
      state = applyEvent(state, event);
    }
  }
  return state;
}
```

---

### 5. Safety vs Observability im State

#### 5.1 Safety-Fields

```typescript
interface SafetyState {
  overall_status: "healthy" | "degraded" | "critical";
  active_violations: {
    type: "sizing" | "reconcile" | "watchdog" | "market_data";
    detected_at: string;
    message: string;
    severity: "block" | "warn";  // block = trading stop
  }[];
  last_violation_at: string | null;
  block_trading: boolean;  // true wenn critical + severity=block
}
```

#### 5.2 Observability-Fields

```typescript
interface ObservabilityState {
  overall_status: "healthy" | "degraded" | "offline";
  active_warnings: {
    type: "discord_down" | "report_fail" | "log_fail";
    detected_at: string;
    message: string;
    severity: "warn" | "info";  // NIEMALS block
  }[];
  last_warning_at: string | null;
  metrics: {
    reports_attempted: number;
    reports_succeeded: number;
    reports_failed: number;
  };
}
```

#### 5.3 Entscheidungsmatrix

| Event | Feld | Effekt auf Trading |
|-------|------|-------------------|
| SAFETY_VIOLATED (severity=block) | safety.block_trading = true | **BLOCK** |
| SAFETY_VIOLATED (severity=warn) | safety.overall_status = degraded | **WARN** |
| SAFETY_RESOLVED | safety.block_trading = false | Resume möglich |
| OBSERVABILITY_WARN | observability.overall_status = degraded | **KEIN EFFEKT** |
| OBSERVABILITY_RESOLVED | observability.overall_status = healthy | - |

---

## Consequences

### Positive
- Klare Trennung von Events (truth) und State (projection)
- Deterministisches Debugging: State zu jedem Zeitpunkt reproduzierbar
- Safety-Observability-Trennung verhindert, dass Discord-Ausfälle das Trading blockieren

### Negative
- Event Store braucht Storage (kompensiert durch Rotation)
- Rebuild kann Zeit kosten (kompensiert durch Incremental)

---

## Related

- ADR-001: Target Architecture
- ADR-002: Hyperliquid Integration
- ADR-004: Risk Controls (Safety-Gates)
- MASTERPLAN_PHASES_1-9.md
