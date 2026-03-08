# Changelog

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
