---
title: Blockers
---

# 🚧 Blockers & Open Issues

> Aktuelle Blockaden und offene Punkte.

---

## Aktuell

| # | Blocker | Status | Lösung |
|---|---------|--------|--------|
| 1 | Memory Search defekt | ⬸ Known | node-llama-cpp fehlt, braucht OpenClaw Update |
| 2 | OpenClaw v2026.4.12 | ⬸ Known | Docker Image von Hostinger |

**Keine akuten Blocker für Paper Trading!** 🎉

---

## Gelöst (2026-04-20)

| # | Blocker | Gelöst am | Lösung |
|---|---------|-----------|--------|
| 1 | Exec-Policy gesperrt | 04-19 | `security=full, ask=off` |
| 2 | Ollama Port | 04-19 | 32770→32769 |
| 3 | Korrupte Marktdaten | 04-18 | Frisch von Binance |
| 4 | Discord Webhook 403 | 04-19 | OpenClaw message tool |
| 5 | ATR-Filter | 04-19 | Getestet und abgelehnt |
| 6 | Discord Embeds | 04-19 | Components v2 Container |
| 7 | CL Gate | 04-19 | CL≤12 approved (75%) |
| 8 | Trailing Stop Bug | 04-19 | CLOSE vs LOW analysiert |
| 9 | **Hyperliquid Testnet** | **04-20** | **API Wallet autorisiert, $999 Balance** |
| 10 | **Capital Model** | **04-20** | **100€ Total (nicht per Asset)** |

---

## Nächste Schritte

1. Monitor V1 bauen (Equity-Kurve, Dashboard, Alerts)
2. 30+ Tage Paper Trading laufen lassen
3. Nach 30 Tagen: Success Criteria prüfen