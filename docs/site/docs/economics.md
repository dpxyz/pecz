---
title: Economics
---

# 💰 Phase 8.3: Economics

> Stand: 2026-04-19 — Backtest-basierte Projektion, wird durch Paper Trading validiert.

---

## Cost Structure

| Position | Monthly (€) | Notes |
|----------|-------------|-------|
| VPS Hostinger | 10 | Current |
| API/Data | 30 | Datenfeeds, Monitoring, etc. |
| **Total Fix** | **40** | Dave-confirmed |

## Revenue Model

### Leverage Tiers (ADR-007)

| Tier | Hebel | Assets | DD Range | Return (2024) |
|------|-------|--------|----------|---------------|
| 1 | 1.8x | BTC, ETH | 18.3-18.5% | +40% |
| 2 | 1.5x | SOL, LINK, ADA | 17.9-19.9% | +54-131% |
| 3 | 1.0x | AVAX | 18.3% | +62% |

### Portfolio Economics (100€/Asset)

| Metric | Value |
|--------|-------|
| Startkapital | 600€ (100€ × 6) |
| Deployed Capital | 910€ (mit Hebel) |
| Brutto/Monat | 37.4€ |
| Fixkosten/Monat | 40€ |
| **Netto/Monat** | **-2.6€** ❌ |
| Break-even | 107€/Asset = 641€ Gesamt |

### Break-Even bei verschiedenen Startkapitalien

| €/Asset | Gesamt | Deployed | Netto/Mo | |
|---------|--------|----------|----------|---|
| 100€ | 600€ | 910€ | -2.6€ | ❌ |
| 150€ | 900€ | 1.365€ | +16.2€ | ✅ |
| 200€ | 1.200€ | 1.820€ | +34.9€ | ✅ |

**Entscheidung:** Paper Trading mit 100€/Asset. Economics-Validierung nach echten Daten.

## Fee Structure

| Komponente | Entry | Exit | Total |
|------------|-------|------|-------|
| Maker Fee | 0.01% | 0.01% | 0.02% |
| Slippage | 1bp | 1bp | 2bp |
| **Round-trip** | | | **0.04%** |

## Strategic Review: Trailing Stop (CLOSE vs LOW)

| Check | Return (BTC 2024) | Pass Rate |
|-------|-------------------|-----------|
| CLOSE (Backtest) | +22% | 75% |
| LOW (Worst-Case) | -47% | 12% |
| Paper Trading | TBD | TBD |

Paper Engine nutzt **Echtzeit-WebSocket-Preise** → realistischster Test.
Wenn Paper deutlich unter Backtest → Trailing von 2% auf 3.5% erhöhen.

## Decision Matrix

| Paper Result | Action |
|-------------|--------|
| Netto > 0€/Mo | → Phase 9, 150€+ Startkapital prüfen |
| Netto ≈ -3€/Mo | → Alpha Stack V2 (Ranking, Sizing) oder mehr Kapital |
| Netto << -3€/Mo | → Strategy überdenken, Trailing anpassen |

---

*Wird aktualisiert nach Paper Trading (≥30 Tage, ≥30 Trades).*