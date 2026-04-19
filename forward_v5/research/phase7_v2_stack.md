# Phase 7 v2 – Strategy Lab Stack
# Design: Jobs + Musk Principles
# Date: 2026-04-18
# Status: DRAFT

## Design-Prinzipien

1. **EINE Wahrheit:** Scorecard ist die Autorität. Keine KI-Korrektur nötig.
2. **Binäre Verdicts:** PASS oder FAIL. Kein TWEAK. Ship or kill.
3. **First Principles:** Was macht eine Strategie live-tauglich?
   - Sie macht Geld (Return > Risk-Free Rate)
   - Sie verliert nicht zu viel (Drawdown begrenzt)
   - Sie ist robust (Walk-Forward bestätigt)
   - Sie läuft auf dem VPS (Ressourcen im Limit)
4. **Delete the unnecessary:** Keine Soft-Targets, keine "maybe" Verdicts,
   keine KI-Überschreibung. Die Harte Gate-Logik macht das Urteil.
5. **Automatisch:** Wenn eine Strategie FAILt, stirbt sie sofort.
   Wenn sie PASSed, geht sie direkt ins Paper Trading. Kein Manuell.

---

## Gate-System (Harte Schwellen)

### G1: Profitability Gate (MUSS PASS für PASS)
- Net Return ≥ 2.0% (annualisiert)
- Profit Factor ≥ 1.5
- Expectancy > 0 (strikt > 0, nicht ≥ 0)

### G2: Risk Gate (MUSS PASS für PASS)
- Max Drawdown ≤ 20%
- Return/Drawdown Ratio ≥ 0.15 (z.B. 3% Return / 20% DD = 0.15)
- Max Consecutive Losses ≤ 10

### G3: Robustness Gate (MUSS PASS für PASS)
- Walk-Forward: ≥ 2 von 3 Windows profitabel
- WF Degradation ≤ 40% (vs. In-Sample)
- Trade Count ≥ 30 (statistische Signifikanz)

### G4: VPS Resource Gate (MUSS PASS für PASS)
- Memory Peak ≤ 256 MB
- Execution Time ≤ 30s pro Run
- CPU Average ≤ 50%

### G5: Guardrail Gate (MUSS PASS für PASS)
- Parameter-Kombinationen ≤ 50
- Assets ≤ 3
- Keine exotischen Dependencies

---

## Verdict-Logik

```
IF G1 AND G2 AND G3 AND G4 AND G5 = PASS → VERDICT: PASS
ELSE → VERDICT: FAIL

Kein TWEAK. Kein "vielleicht". Keine Ausnahme.
```

### Warum kein TWEAK?
- TWEAK bedeutet: "Könnte funktionieren, aber nicht sicher"
- Im Live-Handel gibt es kein "vielleicht" – entweder der Trade funktioniert oder nicht
- Wenn eine Strategie fast gut genug ist: FAIL → verbessern → neu testen
- Das zwingt uns, Strategien zu verbessern statt sie "irgendwie" durchzuwinken

---

## Scorecard v2 Format

```json
{
  "strategy_name": "mean_reversion_panic",
  "hypothesis": "Panic moves revert to mean",
  "version": "2.0",

  "backtest_results": {
    "net_return_pct": 0.85,
    "max_drawdown_pct": 30.45,
    "profit_factor": 1.007,
    "win_rate_pct": 58.89,
    "expectancy": 0.009,
    "trade_count": 90,
    "max_consecutive_losses": 7
  },

  "walk_forward": {
    "windows_profitable": 3,
    "windows_total": 3,
    "degradation_pct": 25,
    "robustness_score": 75
  },

  "resource_usage": {
    "memory_peak_mb": 128,
    "execution_time_ms": 1930,
    "cpu_avg_pct": 12
  },

  "gates": {
    "G1_profitability": {
      "net_return": {"value": 0.85, "threshold": 2.0, "passed": false},
      "profit_factor": {"value": 1.007, "threshold": 1.5, "passed": false},
      "expectancy": {"value": 0.009, "threshold": 0, "passed": true},
      "gate_passed": false
    },
    "G2_risk": {
      "max_drawdown": {"value": 30.45, "threshold": 20.0, "passed": false},
      "return_dd_ratio": {"value": 0.028, "threshold": 0.15, "passed": false},
      "max_consecutive_losses": {"value": 7, "threshold": 10, "passed": true},
      "gate_passed": false
    },
    "G3_robustness": {
      "wf_windows_profitable": {"value": 3, "threshold": 2, "passed": true},
      "wf_degradation": {"value": 25, "threshold": 40, "passed": true},
      "trade_count": {"value": 90, "threshold": 30, "passed": true},
      "gate_passed": true
    },
    "G4_resources": {
      "memory_peak": {"value": 128, "threshold": 256, "passed": true},
      "execution_time": {"value": 1930, "threshold": 30000, "passed": true},
      "cpu_avg": {"value": 12, "threshold": 50, "passed": true},
      "gate_passed": true
    },
    "G5_guardrails": {
      "combinations": {"value": 9, "threshold": 50, "passed": true},
      "assets": {"value": 1, "threshold": 3, "passed": true},
      "gate_passed": true
    }
  },

  "verdict": "FAIL",
  "verdict_reason": "G1: net_return 0.85% < 2.0%, profit_factor 1.007 < 1.5; G2: max_drawdown 30.45% > 20%, return/dd ratio 0.028 < 0.15",
  "failed_gates": ["G1_profitability", "G2_risk"],
  "passed_gates": ["G3_robustness", "G4_resources", "G5_guardrails"],

  "improvement_hints": [
    "G1: Profit Factor zu niedrig – bremsende Verluste reduzieren",
    "G2: Drawdown zu hoch – Stop-Loss oder Volatility-Filter",
    "G2: Return/DD Ratio 0.028 – Strategie ist riskanter als lohnend"
  ],

  "timestamp": "2026-04-18T22:41:00Z",
  "scorecard_version": "2.0"
}
```

