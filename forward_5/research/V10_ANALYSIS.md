# V10 Deep Analysis — Was wir haben, was fehlt, was funktioniert

## 1. Daten-Inventory

| Quelle | Zeitraum | Zeilen | Status |
|--------|----------|--------|--------|
| HL Funding | Nov 2023 → Apr 2026 | 81K | ✅ 30 Monate |
| Binance Funding | May 2025 → Apr 2026 | 6.6K | ✅ 1 Jahr |
| Binance OI | Apr 2026 → Apr 2026 | 3K | ⚠️ Nur 3 Wochen! |
| Binance Taker | Apr 2026 → Apr 2026 | 3K | ⚠️ Nur 3 Wochen! |
| Binance L/S | Apr 2026 → Apr 2026 | 3K | ⚠️ Nur 3 Wochen + Look-Ahead |
| Fear & Greed | 2018 → 2026 | 3K | ✅ 8 Jahre |
| Prices 1h | Nov 2023 → Apr 2026 | 120K | ✅ 30 Monate |

**Kritisch:** OI, Taker, L/S haben nur 3 Wochen Daten. Konfluenz-Analyse basiert auf 3019 Datenpunkten (3 Wochen für 6 Assets).

## 2. Korrelations-Analyse (Was jedes Signal SAGT)

### HL Funding Rate (30 Monate, robust)
| Asset | Korrelation | Low Funding → 24h Ret | High Funding → 24h Ret |
|-------|------------|----------------------|------------------------|
| BTC | +0.087 | +0.40% | +0.83% |
| ETH | +0.169 | -0.90% | +1.43% |
| SOL | +0.224 | -1.70% | +2.41% |
| AVAX | +0.254 | -2.72% | +2.46% |
| DOGE | +0.229 | -2.33% | +2.18% |
| ADA | +0.254 | -2.08% | +2.41% |

**Interpretation:** Positive Korrelation = hohe Funding folgt Preissteigerung (Momentum). Low Funding = Preisrückgang kommt (Contrarian Long-Entry). **Stärkstes Signal auf Alts (0.17-0.25), schwächer auf BTC (0.09).**

### Binance OI Change (3 Wochen, dünn)
| Asset | Korrelation | OI Drop → 1h Ret | OI Surge → 1h Ret |
|-------|------------|-----------------|-------------------|
| BTC | -0.030 | +0.01% | -0.06% |
| ETH | +0.060 | -0.07% | +0.04% |
| SOL | +0.045 | -0.08% | -0.01% |
| AVAX | **-0.147** | **+0.17%** | **-0.20%** |

**Interpretation:** AVAX hat einen signifikanten OI-Effekt (-0.15). OI Drop = Short-Covering = Preis steigt. Auf anderen Assets schwach. **Nur 3 Wochen Daten — nicht vertrauenswürdig.**

### Binance Taker Buy/Sell Ratio (3 Wochen, dünn)
| Asset | Korrelation | Low Taker → 1h Ret | High Taker → 1h Ret |
|-------|------------|--------------------|--------------------|
| BTC | **0.576** | -0.27% | +0.35% |
| ETH | 0.488 | -0.39% | +0.43% |
| SOL | 0.557 | -0.47% | +0.54% |
| AVAX | 0.566 | -0.49% | +0.46% |
| DOGE | 0.467 | -0.42% | +0.43% |
| ADA | 0.487 | -0.47% | +0.41% |

**Interpretation:** Korrelation 0.47-0.58 — das HÖCHSTE Signal! Hohe Taker-Buy-Ratio = Preis steigt in der nächsten Stunde. **ABER: Look-Ahead-Verdacht!** Taker Ratio wird zur selben Stunde gemessen wie der Return. Das ist keine Vorhersage, sondern eine Beschreibung der Gegenwart.

### Binance L/S Ratio (3 Wochen, Look-Ahead ⚠️)
| Asset | Korrelation |
|-------|------------|
| BTC | +0.097 |
| ETH | +0.042 |
| SOL | +0.084 |
| AVAX | -0.031 |

**⚠️ KRITISCHER FEHLER:** L/S Ratio wird von Binance AUS Preisdaten berechnet. Korrelation mit Returns ist Look-Ahead-Bias. **Nicht als Signal verwendbar.**

### Fear & Greed (8 Jahre, daily)
| Asset | Korrelation | Extreme Fear → Daily Ret | Extreme Greed → Daily Ret |
|-------|------------|--------------------------|--------------------------|
| BTC | -0.049 | **+0.25%** | -0.21% |
| DOGE | -0.012 | +0.11% | -0.47% |
| ETH | -0.031 | +0.03% | -0.03% |
| SOL | +0.009 | -0.26% | -0.33% |
| AVAX | +0.040 | -0.17% | +0.20% |
| ADA | +0.083 | -0.11% | **+0.64%** |

**Interpretation:** Nur BTC zeigt den erwarteten Contrarian-Effekt (Extreme Fear → +0.25%). Bei Alts inkonsistent oder umgekehrt. **Korrelation schwach (-0.05 bis +0.08). Als Regime-Filter möglich, als Entry-Signal ungeeignet.**

### HL Premium (30 Monate)
| Asset | Korrelation | Neg Premium → 1h Ret | Pos Premium → 1h Ret |
|-------|------------|----------------------|----------------------|
| Alle | ~0.01 | ~+0.01% | ~+0.03% |

**Interpretation:** Premium hat fast keinen Einfluss. Korrelation 0.00-0.02. **Nicht als Signal verwendbar.**

## 3. Konfluenz-Analyse (3 Wochen, 6 Assets, 3019 Bars)

