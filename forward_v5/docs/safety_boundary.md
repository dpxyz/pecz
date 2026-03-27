# Safety Boundary

**Domain:** SAFETY  
**Effect:** BLOCK/PAUSE + Event + Log  
**Trigger:** Trading-critical system failures

## Überblick

SAFETY-Checks schützen das Trading-System vor katastrophalen Fehlern. Bei einem SAFETY-Fehler wird das Trading sofort gehalten und ein Circuit Breaker ausgelöst.

> **Regel:** SAFETY-Fehler blockieren. Keine Ausnahmen.

## SAFETY Checks

| Check | Was wird geprüft | Effekt bei Fehler | Recovery |
|-------|------------------|-------------------|----------|
| `event_store` | Datenbank-Reads/Writes | BLOCK + Event + Log | Manuelle Prüfung |
| `state_projection` | State-Konsistenz | BLOCK + Event + Log | Rebuild erforderlich |
| `risk_engine` | Risiko-Validierung | BLOCK + Event + Log | Konfiguration fixen |
| `watchdog_tick` | Tick-Frische (<30s) | BLOCK + Event + Log | Datenquelle prüfen |
| `reconcile_positions` | Position-Abgleich | BLOCK + Event + Log | Manuelle Reconcile |

## Circuit Breaker Integration

```
SAFETY-Fehler detected
        ↓
   Circuit Breaker OPEN
        ↓
   Trading BLOCKED
        ↓
   Manuelle Untersuchung
        ↓
   Fix applied
        ↓
   attemptReset() → HALF_OPEN
        ↓
   Alle Checks GRÜN
        ↓
   confirmReset() → CLOSED
        ↓
   Trading resumed
```

## Events

- `SAFETY_VIOLATION_DETECTED` — Fehler erkannt
- `CIRCUIT_BREAKER_OPENED` — Trading gestoppt
- `CIRCUIT_BREAKER_HALF_OPEN` — Recovery-Test läuft
- `CIRCUIT_BREAKER_CLOSED` — Trading wieder erlaubt
- `TRADING_HALTED` — System pausiert

## Resume-Bedingungen

1. Root Cause identifiziert
2. Fix deployed
3. Alle SAFETY-Checks passen
4. Manuelles `resumeTrading()`

## Verantwortlichkeit

| Rolle | Aufgabe |
|-------|---------|
| CircuitBreaker | Zustands-Management |
| Health Service | Check-Ausführung |
| Engine | Trading-Blockade bei OPEN |

---
*Part of Phase 4: System Boundaries*
