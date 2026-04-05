# ADR-004: Risk Controls

**Status:** Accepted  
**Date:** 2026-03-08  
**Deciders:** Assistant + User  

## Context

Alle Risk Gates müssen explizit definiert sein: Input, Entscheidungslogik, Output-Event, und Effekt (BLOCK vs WARN). Dieses ADR ist verbindlich für Implementierung und Incident Response.

## Decision

### 1. Risk Gates Übersicht

| # | Gate | Domain | Effekt | Beschreibung |
|---|------|--------|--------|--------------|
| R1 | Sizing | Safety | BLOCK | Positionsgrößen-Limits |
| R2 | Reconcile | Safety | BLOCK | State vs Exchange/Paper Abgleich |
| R3 | Watchdog | Safety | BLOCK | Stale State / Timeouts |
| R4 | Market Data Freshness | Safety | BLOCK | Tick-Daten nicht aktuell |
| R5 | Symbol Whitelist | Safety | BLOCK | Nur erlaubte Symbole |
| R6 | Min/Max Notional | Safety | BLOCK | HL-Regeln ($10 min) |
| R7 | Leverage | Safety | BLOCK | Max Leverage überschritten |
| R8 | Unmanaged Position | Safety | BLOCK | Position ohne zugehörigen Run |
| R9 | Report Failure | Observability | WARN | Discord/Report nicht gesendet |
| R10 | Log Failure | Observability | WARN | Logging-System fehlerhaft |
| R11 | Config Warning | Observability | WARN | Ungewöhnliche Config-Werte |

**Kardinalregel:** Observability-Fehler blockieren niemals das Trading.

---

### 2. Detaillierte Gate-Spezifikationen

#### R1: Sizing

```typescript
interface SizingGate {
  name: "sizing";
  domain: "safety";
  default_effect: "block";
}

// Input
interface SizingInput {
  intent: Intent;
  current_position: Position | null;
  account_balance: number;
  active_config: Config;
}

// Entscheidung
function evaluateSizing(input: SizingInput): SizingDecision {
  const { intent, current_position, account_balance, active_config } = input;
  
  // Checks
  const notional = intent.target_size * getCurrentPrice(intent.symbol);
  const exposure = calculateTotalExposure(current_position, intent);
  
  const violations = [];
  
  if (notional < active_config.min_notional) {
    violations.push({
      type: "MIN_NOTIONAL",
      value: notional,
      limit: active_config.min_notional,
      message: `Order notional $${notional.toFixed(2)} < min $${active_config.min_notional}`
    });
  }
  
  if (notional > active_config.max_notional) {
    violations.push({
      type: "MAX_NOTIONAL",
      value: notional,
      limit: active_config.max_notional,
      message: `Order notional $${notional.toFixed(2)} > max $${active_config.max_notional}`
    });
  }
  
  if (exposure.risk_amount > account_balance * active_config.risk_per_trade) {
    violations.push({
      type: "RISK_PER_TRADE",
      value: exposure.risk_amount,
      limit: account_balance * active_config.risk_per_trade,
      message: `Risk $${exposure.risk_amount.toFixed(2)} exceeds ${(active_config.risk_per_trade * 100).toFixed(1)}% of balance`
    });
  }
  
  if (exposure.leverage > active_config.max_leverage) {
    violations.push({
      type: "MAX_LEVERAGE",
      value: exposure.leverage,
      limit: active_config.max_leverage,
      message: `Leverage ${exposure.leverage.toFixed(1)}x > max ${active_config.max_leverage}x`
    });
  }
  
  return {
    passed: violations.length === 0,
    violations,
    decision_at: new Date().toISOString()
  };
}

// Output Events
interface SizingDecision {
  passed: boolean;
  violations: SizingViolation[];
  decision_at: string;
}

// Bei passed === false:
event = {
  event_type: "SAFETY_VIOLATED",
  payload: {
    gate: "sizing",
    severity: "block",  // Sizing ist immer block
    violations: decision.violations,
    intent_id: input.intent.intent_id,
    blocked_action: input.intent.action
  }
};

// Bei passed === true:
event = {
  event_type: "INTENT_VALIDATED",
  payload: {
    intent_id: input.intent.intent_id,
    gates_passed: ["sizing"],
    validated_at: new Date().toISOString()
  }
};
```

---

#### R2: Reconcile

