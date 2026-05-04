# Forward V5 — Master Roadmap
**Stand:** 2026-05-04  
**Status:** Post-Deep-Research, Pre-Implementation  
**Ziel:** 3+ unkorrelierte WF-passed Signale → profitables System bei skaliertem Kapital

---

## 📍 Wo wir stehen

### Was funktioniert
- **SOL z∈[-0.5, 0) Long + EMA200** — WF R=70, OOS=+4.83%, 239 Trades
- **V2 Paper Engine** — läuft, SOL/BTC/ETH, Capital 100€
- **Foundry V12** — 4/24 passed OOS, findet ergänzende Ansätze
- **359 Tests** — Pre-Commit Hook grün

### Was NICHT funktioniert
- **€500 @ 5x** — Fee-Drag frisst 77% der Returns = deterministischer Ruin
- **SOL-only** — Single point of failure, Edge wahrscheinlich False Positive (1/6000 BT)
- **Short-Seite** — z>0.5 = tot, braucht z>3.0 + OI-Divergenz
- **Statistische Robustheit** — 24 Trades/WF-Window < 30, kein DSR, keine Monte Carlo

### Was die Research gelehrt hat
- 4h = mathematischer Sweet Spot (2 Updates/8h Epoch)
- DXY -0.72 Korrelation mit BTC → starker Regime-Filter
- Cross-Sectional Funding = neue Signal-Klasse mit belegter Alpha
- Prop-Firm = viahter Skalierungspfad (Breakout Prop ⭐)
- Hyperliquid = bessere Fees + stündliches Funding, aber Parallelbetrieb mit Binance
- DeFi Utilization + Liquidations als Regime-Filter nutzbar
- §15 EStG (Gewerbe) = steuerlich VORTEILHAFT vs §20 EStG bei Prop-Firm

---

## 🗺️ Roadmap — 3 Phasen, 12 Monate

### **PHASE 0: FOUNDATION (Woche 1-4)** ⬅️ JETZT
*Stabilisieren was da ist, Daten-Infra aufbauen, Statistik reparieren*

#### 0.1 V2 Engine Fix & Stabilisierung [1 Woche]
- [ ] SOL Signal-Parameter: z<-1.5 → **z∈[-0.5, 0)** (V13b beweist: mild negativ = robust)
- [ ] Trailing Stop komplett entfernen (V13b: immer schlechter)
- [ ] 4h-Kerzen-Aggregation implementieren (I2, Priorität 1)
- [ ] Exit: 24h time-based, SL 4% (von 5% runter für Prop-Firm-Kompatibilität)
- [ ] Hyperliquid als Parallel-Exchange integrieren (ccxt.hl)
- [ ] **Test:** `pytest tests/ -v` → grün

#### 0.2 Liquidation Data Pipeline [1-2 Wochen]
- [ ] Binance `!forceOrder@arr` WebSocket Daemon → SQLite
  - Referenz: `binance-liquidation-tracker` (Python)
  - Schema: `(ts, symbol, side, qty, price, notional, liq_side)`
  - Rollup: 1h Aggregate pro Asset + Long/Short
- [ ] Coinalyze `liquidation_history` API für 60-Tage-Backfill (kostenlos)
- [ ] Hyperliquid: Dune Dashboard für Tages-Aggregate (kostenlos)
- [ ] **Deliverable:** `data/liquidations/` mit 1h-Aggregaten für BTC/ETH/SOL

#### 0.3 DeFi Regime Data Pipeline [1-2 Wochen]
- [ ] DeFiLlama API: `/yields/chartLendBorrow/{pool}` für Aave ETH/USDC Utilization
- [ ] Solend REST API: SOL + USDC Supply/Borrow/APY
- [ ] Kamino API: Lending Pool Metrics
- [ ] DeFiLlama Stablecoins API: Solana Stablecoin Market Cap
- [ ] **Deliverable:** `data/defi/` mit täglichen Regime-Metriken

#### 0.4 Statistische Robustheit [2-3 Wochen]
- [ ] Monte Carlo Permutation Test (1000 Resamples der Trade-Reihenfolge)
- [ ] Deflated Sharpe Ratio (DSR) — López de Prado Test
- [ ] Bonferroni-Korrektur für 6000 Backtests → angepasste Signifikanz
- [ ] Min 30 Trades/WF-Window sicherstellen (ggf. 6-Monats-Windows statt 2-Monats)
- [ ] **Deliverable:** `research/statistical_robustness.py` mit DSR/MC/Bonferroni

#### 0.5 Korrelations-Matrix [1 Woche]
- [ ] Alle Signale (SOL, BTC 4h, ETH 4h, Macro-Filter) gegen SOL-Champion testen
- [ ] Spearman + Rolling Correlation (30d Fenster)
- [ ] Schwelle: ρ ≥ 0.7 = korreliert, nicht als 2. Signal zählbar
- [ ] **Deliverable:** `research/correlation_matrix.py`

