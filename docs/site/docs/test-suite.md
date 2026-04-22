---
title: Test Suite
---

# 🧪 Test Suite — Executor V1

> **297 Tests, 100% Grün, 81% Coverage** | Run: `pytest tests/ -v`

---

## 4-Layer Hardening Protocol — ✅ COMPLETE

| Schicht | Methode | Ergebnis |
|---------|---------|----------|
| **1** | pytest-cov Coverage | 81% Total, alle Module gemessen |
| **2** | ruff + mypy Static Analysis | 0 Issues |
| **3** | hypothesis Property Tests | 15 Tests ✅ |
| **4** | Fault Injection | 21 Tests ✅ |

**Success Criteria — ALL MET:**
- ✅ ≥250 Tests → **297**
- ✅ ≥80% Coverage per Module → **81% Total**
- ✅ 0 static issues → **0**
- ✅ ≥15 property tests → **15**
- ✅ ≥10 fault injection tests → **21**

---

## Coverage per Module

| Modul | Coverage | Tests |
|-------|----------|-------|
| accounting_check | 94% | 29 |
| signal_generator | 81% | 17 |
| state_manager | 83% | 14 |
| risk_guard | 69% | 10 |
| paper_engine | 61% | 46 |
| command_listener | 56% | 23 |
| data_feed | 48% | 7+21 |
| discord_reporter | 48% | 18 |
| watchdog_v2 | 46% | 27 |

---

## Test Files Overview

| File | Tests | Focus |
|------|-------|-------|
| `test_state_manager` | 14 | Position lifecycle, equity, accounting |
| `test_risk_guard` | 10 | Guard states, DD, consecutive losses |
| `test_signal_generator` | 17 | Entry/exit conditions, indicators |
| `test_discord_reporter` | 18 | Format functions, color constants |
| `test_paper_engine` | 11 | Entry fees, PnL, position sizing |
| `test_data_feed` | 7 | API error handling, gap recovery |
| `test_e2e_system` | 7 | Full pipeline candle→signal→exit |
| `test_crash_recovery` | 22 | Gap recovery, position integrity, DB |
| `test_paper_engine_critical` | 25 | Unrealized DD, KILL close-all, dedup |
| `test_audit_round6` | 20 | Round 6 bug regressions |
| `test_watchdog_v2` | 27 | Circuit breaker, escalation, restart |
| **`test_property`** | **15** | **Hypothesis property-based (DD math, PnL, sizing, fees, signals)** |
| **`test_fault_injection`** | **21** | **API failures, DB corruption, malformed data, edge cases** |
| **`test_paper_engine_coverage`** | **21** | **Dedup, unrealized DD, signal processing, 4h summary** |
| **`test_accounting_check`** | **29** | **Equity invariant, orphans, guard state, freshness, peak** |
| **`test_command_listener`** | **23** | **Command parsing, dedup, bot filtering, kill/resume/help** |

---

## Bug → Test Workflow

```
1. Bug finden → fixen
2. Test schreiben der Bug VOR dem Fix reproduziert (FAIL)
3. Fix anwenden → Test muss PASSen
4. pytest tests/ -v → alles grün
5. Commit mit Bug-Referenz
```

---

## Bug Audit Summary

| Round | Bugs | Critical | Fixed |
|-------|------|----------|-------|
| 2 | 3 | 2 (WS format, partial candle, position sizing) | ✅ |
| 3 | 1 | 1 (mainnet/testnet data mismatch) | ✅ |
| 4 | 5 | 2 (entry fee, gross PnL) | ✅ |
| 5 | 8 | 2 (SOFT_PAUSE loop, KILL no close) | ✅ |
| 6 | 10 | 2 (API error handling, unrealized DD) | ✅ |

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

---

## Quality Pipeline

```
Code-Änderung → Pre-Commit Hook (pytest) → Commit → Push → Cloudflare Build
                     ↓ FAIL
                 Commit blockiert
```

---

## Quick Reference

```bash
cd forward_5/executor
pytest tests/ -v              # Alle Tests
pytest tests/ -k "property"   # Nur Property Tests
pytest tests/ -k "fault"      # Nur Fault Injection
pytest tests/ --cov=.         # Mit Coverage
```