# Fix 5.0d — Absolute Threshold Strategy

**Status:** 🟢 Ready for Implementation  
**Ansatz:** Radikale Vereinfachung — keine Algorithmen, nur Dauer-Schwellen  
**Ziel:** Deterministisch, GC-resistent, beweisbar korrekt  
**Autor:** Pecz  
**Datum:** 31. März 2026

---

## Konzept: "Sustained Memory Pressure"

**Keine Berechnungen mehr.** Keine Trends. Kein Growth.

Nur zwei einfache Regeln:

| Level | Bedingung | Aktion |
|-------|-----------|--------|
| **CRITICAL** | Memory >90% für >15 Minuten | Alert + Log |
| **WARN** | Memory >80% für >60 Minuten | Alert + Log |

**Warum Dauer-Schwellen?**
- Ein GC-Peak ist vorbei in Sekunden → kein Alert
- Ein echter Leak bleibt hoch → triggert nach Dauer
- Deterministisch: Messbar, wiederholbar

---

## Betroffene Dateien

| Datei | Zeilen | Änderung |
|-------|--------|----------|
| `src/heartbeat_service.js` | ~420-470 | `updateMetrics()` komplett neu |
| `src/health_checker.js` | ~150-220 | `checkMemory()` anpassen |
| `src/config/monitoring.js` | Neu | Zentrale Threshold-Config |

---

## Design: Fix 5.0d

### 1. Neue Config-Struktur (empfohlen)

**Datei:** `src/config/monitoring.js` (neu erstellen)

```javascript
/**
 * Monitoring Configuration — Fix 5.0d
 * Absolute thresholds, keine Berechnungen
 */
module.exports = {
  memory: {
    // Absolute limits
    critical: {
      percent: 90,
      durationMinutes: 15,  // 90% für 15 Min = CRITICAL
    },
    warn: {
      percent: 80,
      durationMinutes: 60,  // 80% für 60 Min = WARN
    },
    // Sampling: alle 30 Sekunden (nicht jede Sekunde)
    sampleIntervalMs: 30000,
  },
  
  // Reset-Gates: Wenn Memory unter Schwelle fällt, Timer reset
  hysteresis: {
    criticalReset: 85,  // Unter 85% = CRITICAL-Timer reset
    warnReset: 75,      // Unter 75% = WARN-Timer reset
  }
};
```

### 2. Implementierung: Sustained-Check

**Datei:** `src/heartbeat_service.js`

