# V2 Strategy Design — Der Oktopus 🐙

**Status:** PLANNED (post Paper Trading)
**ADR:** Will be formalized as ADR-008 after Phase 8

## Inhalt

- [Die Oktopus-Metapher](#die-oktopus-metapher)
- [V1 Lessons → V2 Requirements](#v1-lessons--v2-requirements)
- [V2 Stufe 1 Scope](#v2-stufe-1-scope--was-wir-bauen-und-beweisen)
- [V2 Design Principles (1–12)](#v2-design-principles)
- [Sniper-Upgrade & Exit-Regeln](#sniper-upgrade-modus-b)
- [Strategy Review: Bewertete Risiken](#strategy-review-bewertete-risiken)
- [V2 Validierung](#v2-validierung)
- [V2 Module](#v2-module)
  - [Modul 1: Regime Detection](#modul-1-regime-detection-stufe-1--kern)
  - [Modul 2: Sentiment](#modul-2-sentiment)
  - [Modul 3: Asset Selection](#modul-3-asset-selection-stufe-3--advanced)
  - [Modul 4: Risk Management](#modul-4-risk-management-stufe-1-2)
  - [Modul 5: Sniper](#modul-5-sniper-stufe-1--kern)
- [KI-Einsatz-Strategie](#ki-einsatz-strategie)
- [Alpha Stack V2 (Priorität)](#alpha-stack-v2-priorität-nach-stufen)
- [SHORT-Positionen](#short-positionen--hypothese-stufe-2-kandidat)
- [V2 Implementierung — 3 Stufen](#v2-implementierung--3-stufen-1-release)

---

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

## V1 Lessons → V2 Requirements

**Fundamentale Erkenntnis aus 170+ Foundry-Kandidaten:**
- 1h-Crypto mit Standard-Indikatoren (BB/RSI/EMA/MACD/ADX) hat **keinen robusten Edge**
- TREND: -13% bis -79% Return | MOM: -50% | VOL: -24% | MR: -3% bis -28%
- 4H IS=+1.09 ist overfitted | REGIME hat nur 4 Trades
- Nur MR hat genug Trades, aber 10-Window-WF = FAIL
- **V2 braucht fundamental andere Ansätze**, nicht nur Indikator-Variationen:
  - Zeitreihen-Muster (Pattern-Erkennung, nicht nur Indikator-Schwellen)
  - Multi-Timeframe-Korrelationen (1h Entry + 4h Trend + 15s Execution)
  - Cross-Asset-Signale (BTC führt, Alts folgen)
  - Regime-Score als 6. Sinn (nicht nur ADX > 25)
  - Volatility-Parity statt Equal-Weight
  - Sentiment als Kill-Switch (nicht als Signal)

## V2 Stufe 1 Scope — Was wir bauen und beweisen

**Nur 7 Features in Stufe 1.** Alles andere = Stufe 2+ bis bewiesen.

| Feature | Details | Beweis |
|---------|---------|--------|
| Regime-Score | ADX 45% + Slope 30% + Vol 25%, OI 0% | Backtest: Sharpe > V1 |
| Sniper | Regime > 70, 5x, starr Trail 2.5%, Max Hold 24h | Backtest + Paper |
| DD-Scaling | 10/15/20% Stufen + Global Equity Stop | Paper DD < 25% |
| Global Equity Stop | 1h-DD > 8%, starr 24h Cooldown | Paper |
| Sentiment = Funding Rate | Kontraindikator bei Extremen, 100% in Stufe 1 | Backtest Invertierung |
| Slippage Tax | SLIPPAGE_BPS auf jeden Paper-Entry | Trivial |
| Decision Logging | SKIP-Events loggen (Asset, Regime, Grund) | Telemetrie |

**Was NICHT in Stufe 1:**
- Kinetischer Trail → Stufe 2 (braucht Trade-Daten)
- Dynamic Cooldown → Stufe 2 (starr 24h reicht erstmal)
- Volatility-Parität → Stufe 2 (braucht ATR-Daten)
- SHORT → Stufe 2 (braucht separaten Backtest)
- Gezeiten-Blocker → Stufe 2 (braucht Kalender-Feed)
- News Sentiment → Stufe 3 (braucht validierten Prompt)

---

## V2 Design Principles

Die Principles sind kurz gefasst — Details stehen in den [V2 Modulen](#v2-module) unten.

| # | Principle | Kurz | Modul |
|---|-----------|------|-------|
| 1 | **Regime-Erkennung** | Score 0-100, nicht binär. Range = kein Trade. | [Modul 1](#modul-1-regime-detection-stufe-1--kern) |
| 2 | **Volatility-Parity** | Risiko konstant, nicht Kapital. Ersetzt Leverage-Tiers. | [Modul 4](#modul-4-risk-management-stufe-1-2) |
| 3 | **Sentiment = Kill-Switch** | Nur Downsizing, nie Upsizing. Score ≤ 15 = kein Entry. | [Modul 2](#modul-2-sentiment) |
| 4 | **On-Chain als Regime-Filter** | Exchange Netflow 7-14d, keine Whale-Jagd. | [Modul 2](#modul-2-sentiment) |
| 5 | **Kein Indikatoren-Salat** | Bessere Regeln, nicht mehr Indikatoren. ATR abgelehnt. | — |
| 6 | **Korrelations-Filter** | Max 2 stark korrelierte Positionen. Fallback: Global Equity Stop. | [Modul 4](#modul-4-risk-management-stufe-1-2) |
| 7 | **Re-Entry Logik** | V1: 1h Cooldown. Sniper: Score muss <70 fallen und wieder >70. | [Modul 5](#modul-5-sniper-stufe-1--kern) |
| 8 | **Regime-basierter Exit** | Strong=Trail 2.5%, Weak=1.5%. Stufe 2: Kinetischer Trail. | [Modul 4](#modul-4-risk-management-stufe-1-2) |
| 9 | **Partial Exits** | 50% bei Trail, 50% laufen lassen. Nur V1. Sniper = 100%. | [Modul 4](#modul-4-risk-management-stufe-1-2) |
| 10 | **DD-Scaling + Global Equity Stop** | 10/15/20% Stufen. 1h-DD > 8% = alles schließen. | [Modul 4](#modul-4-risk-management-stufe-1-2) |
| 11 | **Execution-Staffelung** | Stufe 1=Market, Stufe 2=IOC, Stufe 3=Limit. Sniper=immer Market. | [Modul 4](#modul-4-risk-management-stufe-1-2) |
| 12 | **Dynamische Korrelationsmatrix** | Rolling 20-Bar, r>0.7 blockt Entry. Stufe 2. | [Modul 4](#modul-4-risk-management-stufe-1-2) |

---

### Sniper-Upgrade (Modus B)

> ℹ️ Vollständige Details im [Sniper-Modul](#modul-5-sniper-stufe-1--kern) unten.
- Kein separater Pool — Sniper **upgraded** den besten V1-Trade
- V1 entscheidet welcher Trade. Sniper-Bedingungen erfüllt → Hebel von 1.8x auf 4-5x
- Keine doppelte Position auf demselben Asset
- **Max 30€ allocated** für Sniper-Trade (statt 16.67€), × 5x = 150€ Notional
- Restliche 70€ verteilen sich auf V1-Positionen normal
- Kein Kapitalkonflikt

---

## Sniper-Exit: Vier Regeln

> ℹ️ Ergänzt das [Sniper-Modul](#modul-5-sniper-stufe-1--kern) — Exit-Regeln im Detail.

| Signal | Aktion |
|--------|--------|
| Regime-Score fällt < 50 | Sofort raus (Trend bricht) |
| Regime-Score fällt 50-70 | Downgrade auf V1-Hebel, Trail auf 2.0% |
| Trailing Stop 2.5% | Standard-Exit im Strong Trend |
| Kinetischer Trail (Stufe 2) | Trail zieht sich enger je laenger der Trade offen ist (2.5% -> 1.0%). Stufe 1: starr 2.5%. |

Sniper-Trail = 2.5% (nicht 1.5%), weil Sniper im Strong Trend schießt → mehr Raum zum Atmen.
DD-Limit: max 10% Portfolio-DD aus Sniper-Trades. Worst-case 1 Trade = 2.5% Trail × 5x = 12.5% auf 30€ = 3.75€ = 3.75% des Gesamtportfolios. Heißt: 1 Sniper-Verlust verbraucht ~38% des DD-Budgets. Max 2-3 Sniper-Verluste bevor Sniper pausiert.

---

## Strategy Review: Bewertete Risiken

_Externe Analyse vom 2026-04-24. Jeder Punkt geprüft gegen Oktopus-Design und unsere Principles._

### ✅ Bereits abgedeckt

| Risiko | Oktopus-Lösung | Wo im Design |
|--------|---------------|-------------|
| Sentiment-Lag bei Flash-Crash | Funding Rate = Priority-0 (40%, direkt von Börse, kein KI-Lag). Regime-Herz (ADX+Vol) fängt Flash-Crash. | Prinzip 3, Modul 2 |
| Regime-Score Hysterese | 5-Puffer-Zonen: Range→Trend >35, Trend→Range <25, Trend→Strong >75, Strong→Trend <65 | Modul 1 |
| API-Rate-Limits | V1: 60s Polling. V2: OI+Funding alle 4-8h. Hyperliquid Limit 1200/min, wir nutzen <5. | Nicht relevant |

### ⚠️ Aufgenommen und gelöst

| Risiko | Schwere | Loesung | Wo im Design |
|--------|---------|---------|-------------|
| **Korrelations-Kollaps im Crash** | HOCH | **Global Equity Stop**: 1h-DD > 8% -> alle Positionen Market-Order schliessen. Verschrfung der DD-Scaling mit Zeitfenster. Stufe 1. | Prinzip 10 (erweitert) |
| **Limit-Order-Falle (Execution)** | HOCH | **Execution-Staffelung**: Stufe 1 = Market, Stufe 2 = IOC, Stufe 3 = Limit. Sniper = IMMER Market. | Prinzip 11 (qualifiziert) |
| Korrelations-Filter-Luecke in Crashes | MITTEL | Crash-Einschraenkung dokumentiert: Korrelations-Filter wirkungslos bei 1.0-Korrelation -> Global Equity Stop als Fallback | Prinzip 12 (Ergaenzung) |
| **Funding-Rate-Falle (Kontraindikator)** | HOCH | Extreme Funding invertiert: Stark negativ = Short-Squeeze-Treibstoff (Bullish), Stark positiv = Overcrowded (Bearish). Invertierung nur bei |Funding| > 0.05%. Vor Validierung -> Score = 50. | Modul 2 |
| **Oracle-Risiko (Daten-Integritaet)** | HOCH | **Price Sanity Check**: Unphysiologische Preisbewegungen (>5%/Min) -> Bot pausiert statt handelt. Global Stop loest nur bei validierten Daten aus. V1 hat bereits PRICE_FLOORS. | Modul 4 (neu) |
| **Slippage beim Global Stop** | MITTEL | **TWAP-Light**: Global Exit nicht als einzelne Market-Order, sondern in Tranchen ueber 30-60s verteilt. Bei 6 Positionen a ~17EUR ist Impact gering, aber principiell richtig. | Prinzip 10 (Ergaenzung) |
| **Dead Man's Switch** | HOCH | Exchange-seitige Stop-Loss Orders als physisches Herz. Bot zieht Trail lokal nach, aber Not-Aus liegt auf der Boerse. Hyperliquid unterstuetzt SL-on-Open. | Stufe 1 Infrastruktur |

<details>
<summary>❌ Bewusst abgelehnt (12 Vorschläge) — klicken zum Aufklappen</summary>

| Vorschlag | Warum abgelehnt | Oktopus-Test |
|-----------|-----------------|-------------|
| Volatility-Expansion als Regime-Vorfilter | ATR-Filter im Backtest bewiesen: kein Improvement. Neuer Indikator = Indikatoren-Salat (Prinzip 5). | 9. Arm? Nein. |
| Multi-Timeframe-Bestaerkung (1h vs 4h) | Komplexitaetslayer ohne Backtest-Beweis. EMA-Slope hat 30% Gewicht als fhrende Komponente. Heatmap = Dashboard-Feature, kein Entry-Signal. | 9. Arm? Nein. |
| Bollinger Band Breakout | Dasselbe Kategorie wie ATR - nachlaufend, kein Backtest-Beweis. | 9. Arm? Nein. |
| L2 Orderbook Check (Saugnapf/Gravity) | Rauschen auf 1h-Timeframe. Whale-Spoofing. 3x Bid/Ask flippt sekundaerlich. Bei 100e Position = 0 Impact. Bereits im V2 Audit abgelehnt. | 9. Arm? Nein. |
| Shadow-Bot / Parameter-Optimierung | Hyper-Optimization explizit verboten (PRINCIPLES.md). Kontinuierliche Parameter-Variation = Curve-Fitting in Echtzeit. | 9. Arm? Nein. |
| Leader-Laggard Veto (BTC-Slope) | Korrelationsfilter (Prinzip 12) deckt denselben Fall ab. BTC-Slope Veto = redundanter Filter + False-Positives bei legitimen ALT-Breakouts. | 9. Arm? Nein. |
| Micro-Probing (2e Test-Order) | Falscher Timeframe (3 Min Noise auf 1h). Hyperliquid Mindestgroesse ~10$. Doppelte Gebuehren. Gefuehl, nicht Strategie. | 9. Arm? Nein. |
| Digital Twin Visualisierung | Monitor V1 reicht. JSON-Stream + PowerBI = schoen, aber kein Trading-Signal. | Kein Arm, kein Signal. |
| Ghost-Mode Recovery (Schatten-Trades) | Dynamic Cooldown (12h + Regime > 60 x 3) loest dasselbe Problem einfacher. 2 Paper-Trades auf 1h = statistisch irrelevant. | Dynamic Cooldown bereits implementiert. |
| Tiefsee-Vakuum (Crash-Limit-Buys) | Widerspricht Oktopus-Identitaet: Bei Gefahr RUECKZUG, nicht Angriff. Auf Perps: Long bei -20% im Crash = Liquidationsrisiko. Global Equity Stop schliesst ALLES, nicht nur schlechte Positionen. | Oktopus-Test: Ja, aber falsche Richtung. |
| Actor Model Architecture | 6 Assets / 1h Candles / 60s Polling = zero Contention. Over-Engineering. 326 Tests muessen komplett neu geschrieben werden. | Falsche Skala. |
| Event Sourcing | Bereits geloest: trades.jsonl + state.db (SQLite) + equity_history. Unsere Crash-Probleme waren nie State-Korruption. | Bereits implementiert. |

**Stufe-3 Hypothesen** (nicht abgelehnt, aber nicht jetzt):
- Session-Timing (Gezeiten-Filter): 0.9x/1.05x Regime-Multiplikator nach Trading-Session. Vol-Score (25%) filtert Low-Liquidity bereits. Needs Backtest.
- Sector Tags (Sektor-Topografie): Bei 6 Assets mit 3 Sektoren = statistisch irrelevant. Korrelationsmatrix (Stufe 2) ist die bessere Loesung.
- House-Money Sniper (Core/Prey Wallets): Sniper nutzt nur Profit-Kapital, nie Start-Kapital. Elegant bei 1000e+, aber bei 100e keine "Beute" vorhanden. Stufe-3 wenn Kapital signifikant waechst.
- Schmerzgedaechtnis (Per-Asset Cooldown): 3 consecutive SLs auf einem Asset = 48h Bann. Granularer als globaler Circuit Breaker. Bei 6 Assets + niedriger Trade-Frequenz selten triggert. Regime-Score + Korrelations-Filter decken denselben Fall ab.

**Der Oktopus-Test zieht:** Jeder abgelehnte Vorschlag waere ein 9. Arm. Der Oktopus braucht keine weitere Sensorik - er braucht bessere Reflexe (Global Equity Stop, Kinetischer Trail) und praesizere Execution (Market -> IOC -> Limit).

</details>

### 🏗️ Die 3 Herzen des Oktopus (Infrastruktur-Layer)

Das Review identifizierte 3 infrastrukturelle Schichten, die das Strategie-Design ergaenzen:

| Herz | Funktion | Status |
|------|----------|--------|
| **Strategisches Herz** | Regime-Filter + Sniper-Logic | Ready (V2 Design) |
| **Operatives Herz** | Global Equity Stop (1h-Window) + TWAP-Light + Gezeiten-Blocker (Stufe 2) | Stufe 1 Kern (neu) |
| **Physisches Herz** | Exchange-seitige Stops + Heartbeat-Monitoring | Stufe 1 Infrastruktur (neu) |

**Das physische Herz ist der wichtigste neue Punkt:** Ohne exchange-seitige Stop-Loss Orders ist der Bot bei einem Infrastruktur-Ausfall "blind" im Markt. Hyperliquid erlaubt das Hinterlegen von SL bei Positionseroeffnung. Das muss in Stufe 1 implementiert werden.

---

## V2 Validierung

### Global Equity Stop: Recovery nach Ausloesung

Wenn der Global Equity Stop ausloest (1h-DD > 8%), bleibt der Bot **SOFT_PAUSE**:

**Stufe 1: Starrer 24h Cooldown** (simpel, konservativ)
- 24h Ruhepause — kein automatischer Re-Entry
- Nach 24h: Resume wenn Regime-Score > 50 + Equity stabil
- Manuell jederzeit durch `!resume` Command
- Warum starr: Einfach zu implementieren, einfach zu testen, kein Tuning noetig

**Stufe 2: Dynamischer Cooldown (Parametrische Tinte)** — braucht Regime-Daten aus Stufe 1
- **Minimum 12h** Ruhepause — nach 8% DD in 1h ist 4h zu frueh, 24h zu starr
- **Early Resume** nach 12h wenn: Regime-Score > 60 fuer 3 aufeinanderfolgende Kerzen + Equity stabil
- **Full Resume** nach 24h wenn: Regime-Score > 50 + Equity stabil
- Warum 12h statt 4h: Nach einem echten Crash ist 4h zu frueh
- Warum Regime > 60 (nicht 80): Regime > 80 nach Crash ist selten. > 60 fuer 3 Candles = echte Stabilitaet
- Warum Stufe 2: 2 Pfade + 2 Schwellenwerte = mehr Komplexitaet. Erst bauen wenn Stufe 1 Daten zeigen dass 24h zu starr ist.

Der Oktopus zieht sich zurueck und beobachtet — Stufe 1 starr, Stufe 2 parametrisch.

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

### Modul 2: Sentiment

**Ziel**: KI-basierter Kill-Switch bei Crash-Szenarien die Indikatoren verpassen

**Stufen-Plan (Operative Realitaet)**:
| Stufe | Sentiment-Bestandteile | Aufwand | Kapital-Voraussetzung |
|-------|----------------------|--------|----------------------|
| **Stufe 1** | **100% Funding Rate** (gratis von Hyperliquid) | Minimal | 100e (jetzt) |
| **Stufe 2** | Funding Rate + News (Gemma4 JSON-Mode) | Mittel | 200e+ |
| **Stufe 3** | + On-Chain (falls kostenlose Quelle bewiesen) | Hoch | 500e+ |

**Warum Stufe 1 = nur Funding Rate:**
- On-Chain (Glassnode 80$/Mo bei 100e = oekonomischer Selbstmord) → 0% bis kostenlose Quelle bewiesen (CryptoQuant/Coinglass pruefen)
- Macro (10%) → kein Score 0-100, sondern **Gezeiten-Blocker**: Fed-Meeting in 2h = SOFT_PAUSE. Gehoert ins operative Herz, nicht ins Sentiment-Modul.
- News (30%) → braucht validierten Prompt + Fail-Safe. Aufwand steht bei 100e in keinem Verhaeltnis.
- Die restlichen 60% bleiben als leere Interfaces (Mocks) im Code, bis Datenquellen leistbar und bewiesen sind.
- Funding Rate 40% → **60%** in Stufe 1 (oder 100% wenn rest neutral=50). Direkt von Hyperliquid, kostenlos, kein KI-Call.

**AIXBT Evaluation (2026-04-28):**

AIXBT wurde als potenzielle Datenquelle evaluiert. Ergebnis: DIY reicht für V2.

| Feature | AIXBT | DIY | Entscheidung |
|---------|-------|-----|-------------|
| Regime-Feed (Macro/Crypto) | Grounding API (kostenlos, 10/min, 300/Tag) | Eigene Aggregation | **AIXBT Grounding nutzen** — kostenlos, 1h-Polling reicht |
| Sentiment-Kill-Switch | Data-Plan $100/Mo | Funding Rate (Hyperliquid, gratis) + Fear&Greed Index (gratis) | **DIY** — Funding Rate ist bereits Priority-0, FGI ergänzt |
| Momentum-Clustering | Data-Plan $100/Mo | Eigener Twitter/Reddit Scraper | **Skip für V2** — erst evaluieren wenn V2 profitabel |
| Intel-Events | Data-Plan | CoinGecko/CoinMarketCap API (teils gratis) + Hyperliquid Funding | **DIY** — 3-5 Tage Aufwand |
| Historisches Backtesting | `?at=ISO8601` | Eigene Datensammlung (Wochen) | **Später** — braucht erst Datensammlung |

**Fazit:** AIXBT Grounding API (kostenlos) als Regime-Layer nutzen. Bezahlte Features ($100/Mo) durch DIY ersetzen. Momentum-Clustering erst nach V2-Profitabilität evaluieren.

**Gezeiten-Blocker (Macro = Risk Management, nicht Sentiment)**:
- Fed-Meeting, CPI-Release, FOMC → 2h vorher SOFT_PAUSE, 1h nachher
- Wirtschaftskalender-Feed = trivial (z.B. finnhub.io gratis)
- Das ist kein Sentiment-Score, sondern operatives Herz: "Handel nicht wenn der Markt gleich explodieren koennte"
- Gehoert zu **Operatives Herz** (Global Equity Stop + Gezeiten-Blocker)

**News Prompt = JSON-Mode + Fail-Safe 50**:
- Prompt MUSS deterministisch sein: nur `{"score": 35, "confidence": 0.8, "regime": "fear"}`
- Keine Interpretationen, keine Prosa, keine Halluzinationen
- Fail-Safe: KI halluziniert oder liefert Text → Score = 50 (neutral)
- Confidence < 0.3 → Score = 50
- Timeout → letzter Score (decay nach 4h → 50)
- **Niemals Upsizing** → Sentiment kann nur verkleinern, nie vergroessern

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
- **Kontraindikator-Logik bei Extremen:** Funding Rate ist nicht linear!
  - Normale positive Funding (~0.01%) = Longs zahlen Shorts = leicht überfüllt = Score 55-65 (leicht bullish, aber Vorsicht)
  - Normale negative Funding (~-0.01%) = Shorts zahlen Longs = leicht überlevert = Score 35-45 (leicht bearish)
  - **Extreme positive Funding (>0.05%)** = Long-Überhang, Overcrowded = Score 20-30 (Crash-Risiko, nicht Euphorie!)
  - **Extreme negative Funding (<-0.05%)** = Short-Überhang, Short-Squeeze-Treibstoff = Score 70-80 (Bullish-Signal, nicht Fear!)
- **Warum invertiert:** Bei Extremen ist die Funding Rate ein Kontraindikator. Stark negative Funding = Short Squeeze möglich. Stark positive Funding = Long Liquidation Cascade möglich.
- Die Invertierung gilt nur bei |Funding| > 0.05% (5x Normal) — im Normalbereich bleibt die Logik intuitiv
- Mapping (nicht-linear, invertiert bei Extremen): 
  - `funding_abs = abs(funding_rate)`
  - `if funding_abs < 0.03: score = 50 + funding_rate * 500` (linear, ~35-65 Bereich)
  - `if funding_abs >= 0.03: score = invertiert` → positive = bearish, negative = bullish
  - Gekappt 0-100
- 8h Aggregation = stabil genug für 1h-Candles, filtert Noise
- **Warum besser als Fear&Greed Index**: Echtzeit von unserer Börse, nicht aggregiert von 5 Quellen
- **⚠️ Backtest-Pflicht:** Die Invertierungs-Logik bei Extremen muss historisch validiert werden. Vor Validierung: extreme Funding → Score = 50 (neutral), keine Invertierung.

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
Exit: Stufe 1 = starr Trail 2.5% + Max Hold 24h. Stufe 2 = Kinetischer Trail (2.5% -> 1.0%). Regime < 50 = raus, Regime 50-70 = Downgrade
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

**Stufe 1 — Kern** (bauen + beweisen)
| # | Feature | Warum |
|---|---------|-------|
| 1 | Regime-Score (ADX+ATR+Slope, OI 0%) | Filtert ~70% Range-Trades raus |
| 2 | Sniper-Modul (4-5x, starr Trail 2.5%) | Conviction-Upgrade auf Top-Asset |
| 3 | DD-basierte Positionsreduktion | 10/15/20% Stufen |
| 4 | Global Equity Stop (1h-DD > 8%, starr 24h Cooldown) | Crash-Antwort |
| 5 | Sentiment = Funding Rate only | Gratis von Hyperliquid, Kontraindikator |
| 6 | Slippage Tax (SLIPPAGE_BPS) | Pessimistisches Paper Trading |
| 7 | Decision Logging | Warum kein Trade? Telemetrie |

**Stufe 2 — Enhancement** (nach Stufe 1 bewiesen)
| # | Feature | Warum |
|---|---------|-------|
| 8 | Kinetischer Trail (Zeit-Ermuedung) | Loest V1 Trailing-Problem, braucht Trade-Daten |
| 9 | Dynamic Cooldown (12h + Regime > 60) | Flexibler als starr 24h, braucht Stufe 1 Daten |
| 10 | Volatility-Parität | Riskoparität statt Equal-Weight |
| 11 | Partial Exits (V1 only) | Gewinn sichern, Upside offen |
| 12 | Re-Entry Logik | 1h Cooldown, dann wieder möglich |
| 13 | Korrelations-Filter | max 2 korrelierte Positionen |
| 14 | Regime-basierter Exit (dynamischer Trail) | Trail dynamisch nach Regime-Score |
| 15 | SHORT-Positionen | Bidirektional, braucht separaten Backtest |
| 16 | Gezeiten-Blocker (Fed/CPI Pause) | Risk Management, braucht Kalender-Feed |
| 17 | Exchange-seitige Stop-Loss | Physisches Herz, Stufe 1 Infra vor Live |

**Stufe 3 — Advanced** (Hypothesen, brauchen Daten)
| # | Feature | Warum |
|---|---------|-------|
| 18 | News Sentiment (Gemma4 JSON-Mode) | Crash-Schutz, braucht validierten Prompt |
| 19 | On-Chain Regime-Filter | Exchange Netflow, braucht kostenlose Quelle |
| 20 | Limit-Orders | Fee-Reduktion |
| 21 | Asset-Ranking (ROC) | Stärkster Momentum bevorzugen |
| 22 | Dynamische Korrelationsmatrix | Statt max 2-Regel |
| 23 | Session-Timing (Gezeiten-Filter) | 0.9x/1.05x Regime-Multiplikator, needs Backtest |
| 24 | House-Money Sniper | Core/Prey Wallets, braucht >1000e |
| 25 | Schmerzgedaechtnis | Per-Asset Cooldown, needs Validation |

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