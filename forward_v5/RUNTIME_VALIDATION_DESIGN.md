# Runtime Validation Design — FINAL (v1.0)

**Phase:** 5.0 (Pflicht-Prerequisite)  
**Ziel:** 48h Paper/Testnet-Run mit aktivem Monitoring  
**Status:** 🟢 Design final, Implementierung kann starten  
**Dauer:** Fest **48 Stunden** (keine Abkürzung)  

---

## ⚠️ OFFIZIELLE KLARSTELLUNG

> **Phase 4 war Code Freeze (erfolgreich).**
> **Production-like runtime validation ist NOCH OFFEN.**
> 
> Dieses Dokument definiert den Gate-Run für Phase 5.0.

---

## 1. Korrigierte Intervalle und Schwellen (Widersprüche aufgelöst)

| Parameter | Wert | Begründung |
|-----------|------|------------|
| **Heartbeat-Interval** | **60 Sekunden** | Häufig genug für schnelles Erkennen von Ausfällen |
| **Heartbeat-Toleranz** | **5 Minuten** | Nach 5 fehlenden Heartbeats (=5min) = Alert |
| **Health-Check-Interval** | **5 Minuten** | Regelmäßige Systemprüfung |
| **Run-Dauer** | **48 Stunden (fest)** | Eindeutig, reproduzierbar, keine Diskussion |
| **Memory-Check** | **Jeder Health-Check** | Stabile Speichernutzung prüfen |
| **Log-Größen-Check** | **Alle 30 Minuten** | Frühzeitige Erkennung von Log-Explosion |

**Widerspruch aufgelöst:** Früher stand 30 Min Heartbeat mit >60s FAIL — das war inkonsistent. Jetzt: 60s Heartbeat mit 5min Toleranz.

---

## 2. Laufzeitfenster (Festgelegt)

### Offizieller Gate-Run: **48 Stunden**

**Kein Spielraum.** Keine "Minimum+Empfohlen". Keine Abkürzung.

| Phase | Dauer | Bedingung |
|-------|-------|-----------|
| **Vorbereitung** | 30 Min | System-Check vor Start |
| **Gate-Run** | **48h** | Ununterbrochene Überwachung |
| **Abschluss** | 15 Min | Report-Generierung |
| **Gesamt** | ~48.5h |  |

**Abbruch-Kriterien (führen zu FAIL und Neustart):**
- Heartbeat fehlt >10 Minuten
- System Crash/Unbehandelte Exception
- Memory Leak >20%
- >3 ungeklärte CRITICAL Events

**Kein Abbruch bei:**
- Erwarteten Circuit-Breaker Events (Tests, Simulationen)
- Markierten/erklärten Events
- WARN-Levels (werden geloggt, aber nicht beendet)

---

## 3. Ereignisdefinitionen (Präzisiert)

### 3.1 Was ist ein "ungeklärter CRITICAL Event"?

**Definition:**
Ein CRITICAL Event ist **ungeklärt**, wenn:
- Level = FATAL oder ERROR
- UND `explained: false` im State-File
- UND kein Kommentar vorhanden
- UND nicht in der Liste "Expected Events"

**Expected Events** (gelten automatisch als erklärt):
- Circuit Breaker Tests (Simulation)
- Health Check Integration Tests
- Memory Pressure Tests (wenn markiert)
- Manuelle Trigger für Wartung

**Markierung als erklärt:**
```json
{
  "event_id": "evt-123",
  "timestamp": "2026-03-28T12:15:00Z",
  "level": "ERROR",
  "module": "circuit_breaker",
  "explained": true,
  "explained_by": "Dave",
  "explanation": "Intentionaler Test: Circuit Breaker Simulation",
  "expected": true
}
```

### 3.2 Was ist ein "ungeklärter PAUSE Event"?

**Definition:**
Ein PAUSE Event ist **ungeklärt**, wenn:
- Circuit Breaker wechselt zu OPEN
- UND `explained: false` im CB Event Log
- UND kein bekannter Test/Grund
- UND nicht in der "Expected CB Events"-Liste

**Erlaubte/erwartete CB Events** (gelten als erklärt):
- Test-bedingte SAFETY violations
- Simulierte Feed-Unterbrechungen
- Manuelle Pause für Wartung

