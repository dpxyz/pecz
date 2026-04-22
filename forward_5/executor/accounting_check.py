#!/usr/bin/env python3
"""
Accounting Invariant Check — validates state.db consistency.

Runs daily via housekeeping. Checks:
1. Equity invariant: equity ≈ start_equity + sum(pnl) - sum(entry_fees)
2. No orphan positions (open for >48h)
3. Guard state consistent (timestamps match state)
4. Candle freshness (last candle < 2h ago)
5. Peak equity >= current equity

Exit codes: 0=pass, 1=warnings, 2=critical
"""

import json
import sqlite3
import sys
import time

DB_PATH = "/data/.openclaw/workspace/forward_v5/forward_5/executor/state.db"

EQUITY_TOLERANCE_EUR = 0.50
STALE_POSITION_HOURS = 48
STALE_CANDLE_HOURS = 2


def get_db():
    conn = sqlite3.connect(DB_PATH)
    return conn


def check_equity_invariant(conn):
    """equity = start - entry_fees + sum(pnl from EXIT trades)."""
    issues = []
    cur = conn.cursor()

    equity_row = cur.execute("SELECT value FROM state WHERE key='equity'").fetchone()
    start_row = cur.execute("SELECT value FROM state WHERE key='start_equity'").fetchone()

    if not equity_row or not start_row:
        return [("CRITICAL", "Missing equity or start_equity in state")]

    equity_val = float(equity_row[0])
    start_val = float(start_row[0])

    # Sum pnl from EXIT trades
    pnl_row = cur.execute("SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE event='EXIT'").fetchone()
    total_pnl = float(pnl_row[0]) if pnl_row else 0.0

    exit_count = cur.execute("SELECT COUNT(*) FROM trades WHERE event='EXIT'").fetchone()[0]

    # implied_entry_fees = start - equity + sum(pnl)
    # Should be positive (small, ~0.0054€ per trade)
    # But could be negative if equity drifted UP unexplained
    implied_fees = start_val - equity_val + total_pnl

    # Check both directions: fees should always be >= 0
    # Negative implied_fees = money appeared from nowhere
    # Very large positive = money disappeared
    if implied_fees < -EQUITY_TOLERANCE_EUR:
        issues.append(("CRITICAL",
            f"Accounting broken: implied_fees={implied_fees:.4f}€ (negative — money appeared!). "
            f"equity={equity_val:.4f}, start={start_val:.4f}, pnl={total_pnl:.4f}"))
    elif implied_fees > EQUITY_TOLERANCE_EUR * 10:
        # Large positive = many entry fees is fine, but flag if extreme
        issues.append(("WARN",
            f"Accounting drift: implied_fees={implied_fees:.4f}€ (very large). "
            f"equity={equity_val:.4f}, start={start_val:.4f}, pnl={total_pnl:.4f}"))
    elif implied_fees < -0.10:
        issues.append(("WARN",
            f"Accounting drift: implied_fees={implied_fees:.4f}€. "
            f"equity={equity_val:.4f}, start={start_val:.4f}, pnl={total_pnl:.4f}"))

    if equity_val < 0:
        issues.append(("CRITICAL", f"Equity negative: {equity_val:.4f}€"))
    if equity_val > start_val * 3:
        issues.append(("WARN", f"Equity suspiciously high: {equity_val:.4f}€"))

    if not issues:
        return [("OK",
            f"Equity={equity_val:.2f}€ | Start={start_val:.2f}€ | PnL={total_pnl:+.4f}€ | "
            f"ImpliedFees≈{implied_fees:.4f}€ | Exits={exit_count}")]
    return issues


def check_orphan_positions(conn):
    """No position should be open for >48h."""
    issues = []
    now_sec = time.time()
    stale_sec = now_sec - (STALE_POSITION_HOURS * 3600)

    positions = conn.execute(
        "SELECT symbol, entry_time FROM positions WHERE state = 'IN_LONG'"
    ).fetchall()

    for sym, entry_ms in positions:
        if entry_ms:
            entry_sec = entry_ms / 1000.0
            if entry_sec < stale_sec:
                hours = (now_sec - entry_sec) / 3600
                issues.append(("WARN", f"Stale position: {sym} open {hours:.0f}h (>{STALE_POSITION_HOURS}h)"))

    if not issues and positions:
        return [("OK", f"Open: {', '.join(p[0] for p in positions)} — all fresh")]
    elif not issues:
        return [("OK", "No open positions")]
    return issues


