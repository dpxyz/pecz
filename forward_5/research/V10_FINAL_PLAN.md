# V10 FINAL PLAN — Pecz Version (2026-04-30)

**Status:** APPROVED
**Prinzip:** Testen, entscheiden, handeln. OOS vor Foundry. Weniger = robuster.

---

## Warum dieser Plan anders ist

- 6 Features, nicht 36 (Overfitting-Vermeidung)
- 3 Arme, nicht 6 (fokussiert, nicht diffus)
- ~100 Seeds, nicht 1000 (Qualität > Quantität)
- OOS-Test VOR Foundry-Build (nicht danach)
- V2 Module NACH Fundament (A/B-Test ob sie helfen oder killen)
- Kill-Kriterien pro Phase (ehrliches Go/No-Go)

---

## PHASE 0: V1 STOPPEN + OOS-ISOLATION (Tag 1)

1. Paper Engine V1 Kill-Switch (MACD Momentum = 0 Alpha, weiterlaufen lassen ist Verschwendung)
2. Feb-Apr 2026 als TRUE OOS separieren — diese Daten sind HEILIG
3. Alle Muster-Entwicklungen nur auf Nov 2023 → Jan 2026
4. Dauer: 1 Stunde

**Kill-Kriterium:** Keins — V1 stoppen ist frei.

---

## PHASE 1: 6 FEATURES + OOS-VALIDIERUNG (Tag 1-3)

### 6 Features bauen

1. **`funding_z`** — 30d rollierender Z-Score der HL Funding Rate
2. **`regime_score`** — V2 Design (ADX 45% + ATR 25% + Slope 30%), ABER mit Funding-Regime als 4. Komponente (Start 0%, zu validieren)
3. **`squeeze`** — 4h Return < -2% AND funding_z > 1.5
4. **`fund_shift`** — 7d Funding-Mean kreuzt Null
5. **`hour_filter`** — UTC Stunde (Asset-spezifisch: BTC 08:00, SOL 04:00, AVAX 12:00)
6. **`vol_ratio`** — Volume / 24h-MA (als Bestätigung, nicht Entry)

### OOS-Validierung der 5 bewiesenen Signale

Teste auf Feb-Apr 2026 (TRUE unseen):

1. BTC Long P10 (funding_z < P10) — erwartet: +1.42%/trade
2. SOL Long (funding_z < -2) — erwartet: +0.36%/trade
3. AVAX Long (funding_z < -1) — erwartet: +0.69%/trade
4. ETH Squeeze (4h Drop > 2% + high funding) — erwartet: +0.75%/trade
5. ETH 7d Fund→Pos Shift — erwartet: +0.85%/trade

### Kill-Kriterium
> Wenn KEINES der 5 Signale im OOS positiv ist → Funding hat keinen echten Edge auf HL. **Projekt beenden.**

### Dauer
- Tag 1: Features 1-3 + OOS-Test Setup
- Tag 2: Features 4-6 + OOS-Validierung der 5 Signale
- Tag 3: A/B-Test: Welche Signale überleben? Report.

---

## PHASE 2: FOUNDRY V10 (Tag 4-6)

### 3 Arme

1. **FUNDING-LONG** — Entry = funding_z < Schwelle. Asset: BTC, SOL, AVAX, DOGE
2. **FUNDING-SHORT** — Entry = funding_z > Schwelle. Asset: ADA, SOL (z>3σ)
3. **SQUEEZE** — Entry = squeeze=True. Asset: ETH, BTC, SOL

### Konfiguration
- ~100 Seeds pro Run (nicht 1000)
- 10-Fenster Walk-Forward Gate (bestehend)
- Fitness: Net/Trade × Window-Konsistenz
- DeepSeek-v4-pro, reasoning_effort=high
- 5 Runs (nicht mehr — wenn nach 5 Runs nichts kommt, kommt nichts)

### Kill-Kriterium
> Nach 5 Runs — wenn 0 Strategien ≥5/10 Fenster positiv → 6 Features reichen nicht. **Fallback: 5 manuelle Signale als Paper Engine V2 deployen (ohne Foundry). Keine neuen Features addieren.**

### Dauer
- Tag 4: Foundry Setup + Run 1-2
- Tag 5: Run 3-4, Autopsie
- Tag 6: Run 5, Final Selection, Champion-Dossier

---

## PHASE 3: HÄRTUNG + V2 MODUL-ENTScheidUNG (Tag 7-8)

### Härtung der Top-Strategien
1. OOS-Test auf Feb-Apr 2026 (wirklich unseen)
2. Regime-Split: funktioniert in Bären- UND Bullenphasen?
3. Kosten: 0.04% round-trip Maker + 0.06% Slippage
4. SL: Regime-basiert (3% Weak, 5% Strong)

