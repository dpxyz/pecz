# Fix 5.0c — Memory Alert Algorithmus Korrektur

**Status:** 🟡 Ready for Implementation  
**Priorität:** P0 (Blocker für Phase 5 GO)  
**Geschätzter Aufwand:** 30-60 Minuten  
**Autor:** Pecz (Automatische Analyse)  
**Datum:** 31. März 2026

---

## Problem-Zusammenfassung (aus Fix 5.0b Report)

Der `heartbeat_service.js` berechnet Memory-Growth als **Peak-to-Start**, nicht als **Trend über Zeit**:

```javascript
// ❌ DEFEKT: Einfache Differenz
const memGrowth = ((current - start) / start) * 100;
```

**Ergebnis:** False-Positives bei jedem GC-Peak (25% statt 0% echter Trend).

---

## Lösung (Empfohlene Option: Hybrid-Ansatz)

Kombination aus:
1. **Schneller Workaround** (sofort — 5 Min Fix)
2. **Korrekte Implementierung** (heute — 30 Min Fix)
3. **Cleanup** (morgen — optional)

---

## Schritt 1: Sofortiger Workaround (5 Min)

**Datei:** `forward_v5/src/heartbeat_service.js`

### Änderung 1: Threshold temporär erhöhen

```javascript
// Zeile ~20
const CONFIG = {
  // ... andere Configs ...
  
  // WORKAROUND 5.0c: Threshold erhöht bis Algorithmus korrigiert
  // STATT: MEMORY_LEAK_THRESHOLD: 20
  MEMORY_LEAK_THRESHOLD: 50,  // 50% erlaubt Startup-GC-Spikes
  
  // NEU: Minimale Laufzeit vor Leak-Checks (Minuten)
  MEMORY_LEAK_MIN_UPTIME_MINUTES: 60,  // Erst nach 1h checken
};
```

### Änderung 2: Uptime-Check hinzufügen

```javascript
// Zeile ~420 (in updateMetrics())
function updateMetrics(healthResults) {
  if (!state) return;
  
  // Update memory metrics
  const memUsage = process.memoryUsage();
  state.metrics.memory_current_mb = Math.round(memUsage.heapUsed / 1024 / 1024);
  if (state.metrics.memory_current_mb > state.metrics.memory_peak_mb) {
    state.metrics.memory_peak_mb = state.metrics.memory_current_mb;
  }
  
  // WORKAROUND 5.0c: Einfache Differenz bleibt, aber nur nach Uptime-Gate
  const memGrowth = ((state.metrics.memory_current_mb - state.metrics.memory_start_mb) 
    / state.metrics.memory_start_mb) * 100;
  state.metrics.memory_growth_percent = parseFloat(memGrowth.toFixed(2));
  
  // Check memory thresholds
  const memPercent = (memUsage.heapUsed / memUsage.heapTotal) * 100;
  if (memPercent > CONFIG.MEMORY_THRESHOLD_ERROR) {
    sendAlert('CRITICAL', 'Memory Usage Critical', `${memPercent.toFixed(1)}% > ${CONFIG.MEMORY_THRESHOLD_ERROR}%`);
    logEvent('MEMORY_CRITICAL', `${memPercent.toFixed(1)}%`, 'CRITICAL');
  } else if (memPercent > CONFIG.MEMORY_THRESHOLD_WARN) {
    sendAlert('WARN', 'Memory Usage High', `${memPercent.toFixed(1)}% > ${CONFIG.MEMORY_THRESHOLD_WARN}%`);
    logEvent('MEMORY_WARN', `${memPercent.toFixed(1)}%`, 'WARN');
  }
  
  // WORKAROUND 5.0c: Leak-Check nur nach Mindest-Uptime
  const uptimeMinutes = process.uptime() / 60;
  if (uptimeMinutes > CONFIG.MEMORY_LEAK_MIN_UPTIME_MINUTES) {
    if (state.metrics.memory_growth_percent > CONFIG.MEMORY_LEAK_THRESHOLD) {
      sendAlert('CRITICAL', 'Memory Leak Detected', 
        `Growth: ${state.metrics.memory_growth_percent.toFixed(1)}% > ${CONFIG.MEMORY_LEAK_THRESHOLD}%`);
    }
  }
  
  persistState();
}
```

