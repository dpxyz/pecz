# Phase 7 – Foundry Architecture (BUILD IN PROGRESS)

**Status:** 🔨 BUILD – V1 Foundry Pipeline wird gebaut
**Start:** 2026-04-18
**Beschluss:** OpenClaw Foundry – siehe FOUNDRY_CHARTER.md

---

## Was passiert ist

1. Phase 7 v1 angeblich "audit-fest abgeschlossen" → Re-Evaluation: alle 3 Strategien FAIL
2. Scorecard-Verdict PASS war zu großzügig (TWEAK ist keine Entscheidung)
3. Foundry Charter verfasst als Gründungsurkunde
4. Konzeptfreigabe durch Dave am 2026-04-18
5. **V1 Build gestartet**

---

## Foundry V1 Architecture

```
spec.yaml (Wahrheit)
    ↓
generator.py → Gemma4:31b liest Spec → 3 Kandidaten als DSL-JSON
    ↓
strategy_dsl.py → Syntax-Validierung (DSL-Regeln)
    ↓
dsl_translator.py → DSL-JSON → strategy_func(df, params)
    ↓
backtest_engine.py → Backtest mit Polars + Fees/Slippage
    ↓
walk_forward.py → Walk-Forward Analysis (3 Windows)
    ↓
gate_evaluator.py → 5 harte Gates, binär PASS/FAIL
    ↓
Discord: "1 BACKTEST_PASS, 2 FAIL" oder "0 PASS, 3 FAIL"
```

### Semantik
- **PASS = BACKTEST_PASS** = Strategie gefunden + im Backtest validiert, NICHT deployed
- **FAIL** = verworfen, keine manuelle Rettung
- Paper/Shadow Trading = V2 Baustein, nicht Voraussetzung

### Pipeline-Dateien (V1)

| Datei | Funktion | Status |
|-------|----------|--------|
| `spec.yaml` | Spezifikation (Wahrheit) | ✅ Aktualisiert mit Fees + Data |
| `strategy_dsl.py` | DSL-Definition + Validierung | ✅ Vorhanden |
| `generator.py` | Gemma4-Generator | ✅ Vorhanden |
| `dsl_translator.py` | DSL-JSON → strategy_func | ✅ **NEU gebaut** |
| `backtest_engine.py` | Polars-Backtest | ✅ Vorhanden |
| `walk_forward.py` | Walk-Forward Analysis | ✅ Vorhanden |
| `gate_evaluator.py` | 5 Gates, binäre Verdicts | ✅ Vorhanden |
| `evolution_runner.py` | Orchestrierung | ✅ **NEU: v2.0 mit echtem Backtest** |

### Offen (vor erstem Run)

- [ ] Daten-Pfad verifizieren – `DATA_PATH` zeigt auf `/research/backtest/data/` – existieren die Parquet-Dateien?
- [ ] Walk-Forward Integration testen – `WalkForwardAnalysis` API-Check
- [ ] Discord-Webhook für Report – Channel konfigurieren
- [ ] Erster Foundry-Run: `python3 evolution_runner.py --mock` → `python3 evolution_runner.py`
- [ ] Cron-Job: Wöchentlicher Foundry-Run (z.B. Sonntag 10:00 UTC)

### Offen (V2)

- [ ] Paper/Shadow Trading Interface
- [ ] Promoted-Status statt nur BACKTEST_PASS
- [ ] Live-Feed-Handler für Paper Trading
- [ ] Slippage-Modell verfeinern

---

## Foundry-Prinzipien (FOUNDRY_CHARTER.md)

1. Wöchentlicher, vollautomatischer Prozess
2. KI entwirft Strategien, bewertet nie selbst
3. Spec ist Wahrheit
4. Binäre Verdicts: PASS oder FAIL
5. PASS → kontrolliert promoted (V2: Paper/Shadow)
6. FAIL → verworfen, nicht gerettet
7. Nutzerprodukt = 1 Discord-Nachricht
8. Innovation durch Spec + Gates, nicht mehr KI
9. Trennung von Generierung und Bewertung
10. Strategy Factory, keine Spielwiese

---

## Historie

- **2026-04-18:** Phase 7 RE-OPENED, Foundry Charter, Konzeptphase
- **2026-04-18:** V1 Build gestartet: dsl_translator.py, evolution_runner.py v2.0, spec.yaml erweitert
- **Nächster Schritt:** Daten verifizieren, Mock-Run, dann echter Foundry-Run