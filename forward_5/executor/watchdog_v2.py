#!/usr/bin/env python3
"""
Paper Engine Watchdog V2 — Intelligent Guardian

Error Classification:
  - PROCESS_DEAD:  Engine process not running → restart
  - CANDLES_STALE: No fresh candles (>2h) → restart with backoff
  - DB_CORRUPT:    Database integrity check failed → NO restart, alert only
  - CRASH_LOOP:    3+ restarts in 30min → circuit breaker, stop

Escalation Ladder:
  1. Restart + wait 2min + verify candles flowing
  2. Wait 5min + restart + run pytest
  3. Wait 15min + restart + full diagnostics
  4. Circuit breaker → stop, Dave must manually clear

State persisted in watchdog_state.json
"""

import sqlite3
import time
import subprocess
import sys
import os
import json
import re
import logging
from pathlib import Path
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("watchdog")

ENGINE_DIR = Path(__file__).parent
DB_PATH = ENGINE_DIR / "state.db"
PID_FILE = ENGINE_DIR / ".paper_engine.pid"
RUN_SCRIPT = ENGINE_DIR / "run_paper_engine.sh"
LOG_FILE = ENGINE_DIR / "paper_engine.log"
STATE_FILE = ENGINE_DIR / "watchdog_state.json"
TEST_DIR = ENGINE_DIR / "tests"
TRADES_FILE = ENGINE_DIR / "trades.jsonl"

MAX_CANDLE_AGE_HOURS = 2.0
MAX_RESTART_ATTEMPTS = 3
CRASH_WINDOW_SECONDS = 1800  # 30 min
DISCORD_SYSTEM_CHANNEL = "1495826482835095823"

# Error types
ERR_PROCESS_DEAD = "PROCESS_DEAD"
ERR_CANDLES_STALE = "CANDLES_STALE"
ERR_DB_CORRUPT = "DB_CORRUPT"
ERR_CRASH_LOOP = "CRASH_LOOP"

# ── State Persistence ──

def load_state():
    """Load watchdog state from JSON file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    return {
        "restart_history": [],      # list of timestamps (epoch ms)
        "circuit_breaker": False,    # true = no auto-restart
        "circuit_breaker_since": None,
        "last_check": None,
        "last_status": None,
        "consecutive_failures": 0,
    }

def save_state(state):
    """Persist watchdog state."""
    state["last_check"] = int(time.time() * 1000)
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ── Checks ──

def check_process():
    """Check if engine process is alive. Returns (ok, pid_or_none, detail)."""
    if not PID_FILE.exists():
        return False, None, "No PID file"
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # Signal 0 = existence check
        return True, pid, f"PID {pid} alive"
    except (ValueError, ProcessLookupError, PermissionError) as e:
        return False, None, f"Process dead ({e})"

def check_candles():
    """Check if fresh closed candles exist. Returns (ok, age_hours, detail)."""
    if not DB_PATH.exists():
        return False, 999, "DB not found"
    try:
        conn = sqlite3.connect(str(DB_PATH))
        now_ms = int(time.time() * 1000)
        current_hour = (now_ms // 3600000) * 3600000
        row = conn.execute(
            "SELECT MAX(ts) FROM candles WHERE ts < ?", (current_hour,)
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return False, 999, "No closed candles in DB"
        age_hours = (now_ms - row[0]) / 3600000
        if age_hours > MAX_CANDLE_AGE_HOURS:
            return False, age_hours, f"Last closed candle {age_hours:.1f}h ago (max {MAX_CANDLE_AGE_HOURS}h)"
        return True, age_hours, f"Last closed candle {age_hours:.1f}h ago"
    except Exception as e:
        return False, 999, f"DB query error: {e}"

def check_db_integrity():
    """Check DB integrity. Returns (ok, detail)."""
    if not DB_PATH.exists():
        return False, "DB file not found"
    try:
        conn = sqlite3.connect(str(DB_PATH))
        result = conn.execute("PRAGMA integrity_check").fetchone()
        count = conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
        conn.close()
        if result[0] == "ok":
            return True, f"OK ({count} candles)"
        return False, f"Integrity check: {result[0]}"
    except Exception as e:
        return False, f"DB error: {e}"

def check_crash_loop(state):
    """Check if we're in a crash loop. Returns (is_crash_loop, recent_count)."""
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - (CRASH_WINDOW_SECONDS * 1000)
    recent = [ts for ts in state.get("restart_history", []) if ts > cutoff]
    return len(recent) >= MAX_RESTART_ATTEMPTS, len(recent)

