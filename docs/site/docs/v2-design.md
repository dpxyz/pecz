# V2 Strategy Design — Der Oktopus 🐙

**Status:** PLANNED (post Paper Trading)
**ADR:** Will be formalized as ADR-008 after Phase 8

## Die Oktopus-Metapher

Der Oktopus ist die Identität unserer Strategie — nicht nur eine Metapher, sondern ein **Entscheidungsrahmen**.

- **8 Arme** = 6 Assets + Regime + Sentiment — alle Arme tasten **denselben Markt** ab, nur zuschlagen wenn alle Signale grün sind. Vielseitig wahrnehmend, fokussiert handelnd — nicht viele Eisen im Feuer, sondern viele Augen auf ein Ziel
- **3 Herzen** = Redundanz — Fail-Safes, Kill-Switches, Circuit-Breaker
- **Knochenlos** = anpassungsfähig — verhält sich in Range anders als im Trend (Regime-Erkennung)
- **Kamera-Augen** = sieht was andere nicht sehen — Regime-Score als 6. Sinn
- **Tintensäcke** = bei Gefahr Rückzug + Nebelwand — Kill-Switch, DD-Scaling, Circuit-Breaker
- **Solitär mit Schwarm-Prinzip** = ein Körper, dezentrale Sensorik — Arme entscheiden lokal, Kopf entscheidet global

**Der Oktopus-Test für neue Features:**
- Braucht der Oktopus einen 9. Arm? → Nein → Kein neuer Indikator
- Schützt die Tinte? → Ja → Kill-Switch
- Greift der Oktopus an? → Nein, er beobachtet und schlägt präzise zu → Sniper nur bei voller Conviction
- Schwimmt der Oktopus mit den Walen? → Nein, er drückt sich in die Ritze und wartet

---

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

**Score-Formel**:
```
regime_score = (
  adx_score * 0.45 +     # Trendstärke
  vol_score * 0.25 +     # Volatilitäts-Regime
  slope_score * 0.30 +   # Trend-Geschwindigkeit
  oi_score * 0.00        # Open Interest Change — ZU VALIDIEREN (aktuell 0%)
)
```

> **⚠️ OI Change = Hypothese, nicht bewiesen.** Weight steht auf 0% bis Backtest beweist dass es hilft. Wenn validiert: 10% (ADX→40%, Slope→25%). Siehe V2 Principle 5: Kein Indikatoren-Salat — jeder neue Input muss Pass-Rate verbessern.

**Komponenten im Detail**:

| Komponente | Quelle | Berechnung | Range |
|-----------|--------|------------|-------|
| adx_score | ADX-14 | `min(adx / 50 * 100, 100)` | 0-100 |
| vol_score | ATR-14 / ATR_SMA20 | Invertiert: stabil=100, crash=0 | 0-100 |
| slope_score | EMA-50 Steigung | `(slope / max_slope) * 100`, gekappt | 0-100 |

**ADX-Normalisierung**:
- ADX < 20 → Score 0-40 (Range)
- ADX 20-40 → Score 40-80 (Trend)
- ADX > 40 → Score 80-100 (Strong Trend)
- Kappung bei 100 → kein ADX-Wert kann Score dominieren

**Vol-Score Invertierung**:
- ATR-Ratio nahe 1.0 → volatil stabil → Score 80-100
- ATR-Ratio > 1.5 → Vol-Explosion (Crash) → Score 0-20
- ATR-Ratio < 0.7 → erstarrter Markt → Score 40-60
- Formel: `vol_score = max(0, min(100, 100 - abs(ratio - 1.0) * 80))`

**Slope-Normalisierung**:
- `slope = (ema_50[t] - ema_50[t-1]) / ema_50[t-1]`
- Normalisiert auf letzten 20 Bars: `slope_pct = slope / max(abs(slope_20)) * 100`
- Kappung: `min(max(slope_pct, 0), 100)` → negativer Slope = 0

