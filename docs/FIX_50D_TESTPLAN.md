# Testplan: Fix 5.0d Absolute Threshold Strategy

**Zweck:** Validierung der neuen Memory-Monitoring-Logik  
**Dauer:** 2 Tage (statt ursprünglich geplanter 3-4 Tage bei Fix 5.0c)  
**Ansatz:** Inkrementelle Validierung, frühes Erkennen von Problemen

---

## Übersicht

| Phase | Dauer | Ziel | Go/No-Go Kriterium |
|-------|-------|------|-------------------|
| **1** | 10 Min | Unit Tests | 3/3 Tests bestehen |
| **2** | 2h | Kurz-Test (heute) | 0 sustained alerts |
| **3** | 4h | Mini-Run (morgen früh) | 0 sustained alerts |
| **4** | 12h | Extended (morgen Nacht) | 0 sustained alerts |
| **5** | 48h | Gate-Run | Sustained Critical <1 = GO |

**Abbruch-Kriterien (jederzeit):**
- >1 sustained CRITICAL Alert → Auto-Abort
- Manuelle Inspektion zeigt Anomalie → Abort

---

## Phase 1: Unit Tests (10 Min)

**Ort:** Lokal, Entwicklermaschine  
**Tool:** Node.js Script  
**Datei:** `tests/memory_threshold_unit.test.js`

### Test 1: GC-Oszillation (Anti-False-Positive)
```javascript
// Simuliere 100 Samples: 81%, 79%, 82%, 78%, 81%, ...
// Über 70 Minuten (4.2h in Echtzeit beschleunigt)
// Erwartet: 0 sustained Alerts
```
**Resultat:** ✅ PASS wenn 0 CRITICAL, 0 WARN sustained

---

### Test 2: Echter Leak (Leak-Detection)
```javascript
// Simuliere: 75% → 95% über 20 Min
// Halte 95% für 20 Min
// Erwartet: CRITICAL nach 15 Min
```
**Resultat:** ✅ PASS wenn CRITICAL nach ~15 Min

---

### Test 3: Spike + Recovery (Hysterese)
```javascript
// 91% für 10 Min → Recovery auf 70%
// 10 Min sind unter 15-Min-Threshold
// Erwartet: Kein Alert
```
**Resultat:** ✅ PASS wenn 0 CRITICAL

---

### Phase 1 Abnahme
**Go Kriterium:** Alle 3 Tests PASS  
**No-Go:** Ein Test FAIL → Fix revisionieren  
**Dauer:** 10 Min

---

## Phase 2: Kurz-Test (2h)

**Ort:** Produktions-Ähnliche Umgebung (VPS, Docker)  
**Start:** Heute, sobald Phase 1 Go  
**Dauer:** 2 Stunden  
**Monitoring:** Manuelle Prüfung alle 30 Min

### Timeline

| Zeit | Aktion | Prüfung |
|------|--------|---------|
| T+0 | Start `runtime_validation/runner.js` | System startet, Logs zeigen INFO |
| T+30min | Erste Prüfung | Memory <80%, Logs: keine Alerts |
| T+60min | Zweite Prüfung | Memory schwankt 75-85%, keine sustained Alerts |
| T+90min | Dritte Prüfung | Memory stabil, 0 sustained CRITICAL |
| T+120min | Abschluss | Log-Review: 0 sustained CRITICAL, 0 sustained WARN |

### Log-Muster (erwartet)
```
[INFO] Memory: 81.2% [timer: warn=5min, crit=0min]
[INFO] Memory: 79.1% [timer: reset warn, reset crit]
[INFO] Memory: 82.3% [timer: warn=2min, crit=0min]
... (niemals warn≥60 oder crit≥15)
```

### Phase 2 Abnahme
**Go Kriterium:** 
- 0 sustained CRITICAL Alerts (90%/15min)
- 0 sustained WARN Alerts (80%/60min)
- System läuft durch (kein Crash)

**No-Go:**
- ≥1 sustained Alert
- Crash oder Error

**Dauer:** 2h + 10 Min Review

---

## Phase 3: Mini-Run (4h)

**Ort:** VPS, Docker  
**Zeitfenster:** Morgen früh (z.B. 08:00-12:00 CET)  
**Dauer:** 4 Stunden  
**Monitoring:** Automatisch + manuelle Prüfung T+2h, T+4h

### Setup
```bash
cd forward_v5/forward_v5
export EVENT_STORE_PATH=./runtime/event_store.db
node runtime_validation/runner.js
```

### Timeline

| Zeit | Status | Aktion |
|------|--------|--------|
| T+0 | 🟢 Start | System bootet, Pre-flight checks |
| T+2h | 🟡 Checkpoint | Manuelle Prüfung: Logs durchsehen |
| T+4h | 🟢 Ende | Auto-abschalten, Report generieren |

### Checkpoint-T+2h Prüfliste
- [ ] Memory schwankt normal (75-85%)
- [ ] Keine CRITICAL Alerts
- [ ] Event Store: Größe wächst nicht ungebremst
- [ ] Circuit Breaker: CLOSED
- [ ] Health Checks: OK oder WARN, nie CRITICAL

### Phase 3 Abnahme
**Go Kriterium:**
- 0 sustained Alerts (CRITICAL + WARN)
- Memory überwiegend <85%
- Keine ungeklärten Errors

**No-Go:**
- ≥1 sustained Alert
- Memory durchgehend >90%
- Health Checks FAIL

**Dauer:** 4h + 15 Min Review

---

## Phase 4: Extended Validation (12h)

