# ADR-002: Hyperliquid Integration

**Status:** Proposed  
**Date:** 2026-03-06  
**Replaces:** Binance-only Legacy Architecture

---

## 1. Kontext: Warum Hyperliquid?

### 1.1 Binance Probleme
- Zentralisierte Custody
- API-Key-Risiko
- Rate Limits
- Regulatory Risiko

### 1.2 Hyperliquid Vorteile
- Dezentrale Perp-DEX
- Self-Custody (Wallet)
- Vault-System für Sub-Accounts
- Bessere Liquidität für Alts

### 1.3 Neue Herausforderungen
- EIP-712 Signing komplex
- On-Chain Confirmation Delays
- Gas Costs (aber auf L2)

---

## 2. Entscheidung: Architektur

```
┌────────────────────────────────────────────────────────┐
│              HYPERLIQUID INTEGRATION                    │
├────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │  Core Engine │───▶│  Execution   │───▶│  HL Mock  │ │
│  │              │    │  Router      │    │ (Default) │ │
│  └──────────────┘    └──────────────┘    └───────────┘ │
│                              │                        │
│                    ┌─────────┴─────────┐              │
│                    ↓                   ↓              │
│              ┌──────────┐       ┌──────────┐         │
│              │  Paper   │       │  Real HL │         │
│              │  Engine  │       │  Gateway │         │
│              │ (active) │       │ (BLOCKED)│         │
│              └──────────┘       └──────────┘         │
│                                                         │
│  ┌────────────────────────────────────────────────┐    │
│  │           AUTHENTICATION FLOW                    │    │
│  │                                                  │    │
│  │  Option A: External Signer (recommended)         │    │
│  │    - Private Key niemals im System             │    │
│  │    - Signer-Service oder Hardware Wallet        │    │
│  │                                                  │    │
│  │  Option B: Vault (für später)                   │    │
│  │    - Hyperliquid Vault für Sub-Account         │    │
│  │    - Delegated Signing                          │    │
│  │                                                  │    │
│  │  Option C: ENV (BLOCKED)                        │    │
│  │    - Private Key in ENV                         │    │
│  │    - NIE FÜR PRODUKTION!                        │    │
│  └────────────────────────────────────────────────┘    │
│                                                         │
└────────────────────────────────────────────────────────┘
```

---

## 3. Hyperliquid-Spezifika

### 3.1 Authentication

**Nicht wie Binance:**
```javascript
// ❌ Binance-Style
const signature = hmac_sha256(params, api_secret);
```

**Aber EIP-712:**
```javascript
// ✅ Hyperliquid-Style
const signature = eip712_sign(typed_data, private_key);
```

**Typed Data Example:**
```javascript
const action = {
  type: 'order',
  asset: 'BTC',
  is_buy: true,
  limit_px: 50000,
  sz: 0.1,
  reduce_only: false
};

// Sign with EIP-712
const signature = signTypedData(domain, types, action, privateKey);
```

### 3.2 Symbols

| Binance (alt) | Hyperliquid (neu) |
|---------------|---------------------|
| BTCUSDT | BTC-USD |
| ETHUSDT | ETH-USD |
| SOLUSDT | SOL-USD |

### 3.3 Order Types

| Type | Verfügbar | Nutzung |
|------|-----------|---------|
| Market | ✅ | Primary (im Paper-Canary) |
| Limit | ✅ | Für präzise Entries |
| Stop-Market | ✅ | SL Orders |
| TP-Market | ✅ | TP Orders |

---

## 4. Sicherheits-Architektur

### 4.1 Private Key Handling

**ABSOLUT VERBOTEN:**
```javascript
// ❌ NIE MACHEN
const privateKey = process.env.HL_API_PRIVATE_KEY;
```

**Akzeptabel (Paper/Mock):**
```javascript
// ✅ Mock-Mode, kein echter Key
const mockWallet = '0x' + '1'.repeat(40); // Dummy
```

**Zukunft (Live):**
```javascript
// ✅ External Signer-Server
const signerUrl = process.env.HL_SIGNER_URL;
const signature = await http_post(signerUrl, action);
```

### 4.2 Hard Security Gates

```javascript
// src/config/security_gates.js
const SECURITY_GATES = {
  // Gate 1: Execution Master Switch
  ENABLE_EXECUTION_LIVE: {
    default: false,
    change_requires: ['manual_approval', 'strategy_lab_complete'],
    hard_block: true
  },
  
  // Gate 2: Mainnet Blocker
  MAINNET_TRADING_ALLOWED: {
    default: false,
    change_requires: ['phase_9_complete', 'written_sign_off'],
    hard_block: true
  },
  
  // Gate 3: Mode Validation
  HL_MODE: {
    allowed: ['mock', 'paper'],  // 'testnet', 'mainnet' BLOCKED
    change_requires: ['manual_approval']
  },
  
  // Gate 4: Private Key Check (nicht als Freigabe!)
  PRIVATE_KEY_PRESENT: {
    action: 'log_only',
    never_triggers_go: true
  }
};
```

---

## 5. Implementierungs-Phasen

### Phase 1-6: Mock/Paper only
```javascript
// Nur diese Modi erlaubt
const allowedModes = ['mock', 'paper'];
```

### Phase 7: Strategy Lab
- Backtests mit Hyperliquid-Daten
- Keine Live-Integration

### Phase 8+: Live-Freigabe
- **ERST nach manueller Freigabe durch Nutzer**
- External Signer Setup
- Testnet (wenn verfügbar)
- Mainnet (extrem restriktiv)

---

## 6. ENV-Variablen

### 6.1 Erlaubt (Paper/Mock)

```bash
# Mode
HL_MODE=mock                    # oder "paper"

# Mock/Placeholder (kein echter Wert!)
HL_MOCK_WALLET=0x1234...      # Dummy für Tests

# RPC (nur lesend in Paper)
HL_RPC_ENDPOINT=https://api.hyperliquid.xyz
```

### 6.2 BLOCKIERT (bis manuelle Freigabe)

```bash
# ❌ NICHT setzen ohne ausdrückliche Genehmigung:
HL_API_PRIVATE_KEY=<PRIVATE_KEY>
HL_VAULT_ADDRESS=<VAULT>
HL_MODE=testnet
HL_MODE=mainnet
ENABLE_EXECUTION_LIVE=true
MAINNET_TRADING_ALLOWED=true
```

---

## 7. Konsequenzen

### 7.1 Positiv
- Self-custody (kein Exchange-Risiko)
- Besseres Altcoin-Universum
- Transparente on-chain Verification

### 7.2 Negativ
- Komplexeres Signing (EIP-712)
- Initial: kein Testnet (HL hat kein öffentliches Testnet)
- On-chain Latency

### 7.3 Risken
- Smart Contract Risiken
- Bridge-Risiken (für Ein-/Auszahlung)

---

## 8. Alternativen

| Alternative | Abgelehnt wegen |
|-------------|-----------------|
| Beibehaltung Binance | Custody-Risiko |
| dYdX | Weniger Liquidität |
| GMX | Höhere Fees |

---

## 9. Nächste Schritte

1. Hyperliquid Mock-Modul implementieren
2. Paper-Trading mit HL-Preisen
3. **ERST nach Phase 7**: External Signer evaluieren
4. **ERST nach Phase 9**: Manuelle Live-Freigabe

---

**Approved:** 2026-03-06  
**Implementation:** Mock-Modul in Phase 1-2
