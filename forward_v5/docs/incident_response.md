# Incident Response

Runbooks für System-Fehler und Recovery.

---

## Incident: SAFETY Violation (Circuit Breaker OPEN)

**Severity:** CRITICAL  
**Auto-Action:** Trading HALTED

### Erkennung
- Event: `CIRCUIT_BREAKER_OPENED`
- Health Status: `isPaused = true`
- Alert: Discord (if configured)

### Sofortmaßnahmen
| Schritt | Aktion | Zeit |
|---------|--------|------|
| 1 | ACK in Logs/Event-Stream | <1 min |
| 2 | Fehlenden SAFETY-Check identifizieren | <5 min |
| 3 | Root Cause Analysis starten | <15 min |

### Investigation
```bash
# Health-Status prüfen
./cli.js health status

# Logs filtern
tail -f logs/forward-v5.*.log | grep "SAFETY_VIOLATION"

# Circuit Breaker Status
./cli.js circuit-breaker status
```

### Fix
- Fehler beheben oder umgehen
- Konfiguration korrigieren
- Datenquelle wechseln (falls nötig)

### Resume
```bash
# 1. Validiere Health
./cli.js health validate

# 2. Setze in HALF_OPEN
./cli.js circuit-breaker attempt-reset

# 3. Prüfe alle SAFETY-Checks
./cli.js health check --domain SAFETY

# 4. Bestätige Recovery
./cli.js circuit-breaker confirm-reset

# 5. Resume Trading
./cli.js resume
```

### Escalation
- >15 min ungelöst → Page on-call
- >1h ungelöst → Emergency Review

---

## Incident: OBSERVABILITY Degradation

**Severity:** WARN  
**Auto-Action:** Degraded Mode (Queue + Retry)

### Erkennung
- Event: `HEALTH_OBSERVABILITY_WARNING`
- Log: `WARN` entries
- Discord: Notification (if configured)

### Aktionen
| Schritt | Aktion |
|---------|--------|
| 1 | Logs prüfen: `grep WARN logs/forward-v5.*.log` |
| 2 | Fallback aktiv? Ja → OK |
| 3 | Queue-Status prüfen |  
| 4 | Escalate wenn >30 min |

### Resume
- **Auto-resume** bei Recovery
- Keine manuelle Aktion nötig

### Escalation
- >30 min → Ticket erstellen
- >2h → Incident Review

---

## Quick Reference: Commands

```bash
# Status prüfen
./cli.js status              # Gesamt-Status
./cli.js health status       # Health-Status
./cli.js circuit-breaker status  # Breaker-Status

# Circuit Breaker
./cli.js circuit-breaker attempt-reset   # → HALF_OPEN
./cli.js circuit-breaker confirm-reset   # → CLOSED
./cli.js circuit-breaker force-reset     # ⚠️ Emergency only

# Trading
./cli.js pause             # Manuelle Pause
./cli.js resume            # Resume (prüft Breaker)
```

---

## Severity Matrix

| Incident | Severity | Auto-Action | Manual |
|----------|----------|-------------|--------|
| SAFETY Violation | CRITICAL | BLOCK | Required |
| OBSERVABILITY Warn | WARN | Degrade | Optional |
| Circuit OPEN | CRITICAL | HALT | Required |
| HALF_OPEN Recovery | WARN | Monitor | Optional |

---
*Part of Phase 4: System Boundaries*