---

### **PHASE 1: SIGNAL DISCOVERY (Woche 5-12)**
*Neue Signale finden, validieren, kombinieren*

#### 1.1 4h Sweep [2-3 Wochen] — PRIORITÄT 1
- [ ] Funding Z-Score auf 4h-Kerzen (statt 1h/8h)
- [ ] Sweep: 6 Assets × z-Ranges × SL-Varianten × Hold-Periods
- [ ] WF-Validierung mit robuster Statistik (DSR, MC)
- [ ] Erwartung: Bessere Alignment mit 8h Funding Epoch = robustere Signale
- [ ] Foundry V12 bestätigte: BTC 4h WidePullback + Bull200 = OOS 4/6

#### 1.2 Post-Liquidation Mean Reversion [2-3 Wochen]
- [ ] Hypothese A: Large Long-Liquidation + OI-Drop + Funding-Flip → Long 24-72h
- [ ] Hypothese B: Pre-Cascade (OI ATH + extremes Funding) → Skip/Tighten
- [ ] Daten: 1h Liquidations (Binance WS) + OI + Funding + Preis
- [ ] Signal: `liq_pct_oi > 3σ` = Cascade Flag; zurück < 1σ = Entry-Zone
- [ ] **Test:** Backtest 12+ Monate, WF mit 30+ Trades/Window

#### 1.3 DeFi Regime Filter Integration [2-3 Wochen]
- [ ] Filter 1: Aave ETH+USDC Utilization < 75% + nicht 30d-Hoch → Longs erlauben
- [ ] Filter 2: Deleveraging-Intensity Cooldown — 24h Liq/TVL > 95%.Perz = BLOCK
- [ ] Filter 3: Solana-Local — Solend+Kamino USDC Utilization 40-80% + Solana Stablecoin Share nicht im 30d-Tief
- [ ] Korrelation mit Funding Z-Score testen: < 0.5 = wertvoll, > 0.7 = redundant
- [ ] **Test:** Jeden Filter einzeln + kombiniert gegen SOL-Champion backtesten

#### 1.4 Cross-Sectional Funding [2-3 Wochen]
- [ ] Daten: Stündliches Funding über 6 Assets (BTC/ETH/SOL/AVAX/DOGE/ADA)
- [ ] Signal: Long Asset mit niedrigstem Funding, Short höchstes (oder skip Short)
- [ ] Natürliche Diversifikation über Assets
- [ ] Korrelation mit SOL-Champion testen
- [ ] **Test:** Portfolio-Level Backtest mit Risk-Parity Weighting

#### 1.5 Macro-Filter (DXY + FGI) [1-2 Wochen]
- [ ] DXY 10d-ROC: 2%+ Rückgang = 94% BTC-Win-Rate → Long-Filter
- [ ] FGI < 40: Confluence-Filter für Longs (nie alleiniger Entry)
- [ ] Einfach zu implementieren, hohe erwartete Filter-Wirkung
- [ ] **Test:** Overlay auf bestehende Signale, Messung von gefilterten vs. gefangenen Trades

#### 1.6 Short-Seite: Neu definieren [1 Woche]
- [ ] z>3.0 + OI-Divergenz statt z>0.5 (Deep Research: z>0.5 = normaler Contango)
- [ ] Falls keine Signale bei z>3.0: Short-Seite komplett streichen
- [ ] **Entscheidung:** Short nur mit OI-Bestätigung, oder Long-only bleiben

---

### **PHASE 2: VALIDATION & SCALING (Woche 13-24)**
*Robustheit beweisen, Kapital skalieren*

#### 2.1 Rigorous Validation [4 Wochen]
- [ ] Alle Phase-1 Signale durch DSR + Monte Carlo + Bonferrori laufen
- [ ] CPCV (Combinatorial Purged Cross-Validation) statt reines WF
- [ ] Mindestens 3 unkorrelierte Signale (ρ < 0.7 untereinander)
- [ ] Live Paper Trading 90 Tage mit allen Signalen
- [ ] **Gate:** Nur Signale die DSR bestehen → Phase 2.2

#### 2.2 Capital Scaling: Prop-Firm Path [2-4 Wochen]
- [ ] **Target:** Breakout Prop (Kraken) — $25k Account
  - Evaluation: ~$100-150, 1-Step
  - Static 6% MaxDD, keine Konsistenz-Regeln, kein Pflicht-SL
  - ⚠️ SOL = nur 2x Leverage → BTC/ETH (5x) bevorzugen auf Breakout