**OI-Score (Open Interest Change)**:
- `oi_change = (oi_now - oi_24h_ago) / oi_24h_ago * 100`
- OI steigt + Preis steigt = echtes Kapital → Score 80-100
- OI steigt + Preis fällt = Short-Aufbau → Score 40-60 (Vorsicht)
- OI fällt + Preis steigt = Fake-Rally (Short-Covering) → Score 0-30
- OI fällt + Preis fällt = Kapital verlässt → Score 0-20
- Normalisierung: `oi_score = max(0, min(100, base_score + oi_change * weight))`
- Datenquelle: Hyperliquid `/info` API, `openInterest` pro Asset
- Aggregation: 24h Change, aktualisiert alle 4h
- Kein externer Dienst nötig — kommt direkt von der Börse

**Gewichtung 45/25/30/0 — Warum**:
- ADX 45% → Trendstärke ist der wichtigste Indikator (V1 bewiesen)
- Slope 30% → Steigung unterscheidet echten Trend von flacher EMA-Bewegung
- Vol 25% → Crash-Erkennung wichtig, aber soll Score nicht dominieren
- OI 0% → **Zu validieren** — wenn Backtest beweist dass Fake-Rally-Erkennung hilft, Upgrade auf 10%

**Regime-Mapping**:
| Score | Regime | Entry-Regel | Exit-Regel |
|-------|--------|-------------|------------|
| 0-30 | Range | Kein Entry | Bestehende: Trail auf 1.5% tighten |
| 30-70 | Trend | V1 normal | V1 normal (Trail 2%) |
| 70-100 | Strong Trend | Sniper möglich | Trail 2.5%, Position atmen |

**Regime-Übergänge (Hysterese)**:
- Range→Trend: Score muss >35 erreichen (nicht >30)
- Trend→Range: Score muss <25 fallen (nicht <30)
- Trend→Strong: Score muss >75 erreichen (nicht >70)
- Strong→Trend: Score muss <65 fallen (nicht <70)
- Verhindert Flip-Flopping an den Grenzen

**Berechnung pro Candle**:
- Kein API-Call — rein aus OHLCV-Daten berechnet
- Alle 3 Komponenten auf demselben Bar
- Kein Lookahead — nur abgeschlossene Candles
- Speichert letzten Score für Hysterese-Vergleich

**Backtest-Validierung**:
- Gleicher Gate wie V1: ≥75% Pass-Rate, CL≤12, DD≤20%
- Vergleich: Regime-gefiltert vs ungefiltert
- Erwartung: ~70% weniger Trades, ~50% weniger DD
- **A/B-Test**: V1-Strategie mit Regime-Score vs ohne

**Implementierung**:
- Neues Modul: `regime_detector.py`
- Input: Candle-Daten (close, high, low, volume)
- Output: `regime_score` (0-100) + `regime_label` (range/trend/strong)
- Integration: `paper_engine.py` fragt `regime_detector` vor jedem Entry
- Sniper-Modul nutzt `regime_score > 70` als Entry-Bedingung

---

### Modul 2: Sentiment (Stufe 3 — Advanced)

**Ziel**: KI-basierter Kill-Switch bei Crash-Szenarien die Indikatoren verpassen

**Pipeline im Detail**:
```
News Sources → Aggregator → Gemma4 Cloud JSON-Mode → Sentiment Score (0-100)
                                                                    ↓
                                                            Position Sizing Filter
                                                            Score ≤ 15 → No Entry (Kill)
                                                            Score 15-30 → Half Position
                                                            Score 30-50 → Cautious (V1 only, kein Sniper)
                                                            Score > 50 → Full Position (Sniper möglich)
```

**News Sources (Priorität)**:
| Priority | Source | Format | Update-Frequenz |
|----------|--------|--------|-----------------|
| 0 | Funding Rate (Hyperliquid API) | Score 0-100, direkt | 8h |
| 1 | Crypto News (CoinDesk, CryptoSlate) | KI-Score 0-100 | Echtzeit |
| 2 | Macro (Fed, CPI, DXY) | Regime-Flag | Täglich |
| 3 | On-Chain (Exchange Netflow) | Flow-Rate | Täglich |

