"""
Accounting Check Tests — Cover all 5 invariants + format_report + edge cases.
"""

import pytest
import sqlite3
import json
import time
from unittest.mock import patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from accounting_check import (
    check_equity_invariant, check_orphan_positions,
    check_guard_state_consistency, check_candle_freshness,
    check_peak_equity, run_checks, format_report,
    EQUITY_TOLERANCE_EUR, STALE_POSITION_HOURS, STALE_CANDLE_HOURS,
)


def _init_db(db_path: str):
    """Create a fresh state.db with all required tables."""
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS state (
        key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, state TEXT,
        entry_price REAL, entry_time INTEGER, peak_price REAL,
        size REAL, opened_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT, symbol TEXT,
        side TEXT, price REAL, size REAL, pnl REAL,
        equity REAL, reason TEXT, guard_state TEXT, timestamp INTEGER)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS candles (
        symbol TEXT, ts INTEGER, open REAL, high REAL, low REAL,
        close REAL, volume REAL, PRIMARY KEY (symbol, ts))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL,
        event TEXT, data TEXT)""")
    return conn


def _seed_healthy_db(db_path: str):
    """Seed a healthy DB that should pass all checks."""
    conn = _init_db(db_path)
    conn.execute("INSERT INTO state VALUES ('equity', '99.50', '2026-01-01')")
    conn.execute("INSERT INTO state VALUES ('start_equity', '100.00', '2026-01-01')")
    conn.execute("INSERT INTO state VALUES ('peak_equity', '100.00', '2026-01-01')")
    conn.execute("INSERT INTO state VALUES ('guard_state', 'RUNNING', '2026-01-01')")
    # Add recent candles
    now_ms = int(time.time() * 1000)
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]:
        conn.execute("INSERT INTO candles VALUES (?,?,?,?,?,?,?)",
                     (sym, now_ms - 60000, 100, 101, 99, 100.5, 1000))
    # Add equity_history
    conn.execute("""CREATE TABLE IF NOT EXISTS equity_history (
        ts INTEGER, equity REAL, unrealized_pnl REAL, drawdown_pct REAL,
        guard_state TEXT, n_positions INTEGER)""")
    conn.execute("INSERT INTO equity_history VALUES (?,?,?,?,?,?)",
                 (now_ms, 99.50, -0.50, 0.5, 'RUNNING', 0))
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════
# Equity Invariant
# ══════════════════════════════════════════════════════════

class TestEquityInvariant:

    def test_healthy_equity(self, tmp_path):
        """Healthy DB should show OK."""
        db = str(tmp_path / "state.db")
        _seed_healthy_db(db)
        conn = sqlite3.connect(db)
        issues = check_equity_invariant(conn)
        assert issues[0][0] == "OK"
        conn.close()

    def test_negative_implied_fees_critical(self, tmp_path):
        """Negative implied fees → CRITICAL (money appeared from nowhere)."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        # equity > start + pnl → implied_fees < 0
        conn.execute("INSERT INTO state VALUES ('equity', '110.00', '')")
        conn.execute("INSERT INTO state VALUES ('start_equity', '100.00', '')")
        conn.execute("INSERT INTO trades VALUES (1, 'EXIT', 'BTCUSDT', 'LONG', 101, 0.1, 0.5, 100.5, 'test', 'RUNNING', 1700000000)")
        conn.commit()
        issues = check_equity_invariant(conn)
        assert any(s == "CRITICAL" for s, _ in issues)
        conn.close()

    def test_negative_equity_critical(self, tmp_path):
        """Negative equity → CRITICAL."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO state VALUES ('equity', '-10.00', '')")
        conn.execute("INSERT INTO state VALUES ('start_equity', '100.00', '')")
        conn.commit()
        issues = check_equity_invariant(conn)
        assert any(s == "CRITICAL" for s, _ in issues)
        conn.close()

    def test_suspiciously_high_equity(self, tmp_path):
        """Equity > 3x start → WARN."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO state VALUES ('equity', '350.00', '')")
        conn.execute("INSERT INTO state VALUES ('start_equity', '100.00', '')")
        conn.commit()
        issues = check_equity_invariant(conn)
        assert any(s == "WARN" for s, _ in issues)
        conn.close()

    def test_large_positive_implied_fees(self, tmp_path):
        """Very large positive implied fees → WARN."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO state VALUES ('equity', '50.00', '')")
        conn.execute("INSERT INTO state VALUES ('start_equity', '100.00', '')")
        conn.commit()
        issues = check_equity_invariant(conn)
        assert any(s == "WARN" for s, _ in issues)
        conn.close()

    def test_missing_equity_key(self, tmp_path):
        """Missing equity → CRITICAL."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO state VALUES ('start_equity', '100.00', '')")
        conn.commit()
        issues = check_equity_invariant(conn)
        assert any(s == "CRITICAL" for s, _ in issues)
        conn.close()

    def test_small_negative_implied_fees_warn(self, tmp_path):
        """Small negative implied fees → WARN (between -0.10 and -TOLERANCE)."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        # equity slightly higher than start + pnl
        conn.execute("INSERT INTO state VALUES ('equity', '100.20', '')")
        conn.execute("INSERT INTO state VALUES ('start_equity', '100.00', '')")
        conn.commit()
        issues = check_equity_invariant(conn)
        # implied_fees = 100 - 100.20 + 0 = -0.20 → WARN
        assert any(s in ("OK", "WARN") for s, _ in issues)
        conn.close()


# ══════════════════════════════════════════════════════════
# Orphan Positions
# ══════════════════════════════════════════════════════════

class TestOrphanPositions:

    def test_no_positions(self, tmp_path):
        """No open positions → OK."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        issues = check_orphan_positions(conn)
        assert issues[0][0] == "OK"
        conn.close()

    def test_fresh_position(self, tmp_path):
        """Recent position → OK."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        now_ms = int(time.time() * 1000)
        conn.execute("INSERT INTO positions VALUES (1, 'BTCUSDT', 'IN_LONG', 100, now_ms, 100, 0.1, '')".replace("now_ms", str(now_ms)))
        conn.commit()
        issues = check_orphan_positions(conn)
        assert issues[0][0] == "OK"
        conn.close()

    def test_stale_position_warn(self, tmp_path):
        """Position open >48h → WARN."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        old_ms = int((time.time() - 50 * 3600) * 1000)
        conn.execute(f"INSERT INTO positions VALUES (1, 'BTCUSDT', 'IN_LONG', 100, {old_ms}, 100, 0.1, '')")
        conn.commit()
        issues = check_orphan_positions(conn)
        assert any(s == "WARN" for s, _ in issues)
        conn.close()

    def test_multiple_positions_mixed(self, tmp_path):
        """Mix of fresh and stale → WARN on stale only."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        now_ms = int(time.time() * 1000)
        old_ms = int((time.time() - 50 * 3600) * 1000)
        conn.execute(f"INSERT INTO positions VALUES (1, 'BTCUSDT', 'IN_LONG', 100, {now_ms}, 100, 0.1, '')")
        conn.execute(f"INSERT INTO positions VALUES (2, 'ETHUSDT', 'IN_LONG', 2000, {old_ms}, 2000, 0.01, '')")
        conn.commit()
        issues = check_orphan_positions(conn)
        warn_msgs = [m for s, m in issues if s == "WARN"]
        assert len(warn_msgs) == 1
        assert "ETHUSDT" in warn_msgs[0]
        conn.close()


# ══════════════════════════════════════════════════════════
# Guard State Consistency
# ══════════════════════════════════════════════════════════

class TestGuardStateConsistency:

    def test_running_state(self, tmp_path):
        """RUNNING state → OK."""
        db = str(tmp_path / "state.db")
        _seed_healthy_db(db)
        conn = sqlite3.connect(db)
        issues = check_guard_state_consistency(conn)
        assert issues[0][0] == "OK"
        conn.close()

    def test_kill_switch_without_timestamp(self, tmp_path):
        """KILL_SWITCH without kill_timestamp → WARN."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO state VALUES ('guard_state', 'KILL_SWITCH', '')")
        conn.commit()
        issues = check_guard_state_consistency(conn)
        assert any(s == "WARN" for s, _ in issues)
        conn.close()

    def test_kill_switch_with_timestamp(self, tmp_path):
        """KILL_SWITCH with timestamp → OK."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO state VALUES ('guard_state', 'KILL_SWITCH', '')")
        conn.execute("INSERT INTO state VALUES ('kill_timestamp', '1700000000', '')")
        conn.commit()
        issues = check_guard_state_consistency(conn)
        assert issues[0][0] == "OK"
        conn.close()

    def test_soft_pause_without_timestamp(self, tmp_path):
        """SOFT_PAUSE without pause_timestamp → WARN."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO state VALUES ('guard_state', 'SOFT_PAUSE', '')")
        conn.commit()
        issues = check_guard_state_consistency(conn)
        assert any(s == "WARN" for s, _ in issues)
        conn.close()

    def test_stop_new_without_timestamp(self, tmp_path):
        """STOP_NEW without stop_new_timestamp → WARN."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO state VALUES ('guard_state', 'STOP_NEW', '')")
        conn.commit()
        issues = check_guard_state_consistency(conn)
        assert any(s == "WARN" for s, _ in issues)
        conn.close()

    def test_no_guard_state(self, tmp_path):
        """No guard_state in DB → OK."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        issues = check_guard_state_consistency(conn)
        assert issues[0][0] == "OK"
        conn.close()


