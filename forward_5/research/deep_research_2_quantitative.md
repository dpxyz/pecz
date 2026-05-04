# Deep Research 2: Quantitative Evaluation of Funding Rate Mean Reversion

**Quelle:** Google Docs (Deep Research Prompt 2)
**Datum:** 2026-05-04

## Executive Summary

Detaillierte quantitative Analyse der Funding-Rate-Mikrostruktur, Statistik-Kritik und architektonische Empfehlungen.

## Key Findings (über Dokument 1 hinaus)

### 1. Funding Rate Math — Struktureller Positiv-Bias
- Basisrate 0.01%/8h = 10.95% annualisiert → Funding ist **85% der Zeit positiv** bei BTC
- Z-Score um 0 ist NICHT neutral — "neutral" ist z ≈ +1.0 (wegen Basisrate)
- Das macht Short bei z>0.5 zum Garantieverlust: man shortet bei "normal positivem" Funding

### 2. Short-Seite ist FUNDAMENTAL GESCHEITERT
- z>0.5 Short = "fundamentales Missverständnis der Krypto-Mikrostruktur"
- Short braucht **z>3.0 + OI-Divergenz** (extreme overcrowding), nicht mild positiv
- Liquidation mechanics sind asymmetrisch: Long-Squeezes sind kurz und violent, Short-Squeezes sind lang und sustained
- **Phase 1 (z>0.5 Short) muss komplett überdacht werden**
- Falls Short überhaupt: z>3.0 als extreme overcrowding-Bedingung

### 3. 4h ist der mathematische Sweet Spot
- 4h-Kerzen = 2 Updates pro 8h Funding-Epoch (aligned)
- 1h = 8 Updates/Epoch (misaligned, rauscht)
- Das gibt BTC 4h WidePullback R=67 eine theoretische Grundlage
- 4h reduziert nicht nur Rauschen — es ist **strukturell kompatibel** mit dem Funding-Mechanismus

### 4. SOL Edge — Mechanische Erklärung
- SOL: 80% realisierte Volatilität (2x BTC)
- Delta-neutrale Arbs können nicht einsteigen: Margin-Requirements zu hoch, Liquidations-Risiko
- Retail shortet premature → persistent negative funding → Short Squeeze
- **Edge ist real aber decayend** (ETF, Institutionelles werden kommen)

### 5. Statistik-Kritik — WF-Validierung nicht robust genug
- 24 Trades/Window < 30 (Minimum für CLT, t-Tests, Konfidenzintervalle)
- 7/10 windows profitable = P-Wert nicht signifikant genug
- Braucht: **Monte Carlo Bootstrap** + **Bonferroni-Korrektur** für Multiple Testing
- Empfehlung: Mindestens 30 Trades/Window, idealerweise 50+

### 6. DXY als Regime-Filter
- DXY-BTC Korrelation: -0.72 (2024)
- DXY 2%+ Rückgang → 94% BTC-Win-Rate über 90 Tage
- DXY 10-Tage Rate-of-Change < 0 als Long-Filter
- **Starke Macro-Signal-Grundlage**

### 7. FGI als Confluence-Filter
- Extreme Fear (FGI < 20) korreliert mit Kapitulation → aligniert mit negativem Funding
- FGI < 40 als Long-Filter für SOL-Signal
- **NIEMALS als alleiniger Entry** — "sentiment can remain irrational longer than you can remain solvent"

### 8. Portfolio-Konstruktion
- 2-4 unkorrelierte Signale nötig
- Cross-sectional stat-arb (relatives Funding) skaliert besser als directional
- Min order size + Fee drag sind Hauptprobleme bei 500€
- Sharpe ~1-2 ist realistisch für crypto quant

## Actionable Changes für unseren Plan

| Item | Alt | Neu | Grund |
|------|-----|-----|-------|
| Phase 1 Short | z>0.5 → Short | **z>3.0 + OI-Divergenz** oder komplett streichen | Mild positiv = strukturell normal |
| Phase 2 4h | nice-to-have | **Priorität 1** | 2 Updates/Epoch = aligned |
| WF-Statistik | R≥70, 10 Windows | **+Monte Carlo, +Bonferroni** | 24 trades/window nicht robust genug |
| DXY | nicht im Plan | **Regime-Filter** | -0.72 Korrelation, 94% Win-Rate |
| FGI | Entry-Signal | **Confluence-Filter (FGI<40 für Longs)** | Nie als alleiniger Entry |
| Cross-Sectional | nicht im Plan | **Neue Phase: relatives Funding** | Rho Labs = belegte Alpha |