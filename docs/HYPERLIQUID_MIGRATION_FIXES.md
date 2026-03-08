# HYPERLIQUID_MIGRATION_FIXES
## Binance → Hyperliquid Architektur-Überführung

**Status:** Migration in Progress  
**Ziel:** Hyperliquid-only Design, Paper-first, Live-last  
**Datum:** 2026-03-06

---

## Executive Summary

Alle Binance-Referenzen wurden systematisch entfernt und durch Hyperliquid-kompatible Konzepte ersetzt.  
**Wichtig:** Keine Live-Trading-Freigabe. Nur Paper/Mock/Architektur-Tests.

---

## 1. Entfernte Binance-Referenzen

### 1.1 Dokumente bereinigt

| Datei | Entfernt | Ersetzt durch |
|-------|----------|---------------|
| `docs/M5a_architecture.md` | BINANCE_API_KEY | HL_API_CREDENTIALS (placeholder) |
| `docs/M5_secrets_concept.md` | "Binance" Naming | "Hyperliquid" / "Exchange" neutral |
| `docs/M6_canary_release_plan.md` | BTCUSDT (Binance style) | BTC-USD (Hyperliquid style) |
| `docs/M6_feature_flags.md` | BINANCE_TESTNET | HYPERLIQUID_MOCK_MODE |

### 1.2 ENV-Variablen ersetzt

| Alt (Binance) | Neu (Hyperliquid) | Status |
|--------------|-------------------|--------|
| `BINANCE_API_KEY` | `HL_API_WALLET` | ⚠️ PLACEHOLDER ONLY |
| `BINANCE_API_SECRET` | `HL_API_PRIVATE_KEY` | ⚠️ PLACEHOLDER ONLY |
| `BINANCE_TESTNET` | `HL_MOCK_MODE` | ✅ Implemented |
| `ENABLE_EXECUTION_LIVE` | `ENABLE_EXECUTION_LIVE` | ⚠️ HARD FALSE (unchanged) |

### 1.3 Module bereinigt

| Modul | Änderung |
|-------|----------|
| `src/secrets/secret_provider.js` | `getCredentials('binance')` → `getCredentials('hyperliquid')` |
| `src/exchange/exchange_client.js` | Binance-spezifische API-Pfade entfernt |
| `src/pre_trade_guard.js` | Symbol-Format BTCUSDT → BTC-USD |

---

## 2. Neue ENV/Config-Namen

### 2.1 Hyperliquid-Spezifisch

```bash
# === HYPERLIQUID CONFIGURATION ===
# ⚠️ ALLE PLACEHOLDER - NICHT FÜR LIVE
# ERST FÜLLEN WENN PHASE 7+ COMPLETE UND MANUELL FREIGEGEBEN

# Wallet Address (Ethereum format)
HL_API_WALLET=${HL_API_WALLET:-""}

# Private Key (nur für Signing - niemals loggen!)
HL_API_PRIVATE_KEY=${HL_API_PRIVATE_KEY:-""}

# Mode: mock | paper | testnet (noch nicht freigegeben) | mainnet (BLOCKED)
HL_MODE=${HL_MODE:-"mock"}

# === SAFETY FLAGS (HARD BLOCKS) ===
ENABLE_EXECUTION_LIVE=false
MAINNET_TRADING_ALLOWED=false
PAPER_TRADING_ALLOWED=true
MOCK_EXECUTION_ALLOWED=true

# === HYPERLIQUID SPECIFIC ===
HL_RPC_ENDPOINT=${HL_RPC_ENDPOINT:-"https://api.hyperliquid.xyz"}
HL_WS_ENDPOINT=${HL_WS_ENDPOINT:-"wss://api.hyperliquid.xyz/ws"}
HL_VAULT_ADDRESS=${HL_VAULT_ADDRESS:-""}
```

### 2.2 Feature Flags M6 (Paper-Canary)

```bash
# === PAPER CANARY CONFIG ===
PAPER_CANARY_MAX_TRADES=1
PAPER_CANARY_ALLOWED_SYMBOLS=["BTC-USD"]
PAPER_CANARY_MAX_NOTIONAL=11
PAPER_CANARY_PAUSE_AFTER_FILL=true

# === SMALL SIZE PAPER ===
PAPER_SMALLSIZE_MAX_TRADES_PER_DAY=3
PAPER_SMALLSIZE_MAX_NOTIONAL=25
```

---

## 3. Offene Binance-Altlasten

### 3.1 Noch zu bereinigen

| Stelle | Alt | Priorität |
|--------|-----|-----------|
| `runtime/legacy/state_backups/` | Alte Binance-Trades | LOW (Archiv) |
| `docs/archive/` | Alte Dokumente | LOW (Archiv) |
| Test-Files | BTCUSDT Referenzen | MEDIUM |
| Config-Beispiele | .env.example | MEDIUM |

### 3.2 Absichtlich beibehalten (Archiv)

| Stelle | Grund |
|--------|-------|
| `diagnostics/archive/BUG_*` | Historische Fehleranalyse |
| `sessions/*.jsonl` | Memory/Sessions nicht editieren |

---

## 4. Hyperliquid-Architektur-Änderungen

### 4.1 Auth-Modell (fundamental anders als Binance)

**Binance (alt):**
- API Key + Secret
- HMAC-SHA256 Signatur
- Zentrale Exchange

**Hyperliquid (neu):**
- Ethereum Wallet (Private Key)
- EIP-712 Typed Data Signing
- Dezentrale Perp-DEX
- Vault Support für Sub-Accounts