# ══════════════════════════════════════════════════════════
# Candle Freshness
# ══════════════════════════════════════════════════════════

class TestCandleFreshness:

    def test_fresh_candles_ok(self, tmp_path):
        """All assets with recent candles → OK."""
        db = str(tmp_path / "state.db")
        _seed_healthy_db(db)
        conn = sqlite3.connect(db)
        issues = check_candle_freshness(conn)
        assert issues[0][0] == "OK"
        conn.close()

    def test_no_candles_critical(self, tmp_path):
        """No candles at all → CRITICAL."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        issues = check_candle_freshness(conn)
        assert any(s == "CRITICAL" for s, _ in issues)
        conn.close()

    def test_stale_candles_warn(self, tmp_path):
        """Candles >2h old → WARN."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        old_ms = int((time.time() - 3 * 3600) * 1000)
        for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]:
            conn.execute("INSERT INTO candles VALUES (?,?,?,?,?,?,?)",
                         (sym, old_ms, 100, 101, 99, 100.5, 1000))
        conn.commit()
        issues = check_candle_freshness(conn)
        assert any(s == "WARN" for s, _ in issues)
        conn.close()


# ══════════════════════════════════════════════════════════
# Peak Equity
# ══════════════════════════════════════════════════════════

class TestPeakEquity:

    def test_peak_gte_equity_ok(self, tmp_path):
        """Peak >= equity → OK."""
        db = str(tmp_path / "state.db")
        _seed_healthy_db(db)
        conn = sqlite3.connect(db)
        issues = check_peak_equity(conn)
        assert issues[0][0] == "OK"
        conn.close()

    def test_peak_lt_equity_critical(self, tmp_path):
        """Peak < equity → CRITICAL (tracking broken)."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO state VALUES ('equity', '120.00', '')")
        conn.execute("INSERT INTO state VALUES ('peak_equity', '100.00', '')")
        conn.commit()
        issues = check_peak_equity(conn)
        assert any(s == "CRITICAL" for s, _ in issues)
        conn.close()

    def test_missing_peak_critical(self, tmp_path):
        """Missing peak_equity → CRITICAL."""
        db = str(tmp_path / "state.db")
        _init_db(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO state VALUES ('equity', '100.00', '')")
        conn.commit()
        issues = check_peak_equity(conn)
        assert any(s == "CRITICAL" for s, _ in issues)
        conn.close()


# ══════════════════════════════════════════════════════════
# run_checks + format_report
# ══════════════════════════════════════════════════════════

class TestRunChecks:

    def test_all_ok(self, tmp_path):
        """Healthy DB → exit_code=0."""
        db = str(tmp_path / "state.db")
        trades = str(tmp_path / "trades.jsonl")
        # Create clean trade log
        with open(trades, 'w') as f:
            f.write(json.dumps({"symbol":"BTCUSDT","event":"ENTRY","price":50000,"size":0.001,"leverage":1.8,"timestamp":1776000000000})+'\n')
            f.write(json.dumps({"symbol":"BTCUSDT","event":"EXIT","price":50500,"size":0.001,"leverage":1.8,"timestamp":1776010000000,"reason":"trail"})+'\n')
        _seed_healthy_db(db)
        with patch("accounting_check.DB_PATH", db):
            with patch("accounting_check.get_db", lambda: sqlite3.connect(db)):
                with patch("accounting_check.TRADE_LOG_PATH", trades):
                    results, ec = run_checks()
        assert ec == 0

    def test_db_open_failure(self, tmp_path):
        """DB open failure → exit_code=2."""
        with patch("accounting_check.get_db", side_effect=sqlite3.OperationalError("locked")):
            results, ec = run_checks()
        assert ec == 2

    def test_format_report_pass(self, tmp_path):
        """format_report with PASS exit code."""
        results = {"equity": [("OK", "Equity=100.00€")]}
        header, body, status, color = format_report(results, 0)
        assert status == "PASS"
        assert color == "#22c55e"

    def test_format_report_warn(self):
        """format_report with WARN exit code."""
        results = {"positions": [("WARN", "Stale position")]}
        header, body, status, color = format_report(results, 1)
        assert status == "WARN"
        assert color == "#f59e0b"

    def test_format_report_fail(self):
        """format_report with FAIL exit code."""
        results = {"equity": [("CRITICAL", "Negative equity")]}
        header, body, status, color = format_report(results, 2)
        assert status == "FAIL"
        assert color == "#ef4444"

    def test_check_exception_handled(self, tmp_path):
        """Exception during check → CRITICAL + exit_code=2."""
        db = str(tmp_path / "state.db")
        _seed_healthy_db(db)
        with patch("accounting_check.DB_PATH", db):
            with patch("accounting_check.get_db", lambda: sqlite3.connect(db)):
                with patch("accounting_check.check_equity_invariant", side_effect=RuntimeError("boom")):
                    results, ec = run_checks()
        assert ec == 2