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
- Strong Trend (Score >70): weiter Trail 2.5-3%, Position atmen lassen
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
- **Stufe 2** — baut auf Regime-Score auf

---

### Sniper-Upgrade (Modus B)
- Kein separater Pool — Sniper **upgraded** den besten V1-Trade
- V1 entscheidet welcher Trade. Sniper-Bedingungen erfüllt → Hebel von 1.8x auf 4-5x
- Keine doppelte Position auf demselben Asset
- **Max 30€ allocated** für Sniper-Trade (statt 16.67€), × 5x = 150€ Notional
- Restliche 70€ verteilen sich auf V1-Positionen normal
- Kein Kapitalkonflikt

---

## Sniper-Exit: Vier Regeln

| Signal | Aktion |
|--------|--------|
| Regime-Score fällt < 50 | Sofort raus (Trend bricht) |
| Regime-Score fällt 50-70 | Downgrade auf V1-Hebel, Trail auf 2.0% |
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
- Regime-Score fällt auf 50-70 → Downgrade auf V1-Hebel
- Volatility-Parität gilt für V1, Sniper ist fix 5x
- **Sniper-Circuit-Breaker**: 3 aufeinanderfolgende Sniper-Verluste → Sniper pausiert für 48h, dann Resume

### Warum 4-5x vertretbar
- Regime-Score > 70 filtert ~70% aller Bars raus (nur Strong Trend)
- Asset-Ranking Top-2 = stärkster Momentum in stärkstem Trend
- DD pro Trade: max 3.75% des Portfolios (2.5% Trail × 5x auf 30€ allocated)
- V1-DD von 14% kommt aus Range-Trades — die fallen komplett weg

### Scharfmacher
Sniper ist standardmäßig AUS. Erst aktivieren wenn Regime-Score + Asset-Ranking im Backtest bewiesen sind.

---

## V2 Module

### Modul 1: Regime Detection (Stufe 1 — Kern)

**Ziel**: Jedes Candle einen Regime-Score 0-100 berechnen

**Score-Formel (Basis)**:
```
regime_score = (
  adx_score * 0.45 +     # ADX normalisiert auf 0-100
  vol_score * 0.25 +     # ATR-Ratio: niedrig=stabil, hoch=crash
  slope_score * 0.30     # EMA-Slope normalisiert auf 0-100
)
```

**Komponenten**:
| Signal | Quelle | Berechnung | Range |
|--------|--------|------------|-------|
| adx_score | ADX-14 | `min(adx / 50 * 100, 100)` | 0-100 |
| vol_score | ATR-Ratio | `ATR / ATR_SMA20` → invertiert | 0-100 |
| slope_score | EMA-50 | Steigung normalisiert | 0-100 |

**Gewichtung**: 45/25/30 — ADX dominiert weil Trendstärke der wichtigste Indikator ist

**Regime-Mapping**:
| Score | Regime | Aktion |
|-------|--------|--------|
| 0-30 | Range | Kein Entry, bestehende Positionen tighten |
| 30-70 | Trend | V1 normal traden |
| 70-100 | Strong Trend | Sniper-Modul kann aktivieren |

**Gemma4-Einsatz (Stufe 1)**:
- Kein KI-Regime in Stufe 1 — deterministische Formel reicht
- Gemma4 evaluiert später ob KI-Regime die Formel verbessern kann (Stufe 3)
- Vorteil: Deterministisch, reproduzierbar, kein API-Call pro Candle

**Backtest-Validierung**:
- Gleicher Gate wie V1: ≥75% Pass-Rate, CL≤12, DD≤20%
- Vergleiche: Regime-gefiltert vs ungefiltert
- Erwartung: ~70% weniger Trades, ~50% weniger DD

---

### Modul 2: Sentiment (Stufe 3 — Advanced)

**Ziel**: KI-basierter Kill-Switch bei Crash-Szenarien

**Pipeline**:
```
News API → Gemma4 JSON-Mode → Sentiment Score (0-100)
                                        ↓
                                Position Sizing Filter
                                Score ≤ 30 → Half Position
                                Score ≤ 15 → No Entry
                                Score > 50 → Full Position
```

**Warum Gemma4, nicht GLM**:
- Lokal, keine API-Kosten, keine Rate-Limits
- Sentiment-Parsing ist einfacher als Strategy-Design
- JSON-Mode funktioniert stabil auf Gemma4:31b
- Keine Latenz — lokal in <1s statt Cloud-Roundtrip

**Warum erst Stufe 3**:
- Sentiment ist ein Filter, kein Motor
- Regime-Score (Stufe 1) filtert bereits Range-Trades raus
- Sentiment fängt Black-Swans die Indikatoren verpassen
- Aber: Black-Swans sind selten → schwer zu backtesten → braucht Live-Validierung

**Fail-Safe**:
- Gemma4 fail → Score = 50 (neutral)
- API timeout → letzter Score beibehalten (decay nach 4h → 50)
- Widersprüchliche Signale → konservativster Score
- Niemals Upsizing — Sentiment kann nur verkleinern

---

### Modul 3: Asset Selection (Stufe 3 — Advanced)

**Ziel**: ROC-Ranking der Assets statt Equal-weight

**Basis (Stufe 1)**:
- ROC-5/10/20 berechnen
- Top 2-3 Assets bevorzugen
- Rein mathematisch, keine KI nötig

**Gemma4-Erweiterung (Stufe 3)**:
- Momentum-Kontext verstehen: "BTC rallyt wegen ETF-News" vs. "BTC rallyt technisch"
- News-Attribution: Welches Asset profitiert von welchem Event?
- Nur wenn ROC-Baseline bewiesen ist