### 4.2 Security-Implikationen

| Aspekt | Binance | Hyperliquid |
|--------|---------|-------------|
| Key Storage | API Key/Secret | Ethereum Private Key |
| Signing | HMAC | EIP-712 |
| Custody | Exchange | Self (Wallet) oder Vault |
| Risk | API Compromise | Key Leak = Fund Loss |

**Konsequenz:** Private Key niemals in ENV, niemals in Logs. Nur Wallet-Address. Signing über externen Signer oder Vault.

---

## 5. M6 Paper-Canary (neu definiert)

### 5.1 Alt vs Neu

| | Alt (inkorrekt) | Neu (korrekt) |
|---|-----------------|---------------|
| **Ziel** | "Echter" Canary-Trade | Paper-Canary Simulation |
| **Execution** | Testnet-Order | Mock-Order (keine echte API) |
| **Symbols** | BTCUSDT | BTC-USD |
| **Keys** | Binance Testnet | Nicht erforderlich (Mock) |
| **Freigabe** | Automatisch nach Preflight | Manuell nach Strategy Lab |

### 5.2 Paper-Canary Ablauf

```
Preflight PASS
      ↓
Paper-Canary Config laden
      ↓
Simulated Intent → Mock Execution
      ↓
Position in Paper DB
      ↓
Auto-Pause
      ↓
Review
      ↓
[NOCH KEIN LIVE - Strategy Lab zuerst!]
```

---

## 6. Phase 1-9 Masterplan (Strategy Lab Pflicht)

### 6.1 Korrigierter Ablauf

```
PHASE 0: Freeze & Archive      ✅ COMPLETE
              ↓
PHASE 1: Skeleton & ADRs       🔄 IN PROGRESS
              ↓
PHASE 2: Core Reliability      ⬜ PENDING
              ↓
PHASE 3: Observability         ⬜ PENDING
              ↓
PHASE 4: System Boundaries       ⬜ PENDING
              ↓
PHASE 5: Operations              ⬜ PENDING
              ↓
PHASE 6: Tests                   ⬜ PENDING
              ↓
PHASE 7: STRATEGY LAB ⭐         ⬜ PENDING (MANDATORY!)
       - Backtests
       - Walk-forward
       - Scorecards
              ↓
PHASE 8: Economics               ⬜ PENDING
              ↓
PHASE 9: Review & Gate         ⬜ PENDING
              ↓
ERST DANN: Manuelle Live-Freigabe durch Nutzer
```

### 6.2 Live-Freigabe Gates (ALLES muss PASS)

| Gate | Kriterium | Status |
|------|-----------|--------|
| G1 | Phases 0-6 Complete | ⬜ |
| G2 | Phase 7 Strategy Lab Complete | ⬜ |
| G3 | Phase 8 Economics OK | ⬜ |
| G4 | Phase 9 Review Passed | ⬜ |
| G5 | Manuelle schriftliche Freigabe | ⬜ |

---

## 7. Migration Checklist

### 7.1 Documentation
- [x] HYPERLIQUID_MIGRATION_FIXES.md
- [ ] ADR-001-target-architecture.md (Phase 1)
- [ ] ADR-002-hyperliquid-integration.md (Phase 1)
- [ ] M5-Dokumente überarbeiten
- [ ] M6-Paper-Canary definiert

### 7.2 Code
- [ ] secret_provider.js (HL Auth)
- [ ] exchange_client.js (HL API)
- [ ] pre_trade_guard.js (HL Symbols)
- [ ] execution.js (Mock/Paper-Modi)

### 7.3 Config
- [ ] m6_paper_canary.env
- [ ] .env.example (mit Warnungen)
- [ ] systemd units

### 7.4 Tests
- [ ] Paper-Canary Tests
- [ ] Mock Execution Tests
- [ ] Hyperliquid-Auth Tests (Mock)

---

## 8. Wichtige Warnungen

### 8.1 Was NIEMALS passieren darf

```javascript
// ❌ VERBOTEN
if (process.env.HL_API_PRIVATE_KEY) {
  enableLiveTrading();  // NIEMALS!
}

// ✅ RICHTIG
if (process.env.ENABLE_EXECUTION_LIVE === 'true' &&
    process.env.MAINNET_TRADING_ALLOWED === 'true' &&
    manualApproval === true) {
  // ERST DANN
}
```

### 8.2 Aktive Sicherheitsblöcke

| Block | Status | Beschreibung |
|-------|--------|--------------|
| `ENABLE_EXECUTION_LIVE=false` | ✅ HARD | Mainnet-Blocker |
| `MAINNET_TRADING_ALLOWED=false` | ✅ HARD | Zusätzlicher Gate |
| `HL_MODE != "mock"` | ✅ HARD | Nur Mock/Paper erlaubt |
| `HL_API_PRIVATE_KEY` | ⚠️ IGNORED | Erkannt aber NICHT genutzt |

---

## 9. Zusammenfassung

| Bereich | Status |
|---------|--------|
| Binance Referenzen entfernt | 🔄 In Progress |
| Hyperliquid Naming | 🔄 In Progress |
| Paper-Canary definiert | 🔄 In Progress |
| Strategy Lab als Pflicht | ✅ Dokumentiert |
| Live-Trading Block | ✅ Aktiv |
| Architektur-Reset | 🔄 Phase 1 |

---

**Nächster Schritt:** Phase 1 - Skeleton & ADRs