```typescript
interface ReconcileGate {
  name: "reconcile";
  domain: "safety";
  default_effect: "block";
}

// Input
interface ReconcileInput {
  projected_positions: Position[];
  exchange_positions: ExchangePosition[];  // von Hyperliquid API
}

interface ExchangePosition {
  symbol: string;
  side: "long" | "short";
  size: number;
  entry_price: number;
  unrealized_pnl: number;
}

// Entscheidung
function evaluateReconcile(input: ReconcileInput): ReconcileDecision {
  const mismatches = [];
  
  // 1. Check: Haben wir eine Position, die Exchange nicht kennt?
  for (const proj of input.projected_positions) {
    const exchange = input.exchange_positions.find(p => p.symbol === proj.symbol);
    
    if (!exchange && proj.status === "open") {
      mismatches.push({
        type: "GHOST_POSITION",
        symbol: proj.symbol,
        projected_size: proj.size,
        exchange_size: 0,
        message: `Projected position ${proj.symbol} size ${proj.size} not found on exchange`
      });
    } else if (exchange && proj.status === "open") {
      // 2. Check: Größen-Mismatch?
      const size_diff = Math.abs(proj.size - exchange.size);
      const tolerance = 0.001; // 0.1% Toleranz
      
      if (size_diff / proj.size > tolerance) {
        mismatches.push({
          type: "SIZE_MISMATCH",
          symbol: proj.symbol,
          projected_size: proj.size,
          exchange_size: exchange.size,
          message: `${proj.symbol}: projected ${proj.size} ≠ exchange ${exchange.size} (diff: ${size_diff})`
        });
      }
      
      // 3. Check: Seiten-Mismatch?
      if (proj.side !== exchange.side && proj.size > 0 && exchange.size > 0) {
        mismatches.push({
          type: "SIDE_MISMATCH",
          symbol: proj.symbol,
          projected_side: proj.side,
          exchange_side: exchange.side,
          message: `${proj.symbol}: projected ${proj.side} ≠ exchange ${exchange.side}`
        });
      }
    }
  }
  
  // 4. Check: Exchange hat Position, die wir nicht kennen?
  for (const exchange of input.exchange_positions) {
    const proj = input.projected_positions.find(p => p.symbol === exchange.symbol && p.status === "open");
    
    if (!proj) {
      mismatches.push({
        type: "UNMANAGED_POSITION",
        symbol: exchange.symbol,
        exchange_size: exchange.size,
        projected_size: 0,
        message: `Exchange has ${exchange.side} ${exchange.size} ${exchange.symbol} not tracked in state`
      });
    }
  }
  
  return {
    passed: mismatches.length === 0,
    mismatches,
    checked_at: new Date().toISOString()
  };
}

// Output Events
// Bei mismatches.length > 0:
event = {
  event_type: "SAFETY_VIOLATED",
  payload: {
    gate: "reconcile",
    severity: "block",
    mismatches: decision.mismatches,
    auto_pause: true  // Sofortiger Pause-Befehl
  }
};

// Bei passed:
event = {
  event_type: "RECONCILE_PASSED",
  payload: {
    checked_at: decision.checked_at,
    positions_matched: input.projected_positions.length
  }
};
```

---

#### R3: Watchdog

```typescript
interface WatchdogGate {
  name: "watchdog";
  domain: "safety";
  default_effect: "block";
}

// Input
interface WatchdogInput {
  last_tick_at: string | null;
  last_order_sent_at: string | null;
  last_health_check_at: string | null;
  max_tick_staleness_ms: number;   // z.B. 60000 (1 Min)
  max_order_timeout_ms: number;    // z.B. 30000 (30 Sek)
}

// Entscheidung
function evaluateWatchdog(input: WatchdogInput): WatchdogDecision {
  const now = Date.now();
  const violations = [];
  
  // 1. Stale Tick
  if (input.last_tick_at) {
    const tick_age = now - new Date(input.last_tick_at).getTime();
    if (tick_age > input.max_tick_staleness_ms) {
      violations.push({
        type: "STALE_TICK",
        type_label: "Tick-Daten nicht aktuell",
        last_tick_at: input.last_tick_at,
        age_ms: tick_age,
        max_ms: input.max_tick_staleness_ms,
        message: `Last tick ${(tick_age / 1000).toFixed(1)}s ago, max ${(input.max_tick_staleness_ms / 1000).toFixed(0)}s`
      });
    }
  } else {
    violations.push({
      type: "NO_TICK_DATA",
      type_label: "Keine Tick-Daten empfangen",
      message: "No tick data received since start"
    });
  }
  
  // 2. Pending Order Timeout
  if (input.last_order_sent_at) {
    const order_age = now - new Date(input.last_order_sent_at).getTime();
    // Nur warn, wenn Order noch pending (nicht blocken)
    if (order_age > input.max_order_timeout_ms) {
      violations.push({
        type: "ORDER_TIMEOUT",
        type_label: "Order-Antwort ausstehend",
        last_order_at: input.last_order_sent_at,
        age_ms: order_age,
        max_ms: input.max_order_timeout_ms,
        message: `Order pending for ${(order_age / 1000).toFixed(1)}s`,
        severity: "warn"  // Nicht blocken, nur warn
      });
    }
  }
  
  // 3. Health Check Timeout
  if (input.last_health_check_at) {
    const health_age = now - new Date(input.last_health_check_at).getTime();
    if (health_age > input.max_tick_staleness_ms * 2) {
      violations.push({
        type: "HEALTH_TIMEOUT",
        type_label: "Health-Checks laufen nicht",
        last_check_at: input.last_health_check_at,
        age_ms: health_age,
        message: `Health check stale for ${(health_age / 1000).toFixed(1)}s`
      });
    }
  }
  
  // Severity bestimmen
  const has_block = violations.some(v => v.severity !== "warn");
  
  return {
    passed: violations.length === 0,
    violations,
    severity: has_block ? "block" : "warn",
    checked_at: new Date().toISOString()
  };
}

// Output Events
// Bei violations:
event = {
  event_type: "SAFETY_VIOLATED",
  payload: {
    gate: "watchdog",
    severity: decision.severity,  // "block" oder "warn"
    violations: decision.violations
  }
};
```