---

## KI-Analyse – Neue Rolle

Die KI ist nicht mehr Korrektur, sondern **Erklärung**:

```
Scorecard → Gates → Verdict (automatisch, harte Logik)
    ↓
KI-Analyse → Warum FAIL? Was specifically verbessern?
    ↓
Entwickler → Verbessert Strategie → Neuer Backtest → Neue Scorecard
```

Die KI sagt nicht mehr "TWEAK", sondern:
- "FAIL weil G1 und G2. Konkrete Verbesserungsvorschläge: ..."

Das ist Musk: Die Maschine entscheidet. Der Mensch verbessert.

---

## Was sich ändert vs. v1

| Aspekt | v1 (alt) | v2 (neu) |
|--------|----------|----------|
| Verdicts | PASS/TWEAK/FAIL | PASS/FAIL (binär) |
| Scorecard-Logik | Weich, WF-dominiert | 5 harte Gates |
| KI-Rolle | Korrektur der Scorecard | Erklärung der Gates |
| TWEAK-Strategien | "Vielleicht live" | FAIL → verbessern → neu testen |
| Acceptance | "3 Scorecards mit Verdict" | "3 Scorecards die GATES passen ODER dokumentiert FAILen" |
| Durchlauf-Zeit | 1 Runde | Iterativ bis PASS oder Abbruch |

---

## Migration v1 → v2

1. Scorecard-Versionierung: v2.0 Format
2. Gate-Evaluator als eigenständiges Modul
3. KI-Prompt anpassen: "Erkläre die FAIL-Gates, nicht das Verdict"
4. Bestehende 3 Scorecards re-evaluieren mit v2 Gates
5. Phase 7 Acceptance: Alle 3 müssen entweder PASS oder dokumentiert FAIL sein

---

## Re-Evaluation der 3 Strategien (v2 Gates)

### trend_pullback
- G1: Return -0.04% → ❌ FAIL (Return negativ)
- G2: DD 3.59% → ✅, aber Return/DD ratio negativ → ❌ FAIL
- G3: Trades 3 → ❌ FAIL (zu wenige)
- G4: ✅
- G5: ✅
- **Verdict: FAIL** (G1, G2, G3) – Strategie funktioniert nicht

### mean_reversion_panic
- G1: Return 0.85% → ❌ (< 2%), PF 1.007 → ❌ (< 1.5), Expectancy ✅
- G2: DD 30.45% → ❌ (> 20%), Return/DD 0.028 → ❌ (< 0.15)
- G3: WF 3/3 ✅, Degradation 25% ✅, Trades 90 ✅
- G4: ✅
- G5: ✅
- **Verdict: FAIL** (G1, G2) – Robust aber nicht profitabel genug

### multi_asset_selector
- G1: Return 1.21% → ❌ (< 2%), PF unbekannt, Expectancy ✅
- G2: DD 39.71% → ❌ (> 20%), Return/DD 0.03 → ❌
- G3: WF ✅, Trades 193 ✅
- G4: ✅
- G5: ✅
- **Verdict: FAIL** (G1, G2) – Gleiche Probleme wie MRP

---

## Fazit

Alle 3 Strategien FAILen unter v2 Gates. Das ist nicht schön, aber es ist die Wahrheit.

**Musk:** "If you're not failing, you're not innovating enough."
**Jobs:** "We don't ship junk."

Die Strategien müssen verbessert werden, nicht die Standards gesenkt.
Phase 7 v2 ist erledigt, wenn mindestens EINE Strategie alle 5 Gates passed.