---
title: Economics
---

# 💰 Phase 8.3: Economics

> Stand: 2026-04-20 — Paper Trading läuft. Zahlen werden nach 30+ Tagen mit echten Daten validiert.

---

## Cost Structure

| Position | Monthly (€) | Notes |
|----------|-------------|-------|
| VPS Hostinger | 10 | Current |
| API/Data | 30 | Datenfeeds, Monitoring |
| **Total Fix** | **40** | Dave-confirmed |

## Current Setup: 100€ TOTAL

⚠️ **100€ ist das GESAMT-Kapital**, nicht per Asset. Bei 6 Assets: ~16.67€/Asset.

| Asset | Leverage | Allocation | Deployed |
|-------|----------|------------|----------|
| BTC | 1.8x | 16.67€ | 30.01€ |
| ETH | 1.8x | 16.67€ | 30.01€ |
| SOL | 1.5x | 16.67€ | 25.01€ |
| AVAX | 1.0x | 16.67€ | 16.67€ |
| DOGE | 1.5x | 16.67€ | 25.01€ |
| ADA | 1.5x | 16.67€ | 25.01€ |
| **Total** | | **100€** | **~152€** |

### Break-Even bei verschiedenen Startkapitalien

| Total Capital | Netto/Mo | |
|--------------|----------|---|
| 100€ | TBD (Paper Trading) | 🔵 Testing |
| 600€ | +37€/mo | ✅ (6× 100€/Asset) |
| 900€ | +16€/mo | ✅ |

**Entscheidung:** Paper Trading mit 100€ TOTAL. Break-even wird nach echten Daten berechnet.

## Fee Structure

| Komponente | Entry | Exit | Total |
|------------|-------|------|-------|
| Maker Fee | 0.01% | 0.01% | 0.02% |
| Slippage | 1bp | 1bp | 2bp |
| **Round-trip** | | | **0.04%** |

## Decision Matrix

| Paper Result | Action |
|-------------|--------|
| Strategie profitabel | → Phase 9, Kapitalerhöhung prüfen |
| Break-even ±3€/Mo | → V2 Alpha Stack (Regime + Vol-Parity) |
| Deutlicher Verlust | → Strategy überdenken |

---

*Wird aktualisiert nach Paper Trading (≥30 Tage, ≥30 Trades).*