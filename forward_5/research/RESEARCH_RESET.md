# Research Reset — Edge Discovery in Crypto

## Status: REDIRECT
**Datum:** 2026-05-02  
**Autor:** Pecz + Dave  
**Auslöser:** V10/V11 Foundry zeigt: Funding-Mean-Reversion ist regime-abhängig, dünn, und nicht profitabel im aktuellen Bull-Markt. 150+ Strategien getestet, kein robuster Edge.

---

## 1. Was wir bewiesen haben

| Erkenntnis | Beweis | Konsequenz |
|-----------|--------|------------|
| Standard-Indikatoren = 0 Alpha | 150+ Tests, 0 Gate-passed | Nie wieder MACD/RSI/BB/EMA-Kreuzungen |
| Funding Rate hat konträren Edge | V10: 5/6 Assets OOS-positiv, V11: SOL 6/6 WF | Edge ist REAL aber regime-abhängig |
| Bear-only Signale feuern nicht in Bullen | AVAX/DOGE: 0 Trades in 4/6 WF-Windows | Bull-Market = keine Trades = keine Validierung |
| 1h Zeitrahmen ist limitiert | Alle Tests auf 1h, nie 4h/daily untersucht | Andere Zeitrahmen ungetestet |
| Long-only Mean Reversion ist einseitig | 100% der getesteten Strategien | Short, Momentum, Trendfolge = blind spot |

## 2. Was wir NICHT wissen (Research Questions)

### RQ1: Hat Funding einen prozyklischen Edge?
- **Hypothese:** Positive Funding → Trend geht weiter (nicht reversion, sondern continuation)
- **Warum ungetestet:** Wir haben nur z<-1 (negative Funding = Long) getestet
- **Test:** z>+1 → Short (Short Momentum)? Oder z>+1 → Long (Trend Continuation)?

### RQ2: Funktioniert Momentum in Crypto?
- **Hypothese:** Breakouts und Trendfolge sind profitabler als Mean Reversion
- **Warum ungetestet:** V1-V11 waren 100% Mean Reversion
- **Test:** EMA-Crossover mit Funding-Bestätigung? Breakout + Volume?

### RQ3: Ist 4h/daily besser als 1h?
- **Hypothese:** Höhere Zeitrahmen filtern Rauschen, Funding 8h zyklisch = natürlicher Fit für 4h+
- **Warum ungetestet:** Alle Daten und Backtests auf 1h
- **Test:** 4h-Candles mit 8h-Funding Alignment

### RQ4: Was machen profitable Crypto-Trader?
- **Hypothese:** Der Edge liegt nicht in Indikatoren, sondern in Informationsasymmetrie
- **Quellen:** Hyperliquid leaderboard, Whale-Tracking, Liquidation-Cascaden
- **Test:** Open Interest Spikes als Signal? Liquidation-Clustering?

### RQ5: Gibt es Short-Edge?
- **Hypothese:** In Bullen profitabel short sein = Anti-Fragile Strategie
- **Warum ungetestet:** SOL Short war -21%, aber das war ein schlechtes Signal, nicht Short generell
- **Test:** z>+2 → Short in Bullen (overcrowded longs)?

## 3. Systematischer Ansatz

### Phase 1: Daten erweitern (1-2 Tage)
- [ ] 4h-Candles aus 1h-Daten aggregieren
- [ ] Funding Rate als Feature (nicht nur z-Score): raw rate, 8h change, extreme events
- [ ] Open Interest als Signal (OI Spikes, OI-Price Divergence)
- [ ] Liquidation-Daten (Hyperliquid API)
- [ ] Volume Profile (relative Volume Spikes)

### Phase 2: Hypothesen-basierte Tests (3-5 Tage)
Jede Research Question wird EINE klare Hypothese → EIN Backtest → EIN WF-Gate.

Format:
```
Hypothese: "Positive Funding z>+1.5 → Short in Bullen hat Edge"
Test: SOL/BTC/ETH, 1h, z>1.5 → Short, 24h hold
Gate: ≥4/6 OOS windows profitable, cum PnL > 0
```

Nicht raten. Nicht 16 Varianten gleichzeitig. Eine Hypothese, ein Test, ein klares Ja/Nein.

### Phase 3: Validierung (nach Phase 2)
- Top 1-2 Strategien ins Paper Trading
- Evaluation nach 10+ Trades, nicht nach 14 Tagen
- Live vs Backtest Divergence messen

## 4. Was wir STOPPEN

- ❌ Weitere Foundry-Iterationen auf 1h Mean Reversion
- ❌ Filter-Kombinationen auf demselben Signal (FGI+DXY+z<-1 = Overfitting)
- ❌ 14-Tage-Counter für Paper Trading
- ❌ "Noch ein Threshold-Test" (z<-1.3, z<-1.7, etc.)

## 5. Was wir STARTEN

- ✅ Neue Hypothesen formulieren (RQ1-RQ5)
- ✅ Daten erweitern (4h, OI, Liquidations, Volume)
- ✅ EIN Test pro Hypothese, kein Scattergun
- ✅ Ehrliche Evaluation: kein Edge = kein Trade

## 6. Meta-Frage

> **Ist systematisches Trading mit öffentlichen Daten auf 1h-Crypto überhaupt profitabel?**

Wenn die Antwort nach Phase 2 "nein" ist, ist das auch OK. Besser ehrlich als 6 Monate optimieren.

---

*Dieses Dokument ersetzt die Foundry V1-V11 Ergebnisliste als Arbeitsgrundlage.*