**Funding Rate als Priority-0**:
- Kommt direkt von Hyperliquid API (`/info`, `fundingHistory`) — kein externer Dienst, kein KI-Call
- Positive Funding = Longs zahlen Shorts = überfüllt = Top-Signal
- Negative Funding = Shorts zahlen Longs = überlevert = Bottom-Signal
- Mapping: `funding_score = 50 + (funding_rate * scaling_factor)`, gekappt 0-100
- Extreme Funding (>0.1%) = Score 0-10 (Crash-Risiko) oder 90-100 (Euphorie-Risiko)
- Normale Funding (~0.01%) = Score 40-60 (neutral)
- 8h Aggregation = stabil genug für 1h-Candles, filtert Noise
- **Warum besser als Fear&Greed Index**: Echtzeit von unserer Börse, nicht aggregiert von 5 Quellen

**Gemma4 Cloud Prompt (JSON-Mode)**:
```
Analyze the following crypto market news and return a JSON score.

Rules:
- Score 0-100 (0=extreme fear/crash, 50=neutral, 100=extreme greed/euphoria)
- Only consider the last 24h of news
- Major exchange hacks → Score 0-10
- Regulatory crackdowns → Score 10-25
- Minor FUD → Score 25-40
- Neutral/boring → Score 40-60
- Positive developments → Score 60-75
- Major adoption news → Score 75-90
- Extreme euphoria → Score 90-100

Return ONLY: {"score": <int>, "confidence": <0.0-1.0>, "regime": "crash|fear|neutral|greed|euphoria"}
```

**Aggregation**:
- Funding Rate hat 40% Gewicht (kostenlos, direkt von Börse, kein KI nötig)
- News-Sentiment hat 30% Gewicht
- On-Chain Netflow hat 20% Gewicht
- Macro hat 10% Gewicht
- Widersprüchliche Signale → konservativster Score gewinnt
- Confidence < 0.3 → Score verwerfen, auf 50 (neutral) fallen

**Fail-Safe-Kaskade**:
1. **Gemma4 fail** → Score = 50 (neutral, kein Einfluss)
2. **API timeout** → letzter Score beibehalten (decay nach 4h → 50)
3. **Confidence < 0.3** → Score = 50
4. **Keine News in 24h** → Score = 50
5. **Niemals Upsizing** → Sentiment kann nur verkleinern, nie vergrößern

**Sizing-Regeln im Detail**:
| Score | V1 Position | Sniper | Begründung |
|-------|-------------|--------|------------|
| 0-15 | Kein Entry | Kein Entry | Crash oder extremes Risiko |
| 15-30 | 50% Size | Kein Entry | Erhebliche Unsicherheit |
| 30-50 | 100% Size | Kein Entry | Vorsichtig, keine Conviction |
| 50-75 | 100% Size | Erlaubt | Normale Bedingungen |
| 75-100 | 100% Size | Erlaubt | Starke Conviction (kein Upsizing!) |

**Warum Gemma4 Cloud**:
- Cloud-Infrastruktur, kein lokaler GPU-Bedarf
- JSON-Mode stabil für strukturierte Extraktion
- Sentiment-Parsing braucht kein Flagship-Modell
- Zukunft: Migration auf lokal möglich wenn Hardware reicht
- GLM-5.1 = Reserve für komplexe Tasks

**Warum erst Stufe 3**:
- Sentiment ist ein Filter, kein Motor
- Regime-Score (Stufe 1) filtert bereits Range-Trades raus
- Sentiment fängt Black-Swans die Indikatoren verpassen
- Aber: Black-Swans sind selten → schwer zu backtesten → braucht Live-Validierung
- Stufe 3 = Sniper + Regime bewiesen → Sentiment als Krönung

**Backtest-Validierung**:
- Historische Events manuell bewerten (FTX, Terra, SEC, ETF-Approvals)
- Simulierter Sentiment-Score auf historischen Daten → DD-Verbesserung messen
- Gate: DD-Reduktion > 5% bei Crash-Events ODER keine Verschlechterung im Normalbetrieb

---

### Modul 3: Asset Selection (Stufe 3 — Advanced)

