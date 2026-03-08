# BINANCE LEGACY CHECK
## Systematische Suche nach Altlasten

**Status:** Initial scan completed  
**Date:** 2026-03-06

---

## 1. Bereits bereinigt ✅

| Stelle | Alt | Neu | Status |
|--------|-----|-----|--------|
| `docs/M5a_architecture.md` | BINANCE_API_KEY | HL_API_CREDENTIALS | ✅ |
| `docs/M5_secrets_concept.md` | "Binance" | "Hyperliquid" | ✅ |
| `docs/ADR-002-hyperliquid-integration.md` | Binance-Auth | EIP-712 | ✅ |
| `config/m6_paper_canary.env` | BTCUSDT | BTC-USD | ✅ |

---

## 2. Noch zu bereinigen 📋

### 2.1 In `forward_v5/` (neues System - CRITICAL)

| Datei | Fundstelle | Aktion |
|-------|-----------|--------|
| `src/secrets/secret_provider.js` | Fallback für 'binance' | Entfernen |
| `src/exchange/exchange_client.js` | Binance-API-URLs | Replace mit Hyperliquid |

### 2.2 In `forward/forward_v5/` (altes System - MEDIUM)

| Datei | Fundstelle | Aktion |
|-------|-----------|--------|
| `src/execution.js` | Binance references | Archivieren/Read-only |
| `docs/M5b_pretrade_checks.md` | BTCUSDT example | Ersetzen |
| Tests | BTCUSDT asserts | Ersetzen durch BTC-USD |

### 2.3 Runtime/Config (LOW)

| Datei | Fundstelle | Aktion |
|-------|-----------|--------|
| `.env.example` | Wahrscheinlich vorhanden | Ersetzen durch HL-Beispiel |
| Legacy logs | Alte Trades | Archivieren, nicht löschen |

---

## 3. Archiviert (nicht editieren) 📦

Diese Bereiche bleiben unverändert:

```
forward/
├── incident_bundles/       # Historische Fehler
├── diagnostics/archive/    # Alte Bug-Reports
├── sessions/               # Memory/Sessions
└── runtime/backup_*       # State-Backups
```

---

## 4. Automatisierter Check

```bash
#!/bin/bash
# run_binance_check.sh

echo "=== Binance Legacy Check ==="

# Search in new system
echo "\n1. Checking forward_v5..."
grep -r -i "binance" forward_v5/src/ 2>/dev/null || echo "  ✓ No Binance refs in src"
grep -r -i "binance" forward_v5/docs/ 2>/dev/null || echo "  ✓ No Binance refs in docs"
grep -r "BTCUSDT" forward_v5/ 2>/dev/null || echo "  ✓ No BTCUSDT refs"

# Search ENV patterns
echo "\n2. Checking ENV variables..."
grep -r "BINANCE_API" forward_v5/ 2>/dev/null || echo "  ✓ No BINANCE_API refs"

# Search in tests
echo "\n3. Checking tests..."
grep -r "binance" forward_v5/tests/ 2>/dev/null || echo "  ✓ No Binance in tests"

echo "\n=== Check Complete ==="
```

---

## 5. Verification

Nach Bereinigung:

```bash
# Sollte leer sein:
grep -r -i "binance" forward_v5/src/
grep -r "BTCUSDT" forward_v5/

# Sollte Hyperliquid zeigen:
grep -r "hyperliquid\|HL_" forward_v5/config/
```

---

## 6. Zuständigkeiten

| Layer | Owner | Status |
|-------|-------|--------|
| Docs | Assistant | ✅ In Progress |
| Config | Assistant | ✅ Done |
| Src (new) | Assistant | 📋 Pending |
| Src (old) | User (archival) | 📦 Frozen |
| Tests | Assistant | 📋 Pending |

---

**Next Step:** Src-Module bereinigen
