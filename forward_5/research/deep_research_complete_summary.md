# Deep Research — Komplette Synthese (4 Dokumente)

## ⚠️ KERNBEFUNDE — Das ändert alles

### 1. SOL Funding Edge = wahrscheinlich False Positive
- 1/6000 Backtests → statistisch erwartet 1-2 False Positives
- **Deflated Sharpe Ratio (DSR) Test** besteht wahrscheinlich NICHT
- 24 Trades/WF-Window < 30 (CLT-Minimum) = nicht robust
- Brauche: Monte Carlo, CPCV, Bonferroni-Korrektur

### 2. €500 @ 5x = Deterministic Ruin
- 239 Trades × ~2€ Fees = 478€ Fee-Drag (95.6% des Kapitals!)
- Selbst bei 20% p.a. Return = 100€ Gewinn < 120€ VPS-Kosten
- **Realistischer Frame:** R&D-Projekt, kein Profit-Center
- Prop-Firm oder Kapital-Scaling nötig für Profitabilität

### 3. Foundry-V13b Label-Bug bestätigt
- `bear_z<-0.5` war eigentlich z∈[-0.5, 0) = mild negativ
- Extreme z-Scores zerstören Performance (zu wenige Trades)
- **Nur mild negatives Funding hat Edge** — aber fragil

### 4. Short-Seite = ASYMMETRISCH
- z∈[-0.5, 0) → Long funktioniert NICHT symmetrisch als Short
- Mild positives Funding = normaler Contango, kein Signal
- Short braucht z>3.0 + OI-Divergenz oder streichen

---

## Signal-Familien (Ranking nach Viability bei €500)

### 🟢 Tier 1: Sofort umsetzbar mit vorhandenen Daten

| Signal | Was | Daten | Aufwand |
|--------|-----|-------|---------|
| **SOL z∈[-0.5,0) Long** | Aktueller Champion | Funding 8h | ✅ Live, aber fragil |
| **FGI < 40 Confluence-Filter** | Longs nur bei Fear | FGI Daily | Klein |
| **DXY 10d-ROC Regime-Filter** | Longs skippen bei starkem USD | DXY Daily | Klein |
| **EMA200 Bull-Regime-Filter** | Longs nur über EMA200 | Preis 1h | Klein |

### 🟡 Tier 2: Neue Datenquellen nötig, aber kostenlos

| Signal | Was | Daten | Aufwand |
|--------|-----|-------|---------|
| **Cross-Sectional Funding** | Long niedrigstes, Short höchstes Funding | 6-Asset Funding | Mittel |
| **Post-Liquidation Mean Reversion** | Post-Flush Long nach Kaskade | Liquidation-Daten | Mittel |
| **OI-Reset + Funding-Flip** | OI-Drop + Funding-Vorzeichenwechsel | OI stündlich | Mittel |
| **Pre-Cascade "Loaded Spring"** | OI ATH + extrem Funding = Risk-Brake | OI + Funding | Mittel |
| **BTC-Dominance Regime** | BTC↑ = Alts↓, umgekehrt | BTC Dom Index | Klein |

### 🔴 Tier 3: Mehr Infrastruktur/Kosten nötig

| Signal | Was | Daten | Aufwand |
|--------|-----|-------|---------|
| **DeFi Yield Regime** | On-Chain Leverage-Index | Aave/Compound API | Hoch |
| **Whale Exchange Flows** | Großeinlagen → Selling | On-Chain Analytics | Hoch |
| **Options IV Skew** | Puts reich + Perps long = Vermeiden | Deribit/Delta Exchange | Mittel |
| **OFI (Order Flow Imbalance)** | Taker Net Volume als Timing | Tick-Data oder 1m | Sehr hoch |
| **Basis Arbitrage** | Spot-Perp Carry | Multi-Venue | Hoch |

---

## Statistische Anforderungen (ALLE Docs stimmen überein)

1. **DSR (Deflated Sharpe Ratio)** — muss bestehen, sonst False Positive
2. **Monte Carlo Permutation** — Trade-Reihenfolge resamplen
3. **CPCV** statt reines Walk-Forward (Combinatorial Purged CV)
4. **Bonferroni/FDR** — Multiple-Testing-Korrektur für 6000 Backtests
5. **Min 30 Trades/WF-Window** — aktuell 24, zu wenig
6. **t-Stat > 3.0** statt > 2.0 (Harvey et al., Data Mining Adjustment)
7. **3+ unkorrelierte Signale** für Portfolio-Stabilität
8. **Korrelations-Check** — neue Signale gegen SOL testen (≥0.7 = korreliert)