**Ziel**: Stärkstes Asset bevorzugen statt Equal-Weight über 6 Assets

**ROC-Ranking (Basis, Stufe 3)**:
```
roc_score = (
  ROC_5 * 0.20 +    # Kurzfristiger Momentum
  ROC_10 * 0.30 +   # Mittelfristiger Momentum
  ROC_20 * 0.50     # Trend-Momentum (gewichtigster)
)
```

**Berechnung**:
| Metrik | Formel | Gewichtung |
|--------|--------|------------|
| ROC_5 | `(close - close[5]) / close[5] * 100` | 20% |
| ROC_10 | `(close - close[10]) / close[10] * 100` | 30% |
| ROC_20 | `(close - close[20]) / close[20] * 100` | 50% |

**Warum ROC_20 am wichtigsten**:
- Kurzfristiger Momentum (5 Bars) ist Noise
- 20-Bar-Trend korreliert mit V1-EMA-50 Zeitrahmen
- Momentum-Anomalien verschwinden über 20 Bars

**Ranking-Regeln**:
| Rank | Behandlung |
|------|------------|
| #1 | Sniper-Kandidat (wenn Regime > 70) |
| #2 | Normaler Entry |
| #3-4 | Reduzierte Position (50% Size) |
| #5-6 | Kein Entry (schwacher Momentum) |

**Kombination mit Regime-Score**:
| Regime | Rank #1 | Rank #2 | Rank #3-6 |
|--------|---------|---------|------------|
| Strong (>70) | Sniper 5x | V1 normal | Kein Entry |
| Trend (30-70) | V1 normal | V1 normal | Kein Entry |
| Range (<30) | Kein Entry | Kein Entry | Kein Entry |

**Gemma4 Cloud-Erweiterung (Stufe 3)**:
- News-Attribution: "BTC rallyt wegen ETF-News" vs. "BTC rallyt technisch"
- Korrelations-News: "ETH folgt BTC" vs. "ETH hat eigenes Narrativ"
- Nur wenn ROC-Baseline bewiesen → Gemma4 ergänzt, nicht ersetzt

**Implementierung**:
- Neues Modul: `asset_selector.py`
- Input: close-Preise aller 6 Assets, letzter Regime-Score
- Output: `ranking` (Liste der Assets sortiert nach roc_score)
- Integration: `paper_engine.py` fragt Ranking vor Entry → Top-2 bekommen Priority
- Sniper nutzt `ranking[0]` als Kandidat

**Backtest-Validierung**:
- Vergleich: ROC-gefiltert vs Equal-Weight
- Gate: Sharpe > V1 Equal-Weight, DD ≤ V1 Equal-Weight
- Fairness: Gleiche Anzahl Trades (ROC schneidet nur schwache ab)

---

### Modul 4: Risk Management (Stufe 1-2)

**Ziel**: Portfolio-DD kontrollieren, Korrelation begrenzen, Sniper bremsen

**Kein KI-Einsatz** — reine Mathematik

**DD-Scaling (Stufe 1)**:
| Schwelle | Aktion | Begründung |
|----------|--------|------------|
| DD > 10% | Alle Positionen halbieren | Early Warning, Risiko reduzieren |
| DD > 15% | Keine neuen Entries (SOFT_PAUSE) | Defensive, nur noch Exits |
| DD > 20% | KILL (alles schließen) | Kapitalerhalt, kein Ermessen |

**DD-Berechnung (Stufe 1)**:
```
drawdown_pct = (peak_equity - current_equity) / peak_equity * 100
```
- `peak_equity` = höchster je erreichter Equity-Stand
- `current_equity` = mark-to-market (realized + unrealized)
- Wird jeden Candle neu berechnet
- Kein Smoothing, keine Ausnahme

**Korrelations-Filter (Stufe 2)**:
- Max 2 stark korrelierte Positionen gleichzeitig
- Korrelationsschwelle: Pearson r > 0.7 über letzten 20 Bars
- Wenn 2 Positionen offen und 3. korreliert → Entry blockiert
- BTC und ETH gelten IMMER als korreliert (r > 0.8 historisch)

