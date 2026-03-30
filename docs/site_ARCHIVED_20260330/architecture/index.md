# Architecture

## Architecture Decision Records

| ADR | Status |
|-----|--------|
| [ADR-001: Target Architecture](https://github.com/dpxyz/pecz/blob/main/forward_v5/docs/ADR-001-target-architecture.md) | ✅ Approved |
| [ADR-002: Hyperliquid Integration](https://github.com/dpxyz/pecz/blob/main/forward_v5/docs/ADR-002-hyperliquid-integration.md) | ✅ Approved |
| ADR-003: State Model | 🔄 Draft |
| ADR-004: Risk Controls | ⬜ Pending |

## Design Principles

1. **Single Writer** — Only core_engine writes
2. **Deterministic State** — Rebuild from events
3. **Idempotency** — UUIDs prevent duplicates
4. **Timeouts Everywhere** — Every operation
5. **Health = Functionality** — Not just "process exists"

---

*Last updated: 2026-03-06 13:07 UTC*
