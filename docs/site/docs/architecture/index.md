# Architecture

## Architecture Decision Records

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](adr-001.md) | Target Architecture | ✅ Approved |
| [ADR-002](adr-002.md) | Hyperliquid Integration | ✅ Approved |
| [ADR-003](adr-003.md) | State Model | ✅ Approved |
| [ADR-004](adr-004.md) | Risk Controls | ✅ Approved |
| [ADR-005](adr-005.md) | Three-Layer Architecture | ✅ Approved |
| [ADR-006](adr-006.md) | Paper Trading (14+14) | ✅ Approved |
| [ADR-007](adr-007.md) | Leverage Tiers | ✅ Approved |
| [ADR-008](adr-008.md) | Crash & Uptime Strategy | 🔄 Proposed |
| [ADR-009](adr-009.md) | V2 Data Availability | ✅ Accepted |
| [ADR-010](adr-010.md) | V2 Strategy — Der Oktopus | 🔄 Proposed |
| [ADR-011](adr-011.md) | Foundry V9 Oktopus Redesign | ✅ Accepted |

## Design Principles

1. **Single Writer** — Only core_engine writes
2. **Deterministic State** — Rebuild from events
3. **Idempotency** — UUIDs prevent duplicates
4. **Timeouts Everywhere** — Every operation
5. **Health = Functionality** — Not just "process exists"

---

*Last updated: 2026-04-29*