# Changelog

## [v10-funding-first] - 2026-04-30

### V10 Funding-First Strategy
- **Funding Rate Standalone Test**: 6/6 assets profitable vs random, +0.43% avg per trade
- **DOGE strongest**: +1.12% per trade, 70.2% win rate, +0.76% vs random
- **V9 CONFIRMED**: 150+ strategies, 0 WF-passed — standard indicators have zero alpha
- **Foundry CRON PAUSED**: no more runs until V2 data validated
- **V2 Data Collector**: 6 free sources (HL Funding, Binance Funding/OI/LS/Taker, F&G)
- **Correlation Analysis**: Funding Rate -0.11 to -0.17 with 24h returns (above 0.05 threshold)
- **Funding Filter Test**: +1.6% improvement on existing strategies, but can't rescue negative base
- **V10 Spec**: `/research/V10_SPEC.md` — hypothesis-driven, kill criteria at every step
- **Dave Decision**: Foundry = Motor, Funding = Kraftstoff. Don't bypass Foundry, extend it.
- **3 Self-Corrections**: (1) Funding as Kill-Switch vs Entry — V2 assumptions outdated, (2) WF windows overlap with 60d data — need 1yr, (3) Engineering estimate 3-5d was overblown — 1-2d realistic
- **Key Insight**: Funding payment is a hidden cost (up to 0.15% for 24h hold) — must be modeled in backtest

### Plan
- Phase 1: Validate Edge (2 days) — 1yr data, slippage+fees, regime analysis
- Phase 2: Foundry V10 (2 days eng, 7-14d running) — Funding data as kraftstoff
- Phase 3: Paper Engine (2 days) — best strategy live 14 days

## [v9-redesign] - 2026-04-29

### Foundry V9 Oktopus Redesign (ADR-011)
- **WF-Gate V8.1**: New scoring — OOS Return 40% + Profitable Ratio 30% + Trade Floor 30%
- **ALL 4 old champions DEMOTED** — were statistical noise, not real edge
- **Zero strategies pass new gate** — confirms: no edge on 1h standard indicators
- **V9 Arms**: MR-ALT (alts only), MR-RELAXED, TREND-REGIME, SIGNAL-EXIT, VOL-BOOSTED, CROSS-ASSET
- **Exit Overhaul**: Trailing Stop removed, Signal-Reversal-Exit instead
- **Mutation Guards**: HOF-only, entry-only, trade floor ≥3, MR max 40%
- **Composite Fitness V9**: OOS 30%, Target-Asset 25%, Trades 20%, WF 15%, DD 10%
- **HOF Reset**: Starts empty — all V8 entries failed V8.1 gate
- **IS Pre-Filter**: <3 trades/asset/window → skip WF (saves 80% compute)

### Key Lessons (150+ strategies)
1. MR works only on DOGE/ADA/AVAX — never on BTC/ETH
2. Trailing Stop 2-3% never fires (80-91% signal_exit)
3. Entries too restrictive — 0.4 trades/window = noise
4. IS-Score overfits 150x (V17: IS=4.88, OOS=-0.15%)
5. "Not losing" ≠ "making money" — old gate rewarded 0-trade strategies
6. Standard indicators (BB/RSI/EMA) have no edge on 1h crypto

## [v8-oktopus] - 2026-04-27

### Foundry V8 Oktopus Architecture
- 6 arms: MR, Trend, Momentum, Volume, Regime, 4H
- Deep Autopsy V2: 6 analyses (Exit-Reason, Window, Asset, Regime, Trade-Density, DD)
- Parameter Sweep with Grid + Regime Overlay
- Budget steering: arm performance → dead=probe, producing=extra
- 4h arm with on-the-fly aggregation
- Gradient IS-Score (negative = losing but comparable)
- Mutation feed from autopsy generates concrete entry_modifier + exit_modifier
- Fixed: 4H arm candidates=0 bug (strategy_type vs classify_strategy_type)
- Fixed: exit_modifier {} overwriting defaults → merge with base config
- N_EXPLORATION_PER_TYPE raised from 2 to 5

