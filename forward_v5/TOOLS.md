# TOOLS.md - OpenClaw Forward v5

## ⚠️ MANDATORY: Pre-Push Safety Checklist

**Diese Checkliste MUSS von Pecz vor jedem Push abgearbeitet werden:**

### Pre-Push Security Verification (Pﬂicht)

Vor `git push origin main` IMMER ausführen:

```bash
cd /data/.openclaw/workspace/forward_v5

echo "=== MANDATORY PRE-PUSH CHECKLIST ==="
echo ""
echo "[✓] Step 1: Pre-commit hook ran successfully?"
git status

echo ""
echo "[✓] Step 2: No .env files staged?"
! git diff --cached --name-only | grep -q "\\.env" && echo "   ✅ PASS" || echo "   ❌ FAIL - .env found!"

echo ""
echo "[✓] Step 3: No real secrets in staged changes?"
git diff --cached -p | grep -iE "(ghp_|github_pat_|sk-[a-zA-Z]{20,}|discord\\.com/api/webhooks/[0-9]+/[a-zA-Z0-9_-]{40,})" | grep -v "YOUR_" | grep -v "test_" && echo "   ❌ FAIL - Real secrets found!" || echo "   ✅ PASS"

echo ""
echo "[✓] Step 4: Safety-Checklist committed?"
git diff --cached --name-only | grep -q "SAFETY_CHECKLIST" && echo "   ✅ Yes" || echo "   ⚠️  No (fine if not modified)"

echo ""
echo "=== CHECKLIST COMPLETE ==="
echo "If all checks passed: Push allowed"
echo "If any check failed: STOP and fix"
```

### Red Lines (NIEMALS brechen)

| Verboten | Konsequenz |
|----------|------------|
| `git push --no-verify` | AUSGESCHLOSSEN |
| Secrets in Commit | SOFORT Revert |
| `.env` commiten | SOFORT Revert |
| "Schnell mal pushen" | VERBOTEN |

### Verify Hook is Active

Test:
```bash
cd /data/.openclaw/workspace/forward_v5/.git/hooks
ls -la pre-commit  # Sollte existieren und executable sein
```

---

## Discord Alert Configuration

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
