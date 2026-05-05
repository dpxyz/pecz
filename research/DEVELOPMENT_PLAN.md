# Entwicklungsplan — G2→G3 Transition (2026-05-05)

## Ziel: 90-Day Track Record profitabel (G3), Edge Decay erkennen, Drift vermeiden

### 🟢 Läuft (Autonom)
- V2 Paper Engine: 5 Signale + DXY/FGI Filter + HL 1h Funding
- Monitor: Dashboard, hourly watchdog, 4h updates
- 90-Day Clock: Tag 1, Start 2026-05-05 12:54

---

## Sprint 1: Statistische Robustheit (Diese Woche, W9)

### 1.1 t-Stat berechnen & Edge Registry ergänzen
- **Problem:** DR fordert t>3.0 (Harvey), nie formal geprüft
- **Lösung:** t-Stat = Sharpe × √(N_trades) für alle 5 Signale berechnen
- **Deliverable:** Edge Registry Einträge mit t-stat, DSR, MC p-value
- **Aufwand:** 1h

### 1.2 Edge Decay Monitoring aufsetzen
- **Problem:** SOL Funding -20pp Decay erkannt, kein Monitoring
- **Lösung:**
  - Cron-Job (daily): Funding-Verteilung pro Asset tracken (neg%, mild-neg%, mean, std)
  - Threshold: >10pp Shift → Discord Alert
  - Historical baseline: Letzte 30d als Referenz
- **Deliverable:** `executor/edge_decay_monitor.py` + daily cron
- **Aufwand:** 2h

### 1.3 Trade-Count pro CPCV-Window prüfen
- **Problem:** SOL Champion hat 24 Trades/Window, CLT-Minimum = 30
- **Lösung:**
  - Mit HL 1h Funding → feinere Z-Score-Auflösung → mehr Signal-Feuerungen
  - Berechnen: Wie viele Trades entstehen mit 1h-Funding statt 8h?
  - Falls immer noch <30: Window vergrößern oder Signale kombinieren
- **Deliverable:** Analyse + Empfehlung
- **Aufwand:** 2h

---

## Sprint 2: Proaktive Optimierung (Nächste Woche, W10)

### 2.1 HL 1h Z-Score Kalibrierung
- **Problem:** HL 1h z-Scores haben andere Distribution als Binance 8h
- **Lösung:**
  - Sweep: 1h-Funding-Z-Thresholds auf 2yr Daten → optimale Einträge finden
  - Vergleich: 8h-Thresholds vs 1h-Thresholds → bessere Sharpe?
  - Falls 1h besser: Engine auf funding_z_1h umschalten
- **Deliverable:** Kalibrierungs-Report, Engine-Update falls besser
- **Aufwand:** 4h

### 2.2 4h Candle Alignment
- **Problem:** DR sagt "4h ist der mathematische Sweet Spot" (2 Updates/Epoch)
- **Lösung:**
  - Engine auf 4h-Candles umstellen (aktuell 1h)
  - Funding-Update alle 8h aligned mit 4h-Candle-Close
  - Weniger Noise, mehr Signal-Qualität
- **Deliverable:** 4h-Engine-Modus + Backtest-Vergleich
- **Aufwand:** 4h

### 2.3 Cross-Sectional Z-Score Validierung
- **Problem:** Signal #3 (BTC crosssec z<-1) nur auf IS-Daten validiert
- **Lösung:**
  - CPCV-Validierung auf 2yr HL-Daten
  - PBO und OOS-Mean berechnen
  - Falls PBO>0.5: Threshold anpassen oder Signal schwächen
- **Deliverable:** CPCV-Result-JSON für crosssec
- **Aufwand:** 3h

---

## Sprint 3: Foundry & Neue Signale (W11-12)

### 3.1 Foundry V13 Cron (1x/Woche)
- **Lösung:** Cron-Job, der wöchentlich neue Hypothesen generiert
- **Hypothesen-First:** LLM generiert Logik (JSON-DSL), Sweep macht Parameter
- **BH-FDR:** Multiple-Testing-Korrektur automatisch
- **Deliverable:** Cron-Job + Discord-Report
- **Aufwand:** 1h Setup

### 3.2 Short-Seite z>3.0 Sweep
- **Problem:** DR sagt z>0.5 = tot, z>3.0 könnte funktionieren
- **Lösung:** Sweep auf 2yr Daten: z>3.0 + OI-Divergenz als Short-Trigger
- **Erwartung:** Sehr wenige Trades, aber unkorreliert
- **Deliverable:** Sweep-Result-JSON
- **Aufwand:** 2h (läuft als Batch)

### 3.3 Post-Liquidation Mean Reversion
- **Problem:** DR Track 1 = vielversprechend aber nicht implementiert
- **Lösung:** Liquidation-Proxy (ΔOI>3σ + Price Wick + Taker Spike) als Signal
- **Deliverable:** Hypothese + Sweep-Skript
- **Aufwand:** 3h

---

## Sprint 4: Infra & Migration (W13-16, parallel zum Track Record)

### 4.1 HyperLiquid Migration Plan
- **Problem:** Binance Testnet ≠ echte Conditions
- **Lösung:**
  - Paper Engine bleibt auf Binance Testnet für Track Record
  - Parallel: HL Live-Feed als Cross-Check
  - Nach G3: Migration auf HL Live (bessere Fees, 1h Funding)
- **Deliverable:** Migrations-Plan (ADR-011)
- **Aufwand:** 2h Planung

### 4.2 WebSocket Execution (Vorbereitung)
- **Problem:** REST Polling = 60s Latenz, DR fordert WS
- **Lösung:**
  - V2 Paper Engine bleibt REST (Track Record-Konsistenz)
  - V3 Architecture: WS-basiert, HL-first
  - Nach Track Record: WS-Modus implementieren
- **Deliverable:** Architecture Design
- **Aufwand:** 4h (Design, nicht Implementierung)

### 4.3 Quarterly Re-Sweep
- **Problem:** Edge Decay kann unbemerkt eintreten
- **Lösung:** Quartalsweiser Re-Sweep der kalibrierten Signale auf letzten 6 Monaten
- **Trigger:** Automatisch, wenn Neg% Shift > 10pp
- **Deliverable:** Re-Sweep Cron + Alert-Mechanismus
- **Aufwand:** 3h

---

## Prioritäten (Diese Woche)

| Prio | Task | Aufwand | Status |
|------|------|---------|--------|
| P0 | Edge Decay Monitor + Cron | 2h | ⬜ |
| P0 | t-Stat für Edge Registry | 1h | ⬜ |
| P1 | Trade-Count pro Window Analyse | 2h | ⬜ |
| P1 | Foundry V13 Cron Setup | 1h | ⬜ |
| P2 | HL 1h Kalibrierung | 4h | ⬜ |
| P2 | 4h Alignment | 4h | ⬜ |

---

## KPIs für G3 (90d Track Record)

| KPI | Target | Current |
|-----|--------|---------|
| Total PnL | >0€ (profitabel) | 0€ (Day 1) |
| Max Drawdown | <25% | 0% |
| Win Rate | >45% | N/A |
| Sharpe (annualized) | >1.0 | N/A |
| SOL neg% Decay | <10pp shift | -20pp ⚠️ |
| Trade Count | >30/Window | ~24 ⚠️ |
| Signals active | 5 | 5 ✅ |