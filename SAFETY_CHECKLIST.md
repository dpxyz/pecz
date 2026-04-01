# SAFETY CHECKLIST - Pre-Commit Pflicht

**Status:** BINDEND für alle Commits  
**Letzte Aktualisierung:** 2026-04-01  
**Verantwortlich:** Pecz (OpenClaw Agent)

---

## 🚨 ABSOLUTE PFlicht vor jedem Commit

Diese Checks MÜSSEN ausgeführt und dokumentiert werden:

### 1. Secrets Scanner (AUTOMATISCH)

```bash
# Vor jedem Commit ausführen:
cd /data/.openclaw/workspace/forward_v5

echo "=== SECRETS CHECK ==="

# Check 1: GitHub Tokens
git diff --cached | grep -iE "(ghp_|github_pat_|gho_|gpr_)" && echo "❌ GITHUB TOKEN FOUND" || echo "✅ No GitHub tokens"

# Check 2: API Keys (OpenAI, etc)
git diff --cached | grep -iE "(sk-|pk-)[a-zA-Z0-9]{20,}" && echo "❌ API KEY FOUND" || echo "✅ No API keys"

# Check 3: Generic Secrets
git diff --cached | grep -iE "(api_key|apikey|secret|password|token)\"?\s*[;:=]\s*\"?[a-z0-9]{16,}" && echo "❌ POTENTIAL SECRET" || echo "✅ No generic secrets"

# Check 4: Private Keys
git diff --cached | grep -E "(BEGIN|END) (RSA|DSA|EC|OPENSSH) PRIVATE KEY" && echo "❌ PRIVATE KEY FOUND" || echo "✅ No private keys"

# Check 5: Discord Webhooks (real ones)
git diff --cached | grep "discord.com/api/webhooks/[0-9]*/[a-zA-Z0-9_-]{40,}" && echo "❌ REAL DISCORD WEBHOOK" || echo "✅ No real webhooks"

echo "=== CHECK COMPLETE ==="
```

### 2. Manuelle Review (Pflicht)

- [ ] `.env` Dateien NIEMALS commiten
- [ ] `node_modules/` NIEMALS commiten
- [ ] Keine hardcoded URLs mit Tokens
- [ ] Keine Log-Files mit Session-Daten

### 3. Red Lines (NIEMALS übertragen)

| Was | Warum |
|-----|-------|
| `~/.netrc` | Niemals im Git |
| `.env` | Niemals commiten |
| `config.local.js` | Niemals commiten |
| `*.key`, `*.pem` | Niemals commiten |

---

## 📝 COMMIT TEMPLATE

Jeder Commit Message Prefix:

```
[Safety-Checked: YES/NO] Commit message

Details...
```

---

## ❌ Bei Verstoß

Wenn Secrets gefunden:
1. SOFORT Commit abbrechen
2. Secrets entfernen
3. `git commit --amend` oder reset
4. Neuen Clean-Commit erstellen

---

**Verpflichtung:** Diese Checkliste wird vor JEDEM Commit durchgeführt.