- [ ] **Parallel:** HyroTrader (Bybit) — für SOL (1:100 Leverage)
  - SL innerhalb 5 Min Pflicht → im Bot hardcoden
  - Trailing Drawdown → Float-Management wichtig
- [ ] **Position Sizing:** 1% Equity Risk/Trade → 0.2x effektiv
  - $25k × 20% = $5k Position → $241.50 PnL/Trade (vor Split)
  - Netto: ~$1,082/Monat bei 80% Split - 30% Steuer
- [ ] **Budget:** 2-3 Evaluations = €300-600 Risk

#### 2.3 Steuern & Admin [1-2 Wochen]
- [ ] Gewerbeanmeldung (§15 EStG, nicht §20!)
- [ ] USt-IdNr. beantragen (Reverse-Charge für Prop-Firm Payouts)
- [ ] Evaluation-Gebühren als Betriebsausgaben verbuchen
- [ ] Rechnungsvorlage mit Steuerschuldnerschaft-Klausel
- [ ] **Vorteil:** Kein €20k Verlustabzugsdeckel + VPS/Kosten voll absetzbar

#### 2.4 Copy Trading: Parallel Path [ab Woche 16]
- [ ] Nach 90 Tagen Track Record → Bitget/Bybit Lead Trader registrieren
- [ ] 8-15% Follower-Gewinne, NULL Einschränkungen
- [ ] Kann parallel zu Prop-Firm laufen
- [ ] **Voraussetzung:** Öffentlicher Track Record auf V2 Engine

#### 2.5 Solana Foundation Grant (Optional) [1-2 Wochen Aufwand]
- [ ] Micro-Grant $5,000-$10,000 für Open-Source Quant-Tools
- [ ] Bedingungen: Teile des Stacks open-source (z.B. Data Pipeline, Backtest Framework)
- [ ] Kein IP-Transfer, keine Equity-Dilution
- [ ] **Nutzen:** Seed Capital ohne Prop-Firm-Regeln

---

### **PHASE 3: OPERATIONAL EXCELLENCE (Woche 25-52)**
*Multi-Venue, Multi-Signal, Monitorig, Edge Decay Prevention*

#### 3.1 Multi-Venue Execution
- [ ] Hyperliquid parallel zu Binance/Bybit/Kraken
  - Stündliches Funding = 8× mehr Datenpunkte für Z-Score
  - Maker 0.015% (realistisch) vs Binance Taker 0.04%
  - SOL-Exposure schrittweise zu HL migrieren
- [ ] Smart Order Routing: Limit Orders bevorzugen (Maker-Fees)
- [ ] VPS-Latency: AWS Frankfurt für Bybit/Kraken API

#### 3.2 Portfolio-Level Risk Management
- [ ] Risk-Parity über 3+ unkorrelierte Signale
- [ ] Max Korrelation zwischen Signalen: ρ < 0.7
- [ ] Total Portfolio Risk: 2% max pro Trade
- [ ] Drawdown-Monitor mit automatischem Throttle

#### 3.3 Edge Decay Monitoring
- [ ] Quartalsweise Re-Sweeps der Champion-Parameter
- [ ] Funding-Distribution tracken (Shift = Edge Decay)
- [ ] Watch: Ethena SOL-Entry, SOL ETF, Exchange-Formel-Änderungen
- [ ] Alert: Win-Rate < 50% über 30 Trades →自动停机

#### 3.4 Monitoring & Reporting
- [ ] Equity-Kurve Dashboard (Daily PnL, Drawdown, Win Rate)
- [ ] Daily Report via Discord #system
- [ ] Weekly Performance Review (Sharpe, Sortino, MaxDD)
- [ ] Monthly Strategy Health Check (Edge Decay Indicators)

#### 3.5 Data Pipeline Maintenance
- [ ] Binance Liquidation WS: Health-Check + Auto-Reconnect
- [ ] DeFiLlama: Tägliches Update (Cron)
- [ ] Coinalyze: Stündlicher Poll für Backfill-Validierung
- [ ] Dune: Wöchentlicher Hyperliquid-Export
- [ ] Tardis.dev: Einmaliger Backfill wenn nötig ($49-149/Monat für 1-2 Monate)

---

## 📊 Erfolgs-Metriken & Gates

| Gate | Kriterium | Nächster Schritt |
|------|-----------|------------------|
| **G0** | V2 Engine stabil + 4h Daten | → Phase 1 |
| **G1** | 1+ neues Signal mit DSR bestanden | → Integration |
| **G2** | 3+ unkorrelierte Signale (ρ<0.7) | → Phase 2 |
| **G3** | 90 Tage Paper Trading profitabel | → Prop-Firm Evaluation |
| **G4** | Prop-Firm Evaluation bestanden | → Funded Trading |
| **G5** | 6 Monate Funded profitabel | → Copy Trading + Scale |

---

