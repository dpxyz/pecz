# Roadmap

## Aktueller Status 🎉

**Phase 6: Test Strategy — ✅ COMPLETE**  
*24h Stability Test PASSED (2026-04-05)*

---

## Test Results Summary ✅

### 24h Stability Test — PASSED

| Metrik | Wert |
|--------|------|
| Status | ✅ **PASSED** |
| Dauer | 24h (86,409,577 ms) |
| Health Success Rate | 100.0% (96/96 checks) |
| Max Memory | 83.4% |
| Circuit Breaker Changes | 0 |
| Total Errors | 0 |
| Start | 2026-04-04 09:40 GMT+2 |
| Ende | 2026-04-05 09:40 GMT+2 |

**Alle Acceptance Gates G1-G5:** ✅ PASSED

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

---

## ⭐ Phase 7: Strategy Lab — REGIME FILTER VALIDATED

**Status:** 🎯 **BASELINE COMMITTED — PAPER TRADING NEXT**

### Baseline Strategy: MACD Momentum + ADX+EMA

```
Entry: macd_hist > 0 AND close > ema_50 AND ema_50 > ema_200 AND adx_14 > 20
Exit:  trailing_stop 2%, stop_loss 2.5%, max_hold 48 bars
```

| Metrik | Wert |
|--------|------|
| Pass Rate | 8/16 (50%) |
| Avg Return | +35.9% |
| Avg Drawdown | 14.1% |
| Avg Consecutive Losses | 6.5 |
| ATR-Filter getestet | ❌ Keine Verbesserung |
| Gate-Lockerung | ❌ Abgelehnt |

### Foundry V1 Status

| Komponente | Status | Beschreibung |
|------------|--------|--------------|
| backtest_engine.py | ✅ | Mit Trailing Stop + Sharpe + CL |
| walk_forward.py | ✅ | Walk-Forward Validierung |
| dsl_translator.py v3 | ✅ | 8+ Indikatoren, ADX+ATR+bb_width Fix |
| evolution_runner.py v2 | ✅ | 3 Modi (mock/dry-run/live) |
| gate_evaluator.py | ✅ | Standalone Functions + GateResult |
| Regime Filter | ✅ | ADX+EMA (50% Pass), ATR getestet (kein Gewinn) |
| Broad Validation | ✅ | 8 Assets × 2 Perioden × 5 Filter = 80 Tests |

### Nächster Schritt: Paper/Forward Trading (ADR-006)

→ Siehe ADR-006: Executor V1 mit Kill-Switches, Runtime Guards, Discord-Reporting

### Backtest Engine

| Komponente | Status | Beschreibung |
|------------|--------|--------------|
| backtest_engine.py | ⬜ TODO | Haupt-Backtest-Framework |
| parameter_sweep.py | ⬜ TODO | Parameter-Optimierung |
| walk_forward.py | ⬜ TODO | Walk-forward Validierung |

### Strategien

| Strategie | Status | Notizen |
|-----------|--------|---------|
| rsi_regime_filter.py | ⬜ TODO | RSI mit Regime-Erkennung |
| volatility_filter.py | ⬜ TODO | Volatilitäts-basierte Filter |
| multi_asset_selector.py | ⬜ TODO | Asset-Auswahl-Logik |
| mean_reversion_panic.py | ⬜ TODO | Mean Reversion Panic-Detection |
| trend_pullback.py | ⬜ TODO | Trend-Pullback Entries |

### Definition of Done

- [ ] Mindestens 3 Strategien mit Scorecards
- [ ] Jede Strategie: Hypothesis → Backtest → Walk-forward
- [ ] Alle Scorecards als JSON gespeichert
- [ ] Multi-Asset-Selektor implementiert
- [ ] Regime-Filter getestet

---

## Parallel Tasks

### Systemd Host Test (5.1)

| Teil | Status | Next Action |
|------|--------|-------------|
| Code | ✅ Complete | Service-Files ready |
| Host Test | ⏳ Deferred | VPS-Deploy pending |

Kein Blocker für Phase 7 — kann parallel laufen.

---

## Timeline

```
✅ COMPLETED:
Mar 06: Phase 0-1 Complete
Mar 08: Phase 2 Complete (103 Tests)
Mar 27: Phase 3 Complete (Observability)
Apr 01: Phase 5 Complete (Operations)
Apr 05: Phase 6 Complete (24h Test) 🎉

🚀 NEXT:
Apr 05-12: Phase 7 — Strategy Lab ⭐
Apr 12-19: Phase 8 — Economics
Apr 19-26: Phase 9 — Review & Gate
May 01:    ⛔ Manual Sign-off target
```

---

## Blocker Summary

| ID | Blocker | Status | Impact |
|----|---------|--------|--------|
| B10 | Memory Monitoring Fix | ✅ Gelöst | - |
| **Phase 6** | **Alle Tests** | **✅ Complete** | **-** |
| **Phase 7** | **Strategy Lab** | **⭐ Ready** | **Blocks Live** |
| 5.1 | Host Validation | ⏳ Deferred | Kein Blocker |

**Keine blockierenden Issues!** 🎉

---

*Last updated: 2026-04-05*  
*24h Test: PASSED ✅*
