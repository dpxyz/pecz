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

### 6. Korrelations-Filter
- V1 öffnet oft 5+ LONGs gleichzeitig — alle BTC-korreliert
- V2: max 2 stark korrelierte Positionen gleichzeitig
- Reduziert DD massiv ohne Return zu schneiden

### 7. Re-Entry Logik
- V1: Nach Exit → 1h Cooldown → wenn MACD+EMA noch aligned → Re-Entry möglich
- Sniper: Kein Re-Entry nach Max Hold oder Regime-Exit. Score muss erst < 70 fallen und wieder > 70 steigen für einen neuen Sniper-Trade.

### 8. Regime-basierter Exit
- Strong Trend (Score >65): weiter Trail 2.5-3%, Position atmen lassen
- Weak Trend (Score 30-50): tighter Trail 1.5%, schneller raus
- Hoher Regime-Score = höhere Conviction = mehr Raum

### 9. Partial Exits
- 50% bei Trail nehmen, 50% laufen lassen
- Trend-following-Klassiker: Gewinn sichern, aber Raum für weiteren Upside
- Komplexer zu implementieren, aber messbar besser als Voll-Exit
- **Nur für V1-Trades** — Sniper hat 100% Entry/Exit
- Sniper-Exit: Regime < 50 = komplett raus, Trail 2.5% = komplett raus, kein Halbschritt bei 5x Hebel

### 10. DD-basierte Positionsreduktion
- Portfolio-DD > 10% → alle Positionen halbieren
- Portfolio-DD > 15% → keine neuen Entries (SOFT_PAUSE)
- Portfolio-DD > 20% → KILL (alles schließen)
- V2 macht das glatter als V1 Risk Guard

### 11. Limit-Orders statt Market
- Hyperliquid Maker 0.01% vs Taker 0.035%
- Bei 6 Trades/Tag: ~1€/Monat gespart auf 100€
- Auf 1000€+ relevant
- Entry = Limit an EMA-50, Exit = Limit an Trail

### 12. Dynamische Korrelationsmatrix
- Rolling-Correlation berechnen (20-Bar-Window)
- Entry blocken wenn Korrelation > 0.7 mit bestehender Position
- Besser als willkürliche "max 2"-Regel
- V3-Kandidat, nicht V2-Start

---

### Sniper-Upgrade (Modus B)
- Kein separater Pool — Sniper **upgraded** den besten V1-Trade
- V1 entscheidet welcher Trade. Sniper-Bedingungen erfüllt → Hebel von 1.8x auf 4-5x
- Keine doppelte Position auf demselben Asset
- **Max 30€ allocated** für Sniper-Trade (statt 16.67€), × 5x = 150€ Notional
- Restliche 70€ verteilen sich auf V1-Positionen normal
- Kein Kapitalkonflikt

---

## Sniper-Exit: Drei Regeln

| Signal | Aktion |
|--------|--------|
| Regime-Score fällt < 50 | Sofort raus (Trend bricht) |
| Regime-Score fällt 50-65 | Downgrade auf V1-Hebel, Trail auf 2.0% |
| Trailing Stop 2.5% | Standard-Exit im Strong Trend |
| Max Hold 24h | Raus, egal was passiert |

Sniper-Trail = 2.5% (nicht 1.5%), weil Sniper im Strong Trend schießt → mehr Raum zum Atmen.
DD-Limit: max 10% Portfolio-DD aus Sniper-Trades. Worst-case 1 Trade = 2.5% Trail × 5x = 12.5% auf 30€ = 3.75€ = 3.75% des Gesamtportfolios. Heißt: 1 Sniper-Verlust verbraucht ~38% des DD-Budgets. Max 2-3 Sniper-Verluste bevor Sniper pausiert.

---

## V2 Validierung

### 3-Level-Test