**Korrelations-Kaskade**:
| Situation | Aktion |
|-----------|--------|
| 0 Positionen offen | Entry frei (max 2 korreliert) |
| 1 Position offen | Entry frei wenn nicht r>0.7 mit bestehend |
| 2 korrelierte Positionen | Kein weiterer Entry wenn r>0.7 |
| KILL ausgelöst | Alle Positionen schließen, COOLDOWN 24h |

**Circuit-Breaker (Stufe 1)**:
| Event | Aktion | Dauer |
|-------|--------|-------|
| 3 aufeinanderfolgende Sniper-Verluste | Sniper pausiert | 48h |
| 5 aufeinanderfolgende V1-Verluste | SOFT_PAUSE | 24h |
| DD > 20% (KILL) | Alle schließen | COOLDOWN 24h |
| Circuit-Breaker Reset | Resume | Nach Ablauf |

**Volatility-Parität (Stufe 2)**:
- Ersetzt starre Leverage-Tiers (ADR-007)
- Position Size = `target_risk / (ATR_14 * point_value)`
- `target_risk` = konstanter Risiko-Betrag pro Trade (z.B. 1% des Kapitals)
- High-Vol (AVAX) → kleinere Position, Low-Vol (BTC) → größere
- Sniper: Ausnahme — fix 5x unabhängig von Vol-Parität

**Regime-basierter Exit (Stufe 2)**:
| Regime-Score | Trail | Begründung |
|--------------|-------|------------|
| >70 (Strong) | 2.5% | Position atmen, Conviction hoch |
| 50-70 (Trend) | 2.0% | Normaler V1-Trail |
| 30-50 (Weak) | 1.5% | Trend schwächt, schneller raus |
| <30 (Range) | 1.5% + Exit-Check | Eng führen, ggf. manuell schließen |

**Partial Exits (Stufe 2)**:
- V1 only: 50% bei Trail nehmen, 50% laufen lassen
- Sniper: 100% Entry/Exit, kein Halbschritt
- Implementierung: Position wird in 2 Sub-Positionen aufgeteilt
- Trail-Trigger schließt erste 50%, zweite 50% läuft mit neuem Trail

**Re-Entry Logik (Stufe 2)**:
- V1: Nach Exit → 1h Cooldown → wenn MACD+EMA noch aligned → Re-Entry
- Sniper: Kein Re-Entry. Score muss <70 fallen und wieder >70 steigen.
- Max 1 Re-Entry pro Asset pro Trend-Phase (verhindert Ping-Pong)

**Implementierung**:
- Erweitertes Modul: `risk_guard.py` (V1 Baseline existiert)
- Neue Methoden: `check_correlation()`, `check_circuit_breaker()`, `calc_vol_parity_size()`
- Integration: `paper_engine.py` fragt Risk Guard vor jedem Entry + jede DD-Check-Periode
- State: Circuit-Breaker-Zähler in `state.db` persistiert (survived Restart)

**Backtest-Validierung**:
- DD-Scaling: Vergleich V1 Risk Guard vs V2 DD-Scaling → DD-Reduktion messbar
- Korrelations-Filter: Vergleich mit/ohne → DD-Reduktion bei correlated-Moves
- Circuit-Breaker: Simulation auf historischen Crash-Phasen
- Gate: Jede Komponente einzeln bewiesen, dann kombiniert

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

**Warum Gemma4 Cloud statt GLM-5.1**:
- Cloud-Infrastruktur, kein lokaler GPU-Bedarf
- JSON-Mode stabil für strukturierte Extraktion
- Ausreichend → Sentiment-Parsing braucht kein Flagship-Modell
- Zukunft: Migration auf lokal möglich wenn Hardware reicht
- GLM-5.1 cloud = Reserve für komplexe Aufgaben

---

## Alpha Stack V2 (Priorität, nach Stufen)

