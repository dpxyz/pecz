---
title: Blockers
---

# 🚧 Blockers & Open Issues

> Aktuelle Blockaden und offene Punkte, die gelöst werden müssen.

---

## Aktuell

| # | Blocker | Status | Lösung |
|---|---------|--------|--------|
| 1 | Memory Search defekt | ⬸ Known | node-llama-cpp fehlt, braucht OpenClaw Update |
| 2 | OpenClaw v2026.4.12 | ⬸ Known | Docker Image von Hostinger, kein selbst-Update |
| 3 | **Hyperliquid Testnet** | 🔴 Blocked | Braucht Dave für API-Key Setup |

---

## Gelöst

| # | Blocker | Gelöst am | Lösung |
|---|---------|-----------|--------|
| 1 | Exec-Policy gesperrt | 2026-04-19 | `security=full, ask=off` gesetzt |
| 2 | Ollama Port nach Update | 2026-04-19 | 32770→32769, Config aktualisiert |
| 3 | Korrupte Marktdaten | 2026-04-18 | Frisch von Binance geladen |
| 4 | Discord Webhook 403 | 2026-04-19 | Auf OpenClaw message tool umgestellt |
| 5 | ATR-Filter | 2026-04-19 | Getestet und abgelehnt — ADX+EMA bleibt Gold Standard |
| 6 | Discord Embed-Formatierung | 2026-04-19 | Components v2 Container mit Farbaccent |
| 7 | CL Gate | 2026-04-19 | CL≤12 approved (75% Pass-Rate) |
| 8 | Trailing Stop Bug | 2026-04-19 | CLOSE vs LOW analysiert, Backtest auf CLOSE revertiert, Paper Engine validiert |

---

## Einzig verbleibender Blocker für Paper Trading

**Hyperliquid Testnet API Keys** — Dave muss das Setup machen.

Alles andere steht: Executor V1, Leverage Tiers, Discord Commands, Guard States.