| Level | Kriterium | Threshold |
|-------|-----------|-----------|
| Backtest | Sniper Sharpe | > V1 Baseline Sharpe |
| Backtest | Sniper DD | < V1 Baseline DD |
| Paper | ≥5 Sniper-Trades | in 14 Tagen |
| Paper | Sniper-PnL | positiv oder < 3% Portfolio-DD |

Sniper schießt selten — fair. Wenn in 14 Tagen <3 Signale, Verlängerung auf 21 Tage.

---

## Sniper-Modul

### Kernidee
Kein separates Modul — **Upgrade** für den besten V1-Trade. Wenn alle Signale aligned sind, wird das Top-Asset von 1.8x auf 4-5x gehoben. Die anderen 5 Assets laufen normal.

### Modus B: Sniper als V1-Upgrade
- V1 scannt alle 6 Assets normal
- Sniper-Bedingungen erfüllt → Top-Asset wird NICHT mit V1-Hebel tradet, sondern mit 4-5x
- Die anderen 5 Assets: normale V1-Regeln
- Kein Kapitalkonflikt — das Top-Asset wird nur "aufgewertet"

### Entry-Stack (ALLE müssen grün sein)
1. Regime-Score > 70 (Strong Trend, nicht nur „irgendein Trend“)
2. Asset-Ranking: nur #1 oder #2
3. Sentiment > 50 (kein Panic)
4. MACD-Entry (Trigger bleibt gleich)
5. EMA-Slope > 0.5 (Trend hat Geschwindigkeit)

### Leverage
- V1: 1.0-1.8x (gestreut, defensive)
- Sniper: **4-5x** (1 Position, maximale Conviction)
- Nicht 2-3x — das wäre V1 mit Filter

### Risiko-Kontrolle
- Nur 1 Position gleichzeitig (Konzentration)
- Trailing Stop: 2.5% (Strong Trend = mehr Raum, nicht enger)
- Max Hold: 24h statt 48h (Conviction hat Zeitlimit)
- Capital: max 30€ allocated × 5x = 150€ Notional
- Regime-Score fällt auf 50-65 → Downgrade auf V1-Hebel
- Volatility-Parität gilt für V1, Sniper ist fix 5x
- **Sniper-Circuit-Breaker**: 3 aufeinanderfolgende Sniper-Verluste → Sniper pausiert für 48h, dann Resume

### Warum 4-5x vertretbar
- Regime-Score > 65 filtert ~70% aller Bars raus (nur Strong Trend)
- Asset-Ranking Top-2 = stärkster Momentum in stärkstem Trend
- DD pro Trade: ~7-8% bei 2.5% Trail × 5x = vertretbar
- V1-DD von 14% kommt aus Range-Trades — die fallen komplett weg

### Scharfmacher
Sniper ist standardmäßig AUS. Erst aktivieren wenn Regime-Score + Asset-Ranking im Backtest bewiesen sind.

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
| 1 | Regime-Score (ADX+ATR+Slope) | **Hoch** | Filtert ~70% Range-Trades raus |
| 2 | Asset-Ranking (ROC) | **Hoch** | Bessere Asset-Auswahl bei >1 Signal |
| 3 | Sniper-Modul (4-5x) | **Hoch** | Conviction-Upgrade auf Top-Asset |
| 4 | Volatility-Parität | **Mittel** | Riskoparität statt Equal-Weight |
| 5 | Partial Exits (V1) | **Mittel** | Gewinn sichern, Upside offen halten |
| 6 | Limit-Orders | **Mittel** | Fee-Reduktion, weniger Slippage |
| 7 | Korrelations-Filter | Niedrig | max 2 korrelierte Positionen |
| 8 | HTF-Alignment | Niedrig | 4h Bestätigung vor 1h Entry |
| 9 | Sentiment Kill-Switch | Niedrig | Crash-Schutz, V3-Kandidat |
| — | ~~ATR-Stops~~ | Abgelehnt | Kein Improvement bewiesen |
| — | ~~Kelly Criterion~~ | Abgelehnt | Win-Rate zu instabil |

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