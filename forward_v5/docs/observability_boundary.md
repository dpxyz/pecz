# Observability Boundary

**Domain:** OBSERVABILITY  
**Effect:** WARN + Log (NEVER blocks)  
**Trigger:** Infrastructure-/Delivery-Fehler

## Überblick

OBSERVABILITY-Checks überwachen das System ohne das Trading zu blockieren. Bei Fehlern wird gewarnt, in die Queue geschrieben und automatisch retryed — aber niemals gehalten.

> **Regel:** OBSERVABILITY-Fehler warnen nur. Trading läuft weiter.

## OBSERVABILITY Checks

| Check | Was wird geprüft | Effekt bei Fehler | Recovery |
|-------|------------------|-------------------|----------|
| `discord_webhook` | Webhook-Lieferung | WARN + Queue + Retry | Auto-retry |
| `logger_fallback` | Datei-Schreiben | WARN + Console fallback | Auto |
| `check_latency` | Antwortzeit | WARN + Log | Monitor |
| `report_service` | Report-Generierung | WARN + Queue | Auto-retry |
| `health_check_slow` | Langsame Checks | WARN + Log | Monitor |

## Non-Blocking Guarantee

```
OBSERVABILITY-Fehler
        ↓
     WARN Log
        ↓
   Queue/Retry
        ↓
  Trading läuft weiter
```

## Circuit Breaker Regel

```javascript
// Dies passiert NIE:
if (observabilityCheckFails) {
    circuitBreaker.open();  // VERBOTEN ❌
}

// Richtig:
if (safetyCheckFails) {
    circuitBreaker.open();  // Erlaubt ✅
}
```

## Degradation Path

| Stufe | Aktion | Trading-Impact |
|-------|--------|----------------|
| 1 | WARN loggen | Keiner |
| 2 | Fallback aktivieren | Keiner |
| 3 | Queue + Retry | Keiner |
| 4 | Alert bei Persistenz | Keiner |

## Versprechen

> "OBSERVABILITY soll niemals den Unterschied zwischen einem profitablen Trade und einem verpassten Trade ausmachen."

## Events

- `HEALTH_OBSERVABILITY_WARNING` — Check fehlgeschlagen
- `OBSERVABILITY_RECOVERED` — Check wieder grün

---
*Part of Phase 4: System Boundaries*
