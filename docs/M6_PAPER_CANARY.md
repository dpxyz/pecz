# M6: Paper-Canary Release Plan
## NO LIVE TRADING - Mock/Paper only

**Status:** Planning  
**Target:** Phase 1 (Skeleton)  
**Execution:** MOCK/PAPER only  
**Real Keys:** NOT REQUIRED  
**Live Freigabe:** BLOCKED until Phase 9

---

## 1. Ziele

| # | Ziel | Wie |
|---|------|-----|
| 1 | Core Engine testen | Mit Mock-Execution |
| 2 | Risk Engine validieren | Paper-Orders |
| 3 | State Projection prüfen | Rebuild aus Events |
| 4 | Observability testen | Discord, Reports |
| 5 | Keine Live-Risiken | Keine echten Keys |

---

## 2. Was ist "Paper-Canary"?

### Nicht:
- ❌ Keine echten API-Aufrufe
- ❌ Keine Testnet-Keys
- ❌ Keine echten Orders

### Sondern:
- ✅ Simulierte Intents
- ✅ Mock-Execution
- ✅ Paper-Positionen (in DB)
- ✅ Events wie bei echtem Trading

### Flow

```
Signal → Intent → MOCK Execution → Paper Position
              ↓
         Events schreiben
              ↓
         State Projection
              ↓
         Discord Alert
```

---

## 3. Configuration

```bash
# config/m6_paper_canary.env

# === MODE ===
HL_MODE=paper              # oder "mock"

# === SAFETY ===
ENABLE_EXECUTION_LIVE=false
MAINNET_TRADING_ALLOWED=false

# === PAPER CANARY ===
PAPER_CANARY_MAX_TRADES=1
PAPER_CANARY_ALLOWED_SYMBOLS=["BTC-USD"]
PAPER_CANARY_MAX_NOTIONAL=11
PAPER_CANARY_PAUSE_AFTER_FILL=true

# === RISK ===
PAPER_CANARY_SL_PCT=0.88
PAPER_CANARY_TP_PCT=1.76

# === OBSERVABILITY ===
DISCORD_WEBHOOK=${DISCORD_WEBHOOK:-""}
ALERT_ON_PAPER_FILL=true
```

---

## 4. Phasen

### Phase 0: Preflight (Auto)

```bash
./cli.js preflight --phase paper-canary
```

**Checks:**
- [ ] Database exists
- [ ] Events table ready
- [ ] HL_MODE = paper/mock
- [ ] ENABLE_EXECUTION_LIVE = false
- [ ] No unmanaged positions
- [ ] Discord webhook configured (optional)

**Result:** ⬜ GO / ⬜ NO-GO

### Phase 1: Paper-Canary Execution

```javascript
// Simulierter Ablauf:

// 1. Signal generieren
const signal = {
  symbol: 'BTC-USD',
  side: 'LONG',
  entry_price: 50000,  // Simuliert
  confidence: 0.85,
  timestamp: Date.now()
};

// 2. Intent erstellen
const intent = createIntent(signal);

// 3. Risk Engine prüfen
const validation = riskEngine.validate(intent);
if (!validation.passed) {
  logEvent('INTENT_REJECTED', validation);
  return;
}

// 4. MOCK Execution (keine echte API!)
const mockFill = {
  order_id: generateUUID(),
  filled_price: signal.entry_price * (1 + randomSlippage()),
  filled_qty: intent.qty,
  status: 'FILLED',
  timestamp: Date.now()
};

// 5. Paper Position speichern
const position = {
  position_id: generateUUID(),
  ...mockFill,
  sl_price: intent.sl_price,
  tp_price: intent.tp_price,
  unrealized_pnl: 0
};
await db.positions.insert(position);

// 6. Event loggen
logEvent('PAPER_POSITION_OPENED', position);

// 7. Auto-pause
canary.pauseAfterFill();

// 8. Discord Alert
sendAlert('📝 Paper-Canary Trade Executed', position);
```

### Phase 2: Review (Manual)

**Checklist:**
- [ ] Event in Datenbank?
- [ ] Position korrekt angelegt?
- [ ] State Projection OK?
- [ ] Discord Alert gesendet?
- [ ] Auto-pause funktioniert?

**Result:**  
⬜ Phase 2 Success → Continue to Integration  
⬜ Phase 2 Issues → Debug → Retry

---

## 5. Events Generated

| Event | Status | Daten |
|-------|--------|-------|
| `CANARY_REHEARSAL_START` | OK | Config |
| `SIGNAL_RECEIVED` | OK | Signal Details |
| `PRETRADE_VALIDATION_PASS` | OK | All Checks |
| `INTENT_CREATED` | OK | Intent |
| `MOCK_ORDER_SENT` | OK | Order ID |
| `MOCK_ORDER_FILLED` | OK | Fill Details |
| `PAPER_POSITION_OPENED` | OK | Position |
| `CANARY_AUTO_PAUSE` | OK | Reason |
| `ALERT_SENT` | OK | Channel |
| `CANARY_REHEARSAL_COMPLETE` | OK | Summary |

---

## 6. Go/No-Go

### Paper-Canary ist GO wenn:

```
✅ All 10 Events generated
✅ Position in DB
✅ State projection correct
✅ Risk validation passed
✅ Auto-pause triggered
✅ Discord alert sent (or logged)
```

### Paper-Canary ist NO-GO wenn:

```
❌ Missing events
❌ State mismatch
❌ Risk validation failed
❌ Auto-pause didn't trigger
```

---

## 7. Nächster Schritt (NICHT LIVE!)

| Current | Next |
|---------|------|
| Paper-Canary Success | Phase 2 Reliability Tests |
| Phase 2 Success | Phase 3 Observability |
| ... | ... |
| Phase 6 Success | Phase 7: Strategy Lab |
| Phase 7-9 Success | **ERST DANN: Manuelle Live-Freigabe** |

---

## 8. Rollback

Immer möglich (auch in Paper-Mode):

```bash
./cli.js pause --reason "Paper-canary review"
```

Wirkung:
- Execution stop
- Intents cleared
- State preserved für Analysis

---

**Document Version:** 1.0  
**Status:** Planning  
**Live Trading:** ⛔ BLOCKED