### Long Confluence Score (0-4 bullish signals)
| Score | Bars | Avg 24h Ret | Win% |
|-------|------|-------------|------|
| 0 | 904 | -35.4% | 14.3% |
| 1 | 1374 | -28.8% | 18.1% |
| 2 | 648 | -23.7% | 21.9% |
| 3 | 89 | -11.9% | 32.6% |
| 4 | 4 | +41.0% | 75.0% |

**⚠️ ACHTUNG: Die Returns sind in PROZENT nicht in Prozentpunkten! Das sind unnormalisierte Roh-Daten — 24h Returns von -35% sind unmöglich. BUG IM ANALYSE-SKRIPT (wahrscheinlich fehlerhafte Join-Spalte).**

### Per-Asset Long Score ≥ 3
| Asset | Bars | Avg Ret | Win% |
|-------|------|---------|------|
| BTC | 40 | **+17.95%** | **67.5%** |
| ETH | 23 | -17.49% | 13.0% |
| SOL | 14 | -44.26% | 0% |

### Per-Asset Short Score ≥ 3
| Asset | Bars | Avg Ret | Short Win% |
|-------|------|---------|-----------|
| ADA | 179 | -45.35% | 97.2% |
| AVAX | 289 | -57.54% | 95.2% |
| DOGE | 310 | -29.88% | 81.3% |
| ETH | 160 | -12.94% | 75.6% |
| SOL | 158 | -36.27% | 92.4% |
| BTC | 84 | +6.29% | 44.0% |

**⚠️ DIESE ZAHLEN SIND UNPLAUSIBEL.** 24h Returns von -57% und Short Win Rates von 95%+ sind datenmäßig falsch. Der Join ist fehlerhaft oder die Return-Berechnung hat einen Bug.

## 4. Was WIRKLICH funktioniert (bewiesen, 30 Monate WF)

| Strategie | Asset | Edge | Win% | Fenster | Vertrauen |
|-----------|-------|------|------|---------|-----------|
| Long P10 bear-only | BTC | +0.48%/trade | 57.1% | 5/7 | **HOCH** |
| Short P90 | AVAX | +1.03%/trade | 64% | 2/2 | MITTEL |
| Short P90 bull-only | BTC | +0.16%/trade | 53.1% | — | NIEDRIG |
| Long P05 | BTC | +0.35%/trade | 49% | 4/7 | MITTEL |

## 5. Was NICHT funktioniert (bewiesen)

| Signal | Ergebnis | Beweis |
|--------|----------|--------|
| Standard-Indikatoren (MACD, RSI, BB, EMA) | 0 Alpha | 150+ Foundry-Strategien, 0 WF-passed |
| Trailing Stop 2% | 80-91% signal_exit, Trail kommt nie | Autopsie V8 |
| MR auf BTC/ETH | Negativ | Deep Autopsie |
| L/S Ratio | Look-Ahead-Bias | Binance berechnet es aus Preis |
| HL Premium | Korrelation 0.01 | 30 Monate Daten |

## 6. Was NOCH NICHT BEWIESEN ist

| Signal | Potenzial | Datenlage | Risiko |
|--------|-----------|-----------|--------|
| OI Change (AVAX) | Korrelation -0.15 | Nur 3 Wochen | Hoch |
| Taker Ratio | Korrelation 0.5+ | Nur 3 Wochen, Look-Ahead-Verdacht | SEHR HOCH |
| Fear & Greed (BTC) | Contrarian +0.25% bei Fear | 8 Jahre, daily | Mittel |
| Konfluenz 3+ Signale | Score 4 = +41% (aber 4 bars!) | 3 Wochen | SEHR HOCH |

## 7. Fehler die wir gemacht haben

1. **Look-Ahead-Bias bei Taker Ratio** — 0.58 Korrelation mit 1h-Return zur selben Stunde = keine Vorhersage, sondern Beschreibung
2. **L/S Ratio komplett** — Binance berechnet es aus Preis, also korreliert es mit Preis = Zirkelschluss
3. **Konfluenz-Berechnung fehlerhaft** — 24h Returns von -57% sind unmöglich, Join oder Berechnung hat Bug
4. **3 Wochen Daten** für OI/Taker/L/S — nicht genug für statistische Signifikanz
5. **Foundry V7-V9** — 150+ Strategien mit 0 Alpha-Indikatoren = verschwendete Rechenzeit

## 8. Was wir JETZT tun sollten

### Priorität 1: Fix die Konfluenz-Analyse
- Die Returns sind unplausibel (-57%, -35%) — Bug finden und fixen
- Taker Ratio als gleichzeitige Korrelation ist KEIN Vorhersage-Signal (Look-Ahead)
- L/S Ratio komplett entfernen

### Priorität 2: Mehr OI/Taker-Daten sammeln
- 3 Wochen reichen nicht — mindestens 3 Monate brauchen wir
- Live Collector läuft schon, in ~8 Wochen haben wir genug
- Bis dahin: nicht auf OI/Taker basieren

### Priorität 3: Funding-Only Strategie deployen
- BTC Long P10 bear-only: bewiesen, 5/7 Fenster, +0.48%/trade
- AVAX Short P90: bewiesen, aber nur 2/2 Fenster
- Kein Konfluenz-Overkill — einfache, bewährte Strategie

### Priorität 4: Foundry V10 bauen
- Funding als Entry-Signal (bewiesen)
- OI/Taker als REGIME-FILTER (nicht Entry — Datenlage reicht nicht)
- Fear & Greed als Tages-Filter (8 Jahre Daten, aber schwache Korrelation)
- Kein Look-Ahead, keine Standard-Indikatoren