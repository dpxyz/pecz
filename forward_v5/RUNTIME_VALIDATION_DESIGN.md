# Runtime Validation Design — Heartbeat & Monitoring

**Phase:** 5.0 (Pflicht-Prerequisite)  
**Ziel:** 24-48h Paper/Testnet-Run mit aktivem Monitoring  
**Dauer:** Mindestens 24h, empfohlen 48h  

---

## Übersicht

Das Runtime Validation System überwacht den Forward V5 Paper/Testnet-Run während der Phase 5.0. Es stellt sicher, dass:

1. Das System **stetig läuft** (keine stillen Ausfälle)
2. **Health Checks** funktionieren
3. **Circuit Breaker** korrekt arbeitet
4. **Speicher und Logs** kontrolliert bleiben
5. Bei Problemen **Alerts** ausgelöst werden

---

## Architektur

```
┌─────────────────────────────────────────────────────────┐
│                     Forward V5 System                    │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐│
│  │ Event Store │  │ Risk Engine  │  │ Circuit Breaker ││
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘│
│         │                │                   │          │
│         └────────────────┼───────────────────┘          │
│                          │                             │
│                   ┌──────▼──────┐                      │
│                   │ Health Service │                      │
│                   └──────┬──────┘                      │
└──────────────────────────┼──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                     Heartbeat Service                    │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐│
│  │  Scheduler  │  │ Health Check │  │   Log Monitor   ││
│  │ (30min)     │  │ (poll)       │  │ (tail -f)       ││
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘│
│         │                │                   │          │
│         └────────────────┼───────────────────┘          │
│                          │                             │
│                   ┌──────▼──────┐                      │
│                   │ Alert Router  │                      │
│                   │ (Discord/Web) │                      │
│                   └─────────────┘                      │
└─────────────────────────────────────────────────────────┘
```

---

## Heartbeat Service

### Zweck
Heartbeat beweist, dass das System noch lebt. Fehlende Heartbeats = System möglicherweise tot.

### Implementation

**heartbeat.js**
```javascript
// Konfiguration
const HEARTBEAT_INTERVAL_MS = 30 * 60 * 1000; // 30 Minuten
const HEALTH_CHECK_INTERVAL_MS = 5 * 60 * 1000; // 5 Minuten
const HEARTBEAT_LOG_FILE = './logs/heartbeat.log';
const STATE_FILE = './runtime_validation/state.json';
```

**Funktionen:**
1. **Heartbeat Loop** — Schreibt alle 30 Minuten Status
2. **Health Check Loop** — Ruft Health-Status alle 5 Min ab
3. **Log Monitoring** — Überwacht Logs auf FATAL/ERROR
4. **Alerting** — Sendet Discord/Webhook bei Problemen

**Heartbeat Eintrag Format:**
```json
{
  "timestamp": "2026-03-28T12:15:00.000Z",
  "type": "HEARTBEAT",
  "status": "OK", // OK | WARN | CRITICAL
  "run_duration_hours": 12.5,
  "checks": {
    "event_store": "OK",
    "circuit_breaker": "CLOSED",
    "last_health_check": "2026-03-28T12:10:00.000Z",
    "memory_mb": 124
  },
  "alerts_since_last": 0,
  "pid": 12345
}
```

---

## Health Checks

### Check-Typen

| Check | Frequenz | Action bei FAIL |
|-------|----------|-----------------|
| **Event Store** | 5 min | Log ERROR, zähle zu CRITICAL Events |
| **Circuit Breaker State** | 5 min | Log WARN, zähle PAUSE Events |
| **Memory Usage** | 5 min | Log WARN >80%, ERROR >90% |
| **Log File Growth** | 30 min | Rotiere bei >100MB |
| **Last Trade Timestamp** | 30 min | WARN wenn >1h keine Activity |

### Health Check Implementation

