# Deep Research 3: Statistical Validation, Regime Risk, and Execution Viability

**Quelle:** Google Docs (Deep Research Prompt 3)
**Datum:** 2026-05-04

## Executive Summary

Dieses Dokument ist das kritischste der drei. Hauptthese: **Die SOL funding Strategie ist mit hoher Wahrscheinlichkeit ein statistischer False Positive** aufgrund des Multiple Testing Problems (6000 Backtests → 1 passing). Zudem ist €500 bei 5x Leverage mathematisch nicht überlebensfähig aufgrund von Fee-Drag.

## Key Findings

### 1. Multiple Testing Problem — SEHR KRITISCH
- 6000 Backtests → 1 passing Strategie = **textbook multiple testing problem**
- Nach DSR (Deflated Sharpe Ratio) von López de Prado: Die SOL Strategie **ist mathematisch garantiert** den DSR-Test zu scheitern
- Expected max Sharpe Ratio nach 1000 unabhängigen Backtests auf Zufallsdaten = 3.26
- Bonferroni-Korrektur ist zu konservativ für korrelierte Finanzdaten → DSR stattdessen
- **Fazit: 1/6000 = False Positive, nicht Alpha**

### 2. Walk-Forward ist nicht genug
- WFA testet nur EINEN historischen Pfad
- 24 trades/window = leicht durch Zufall 70% zu erreichen
- Empfohlen: **Combinatorial Purged Cross-Validation (CPCV)**
  - Purging: Entfernt überlappende Daten um Test-Sets
  - Embargoing: Zusätzlicher Buffer nach Test-Sets
  - Generiert Distribution von Sharpe Ratios über mehrere Pfade
- Bootstrap zerstört serielle Korrelation → ungeeignet
- Monte Carlo braucht akkurate Fat-Tail-Modelle → schwer

### 3. Regime Risk — Bärenmarkt = Tod
- 2024-2026 = predominantly bullish
- 2022 Bärenmarkt: BTC -78%, Funding monatelang negativ/Null
- SOL z∈[-0.5, 0) würde in einem Bärenmarkt **kontinuierlich Longs triggern** → sequenzielle 5% SL-Verluste
- **Ohne Regime-Filter ist die Strategie in einem Bärenmarkt bankrott**

### 4. €500 bei 5x = Mathematischer Ruin
- Taker Fees (0.05%) + Slippage (0.03%) + Funding-Kosten fressen kleine Edges
- Bei 239 Trades in 2.5 Jahren ≈ 96 Trades/Jahr
- Pro Trade: ~0.16% Kosten (0.08% round-trip + slippage)
- 96 × 0.16% × 5x leverage = **76.8% annual cost drag**
- **Die Strategie muss >76.8% pro Jahr returnen NUR UM KOSTEN ZU DECKEN**
- Das ist bei ~5% OOS return pro Trade unrealistisch

### 5. Cross-Asset Spillover statt univariate Signale
- BTC Returns und Funding sind statistisch signifikante Prädiktoren für Altcoin-Returns
- "Gradual Information Diffusion" — BTC absorbiert Info sofort, Alts reagieren mit Verzögerung
- Adaptive LASSO + PCA auf BTC-Features → bessere Out-of-Sample Returns als univariate Modelle
- **BTC als Leading Indicator für SOL nutzen, nicht SOL-Funding allein**

### 6. Short-Side: Nochmal bestätigt
- Mildly positive funding = Equilibrium-Zustand (wegen Basisrate)
- z ∈ [0, 1.5] = **kein Short-Signal**, das ist normaler Contango
- Short nur bei z > 1.5-2.0 (extreme overcrowding)

## Actionable Changes (NEUE KRITISCHE ERKENNTNISSE)

| Item | Alt | Neu | Grund |
|------|-----|-----|-------|
| WF-Validierung | R≥70, 10 Windows | **CPCV** + DSR | 1 Pfad = nicht robust genug |
| Multiple Testing | Ignoriert | **DSR berechnen** | 1/6000 = wahrscheinlich False Positive |
| Regime-Filter | Nice-to-have | **KRITISCH** | Bärenmarkt = kontinuierliche SL-Verluste |
| Kapital | €500 @ 5x | **Paper traden bis €5k+** oder Funded | Fee-Drag = 76.8%/Jahr |
| Cross-Asset | Nicht im Plan | **BTC → SOL Spillover** | Gradual Information Diffusion |
| Short | z>0.5 | **z>1.5-2.0 oder streichen** | Nochmal bestätigt: mild positiv = normal |

## Harter Wahrheitscheck

Dieses Dokument sagt im Kern:
1. **Unsere SOL Strategie ist wahrscheinlich ein False Positive** (1/6000)
2. **€500 @ 5x ist nicht überlebensfähig** (Fee-Drag > Edge)
3. **WF allein reicht nicht** als Validierung
4. **Ohne Regime-Filter stirbt die Strategie im nächsten Bärenmarkt**

Das ändert die Prioritäten fundamentally:
- CPCV + DSR Implementierung VOR weiterer Strategie-Entwicklung
- Regime-Filter (DXY + FGI) VOR Live-Geh
- Kapital-Frage klären: Paper traden bis genug Edge bewiesen ist