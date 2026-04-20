---
title: Test Suite
---

# 🧪 Test Suite — Executor V1

> **82 Tests, 100% Grün** | Commit `68e4f8e` | Run: `pytest tests/ -v`

---

## Übersicht

| Schicht | Files | Tests | Was sie fangen |
|---------|-------|-------|---------------|
| **Unit** | 5 | 75 | Modul-Logik, Bug-Regressionen pro Funktion |
| **E2E** | 1 | 7 | Full Pipeline: Candle → Signal → Guard → Entry → Exit → Equity |

---

## Unit Tests

### `test_state_manager` (14 Tests)

| Kategorie | Tests | Bug-Regression |
|-----------|-------|---------------|
| Position Lifecycle | 5 | Open/Close/Persistenz |
| Equity Tracking | 4 | Start/Peak/Persistenz |
| **BUG 2 Regr.** | 3 | NET vs GROSS PnL in trades-Tabelle |
| Accounting-Invariante | 3 | `equity = initial + sum(net_pnl) - sum(entry_fees)` |

### `test_risk_guard` (9 Tests)

| Kategorie | Tests | Bug-Regression |
|-----------|-------|---------------|
| Guard State Machine | 2 | RUNNING → KILL_SWITCH |
| **BUG 4 Regr.** | 2 | Daily Loss nutzt CURRENT equity (nicht start_equity) |
| Consecutive Losses | 3 | CL-Counter, Reset, SOFT_PAUSE |
| Drawdown | 2 | < 20% kein Kill, > 20% Kill |

### `test_signal_generator` (17 Tests)

| Kategorie | Tests |
|-----------|-------|
| Entry Conditions | 5 |
| Exit Conditions | 6 |
| Indicator Calculation | 3 |
| Parameter Consistency | 6 |

### `test_discord_reporter` (18 Tests)

| Kategorie | Tests | Bug-Regression |
|-----------|-------|---------------|
| **BUG 3 Regr.** | 8 | Alle 6 Assets in Hourly Status (war nur BTC/ETH) |
| Format Functions | 5 | Entry/Exit/Blocked/Guard Tuples |
| Color Constants | 5 | Green/Red/Amber/Blue/Gray |

### `test_paper_engine` (11 Tests)

| Kategorie | Tests | Bug-Regression |
|-----------|-------|---------------|
| **BUG 1 Regr.** | 2 | Entry Fee wird von Equity abgezogen |
| **BUG 2 Regr.** | 1 | NET PnL in trades-Tabelle |
| Position Sizing | 5 | Leverage Tiers, Fee in Size |
| Multi-Trade Accounting | 2 | Invariante über 3 Trades |
| PnL Tracking | 2 | Daily PnL, Equity ≥ 0 |

---

## E2E System Tests

### `test_e2e_system` (7 Tests)

Testet die **Integration** — das was Unit-Tests nicht können:

| Test | Was geprüft wird |
|------|-----------------|
| No trade on flat market | Kein SIGNAL_LONG → kein Entry |
| Entry on uptrend | SIGNAL_LONG → Position geöffnet, Fee abgezogen |
| Full trade cycle accounting | Entry → Exit: `final = start - entry_fee + net_pnl` |
| Risk guard blocks after KILL | DD > 20% → kein neuer Entry |
| Accounting invariant | Ein vollständiger Trade-Zyklus: Equity stimmt exakt |
| All 6 assets in status | BUG 3 auf System-Ebene |
| PAPER_MODE enforcement | Engine bricht ab wenn PAPER_MODE=False |

---

## Bug → Test Workflow

Jeder neue Bug folgt diesem Prozess:

```
1. Bug finden → fixen
2. Test schreiben der den Bug VOR dem Fix reproduziert (sollte FAILen)
3. Fix anwenden → Test muss PASSen
4. pytest tests/ -v → alles grün = sicher
5. Commit mit Bug-Referenz
```

**Beispiel BUG 1 (Entry Fee):**
```python
# Test BEFORE fix: entry fee not in equity
def test_equity_decreases_on_entry(self):
    engine._open_position("BTCUSDT", 85000, ...)
    equity_after = engine.state.get_equity()
    assert equity_after < 100.0  # FAIL with bug, PASS after fix
```

---

## Bekannte Lücken

Tests decken **Modul-Logik + Integration** ab, aber nicht:

| Lücke | Warum riskant | Nur lösbar durch |
|-------|---------------|-----------------|
| Multi-Asset Concurrent | SQLite Race Conditions | Paper Trading |
| Crash Mid-Trade | Position in DB, Equity falsch | Restart-Recovery Test |
| Echte WebSocket-Formate | API-Änderungen | Live-Feed Test |
| CommandListener + Discord | Polling, Rate Limits | Integration Test |
| Echte Marktdaten | Synthetische ≠ Real | 30 Tage Paper Trading |

**Echte Sicherheit kommt nur aus 30+ Tagen Paper Trading mit echten Testnet-Daten.**

---

## Quick Reference

```bash
# Alle Tests laufen
cd forward_5/executor
pytest tests/ -v

# Nur E2E
pytest tests/test_e2e_system.py -v

# Nur Bug-Regressionen
pytest tests/ -v -k "Regression"

# Mit Coverage
pytest tests/ --cov=. --cov-report=term-missing
```