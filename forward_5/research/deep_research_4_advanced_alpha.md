# Deep Research 4: Advanced Alpha Generation — Microstructure, Liquidation, DeFi, Options

**Quelle:** Google Docs (Deep Research Prompt 4)
**Datum:** 2026-05-04

## Executive Summary

Dieses Dokument beschreibt NEXT-LEVEL Alpha-Quellen jenseits von Funding z-scores: Order Flow Imbalance, Liquidation Cascades, DeFi Yield Signals, Options IV Skew, und Non-Directional Arbitrage.

## Key Findings

### 1. Order Flow Imbalance (OFI) — Das nächste Level
- Limit Order Book (LOB) enthält die echten Prekursors für Price Discovery
- OFI trackt passive + aggressive Veränderungen am BBO (Best Bid/Offer)
- **Event-Time Sampling** statt Clock-Time: aggregiere alle 100 LOB-Updates statt stündlich
- CNN + LSTM auf Event-Time OFI zeigt signifikante Out-of-Sample Vorhersagekraft
- **Problem für uns:** Braucht Tick-Level Binance WebSocket Data — große Infrastruktur-Änderung

### 2. CVD Divergence / Absorption
- Cumulative Volume Delta: Aggressive Buy vs Sell Volume als Druck-Indikator
- **Bearish Divergence:** Preis Higher High, CVD Lower High → unsupported rally → mean reversion
- **Bullish Divergence (Absorption):** Preis Lower Low, CVD stabil → passive Käufer absorbieren → Boden
- **Cohort Filtration:** Nur große Trades isolieren = "Smart Money" Signal
- **Problem für uns:** Braucht Tick-Level Trade-Daten + Größenklassifikation

### 3. Liquidation Cascades — Berechenbare Zwangsliquidationen
- Kyle's Market Impact: ΔP = λ × Q
- Liquidations treiben Preise MECHANISCH zu weiteren Liquidations (Kaskade)
- **Liquidation Heatmaps:** Konzentration von Liquidationspreisen = "magnetic zones"
- Bei λ→∞ (Market Maker ziehen Orders zurück) + Q_liq (forced selling) = exponenzielle Preisbewegung
- **Strategie:** Long wenn Liquidation-Cascade auf Shorts sich erschöpft (Capitulation Bottom)
- **Problem für uns:** Braucht Echtzeit-Liquidationsdaten + Order Book Depth

### 4. DeFi Yield Signals — Leading Indicator
- Aave USDC/USDT Borrow Rate Spikes → Leading Indicator für Binance Funding + Spot Pump
- Wenn Whales Stablecoins aus DeFi ziehen um Longs aufzubauen → Borrow Rate spitzt zu (14-15%)
- On-chain, transparent, Echtzeit verfügbar
- **Umgekehrt:** Einlagen + sinkende Borrow Rates = Risk-Off = Deleveraging
- **Vorteil für uns:** On-chain Daten öffentlich, API verfügbar (Aave, Compound)

### 5. Options Volatility Skew — Deribit 25-Delta Risk Reversal
- **IV Smile:** Steil = große Moves erwartet → TP verbreitern, SL lockern
- **25-Delta Risk Reversal (RR):** IV_call - IV_put
  - Negativer Skew = Puts teurer = Fear → extreme = Capitulation Bottom = Long Entry
  - Positiver Skew = Calls teurer = Greed → extreme = Top = Short Entry
  - **Skew-Normalisierung zurück zu 0** = hoch-präzises Leading Signal
- **Problem für uns:** Deribit Options Daten API verfügbar, aber Options-Komplexität

### 6. Non-Directional Stat-Arb (Cross-Sectional)
- Dynamische Cointegration zwischen Krypto-Paaren (nicht statisch)
- Engle-Granger / Johansen Test für Cointegration
- Mean-Reversion des Spread = Trade unabhängig von Richtung
- **Vorteil:** Markt-neutral, kein Regime-Risiko, kein Directional-Risiko
- **Beispiel:** SOL/ETH Ratio Mean-Reversion, BTC/ETH Basis-Spread
- **Fee-Problem:** High Turnover, braucht Maker-Fees (Limit Orders)

### 7. Capital-Effiziente Execution für €500
- **Maker-Orders statt Taker-Orders** — 0.02% vs 0.05% (60% Fee-Sparung)
- **TWAP/Iceberg** um Slippage zu minimieren
- **Funded Accounts** (Prop-Firms) statt eigenes Kapital
- **Problem:** 500€ Taker-Fees fressen jeden kleinen Edge; Maker-Fees sind überlebenswichtig

## Actionable Prioritäten (aus Doc 4)

| Signal | Daten-Requirement | Infra-Aufwand | Alpha-Potential | Für uns machbar? |
|--------|-------------------|----------------|-----------------|------------------|
| 4h Funding Sweep | Vorhanden | Niedrig | Mittel | ✅ SOFORT |
| Cross-Sectional Funding | Vorhanden | Mittel | Hoch | ✅ Nächste Woche |
| DXY/FGI Regime-Filter | Vorhanden | Niedrig | Mittel | ✅ Nächste Woche |
| DeFi Yield (Aave) | API verfügbar | Mittel | Hoch | 🟡 Nach Infra |
| Options Skew (Deribit) | API verfügbar | Mittel | Hoch | 🟡 Nach Infra |
| CVD Divergence | Tick-Data nötig | Hoch | Sehr hoch | ❌ Später |
| OFI / LOB | Tick-Data + WS | Sehr hoch | Sehr hoch | ❌ Später |
| Liquidation Cascades | Echtzeit-Liq-Data | Hoch | Sehr hoch | ❌ Später |
| Stat-Arb Pairs | Vorhanden | Mittel | Mittel-Hoch | ✅ Nächste Woche |

## Kern-Botschaft

**Wir müssen aufhören, stundenlang zu angeln.** Die Low-Hanging Fruits die wir mit unseren Daten schon testen können:
1. 4h Funding Sweep (aligned mit Epoch)
2. Cross-Sectional Funding (relatives Funding)
3. DXY/FGI Regime-Filter
4. Stat-Arb Pairs (Cointegration)

Dann als nächste Stufe mit API-Daten:
5. DeFi Yield (Aave Borrow Rates)
6. Options Skew (Deribit 25-Delta RR)

Tick-Level (OFI, CVD, Liquidations) = Phase für später wenn die Infrastruktur steht.