### V2 Modul A/B-Tests
5. **Regime-Score:** Backtest MIT vs OHNE — hilft er oder killt er den Edge?
6. **Korrelations-Filter:** Prüfen ob er Cross-Asset-Trades blockt (BTC+ALT low = unsere besten!)
7. **Sniper-Entry-Stack:** Funding statt MACD, aber: ist 5x Hebel auf schwachem Edge vertretbar?

### V2 Module Decision Matrix
| Modul | Einbauen? | Begründung |
|-------|-----------|------------|
| Regime Detection | NACH A/B-Test | Wenn Edge verbessert → ja, sonst nein |
| Sentiment = Funding | JA | Ist unser Entry, Kill ≤15 übernehmen |
| Risk Management | JA | DD-Scaling + Global Equity Stop aus V1 |
| Asset Selection | JA | Long/Short pro Asset = Teil des Signals |
| Sniper | NACH Champion | Braucht >60% Win, Funding statt MACD |

### Kill-Kriterium
> Net/Trade < 0.05% nach Kosten → keine Paper Engine.

### Dauer
- Tag 7: OOS + Regime + Kosten
- Tag 8: V2 Modul-Entscheidungen, finaler Stack

---

## PHASE 4: PAPER ENGINE V2 (Tag 9-11)

### Was V1-Infrastruktur bleibt
- Accounting (trades.jsonl, state.db, equity_history)
- Discord-Reports (#foundry-reports, #system)
- HL API-Verbindung (REST Polling 60s)
- Command-Listener (!kill, !resume, !status)
- DD-Scaling + Global Equity Stop

### Was NEU reinkommt
- Funding-Feed (Data Collector läuft schon stündlich)
- Signal-Generator: funding_z + regime_score + squeeze → Long/Short/Flat
- Asset-spezifische Richtung (BTC/SOL/AVAX/DOGE=Long, ADA=Short)
- Regime-basierter SL (3% Weak, 5% Strong)
- Decision Logging (warum kein Trade? SKIP-Events)
- Sentiment Kill ≤15 (extreme Funding → kein Entry)

### Was SPÄTER kommt (nicht in V2-Start)
- Sniper (braucht Champion)
- Kinetischer Trail (Stufe 2)
- Vol-Parität (bei 100€ irrelevant)
- Korrelations-Filter (falls A/B zeigt dass er killt)

### Dauer
- Tag 9: Signal-Generator + Funding-Feed
- Tag 10: V2 Engine Integration, Accounting, Discord
- Tag 11: 24h Trockentest mit Live-Daten

---

## PHASE 5: LIVE-PAPER-TEST (Tag 12-25)

### 14 Tage parallel... aber wozu? V1 hat 0 Alpha.
→ V1 ist tot. V2 läuft ALLEIN. Es gibt keinen Vergleich weil V1 nichts zum Vergleichen hat.

### Monitoring
- Täglich: Equity, Trades, Funding-Regime, Feature-Usage
- Wöchentlich: OOS vs Backtest-Vergleich
- Bei DD > 10%: Stop + Autopsie

### Kill-Kriterium (ultimativ)
> DD > 15% in 14 Tagen ODER Edge verschwindet (Net/Trade < 0 nach Kosten) → V2 stoppen, Autopsie.

---

## KILL-KRITERIEN ZUSAMMENFASSUNG

| Phase | Kill | Konsequenz |
|-------|------|------------|
| 1 | 0/5 Signale OOS positiv | **Projekt beenden** |
| 2 | 0 Strategien ≥5/10 Fenster nach 5 Runs | Manuelle Signale als V2 |
| 3 | Net/Trade < 0.05% nach Kosten | Kein Deployment |
| 4 | >3 Trades Slippage >0.2% in 48h | Execution fixen |
| 5 | DD > 15% oder Edge verschwindet | V2 stoppen |

## WAS WIR NICHT TUN

- ❌ 36 Features (Overfitting)
- ❌ 1000 Seeds (verschwendet)
- ❌ V2 Module blind übernehmen (A/B-Test erst)
- ❌ Sniper vor Champion
- ❌ Korrelations-Filter der Cross-Asset-Trades blockt
- ❌ MACD als Entry (0 Alpha)
- ❌ Binance-Daten für HL-Trading

## WAS WIR TUN

- ✅ OOS vor Foundry (erst validieren, dann bauen)
- ✅ 6 Features, 3 Arme, ~100 Seeds
- ✅ Asset-spezifisch (ADA=Short, Rest=Long)
- ✅ V2 Risk Management (DD-Scaling, Global Equity Stop)
- ✅ V2 Sentiment Kill (Funding-basiert)
- ✅ Decision Logging
- ✅ V1 stoppen (0 Alpha = 0 Grund weiterzumachen)