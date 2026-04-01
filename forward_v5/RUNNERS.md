# Workspace Cleanup - RUNNERS.md
**Cleanup Date:** 2026-04-01 09:07 CET  
**Performed by:** Pecz (OpenClaw Agent)  
**Reason:** Remove stale parallel runners/logs to prevent status confusion

---

## ✅ ACTIVE RUN (DO NOT TOUCH)

| Attribute | Value |
|-----------|-------|
| **Run ID** | rv-2026-03-31-2pv6s2 |
| **PID** | 20027 |
| **Type** | Fix 5.0d Validation Run (24h, was 48h) |
| **Status** | RUNNING |
| **Start** | 2026-03-31 09:57 CET |
| **Planned End** | 2026-04-01 09:57 CET (~1h remaining) |
| **Uptime** | ~23h 10min |
| **State File** | `/data/.openclaw/workspace/forward_v5/forward_v5/runtime_validation/state.json` |
| **Log File** | `/tmp/fix_50d_2h_test.log` |
| **PID File** | `/tmp/fix_50d_pid.txt` (contains: 20027) |

### Current Metrics (from state.json)
- **Heartbeats:** 1373 received, 0 missed ✅
- **Health Checks:** 159 passed / 117 failed (57% pass rate)
- **Alerts:** 24 CRITICAL, 93 WARN, 0 FATAL
- **Memory:** 75.3% used (stable, no growth)

---

## 📦 ARCHIVED RUNS (Moved to `/archive/2026-04-01_cleanup_legacy/`)

### Stopped PIDs (SIGTERM sent)
| PID | Status | Age at Stop | Notes |
|-----|--------|-------------|-------|
| 699 | STOPPED ✅ | 3d 19h | Legacy validation runner |
| 14621 | STOPPED ✅ | 1d 17h | Legacy validation runner |

### Archived Artifacts
| Category | Files | Destination |
|----------|-------|-------------|
| **States** | state.json.2026-03-28T11-31-56-546Z.archive | `archive/2026-04-01_cleanup_legacy/states/` |
| **PIDs** | validation.pid (completed), safe_daemon.pid (stale, PID 63804) | `archive/2026-04-01_cleanup_legacy/pids/` |
| **Logs** | mini_run_*.log (3 files from Mar 30) | `archive/2026-04-01_cleanup_legacy/logs/` |
| **Temp** | Various stale temp files | `archive/2026-04-01_cleanup_legacy/temp/` |

---

## 🗂️ ALREADY ARCHIVED (Pre-existing)

These were already in archive directories, untouched:
- `/archive/2026-03-r4c-legacy/` - Multiple state backups, reports
- `/archive/2026-02-runtime-legacy/` - Legacy aborted runs
- `/tests/*/state.*.json` - Golden test files (intentionally kept in place)

---

## 📋 GIT STATUS SUMMARY

From `/data/.openclaw/workspace/forward_v5/forward_v5/`:

```
Modified (active):
  runtime/logs/mini_run_20260330_154520.log  [Current run log]
  runtime_validation/state.json              [Current run state]

Deleted (archived):
  runtime/logs/mini_run_20260330_153407.log
  runtime/logs/mini_run_5.0b_20260330_202123.log
  runtime/logs/validation_48h_20260330_171733.log
  runtime_validation/validation.pid
  runtime_validation/state.json.2026-03-28T11-31-56-546Z.archive
```

---

## 🎯 SINGLE SOURCE OF TRUTH

**For current run status, ONLY use:**
```
/data/.openclaw/workspace/forward_v5/forward_v5/runtime_validation/state.json
cat /tmp/fix_50d_pid.txt
ps -p 20027
```

**Do NOT reference:**
- Any files in `/archive/*/`
- Any files in `runtime_validation/*.archive`
- Any `/tmp/fix_*` files except the two active ones
- PID files other than `/tmp/fix_50d_pid.txt`

---

## ⚠️ SAFETY NOTES

1. **PID 20027 was NOT touched** - Runner continues normally
2. **Active state.json was NOT moved** - Still in runtime_validation/
3. **Active log /tmp/fix_50d_2h_test.log was NOT moved** - Still being written
4. **Old runners stopped gracefully** with SIGTERM
5. **Everything archived before deletion** where applicable

---

## 📊 CLEANUP VERIFICATION

- [x] Legacy runners stopped (699, 14621)
- [x] Stale PIDs archived (validation.pid, safe_daemon.pid)
- [x] Old logs archived (3 files)
- [x] Stale state archives moved
- [x] Active run preserved (PID 20027, state.json, fix_50d_2h_test.log)
- [x] Documentation created

**Workspace cleanup COMPLETE**
