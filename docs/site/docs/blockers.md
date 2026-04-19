---
title: Blockers
---

# 🚧 Blockers & Open Issues

> Aktuelle Blockaden und offene Punkte, die gelöst werden müssen.

---

## Aktuell

| # | Blocker | Status | Lösung |
|---|---------|--------|--------|
| 1 | Discord Embed-Formatierung | 🔨 In Arbeit | Bot API 403 → Alternative finden |
| 2 | Memory Search defekt | ⬸ Known | node-llama-cpp fehlt, braucht OpenClaw Update |
| 3 | OpenClaw v2026.4.12 | ⬸ Known | Docker Image von Hostinger, kein selbst-Update |

---

## Gelöst

| # | Blocker | Gelöst am | Lösung |
|---|---------|-----------|--------|
| 1 | Exec-Policy gesperrt | 2026-04-19 | `security=full, ask=off` gesetzt |
| 2 | Ollama Port nach Update | 2026-04-19 | 32770→32769, Config aktualisiert |
| 3 | Korrupte Marktdaten | 2026-04-18 | Frisch von Binance geladen |
| 4 | Discord Webhook 403 | 2026-04-19 | Auf OpenClaw message tool umgestellt |
| 5 | ATR-Filter | 2026-04-19 | Getestet und abgelehnt — ADX+EMA bleibt Gold Standard |

---

## Keine Blockers für Paper Trading

Die Executor V1 Module sind alle gebaut und getestet. Die verbleibenden Punkte (Embeds, Commands, systemd) sind **Enhancements**, keine Blocker.