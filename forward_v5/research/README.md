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
├── analyst.py                      → 🧠 KI Meta-Analyst (Einzeltool)
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

### 2. Full Workflow

```bash
# Ohne KI
python run_demo_strategy.py --strategy trend_pullback

# Mit KI-Analyse (empfohlen)
export OLLAMA_API_KEY='your-key-here'
python run_demo_strategy.py --strategy trend_pullback --analyze
```

### 3. Direkte KI-Analyse (optional)

```bash
# Falls Scorecard schon existiert
export OLLAMA_API_KEY='your-key-here'
python analyst.py --scorecard scorecards/demo_scorecard.json
# Output: scorecards/meta_analysis_[strategy]_[timestamp].json
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

**Ein Tool:** Eingebettet in `analyst.py` — nutzt Ollama Cloud / Kimi 2.5.

### Was der Analyst macht:

| Check | Bewertung |
|-------|-----------|
| Hypothese-Check | Logisch? Testbar? Bestätigt? |
| Datenqualität | Trades >30? Zeitraum abgedeckt? |
| Metriken | PF>1.5? DD<20%? WR>45%? |
| Walk-Forward | OOS stabil? Degradation <30%? |
| VPS-Fit | time<300s? memory<500MB? |
| Schwachstellen | Wann/wo verliert die Strategie? |

### Output-Form

```json
{
  "analyzed_at": "2026-04-05T13:30:00Z",
  "strategy_name": "trend_pullback",
  "analysis": {
    "hypothesis_valid": true,
    "data_quality": "GOOD",
    "metric_pass": true,
    "walk_forward_pass": true,
    "vps_fit": true,
    "weaknesses": ["Schwäche in Seitwärtsphasen"],
    "hypotheses_next": ["Volatility-Filter testen"],
    "verdict": "PASS",
    "reason": "Solide Performance, robuste Metriken",
    "confidence": 0.85
  }
}
```

### Konfiguration

```bash
# Required
export OLLAMA_API_KEY='your-key-here'

# Optional (defaults)
export OLLAMA_MODEL='kimi-k2.5'
export OLLAMA_TIMEOUT='30'
export OLLAMA_MAX_TOKENS='1000'
```

**Fallback:** Ohne `OLLAMA_API_KEY` wird eine heuristische Analyse durchgeführt.

---

## 📋 Vollständiger Workflow

```
┌────────────────────────────────────────────────────────────┐
│  PHASE 7 WORKFLOW                                          │
├────────────────────────────────────────────────────────────┤
│  1. Hypothese formulieren                                  │
│     └─ trend_pullback: "EMA above + RSI oversold = entry"   │
│                                                            │
│  2. Daten prüfen                                            │
│     └─ OHLCV Parquet in data/                              │
│     └─ python generate_dummy_data.py (Demo)             │
│                                                            │
│  3. Strategie testen                                     │
│     └─ python run_demo_strategy.py --strategy [name]     │
│     └─ Output: Scorecard JSON                              │
│                                                            │
│  4. (Optional) KI-Analyse                                  │
│     └─ export OLLAMA_API_KEY=...                          │
│     └─ --analyze Flag bei run_demo_strategy.py            │
│     └─ oder: python analyst.py --scorecard [file]         │
│     └─ Output: meta_analysis_[strategy]_[ts].json         │
│                                                            │
│  5. Bewertung                                              │
│     └─ Verdict: PASS / FAIL / TWEAK / INCONCLUSIVE        │
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

```bash
$ python run_demo_strategy.py --strategy mean_reversion_panic --analyze

╔════════════════════════════════════════════════════════════╗
║  PHASE 7: Strategy Lab — Research Workflow                   ║
╚════════════════════════════════════════════════════════════╝

Selected Strategy: mean_reversion_panic
KI Analyst: ✓ Available (Kimi 2.5)
...

Demo: Parameter Sweep (mean_reversion_panic)
============================================================
Strategy: mean_reversion_panic
Grid: 12 combinations (VPS-Safe)
[1/12] Testing: {...} ✓ Return: 8.4%, Trades: 23
...

✓ Sweep Complete:
  Total: 12
  Completed: 11

╔══════════════════════════════════════════════════════════╗
║  SCORECARD: mean_reversion_panic                         ║
╠══════════════════════════════════════════════════════════╣
║  Verdict: PASS                                           ║
║  Return:    12.50%                                       ║
║  Drawdown:   -6.20%                                      ║
╚══════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════╗
║  KI META-ANALYST REPORT                                  ║
╠══════════════════════════════════════════════════════════╣
║  Verdict:     ✅ PASS                                    ║
║  Konfidenz:   85%                                        ║
╠══════════════════════════════════════════════════════════╣
║  CHECKS                                                  ║
║    Hypothese:    ✓ Gültig                                ║
║    Daten:        GOOD (45 Trades über 12 Monate)        ║
║    Metriken:     ✓ Pass                                  ║
║    Walk-Forward: ✓ OOS: 12% Degradation                ║
║    VPS-Fit:      ✓ Tauglich                              ║
╠══════════════════════════════════════════════════════════╣
║  NÄCHSTE HYPOTHESEN (max 3)                            ║
║    1. Volatility-Filter testen                          ║
║    2. Exit-Regel verschärfen                            ║
╚══════════════════════════════════════════════════════════╝

Workflow Complete!

Artifacts:
  📄 Scorecard: scorecards/scorecard_mean_reversion_panic.json
  🧠 Meta-Analysis: scorecards/meta_analysis_mean_reversion_panic_2026...

Verdict: PASS
✅ Strategy PASSED — Integrate into forward_v5
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

## Status: 🟢 Phase 7 Komplett

| Komponente | Status |
|------------|--------|
| Backtest Engine | ✅ Fees, Slippage, Equity Curve |
| Parameter Sweep | ✅ Max 50, VPS-safe |
| Walk-Forward | ✅ Robustness Scoring |
| 3 Strategien | ✅ Testfähig |
| Scorecards | ✅ Harte Verdicts |
| KI Analyst | ✅ Einzeltool, integriert |

**Phase 7:** Vollständiger Research-Ablauf bereit.

**Next:** Echte Scorecards generieren → Mit KI-Analyst bewerten → Beste zu Phase 8.