### Key Insight
- 170+ strategies tested, 0 with 10-Window WF-passed
- 92% signal_exit, 0.6-2.5 trades/window (too restrictive)
- MR works only on volatile alts (DOGE, ADA)
- 1h-crypto with standard indicators has no robust edge

## [v5.0.0-phase4-frozen] - 2026-03-28

### ✅ Phase 4 FREEZE COMPLETE — 24 Hours, No Incidents

**Freeze Period:** 2026-03-27 12:11 UTC → 2026-03-28 12:11 UTC  
**Duration:** 24 hours  
**Status:** ✅ **SUCCESS** — System validated, Phase 5 GO granted

**Freeze Summary:**

| Metric | Value |
|--------|-------|
| Tests Passing | 191/191 ✅ |
| Critical Issues | 0 |
| Code Changes | 0 (only 1 test fix at T+0h) |
| Freeze Violations | 0 |

**Key Findings:**
- System remained stable for 24 hours with no changes
- All automated health checks passed
- No circuit breaker events triggered
- No SAFETY or OBSERVABILITY violations

**Go/No-Go Decision:**

| Criterion | Result |
|-----------|--------|
| Freeze without critical incidents | ✅ **YES** |
| New bugs found | ✅ **NO** |
| Unexpected events | ✅ **NO** |
| Recommendation | ✅ **GO for Phase 5** |

**Next:** Phase 5 — Operations (Production Readiness)

**Tags:**
- `v5-phase4-frozen`
- See also: `FINAL_FREEZE_REPORT.md`

---

## [v5.0.0-phase4-complete] - 2026-03-27

### ✅ Phase 4 COMPLETE — System Boundaries (10/10 Tests)

**Phase 4 Summary:**
| Block | Deliverable | Tests |
|-------|-------------|-------|
| Block 4.1 | Safety Boundary docs | — |
| Block 4.2 | Observability Boundary docs | — |
| Block 4.3 | Incident Response runbooks | — |
| Block 4.4 | Circuit Breaker MVP | 10/10 ✅ |
| Block 4.5 | Integration Tests | 10/10 ✅ |
| **Total** | | **10/10** ✅ |

**Circuit Breaker States:**
- CLOSED → Normal operation, trading allowed
- OPEN → SAFETY failure, trading BLOCKED
- HALF_OPEN → Recovery validation

**Key Guarantees:**
- SAFETY failures → Circuit Breaker OPEN (trading halts)
- OBSERVABILITY failures → Log only (NEVER blocks)
- Manual reset required: `attemptReset()` → `confirmReset()`
- All mutations via explicit events

**Integration Tests:**
- IT1-10: Full end-to-end SAFETY/OBSERVABILITY boundary
- Event chain verified
- Documentation matches runtime behavior

**Tags:**
- `v5-phase4-complete`
- `freeze/phase4`

---

## [v5.0.0-phase3-complete] - 2026-03-27

### ✅ Phase 3 COMPLETE — Observability (68/68 Tests)

**Phase 3 Summary:**
| Block | Deliverable | Tests |
|-------|-------------|-------|
| Block 3.1 | Logger (structured JSON) | 14/14 ✅ |
| Block 3.2 | Health Service + Boundary | 30/30 ✅ |
| Block 3.4 | Rebuild CLI | 10/10 ✅ |
| Block 3.3 | Report Service | 14/14 ✅ |
| **Total** | | **68/68** ✅ |

**Block 3.1: Logger**
- 5 log levels: DEBUG, INFO, WARN, ERROR, FATAL
- Structured JSON output with correlation IDs
- Size-based rotation with retention
- Console fallback on file errors
- Never throws (fail-safe)

**Block 3.2: Health Service**
- Continuous health monitoring (30s interval)
- SAFETY/OBSERVABILITY strict boundary
- SAFETY failure → BLOCK/PAUSE + Event + Log
- OBSERVABILITY failure → WARN + Log (never blocks)
- Discord webhook integration
- isPaused tracking with resumeTrading()

