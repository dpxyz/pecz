---
title: Test Suite
---

# 🧪 Test Suite — Executor V1

> **83 Tests, 100% Grün** | Run: `pytest tests/ -v`

---

## Übersicht

| Schicht | Files | Tests | Was sie fangen |
|---------|-------|-------|---------------|
| **Unit** | 5 | 75 | Modul-Logik, Bug-Regressionen pro Funktion |
| **E2E** | 1 | 7 | Full Pipeline: Candle → Signal → Guard → Entry → Exit → Equity |
| **Regression** | (in Unit) | 1 | SOFT_PAUSE Endlos-Loop |

---

## Unit Tests

### `test_state_manager` (14 Tests)

| Kategorie | Tests | Bug-Regression |
|-----------|-------|---------------|
| Position Lifecycle | 5 | Open/Close/Persistenz |
| Equity Tracking | 4 | Start/Peak/Persistenz |
| **BUG 2 Regr.** | 3 | NET vs GROSS PnL in trades-Tabelle |
| Accounting-Invariante | 3 | `equity = initial + sum(net_pnl) - sum(entry_fees)` |

### `test_risk_guard` (10 Tests)

| Kategorie | Tests | Bug-Regression |
|-----------|-------|---------------|
| Guard State Machine | 2 | RUNNING → KILL_SWITCH |
| **BUG 4 Regr.** | 2 | Daily Loss nutzt CURRENT equity (nicht start_equity) |
| Consecutive Losses | 4 | CL-Counter, Reset, SOFT_PAUSE, **CL-Reset bei Expiry** |
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

| Test | Was geprüft wird |
|------|-----------------|
| No trade on flat market | Kein SIGNAL_LONG → kein Entry |
| Entry on uptrend | SIGNAL_LONG → Position geöffnet, Fee abgezogen |
| Full trade cycle accounting | Entry → Exit: `final = start - entry_fee + net_pnl` |
| Risk guard blocks after KILL | DD > 20% → kein neuer Entry |
| Accounting invariant | Ein vollständiger Trade-Zyklus |
| All 6 assets in status | BUG 3 auf System-Ebene |
| PAPER_MODE enforcement | Engine bricht ab wenn PAPER_MODE=False |

---

## Accounting Invariant Check

Neben der Test Suite gibt es einen **täglichen Live-Check** der die produktive `state.db` prüft:

| Check | Was geprüft wird |
|-------|-----------------|
| Equity Invariant | `equity ≈ start - entry_fees + sum(pnl)` |
| Orphan Positions | Position offen >48h |
| Guard Consistency | Timestamps passen zum Guard-State |
| Candle Freshness | Letzter Candle <2h her |
| Peak ≥ Equity | Peak-Equity-Tracking nicht kaputt |

**Läuft:** Täglich 09:00 Berlin via Housekeeping → Report nach #system

---

## Bug → Test Workflow

```
1. Bug finden → fixen
2. Test schreiben der den Bug VOR dem Fix reproduziert (sollte FAILen)
3. Fix anwenden → Test muss PASSen
4. pytest tests/ -v → alles grün = sicher
5. Commit mit Bug-Referenz
```

---

## Quality Pipeline

```
Code-Änderung → Pre-Commit Hook (pytest) → Commit → Push → Cloudflare Build
                     ↓ FAIL
                 Commit blockiert
```

**Pre-Commit Hook:** `scripts/pre-commit.sh` — pytest MUSS grün sein für Executor-Commits.

---

## Bekannte Lücken

| Lücke | Nur lösbar durch |
|-------|-----------------|
| Multi-Asset Concurrent (SQLite Race) | Paper Trading |
| Crash Mid-Trade / Restart | Recovery Test |
| Echte WebSocket-Formate | Live-Feed Test |
| CommandListener + Discord Polling | Integration Test |
| Echte Marktdaten | 14+ Tage Paper Trading |

**Echte Sicherheit kommt nur aus Paper Trading mit echten Testnet-Daten.**

---

## Quick Reference

```bash
cd forward_5/executor
pytest tests/ -v          # Alle Tests
pytest tests/ -k "Regression"  # Nur Bug-Regressionen
pytest tests/ --cov=.     # Mit Coverage
```