# Phase 7 – Inverse Design v0.1
# Minimal viable stack: Spec → DSL → Evaluator → 5 Iterationen

## Was wir bauen (und was NICHT)

### ✅ v0.1 Scope
- Eine Spec-Datei (YAML)
- Eine kleine DSL für Strategie-Kandidaten
- Ein harter Gate-Evaluator (Python, keine KI)
- KI generiert Kandidaten aus Spec (Gemma4)
- Automatische 5 Iterationen pro Lauf
- Jede Iteration auditierbar (Log + JSON)

### ❌ NICHT in v0.1
- Kein offener "LLM schreibt alles" Loop
- Kein Live Guardian (Phase 8+)
- Keine automatische Paper-Trading-Einbindung
- Kein Evolution-Loop über mehrere Tage
- Keine Multi-Asset-Generation

---

## Architektur v0.1

```
spec.yaml
    ↓
generator.py → KI (Gemma4) liest Spec, generiert Kandidaten im DSL-Format
    ↓
evaluator.py → Harte Gates, keine KI. Binär: PASS/FAIL
    ↓
Wenn FAIL → Feedback-JSON → zurück zu generator.py (gleiche Spec, Feedback dazu)
    ↓
Max 5 Iterationen → Ergebnis-Log
```

### Kontrollpunkte

1. **Mensch schreibt Spec** → kein KI-Einfluss
2. **KI generiert Kandidaten** → aber im DSL-Format, nicht freier Code
3. **Evaluator ist reiner Code** → keine KI im Urteil
4. **Feedback-Loop ist begrenzt** → 5 Iterationen, dann Stop
5. **Alles auditierbar** → Jede Iteration hat Log + JSON

---

## Dateien

```
research/
├── spec.yaml              # Menschliche Spezifikation
├── strategy_dsl.py        # DSL-Definition + Validierung
├── gate_evaluator.py      # 5 Gates, harte Schwellen
├── generator.py           # KI-gestützter Kandidaten-Generator
├── evolution_runner.py    # Orchestriert: Generate → Evaluate → Feedback → Repeat
└── runs/                   # Audit-Logs pro Lauf
    └── run_YYYYMMDD_HHMM/
        ├── spec_used.yaml
        ├── iteration_1/
        │   ├── candidate.json
        │   ├── backtest_result.json
        │   └── gate_result.json
        ├── iteration_2/
        │   └── ...
        └── summary.json    # Endresultat: PASS/FAIL nach max 5 Iter
```

---

## Nächster Schritt

1. spec.yaml definieren (zusammen mit Dave)
2. strategy_dsl.py bauen
3. gate_evaluator.py bauen
4. generator.py bauen (Gemma4)
5. evolution_runner.py bauen
6. Testlauf mit bestehender mean_reversion_panic Spec