**Block 3.4: Rebuild CLI**
- `rebuild_state.js` CLI tool
- `--dry-run` mode (show diff)
- `--force` mode (apply with backup)
- State validation: Rebuild == Live
- Automatic backup before force

**Block 3.3: Report Service**
- Hourly reports: Positions, PnL, Trades, Health
- Daily session recaps
- Queue on Discord failure
- Retry with exponential backoff (5s, 15s, 30s, 60s)
- Dedup against spam (5 min cooldown)
- Health pause visibility

**Tag:** `v5-phase3-complete`

---

## [v5.0.0-phase2-complete] - 2026-03-08

### ✅ Phase 2 COMPLETE — Core Reliability (103/103 Tests)

**Block 4: Reconcile Engine**
- `src/reconcile.js` — 4 Mismatch Detectors
- Ghost Position: Internal exists, External missing → BLOCK
- Unmanaged Position: External exists, Internal missing → BLOCK/WARN
- Size Mismatch: Tolerance-based (10 bps = 0.1%)
- Side Mismatch: Direction conflict → BLOCK
- Pure functions, deterministic
- **Tests: 28/28 passing**

**Phase 2 Stats:**
| Block | Module | Tests |
|-------|--------|-------|
| Block 1 | Event Store | 17/17 ✅ |
| Block 2 | State Projection | 19/19 ✅ |
| Block 3 | Risk Engine | 39/39 ✅ |
| Block 4 | Reconcile | 28/28 ✅ |
| **Total** | | **103/103** ✅ |

**Architecture Decisions**
- Sequence-based ordering (deterministic)
- Safety gates BLOCK, Observability gates WARN
- Tolerance-based severity (Size mismatch)
- Pure functions throughout

**Safety**
- All gates tested, no live trading paths
- Hyperliquid paper/mock only
- Deterministic: same input → same output

**Tag:** `v5-phase2-block4-complete`

---

### Added
- **Block 1: Event Store** (`src/event_store.js`)
  - SQLite Events table with sequence for deterministic ordering
  - Idempotent append via ON CONFLICT(event_id) DO NOTHING
  - Query interface with pagination
  - **17/17 Tests passing**
  
- **Block 2: State Projection** (`src/state_projection.js`)
  - 27 Event Reducers for all event types
  - `project(events[])` → State (pure functions)
  - `rebuild()` from Event Store (deterministic)
  - `incrementalUpdate()` for live updates
  - **19/19 Tests passing**
  
- **Block 3: Risk Engine** (`src/risk_engine.js`)
  - 6 Gates: Sizing, Hyperliquid Rules, Whitelist, Watchdog, Reconcile, Unmanaged
  - Safety → BLOCK / Observability → WARN (never blocks)
  - `checkAll()` returns events + decisions
  - **39/39 Tests passing**

### Architecture Decisions
- ADR-003: State Model (Event Sourcing)
- ADR-004: Risk Controls (6 Gates)
- Sequence-based ordering (not just timestamp)
- Pure functions: no side effects in state projection

### Commits
- `1e46885` Block 1 Complete: Event Store
- `b64ff9a` Block 2 COMPLETE: State Projection (100% green)
- `???????` Block 3 COMPLETE: Risk Engine (100% green)

### Security
- Safety:Gates may BLOCK trading
- Observability:Gates may NEVER block trading
- Hyperliquid-only (paper/mock)
- All modules: test-first, deterministic

---

## [v5.0.0-phase1] - 2026-03-06

### Added
- Mission Control site
- ADR-001, ADR-002
- Phase 0-9 Masterplan
- M5/M6 documentation
- Cloudflare Pages config

### Changed
- Architecture: clean rebuild
- Platform: Binance → Hyperliquid
- Mode: testnet → paper/mock

### Security
- ENABLE_EXECUTION_LIVE=false
- MAINNET_TRADING_ALLOWED=false
- HL_MODE ∈ {mock, paper}

---

*Last updated: 2026-03-08 12:46 UTC*