def check_guard_state_consistency(conn):
    """Guard state should have matching timestamps."""
    guard = conn.execute("SELECT value FROM state WHERE key='guard_state'").fetchone()
    if not guard:
        return [("OK", "No guard_state in DB yet")]

    state = guard[0]

    if state == "KILL_SWITCH":
        if not conn.execute("SELECT value FROM state WHERE key='kill_timestamp'").fetchone():
            return [("WARN", "KILL_SWITCH active but no kill_timestamp")]
    if state == "SOFT_PAUSE":
        if not conn.execute("SELECT value FROM state WHERE key='pause_timestamp'").fetchone():
            return [("WARN", "SOFT_PAUSE active but no pause_timestamp")]
    if state == "STOP_NEW":
        if not conn.execute("SELECT value FROM state WHERE key='stop_new_timestamp'").fetchone():
            return [("WARN", "STOP_NEW active but no stop_new_timestamp")]

    return [("OK", f"Guard: {state} — consistent")]


def check_candle_freshness(conn):
    """Last candle < 2h ago for each asset."""
    issues = []
    now_ms = int(time.time() * 1000)
    stale_ms = STALE_CANDLE_HOURS * 3600 * 1000
    # DB stores symbols with USDT suffix
    assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]

    for asset in assets:
        row = conn.execute("SELECT MAX(ts) FROM candles WHERE symbol = ?", (asset,)).fetchone()
        if not row or not row[0]:
            issues.append(("CRITICAL", f"No candles for {asset}"))
            continue
        last_t = int(row[0])
        if now_ms - last_t > stale_ms:
            age_h = (now_ms - last_t) / (3600 * 1000)
            issues.append(("WARN", f"{asset}: last candle {age_h:.1f}h ago"))

    if not issues:
        parts = []
        for a in assets:
            r = conn.execute("SELECT MAX(ts) FROM candles WHERE symbol = ?", (a,)).fetchone()
            if r and r[0]:
                age_m = (now_ms - int(r[0])) / (60 * 1000)
                parts.append(f"{a}({age_m:.0f}m)")
        return [("OK", f"Candles: {', '.join(parts)}")]
    return issues


def check_peak_equity(conn):
    """Peak equity >= current equity."""
    eq_row = conn.execute("SELECT value FROM state WHERE key='equity'").fetchone()
    pk_row = conn.execute("SELECT value FROM state WHERE key='peak_equity'").fetchone()

    if not eq_row or not pk_row:
        return [("CRITICAL", "Missing equity or peak_equity")]

    equity_val = float(eq_row[0])
    peak_val = float(pk_row[0])

    if peak_val < equity_val - 0.01:
        return [("CRITICAL", f"Peak({peak_val:.4f}) < Equity({equity_val:.4f}) — tracking broken!")]

    return [("OK", f"Peak={peak_val:.2f}€ ≥ Equity={equity_val:.2f}€")]


def run_checks():
    results = {}
    exit_code = 0

    try:
        conn = get_db()
    except Exception as e:
        return {"error": f"Cannot open DB: {e}"}, 2

    checks = [
        ("equity", check_equity_invariant),
        ("positions", check_orphan_positions),
        ("guard", check_guard_state_consistency),
        ("candles", check_candle_freshness),
        ("peak", check_peak_equity),
    ]

    for name, fn in checks:
        try:
            issues = fn(conn)
            results[name] = issues
            for sev, _ in issues:
                if sev == "CRITICAL":
                    exit_code = max(exit_code, 2)
                elif sev == "WARN":
                    exit_code = max(exit_code, 1)
        except Exception as e:
            results[name] = [("CRITICAL", f"Check failed: {e}")]
            exit_code = 2

    conn.close()
    return results, exit_code


def format_report(results, exit_code):
    lines = []
    for issues in results.values():
        for sev, msg in issues:
            icon = {"OK": "✅", "WARN": "⚠️", "CRITICAL": "🚨"}.get(sev, "•")
            lines.append(f"{icon} {msg}")

    status = "PASS" if exit_code == 0 else ("WARN" if exit_code == 1 else "FAIL")
    color = {"PASS": "#22c55e", "WARN": "#f59e0b", "FAIL": "#ef4444"}[status]
    header = f"🔍 **Accounting Check: {status}**"
    body = "\n".join(lines)
    return header, body, status, color


if __name__ == "__main__":
    results, ec = run_checks()
    header, body, status, color = format_report(results, ec)
    print(json.dumps({"header": header, "body": body, "status": status, "color": color, "exit_code": ec}))
    sys.exit(ec)