**Ort:** VPS, Docker  
**Zeitfenster:** Morgen Nachmittag bis Nacht (z.B. 14:00-02:00)  
**Dauer:** 12 Stunden  
**Monitoring:** Automatisch, manuelle Prüfungen nur bei Alarm

### Speziell für Fix 5.0d
Da Fix 5.0d deterministisch ist:
- Wenn Phase 3 (4h) sauber → Wahrscheinlichkeit für Phase 4 Fehler < 5%

### Timeline

| Zeit | Bedeutung |
|------|-----------|
| T+0 | Start (automatisch) |
| T+6h | Mid-Point-Check (manuell wenn verfügbar, sonst automatisch) |
| T+12h | Abschluss + Report |

### Auto-Abort-Trigger
```
IF sustained_critical_count > 0:
  ABORT_RUN()
  LOG("Phase 4 aborted: sustained CRITICAL detected")
```

### Phase 4 Abnahme
**Go Kriterium:**
- 0 sustained CRITICAL Alerts
- ≤2 sustained WARN Alerts (tolerierbar, nicht kritisch)
- System läuft durch ohne Restart

**No-Go:**
- ≥1 sustained CRITICAL
- System Crash
- Ungeklärter Fehler

**Dauer:** 12h + 20 Min Review

---

## Phase 5: 48h Gate-Run (Offiziell)

**Ort:** VPS, Docker  
**Zeitfenster:** Nach Phase 4 Go, z.B. Dienstag (wenn heute Montag)  
**Dauer:** 48 Stunden  
**Monitoring:** Automatisch, manuelle Checkpoints alle 6h

### Checkpoint-Strategie

| Checkpoint | Manuelle Prüfung | Automatische Prüfung |
|------------|------------------|----------------------|
| T+6h | Streng | sustained_alerts == 0 |
| T+12h | Streng | sustained_alerts == 0 |
| T+18h | Optional | sustained_alerts == 0 |
| T+24h | Streng | sustained_alerts == 0 |
| T+30h | Optional | sustained_alerts == 0 |
| T+36h | Streng | sustained_alerts == 0 |
| T+42h | Optional | sustained_alerts == 0 |
| T+48h | Finale GO/NO-GO | Auto-Entscheidung |

### Strenge Prüfung (T+6h, T+12h, T+24h, T+36h, T+48h)
```
1. Log-Datei öffnen: forward_v5/runtime_validation/logs/heartbeat.log
2. Suchen nach "CRITICAL sustained" oder "CRITICAL Memory"
3. Wenn gefunden → NO-GO sofort
4. Memory-Trend prüfen (sollte oszillieren, nicht steigen)
5. Event Store Größe prüfen (sollte linear wachsen)
```

### Finale GO/NO-GO Entscheidung (T+48h)

**Automatische Kriterien:**
| Kriterium | GO | NO-GO |
|-----------|-----|-------|
| Sustained CRITICAL | 0 | ≥1 |
| Sustained WARN | ≤2 | >2 |
| System Crash | Nein | Ja |
| Health Check FAIL | 0 | ≥1 |
| Memory über 90% | Nie | Sustained |

**Manuelle Überprüfung:**
- Logs durchlesen
- Anomalien erklären (falls vorhanden)
- Entscheidung bestätigen

### Phase 5 Ergebnisse

**Bei GO:**
- Phase 5.0 ist COMPLETE
- Freigabe für Phase 5.1 (Systemd Integration)
- Mission Control aktualisieren

**Bei NO-GO:**
- Root Cause Analysis
- Fix 5.0e (falls nötig)
- Keine Verzweiflung — wir lernen

---

## Zusammenfassung: Timeline

| Tag | Phase | Dauer | Ergebnis |
|-----|-------|-------|----------|
| **Heute** | Unit + Kurz | 10 Min + 2h | Schnelles Vertrauen |
| **Morgen** | Mini-Run | 4h | Stabilitäts-Beweis |
| **Übermorgen** | Extended | 12h | Übernacht-Test |
| **Donnerstag** | Gate-Run | 48h | Phase 5 GO/NO-GO |

**Gesamtdauer bis Entscheidung:** ~4-5 Tage

**Alternative (aggressiv):**
- Unit (heute)
- Mini-Run (morgen)
- Direkt 48h (übermorgen)
**Nur wenn:** Unit + Mini-Run absolut sauber (0 sustained Alerts)

---

## Risiko-Mitigation

| Risiko | Wahrscheinlichkeit | Mitigation |
|--------|-------------------|------------|
| Fix 5.0d hat Bugs | Niedrig | Unit Tests |
| False-Positives trotzdem | Sehr niedrig | Phase 2 (2h) erkennt früh |
| 48h Run fällt spät | Niedrig | Checkpoints alle 6h |
| System instabil | Niedrig | 48h ist bekannt solide |

**Vertrauenslevel bei Fix 5.0d:** 90% (vs. 50% bei Fix 5.0c)

---

## Commit-Vorgang

### Nach Phase 1 (Unit)
```bash
git add src/heartbeat_service.js src/config/monitoring.js
git commit -m "Fix 5.0d: Absolute threshold memory monitoring

- Entfernt: Trend-basierte Berechnung
- Neu: Sustained thresholds (90%/15min, 80%/60min)
- Deterministisch, GC-resistent, minimal
- Unit tests: 3/3 PASS"
```

### Nach Phase 2 (Kurz-Test)
```
Update: README.md mit Test-Ergebnis (2h, 0 sustained alerts)
```

### Nach Phase 5 (48h)
```
FINAL: Phase 5.0 complete — Memory monitoring validated
Gate-Run: 48h, 0 sustained CRITICAL, 0 sustained WARN
Result: GO for Phase 5.1
```

---

*Testplan Fix 5.0d Complete — Ready for Execution*
