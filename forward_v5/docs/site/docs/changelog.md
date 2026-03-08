# Changelog

## [v5.0.0-phase2-blocks-1-3] - 2026-03-08

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