---

#### R4: Market Data Freshness

```typescript
interface MarketDataGate {
  name: "market_data_freshness";
  domain: "safety";
  default_effect: "block";
}

// Input
interface MarketDataInput {
  tick_timestamp: string;      // Wann Tick vom Exchange generiert
  received_at: string;           // Wann bei uns angekommen
  max_delay_ms: number;        // z.B. 5000 (5 Sek)
}

// Entscheidung
function evaluateMarketData(input: MarketDataInput): MarketDataDecision {
  const delay = new Date(input.received_at).getTime() - new Date(input.tick_timestamp).getTime();
  
  if (delay > input.max_delay_ms) {
    return {
      passed: false,
      delay_ms: delay,
      max_ms: input.max_delay_ms,
      severity: "block",
      message: `Tick delay ${(delay / 1000).toFixed(1)}s exceeds max ${(input.max_delay_ms / 1000).toFixed(0)}s`
    };
  }
  
  return {
    passed: true,
    delay_ms: delay,
    checked_at: new Date().toISOString()
  };
}

// Output
// Bei passed === false:
event = {
  event_type: "SAFETY_VIOLATED",
  payload: {
    gate: "market_data_freshness",
    severity: "block",
    tick_timestamp: input.tick_timestamp,
    received_at: input.received_at,
    delay_ms: decision.delay_ms,
    message: decision.message
  }
};
```

---

#### R5: Symbol Whitelist

```typescript
interface SymbolWhitelistGate {
  name: "symbol_whitelist";
  domain: "safety";
  default_effect: "block";
}

// Input
interface SymbolWhitelistInput {
  symbol: string;
  allowed_symbols: string[];  // z.B. ["BTC-USD", "ETH-USD"]
}

// Entscheidung
function evaluateSymbolWhitelist(input: SymbolWhitelistInput): SymbolWhitelistDecision {
  const normalized = normalizeSymbol(input.symbol);
  const allowed = input.allowed_symbols.map(normalizeSymbol);
  
  if (!allowed.includes(normalized)) {
    return {
      passed: false,
      symbol: input.symbol,
      allowed_symbols: input.allowed_symbols,
      message: `Symbol ${input.symbol} not in whitelist: ${input.allowed_symbols.join(", ")}`
    };
  }
  
  return { passed: true };
}

// Output
// Bei passed === false:
event = {
  event_type: "SAFETY_VIOLATED",
  payload: {
    gate: "symbol_whitelist",
    severity: "block",
    symbol: input.symbol,
    allowed: input.allowed_symbols,
    message: decision.message
  }
};
```

---

#### R6: Hyperliquid-spezifische Regeln