```javascript
// Pseudo-Code
async function performHealthCheck() {
  const results = {
    timestamp: new Date().toISOString(),
    overall: 'OK',
    checks: []
  };
  
  // 1. Event Store Ping
  const esStatus = await checkEventStoreConnection();
  results.checks.push({ name: 'event_store', status: esStatus });
  
  // 2. Circuit Breaker State
  const cbState = circuitBreaker.getCurrentState();
  results.checks.push({ name: 'circuit_breaker', state: cbState });
  
  // 3. Memory
  const memUsage = process.memoryUsage();
  const memPercent = (memUsage.heapUsed / memUsage.heapTotal) * 100;
  results.checks.push({ 
    name: 'memory', 
    percent: memPercent,
    status: memPercent > 90 ? 'CRITICAL' : memPercent > 80 ? 'WARN' : 'OK'
  });
  
  // 4. Log file size
  const logSize = await getLogFileSize();
  results.checks.push({ name: 'log_size_mb', value: logSize });
  
  return results;
}
```

---

## Alerting

### Alert Levels

| Level | Trigger | Action | Rate Limit |
|-------|---------|--------|------------|
| **FATAL** | Unbehandelte Exception | Discord + Log | Max 1/Min |
| **CRITICAL** | SAFETY violation, Circuit OPEN | Discord + Log | Max 1/Min |
| **ERROR** | Health Check FAIL | Discord + Log | Max 1/5 Min |
| **WARN** | Memory >80%, OBS failure | Log only | — |

### Discord Webhook Format

```json
{
  "embeds": [{
    "title": "🔴 Forward V5 Runtime Alert",
    "color": 16711680, // Rot
    "fields": [
      { "name": "Level", "value": "CRITICAL", "inline": true },
      { "name": "Check", "value": "circuit_breaker", "inline": true },
      { "name": "Timestamp", "value": "2026-03-28T12:15:00Z", "inline": true },
      { "name": "Run Duration", "value": "12.5h", "inline": true },
      { "name": "Details", "value": "Circuit Breaker OPENED due to SAFETY violation" }
    ],
    "timestamp": "2026-03-28T12:15:00.000Z"
  }]
}
```

---

## State Management

### Runtime Validation State File

**Pfad:** `./runtime_validation/state.json`

```json
{
  "run_id": "rv-2026-03-28-a1b2c3",
  "start_time": "2026-03-28T12:15:00.000Z",
  "target_duration_hours": 48,
  "status": "RUNNING", // RUNNING | PAUSED | COMPLETED | FAILED
  
  "metrics": {
    "heartbeats_total": 24,
    "heartbeats_missed": 0,
    "health_checks_total": 144,
    "health_checks_failed": 0,
    "alerts_fatal": 0,
    "alerts_critical": 1,
    "alerts_error": 2,
    "alerts_warn": 15
  },
  
  "circuit_breaker_events": [
    {
      "time": "2026-03-28T14:30:00.000Z",
      "from": "CLOSED",
      "to": "OPEN",
      "reason": "SAFETY: test_safety"
    },
    {
      "time": "2026-03-28T14:35:00.000Z",
      "from": "OPEN",
      "to": "HALF_OPEN",
      "reason": "attemptReset()"
    },
    {
      "time": "2026-03-28T14:36:00.000Z",
      "from": "HALF_OPEN",
      "to": "CLOSED",
      "reason": "confirmReset()"
    }
  ],
  
  "validation_result": null // Wird bei COMPLETION gesetzt
}
```

---

## Acceptance-Kriterien für Paper-Run

### Absolute Pflichtkriterien (ALLE müssen erfüllt sein)

| # | Kriterium | Definition | Messung |
|---|-----------|------------|---------|
| 1 | **Heartbeat stabil** | Keine fehlenden Heartbeats >60s Minuten | Heartbeat Log überprüfen |
| 2 | **Keine stillen Ausfälle** | System reagiert auf Health Checks | Alle 5-Min-Checks OK |
| 3 | **Keine ungeklärten CRITICAL Events** | Alle FATAL/ERROR erklärt und dokumentiert | Log-Analyse |
| 4 | **Keine ungeklärten PAUSE Events** | Alle Circuit-Breaker-Trigger erklärt | CB Events Log |
| 5 | **Health Checks regelmäßig** | Checks laufen alle 5 Min | Zeitstempel prüfen |
| 6 | **Circuit Breaker stabil** | Nur erwartete State Transitions | State-Log prüfen |
| 7 | **Speicher stabil** | Keine Memory Leaks >10% über 48h | Memory-Checks |
| 8 | **Log-Größe kontrolliert** | Rotation funktioniert <1GB/Tag | Log-Größe prüfen |

