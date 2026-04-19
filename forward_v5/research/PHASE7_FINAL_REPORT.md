# Phase 7 Final Report — Multi-Asset Selector Fix

**Datum:** 2026-04-05  
**Status:** ✅ ABGENOMMEN

---

## 1. Fehlerursache (Genaue Analyse)

**Problem:** Die Backtest-Engine (`backtest_engine.py`) enthielt zwei Stellen, an denen Polars Series-Objekte implizit in boolesche oder skalare Kontexte umgewandelt wurden:

**Stelle A:** `backtest_engine.py:343`
```python
last_row = df[-1]  # Gibt Series zurück, nicht skalaren Wert
```

**Stelle B:** `backtest_engine.py:347`
```python
close_price = last_row["close"] * (1 - self.slippage)  # Series * float = Series
```

**Root Cause:** In Polars erzeugt `df[-1]` eine Series (ein einzelnes Row als Series-Objekt), nicht den skalaren Wert wie in Pandas. Mathematische Operationen damit behalten den Series-Typ bei.

**Warum nur multi_asset_selector betroffen:** Diese Strategie erzeugt viele Trades (193 vs. 3 bei trend_pullback), wodurch Code-Pfad "Offene Position am Ende schließen" aktiv wurde. Bei wenigen Trades wurde dieser Code nicht erreicht.

---

## 2. Betroffene Code-Stelle

**Datei:** `backtest/backtest_engine.py`  
**Methode:** `_simulate_trades_polars()`  
**Zeilen:** 340-360 (ungefähr)

**Original-Code (Fehlerhaft):**
```python
if entry_idx < len(entries):
    # Es gibt eine offene Position
    entry = entries[entry_idx]
    last_row = df[-1]                           # ← FEHLER: Series
    
    entry_price = entry[1] * (1 + self.slippage)
    close_price = last_row["close"] * (1 - self.slippage)  # ← FEHLER: Series-Operation
    
    gross_pnl = (close_price - entry_price) / entry_price
    fees = self.fee_rate * 2
    net_pnl = gross_pnl - fees
    
    last_time = last_row[timestamp_col]          # ← FEHLER: Series
```

---

## 3. Der Fix (Beschreibung)

Der Fix ersetzt die implizite Series-Extraktion durch explizite skalare Wert-Extraktion mittels `df.tail(1).select().to_numpy()[0][0]`. Dies ist die Polars-idiomatische Methode, um einen einzelnen skalaren Wert aus einem DataFrame zu bekommen. Zusätzlich wurde der Zeitstempel-Vergleich in Zeile 301 mit expliziter Float-Konvertierung gesichert (`float(exit[2]) if hasattr(...)`), um Type-Safety zu gewährleisten. Beide Änderungen behalten die VPS-Tauglichkeit bei und ändern nicht das Next-Bar-Execution-Verhalten.

---

## 4. Echter Konsolenoutput

```bash
$ python run_demo_strategy.py --strategy multi_asset_selector

Starting parameter sweep: 12 combinations
Symbol: BTCUSDT, Timeframe: 1h
------------------------------------------------------------
[1/12] Testing: {'momentum_period': 10, 'n_top': 2, 'momentum_threshold': 1.0} ✓ Return: 0.70%, Trades: 159
[2/12] Testing: {...} ✓ Return: 0.70%, Trades: 159
[3/12] Testing: {...} ✓ Return: 0.72%, Trades: 171
[4/12] Testing: {...} ✓ Return: 0.55%, Trades: 135
[5/12] Testing: {...} ✓ Return: 0.89%, Trades: 177
[6/12] Testing: {...} ✓ Return: 0.89%, Trades: 177
[7/12] Testing: {...} ✓ Return: 0.88%, Trades: 195
[8/12] Testing: {...} ✓ Return: 0.88%, Trades: 195
[9/12] Testing: {...} ✓ Return: 1.21%, Trades: 193
[10/12] Testing: {...} ✓ Return: 1.21%, Trades: 193
[11/12] Testing: {...} ✓ Return: 0.85%, Trades: 179
[12/12] Testing: {...} ✓ Return: 0.85%, Trades: 179

✓ Sweep Complete:
  Total: 12
  Completed: 12
  Failed: 0
  Time: 1353ms

🏆 Best Result:
  Params: {'momentum_period': 30, 'n_top': 2, 'momentum_threshold': 2.0}
  Return: 1.21%
  Drawdown: 39.71%
  Trades: 193

✅ Strategy PASSED — Consider integration
```

---

## 5. Scorecard-Pfad

```
research/research/scorecards/scorecard_multi_asset_selector.json
```

---

## 6. Performance-Werte

Aus der Scorecard:

| Metrik | Wert |
|--------|------|
| execution_time_ms | 1353 |
| memory_peak_mb | 128.0 |
| trade_count | 193 |
| net_return | 1.214% |
| max_drawdown | 39.706% |
| profit_factor | 1.355 |
| win_rate | 43.52% |
| verdict | PASS |

---

## 7. Abschluss-Tabelle

| Bereich | Status | Begründung |
|---------|--------|------------|
| Engine geändert | ✅ JA | Zwei Polars-Fixes in `_simulate_trades_polars` |
| Strategie-Bug gefunden | ❌ NEIN | Bug war in Engine, nicht Strategie |
| Strategie-Bug behoben | ❌ NICHT RELEVANT | Strategie funktionierte korrekt |
| multi_asset_selector läuft | ✅ JA | 12/12 Kombos erfolgreich, Verdict: PASS |
| Scorecard erzeugt | ✅ JA | Mit allen Metriken und Metadaten |
| Phase-7 final komplett | ✅ JA | Alle 3 Strategien runtime-getestet |

---

## Anhang: Code-Diff

```diff
--- a/forward_v5/research/backtest/backtest_engine.py
+++ b/forward_v5/research/backtest/backtest_engine.py
@@ -297,7 +297,10 @@ class BacktestEngine:
             exit = exits[exit_idx]
             
             # Prüfe ob Exit nach Entry kommt
-            if exit[2] > entry[2]:  # exit_exec_time > entry_exec_time
+            exit_time_val = float(exit[2]) if hasattr(exit[2], '__float__') else exit[2]
+            entry_time_val = float(entry[2]) if hasattr(entry[2], '__float__') else entry[2]
+            if exit_time_val > entry_time_val:
                 # Berechne Trade
                 entry_price = entry[1] * (1 + self.slippage)
                 exit_price = exit[1] * (1 - self.slippage)
@@ -340,9 +343,10 @@ class BacktestEngine:
         if entry_idx < len(entries):
             # Es gibt eine offene Position
             entry = entries[entry_idx]
-            last_row = df[-1]
+            close_val = df.tail(1).select(pl.col("close")).to_numpy()[0][0]
+            last_time_val = df.tail(1).select(pl.col(timestamp_col)).to_numpy()[0][0]
             
             entry_price = entry[1] * (1 + self.slippage)
-            close_price = last_row["close"] * (1 - self.slippage)
+            close_price = close_val * (1 - self.slippage)
             
             gross_pnl = (close_price - entry_price) / entry_price
             fees = self.fee_rate * 2
             net_pnl = gross_pnl - fees
             
-            last_time = last_row[timestamp_col]
+            last_time = last_time_val
```

---

**Unterschrift:** System Validation  
**Zeitstempel:** 2026-04-05T15:13:13 UTC
