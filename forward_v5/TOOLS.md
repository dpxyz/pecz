# TOOLS.md - OpenClaw Forward v5

## Discord Alert Configuration

**Environment Variable:** `DISCORD_WEBHOOK_URL`

**Location:** Set in `.env` file or export before running:
```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_TOKEN"
```

**Alert Behavior:**
- CRITICAL: @here mention + loud notification + embed
- WARNING: No mention, quiet notification + embed  
- INFO: Not sent

**Test Command:**
```bash
curl -H "Content-Type: application/json" \
  -d '{"content":"Forward v5 Alert Test"}' \
  $DISCORD_WEBHOOK_URL
```

## Health Server

**Port:** 3000 (configurable via `PORT` env)

**Endpoints:**
- `/health/live` - Liveness probe
- `/health/ready` - Readiness + Alert evaluation
- `/health/startup` - Startup probe
- `/health` - Aggregated health
- `/alerts` - Active alerts (for dashboard)

**Start:**
```bash
cd forward_v5/cli
PORT=3000 node health_server.js
```

**Auto-start with systemd:** See Block 5.1 docs

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DISCORD_WEBHOOK_URL` | Alert destination | none (alerts logged only) |
| `PORT` | Health server port | 3000 |

---
Last updated: Block 5.3.3 complete