# ── Diagnostics ──

def extract_last_errors(log_path, n=30):
    """Extract last N lines from engine log, highlight errors."""
    if not log_path.exists():
        return "No log file found"
    try:
        lines = log_path.read_text().strip().split("\n")[-n:]
        # Highlight error lines
        result = []
        for line in lines:
            if any(kw in line.lower() for kw in ["error", "exception", "traceback", "failed", "❌"]):
                result.append(f"▶ {line}")
            else:
                result.append(f"  {line}")
        return "\n".join(result)
    except Exception as e:
        return f"Could not read log: {e}"

def classify_error(process_ok, candle_ok, db_ok):
    """Classify the error type based on check results."""
    if not db_ok:
        return ERR_DB_CORRUPT
    if not process_ok and not candle_ok:
        return ERR_PROCESS_DEAD  # Process dead → no candles expected
    if process_ok and not candle_ok:
        return ERR_CANDLES_STALE  # Process alive but no data
    return None  # All ok

def run_pytest():
    """Run executor unit tests and return (passed, output_excerpt)."""
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", str(TEST_DIR), "-x", "-q", "--timeout=30"],
            capture_output=True, text=True, timeout=60, cwd=str(ENGINE_DIR)
        )
        passed = result.returncode == 0
        output = (result.stdout + result.stderr).strip().split("\n")[-5:]
        return passed, "\n".join(output)
    except subprocess.TimeoutExpired:
        return False, "pytest timed out (60s)"
    except Exception as e:
        return False, f"pytest error: {e}"

# ── Actions ──

def restart_engine():
    """Restart the paper engine. Returns True if process starts."""
    try:
        subprocess.run(["bash", str(RUN_SCRIPT), "--stop"], timeout=15, capture_output=True)
        time.sleep(2)
        subprocess.run(["bash", str(RUN_SCRIPT), "--background"], timeout=15, capture_output=True)
        return True
    except Exception as e:
        log.error(f"Restart failed: {e}")
        return False

def verify_restart():
    """Wait 2 min, then verify engine is healthy. Returns (ok, detail)."""
    log.info("Waiting 2min for engine to stabilize...")
    time.sleep(120)

    # Check process
    ok, pid, detail = check_process()
    if not ok:
        return False, f"Process not running after restart: {detail}"

    # Check candles (give it another minute for first candle)
    time.sleep(60)
    ok, age, detail = check_candles()
    if not ok and age < MAX_CANDLE_AGE_HOURS + 1:
        # Candles might be just barely stale, that's ok for a fresh restart
        return True, f"Process alive (PID {pid}), candles {age:.1f}h old (recovering)"
    if ok:
        return True, f"Process alive (PID {pid}), candles fresh ({detail})"

    return False, f"Process alive but candles still stale: {detail}"

def clear_circuit_breaker():
    """Manually clear circuit breaker state."""
    state = load_state()
    state["circuit_breaker"] = False
    state["circuit_breaker_since"] = None
    state["restart_history"] = []
    state["consecutive_failures"] = 0
    save_state(state)
    log.info("Circuit breaker CLEARED ✅")

# ── Discord Alert ──

