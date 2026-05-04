# Deep Research 1: Funding-Rate Mean-Reversion Strategies

**Quelle:** Google Docs (Dave's Deep Research Prompt)
**Datum:** 2026-05-04

## Executive Summary

- Funding rates sind strukturell mean-reverting, aber als standalone Alpha für ein einzelnes Asset **schwach** — stärker an Extremen und im cross-sectional/stat-arb
- FGI hat teilweise predictive power, aber zeitvarierend und regime-sensitiv; DXY ist als trigger unzuverlässig
- **SOL funding edge ist plausibel aber fragil** — tied to SOL's current market structure, likely to decay as more basis-arb capital enters
- **Short-side symmetry NICHT unterstützt** —_edges sind asymmetrisch und konzentriert an Extremen, nicht bei mild positiven Werten
- 4h+ bars und 1-7 day holding verbessern Signalstabilität (bestätigt unsere 24h exits)
- 500€/5x mit 50-100% annual target ist ambitioniert aber nicht unmöglich mit mehreren unkorrelierten Signalen

## Key Findings

### 1. Funding als Edge
- Presto Labs: Funding changes erklären 12.5% der 7-day Preisvariation im Aggregat, aber **0% single-step prediction** für ein Asset
- Cross-sectional (relatives Funding zwischen Assets/Exchanges) = stat-signifikant
- Rho Labs: Funding-Spread Binance vs OKX als Signal

### 2. Warum SOL aber nicht BTC/ETH
- BTC/ETH: zu tief liquide, zu viel basis-arb, edges sofort komprimiert
- SOL: weniger reif, volatileres Funding, mehr Retail-Flow = persistente Behavioral Biases
- Ethena-Dokumente: SOL Funding "systematisch günstiger" als BTC/ETH 2023-2025
- Edge wahrscheinlich **strukturell aber decayend**

### 3. Short-Seite
- Literatur: Extreme Werte (>0.1% raw, oder z>2) als contrarian Short
- **Keine Evidenz für Symmetrie bei mild positiven Werten**
- Liquidation mechanics sind asymmetrisch
- Fazit: Short bei z>1.5-2.0, nicht bei z>0.5

### 4. FGI/DXY
- FGI: Etwas predictive power an Extremen, regime-sensitiv
- DXY: Negativ korreliert mit BTC aber instabil
- **Beide als Filter/Regime, nicht als Entry-Trigger**

### 5. Portfolio Construction
- 2-4 unabhängig validierte Signale nötig
- Minimum order size und fee drag sind das Hauptproblem bei 500€
- Cross-sectional approaches skalieren besser aber brauchen mehr Infrastruktur

### 6. WF-Statistik
- 24 trades/window = "borderline" sample size
- Bonferroni-Korrektur nötig für Multiple Testing
- Monte Carlo Bootstrap empfohlen
- P(7/10 windows profitable by chance) = "small but non-negligible"

### 7. Overfitting
- ~6000 Backtests für 1 passing Strategie
- SOL als einziges Asset = "against pure overfitting" (wenn alle Assets bestehen würden wäre es Data Mining)
- Aber: Regime-Shift Risk — SOL's microstructure hat sich drastisch geändert (FTX, narrative revival)

## Actionable Recommendations

1. **Cross-sectional Funding** als neue Signal-Klasse (SOL vs BTC vs ETH funding spread)
2. **Short-Seite: z>1.5-2.0 statt z>0.5** — extreme Werte, nicht milde
3. **Regime-Stabilität prüfen** — SOL-Signal in Bull/Bear/Sideways segmentieren
4. **Monte Carlo Bootstrap** statt nur WF-Gate
5. **Fee-Impact bei 500€/5x modellieren** (min order size drag)
6. **FGI als Regime-Filter** auf bestehendes SOL-Signal, nicht als Entry