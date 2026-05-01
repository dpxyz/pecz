# V10 MASTER PLAN — Funding-First Trading System

**Erstellt:** 2026-04-30 (DeepSeek-v4-pro, reasoning_effort=high)
**Ziel:** Paper Engine V2 mit positivem Walk-Forward-Edge in 14 Tagen
**Prinzip:** Keine Hoffnung, nur Beweise. Jede Phase hat ein Kill-Kriterium.

---

## ARCHITEKTUR-ENTSCHEIDUNG

**Foundry V10 = reiner Funding-First Generator.**
- Input: 9 bewiesene Muster als Feature-Familien (keine Standard-Indikatoren)
- Output: Asset-spezifische, regime-abhängige Signal-Bäume
- Validierung: 10-Fenster Walk-Forward Gate (bestehend)
- Budget: 3 Thinking-Modi (DeepSeek-v4-pro) für Evolution

**Warum das funktionieren wird:**
- 30 Monate saubere Funding-Daten OHNE Look-Ahead
- 9 Muster statistisch signifikant über 7 Fenster
- Exchange-Divergenz verstanden (HL = Long-Edge)
- Foundry V9 Mechanik kampferprobt, nur Inputs waren falsch

---

## PHASE 1: FEATURE FACTORY (Tag 1–3)

**Ziel:** Aus 9 Mustern 36 validierte Features bauen, die Foundry fressen kann.

### Features (9 Familien × 4 Features = 36)

1. **Funding Z-Score** — Z über 720h rollierend, Z-Change (1h/4h/24h Delta), Z-Regime (extrem neg/normal/pos)
2. **Funding-Persistenz** — Consecutive hours extreme (1-8h), Streak-Richtung, Streak-Bruch-Indikator
3. **Funding-Regime-Shift** — 7d-Funding neg→pos (ETH-Spezial!), 7d pos→neg, 24h-Flip
4. **Regime × Funding** — 4 Quadranten: Bull+HighFund, Bull+LowFund, Bear+HighFund, Bear+LowFund
5. **Short-Squeeze-Detektor** — 4h Drop>2% AND Fund>P75, 1h Drop>1% AND Fund>P90
6. **Volume + Funding** — 3×3 Matrix (Vol High/Normal/Low × Fund High/Normal/Low)
7. **Uhrzeit** — Stunde 0-23 als One-Hot, Asset-spezifische beste Stunden
8. **Cross-Asset Funding** — BTC+ALT beide Low Flag, BTC Low ALT Normal, Divergenz
9. **Optimale Richtung** — Statische Long/Short-Präferenz pro Asset, SOL Z>3σ Short-Override

### Kill-Kriterium
> Wenn >20% der Features Look-Ahead-Verdacht → Feature Factory neu aufsetzen

### Timeline
- Tag 1: Features 1-4, Look-Ahead-Prüfung
- Tag 2: Features 5-8, Look-Ahead-Prüfung
- Tag 3: Feature 9, alle 36 in Foundry-Format, Qualitätsreport

---

## PHASE 2: FOUNDRY V10 SETUP & BASIS-EVOLUTION (Tag 4–7)

**Ziel:** Foundry V10 füttern, erste Strategie-Generation.

### 6 Arme
1. Long-Only Funding-Extrem (Z-Score)
2. Long-Only Regime+Funding (Matrix)
3. Short-Only Funding-Extrem (ADA, SOL Z>3σ)
4. Long/Short Squeeze (Detektor)
5. Cross-Asset Konfluenz (BTC+ALT)
6. Zeit-Overlays (Uhrzeit-Filter)

### Ablauf
- Tag 4: Seed-Generation (1000 Strategien), Walk-Forward Start
- Tag 5: Walk-Forward abgeschlossen, Autopsie Top-50
- Tag 6: Evolution R1 (Top-50 → 500 neue)
- Tag 7: Evolution R2 (Top-25 → 250 neue), Final Selection Top-10

### Kill-Kriterium
> Keine Strategie ≥4/10 positive Fenster nach 1000 Seeds → zurück zu Phase 1

---

## PHASE 3: STRATEGIE-HÄRTUNG (Tag 8–10)

**Ziel:** Top-10 auf Robustheit prüfen, Overfitting eliminieren.

1. Monte-Carlo-Permutation (1000 Runs)
2. Out-of-Sample-Test: Letzte 3 Monate (Jan-Mar 2026) komplett unseen
3. Regime-Stresstest: Nur Bull / Nur Bear / Nur Sideways / Nur High-Vol
4. Asset-Robustheit: Mindestens 3/6 Assets positiv
5. Kosten-Simulation: 0.1% Slippage + 0.05% Fee

→ Top-3 für Paper Engine V2

### Kill-Kriterium
> Keine Strategie OOS positiv (Net/Trade > 0 nach Kosten) → Phase 2 mit OOS-Gate wiederholen

---

## PHASE 4: PAPER ENGINE V2 INTEGRATION (Tag 11–13)

### Architektur
```
Data Collector (stündlich)
    ↓
Feature Factory (36 Features, Echtzeit)
    ↓
Foundry V10 Signal Generator (Top-3 als Ensemble)
    ↓
Paper Engine V2 (Accounting, Discord-Report)
    ↓
Walk-Forward Gate (wöchentliches Re-Training)
```

1. Signal-Generator: Feature-Vektor → Long/Short/Flat
2. Ensemble-Logik: 3 Strategien, Majority-Vote
3. Position Sizing: 2% Risk, Kelly/4 Obergrenze
4. Accounting: V1-kompatibel
5. Discord-Report: + Funding-Regime, Feature-Usage
6. Monitoring: Feature-Drift-Detektor

### Kill-Kriterium
> >3 Trades mit Slippage >0.2% in 48h → Execution-Modell fixen

---

## PHASE 5: LIVE-PAPER-TEST (Tag 14)

V2 läuft 24h parallel zu V1 → Vergleichsreport → Entscheidung

### Ultimatives Kill-Kriterium
> V2 schlechter als V1 nach 24h → V10 gescheitert, Autopsie

---

## KILL-KRITERIEN ZUSAMMENFASSUNG

| Phase | Kill-Kriterium | Konsequenz |
|-------|----------------|------------|
| 1 | >20% Features Look-Ahead | Feature Factory neu |
| 2 | 0 Strategien ≥4/10 Fenster | Zurück zu Phase 1 |
| 3 | 0 Strategien OOS positiv | Phase 2 mit OOS-Gate |
| 4 | >3 Trades Slippage >0.2% | Execution fixen |
| 5 | V2 < V1 nach 24h | V10 gescheitert |

## WAS WIR NICHT TUN

- ❌ OI/Taker als primäres Signal (3 Wochen = wertlos für WF)
- ❌ Standard-Indikatoren (150+ = 0 Alpha)
- ❌ Manuelle Strategie-Regeln (Foundry soll bauen)
- ❌ Alles auf einmal deployen
- ❌ Binance-Daten für HL-Trading (Divergenz bewiesen)