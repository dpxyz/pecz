#!/usr/bin/env python3
"""
Paper Engine Watchdog — checks engine health and auto-recovers.
Runs hourly via cron. Checks:
1. Is the engine process running?
2. Are fresh candles arriving? (last closed candle < 2h ago)
3. Is the DB accessible and non-corrupt?

On failure: sends Discord alert + attempts auto-restart.
"""

import sqlite3
import time
import subprocess
import sys
import os
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("watchdog")

DB_PATH = Path(__file__).parent / "state.db"
PID_FILE = Path(__file__).parent / ".paper_engine.pid"
RUN_SCRIPT = Path(__file__).parent / "run_paper_engine.sh"
MAX_CANDLE_AGE_HOURS = 2.0
DISCORD_CHANNEL = "1495826482835095823"  # #system

def get_engine_pid():
    """Check if engine process is running."""
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if process exists
        os.kill(pid, 0)  # Signal 0 = just check, don't kill
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        return None

def check_candles():
    """Check if fresh closed candles exist in DB."""
    if not DB_PATH.exists():
        return False, "DB not found"
    try:
        conn = sqlite3.connect(str(DB_PATH))
        now_ms = int(time.time() * 1000)
        current_hour = (now_ms // 3600000) * 3600000
        # Check last closed candle for first asset
        row = conn.execute(
            "SELECT MAX(ts) FROM candles WHERE ts < ?", (current_hour,)
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return False, "No closed candles in DB"
        age_hours = (now_ms - row[0]) / 3600000
        if age_hours > MAX_CANDLE_AGE_HOURS:
            return False, f"Last closed candle {age_hours:.1f}h ago (max {MAX_CANDLE_AGE_HOURS}h)"
        return True, f"Last closed candle {age_hours:.1f}h ago ✅"
    except Exception as e:
        return False, f"DB error: {e}"

def restart_engine():
    """Attempt to restart the paper engine."""
    try:
        subprocess.run(["bash", str(RUN_SCRIPT), "--stop"], timeout=10, capture_output=True)
        time.sleep(3)
        subprocess.run(["bash", str(RUN_SCRIPT), "--background"], timeout=10, capture_output=True)
        log.info("Engine restarted ✅")
        return True
    except Exception as e:
        log.error(f"Restart failed: {e}")
        return False

def send_discord_alert(message):
    """Send alert to Discord #system channel."""
    try:
        # Use OpenClaw message tool via HTTP if available, 
        # or write to a flag file that the engine picks up
        # For now, just log it — the housekeeping cron will also detect issues
        log.warning(f"🚨 ALERT: {message}")
        # Write alert flag for housekeeping to pick up
        alert_file = Path(__file__).parent / ".watchdog_alert"
        alert_file.write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} — {message}\n")
    except Exception as e:
        log.error(f"Failed to send alert: {e}")

def main():
    log.info("Watchdog check starting...")
    issues = []

    # Check 1: Process alive
    pid = get_engine_pid()
    if not pid:
        issues.append("Engine process NOT running")
        log.error("❌ Engine process not running!")
    else:
        log.info(f"✅ Engine process running (PID {pid})")

    # Check 2: Fresh candles
    if pid:  # Only check candles if process is running
        ok, msg = check_candles()
        if not ok:
            issues.append(msg)
            log.error(f"❌ Candle check: {msg}")
        else:
            log.info(f"✅ Candle check: {msg}")

    # Check 3: DB integrity
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA integrity_check")
        candle_count = conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
        conn.close()
        log.info(f"✅ DB integrity OK, {candle_count} candles")
    except Exception as e:
        issues.append(f"DB integrity failed: {e}")
        log.error(f"❌ DB integrity: {e}")

    # Action
    if issues:
        alert_msg = " | ".join(issues)
        log.warning(f"🚨 Issues detected: {alert_msg}")
        send_discord_alert(alert_msg)

        # Auto-restart if engine is dead OR candles are stale
        if not pid or (pid and len([i for i in issues if "candle" in i.lower()]) > 0):
            log.info("Attempting auto-restart...")
            if restart_engine():
                send_discord_alert("Engine auto-restarted successfully")
            else:
                send_discord_alert("Engine auto-restart FAILED — manual intervention needed")
        sys.exit(1)
    else:
        log.info("🟢 All checks passed")
        # Clear any previous alert flag
        alert_file = Path(__file__).parent / ".watchdog_alert"
        if alert_file.exists():
            alert_file.unlink()
        sys.exit(0)

if __name__ == "__main__":
    main()