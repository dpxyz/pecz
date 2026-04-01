# Block 5.3.3: Alert Integration Design

**Status:** Design Phase  
**Scope:** Verlässliche Alerts bei kritischen Zuständen  
**Anti-Goals:** Kein Noise, keine Historie, keine fancy Features  

---

## Design-Prinzipien

1. **Nur echte Probleme** - Keine "WARN" wegen kurzer Spikes
2. **Signal > Noise** - Max 1-2 Alerts pro Stunde in normalen Betrieb
3. **Sofort sichtbar** - Im Dashboard, kein externer Dienst nötig
4. **Self-healing aware** - Keine Alerts während Restart/Startup

---

## A) Alert-Regeln

### Regel 1: Service Down

```yaml
Name: service_down
Condition: /health/ready status == "DOWN"
Severity: CRITICAL
Cooldown: 300s (5 Min)
Message: "Service readiness check failed: {reason}"
```

### Regel 2: Heartbeat Stale

```yaml
Name: heartbeat_stale
Condition: checks.heartbeat starts_with "STALE"
Severity: WARNING
Cooldown: 120s (2 Min)
Message: "No heartbeat for {extracted_seconds}s"
```

### Regel 3: Memory Critical

```yaml
Name: memory_critical
Condition: checks.memory starts_with "CRITICAL"
Severity: CRITICAL
Cooldown: 60s (1 Min)
Message: "Memory usage critical: {extracted_percent}%"
```

### Regel 4: Circuit Breaker Open

```yaml
Name: circuit_breaker_tripped
Condition: checks.circuit_breaker == "OPEN"
Severity: WARNING
Cooldown: 300s (5 Min)
Message: "Risk protection triggered - execution halted"
```

---

## B) Trigger-Bedingungen

### Wann wird ein Alert ausgelöst?

| Bedingung | Logik | Beispiel |
|-----------|-------|----------|
| **Immediate** | Status-Änderung von UP → DOWN | readiness.status ändert sich |
| **Sustained** | 3 aufeinanderfolgende Checks FAILED | 3x heartbeat stale |
| **Threshold** | Wert überschreitet Grenze | memory > 95% |
| **Recovery** | Kein Alert bei UP → DOWN → UP < Cooldown | Filtert Flapping |

### Anti-Noise-Maßnahmen

```javascript
// 1. Cooldown: Gleicher Alert nicht öfter als alle X Sekunden
const lastAlert = alertHistory.get(alertKey);
if (lastAlert && (now - lastAlert) < COOLDOWN) {
  return; // Suppress
}

// 2. Startup-Grace: Keine Alerts in ersten 120s
if (serverUptime < 120) {
  return; // Still starting
}

// 3. Flap-Protection: Mindestens 2 FAILED Checks
if (consecutiveFailures < 2) {
  return; // Wait for confirmation
}
```

---

## C) Severity-Mapping

| Severity | Bedeutung | Farbe | Klingelt es? | Escalation |
|----------|-----------|-------|--------------|--------------|
| **CRITICAL** | Service nicht betriebsbereit | 🔴 Rot | Ja (sofort) | Webhook + Log + Dashboard |
| **WARNING** | Degradiert, aber funktional | 🟡 Gelb | Nein | Log + Dashboard |
| **INFO** | Nur zur Information | 🔵 Blau | Nein | Log |

### Severity-Entscheidungsbaum

```
Is status == "DOWN"?
  ├── Ja ──▶ CRITICAL (Service kaputt)
  └── Nein ──▶ Check heartbeat
       ├── "STALE" ──▶ WARNING (Eventuell repariert sich)
       └── "OK" ──▶ Check memory
            ├── "CRITICAL" ──▶ CRITICAL (Speicher > 95%)
            └── "OK" ──▶ Kein Alert
```

---

## D) Alert-Anzeige im Dashboard v1

### Design: Floating Alert Banner

```html
<!-- Einfach, prominent, nicht störend -->
<div id="alertBanner" class="banner-critical">
  🔴 CRITICAL: Memory usage 96% (threshold: 95%)
  <span class="banner-time">11:18:23</span>
</div>

<div id="alertBanner" class="banner-warning">
  🟡 WARNING: Heartbeat stale (120s ago)
  <span class="banner-time">11:15:45</span>
</div>
```

### Regeln für Anzeige

- **Max 1 Banner** (wichtigster Alert)
- **CRITICAL** überdeckt WARNING
- **Auto-dismiss** bei Recovery (nach 5s Verzögerung)
- **Zeitstempel** zeigt wann der Alert startete

---

## E) Alert-Speicher (v1 - Minimal)

```javascript
// NUR aktive Alerts (keine Historie!)
const activeAlerts = new Map();

// Struktur pro Alert
{
  id: "memory_critical_20260401_111823", // Eindeutig
  rule: "memory_critical",
  severity: "CRITICAL",
  message: "Memory usage critical: 96%",
  startedAt: "2026-04-01T11:18:23.000Z",
  lastSeen: "2026-04-01T11:18:23.000Z",
  acknowledged: false,
  count: 1
}

// Cleanup: Alerts entfernen wenn Bedingung nicht mehr zutrifft
function resolveAlerts(currentChecks) {
  for (const [id, alert] of activeAlerts) {
    if (!checkStillApplies(alert.rule, currentChecks)) {
      activeAlerts.delete(id);
      showRecoveryNotification(alert);
    }
  }
}
```

**Keine Persistenz:** Alerts verschwinden bei Server-Restart.
**Keine Historie:** Kein "Letzte Alerts" View in v1.

---

## F) Webhook-Integration (Optional v1.1)

```javascript
// Config
const WEBHOOK_URL = process.env.ALERT_WEBHOOK_URL; // Optional

// Send on CRITICAL only
if (severity === 'CRITICAL' && WEBHOOK_URL) {
  fetch(WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      service: 'forward_v5',
      severity: severity,
      message: message,
      timestamp: new Date().toISOString(),
      metadata: { /* checks, reason, etc */ }
    })
  }).catch(err => console.error('Webhook failed:', err));
}
```

**Unterstützte Ziele:**
- Discord (via webhook)
- Slack (via webhook)
- Generic HTTP endpoint

**NICHT in v1:**
- Email
- SMS
- PagerDuty

---

## G) Implementierungs-Reihenfolge

1. **Alert-Engine** (`alertEngine.js`)
   - Regel-Evaluation
   - Cooldown-Handling
   - State-Management

2. **Dashboard-Integration** (`dashboard.html`)
   - Alert-Banner
   - Severity-Farben
   - Auto-dismiss

3. **Webhook** (Optional)
   - POST auf externe URL
   - Retry-Logic (3 Versuche)

---

## H) Test-Szenarien

| Szenario | Erwartung |
|----------|-----------|
| Service stoppt | CRITICAL Alert nach 2 Checks, 5 Min Cooldown |
| Kurzer Spike (<2 Checks) | Kein Alert (Flap-Protection) |
| Memory 96% → 80% | Alert sofort, Recovery nach 5s |
| Startup-Phase | Keine Alerts (Grace Period) |
| Schnelles Flapping | Max 1 Alert pro Cooldown-Periode |

---

**Next:** Implementierung Alert-Engine
