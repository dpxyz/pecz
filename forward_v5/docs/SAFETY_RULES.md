# SAFETY_RULES.md

## Disk Space Safety Rules

**Version:** 1.0  
**Status:** ✅ ACTIVE  
**Last Updated:** 2026-04-04

---

## 1. Grundprinzip

**Disk-Full ist ein SYSTEMIC FAILURE und darf nie wieder auftreten.**

Wie Memory-Leaks können Disk-Full-Events das gesamte System zum Absturz bringen:
- Logging stoppt (keine Observability mehr)
- State-Changes können nicht persistiert werden
- Tests werden unterbrochen
- Sessions werden gelöscht

---

## 2. Safety Levels

| Level | Threshold | Action | Severity |
|-------|-----------|--------|----------|
| **🟢 HEALTHY** | < 80% | Normal operation | Info |
| **🟡 WARN** | >= 80% | Warn + Log cleanup suggested | WARN |
| **🔴 CRITICAL** | >= 90% | **PAUSE TRADING** | CRITICAL |
| **🚨 EMERGENCY** | >= 95% | **STOP ALL TESTS** | CRITICAL |

---

## 3. Safety Rules (verbindlich)

### Rule DISK-001: Pre-Test Disk-Check
**Vor jedem Test über 1h Dauer:**
```bash
# Muss erfüllt sein:
df -h | grep "/data" | awk '{print $5}' | tr -d '%' | xargs -I {} test {} -lt 30
```
**Wenn >30% belegt:** Test abbrechen mit Fehler "DISK TOO FULL START TEST"

### Rule DISK-002: Hard-Code Log Limits
**Jeder Langzeittest (4h+) muss Hard-Limits haben:**
```javascript
const MAX_LOG_SIZE_MB = 1;      // Heartbeat max 1MB
const MAX_TEST_LOG_MB = 10;    // Total max 10MB (dann abort)
```

### Rule DISK-003: Frequency Limits
**Log-Intervall in Tests:**
| Test-Typ | Max Frequenz |
|----------|--------------|
| Unit Tests | Kein File-Logging |
| 1h Tests | 5 Min |
| 24h Tests | 15 Min |
| 7d+ Tests | 1 Stunde |

### Rule DISK-004: Built-in Health Check
**Disk-Space-CHECK ist jetzt SAFETY-LEVEL (kann PAUSE triggern):**
```javascript
// In Health Service eingetragen
Health.safetyChecks.disk_space: {
  domain: 'SAFETY',
  severity: 'CRITICAL'
}
```

### Rule DISK-005: Emergency Truncate
**Wenn Disk beim Test >80%:**
```bash
# Sofort verfügbar:
find /data/.openclaw/workspace/forward_v5 -name "*.log" -mtime 0 -size +10M -exec truncate -s 0 {} \;
```

---

## 4. Implementierung

### 4.1 Im Health Service (für Live-System)
```javascript
const Health = require('./src/health.js');

// Bei Initialisierung:
Health.register('disk_space', async () => {
  return await Health.checkDiskSpace();
}, {
  domain: Health.DOMAIN.SAFETY,
  severity: 'CRITICAL',
  interval: 30000  // Jede 30 Sekunden
});

// Critical = kann PAUSE triggern
```

### 4.2 Im Test-Code (für 24h Tests)
```javascript
// Hard-Limit bereits implementiert in simulation_24h_stability.test.js
// Auto-abort bei >10MB total
```

### 4.3 Pre-Flight Check
```bash
#!/bin/bash
# In CI/CD oder vor manuellem Test-Start

DISK_USED=$(df -h /data | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USED" -gt 30 ]; then
  echo "❌ DISK ${DISK_USED}% used - >30% threshold"
  echo "Clean up before running long tests:"
  echo "  du -sh /data/.openclaw/workspace/archive/*"
  exit 1
fi
echo "✅ Disk OK: ${DISK_USED}% used"
```

---

## 5. Monitoring

### 5.1 Während Tests
```bash
# Alle 30 Minuten (automated):
watch -n 1800 'df -h /data && du -sh forward_v5/forward_v5/simulation/'
```

### 5.2 Discord Alerts
| Event | Nachricht |
|-------|-----------|
| WARN (80%) | "⚠️ Disk at 80% - cleanup recommended" |
| CRITICAL (90%) | "🚨 Disk at 90% - TRADING PAUSED" |
| EMERGENCY (95%) | "🛑 Disk at 95% - SYSTEM SHUTDOWN" |

---

## 6. Incident History

### INC-001: 2026-04-03
- **Event:** Disk full (21GB heartbeat.log)
- **Impact:** 24h Test interrupted, Session lost
- **Root Cause:** No log rotation, 1/minute entries, 2MB per entry
- **Resolution:** Compressed 21GB → 182MB, implemented safety rules
- **Prevention:** Rules DISK-001 through DISK-005 now active

---

## 7. Checklist (für jeden 24h+ Test)

**Vor Start:**
- [ ] `df -h` shows <30% used
- [ ] Duplikate in `archive/` bereinigt
- [ ] Hard-Limits im Code verifiziert
- [ ] Emergency truncate command bereit

**Während Test:**
- [ ] Disk <80% (hourly check)
- [ ] Log rotation funktioniert
- [ ] Heartbeat Einträge wie erwartet

**Nach Test:**
- [ ] Alte Logs archivieren oder löschen
- [ ] Disk usage wieder unter 30%

---

## 8. References

| File | Purpose |
|------|---------|
| `src/health.js` | `checkDiskSpace()` implementiert |
| `tests/disk_space_safety.test.js` | Safety tests |
| `tests/simulation_24h_stability.test.js` | Hard-limits im Test |
| `memory/incident_disk_limit_2026-04-04.md` | Incident report |
| `memory/24h_test_disk_protection_strategy.md` | Strategie-Dokument |

---

## 9. Enforcement

**Verstöße gegen diese Rules:**
- CI/CD muss Tests mit `df -h > 30%` abbrechen
- Code-Review muss Log-Limits prüfen
- Runtime-Monitoring aktiviert

**Letzte Änderung:** 2026-04-04 - Pecz