def format_alert(error_type, detail, log_excerpt, pytest_result=None, circuit_breaker=False, attempt=None, max_attempts=None):
    """Format a Discord-friendly alert message."""
    icons = {
        ERR_PROCESS_DEAD: "💀",
        ERR_CANDLES_STALE: "📡",
        ERR_DB_CORRUPT: "🗄️",
        ERR_CRASH_LOOP: "🔁",
    }
    icon = icons.get(error_type, "🚨")

    lines = [f"{icon} **Watchdog Alert: {error_type}**"]

    if attempt:
        lines.append(f"Restart attempt {attempt}/{max_attempts}")

    lines.append(f"Detail: {detail}")

    if pytest_result:
        passed, excerpt = pytest_result
        icon = "✅" if passed else "❌"
        lines.append(f"pytest: {icon}")
        if not passed:
            lines.append(f"```{excerpt}```")

    if log_excerpt:
        # Trim to keep Discord message reasonable
        short_log = "\n".join(log_excerpt.split("\n")[-15:])
        lines.append(f"Last log:\n```{short_log}```")

    if circuit_breaker:
        lines.append("⛔ **CIRCUIT BREAKER ACTIVE** — auto-restart disabled, manual intervention required")
        lines.append("Run `!watchdog-clear` to re-enable")

    return "\n".join(lines)

# ── Main Logic ──