**Markierung als erklärt:**
```json
{
  "cb_event_id": "cb-456",
  "timestamp": "2026-03-28T14:30:00Z",
  "from": "CLOSED",
  "to": "OPEN",
  "reason": "SAFETY: test_safety",
  "explained": true,
  "explained_by": "Dave",
  "explanation": "Test: SAFETY Violation Simulation",
  "expected": true
}
```

### 3.3 Wer/Was markiert ein Event als erklärt?

**Automatisch markiert als erklärt:**
- Events mit `expected: true` (Tests, Simulationen)
- Events mit bekanntem Pattern (z.B. "test_safety" im Reason)

**Manuell markiert:**
- Betreiber via CLI: `./scripts/mark_event_explained.sh --id evt-123 --reason "Test XY"`
- Innerhalb von 2 Stunden nach Event-Timestamp
- Nach 2h: Event gilt dauerhaft als ungeklärt

**Automatisch ungeklärt:**
- Jeder FATAL/ERROR ohne Markierung innerhalb von 2h
- Jeder CB OPEN ohne Markierung innerhalb von 2h

---

## 4. Persistenz-Regel (Festgelegt)

### Verhalten bei Restart des Heartbeat-Service

| Szenario | Aktion | Begründung |
|----------|--------|------------|
| **Unterbrechung <1 Minute** | Run fortsetzen | Netzwerk-Hickup, kein Problem |
| **Unterbrechung 1-60 Minuten** | Run fortsetzen, aber WARN-Event loggen | Service-Neustart, akzeptabel |
| **Unterbrechung >60 Minuten** | **Neuer Run starten** | Zu lange Lücke, Daten unzuverlässig |
| **System-Crash** | Neuer Run starten | Unvollständige Daten |

**State-File-Validierung beim Start:**
```javascript
const MAX_GAP_MINUTES = 60;
const lastHeartbeat = state.last_heartbeat;
const gapMinutes = (now - lastHeartbeat) / 60000;

if (gapMinutes > MAX_GAP_MINUTES) {
  // Neuer Run
  state = createNewRun();
  logEvent("RUN_RESTART", "Gap zu groß: ${gapMinutes}min");
} else {
  // Fortsetzen
  state.status = "RUNNING";
  logEvent("RUN_RESUMED", "Gap akzeptabel: ${gapMinutes}min");
}
```

**Datenerhaltung:**
- Bei Fortsetzung: Historie bleibt erhalten
- Bei Neustart: Alte State-Datei archivieren (`state.json.YYYY-MM-DD-HHmm`)

---

## 5. Finale Go/No-Go-Kriterien

### GO-Kriterien (ALLE müssen erfüllt sein):

| # | Kriterium | Definition | Check |
|---|-----------|------------|-------|
| 1 | **Dauer erreicht** | Mindestens 48h gelaufen | Zeitstempel prüfen |
| 2 | **Heartbeat vollständig** | ≥95% aller erwarteten Heartbeats vorhanden | 47.5h von 48h |
| 3 | **Keine Lücken >5min** | Keine fehlenden Heartbeats über 5min | Log prüfen |
| 4 | **Health Checks OK** | ≥95% aller Health Checks erfolgreich | Statistik |
| 5 | **Keine ungeklärten CRITICAL** | 0 ungeklärte FATAL/ERROR | Event-Liste |
| 6 | **Keine ungeklärten PAUSE** | 0 ungeklärte CB-OPEN Events | CB-Event-Liste |
| 7 | **Memory stabil** | Heap-Wachstum <10% über 48h | Memory-Checks |
| 8 | **Speicher OK** | Keine Heap-Überschreitung >90% | Memory-Checks |
| 9 | **Logs rotiert** | Log-Dateien <1GB pro Tag | Log-Größen |
| 10| **System am Ende OK** | Letzter Health Check: OK | Finaler Check |

### NO-GO-Kriterien (Ein FAIL reicht):

| # | Kriterium | Konsequenz |
|---|-----------|------------|
| 1 | Dauer <48h | Abbruch, Neustart nötig |
| 2 | Heartbeats <90% | Instabilität, Neustart |
| 3 | >3 ungeklärte CRITICAL | Sicherheitsbedenken, Fix nötig |
| 4 | Memory Leak >20% | Speicherproblem, Fix nötig |
| 5 | System Crash | Neustart erforderlich |
| 6 | CB stuck in OPEN >30min | Recovery-Probleme |

