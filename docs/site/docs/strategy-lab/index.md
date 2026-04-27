# Strategy Lab — Foundry

## Current: V8 Oktopus (ab 2026-04-27)

**6-Arm Evolutionary Search** mit Autopsie-Feedback und Budget-Steuerung.

### Architektur

```
Phase 1: Exploration (5 pro Arm × 6 Arme = ~30 Kandidaten)
Phase 2: Evolution (Mutation + Crossover aus HOF + Autopsie-Feed)
Phase 2.5: Parameter Sweep (Grid + Regime Overlay)
Phase 3: Hard Check (10-Window Walk-Forward)
Phase 3.5: Deep Autopsie → gezielte Mutationen für nächsten Run
```

### Arme

| Arm | IS_avg | Trend | Kandidaten | Beschreibung |
|-----|--------|-------|------------|--------------|
| MR | -0.017 | producing | 143 | Mean Reversion (BB+RSI+EMA) |
| TREND | -0.103 | producing | 71 | Trend Following (EMA+ADX+MACD) |
| MOM | +0.000 | stable | 25 | Momentum (ROC+MACD+Volume) |
| VOL | -0.187 | declining | 43 | Volume-Boosted MR |
| REGIME | -0.076 | promising | 30 | Volatility/Regime-Filter |
| 4H | +1.050 | producing | 5 | 4h Aggregation (massiv overfitted) |

### Deep Autopsie (6 Analysen)

1. **Exit-Reason** — SL dominiert? Trail kommt nie? → Exit-Optimierung
2. **Window** — Welche WF-Windows profitabel? → Pattern erkennen
3. **Asset** — Stark/Schwach-Assets → Major vs Alt
4. **Regime** — Strategy-Typ vs Asset-Performance → Regime-Filter
5. **Trade-Density** — Zu viele/wenig Trades → Entry anpassen
6. **DD** — DD/Return-Ratio → SL-Problem

### Kernerkenntnis (170+ Kandidaten)

> **1h-Crypto mit Standard-Indikatoren (BB/RSI/EMA/MACD/ADX) hat keinen robusten Edge.** 92% der Exits sind signal_exit, Entry zu restriktiv (0.6-2.5 Trades/Window), MR funktioniert nur auf volatilen Alts.

### HOF Top 3

| # | Name | WF | IS | Typ |
|---|------|----|----|-----|
| 1 | MeanReversion_BB15_RSI10_EMA100 | 65.0 (5w) | -0.14 | MR |
| 2 | MeanReversion_BB15_RSI10_EMA100_v2 | 65.0 (5w) | -0.17 | MR |
| 3 | MeanReversion_BB15_RSI10_EMA100_v2 | 65.0 (5w) | -0.17 | MR |

⚠️ Alle 3 passed bei 5-Window, **FAIL bei 10-Window** (WF=23.3)

### Pipeline History

- **V4/V5:** FROZEN → V7
- **V6:** FROZEN → V7
- **V7:** FROZEN → V8
- **V8 Oktopus:** AKTIV — 6 Arme, Autopsie, Sweep, Budget-Steuerung

### Files

```
research/
├── run_evolution_v8.py    # Main (alle Phasen)
├── walk_forward_gate.py   # DSL Parser + WF Gate + 4h
├── autopsy.py             # Deep Autopsie V2 (6 Analysen)
├── parameter_sweep.py     # Grid + Regime Sweep
├── FOUNDRY_OCTOPUS.md     # Architektur-Dokument
└── runs/evolution_v7/     # HOF + Ergebnisse
```

### Daily Cron

- **Zeit:** 04:30 Berlin
- **Script:** `run_daily_evolution.sh`
- **Report:** Discord #foundry-reports

---

*Last updated: 2026-04-27*