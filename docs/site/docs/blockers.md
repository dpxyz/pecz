---
title: Blockers
---

# 🚧 Blockers

> Aktuell keine akuten Blocker! 🎉

---

## ✅ Resolved Blockers

| Blocker | Gelöst | Wie |
|---------|--------|-----|
| Hyperliquid Testnet Wallet | 2026-04-20 | API Wallet autorisiert, $999 Balance |
| Capital Model | 2026-04-20 | 100€ TOTAL (nicht per Asset) |
| LINK nicht auf Testnet | 2026-04-20 | Durch DOGE ersetzt |
| Embed-Formatierung | 2026-04-20 | Components v2 Container mit accentColor |
| WS Subscription Format | 2026-04-20 | Korrektes Format dokumentiert & gefixt |
| Candle Data Format | 2026-04-20 | Flat STRING values, nicht nested |
| Position Sizing Bug | 2026-04-20 | Fee in Size-Formel korrigiert |
| Mainnet/Testnet Mismatch | 2026-04-20 | Backfill von Testnet API statt Parquet |
| Entry Fee in Equity | 2026-04-20 | Fee sofort vom Equity abgezogen |
| Daily Loss Denominator | 2026-04-20 | Aktuelles Equity statt Start-Equity |
| Hardcoded Asset List | 2026-04-20 | Dynamic assets Parameter |
| SOFT_PAUSE Endlos-Loop | 2026-04-20 | CL-Reset bei Expiry |
| KILL_SWITCH schließt keine Positionen | 2026-04-20 | Force-close in _evaluate_symbol |

---

## ⚠️ Known Limitations (V1, accepted)

- Same-candle Re-Entry blockiert (konservativer als Backtest)
- Trailing Stop Exit-Preis nutzt Stop-Level (minimal optimistisch)
- Kein Restart-Dedup (sehr unwahrscheinlich, harmlos)
- PAPER_MODE = keine echten Orders (by design)
- Backtest trailing nutzt CLOSE statt LOW (bekannte Lücke)

---

## 📋 Upcoming Work (not blockers)

| Was | Status | Phase |
|-----|--------|-------|
| Monitor V1 (Dashboard, Equity-Kurve) | ⬜ | 8.5 |
| Daily Report (21:00 Berlin) | ⬜ | 8.5 |
| Alerting (DD>15%, Guard-State Change) | ⬜ | 8.5 |
| Testnet API Trading (Phase 2) | ⬜ | 8.7 |
| V2 Strategy Design | ⬜ | 10 |