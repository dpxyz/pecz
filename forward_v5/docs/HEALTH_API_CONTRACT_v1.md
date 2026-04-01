# API Contract: /health/ready → Dashboard v1

**Version:** 1.0 (STABLE)  
**Datum:** 2026-04-01  
**Gültig für:** 5.3.2 Dashboard v1  

---

## Stabile Response-Struktur

```json
{
  "status": "UP" | "DOWN",
  "component": "readiness",
  "timestamp": "2026-04-01T11:18:00.000Z",
  "uptime_seconds": 12345,
  "reason": "optional failure description",
  "checks": {
    "state": "OK" | "MISSING" | "UNREADABLE: ...",
    "heartbeat": "OK" | "STALE (Ns ago)" | "NO_DATA",
    "memory": "OK (N%)" | "CRITICAL (N%)" | "NO_DATA",
    "service_status": "RUNNING" | "COMPLETED" | "STARTING" | "STOPPED" | "ERROR" | "NO_STATE",
    "startup": "COMPLETE" | "IN_PROGRESS"
  }
}
```

---

## Stabile Felder (Dashboard v1)

| Feld | Typ | Werte | Stabil seit |
|------|-----|-------|-------------|
| `status` | string | "UP", "DOWN" | ✅ v1.0 |
| `component` | string | "readiness" | ✅ v1.0 |
| `timestamp` | ISO8601 | UTC Zeit | ✅ v1.0 |
| `uptime_seconds` | number | Integer ≥0 | ✅ v1.0 |
| `reason` | string \| undefined | Fehlerursache | ✅ v1.0 |
| `checks.state` | string | "OK", "MISSING", "UNREADABLE: ..." | ✅ v1.0 |
| `checks.heartbeat` | string | "OK", "STALE (Ns ago)", "NO_DATA" | ✅ v1.0 |
| `checks.memory` | string | "OK (N%)", "CRITICAL (N%)", "NO_DATA" | ✅ v1.0 |
| `checks.service_status` | string | Siehe Tabelle | ✅ v1.0 |
| `checks.startup` | string | "COMPLETE", "IN_PROGRESS" | ✅ v1.0 |

---

## Service Status Werte (Stabil)

| Wert | Bedeutung | Karte im Dashboard |
|------|-----------|-------------------|
| `"RUNNING"` | Service läuft aktiv | "Service Status: Running" 🟢 |
| `"COMPLETED"` | Run erfolgreich beendet | "Service Status: Completed" 🟢 |
| `"STARTING"` | Startet gerade | "Service Status: Starting" 🟡 |
| `"STOPPED"` | Gestoppt | "Service Status: Stopped" 🔴 |
| `"ERROR"` | Fehlerzustand | "Service Status: Error" 🔴 |
| `"NO_STATE"` | Kein Status verfügbar | "Service Status: --" ⚪ |

---

## Breaking Changes Policy

Dashboard v1 akzeptiert ERWEITERUNGEN aber keine ÄNDERUNGEN:

✅ **Erlaubt:** Neue Felder hinzufügen (werden ignoriert)
✅ **Erlaubt:** Neue Check-Typen in `checks`
❌ **Verboten:** Bestehende Feld-Namen ändern
❌ **Verboten:** Werte-Format ändern (z.B. "OK" → "ok")
❌ **Verboten:** Pflichtfelder entfernen

---

## Dashboard-Rendering-Logik

```javascript
// Status-Indikator
const isUp = data.status === 'UP';
indicator.className = isUp ? 'status-up' : 'status-down';

// Uptime
formatDuration(data.uptime_seconds); // "1d 2h 3m"

// Heartbeat
if (data.checks.heartbeat === 'OK') {
  show('Fresh', 'Last <60s');
} else if (data.checks.heartbeat.startsWith('STALE')) {
  show('Stale', data.checks.heartbeat, isError=true);
}

// Memory
const memMatch = data.checks.memory.match(/(\d+)%/);
if (memMatch) {
  const pct = parseInt(memMatch[1]);
  show(`${pct}%`, pct > 95 ? 'CRITICAL' : 'Normal', isError=pct>95);
}

// Service Status
show(data.checks.service_status, data.checks.service_status);
```

---

## Alert-Trigger (für 5.3.3)

Dashboard v1 speichert ALERT-REGELN aber keinen Verlauf:

```javascript
const ALERT_RULES = [
  { check: 'status', value: 'DOWN', severity: 'CRITICAL' },
  { check: 'checks.heartbeat', pattern: 'STALE', severity: 'WARNING' },
  { check: 'checks.memory', pattern: 'CRITICAL', severity: 'CRITICAL' }
];
```

---

**Last Updated:** 2026-04-01 11:18 CET  
**Commit:** API Contract v1.0 STABLE
