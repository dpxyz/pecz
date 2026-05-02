# Edge Discovery — Prozessregeln

## Die 6 Regeln

### 1. EINE Hypothese pro Sprint
- Nie mehr als 1 Hypothese gleichzeitig testen
- Sprint = 1 Tag Setup + 1 Tag Backtest + 1 Tag Auswertung
- Ergebnis: PASS, FAIL, oder INCONCLUSIVE
- INCONCLUSIVE = FAIL. Keine "vielleicht mit anderem Threshold"

### 2. Keine Parameter-Optimierung
- Ein Threshold pro Variable. Nicht: "z<-1, z<-1.2, z<-1.3, z<-1.5"
- Wenn die Hypothese mit z<-1 nicht funktioniert, funktioniert sie mit z<-1.3 auch nicht
- Threshold-Optimierung = Overfitting. Immer.

### 3. WF Gate ist final
- ≥4/6 OOS windows profitabel, cum PnL > 0, ≥30 Trades
- FAIL = tote Hypothese, nicht "nochmal mit anderem Filter"
- Keine "aber im letzten Window war es profitabel"

### 4. Neuer Faktor = neue Hypothese
- FGI, DXY, OI, Volume = verschiedene Hypothesen, nicht Filter zum Draufpacken
- HYP-03 (OI) ist eine eigene Hypothese, kein "Verbesserung" von V2
- Das verhindert Filter-Kombinatorik (16 Varianten × 6 Assets = 96 Tests = Overfitting)

### 5. Doku vor Code
- Bevor ich Code schreibe: Hypothese aufschreiben (EDGE_DISCOVERY.md)
- Nach dem Test: Ergebnis eintragen, inklusive Per-Window-Detail
- Dave entscheidet ob weiter, nicht ich

### 6. Kill-Kriterium
- Nach Phase 2 (6 Hypothesen): Wenn ≤1 PASS → Fundamentale Frage stellen
- "Ist der Markt für diesen Ansatz effizient?" statt "Noch ein Threshold versuchen"
- Besser 3 Wochen ehrliche Arbeit als 3 Monate Overfitting

---

## Sprint-Template

```
SPRINT-XX: HYP-XX "Name"
Datum: YYYY-MM-DD

Entry-Regel: [exakt]
Exit-Regel: 24h time-based, SL 4%
Assets: BTC, ETH, SOL
Zeitrahmen: 1h oder 4h
Gate: ≥4/6 OOS, cum > 0, ≥30 trades

Ergebnis:
- OOS Windows: X/6
- Cum PnL: +X.XX%
- Trades: XXX
- Win Rate: XX.X%
- Status: PASS / FAIL / INCONCLUSIVE

Per-Window:
W1: n=XX, cum=+XX.XX%, WR=XX.X%
...

Nächster Schritt: [nächste Hypothese oder STOP]
```

---

## Was wir NICHT tun

- ❌ Weitere Foundry-Iterationen auf 1h Mean Reversion
- ❌ Filter-Kombinationen (FGI+DXY+z Threshold = Overfitting)
- ❌ "Noch ein Threshold" (z<-1.3, z<-1.7)
- ❌ Threshold-Sweeps als "neue Hypothese" tarnen
- ❌ Asset-Hopping (1 Asset funktioniert, 5 nicht = Edge ist Asset-spezifisch)

## Was wir TUN

- ✅ Echte neue Faktoren testen (OI, Volume, Momentum, 4h)
- ✅ Prozyklische Hypothesen (Short, Trend Continuation)
- ✅ Verschiedene Zeitrahmen (4h, daily)
- ✅ Ehrliche FAIL-Entscheidungen
- ✅ Dave entscheidet, nicht der Backtest