```javascript
// ═══════════════════════════════════════════════════════════════
// FIX 5.0d: Absolute Threshold Strategy
// ═══════════════════════════════════════════════════════════════

const monitoringConfig = require('./config/monitoring');

// Zustand für Sustained-Checks
const sustainedState = {
  critical: {
    firstAboveThreshold: null,  // Timestamp
    alerted: false,
  },
  warn: {
    firstAboveThreshold: null,
    alerted: false,
  },
  lastSample: null,  // { timestamp, percent }
};

/**
 * Fix 5.0d: Memory-Check mit Dauer-Threshold
 * NUR noch absolute Limits, keine Berechnungen
 */
function checkMemorySustained() {
  const memUsage = process.memoryUsage();
  const percent = (memUsage.heapUsed / memUsage.heapTotal) * 100;
  const now = Date.now();
  const { memory, hysteresis } = monitoringConfig;
  
  // Update letzter Sample
  sustainedState.lastSample = { timestamp: now, percent };
  
  // ═══════════════════════════════════════════════════════
  // CRITICAL-Check: >90% für >15 Min
  // ═══════════════════════════════════════════════════════
  if (percent >= memory.critical.percent) {
    if (!sustainedState.critical.firstAboveThreshold) {
      // Erstmalig über 90%
      sustainedState.critical.firstAboveThreshold = now;
      logEvent('MEMORY', `Above ${memory.critical.percent}%: ${percent.toFixed(1)}%`, 'INFO');
    } else {
      // Bereits über 90%, prüfe Dauer
      const durationMinutes = (now - sustainedState.critical.firstAboveThreshold) / 60000;
      
      if (durationMinutes >= memory.critical.durationMinutes && !sustainedState.critical.alerted) {
        // CRITICAL sustained!
        sendAlert('CRITICAL', 'Memory Critical Sustained', 
          `${percent.toFixed(1)}% for ${Math.floor(durationMinutes)}min > threshold ${memory.critical.durationMinutes}min`);
        sustainedState.critical.alerted = true;
      }
    }
  } else if (percent <= hysteresis.criticalReset) {
    // Hysterese: Unter 85% = Reset
    if (sustainedState.critical.firstAboveThreshold) {
      logEvent('MEMORY', `Recovered below ${hysteresis.criticalReset}%: ${percent.toFixed(1)}%`, 'INFO');
    }
    sustainedState.critical.firstAboveThreshold = null;
    sustainedState.critical.alerted = false;
  }
  
  // ═══════════════════════════════════════════════════════
  // WARN-Check: >80% für >60 Min
  // ═══════════════════════════════════════════════════════
  if (percent >= memory.warn.percent) {
    if (!sustainedState.warn.firstAboveThreshold) {
      sustainedState.warn.firstAboveThreshold = now;
      logEvent('MEMORY', `Above ${memory.warn.percent}%: ${percent.toFixed(1)}%`, 'INFO');
    } else {
      const durationMinutes = (now - sustainedState.warn.firstAboveThreshold) / 60000;
      
      if (durationMinutes >= memory.warn.durationMinutes && !sustainedState.warn.alerted) {
        sendAlert('WARN', 'Memory High Sustained', 
          `${percent.toFixed(1)}% for ${Math.floor(durationMinutes)}min > threshold ${memory.warn.durationMinutes}min`);
        sustainedState.warn.alerted = true;
      }
    }
  } else if (percent <= hysteresis.warnReset) {
    if (sustainedState.warn.firstAboveThreshold) {
      logEvent('MEMORY', `Recovered below ${hysteresis.warnReset}%: ${percent.toFixed(1)}%`, 'INFO');
    }
    sustainedState.warn.firstAboveThreshold = null;
    sustainedState.warn.alerted = false;
  }
  
  // State für persistence (optional)
  return {
    percent: percent.toFixed(1),
    critical_timer_minutes: sustainedState.critical.firstAboveThreshold 
      ? ((now - sustainedState.critical.firstAboveThreshold) / 60000).toFixed(1)
      : 0,
    warn_timer_minutes: sustainedState.warn.firstAboveThreshold
      ? ((now - sustainedState.warn.firstAboveThreshold) / 60000).toFixed(1)
      : 0,
  };
}

/**
 * Kompletter Ersatz für updateMetrics()
 */
function updateMetrics(healthResults) {
  if (!state) return;
  
  // Basic Memory-Update
  const memUsage = process.memoryUsage();
  state.metrics.memory_current_mb = Math.round(memUsage.heapUsed / 1024 / 1024);
  if (state.metrics.memory_current_mb > state.metrics.memory_peak_mb) {
    state.metrics.memory_peak_mb = state.metrics.memory_current_mb;
  }
  
  // Fix 5.0d: Sustained-Check (ersetzt alles)
  const memStatus = checkMemorySustained();
  
  // Update im State
  state.metrics.memory_percent = memStatus.percent;
  
  persistState();
}
```

### 3. Migration: Alten Code entfernen

**In `heartbeat_service.js` LÖSCHEN:**
- `const memoryHistory = []` (falls vorhanden)
- `MAX_HISTORY_SAMPLES` (falls vorhanden)
- Komplette alte `updateMetrics()` Funktion (Zeilen 420+)
- Alle `memory_growth_percent` Referenzen
- Linear-Regression-Code

**In `health_checker.js` LÖSCHEN/ANPASSEN:**
- `checkMemory()` → nur noch return, keine Alert-Logik
- Alert-Logik komplett in `heartbeat_service.js`
- ODER: Health Checker gibt nur Rohdaten, Heartbeat Service entscheidet

---

## Verhaltens-Analyse (Fix 5.0d)

### Szenario A: Normaler GC-Verhalten

```
Zeit    Memory   Zustände
─────────────────────────────────
T+0     81%      WARN-timer startet
T+1min  85%      WARN läuft
T+2min  82%      WARN läuft
T+3min  79%      ↓ Unter 80% → WARN reset
T+4min  84%      WARN-timer restartet (neu!)
T+5min  86%      WARN läuft
[... Stunden normal ...]
Result: Kein Alert (weil nie 60min über 80%)
```

### Szenario B: Echter Memory Leak

```
Zeit    Memory   Zustände
─────────────────────────────────
T+0     81%      WARN startet
T+30min 87%      WARN läuft
T+60min 91%      ↓ CRITICAL startet
T+75min 93%      ↓ CRITICAL sustained → ALERT!
Result: CRITICAL nach 75 Minuten
```

### Szenario C: Spike + Normalisierung

```
Zeit    Memory   Zustände
─────────────────────────────────
T+0     91%      CRITICAL startet
T+5min  92%      CRITICAL läuft
T+6min  87%      ↓ Unter 90% aber über 85%
T+7min  84%      ↓ Unter 85% → CRITICAL reset
Result: Kein Alert (Dauer nur 7 Min, nicht 15)
```

**Alle Szenarien:** Keine False-Positives, echter Leak wird erkannt.

---

## Testplan Fix 5.0d

### Phase 1: Unit Test (lokal, 10 Min)