### Warn-Kriterien (verlangen Review, aber kein FAIL):

- 1-2 ungeklärte CRITICAL: Review, aber kann GO sein wenn erklärbar
- Memory Wachstum 10-15%: Review, Monitoring verstärken
- Health Check Erfolgsrate 90-95%: Review

---

## 6. Implementation-Checkliste (nach diesem Design)

### 6.1 Core Service
- [ ] `src/heartbeat_service.js` mit 60s Intervall
- [ ] `src/health_checker.js` mit 5min Intervall
- [ ] State-File Management mit Persistenz-Regeln
- [ ] Event-Tracking mit "explained"-Markierung

### 6.2 Configuration
```javascript
const CONFIG = {
  HEARTBEAT_INTERVAL_MS: 60 * 1000,        // 1 Minute
  HEARTBEAT_TIMEOUT_MS: 5 * 60 * 1000,     // 5 Minuten Toleranz
  HEALTH_CHECK_INTERVAL_MS: 5 * 60 * 1000, // 5 Minuten
  RUN_DURATION_HOURS: 48,                  // Fest
  MAX_GAP_MINUTES: 60,                     // Restart if >60min
  MEMORY_THRESHOLD_WARN: 80,               // %
  MEMORY_THRESHOLD_ERROR: 90,              // %
  MEMORY_LEAK_THRESHOLD: 20,               // % growth
  LOG_SIZE_THRESHOLD_MB: 1000,             // 1GB pro Tag
  EXPLANATION_WINDOW_MINUTES: 120          // 2h
};
```

### 6.3 CLI Commands
```bash
# Start
./scripts/runtime_validation_start.sh --mode paper --duration 48h

# Status (während des Runs)
./scripts/runtime_validation_status.sh

# Event als erklärt markieren
./scripts/mark_event_explained.sh --id evt-123 --reason "Test XY"

# Stop + Report
./scripts/runtime_validation_stop.sh
```

### 6.4 State-File Schema (final)
```json
{
  "run_id": "rv-2026-03-28-a1b2c3",
  "version": "1.0",
  "start_time": "2026-03-28T12:00:00.000Z",
  "planned_end_time": "2026-03-30T12:00:00.000Z",
  "status": "RUNNING",
  "last_heartbeat": "2026-03-28T14:30:00.000Z",
  "last_health_check": "2026-03-28T14:28:00.000Z",
  
  "counters": {
    "heartbeats_expected": 1440,
    "heartbeats_received": 1438,
    "heartbeats_missed": 2,
    "health_checks_total": 288,
    "health_checks_passed": 285,
    "health_checks_failed": 3
  },
  
  "events": [
    {
      "id": "evt-001",
      "timestamp": "2026-03-28T13:30:00Z",
      "level": "ERROR",
      "module": "circuit_breaker",
      "message": "SAFETY violation",
      "explained": true,
      "explained_at": "2026-03-28T13:31:00Z",
      "explained_by": "auto-test-marking",
      "expected": true
    }
  ],
  
  "cb_events": [
    {
      "id": "cb-001",
      "timestamp": "2026-03-28T14:00:00Z",
      "from": "CLOSED",
      "to": "OPEN",
      "reason": "test_safety",
      "explained": true,
      "expected": true
    }
  ],
  
  "metrics": {
    "memory_start_mb": 45,
    "memory_current_mb": 52,
    "memory_peak_mb": 58,
    "memory_growth_percent": 15.5
  },
  
  "result": null
}
```

---

## 7. Finale Aussage

> ✅ **Design final, Implementierung kann starten.**

**Abgeklärte Punkte:**
1. ✅ Heartbeat-Interval: 60 Sekunden, Toleranz: 5 Minuten
2. ✅ Run-Dauer: Fest 48 Stunden
3. ✅ Ereignisdefinitionen: Explizit definiert, 2h Markierungsfenster
4. ✅ Persistenz: Unterbrechung <60min = Fortsetzen, >60min = Neustart

**Nächster Schritt:** Implementierung der drei Scripts und des State-Managements.

**Ziel:** 48h Gate-Run kann starten sobald Implementation bereit.

---

*Design Version: 1.0 (final)*  
*Korrekturen: Intervalle, Laufzeit, Ereignisdefinitionen, Persistenz*  
*Letztes Update: 2026-03-28 12:19 CET*
