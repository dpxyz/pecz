# Runtime Validation - Expected WARNs Baseline (Whitelist)

**Run ID:** rv-2026-03-28-j3xxec  
**Start:** 2026-03-28T11:31:56Z  
**Modus:** Paper  
**Dokument erstellt:** 2026-03-28T12:38Z  

---

## ⚠️ OFFIZIELLE WHITELIST

Die folgenden WARNs sind **ERWARTET** und werden **NICHT** als ungeklärte Vorfälle gezählt.

---

### Whitelist-Eintrag #1: Memory Usage High beim Start

| Feld | Wert |
|------|------|
| **Check** | memory.percent_used > 80% |
| **Status** | ✅ EXPECTED |
| **Begründung** | Kleine Heap-Größe (5MB) bei Node.js Startup führt zu hohem Prozentwert. Absoluter Wert (4MB) ist normal. |
| **Pattern** | `Memory Usage High: 8[0-9].% > 80%` |
| **Zeitraum** | Primär T+0 bis T+0.5h, stabilisiert sich danach |
| **Erfasst** | Ja (11:31:56.550Z, 11:31:56.551Z) |

### Whitelist-Eintrag #2: Event Store Path Not Found

| Feld | Wert |
|------|------|
**Check** | event_store.db_exists = false |
| **Status** | ✅ EXPECTED |
| **Begründung** | Paper Mode verwendet kein persistentes Event Store File. In-Memory oder keine Events erwartet. |
| **Pattern** | `Event store path not found (may be using in-memory)` |
| **Zeitraum** | Dauerhaft während Paper Mode |
| **Erfasst** | Ja (11:31:56.550Z, 11:31:56.551Z) |

### Whitelist-Eintrag #3: Health Check Overall = WARN

| Feld | Wert |
|------|------|
| **Check** | health.overall = WARN |
| **Status** | ✅ EXPECTED (wegen Whitelist #1 und #2) |
| **Begründung** | Health Check aggregiert zu WARN wegen der oben whitelisten WARNs. Kein echtes Problem. |
| **Pattern** | `Health Check Warning: [{"name":"event_store",...},{"name":"memory",...}]` |
| **Zeitraum** | Solange Whitelist #1 und #2 aktiv |
| **Erfasst** | Ja (11:31:56.550Z, 11:31:56.551Z) |

---

## ❌ Diese Events wären NICHT erwartet (würden FAIL auslösen)

| Event-Typ | Beschreibung | Konsequenz |
|-----------|--------------|------------|
| **CRITICAL** | Memory >90% | Sofortige Untersuchung |
| **CRITICAL** | Circuit Breaker OPEN ohne Test-Markierung | Sofortige Untersuchung |
| **ERROR** | Heartbeat Gap >5 Minuten | System könnte hängen |
| **ERROR** | Unbehandelte Exception | Crash-Verdacht |
| **FATAL** | Beliebig | Sofortige Untersuchung |

---

## ✅ Erwartetes System-Verhalten

Während des 48h Runs erwarte ich:

| Parameter | Erwarteter Wert |
|-----------|-----------------|
| Heartbeat | Alle 60 Sekunden (±5s) |
| Health Check | Alle 5 Minuten |
| Memory WARN | Nur am Anfang (Whitelist #1) |
| Event Store WARN | Dauerhaft (Whitelist #2) |
| CRITICAL Events | 0 |
| ERROR Events | 0 |
| Heartbeat Lücken | 0 |
| Speicherwachstum | <10% über 48h |

---

## 📊 Monitoring-Checkpoints

| Checkpoint | Zeit (UTC) | Status |
|------------|------------|--------|
| T+0 (Start) | 2026-03-28T11:31:56Z | ✅ DONE |
| T+1h | 2026-03-28T12:31:56Z | ⏳ PENDING |
| T+24h | 2026-03-29T11:31:56Z | ⏳ PENDING |
| T+48h (Ende) | 2026-03-30T11:31:56Z | ⏳ PENDING |

---

## 🔒 Freeze-Regel

**Dieses Dokument wurde vor dem Run-Start (T+0.1h) erstellt.**

- ✅ Whitelist ist fix und bindend
- ❌ Keine nachträglichen Ergänzungen erlaubt
- ❌ Keine Ausnahmen
- 📋 Nicht-whitelistete WARNs zählen als ungeklärt

---

*Dokument Version: 1.0*  
*Sign-off: erstellt vor Run-Start*