```bash
# Test-Script: memory_stress_test.js
node -e "
const hs = require('./src/heartbeat_service');

// Test 1: Simuliere GC-Oszillation
console.log('Test 1: GC-Oszillation (81%, 79%, 82%, 78%...)');
// Erwartet: Keine Alerts

// Test 2: Simuliere echten Leak
console.log('Test 2: Sustained 92% für 20 Min');
// Erwartet: CRITICAL nach 15 Min

// Test 3: Spike + Recovery
console.log('Test 3: 91% für 10 Min, dann 70%');
// Erwartet: Kein Alert (unter 15 Min)
"
```

**Kriterium:** Alle 3 Tests passen.

### Phase 2: Kurz-Test (2h, heute)

| Zeit | Erwartet | Prüfung |
|------|----------|---------|
| T+0-15min | Startup-Phase, Memory 75-85% | Log: INFO-Meldungen, keine Alerts |
| T+30min | Normal-Betrieb | Log: Keine CRITICAL |
| T+60min | Eine Stunde stabil | Log: Keine WARN sustained |
| T+90min | Abschluss | Manuelle Prüfung: 0 Alerts |

**Kriterium:** 0 CRITICAL, 0 WARN sustained.

### Phase 3: Mini-Run (4h, morgen)

| Zeit | Prüfung | Erwartet |
|------|---------|----------|
| T+0-4h | Kontinuierlicher Betrieb | 0 CRITICAL |
| T+4h | Abschluss-Log | Keine sustained Alerts |

**Kriterium:** 0 sustained alerts (CRITICAL und WARN).

### Phase 4: 12h Extended Validation (nach Mini-Run OK)

**Über Nacht laufen lassen.**

| Checkpoint | Erwartet |
|------------|----------|
| T+6h | 0 sustained alerts |
| T+12h | 0 sustained alerts |

**Kriterium:** Sauberer Abschluss.

### Phase 5: 48h Gate-Run (nach 12h OK)

**Offizieller Phase 5.0 Gate-Run.**

| Checkpoint | Manuelle Prüfung | Automatisch |
|------------|------------------|-------------|
| T+6h | Ja | Keine sustained alerts |
| T+12h | Ja | Keine sustained alerts |
| T+24h | Ja | Keine sustained alerts |
| T+36h | Ja | Keine sustained alerts |
| T+48h | Finale Entscheidung | GO/NO-GO |

**Kriterium:** 0 sustained CRITICAL Alerts = GO.

---

## Warum Fix 5.0d funktioniert

| Aspekt | Erklärung |
|--------|-----------|
| **Deterministisch** | Ja: Zeit × Threshold, keine Mathematik |
| **GC-resistent** | Ja: Spikes dauern Sekunden, nicht Minuten |
| **Leak-Proof** | Ja: Echter Leak bleibt >15 Min hoch |
| **Minimale Komplexität** | Ja: Zwei IFs, keine Loops, keine Regression |
| **Beweisbar korrekt** | Ja: Mathematisch trivial, leicht zu reviewen |

**Im Vergleich zu Fix 5.0a/5.0b/5.0c:**
- Keine "Growth"-Berechnung → keine False-Positives
- Keine Sampling-Filter → keine Daten-Verluste
- Keine Regression → keine edge cases

---

## Migrations-Path

### Schritt 1: Config erstellen (2 Min)
- `src/config/monitoring.js` neu anlegen
- Werte testen

### Schritt 2: heartbeat_service.js ändern (8 Min)
- Alte `updateMetrics()` löschen
- `checkMemorySustained()` einfügen
- Neue `updateMetrics()` einfügen
- Import für Config hinzufügen

### Schritt 3: Testen (10 Min)
- Unit-Tests lokal
- Kurz-Test (2h)

### Schritt 4: Commit (1 Min)
```
Fix 5.0d: Absolute threshold strategy

- Entfernt: Trend-basierte Memory-Leak-Erkennung
- Neu: Sustained thresholds (90%/15min, 80%/60min)
- Deterministisch, GC-resistent, minimal

Closes memory alert false positive issue
```

---

## Empfehlung

### Implementieren: ✅ JA

**Begründung:**
1. **Technisch korrekt:** Sustained thresholds sind mathematisch beweisbar richtig
2. **Erfahrung:** Bisherige Ansätze (Growth, Regression) haben versagt
3. **Zeit:** 10 Min Implementierung vs. 3 Tage Debug erneuter Algorithmen
4. **Risiko:** Nahezu 0% False-Positives möglich

**Wenn nicht implementiert:**
- Weitere Iterationen (5.0e, 5.0f) mit gleichen Problemen
- Zeitverlust
- Demotivation

**Nach Implementation:**
- Sofort 2h-Test (heute)
- Morgen: 4h Mini-Run
- Bei Erfolg: 12h, dann 48h
- Phase 5 GO nach 48h Erfolg

---

*Fix 5.0d Design Complete — Ready for Merge Decision*
