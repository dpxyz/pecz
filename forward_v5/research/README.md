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
├── data/                           # OHLCV Parquet-Dateien
├── backtest/
│   ├── backtest_engine.py          → Kern-Backtesting
│   ├── parameter_sweep.py          ← Max 50 Kombinationen
│   └── walk_forward.py             ← Train/Validate/OOS
├── strategy_lab/
│   ├── trend_pullback.py            ⭐ Ready
│   ├── mean_reversion_panic.py    ⭐ Ready
│   ├── multi_asset_selector.py      ⭐ Ready
│   ├── rsi_regime_filter.py         → Filter-Baustein
│   └── volatility_filter.py         → Filter-Baustein
├── scorecards/
│   ├── scorecard_schema.json         → JSON Standard
│   ├── scorecard_generator.py      → Generator
│   └── *.json                        → Ergebnisse
├── analyst.py                      → 🧠 KI Meta-Analyst (Kimi 2.5)
├── run_demo_strategy.py            → Full Workflow
├── generate_dummy_data.py          → Test-Daten
└── README.md                        → Diese Datei
```

---

## 🚀 Quick Start

### 1. Daten vorbereiten

```bash
cd forward_v5/research

# Option A: Echte Daten (Parquet)
#    data/BTCUSDT_1h.parquet
#    Spalten: timestamp, open, high, low, close, volume

# Option B: Demo-Daten generieren
python generate_dummy_data.py --bars 5000
```

### 2. Full Workflow (ohne KI)

```bash
python run_demo_strategy.py --strategy trend_pullback
```

### 3. Full Workflow (mit KI-Analyst)

```bash
# Ollama Cloud API Key setzen
export OLLAMA_API_KEY='your-key-here'

# Optional: Custom endpoint
export OLLAMA_API_URL='https://api.ollama.com/v1/chat/completions'
export OLLAMA_MODEL='kimi-k2.5'

# Mit Analyse
python run_demo_strategy.py --strategy trend_pullback --analyze
```

---

## 🧪 Die 3 Strategien

| Strategie | Logik | VPS-Safe Grid | Code |
|-----------|-------|---------------|------|
| **trend_pullback** | EMA-Trend + RSI-Oversold | 9 Kombinationen | `strategy_lab/trend_pullback.py` |
| **mean_reversion_panic** | Z-Score Threshold | 12 Kombinationen | `strategy_lab/mean_reversion_panic.py` |
| **multi_asset_selector** | Momentum Ranking | 12 Kombinationen | `strategy_lab/multi_asset_selector.py` |

**Filter-Module:**
- `rsi_regime_filter.py` — Marktregime-Erkennung
- `volatility_filter.py` — ATR-basierte Filterung

---

## 🧠 KI Meta-Analyst

Nutzt **Ollama Cloud** mit **Kimi 2.5** für kontextuelle Analyse von Scorecards.

### Was der Analyst macht:

| Task | Output |
|------|--------|
| Hypothesen-Analyse | Ist die Hypothese logisch/testbar? |
| Schwachstellen-Scan | Kleinste Stichprobe, überflüssigste Annahme |
| Verbesserungsvorschläge | Genau 3 konkrete Änderungen |
| Nächste Experimente | Priorisierte Forschungsrichtung |

### Was der Analyst NICHT macht:

❌ Keine Backtests berechnen  
❌ Keine Trades ausführen  
❌ Keine Architekturentscheidungen  
❌ Keine Strategien ohne Datenbasis freisprechen  

### Konfiguration

```bash
# Required
export OLLAMA_API_KEY='your-api-key'

# Optional (defaults)
export OLLAMA_API_URL='https://api.ollama.com/v1/chat/completions'
export OLLAMA_MODEL='kimi-k2.5'
export OLLAMA_TIMEOUT='30'        # Sekunden
export OLLAMA_MAX_TOKENS='800'    # Kompakte Antworten
```

### Standalone Analyst

```python
from analyst import KIAnalyst
import json

# Lade Scorecard
with open('scorecards/scorecard_trend_pullback.json', 'r') as f:
    scorecard = json.load(f)

# Analysiere
analyst = KIAnalyst()
if analyst.available():
    report = analyst.analyze_scorecard(scorecard)
    print(report.summary())
    report.save('analyst_report.json')
```

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
    "trade_count": 45,
    "sharpe_ratio": 1.2,
    "stability_score": 75
  },
  "walk_forward": {
    "n_windows": 3,
    "robustness_score": 75,
    "passed": true
  },
  "resource_usage": {
    "execution_time_ms": 4500,
    "memory_peak_mb": 128.5,
    "vps_safe": true
  },
  "verdict": "PASS",
  "next_actions": ["Integrate into system", "Paper trade"]
}
```

**Verdicts:**
- **PASS** → Weiter zu Phase 8 (Economics)
- **FAIL** → Hypothese überarbeiten
- **INCONCLUSIVE** → Mehr Daten, kein Go
- **REJECT_VPS_UNSAFE** → Zu schwer, verworfen