---

## Architektur-Empfehlungen

### Exchange: Hyperliquid > Binance
- Maker: 0.015%, Taker: 0.035% (vs Binance 0.02%/0.05%)
- Maker-Rebate bis -0.003%
- Kontinuierliche Funding-Rate (1h statt 8h)
- Kein KYC für Basis-Funktionen

### Execution: WebSocket Pflicht
- REST API Polling = unakzeptabel für Live
- Bei €500: Limit Orders bevorzugen (Maker-Gebühren)
- OFI als Adverse-Selection-Filter (nicht in feindlichen Flow reingehen)

### Timeframe: Multi-Layer
| Layer | Horizont | Zweck |
|-------|----------|-------|
| Fast (5-15m) | Execution-Timing | OFI, Spread-Qualität |
| Medium (1-4h) | Entries/Exits | Funding, Preis, Liquidationen |
| Slow (1-7d) | Regime-Filter | FGI, DXY, DeFi, Whale, Skew |

### 4h Sweet Spot
- 2 Updates pro 8h Funding-Epoch = mathematisch aligned
- Reduziert Rauschen vs 1h
- Foundry V12 "WidePullback" bestätigt (R=67 auf BTC 4h)

---

## Kapital-Strategie

### Aktuell (€500 @ 5x)
- Fee-Drag dominiert bei modestem Sharpe
- VPS-Kosten > erwarteter Net-Return
- **Paper Trading + Token Live (10-50€)** bis Edge bestätigt

### Skalierung (6-12 Monate)
1. Track Record mit Paper + Token Live aufbauen
2. Prop-Firm Evaluation (TopStep, Earn2Trade, etc.)
3. Bei Prop-Zugang: $10-50k Kapital → Fee-Drag vernachlässigbar
4. Alternativ: Eigenkapital auf €2-5k bringen

### Steuern (Deutschland)
- 25% Abgeltungsteuer auf Gewinne
- Verluste nur gegen Gewinne aus gleichen Geschäften verrechenbar
- Holding-Period < 1 Jahr = voll steuerpflichtig
- Einfluss auf Net-Return: 25% weniger effektiv

---

## 3 Empfohlene Forschungstracks (Priorität)

### Track 1: Liquidation + OI Reset Edge
- **Daten:** Stündliche Liquidationen (Long/Short), OI, Funding, Preis
- **Hypothese A:** Nach Large Long-Liquidation + OI-Drop + Funding-Flip → Long 24-72h
- **Hypothese B:** Nach Short-Squeeze + OI-Reset + Funding-Spike → Vermeiden (Exhaustion)
- **Pre-Cascade Filter:** OI ATH + Funding extrem → Tighten Stops / Skip Entries
- **Deliverable:** "Post-Flush" Strategie mit klaren Parametern, WF-getestet

### Track 2: DeFi Yield / Leverage Regime Filter
- **Daten:** Daily Lending/Borrowing APYs (Aave/Compound), Funding/Basis
- **Hypothese:** Strategien performen besser in "gesundem" Leverage-Regime
- **Regime-Klassen:** OFF / NORMAL / OVERHEATED / DEAD
- **Deliverable:** Generischer Regime-Filter für alle Strategien

### Track 3: Cross-Sectional Funding/Basis Tilt
- **Daten:** Stündliches Funding über 6 Assets
- **Hypothese:** Long niedrigstes Funding, Short höchstes = robuster als Single-Asset
- **Skalierung:** Natürlicher von €500 auf €5k+ (mehr Assets = mehr Diversifikation)
- **Deliverable:** Portfolio-Level Stat-Arb Strategie

---

## Was Foundry NICHT tun sollte
- 6000 Parameter-Sweeps kontaminieren statistische Integrität
- LLM-Exploration = Hypothesen-Generator, nicht Validator
- Strenge Trennung: Research (Foundry) ≠ Validation (Deterministic Sweep + WF)
- **Theory-first:** Hypothese aufschreiben BEVOR Parameter gesweept werden

---

## Edge Decay — Was den SOL-Champion töten könnte
1. Ethena betritt SOL-Markt → Funding wird effizienter
2. Mehr Basis-Arb-Kapital → Funding komprimiert
3. SOL ETF → Institutionelle Preise = weniger Retail-Ineffizienz
4. Exchange-Änderungen (Funding-Caps, Berechnungsformel)
5. Macro-Schocks → Funding bleibt über längere Zeit verzerrt
6. **Monitoring:** Quartalsweise Re-Sweeps, Funding-Distribution tracken