---

### Modul 4: Risk Management (Stufe 1-2)

**Kein KI-Einsatz** — das ist Mathematik:

| DD-Schwelle | Aktion |
|-------------|--------|
| > 10% | Alle Positionen halbieren |
| > 15% | Keine neuen Entries (SOFT_PAUSE) |
| > 20% | KILL (alles schließen) |

**Korrelations-Filter (Stufe 2)**:
- Max 2 stark korrelierte Positionen gleichzeitig
- Stufe 3: Dynamische Rolling-Correlation statt statische Regel

**Circuit-Breaker (Stufe 1)**:
- 3 aufeinanderfolgende Sniper-Verluste → 48h Sniper-Pause

---

### Modul 5: Sniper (Stufe 1 — Kern)

**Siehe oben** — detailliert ausgearbeitet im Sniper-Modul Abschnitt

Entry-Stack: Regime > 70, Asset-Ranking #1-2, Sentiment > 50, MACD, EMA-Slope > 0.5
Exit: Trail 2.5%, Max Hold 24h, Regime < 50 = raus, Regime 50-70 = Downgrade
Capital: max 30€ × 5x = 150€ Notional
Circuit-Breaker: 3 Verluste → 48h Pause

---

### KI-Einsatz-Strategie

| Modul | Stufe | KI | Warum |
|-------|-------|----|-------|
| Regime Detection | 1 | Nein | Deterministisch reicht, reproduzierbar |
| Risk Management | 1-2 | Nein | Mathematik, keine Meinung |
| Sniper | 1 | Nein | Regelbasiert, Regime-Score als Input |
| Sentiment | 3 | **Gemma4** | News-Parsing, JSON-Mode, lokal |
| Asset Selection | 3 | **Gemma4** | Momentum-Kontext, erst nach ROC-Baseline |
| Korrelationsmatrix | 3 | Nein | Statistik, Rolling-Correlation |

**Warum Gemma4 statt GLM-5.1**:
- Lokal → keine API-Kosten, keine Rate-Limits
- Schnell → <1s inferenz statt Cloud-Roundtrip
- Ausreichend → Sentiment-Parsing braucht kein Flagship-Modell
- Deterministisch → gleicher Input = gleicher Output (JSON-Mode)
- GLM-5.1 cloud = Reserve für komplexe Aufgaben (z.B. ADR-Formulierung, Code-Review)

---

## Alpha Stack V2 (Priorität, nach Stufen)

**Stufe 1 — Kern**
| # | Feature | Warum |
|---|---------|-------|
| 1 | Regime-Score (ADX+ATR+Slope) | Filtert ~70% Range-Trades raus |
| 2 | Sniper-Modul (4-5x) | Conviction-Upgrade auf Top-Asset |
| 3 | DD-basierte Positionsreduktion | 10/15/20% Stufen |

**Stufe 2 — Enhancement**
| # | Feature | Warum |
|---|---------|-------|
| 4 | Volatility-Parität | Riskoparität statt Equal-Weight |
| 5 | Partial Exits (V1 only) | Gewinn sichern, Upside offen |
| 6 | Re-Entry Logik | 1h Cooldown, dann wieder möglich |
| 7 | Korrelations-Filter | max 2 korrelierte Positionen |
| 8 | Regime-basierter Exit | Trail dynamisch nach Regime-Score |

**Stufe 3 — Advanced**
| # | Feature | Warum |
|---|---------|-------|
| 9 | Sentiment Kill-Switch | Crash-Schutz, KI-Filter |
| 10 | On-Chain Regime-Filter | Exchange Netflow |
| 11 | Limit-Orders | Fee-Reduktion |
| 12 | Asset-Ranking (ROC) | Stärkster Momentum bevorzugen |
| 13 | Dynamische Korrelationsmatrix | Statt max 2-Regel |

**Abgelehnt**
| Feature | Warum |
|---------|-------|
| ATR-Stops | Kein Improvement bewiesen |
| Kelly Criterion | Win-Rate zu instabil |

---

## Was V2 NICHT ist

- Kein Indikator-Salat (mehr Indikatoren ≠ bessere Ergebnisse)
- Keine KI-Entscheidung über Trade-Richtung (nur Filter)
- Keine Short-Positionen (V1 bleibt Long-Only)
- Kein Hyper-Optimization der Backtest-Parameter
- Kein automatisches Upsizing bei "gutem Sentiment"

## V2 Implementierung — 3 Stufen, 1 Release

### Stufe 1: Kern (Regime + Sniper)
- Regime-Score (ADX + ATR-Ratio + EMA-Slope)
- Sniper-Modul (4-5x Upgrade auf Top-Asset)
- DD-basierte Positionsreduktion
- **Gate**: Regime+Sniper Sharpe > V1, DD < V1

### Stufe 2: Enhancement
- Volatility-Parität (statt Leverage-Tiers)
- Partial Exits (V1 only)
- Re-Entry Logik
- Korrelations-Filter (max 2)
- Regime-basierter Exit (Trail dynamisch)
- **Gate**: Gesamt-DD verbessert, Sharpe ≥ Stufe 1

### Stufe 3: Advanced
- Sentiment Kill-Switch
- On-Chain Regime-Filter
- Limit-Orders
- Dynamische Korrelationsmatrix
- Asset-Ranking (ROC)
- **Gate**: Vollständiges V2 durchs Tor, dann LIVE

Alle 3 Stufen = V2. Kein V3. Nach Stufe 3 → Live gehen.