```typescript
interface HyperliquidRulesGate {
  name: "hyperliquid_rules";
  domain: "safety";
  default_effect: "block";
}

// Konfiguration
const HL_RULES = {
  MIN_NOTIONAL_USD: 10.0,
  MAX_LEVERAGE_BTC: 50,
  MAX_LEVERAGE_ETH: 50,
  SUPPORTED_SYMBOLS: ["BTC-USD", "ETH-USD"],
  TICK_SIZE: {
    "BTC-USD": 0.1,
    "ETH-USD": 0.01
  }
};

// Input
interface HLRulesInput {
  symbol: string;
  notional_usd: number;
  leverage: number;
  price: number;
}

// Entscheidung
function evaluateHLRules(input: HLRulesInput): HLRulesDecision {
  const violations = [];
  
  // 1. Min $10 notional
  if (input.notional_usd < HL_RULES.MIN_NOTIONAL_USD) {
    violations.push({
      type: "HL_MIN_NOTIONAL",
      message: `HL requires min $${HL_RULES.MIN_NOTIONAL_USD} notional, got $${input.notional_usd.toFixed(2)}`
    });
  }
  
  // 2. Max Leverage per Symbol
  const max_lev = input.symbol === "BTC-USD" 
    ? HL_RULES.MAX_LEVERAGE_BTC 
    : HL_RULES.MAX_LEVERAGE_ETH;
    
  if (input.leverage > max_lev) {
    violations.push({
      type: "HL_MAX_LEVERAGE",
      message: `${input.symbol} max leverage ${max_lev}x, requested ${input.leverage.toFixed(1)}x`
    });
  }
  
  // 3. Supported Symbols
  if (!HL_RULES.SUPPORTED_SYMBOLS.includes(input.symbol)) {
    violations.push({
      type: "HL_SYMBOL_NOT_SUPPORTED",
      message: `${input.symbol} not supported on Hyperliquid`
    });
  }
  
  return {
    passed: violations.length === 0,
    violations,
    checked_at: new Date().toISOString()
  };
}

// Output
// Bei violations:
event = {
  event_type: "SAFETY_VIOLATED",
  payload: {
    gate: "hyperliquid_rules",
    severity: "block",
    violations: decision.violations
  }
};
```

---

#### R7: Leverage Gate (separat von Sizing)

```typescript
interface LeverageGate {
  name: "leverage";
  domain: "safety";
  default_effect: "block";
}

// Dies ist ein Wrapper für HL-Rules + generische Leverage-Checks
// Siehe R6 für Implementation
// Separat dokumentiert für Klarheit
```

---

#### R8: Unmanaged Position

```typescript
interface UnmanagedPositionGate {
  name: "unmanaged_position";
  domain: "safety";
  default_effect: "block";
}

// Input
interface UnmanagedInput {
  exchange_positions: ExchangePosition[];
  projected_positions: Position[];
  active_runs: Run[];
}

// Entscheidung
function evaluateUnmanaged(input: UnmanagedInput): UnmanagedDecision {
  const unmanaged = [];
  
  for (const exchange of input.exchange_positions) {
    // Check: Haben wir einen Run für dieses Symbol?
    const active_run = input.active_runs.find(r => r.symbol === exchange.symbol && !r.ended_at);
    
    // Check: Haben wir eine Position?
    const projected = input.projected_positions.find(p => p.symbol === exchange.symbol && p.status === "open");
    
    if (exchange.size > 0 && (!active_run || !projected)) {
      unmanaged.push({
        symbol: exchange.symbol,
        size: exchange.size,
        side: exchange.side,
        has_run: !!active_run,
        has_projected: !!projected,
        message: `Unmanaged ${exchange.side} ${exchange.size} ${exchange.symbol} on exchange`
      });
    }
  }
  
  return {
    passed: unmanaged.length === 0,
    unmanaged,
    checked_at: new Date().toISOString()
  };
}

// Output
// Bei unmanaged.length > 0:
event = {
  event_type: "SAFETY_VIOLATED",
  payload: {
    gate: "unmanaged_position",
    severity: "block",
    unmanaged: decision.unmanaged,
    message: `${decision.unmanaged.length} unmanaged position(s) detected - PAUSING NOW`
  }
};
```

---

### 3. Observability Gates (NIEMALS block)

#### R9: Report Failure

```typescript
interface ReportGate {
  name: "report_failure";
  domain: "observability";
  default_effect: "warn";  // NIEMALS block
}

// Input
interface ReportInput {
  last_report_attempt_at: string | null;
  last_successful_report_at: string | null;
  consecutive_failures: number;
}

// Entscheidung
function evaluateReport(input: ReportInput): ReportDecision {
  if (input.consecutive_failures >= 3) {
    return {
      passed: false,
      severity: "warn",  // EXPLIZIT warn, niemals block
      consecutive_failures: input.consecutive_failures,
      message: `Report failed ${input.consecutive_failures} times consecutively`
    };
  }
  
  return { passed: true };
}

// Output
// Bei passed === false:
event = {
  event_type: "OBSERVABILITY_WARN",
  payload: {
    gate: "report",
    severity: "warn",  // NICHT "block"
    consecutive_failures: decision.consecutive_failures,
    message: decision.message,
    note: "This is an OBSERVABILITY warning - trading continues"
  }
};
```