## 🎯 Signal-Familien: Status & Priorität

| # | Signal | Status | Phase | Korrelation (erw.) | Aufwand |
|---|--------|--------|-------|---------------------|---------|
| S1 | SOL z∈[-0.5,0) Long | ✅ Champion (fragil) | 0 Fix | — | 1 Woche |
| S2 | BTC/ETH 4h WidePullback | 🟡 Foundry V12: OOS 4/6 | 1.1 | ~0.4-0.6 | 2-3 Wochen |
| S3 | Post-Liquidation Mean Reversion | 🔴 Daten nötig | 1.2 | ~0.3-0.5 | 2-3 Wochen |
| S4 | DeFi Regime Filter | 🔴 Daten nötig | 1.3 | ~0.3-0.5 (Filter) | 2-3 Wochen |
| S5 | Cross-Sectional Funding | 🔴 6-Asset Daten nötig | 1.4 | ~0.2-0.4 | 2-3 Wochen |
| S6 | DXY 10d-ROC Filter | 🟢 Daten vorhanden | 1.5 | ~0.2-0.3 (Filter) | 1 Woche |
| S7 | FGI<40 Confluence | 🟢 Daten vorhanden | 1.5 | ~0.1-0.2 (Filter) | 1 Woche |
| S8 | Short z>3.0 + OI-Div | 🔴 Wahrscheinlich tot | 1.6 | ??? | 1 Woche |

**Ziel:** S1 + S2 + S3 oder S5 = 3 unkorrelierte Signale
**Filter-Stack:** S6 + S7 + S4 = Regime-Overlay auf alle Signale

---

## 💰 Kapital-Strategie: Der Skalierungspfad

```
€500 @ 5x (aktuell) → Fee-Drag 77% → NICHT lebensfähig
     ↓ Paper Trading + Bugfixes (Phase 0-1, €0 additional)
     ↓ Track Record 90 Tage
€500 @ 1-2x Token Live → Fee-Drag ~30% → marginal
     ↓ Prop-Firm Evaluation
$25k @ 0.2x effektiv → Fee-Drag <5% → LEBENSFÄHIG
     ↓ 80% Profit Split + §15 EStG
Netto: ~$1,082/Monat (S1-only, konservativ)
     ↓ 3+ Signale + Copy Trading
$50k+ Multi-Signal → $2k-4k/Monat Netto
```

---

## ⚠️ Hauptrisiken

1. **SOL Edge = False Positive** — DSR könnte zeigen dass der Champion Schein ist
2. **Prop-Firm Breach** — 5% SL bei $25k = gefährlich nah an 4% Daily Loss Limit
3. **Edge Decay** — Ethena, SOL ETF, mehr Arbs = Funding wird effizienter
4. **Correlation Surprise** — Neue Signale könnten mit SOL korrelieren (ρ>0.7)
5. **Hyperliquid Smart-Contract Risk** — Immer parallel zu CEX laufen
6. **Tax Uncertainty** — §15 EStG = beste Einschätzung, aber Finanzamt entscheidet

---

## 📅 Timeline-Übersicht

```
Woche 1-4:   ████████ Phase 0: Foundation
Woche 5-12:  ████████████████ Phase 1: Signal Discovery  
Woche 13-24: ████████████████ Phase 2: Validation & Scaling
Woche 25-52: ████████████████████████████ Phase 3: Operational Excellence

Key Milestones:
  W2:  V2 Engine gefixt + Liquidation WS läuft
  W4:  DeFi Pipeline + Statistische Robustheit implementiert
  W8:  4h Sweep + Post-Liquidation Signal getestet
  W12: 3+ Signale identifiziert + Korrelations-Matrix
  W16: 90-Tage Paper Record → Prop-Firm Evaluation starten
  W20: Funded Account aktiv
  W24: Copy Trading registriert
  W36: Multi-Venue + Multi-Signal voll operational
  W52: Jahr-1 Review: Sharpe, Profit, Edge Decay Check
```

---

## 📎 Research-Archive

Alle Deep Research Dokumente in `research/`:
- `deep_research_1_funding.md` — Funding Rate Mechanisms
- `deep_research_2_quantitative.md` — Quantitative Frameworks
- `deep_research_3_statistics.md` — Statistical Robustness
- `deep_research_4_advanced_alpha.md` — Advanced Alpha Sources
- `deep_research_complete_summary.md` — Synthese der ersten 4 Docs
- `deep_research_hyperliquid.txt` — Hyperliquid Migration
- `deep_research_propfirm.txt` — Prop-Firm Evaluation (Summary)
- `deep_research_propfirm_full.txt` — Prop-Firm Evaluation (Volltext)
- `deep_research_defi.txt` — DeFi Yield & Regime Filter
- `deep_research_liquidations.txt` — Liquidation Data Sources