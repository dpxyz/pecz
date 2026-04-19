# Roadmap

## Aktueller Status 🔨

**Phase 7: Foundry — 🔨 BUILD IN PROGRESS**  
*Foundry V1 Pipeline wird gebaut (2026-04-19)*

---

## Foundry V1 Pipeline — Status

### Pipeline-Komponenten

| Komponente | Datei | Status |
|------------|-------|--------|
| Spezifikation | `spec.yaml` | ✅ Aktualisiert (Fees, Data-Pfade) |
| DSL-Definition | `strategy_dsl.py` | ✅ Vorhanden |
| KI-Generator | `generator.py` | ✅ Vorhanden (Gemma4:31b) |
| DSL-Translator | `dsl_translator.py` | ✅ **NEU gebaut** |
| Backtest Engine | `backtest_engine.py` | ✅ Vorhanden (Polars) |
| Walk-Forward | `walk_forward.py` | ✅ Vorhanden |
| Gate Evaluator | `gate_evaluator.py` | ✅ Vorhanden (5 Gates) |
| Orchestrierung | `evolution_runner.py` | ✅ **NEU v2.0** |

### Noch offen (vor erstem Run)

- [ ] Datenpfad verifizieren – Parquet-Dateien existieren?
- [ ] Walk-Forward Integration testen
- [ ] Discord-Webhook für Report konfigurieren
- [ ] Erster Foundry-Run: `python3 evolution_runner.py --mock`
- [ ] Echter Foundry-Run: `python3 evolution_runner.py`
- [ ] Wöchentlicher Cron-Job (z.B. Sonntag 10:00 UTC)

### Noch offen (V2)

- [ ] Paper/Shadow Trading Interface
- [ ] Promoted-Status statt nur BACKTEST_PASS
- [ ] Live-Feed-Handler für Paper Trading

---

## Phase-by-Phase Status

### ✅ Phase 0-5: COMPLETE

| Phase | Status | Tests | Notizen |
|-------|--------|-------|---------|
| 0 | ✅ Freeze & Archive | - | Legacy archiviert |
| 1 | ✅ Skeleton & ADRs | - | 5 ADRs complete |
| 2 | ✅ Core Reliability | **103/103** | Event, Projection, Risk, Reconcile |
| 3 | ✅ Observability | **68/68** | Logger, Health, Reports, Rebuild |
| 4 | ✅ System Boundaries | **10/10** | Circuit Breaker, Safety/Observability |
| 5 | ✅ Operations | - | CLI, Dashboard, Alerts |

### ✅ Phase 6: Test Strategy — COMPLETE

| Gate | Name | Status |
|------|------|--------|
| G1 | Zero unmanaged positions | ✅ PASSED |
| G2 | Projection parity | ✅ PASSED |
| G3 | Recovery from restart | ✅ PASSED |
| G4 | No duplicated trade IDs | ✅ PASSED |
| G5 | Discord Failover blockiert nicht | ✅ PASSED |

**Simulation:**
- 1h Smoke Test: ✅ PASSED
- **24h Stability Test: ✅ PASSED (2026-04-05)**
- 7d Stability Test: ⬜ Optional

### 🔨 Phase 7: Foundry — BUILD IN PROGRESS

**Status:** 🔨 Foundry V1 Pipeline wird gebaut  
**⚠️ MANDATORY — Blocks Live Trading**

Foundry Charter beschlossen am 2026-04-18:
- KI generiert Strategien, harte Gates bewerten
- Binäre Verdicts: PASS oder FAIL
- FAIL = verworfen, nicht gerettet
- Nutzerprodukt = 1 Discord-Nachricht/Woche

Alte v1-Strategien: alle FAIL unter realistischen Kriterien.

---

## Blocker Summary

| ID | Blocker | Status | Impact |
|----|---------|--------|--------|
| B11 | **Phase 7 Foundry** | 🔨 Build | ⛔ Blockt Phase 8 |
| B11a | Pipeline-Skripte bauen | ✅ Done | |
| B11b | Backtest-Runner integriert | ✅ Done | |
| B11c | Wöchentlicher Cron + Discord | ⬜ Open | |
| B11d | 1 Strategie die Gates besteht | ⬜ Open | |
| 5.1 | Host Validation | ⏳ Deferred | Kein Blocker |

---

## Timeline

```
✅ COMPLETED:
Mar 06: Phase 0-1 Complete
Mar 08: Phase 2 Complete (103 Tests)
Mar 27: Phase 3 Complete (Observability)
Apr 01: Phase 5 Complete (Operations)
Apr 05: Phase 6 Complete (24h Test) 🎉

🔨 IN PROGRESS:
Apr 18: Phase 7 Foundry-Redesign beschlossen
Apr 19: Phase 7 Foundry V1 Build

⬜ NEXT:
Phase 7 Foundry-Run → Phase 8 Economics → Phase 9 Final Gate → Live
```

---

*Last updated: 2026-04-19*  
*Phase 7: Foundry V1 Build in Progress*