### Soft-Kriterien (sollten erfüllt sein)

| # | Kriterium | Erwartung |
|---|-----------|-----------|
| 9 | **Warnungen minimiert** | <10 WARN/Tag (erklärbar) |
| 10 | **Recovery getestet** | Mind. 1 Circuit-Breaker Recovery ausgeführt |
| 11 | **Trade-Aktivität** | Mindestens 1 Trade pro 6h (Paper) |
| 12 | **Graceful Shutdown** | Clean Shutdown bei SIGTERM |

### FAIL-Kriterien (führen zu NO-GO)

| Bedingung | Konsequenz |
|-----------|------------|
| >3 ungeklärte CRITICAL Events | NO-GO, Fix erforderlich |
| Memory Leak >20% | NO-GO, Investigation |
| System crash / unhandled exception | NO-GO, Fix erforderlich |
| Heartbeat missed >3x | NO-GO, Stability issue |
| Circuit Breaker stuck in OPEN | NO-GO, Recovery fail |

---

## Auswertung nach 24-48h

### Auto-Report Generierung

Nach Ablauf der Runtime-Validation wird automatisch ein Report erstellt:

**Datei:** `./reports/runtime_validation_report_YYYY-MM-DD.md`

**Inhalt:**
```markdown
# Runtime Validation Report

**Run ID:** rv-2026-03-28-a1b2c3  
**Zeitraum:** 2026-03-28 12:15 → 2026-03-30 12:15 (48h)  
**Status:** ✅ PASSED / ❌ FAILED

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Gesamtdauer | 48h |
| Heartbeats | 96/96 (100%) |
| Health Checks | 576/576 (100%) |
| CRITICAL Events | 2 (erklärt) |
| ERROR Events | 5 (erklärt) |
| WARN Events | 23 |
| Memory Start/End | 45MB / 52MB (+15%) |

## Circuit Breaker Events

| Zeit | Von | Nach | Grund |
|------|-----|------|-------|
| 14:30 | CLOSED | OPEN | SAFETY: test_safety (expected) |
| 14:35 | OPEN | HALF_OPEN | attemptReset() |
| 14:36 | HALF_OPEN | CLOSED | confirmReset() |

## Go/No-Go Entscheidung

✅ **GO** — Alle Pflichtkriterien erfüllt.
```

---

## Script-Struktur

**Start:**
```bash
./scripts/runtime_validation_start.sh --duration 48h --mode paper
# Erstellt state.json, startet Heartbeat Service
```

**Nach 48h:**
```bash
./scripts/runtime_validation_stop.sh
# Erstellt Report, prüft Kriterien, gibt GO/NO-GO
```

**Manueller Check während des Runs:**
```bash
./scripts/runtime_validation_status.sh
# Zeigt aktuelle Metriken
```

---

## Abgrenzungen

**Im Scope (Phase 5.0):**
- Heartbeat / Health Check Service
- Log Monitoring
- Circuit Breaker Event-Tracking
- Memory Monitoring
- Alerting (Discord)
- Auto-Reporting

**Nicht im Scope (Phase 5.x):**
- systemd integration (5.1)
- Web API / CLI (5.2)
- Log rotation (5.3 — wird manuell gemacht)
- Deployment automation (5.4)

---

## Files

| Datei | Zweck |
|-------|-------|
| `src/heartbeat_service.js` | Hauptservice |
| `src/health_checker.js` | Health check logic |
| `src/alert_router.js` | Discord/Webhook alerting |
| `runtime_validation/state.json` | Laufender Zustand |
| `logs/heartbeat.log` | Heartbeat Einträge |
| `reports/runtime_validation_*.md` | Finale Reports |

---

*Design Version: 1.0*  
*Erstellt: 2026-03-28*
