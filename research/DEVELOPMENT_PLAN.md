# Entwicklungsplan — G2→G3 Transition

**Erstellt:** 2026-05-05
**Ziel:** 90-Day Track Record profitabel (G3), Edge Decay erkennen, Drift vermeiden
**Status:** Day 1 von 90

---

## Sprint 1: Statische Robustheit (W9, diese Woche)

| # | Task | Aufwand | Prio | Status |
|---|------|---------|------|--------|
| 1.1 | t-Stat für Edge Registry (Harvey t>3.0) | 1h | P0 | ✅ ALL PASS (32-79) |
| 1.2 | Edge Decay Monitor + daily Cron | 2h | P0 | ✅ 10:00 Berlin daily |
| 1.3 | Trade-Count pro CPCV-Window | 2h | P1 | ✅ Known limitation |
| 1.4 | Foundry V13 Cron Setup (1x/Woche) | 1h | P1 | ✅ Mondays 09:00 |

**Deliverables:**
- Edge Registry Einträge mit t-stat, DSR, MC p-value
- `executor/edge_decay_monitor.py` + daily cron
- Analyse: HL 1h → mehr Trades pro Window?
- Foundry V13 Cron läuft autonom

---

## Sprint 2: Proaktive Optimierung (W10)

| # | Task | Aufwand | Prio | Status |
|---|------|---------|------|--------|
| 2.1 | HL 1h Z-Score Kalibrierung | 4h | P2 | ⬜ |
| 2.2 | 4h Candle Alignment | 4h | P2 | ⬜ |
| 2.3 | Cross-Sectional CPCV Validierung | 3h | P1 | ⬜ |

**Deliverables:**
- Kalibrierungs-Report: 1h vs 8h Thresholds
- 4h-Engine-Modus + Backtest-Vergleich
- CPCV-Result-JSON für crosssec

---

## Sprint 3: Neue Signale (W11-12)

| # | Task | Aufwand | Prio | Status |
|---|------|---------|------|--------|
| 3.1 | Short-Seite z>3.0 Sweep | 2h | P2 | ⬜ |
| 3.2 | Post-Liquidation Mean Reversion | 3h | P2 | ⬜ |
| 3.3 | Foundry V13 Ergebnisse auswerten | 1h | P1 | ⬜ |

**Deliverables:**
- Sweep-Result-JSON für z>3.0
- Liquidation-Proxy Hypothese + Sweep-Skript
- Neue Hypothesen aus Foundry in Edge Registry

---

## Sprint 4: Infra & Migration (W13-16)

| # | Task | Aufwand | Prio | Status |
|---|------|---------|------|--------|
| 4.1 | HyperLiquid Migration Plan (ADR-011) | 2h | P2 | ⬜ |
| 4.2 | WebSocket Architecture Design | 4h | P3 | ⬜ |
| 4.3 | Quarterly Re-Sweep Cron | 3h | P1 | ⬜ |

**Deliverables:**
- ADR-011: HL Migration Plan
- WS Architecture Design Document
- Re-Sweep Cron + Alert-Mechanismus

---

## KPIs für G3 (90d Track Record)

| KPI | Target | Current | Check |
|-----|--------|---------|-------|
| Total PnL | >0€ | 0€ (Day 1) | Daily |
| Max Drawdown | <25% | 0% | Daily |
| Win Rate | >45% | N/A | Weekly |
| Sharpe (annualized) | >1.0 | N/A | Weekly |
| SOL neg% Decay | <10pp shift | -20pp ⚠️ | Daily |
| Trade Count | >30/Window | ~24 ⚠️ | Sprint 1.3 |
| Signals active | 5 | 5 ✅ | — |
| t-Stat (Harvey) | >3.0 | N/A | Sprint 1.1 |

---

## Drift-Check (Stand 2026-05-05)

| # | DR-Empfehlung | Status | Drift? |
|---|---------------|--------|--------|
| 1 | DSR + MC + CPCV + BH-FDR | ✅ Implementiert | Kein |
| 2 | Korrelations-Check ρ<0.4 | ✅ 5 Signale | Kein |
| 3 | Min 30 Trades/Window | ⚠️ 24 Trades | Drift |
| 4 | t-Stat > 3.0 | ❓ Nicht geprüft | Drift |
| 5 | 3+ unkorrelierte Signale | ✅ 5 Signale | Kein |
| 6 | Short-Seite z>3.0 | ⬜ Offen | Offen |
| 7 | FGI < 40 Confluence | ✅ Als Filter | Kein |
| 8 | DXY Regime-Filter | ✅ Implementiert | Kein |
| 9 | EMA200 Bull-Filter | ✅ Alle Longs | Kein |
| 10 | Cross-Sectional Funding | ✅ Signal #3 | Kein |
| 11 | 4h Funding (HL 1h) | ✅ Pipeline | Kein |
| 12 | Edge Decay Monitoring | ❌ Nicht impl. | Drift |
| 13 | Hyperliquid Migration | ⬜ Offen | Offen |
| 14 | WebSocket Execution | ⬜ Offen | Offen |

**SOL Edge Decay — Frühwarnung:**
- Jan-Feb: 77.2% negativ → Mär-Mai: 56.8% negativ = **-20.4pp**
- Ursache: Ethena, Arbitrage-Kapital, SOL ETF-Erwartung
- Gegenmaßnahme: 5 Signale auf 3 Assets (nicht SOL-only)
- Monitoring: Edge Decay Cron (Sprint 1.2)