**Ergebnis:** Keine False-Positives in der ersten Stunde. Reicht für 4h Mini-Run.

---

## Schritt 2: Korrekte Implementierung (30 Min)

**Datei:** `forward_v5/src/heartbeat_service.js`

### Änderung 3: Memory-History hinzufügen

```javascript
// Nach den anderen CONFIG-Werten (Zeile ~30)
const CONFIG = {
  // ... andere Configs ...
  
  // KORREKTUR 5.0c: Richtiger Algorithmus
  MEMORY_LEAK_THRESHOLD: 10,  // Zurück auf 10%
  MEMORY_LEAK_MIN_UPTIME_MINUTES: 30,  // Reduziert von 60
  MEMORY_TREND_WINDOW_HOURS: 6,  // Trend über 6h
};

// NEU: Memory-History für Trend-Berechnung
const memoryHistory = [];
const MAX_MEMORY_SAMPLES = 72;  // 6h × 12 Samples/h (alle 5 Min)
```

### Änderung 4: Trend-basierte Berechnung

```javascript
// ERSETZEN: updateMetrics() komplett
function updateMetrics(healthResults) {
  if (!state) return;
  
  // Update basic memory metrics
  const memUsage = process.memoryUsage();
  const currentMB = Math.round(memUsage.heapUsed / 1024 / 1024);
  state.metrics.memory_current_mb = currentMB;
  if (currentMB > state.metrics.memory_peak_mb) {
    state.metrics.memory_peak_mb = currentMB;
  }
  
  // KORREKTUR 5.0c: Speichere Sample mit Timestamp
  const now = Date.now();
  memoryHistory.push({
    timestamp: now,
    memory_mb: currentMB
  });
  
  // Aufräumen: Nur Samples aus letzten 6h behalten
  const cutoffTime = now - (CONFIG.MEMORY_TREND_WINDOW_HOURS * 60 * 60 * 1000);
  while (memoryHistory.length > 0 && memoryHistory[0].timestamp < cutoffTime) {
    memoryHistory.shift();
  }
  
  // Trim auf Max-Samples
  while (memoryHistory.length > MAX_MEMORY_SAMPLES) {
    memoryHistory.shift();
  }
  
  // KORREKTUR 5.0c: Berechne Trend mit Linear Regression
  // (wie im health_checker.js)
  let growthPercent = 0;
  
  if (memoryHistory.length >= 12) {  // Mindestens 1h Daten (12 × 5min)
    const n = memoryHistory.length;
    const firstTime = memoryHistory[0].timestamp;
    
    let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
    for (let i = 0; i < n; i++) {
      const sample = memoryHistory[i];
      const x = (sample.timestamp - firstTime) / (1000 * 60 * 60);  // Stunden
      const y = sample.memory_mb;
      sumX += x;
      sumY += y;
      sumXY += x * y;
      sumXX += x * x;
    }
    
    // Steigung in MB pro Stunde
    const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
    
    // Konvertiere zu Prozent über 6h (relativ zu Start)
    const projectedGrowthMB = slope * CONFIG.MEMORY_TREND_WINDOW_HOURS;
    growthPercent = (projectedGrowthMB / state.metrics.memory_start_mb) * 100;
  }
  
  state.metrics.memory_growth_percent = parseFloat(growthPercent.toFixed(2));
  
  // Check memory thresholds (unverändert)
  const memPercent = (memUsage.heapUsed / memUsage.heapTotal) * 100;
  if (memPercent > CONFIG.MEMORY_THRESHOLD_ERROR) {
    sendAlert('CRITICAL', 'Memory Usage Critical', `${memPercent.toFixed(1)}% > ${CONFIG.MEMORY_THRESHOLD_ERROR}%`);
    logEvent('MEMORY_CRITICAL', `${memPercent.toFixed(1)}%`, 'CRITICAL');
  } else if (memPercent > CONFIG.MEMORY_THRESHOLD_WARN) {
    sendAlert('WARN', 'Memory Usage High', `${memPercent.toFixed(1)}% > ${CONFIG.MEMORY_THRESHOLD_WARN}%`);
    logEvent('MEMORY_WARN', `${memPercent.toFixed(1)}%`, 'WARN');
  }
  
  // KORREKTUR 5.0c: Leak-Check mit Trend (nicht Peak-Start)
  const uptimeMinutes = process.uptime() / 60;
  if (uptimeMinutes > CONFIG.MEMORY_LEAK_MIN_UPTIME_MINUTES) {
    if (state.metrics.memory_growth_percent > CONFIG.MEMORY_LEAK_THRESHOLD) {
      sendAlert('CRITICAL', 'Memory Leak Detected', 
        `Trend: ${state.metrics.memory_growth_percent.toFixed(1)}% over ${CONFIG.MEMORY_TREND_WINDOW_HOURS}h > ${CONFIG.MEMORY_LEAK_THRESHOLD}%`);
    }
  }
  
  persistState();
}
```