**Stufe 1 — Kern**
| # | Feature | Warum |
|---|---------|-------|
| 1 | Regime-Score (ADX+ATR+Slope, OI zu validieren) | Filtert ~70% Range-Trades raus |
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
| 9 | Sentiment Kill-Switch (Funding Rate + News) | Crash-Schutz, Funding Rate als Priority-0 |
| 10 | On-Chain Regime-Filter | Exchange Netflow |
| 11 | Limit-Orders | Fee-Reduktion |
| 12 | Asset-Ranking (ROC) | Stärkster Momentum bevorzugen |
| 13 | Dynamische Korrelationsmatrix | Statt max 2-Regel |

**Abgelehnt**
| Feature | Warum |
|---------|-------|
| ATR-Stops | Kein Improvement bewiesen |
| Kelly Criterion | Win-Rate zu instabil |
| L2 Orderbuch-Imbalance | Ändert sich in Sekunden, 1h-Chart glättet das weg |
| Volume Profile | Bereits in Candle-Daten enthalten |
| Liquidation Levels | Zu unzuverlässig, Preis zeigt es bereits |
| Whale-Tracking (einzelne Adressen) | Noise auf 1h, nicht relevant bei 100€ Kapital |
| On-Chain Microstruktur | Für 1h-Candles und 100€ Kapital Over-Engineering |

---

## Was V2 NICHT ist

- Kein Indikator-Salat (mehr Indikatoren ≠ bessere Ergebnisse)
- Keine KI-Entscheidung über Trade-Richtung (nur Filter)
- Kein Hyper-Optimization der Backtest-Parameter
- Kein automatisches Upsizing bei "gutem Sentiment"

## SHORT-Positionen — Hypothese (Stufe 2 Kandidat)

**Status: ZU VALIDIEREN — nicht als festes Feature aufnehmen ohne Backtest-Beweis**

**Warum SHORT Sinn macht:**
- Regime Detection weiß wenn Trend DOWN → wird aktuell nicht genutzt
- Einnahmen im Bärenmarkt → Fixkosten decken
- Hyperliquid Perps = gleiches Interface, trivial zu implementieren
- UI (LONG/SHORT Badge) ist bereits vorbereitet

**Warum SHORT riskant ist:**
- Bärenmärkte sind volatiler → Shortsqueezes sind brutal
- Funding Rate wirkt GEGEN Shorts → wir zahlen für die Position
- Markt hat natürlichen Aufwärts-Drift → Short ist strukturell schwerer
- V1 25% Win-Rate LONG invertiert NICHT automatisch zu guter SHORT-Win-Rate
- Bidirektional = doppelt so viele Code-Pfade = doppelt so viele Bugs

**Regime-Logik (falls validiert):**

| Regime | Trendrichtung | Aktion |
|--------|--------------|--------|
| Strong (>70) | UP | LONG |
| Strong (>70) | DOWN | SHORT |
| Trend (30-70) | UP | LONG V1 |
| Trend (30-70) | DOWN | SHORT V1 |
| Range (<30) | egal | Kein Trade |

**Gate:**
- V2 Stufe 1 (LONG-only) MUSS erst validiert sein
- SHORT-Backtest MUSS ≥ LONG-Backtest Sharpe zeigen
- SHORT-Backtest MUSS DD ≤ LONG-Backtest DD zeigen
- Paper Trading MUSS ≥5 SHORT-Trades in 14 Tagen zeigen
- Ohne Gate-Bestehen: SHORT wird NICHT aufgenommen

**Reihenfolge:**
1. V2 Stufe 1 bauen + validieren (LONG-only)
2. Regime-Score um Trendrichtung erweitern
3. SHORT-Backtest separat laufen
4. Nur bei positivem Ergebnis → Stufe 2 aufnehmen

## V2 Implementierung — 3 Stufen, 1 Release

### Stufe 1: Kern (Regime + Sniper)
- Regime-Score (ADX + ATR-Ratio + EMA-Slope, OI zu validieren)
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
- Sentiment Kill-Switch (Funding Rate Priority-0 + News)
- On-Chain Regime-Filter
- Limit-Orders
- Dynamische Korrelationsmatrix
- Asset-Ranking (ROC)
- **Gate**: Vollständiges V2 durchs Tor, dann LIVE

Alle 3 Stufen = V2. Kein V3. Nach Stufe 3 → Live gehen.