# Edge Discovery Research — Projektplan

**Start:** 2026-05-02  
**Status:** Phase 0 (Setup)  
**Ziel:** Systematisch klären ob es einen robusten Edge in Crypto-Tradinng mit öffentlichen Daten gibt — und wenn ja, welchen.

---

## Hintergrund

150+ Strategien getestet. Ergebnis:
- **Standard-Indikatoren (MACD, RSI, BB, EMA):** 0 Alpha bewiesen
- **Funding Rate Mean Reversion:** Edge existiert, aber regime-abhängig (nur in Bären)
- **Alle Strategien waren Long-only Mean Reversion** — ein blinder Fleck

V2 Paper Trading läuft mit BTC+ETH+SOL (Funding-basiert). Parallel brauchen wir neue Hypothesen.

---

## Phase 1: Daten erweitern

### 1.1 4h-Candles aus 1h-Daten aggregieren
- [x] 1h-Parquets vorhanden (6 Assets, 2.5 Jahre)
- [ ] Aggregations-Script: 1h → 4h (OHLCV, Funding-Z, Regime)
- [ ] 4h-Parquets generieren
- [ ] Validierung: Vergleich mit echten 4h-Kerzen

### 1.2 Neue Features extrahieren
- [ ] **Funding Rate roh** (nicht nur z-Score): raw rate, 8h change, extreme events (>3σ)
- [ ] **Funding Richtung** (prozyklisch): z>+1.5 als Short-Signal
- [ ] **OI-Changes**: OI-Spike (% change 1h, 4h, 24h), OI-Price Divergence
- [ ] **Volume Profile**: Relative Volume (vs 20h MA), Volume Spikes (>2σ)
- [ ] **Liquidation-Daten**: Hyperliquid API (falls verfügbar)

### 1.3 Datenqualität prüfen
- [ ] Funding-Gaps identifizieren (welche Stunden fehlen?)
- [ ] Bull/Bear-Phasen markieren (Datum-basiert, nicht nur EMA200)
- [ ] Outlier-Check: Extreme Funding-Events (>5σ) als separate Kategorie

---

## Phase 2: Hypothesen-basierte Tests

**Jede Hypothese bekommt EINEN klaren Test. Format:**
```
HYP-XX: "Beschreibung"
Entry: Exakte Entry-Regel
Exit: 24h time-based (wie V2)
Assets: BTC, ETH, SOL
Zeitrahmen: 1h oder 4h
Gate: ≥4/6 OOS windows profitabel, cum PnL > 0
Ergebnis: PASS / FAIL / INCONCLUSIVE
```

### HYP-01: Funding Trend Continuation
> "Positive Funding (z>+1.5) bedeutet Longs überfüllt → Short hat Edge"

**ERGEBNIS: FAIL** (2026-05-02)

15 Varianten getestet (3 Assets × 5 Regime/Threshold-Kombos):
- Alle 15 FAIL — kein einziger PASS
- Jeder Short-Ansatz verliert Geld (cum PnL negativ)
- Bull-Regime Short am schlimmsten (SOL: -102%)
- Kein Threshold hilft (z>+1.0, +1.5, +2.0 — alle FAIL)

**Erkenntnis:** Positive Funding = Trend Continuation, nicht Reversion.
Die Longs haben recht — sie zahlen Premium weil der Trend weitergeht.
Shorting overheated Funding ist in Crypto ein Verlustgeschäft.

Ergebnisse: `research/sprint_01_results.json`

### HYP-02: 4h Funding Alignment
> "Funding-Signale auf 4h sind robuster weil der 8h-Zyklus natürlicher passt"

**ERGEBNIS: PARTIAL PASS** (2026-05-02)

| Asset | 4h PnL | 4h OOS | 1h PnL | 1h OOS |
|-------|--------|--------|--------|--------|
| **BTC** | **+48.72%** | **4/6** | +10.42% | 3/6 |
| **ETH** | -29.17% | 3/6 | -17.24% | 2/6 |
| **SOL** | +29.65% | 4/6 | +29.26% | 4/6 |

**Erkenntnis:**
- BTC auf 4h = **massiver Upgrade** (PnL 5x, Gate FAIL→PASS, WR 63.6%)
- ETH auf beiden Zeitrahmen FAIL — Bear-Only-Edge nicht robust
- SOL auf 4h = gleichwertig mit 1h, kein Upgrade nötig
- 8h-Zyklus-Alignment-These bestätigt für BTC, nicht für andere

Ergebnisse: `research/sprint_02_results.json`

### HYP-03: OI-Spike als Bestätigung
> "Funding + plötzlicher OI-Anstieg = stärkeres Signal"

