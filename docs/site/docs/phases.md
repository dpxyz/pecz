---
title: Phases
---

# Phasen 0–10

> Jede Phase muss vollständig und dokumentiert sein bevor die nächste beginnt.

---

## Status

| Phase | Name | Status | Ergebnis |
|-------|------|--------|----------|
| 0–6 | Foundation | ✅ COMPLETE | Grundstruktur bis Test Strategy |
| 7 | Strategy Lab | ✅ COMPLETE | Gold Standard: MACD+ADX+EMA |
| **8** | **Paper Trading + Economics** | **⭐ LIVE** | **Engine läuft seit 2026-04-20** |
| 9 | Final Gate | ⬜ PENDING | Go/No-Go für Live Trading |
| 10 | V2 Strategy | ⬜ PLANNED | Regime + Volatility-Parity + Sentiment |

---

## Timeline

```
2026-03-06  Phase 0 COMPLETE
2026-03-08  Phase 2 COMPLETE (103 Tests)
2026-03-27  Phase 3 COMPLETE (Observability)
2026-04-01  Phase 5 COMPLETE (Operations)
2026-04-05  Phase 6 COMPLETE (24h Test PASSED)
2026-04-05  Phase 7 COMPLETE (Strategy Lab validated)
2026-04-19  Phase 8 START (Executor V1 built + Audited)
2026-04-20  Phase 8 LIVE (Paper Trading started on Testnet)
```

---

## Phase 8: Paper Trading — LIVE 🟢

**Gestartet:** 2026-04-20 | **Capital:** 100€ TOTAL | **Assets:** 6 | **Mode:** PAPER ONLY

### Was wurde gemacht
- Executor V1: 7 Module, Integrationstest (376 Trades)
- Full Pipeline Audit: 12 Bugs gefunden & gefixt
- Hyperliquid Testnet: API Wallet autorisiert, $999 Balance
- Discord Commands: !kill, !resume, !status, !help
- Components v2 Embeds für Reports
- Capital Model: 100€ Total, Equal-Weight per Asset

### Success Criteria (ADR-006, Updated)

**Phase 1 — Paper Trading (14 Tage):**
- ≥10 Trades
- ≤25% Drawdown
- Accounting-Invariante ✅
- ≥95% Signal Execution Rate
- ≥14 Tage Laufzeit

**Phase 2 — Testnet API (14 Tage):**
- ≥5 Orders platziert auf Testnet
- 0% API-Fehler (unhandled)
- Position sichtbar auf app.hyperliquid-testnet.xyz
- Kill-Switch schließt Position via API
- ≥14 Tage Laufzeit

**Gate:** Phase 2 nur starten wenn Phase 1 bestanden.

### Noch offen
- Monitor V1 (Equity-Kurve, Dashboard, Daily Report)
- 14 Tage Paper Trading (läuft seit 2026-04-20)
- Economics Validierung (nach 14 Tagen)
- Order Executor Module (Phase 2)

---

## Phase 9: Final Gate ⬜

Go/No-Go Entscheidung. Kriterien:
1. Paper Trading Success Criteria erfüllt
2. Economics positiv (oder klarer Pfad dorthin)
3. Manuelle Freigabe durch Dave

---

## Phase 10: V2 Strategy ⬜

**Voraussetzung:** Phase 9 bestanden. Kein V2 ohne bewiesene V1-Pipeline.

### V2 Design Principles
- **Regime-Erkennung als Herzstück** — Trend/Range/Crash → nicht in Range handeln
- **Volatility-Parity** — Risiko pro Trade konstant, nicht Kapital
- **Sentiment als Kill-Switch** — Score 0-100, JSON-Mode, nur downsizing
- **On-Chain Regime-Filter** — Exchange Netflow 7-14d
- **Kein Indikatoren-Salat** — bessere Regeln, nicht mehr Indikatoren