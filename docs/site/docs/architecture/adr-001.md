# ADR-001: Target Architecture

**Status:** Proposed  
**Date:** 2026-03-06  
**Deciders:** System Architect (User), Assistant  
**Context:** Post-R4c Reset, Hyperliquid Integration

---

## 1. Kontext & Problem

Das vorherige System (R4c) war:
- Über-spezifiziert für Binance
- Verteilt über mehrere lose gekoppelte Prozesse
- Mit manuellem State-Management (state.json edits)
- Ohne klare Trennung Safety/Observability
- Ohne Strategy Lab Pfad

## 2. Entscheidung

**Wir bauen ein neues, deterministisches Trading-System mit strikter Trennung:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    FORWARD_V5 TARGET ARCHITECTURE               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐      │
│  │                  CORE ENGINE (Single Process)        │      │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │      │
│  │  │  Tick    │→ │  Signal  │→ │  Intent  │          │      │
│  │  │  Runner  │  │  Filter  │  │  Builder │          │      │
│  │  └──────────┘  └──────────┘  └──────────┘          │      │
│  │         ↓              ↓              ↓            │      │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │      │
│  │  │  Risk    │→ │  Exec    │→ │  Fill    │          │      │
│  │  │  Engine  │  │ (Mock)   │  │ Handler  │          │      │
│  │  └──────────┘  └──────────┘  └──────────┘          │      │
│  └──────────────────────────────────────────────────────┘      │
│                              │                                   │
│                              ↓                                   │
│  ┌──────────────────────────────────────────────────────┐      │
│  │              STATE STORE (SQLite + Events)           │      │
│  │  - events        (append-only)                       │      │
│  │  - positions     (current state)                     │      │
│  │  - orders        (history)                         │      │
│  │  - intents       (pending)                         │      │
│  └──────────────────────────────────────────────────────┘      │
│                              │                                   │
│              ┌───────────────┼───────────────┐                  │
│              ↓               ↓               ↓                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Research    │  │  Control     │  │  Reports     │          │
│  │  Lab         │  │  API/CLI     │  │  (Discord)   │          │
│  │  (isolated)  │  │              │  │  (non-block) │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 3. Komponenten

### 3.1 Core Engine (src/core_engine.js)

- EIN Prozess für den gesamten Tick-zu-Fill Flow
- Harte Timeouts für jeden Schritt
- Single Writer: nur Core Engine schreibt State
- Replay-fähig: State aus Events rebuildbar

### 3.2 State Store (SQLite + Events)

**Nicht mehr:** `state.json` als mutable Quelle  
**Stattdessen:**
- `events` Tabelle: append-only, nie löschen
- `positions`, `orders`: projections/views
- `state.json`: read-only cache für Menschen

### 3.3 Risk Engine (src/risk_engine.js)

**Pre-Trade Checks:**
- min/max notional
- leverage cap
- risk per trade
- max positions
- watchdog freshness
- reconcile clean

**Auf Fail:** reject + event + non-blocking alert

### 3.4 Observability (src/report_service.js)

- Discord-Berichte
- Scheduler-Status
- Healthchecks

**Wichtig:** NON-BLOCKING  
Discord down → WARN + Retry + Log, aber KEIN Trading-Stop

### 3.5 Research Lab (research/)

**Strikte Isolation:**
- Backtests
- Parameter Sweeps
- Walk-Forward
- AI-Research

**Kein direkter Einfluss auf Live-Execution.**

## 4. Prinzipien

### 4.1 Single Writer Principle
```
Nur core_engine darf Trading-State schreiben.
Alles andere ist read-only.
```

### 4.2 Deterministische State Projection
```
Ein Modul: src/state_projection.js
Alle Komponenten importieren NUR dieses Modul.
Keine zweite rebuildState()-Implementierung.
```

### 4.3 Idempotenz
```
Jeder Intent/Order/Event hat stabile UUIDs.
Doppelte Verarbeitung darf keinen doppelten Trade auslösen.
```

### 4.4 Timeouts Überall
```
- tick timeout
- api timeout
- discord timeout
- ws freshness timeout
```

### 4.5 Health = Funktionalität
```
Healthchecks prüfen:
- Last successful action Timestamp
- Freshness checks
- Nicht nur: "Process exists"
```

### 4.6 Replay-Fähigkeit
```
Test: Projection löschen → rebuild → IDENTISCHER Zustand
```

## 5. Safety vs Observability

| Domain | Fail Mode | Trading Impact |
|--------|-----------|----------------|
| **SAFETY** | reconcile break | BLOCK |
| | unmanaged position | BLOCK |
| | watchdog stale | BLOCK |
| | sizing violation | REJECT |
| **OBSERVABILITY** | discord down | WARN only |
| | report delayed | WARN only |
| | scheduler restart | RETRY |

## 6. Konsequenzen

### 6.1 Positiv
- Deterministisches Verhalten
- Eindeutige Fehlerursachen
- Einfachere Tests
- Klare Verantwortlichkeiten

### 6.2 Negativ
- Mehr Code für State Management
- Striktere Deployment-Prozess
- Keine "schnellen Fixes" mehr

### 6.3 Risken
- Komplexe State-Transition-Logik
- SQLite-Performance bei hoher Load

## 7. Alternativen Betrachtet

| Alternative | Abgelehnt wegen |
|-------------|-----------------|
| Redis als State | Single Point of Failure |
| Mehrere Writer | Race Conditions |
| JSON-Only | Keine ACID-Garantien |

## 8. Nächste Schritte

1. Phase 1: Skeleton & Directory Structure
2. Phase 2: Core Reliability (Event Store, State Projection)
3. Phase 3: Observability
4. Phase 7: Strategy Lab (MANDATORY)

---

**Approved:** 2026-03-06  
**Implementation:** Phase 1 startet nach ADR-001 Approval