**ERGEBNIS: INCONCLUSIVE → FAIL** (2026-05-02)

OI-Daten nicht in historischen Parquets. Volume-Spike (2σ) als Proxy getestet.

| Asset | Baseline | +Volume-Spike | Verbesserung? |
|-------|---------|---------------|---------------|
| BTC | +54%, 4/6 | +20%, 4/6 (n=21) | ❌ Zu wenig Trades |
| ETH | +25%, 5/6 | **+44%, 5/6** | ✅ **PnL verdoppelt, WR 68%!** |
| SOL | +77%, 6/6 | +33%, 5/6 | ❌ Robustheit schlechter |

**Erkenntnis:** Volume-Spike verbessert ETH massiv (WR 54%→68%), verschlechtert BTC/SOL.
OI-Daten müssen historisch rückwirkend gesammelt werden für echten Test.

### HYP-04: Volume-Confirmed Entry
> "Funding + ungewöhnliches Volume = stärkerer Bounce"

**ERGEBNIS: PASS für ETH, FAIL für BTC/SOL** (2026-05-02)

Gleiches Test wie HYP-03 (Volume als Proxy für OI).
ETH + Volume-Spike = bestes ETH-Ergebnis (+44%, 68% WR).

Ergebnisse: `research/sprint_03_results.json`

### HYP-05: Momentum Breakout
> "Breakout über 20h-High + positiver Funding-Trend = Trend Continuation"

**ERGEBNIS: FAIL** (2026-05-02)

15 Varianten getestet (3 Assets × 5 Strategien):
- 14/15 FAIL, 1 marginal PASS (ETH EMA-Cross bull, +11.67%, 4/6)
- Breakout + Funding = Rauschen, kein Edge
- EMA-Cross + Bull = knapp über Zufall (45% WR)
- Bull+Greed (FGI>60) = marginal, nicht robust

**Erkenntnis:** Momentum auf 1h-Crypto hat keinen robusten Edge.
Breakout-Signale + Funding-Bestätigung verbessern nichts.

Ergebnisse: `research/sprint_04_results.json`

### HYP-06: Regime-Adaptive Strategie
> "In Bullen: Momentum. In Bären: Mean Reversion. Nicht eins von beiden immer."

**ERGEBNIS: PASS** (2026-05-02)

15/30 Varianten PASS — bestes Ergebnis aller Sprints!

**Was funktioniert:**
- ✅ BTC Bull Pullback (mild neg funding z: -0.3 bis -1.0 in bull): +64.83%, 4/6, 348 Trades
- ✅ ETH: 7/10 PASS, Bull Pullback am besten (+71.47%, 5/6, 372 Trades)
- ✅ SOL: 7/10 PASS, Triple Confirm am besten (+46.35%, 5/6)

**Was NICHT funktioniert:**
- ❌ DXY-basierte Strategien (RA04, RA10) — auf allen 3 Assets FAIL
- ❌ FGI Contrarian (RA07) — nur ETH PASS

**Kernerkenntnis:** Bull-Regime hat Edge durch **Funding-basierte Pullback-Käufe**
(mild negative Funding in Bull = Dip kaufen), NICHT Momentum/Breakout.
Das ist Mean Reversion in BEIDEN Regimes, nur mit verschiedenen Thresholds:
- Bear: z < -1.0 (extreme negative Funding)
- Bull: -1.0 < z < -0.3 (mild negative Funding = Pullback)

Ergebnisse: `research/foundry_hyp06_results.json`

---

## Phase 3: Validierung

- [ ] Top 1-2 Strategien ins Paper Trading
- [ ] Evaluation nach 10+ Trades pro Asset
- [ ] Live vs Backtest Divergence messen
- [ ] Wenn kein Edge: ehrlich zugeben

---

## Meta-Frage

> **Ist systematisches Trading mit öffentlichen Daten auf 1h-Crypto profitabel?**

Wenn nach Phase 2 alle 6 Hypothesen FAIL sind, ist die Antwort wahrscheinlich "nicht mit diesem Ansatz". Das ist OK — bessere Erkenntnis als endloses Optimieren.

---

## Zeitplan

| Phase | Dauer | Abhängigkeit |
|-------|-------|-------------|
| 1.1 4h-Candles | 1 Tag | Keine |
| 1.2 Features | 2 Tage | Keine |
| 2.1-2.6 Tests | 3-5 Tage | Phase 1 |
| 3 Validierung | 14+ Tage | Phase 2 |

**Gesamt:** ~3 Wochen bis zur nächsten strategischen Entscheidung.