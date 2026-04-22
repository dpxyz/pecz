# V2 Strategy Design — Sentiment & Regime

**Status:** PLANNED (post Paper Trading)  
**ADR:** Will be formalized as ADR-008 after Phase 8

## V2 Design Principles

### 1. Regime-Erkennung als Herzstück
- Trend / Range / Crash → **nicht in Range handeln**
- ADX+EMA filtert bereits → V2 macht das explizit als Score
- Regime-Score 0-100 statt binärer Filter

### 2. Volatility-Parity statt Equal-Weight
- Risiko pro Trade konstant, nicht Kapital
- High-Vol Assets (AVAX) → kleinere Position
- Low-Vol Assets (BTC) → größere Position
- Ersetzt die starren Leverage-Tiers

### 3. Sentiment als Kill-Switch (Score 0-100)
- **KI als Signalgeber**, nicht als Richter
- JSON-Mode für deterministische Extraktion
- Fail-safe: Bei Fehler → ignorieren (nicht handeln ist sicherer)
- Nur Downsizing, nie Upsizing
- Sentiment Score ≤ 30 → Position halbieren
- Sentiment Score ≤ 15 → kein neuer Entry

### 4. On-Chain als Regime-Filter
- Exchange Netflow 7-14d Aggregation
- Nicht: Whale-Tracking, einzelne Transactions
- Großflächiger Netflow → Regime-Wechsel Signal

### 5. Kein Indikatoren-Salat
- Bessere Regeln, nicht mehr Indikatoren
- Jeder neue Indikator muss Pass-Rate verbessern
- ATR-Filter abgelehnt (bewiesen: kein Improvement)

---

## Regime-Score — Proof of Concept

### Kombination
| Komponente | Was | Range  |
|------------|-----|--------|
| ADX-14 | Trendstärke | 0-100  |
| ATR-Ratio | ATR / ATR_SMA20 (Volatilitäts-Explosion) | 0.5-2.0 |
| EMA-Slope | Steigung der EMA-50 | -1 bis +1 |

### Mapping
- **< 30**: Range → kein Trade, bestehende tighten
- **30-70**: Trend → normal traden (V1 Baseline)
- **> 70**: Strong Trend → Position vergrößern (V2 Alpha)

### Warum
- ADX allein = binär (drüber/drunter). Score = kontinuierlich.
- ATR-Ratio fängt Crash-Regime (plötzliche Vol-Explosion)
- EMA-Slope unterscheidet Trend von flat-Trend

## Asset-Ranking (Alpha Stack #1)

- ROC-Ranking: Welches Asset hat stärksten Momentum?
- Statt 6 Assets gleich: Top 3-4 bevorzugen
- Reduziert Noise von schwachen Signalen
- Kombinierbar mit Regime-Score: nur Top-Assets in Trend-Phasen

---

## Sentiment Architecture

### Data Sources (Priority)

| Priority | Source | Format | Update |
|----------|--------|--------|--------|
| **Hoch** | Crypto News (CoinDesk, CryptoSlate) | KI-Score 0-100 | Echtzeit |
| **Mittel** | Macro (Fed, CPI, DXY) | Regime-Flag | Täglich |
| **Mittel** | On-Chain (Exchange Netflow) | Flow-Rate | Täglich |
| **Niedrig** | Social (Fear&Greed, Reddit) | Index-Wert | Stündlich |

### Processing Pipeline

```
News API → KI Extraction (JSON-Mode) → Sentiment Score (0-100)
                                            ↓
                                    Position Sizing Filter
                                    Score ≤ 30 → Half Position
                                    Score ≤ 15 → No Entry
                                    Score > 50 → Full Position
```

### Fail-Safe Rules

1. **KI-Extraction fails** → Score = 50 (neutral, kein Einfluss)
2. **API timeout** → Letzter Score beibehalten (decay nach 4h → 50)
3. **Widersprüchliche Signale** → Konservativster Score gewinnt
4. **Niemals Upsizing** → Sentiment kann nur verkleinern, nie vergrößern

---

## Alpha Stack V2 (Priorität)

| # | Feature | Priorität | Erwarteter Impact |
|---|---------|-----------|-------------------|
| 1 | Asset-Ranking (ROC) | **Hoch** | Bessere Asset-Auswahl bei >1 Signal |
| 2 | ADX-based Sizing | **Hoch** | 0.5x bei ADX 20-30, 1.5x bei >40 |
| 3 | 2x Leverage (BTC/ETH) | Mittel | +40% Return, DD noch akzeptabel |
| 4 | Limit-Orders | Mittel | Fee-Reduktion, weniger Slippage |
| 5 | HTF-Alignment | Niedrig | 4h Bestätigung vor 1h Entry |
| 6 | ~~ATR-Stops~~ | Abgelehnt | Kein Improvement bewiesen |
| 7 | ~~Kelly Criterion~~ | Abgelehnt | Win-Rate zu instabil |

---

## Was V2 NICHT ist

- Kein Indikator-Salat (mehr Indikatoren ≠ bessere Ergebnisse)
- Keine KI-Entscheidung über Trade-Richtung (nur Filter)
- Keine Short-Positionen (V1 bleibt Long-Only)
- Kein Hyper-Optimization der Backtest-Parameter
- Kein automatisches Upsizing bei "gutem Sentiment"

## Zeitplan

| Milestone | Timing | Voraussetzung |
|-----------|--------|---------------|
| ADR-008 schreiben | Nach Phase 8 | Paper Trading abgeschlossen |
| Sentiment Prototype | Phase 10 Start | Phase 9 bestanden |
| Integration Test | Phase 10 Mitte | Prototype läuft |
| Paper Trading V2 | Phase 10 Ende | Integration bestanden |