---

## 📋 Vollständiger Workflow

```
┌────────────────────────────────────────────────────────────┐
│  PHASE 7 WORKFLOW                                          │
├────────────────────────────────────────────────────────────┤
│  1. Hypothese formulieren                                  │
│     └─ trend_pullback: "EMA above + RSI oversold = entry" │
│                                                            │
│  2. Daten prüfen                                            │
│     └─ OHLCV Parquet in data/                              │
│     └─ python generate_dummy_data.py (falls nötig)      │
│                                                            │
│  3. Strategie implementieren                               │
│     └─ strategy_lab/[name].py                              │
│     └─ get_vps_safe_param_grid(): max 50 kombos          │
│                                                            │
│  4. Parameter Sweep                                        │
│     └─ python run_demo_strategy.py --strategy [name]     │
│     └─ Output: Scorecard JSON                              │
│                                                            │
│  5. (Optional) KI-Analyse                                  │
│     └─ export OLLAMA_API_KEY=...                          │
│     └─ python run_demo_strategy.py --strategy [name] \\│
│        --analyze                                           │
│     └─ Output: Analyst Report JSON                         │
│                                                            │
│  6. Scorecard bewerten                                     │
│     └─ Verdict: PASS / FAIL / INCONCLUSIVE                 │
│     └─ Bei PASS: Weiter zu Phase 8                         │
└────────────────────────────────────────────────────────────┘
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
| KI Analyst Timeout | 30s | Kein Hängenbleiben |

---

## 🔍 Beispiel-Ausgabe

### Standard Workflow

```bash
$ python run_demo_strategy.py --strategy mean_reversion_panic

╔════════════════════════════════════════════════════════════╗
║  PHASE 7: Strategy Lab — Research Workflow                   ║
╚════════════════════════════════════════════════════════════╝

Selected Strategy: mean_reversion_panic
Description: Z-Score Panic Recovery
...

Demo: Parameter Sweep (mean_reversion_panic)
============================================================
Strategy: mean_reversion_panic
Grid: 12 combinations (VPS-Safe)
------------------------------------------------------------
[1/12] Testing: {'sma_period': 40, 'z_entry_long': -2.5} ✓ Return: 8.4%, Trades: 23
...

✓ Sweep Complete:
  Total: 12
  Completed: 11
  Failed: 1
  Time: 2847ms

🏆 Best Result:
  Params: {'sma_period': 50, 'z_entry_long': -2.0, ...}
  Return: 12.5%
  Drawdown: -6.2%

╔══════════════════════════════════════════════════════════╗
║  SCORECARD: mean_reversion_panic                         ║
╠══════════════════════════════════════════════════════════╣
║  Verdict: PASS                                           ║
║  Return:    12.50%                                       ║
║  Drawdown:   -6.20%                                      ║
║  Trades:    38                                           ║
║  W-F Robustness: 75                                      ║
╚══════════════════════════════════════════════════════════╝

Workflow Complete!

Artifacts:
  📄 Scorecard: scorecards/scorecard_mean_reversion_panic.json

Verdict: PASS
✅ Strategy PASSED — Consider integration
```

### Mit KI-Analyst

```bash
$ export OLLAMA_API_KEY='...'
$ python run_demo_strategy.py --analyze

...

╔══════════════════════════════════════════════════════════╗
║  KI ANALYST REPORT: trend_pullback                       ║
╠══════════════════════════════════════════════════════════╣
║  Verdict: PASS                                           ║
╠══════════════════════════════════════════════════════════╣
HYPOTHESIS ANALYSIS:
The hypothesis is testable: EMA + RSI is a classic setup. Sample
size (38 trades) is borderline adequate. No obvious overfit.

IMPROVEMENTS:
1. Test RSI threshold 35 vs 45 → Expect smoother entries
2. Add ATR-based position sizing → Expect better risk control
3. Run on 4h timeframe → Expect fewer noise trades

NEXT EXPERIMENTS:
  1. Parameter Sweep: rsi_threshold_long in [35, 45]
  2. Add volatility_filter for position sizing
  3. Compare 1h vs 4h performance

╚══════════════════════════════════════════════════════════╝

✓ Report saved: scorecards/scorecard_trend_pullback_analyst_report.json
```

---

## 🔒 Safety

- Keine Live-Trading-Logik in Research
- Keine komplexen Berechnungen ohne Timeout
- Keine Cluster-Annahmen
- Polars LazyFrames überall
- JSON statt DB für Ergebnisse
- KI nur als Meta-Analyst, nicht als Entscheider

---

## Status: 🟢 Phase 7 Bereit

- ✅ Backtest Engine (fees, slippage, equity curve)
- ✅ Parameter Sweep (max 50, VPS-safe)
- ✅ Walk-Forward (robustness scoring)
- ✅ 3 Strategien (testfähig)
- ✅ Scorecards (harte Verdicts)
- ✅ KI Analyst (Ollama Cloud / Kimi 2.5)

**Ready für erste echte Scorecards.**
