# Phase 7: Strategy Lab — VPS-First Research

## 🎯 Ziel

Reproduzierbares Research-System für **max 3 Strategien** auf einem Hostinger-VPS mit begrenztem RAM/CPU.

**Philosophie:**
- Harte Daten statt Stories
- Einfachheit statt Feature-Flut
- VPS-tauglich oder verworfen
- 3 starke Strategien > 10 schwache Ideen

---

## 📁 Struktur

```
research/
├── data/                    # OHLCV Parquet-Dateien
├── backtest/
│   ├── backtest_engine.py   → Kern-Backtesting
│   ├── parameter_sweep.py   ← Max 50 Kombinationen
│   └── walk_forward.py      ← Train/Validate/OOS
├── strategy_lab/
│   ├── trend_pullback.py         ⭐ Ready
│   ├── mean_reversion_panic.py   ⭐ Ready
│   ├── multi_asset_selector.py   ⭐ Ready
│   ├── rsi_regime_filter.py      → Filter-Baustein
│   └── volatility_filter.py      → Filter-Baustein
└── scorecards/
    ├── scorecard_schema.json     → JSON-Schema
    ├── scorecard_generator.py    → Generator
    └── *.json                    → Ergebnisse
```

---

## 🚀 Quick Start

```bash
# Prerequisites
cd forward_v5/research

# 1. Daten vorbereiten (Parquet-Format)
#    data/BTCUSDT_1h.parquet
#    Spalten: timestamp, open, high, low, close, volume

# 2. Backtest laufen lassen
python backtest/backtest_engine.py --data data/ --symbol BTCUSDT

# 3. Parameter Sweep (max 50 Kombinationen)
#    Siehe Beispiel in run_demo_strategy.py

# 4. Scorecard generieren
#    Ergebnis: scorecards/scorecard_*.json
```

---

## 🧪 Die 3 Strategien

| Strategie | Logik | VPS-Safe Grid |
|-----------|-------|---------------|
| **trend_pullback** | EMA-Trend + RSI-Oversold | 9 Kombinationen |
| **mean_reversion_panic** | Z-Score Threshold | 12 Kombinationen |
| **multi_asset_selector** | Momentum Ranking | 16 Kombinationen |

**Filter-Module:**
- `rsi_regime_filter.py` — Marktregime-Erkennung
- `volatility_filter.py` — ATR-basierte Filterung

---

## 📊 Scorecard Schema

```json
{
  "strategy_name": "trend_pullback",
  "hypothesis": "...",
  "dataset": { "symbol": "BTCUSDT", "timeframe": "1h", ... },
  "parameters": { "ema_period": 20, ... },
  "backtest_results": {
    "net_return": 15.5,
    "max_drawdown": -8.2,
    "profit_factor": 1.4,
    "win_rate": 52.3,
    "expectancy": 0.8,
    "trade_count": 45
  },
  "walk_forward": {
    "robustness_score": 75,
    "passed": true
  },
  "verdict": "PASS",
  "next_actions": ["Integrate into system", "Paper trade"]
}
```

---

## ⚠️ VPS Guardrails

| Limit | Wert | Warum |
|-------|------|-------|
| Max Param-Kombinationen | 50 | RAM sparen |
| Max Walk-Forward Windows | 5 | Kein Explosion |
| Max Assets (Multi-Asset) | 2-3 | VPS-Limit |
| Max Memory pro Run | 512MB | Container-Grenze |
| Data Format | Parquet | Efficient IO |
| Processing | Polars Lazy | RAM-sparend |

---

## 🎯 Verdict Logik

Scorecard-Verdicts sind hart:

- **PASS** → Weiter zu Phase 8 (Economics)
- **FAIL** → Hypothese überarbeiten
- **INCONCLUSIVE** → Mehr Daten, kein Go
- **REJECT_VPS_UNSAFE** → Zu schwer, verworfen

---

## 📈 Beispiel-Durchlauf

```python
from backtest.backtest_engine import BacktestEngine
from backtest.parameter_sweep import quick_sweep
from strategy_lab import trend_pullback
from scorecards.scorecard_generator import ScorecardGenerator

# 1. Engine initialisieren
engine = BacktestEngine("research/data/")

# 2. Parameter Sweep
result = quick_sweep(
    engine, "trend_pullback",
    trend_pullback.trend_pullback_strategy,
    trend_pullback.get_vps_safe_param_grid(),
    symbol="BTCUSDT"
)

# 3. Scorecard erstellen
gen = ScorecardGenerator()
scorecard = gen.create(
    strategy_name="trend_pullback",
    hypothesis="Trend + Pullback = Continuation",
    dataset={"symbol": "BTCUSDT", "timeframe": "1h", ...},
    parameters=result.best_result['params'],
    backtest_results=result.best_result
)

gen.save(scorecard)
print(gen.summary(scorecard))
```

---

## 🔒 Safety

- Keine Live-Trading-Logik
- Keine komplexen Berechnungen ohne Timeout
- Keine Cluster-Annahmen
- Polars LazyFrames überall
- JSON statt DB für Ergebnisse

---

**Status:** 🟢 Phase 7 Initialisiert — Bereit für erste Tests
