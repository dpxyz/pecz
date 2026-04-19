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
| 4 | CL Gate (≤8) | 🟡 Decision | EMA-Signale erzeugen CL 10-11 → Dave muss über CL≤12 entscheiden |

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

---

## Fast keine Blocker mehr für Paper Trading

Die Executor V1 Module sind alle gebaut und getestet. Discord Commands und farbige Embeds sind fertig.
Alle 12 Audit-Bugs sind gefixt. Post-Fix Re-Validation läuft.

**Was noch fehlt:**
1. **Hyperliquid Testnet API Keys** (braucht Dave)
2. **CL Gate Entscheidung** — CL≤8 ergibt 12% Pass-Rate, CL≤12 ergibt 75% (Dave entscheidet)