---

## Schritt 3: Testplan für Fix 5.0c

### Test 1: Unit Test (lokal)

```bash
cd forward_v5
node -e "
const hs = require('./src/heartbeat_service');
// Test: Simuliere 6h mit oszillierendem Memory
// Erwartet: Kein Alert bei GC-Spikes, Alert bei echtem Leak
"
```

### Test 2: Mini-Run (4h)

| Zeit | Prüfung | Erwartet |
|------|---------|----------|
| T+0-1h | Keine Leak-Alerts | ✅ Silent |
| T+1-4h | Memory stabil | ✅ Keine Alerts |
| T+4h | Abbruch/OK | ✅ Sauber |

### Test 3: 48h Validation

**Nur wenn Mini-Run sauber:**
- Vollständiger 48h Run
- GO/NO-GO Kriterien prüfen
- Ziel: GO für Phase 5 Freigabe

---

## Risiken & Mitigation

| Risiko | Wahrscheinlichkeit | Mitigation |
|--------|-------------------|------------|
| Fix 5.0c hat Bugs | Mittel | Mini-Run vor 48h |
| Trend-Berechnung zu sensibel | Niedrig | Threshold 10% statt 20% |
| Echter Leak wird übersehen | Niedrig | Peak-Alert bleibt (90%) |

---

## Alternative Option (wenn Schritt 2 zu komplex)

**Delegation an Health Checker:**

Der Heartbeat Service sollte `growth_percent` vom Health Checker übernehmen:

```javascript
function updateMetrics(healthResults) {
  // ... andere Updates ...
  
  // Nutze Health Checker Trend statt eigener Berechnung
  const memoryCheck = healthResults.checks.find(c => c.name === 'memory');
  if (memoryCheck && memoryCheck.growth_percent !== undefined) {
    state.metrics.memory_growth_percent = memoryCheck.growth_percent;
  }
  
  // ... Rest wie gehabt ...
}
```

**Vorteil:** Keine duplizierte Logik, Single Source of Truth.  
**Nachteil:** Abhängigkeit zwischen Services erhöht.

---

## Zusammenfassung der Änderungen

| Datei | Zeilen | Änderung |
|-------|--------|----------|
| `heartbeat_service.js` | ~25 | CONFIG erweitern |
| `heartbeat_service.js` | ~30-35 | memoryHistory Array |
| `heartbeat_service.js` | ~420-470 | updateMetrics() komplett neu |

**Commit-Message:**
```
Fix 5.0c: Memory Leak Detection Algorithmus korrigiert

- Ersatz: Peak-to-Start durch Trend-over-Time
- Linear Regression über 6h Fenster
- Startup-Delay: 30 Min vor Alerts
- Threshold zurück auf 10%

Fixes false positives from Fix 5.0b
```

---

## Approval Checklist

**Vor Merge:**
- [ ] Code implementiert (Schritt 1 oder 1+2)
- [ ] Mini-Run (4h) bestanden
- [ ] Keine False-Positives in Logs
- [ ] Report in docs/FIX_50B_TEST_REPORT.md ergänzt

**Nach Merge:**
- [ ] 48h Validation geplant
- [ ] Phase 5.0 GO/NO-GO Entscheidung

---

*Fix 5.0c Design Complete — Ready for Implementation*
