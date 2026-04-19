# Phase 7 v3 – Inverse Design Stack
# Design: Jobs + Musk Principles (wirklich)
# Date: 2026-04-18

## Warum v2 nicht innovativ war

v2 war ein konventioneller Gate-Evaluator. Standard Quant-Work.
Das ist sicher, aber nicht innovativ. Innovation heißt:
Das Problem von der anderen Seite lösen.

## Das Prinzip: Inverse Design

Statt: Strategie → Test → hoffentlich PASS
Neu:   PASS-Kriterien → Generiere Strategien die PASSen

Analogie:
- SpaceX: Spezifikation zuerst, Design danach
- iPhone: Erlebnis zuerst, Hardware danach
- Pecz: Gates zuerst, Strategie danach

---

## Der Stack

### Schicht 1: Specification Layer (Mensch)

Der Mensch definiert WAS er will, nicht WIE:

```yaml
spec:
  target_return_pct: 5.0        # Annualisiert
  max_drawdown_pct: 15.0        # Hartes Limit
  min_trades: 50                 # Statistische Signifikanz
  max_consecutive_losses: 8     # Psychologisch tragbar
  resource_limit_mb: 256        # VPS-Konstraint
  asset_universe: [BTC, ETH, SOL]
  timeframe: 1h                 # Was der VPS schafft
```

### Schicht 2: Generation Layer (KI)

Die KI bekommt die Spec und generiert Strategie-KANDIDATEN:

```
Prompt: "Du hast folgende Spec: {spec}. 
Generiere 5 Strategie-Kandidaten als parameterisierte JSON-Configs.
Jeder Kandidat MUSS die Spec erfüllen können – baue keine Strategie,
die von vornherein gegen die Spec verstößt."
```

Die KI ist jetzt **Architekt**, nicht Richter.
Sie generiert mit dem Ziel, nicht um zu urteilen.

### Schicht 3: Validation Layer (Code, nicht KI)

Backtest-Runner nimmt Kandidaten → Backtest → Gate-Check:

```python
def validate(candidate, spec):
    results = backtest(candidate)
    gates = check_gates(results, spec)
    if all(gates.passed):
        return PASS, results
    else:
        return FAIL, gates.failed  # → zurück zu Schicht 2 mit Feedback
```

Keine KI im Loop. Code prüft Code. Objektiv.

### Schicht 4: Evolution Layer (Automatisch)

FAIL → Feedback → KI improved → Re-Test:

```
Kandidat A → Backtest → FAIL (G2: DD 22% > 15%)
  → Feedback an KI: "DD zu hoch, reduziere Positionsgröße oder engerer Stop"
  → KI generiert A' mit angepassten Params
  → Backtest → FAIL (G1: Return 1.2% < 5%)
  → Feedback: "Return zu niedrig, weiterer Asset oder längere Haltedauer"
  → KI generiert A'' 
  → Backtest → PASS
```

Max 5 Iterationen. Dann: Strategie stirbt, nächste Kandidatin.

### Schicht 5: Live Guardian (Nach dem PASS)

Einmal PASS reicht nicht. Live-Überwachung:

```
Strategie live → Performance-Monitor → 
  Wenn Live-Return < Spec-Return * 0.5 über 7 Tage → WARN
  Wenn Live-DD > Spec-DD → KILL sofort
  Wenn Live-PF < 1.2 über 14 Tage → KILL
```

Kein "vielleicht geht es wieder". Maschine entscheidet.

---

## Was sich JETZT wirklich ändert

| Aspekt | v1 (alt) | v2 (Gates) | v3 (Inverse Design) |
|--------|----------|------------|---------------------|
| Wer generiert? | Mensch | Mensch | **KI** |
| Wer entscheidet? | KI | Gates | **Gates + Evolution** |
| Wer verbessert? | Mensch | Mensch | **KI (automatisch)** |
| Trial & Error | Manuell | Manuell | **Maschinell, 5 Iterationen** |
| Strategie-Fluss | Zufall → Test | Zufall → Gates | **Spec → Generate → Validate → Evolve** |
| Zeitaufwand | Tage | Stunden | **Minuten** |
| TWEAK-Verdict | Ja | Nein | **Existiert nicht** |
| KI-Rolle | Richter | Arzt | **Architekt** |

---

## KI-Rolle im Detail

### v1: KI als Richter ❌
"Ich bewerte deine Strategie. TWEAK."
→ Subjektiv, inkonsistent

### v2: KI als Arzt ❌  
"Gates sagen FAIL. Ich erkläre warum."
→ Hilfreich, aber Mensch muss handeln

### v3: KI als Architekt ✅
"Ich kenne die Spec. Ich generiere Strategien die passen.
Wenn sie nicht passen, verbessere ich sie automatisch."
→ Kreativ UND diszipliniert. Generiert mit Ziel.

Die KI ist nicht mehr nachgelagert – sie ist **am Anfang**.
Sie ist der Architekt, der weiß was das Gebäude tragen muss,
bevor er den ersten Stein legt.

---

## Konkreter Ablauf

```
1. Mensch definiert Spec (5 Minuten)
2. KI generiert 5 Kandidaten (2 Minuten)
3. Backtest-Runner testet alle 5 (10 Minuten)
4. Gates prüfen automatisch (< 1 Sekunde)
5. FAIL-Kandidaten → Feedback → KI improved (3 Minuten)
6. Repeat bis PASS oder 5 Iterationen (max 30 Minuten)
7. PASS-Kandidat → Paper Trading
8. Live Guardian überwacht ab Tag 1
```

**Gesamtzeit: Max 30 Minuten statt Tage.**

---

## Was wir bauen müssen

1. **spec.yaml** – Menschliche Spezifikation
2. **generator.py** – KI-gestützter Strategie-Generator (Gemma4)
3. **gate_evaluator.py** – Harte Gate-Prüfung (Code, keine KI)
4. **evolution_loop.py** – Automatischer FAIL→Improve→Re-test Cycle
5. **live_guardian.py** – Echtzeit-Überwachung nach dem PASS

5 Module. Keine KI im Verdict. KI im Design.

---

## Warum das innovativ ist

1. **Spec-first:** Wir definieren das Ziel, nicht den Weg
2. **KI als Architekt:** Generativ statt evaluativ
3. **Maschinelles Evolution:** 5 Iterationen in Minuten statt Tage
4. **Code als Wahrheit:** Gates lügen nicht, KI nicht nötig im Urteil
5. **Live Guardian:** Strategie stirbt sofort wenn sie die Spec bricht

Das ist was Musk meint: "The best process is no process."
Und was Jobs meint: "Start with the experience, work backwards to the technology."

Hier: Start with the Spec, work backwards to the Strategy.