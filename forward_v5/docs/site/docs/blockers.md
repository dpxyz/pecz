# Offene Blocker

## Aktueller Status

**Phase 7 🔨 BUILD — Regime-Filter Validierung** – 50% Pass-Rate erreicht, Ziel: ≥60%. Phase 8 blockiert.

## Aktive Blocker

| ID | Blocker | Status | Owner | Impact |
|----|---------|--------|-------|--------|
| B11 | **Phase 7 Foundry** | 🔨 Build — Regime-Filter | Pecz | ⛔ Blockt Phase 8 |
| B11a | Foundry-Script bauen | ✅ dsl_translator.py + evolution_runner.py v2.0 | Pecz | |
| B11b | Echter Backtest-Runner | ✅ WalkForward + Gate Evaluator | Pecz | |
| B11c | Datenpfad verifiziert | ✅ 8 Assets, je ~20K hourly candles | Pecz | |
| B11d | Erster Foundry-Run | ✅ MACD Momentum + Regime-Filter | Pecz | |
| B11e | Breite Validierung | ✅ 90 Tests (6 Strategien × 3 Assets × 5 Perioden) | Pecz | |
| B11f | Regime-Filter Validierung | ✅ 80 Tests (5 Filter × 8 Assets × 2 Perioden) | Pecz | |
| B11g | ADX+EMA Filter erreicht 50% Pass-Rate | ✅ DD -47%, CL -34% vs Unfiltered | Pecz | |
| B11h | **≥60% Pass-Rate** | 🔨 Nächstes Ziel | Pecz | |
| B11i | Paper/Shadow-Trading auf HL Testnet | ⬜ Nach ≥60% Pass-Rate | Pecz | |
| B11j | Wöchentlicher Cron + Discord-Report | ⬜ Nach Paper-Trading | Pecz | |
| B11k | ADR-005 Layer-Interfaces finalisiert | ⬜ Architecture definiert | Dave+Pecz | |

---

## ADR-005: Three-Layer Architecture

```
LAYER 1: FOUNDRY (Pre-Trade)          ← WIR SIND HIER
  Strategy → Backtest → Walk-Forward → Gates → Paper Trading

LAYER 2: EXECUTOR (During Trade)      ← NACH FOUNDARY
  Order Mgmt → Kill-Switches → Position Sizing → Exits
  Deterministisch, kein LLM during trading

LAYER 3: MONITOR (Post-Trade)          ← NACH EXECUTOR
  PnL Tracking → Regime Detection → Retirement → Alerts
```

**Key Principle:** Keine zweite freie KI als Richter. Deterministische Gates, dann deterministischer Executor.

---

## Geschlossene Blocker (Letzte 30 Tage)

| ID | Blocker | Status | Gelöst am |
|----|---------|--------|-----------|
| B10 | **Memory Monitoring Fix** | ✅ Gelöst | 2026-04-05 |
| B6-9 | **24h Stability Test** | ✅ **PASSED** | **2026-04-05** |
| B1 | ADR-003/004 incomplete | ✅ Gelöst | 2026-03-08 |

---

## Phase 6 Abschluss ✅

```
╔══════════════════════════════════════════════════════════╗
║  24h Stability Test — PASSED ✅                         ║
╠══════════════════════════════════════════════════════════╣
║  Start:     2026-04-04 09:40 GMT+2                      ║
║  Ende:      2026-04-05 09:40 GMT+2                      ║
║  Dauer:     24h (86,409,577 ms)                         ║
║  Checks:    96/96 healthy (100%)                      ║
║  Memory:    Max 83.4%                                   ║
║  Errors:    0                                           ║
║  CB Changes: 0                                          ║
╚══════════════════════════════════════════════════════════╝
```

**Alle Acceptance Gates:** ✅ PASSED
- G1: Zero unmanaged positions ✅
- G2: Projection parity ✅
- G3: Recovery from restart ✅
- G4: No duplicated trade IDs ✅
- G5: Discord Failover blockiert nicht ✅

---

## Deferred (Nicht blockierend)

| ID | Blocker | Status | Next Step |
|----|---------|--------|-----------|
| 5.1 | Block 5.1 Host-Test auf systemd-Maschine | ⏳ Code ✅ / Runtime ⏳ | VPS-Zugang oder manuelles Deploy |

---

## Blocker-Policy

| Code | Bedeutung |
|------|-----------|
| 🔨 | Build in Progress |
| 🔄 | In Progress |
| ⬜ | Not started |
| ⏳ | Waiting for dependency |
| ✅ | Resolved |
| ⛔ | Hard block |
| ⏸️ | Deferred (nicht blockierend) |

---

*Last updated: 2026-04-19*  
*Phase 7 Status: BUILD — Regime-Filter Validierung (50% Pass-Rate)*