# Offene Blocker

## Aktiv

| ID | Blocker | Status | Owner | Impact |
|----|---------|--------|-------|--------|
| B1 | ~~ADR-003/004 incomplete~~ | ✅ Gelöst | @assistant | - |
| B3 | Strategy Lab not started | ⏳ | @user | Phase 7 |
| **B11** | **5.1 Host Validation** | ⏳ **DEFERRED** | @user/@assistant | **5.2 blocked** |

## Deferred / Pending Validation

| ID | Blocker | Status | Next Step |
|----|---------|--------|-----------|
| B11 | Block 5.1 Host-Test auf systemd-Maschine | ⏳ Code ✅ / Runtime ⏳ | VPS-Zugang oder manuelles Deploy |

## Gelöst

| ID | Blocker | Gelöst |
|----|---------|--------|
| B0 | Architektur unklar | 2026-03-06 |
| B1 | ADR-003/004 incomplete | 2026-03-08 |
| B2 | Systemd templates fehlen | ➡️ Block 5.1 ✅ Code Complete |
| B10 | Fix 5.0d Memory Monitoring | 2026-04-01 ✅ GO |

## Blocker-Policy

| Code | Bedeutung |
|------|-----------|
| 🔄 | In Progress |
| ⬜ | Not started |
| ⏳ | Waiting for dependency |
| ✅ | Resolved |
| ⛔ | Hard block |
| ⏸️ | Deferred (nicht blockierend) |

## Spezial: Block 5.1 Status

```
┌─────────────────────────────────────────┐
│ Block 5.1: Systemd Integration         │
├─────────────────────────────────────────┤
│ Code:        ✅ COMPLETE (v1.1)          │
│ Syntax:      ✅ VALIDATED               │
│ Host Test:   ⏳ PENDING                 │
│ Impact:      ⏸️ 5.2 waits for systemd │
└─────────────────────────────────────────┘

Action Required:
- Echte systemd-Maschine für Test
- Keine Docker-Workarounds
- Kein künstliches blockieren von 5.2
```

---

*Last updated: 2026-04-01 10:41 CET*