#### R10: Log Failure

```typescript
interface LogGate {
  name: "log_failure";
  domain: "observability";
  default_effect: "warn";
}

// Output
// Bei Log-Fehler:
event = {
  event_type: "OBSERVABILITY_WARN",
  payload: {
    gate: "log",
    severity: "warn",
    message: "Logging system degraded",
    note: "Trading continues - logs may be incomplete"
  }
};
```

#### R11: Config Warning

```typescript
interface ConfigWarningGate {
  name: "config_warning";
  domain: "observability";
  default_effect: "warn";
}

// Beispiel: Ungewöhnlich hohe Leverage
// Output:
event = {
  event_type: "OBSERVABILITY_WARN",
  payload: {
    gate: "config",
    severity: "warn",
    warning_type: "HIGH_LEVERAGE",
    configured_value: 25,
    recommended_max: 10,
    message: "Leverage 25x exceeds recommended 10x - will be allowed but logged"
  }
};
```

---

### 4. Effekt-Matrix

#### 4.1 Safety-Events → Effekte

| Event | Feld | Wert | Effekt |
|-------|------|------|--------|
| `SAFETY_VIOLATED` | `severity` | `"block"` | Trading pause, Alert, Manual review required |
| `SAFETY_VIOLATED` | `severity` | `"warn"` | Log entry, Discord warn, Trading continues |
| `SAFETY_RESOLVED` | `gate` | `<gate_name>` | Resume möglich (nach manual check) |

#### 4.2 Observability-Events → Effekte

| Event | Feld | Wert | Effekt |
|-------|------|------|--------|
| `OBSERVABILITY_WARN` | `severity` | `"warn"` | Log entry, Discord warn, **Trading continues** |
| `OBSERVABILITY_WARN` | `severity` | `"info"` | Log entry only |
| `OBSERVABILITY_RESOLVED` | `gate` | `<gate_name>` | Status zurücksetzen |

**WICHTIG:** Observability-Events haben keinen `severity: "block"`. Falls ein Code-Pfad das versucht, wird es zur Laufzeit in `"warn"` konvertiert.

---

### 5. Dokumentation der Trennung

```
┌─────────────────────────────────────────────────────────────────┐
│                        SAFETY DOMAIN                            │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ SIZING  │ │ RECONCILE│ │ WATCHDOG │ │  SYMBOL  │           │
│  │         │ │          │ │          │ │ WHITELIST│           │
│  └────┬────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│       │           │            │            │                    │
│       └───────────┴────────────┴────────────┘                    │
│                   │                                              │
│                   ▼                                              │
│            ┌──────────────┐                                     │
│            │ SAFETY_CHECK │                                     │
│            └──────┬───────┘                                     │
│                   │                                              │
│         ┌─────────┴─────────┐                                  │
│         ▼                   ▼                                  │
│   ┌────────────┐      ┌────────────┐                           │
│   │   BLOCK    │      │    WARN    │                           │
│   │  (pause)   │      │ (continue) │                           │
│   └────────────┘      └────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ NIEMALS block
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     OBSERVABILITY DOMAIN                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│  │ DISCORD  │ │  REPORT  │ │   LOG    │                        │
│  │   DOWN   │ │  FAIL    │ │  FAIL    │                        │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘                        │
│       │            │            │                              │
│       └────────────┴────────────┘                              │
│                    │                                            │
│                    ▼                                            │
│            ┌──────────────┐                                    │
│            │  WARN_ONLY   │                                    │
│            │ (no trading  │                                    │
│            │   impact)    │                                    │
│            └──────────────┘                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Consequences

### Positive
- Klare Domain-Trennung: Safety blockt, Observability warnt
- Jedes Gate hat explizite Input/Output-Spezifikation
- Testbar: jedes Gate isoliert testbar
- Keine Überraschungen: Discord-Ausfall blockiert nie

### Negative
- Mehr Code (jedes Gate ist separate Funktion)
- Mehr Events (jedes Gate erzeugt eigenes Event)
- Komplexität bei Multi-Gate-Validierung

### Migration
- Legacy `risk_check.js` wird ersetzt durch `risk_engine.js`
- Einzel-Gates können schrittweise migriert werden

---

## Related

- ADR-001: Target Architecture
- ADR-002: Hyperliquid Integration
- ADR-003: State Model (Safety/Observability Felder)
- MASTERPLAN_PHASES_1-9.md