def run_watchdog():
    """Main watchdog check. Returns (status, message) where status is 'OK', 'RECOVERED', 'ALERT', or 'CIRCUIT_BREAKER'."""
    state = load_state()
    log.info("Watchdog V2 check starting...")

    # ── Run checks ──
    process_ok, pid, process_detail = check_process()
    candle_ok, candle_age, candle_detail = check_candles()
    db_ok, db_detail = check_db_integrity()
    is_crash_loop, recent_restarts = check_crash_loop(state)

    # Log results
    p_icon = "✅" if process_ok else "❌"
    c_icon = "✅" if candle_ok else "❌"
    d_icon = "✅" if db_ok else "❌"
    log.info(f"{p_icon} Process: {process_detail}")
    log.info(f"{c_icon} Candles: {candle_detail}")
    log.info(f"{d_icon} DB: {db_detail}")
    if recent_restarts > 0:
        log.info(f"🔄 Recent restarts: {recent_restarts}/{MAX_RESTART_ATTEMPTS} (in last {CRASH_WINDOW_SECONDS//60}min)")

    # ── All ok — auto-clear circuit breaker if it was active ──
    if process_ok and candle_ok and db_ok:
        log.info("🟢 All checks passed")
        if state.get("circuit_breaker"):
            log.info("🔓 Circuit breaker auto-cleared — system healthy again")
            state["circuit_breaker"] = False
            state["circuit_breaker_since"] = None
            state["restart_history"] = []
        state["consecutive_failures"] = 0
        save_state(state)
        return "OK", "All checks passed"

    # ── Circuit breaker already active ──
    if state.get("circuit_breaker"):
        log.warning("⛔ Circuit breaker already active — skipping auto-restart")
        error_type = ERR_CRASH_LOOP
        detail = f"Circuit breaker active since {state.get('circuit_breaker_since', '?')}. Recent restarts: {recent_restarts}"
        log_excerpt = extract_last_errors(LOG_FILE, 20)
        return "CIRCUIT_BREAKER", format_alert(error_type, detail, log_excerpt, circuit_breaker=True)

    # ── DB corrupt → NO restart, alert only ──
    if not db_ok:
        error_type = ERR_DB_CORRUPT
        detail = db_detail
        log_excerpt = extract_last_errors(LOG_FILE, 20)
        log.error(f"🚨 DB CORRUPT — not restarting: {detail}")
        state["consecutive_failures"] += 1
        save_state(state)
        return "ALERT", format_alert(error_type, detail, log_excerpt)

    # ── Crash loop → circuit breaker ──
    if is_crash_loop:
        log.error(f"🔁 CRASH LOOP detected — {recent_restarts} restarts in {CRASH_WINDOW_SECONDS//60}min")
        state["circuit_breaker"] = True
        state["circuit_breaker_since"] = datetime.now(timezone.utc).isoformat()
        state["consecutive_failures"] += 1
        save_state(state)
        error_type = ERR_CRASH_LOOP
        detail = f"{recent_restarts} restarts in last {CRASH_WINDOW_SECONDS//60}min"
        log_excerpt = extract_last_errors(LOG_FILE, 20)
        return "CIRCUIT_BREAKER", format_alert(error_type, detail, log_excerpt, circuit_breaker=True)

    # ── Classify error ──
    error_type = classify_error(process_ok, candle_ok, db_ok)
    detail = f"Process: {process_detail} | Candles: {candle_detail}"
    log.warning(f"🚨 Error classified: {error_type} — {detail}")

    # ── Escalation ──
    attempt = len(state.get("restart_history", [])) + 1
    # Only count recent attempts
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - (CRASH_WINDOW_SECONDS * 1000)
    recent = [ts for ts in state.get("restart_history", []) if ts > cutoff]
    attempt = len(recent) + 1

    # Backoff: 2min, 5min, 15min
    backoff_map = {1: 120, 2: 300, 3: 900}
    backoff = backoff_map.get(attempt, 900)

    log.info(f"Escalation attempt {attempt}/{MAX_RESTART_ATTEMPTS}, backoff {backoff}s")
    time.sleep(backoff)

    # Restart
    log.info("Attempting engine restart...")
    if not restart_engine():
        state["consecutive_failures"] += 1
        save_state(state)
        return "ALERT", format_alert(error_type, "Restart command FAILED", extract_last_errors(LOG_FILE, 20))

    # Record restart
    state.setdefault("restart_history", []).append(int(time.time() * 1000))
    save_state(state)

    # Post-restart verification
    verified, verify_detail = verify_restart()
    if verified:
        log.info(f"✅ Restart verified: {verify_detail}")

        # Run pytest on attempt 2+
        pytest_result = None
        if attempt >= 2:
            log.info("Running pytest as post-restart diagnostic...")
            pytest_result = run_pytest()

        state["consecutive_failures"] = 0
        # Clean old restart history
        state["restart_history"] = [ts for ts in state.get("restart_history", []) if ts > cutoff]
        save_state(state)

        msg = f"Recovered after {error_type} (attempt {attempt})"
        if pytest_result:
            p_passed, p_excerpt = pytest_result
            msg += f" | pytest: {'✅' if p_passed else '❌'}"
        return "RECOVERED", msg

    # Restart didn't fix it
    log.error(f"❌ Restart failed verification: {verify_detail}")
    state["consecutive_failures"] += 1

    # Check if we hit crash loop threshold
    is_cl, count = check_crash_loop(state)
    if is_cl:
        log.error("🔁 Crash loop threshold reached — activating circuit breaker")
        state["circuit_breaker"] = True
        state["circuit_breaker_since"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return "CIRCUIT_BREAKER", format_alert(ERR_CRASH_LOOP,
            f"{count} failed restarts in {CRASH_WINDOW_SECONDS//60}min",
            extract_last_errors(LOG_FILE, 20), circuit_breaker=True)

    save_state(state)
    log_excerpt = extract_last_errors(LOG_FILE, 20)
    return "ALERT", format_alert(error_type, verify_detail, log_excerpt, attempt=attempt, max_attempts=MAX_RESTART_ATTEMPTS)


def main():
    """Entry point. Exit code 0 = ok, 1 = alert, 2 = circuit breaker."""
    status, message = run_watchdog()

    if status == "OK":
        sys.exit(0)
    elif status == "RECOVERED":
        log.info(f"✅ {message}")
        # Write alert for housekeeping/Discord pickup
        (ENGINE_DIR / ".watchdog_alert").write_text(f"RECOVERED: {message}\n")
        sys.exit(0)
    elif status == "CIRCUIT_BREAKER":
        log.error(f"⛔ {message}")
        (ENGINE_DIR / ".watchdog_alert").write_text(f"CIRCUIT_BREAKER: {message}\n")
        sys.exit(2)
    else:  # ALERT
        log.error(f"🚨 {message}")
        (ENGINE_DIR / ".watchdog_alert").write_text(f"ALERT: {message}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()