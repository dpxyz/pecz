"""
Test accounting_check.py — position sanity invariants.

Tests check_position_sanity() which replaces the narrow check_peak_consistency()
with a broader check that validates multiple position properties against market data:
1. peak_price >= MAX(high) since entry (stale peak detection)
2. entry_price within reasonable range of ±24h candles
3. Candles are fresh (data feed alive)
"""

import sqlite3
import tempfile
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from accounting_check import check_position_sanity


def _create_db_with_position(db_path, symbol, entry_price, peak_price,
                             entry_ts, candle_highs, candle_lows=None,
                             recent_candles=True):
    """Create a test DB with a position and candle data.
    
    recent_candles: If True, use timestamps from last hour (avoids stale data WARN).
    """
    conn = sqlite3.connect(db_path)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY,
            symbol TEXT, state TEXT, entry_price REAL,
            entry_time INTEGER, peak_price REAL, size REAL,
            unrealized_pnl REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS candles (
            symbol TEXT, ts INTEGER, open REAL, high REAL,
            low REAL, close REAL, volume REAL
        )
    """)
    
    conn.execute(
        "INSERT INTO positions (symbol, state, entry_price, entry_time, peak_price, size) "
        "VALUES (?, 'IN_LONG', ?, ?, ?, 1.0)",
        (symbol, entry_price, entry_ts, peak_price)
    )
    
    for i, high in enumerate(candle_highs):
        ts = entry_ts + (i + 1) * 3600000
        low = candle_lows[i] if candle_lows else high * 0.98
        conn.execute(
            "INSERT INTO candles (symbol, ts, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, 1000)",
            (symbol, ts, high * 0.999, high, low, high, )
        )
    
    # If recent_candles, add a very recent candle to avoid stale data warning
    if recent_candles:
        import time
        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO candles (symbol, ts, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, 1000)",
            (symbol, now_ms - 30000, entry_price * 0.999, entry_price, entry_price * 0.98, entry_price)
        )
    
    conn.commit()
    conn.close()
    return db_path


class TestPositionSanityCheck:
    """Tests for check_position_sanity() — the broad position invariant."""

    def test_peak_at_max_high_ok(self):
        """Peak equals max candle high — should pass."""
        db = tempfile.mktemp(suffix=".db")
        try:
            _create_db_with_position(
                db, "BTCUSDT",
                entry_price=50000.0, peak_price=52000.0,
                entry_ts=1776000000000,
                candle_highs=[51000, 52000, 51500]
            )
            conn = sqlite3.connect(db)
            results = check_position_sanity(conn)
            assert results[0][0] == "OK"
            conn.close()
        finally:
            os.unlink(db)

    def test_peak_above_max_high_ok(self):
        """Peak above max candle high (entry candle had higher) — should pass."""
        db = tempfile.mktemp(suffix=".db")
        try:
            _create_db_with_position(
                db, "BTCUSDT",
                entry_price=50000.0, peak_price=53000.0,
                entry_ts=1776000000000,
                candle_highs=[51000, 52000, 51500]
            )
            conn = sqlite3.connect(db)
            results = check_position_sanity(conn)
            assert results[0][0] == "OK"
            conn.close()
        finally:
            os.unlink(db)

    def test_stale_peak_critical(self):
        """Peak below max candle high — CRITICAL (the bug we fixed!)."""
        db = tempfile.mktemp(suffix=".db")
        try:
            _create_db_with_position(
                db, "DOGEUSDT",
                entry_price=0.096103, peak_price=0.096753,  # stale peak
                entry_ts=1776000000000,
                candle_highs=[0.0969, 0.0971, 0.097877]  # max > peak!
            )
            conn = sqlite3.connect(db)
            results = check_position_sanity(conn)
            assert results[0][0] == "CRITICAL"
            assert "stale" in results[0][1].lower() or "peak_price" in results[0][1]
            conn.close()
        finally:
            os.unlink(db)

    def test_no_open_positions_ok(self):
        """No open positions — should return OK (N/A)."""
        db = tempfile.mktemp(suffix=".db")
        try:
            conn = sqlite3.connect(db)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY, symbol TEXT, state TEXT,
                    entry_price REAL, entry_time INTEGER, peak_price REAL, size REAL,
                    unrealized_pnl REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    symbol TEXT, ts INTEGER, open REAL, high REAL,
                    low REAL, close REAL, volume REAL
                )
            """)
            conn.commit()
            results = check_position_sanity(conn)
            assert results[0][0] == "OK"
            assert "N/A" in results[0][1] or "No open" in results[0][1]
            conn.close()
        finally:
            os.unlink(db)

    def test_exact_doge_bug_scenario(self):
        """Reproduces the exact DOGE stale peak bug from Apr 24, 2026."""
        db = tempfile.mktemp(suffix=".db")
        try:
            _create_db_with_position(
                db, "DOGEUSDT",
                entry_price=0.096103, peak_price=0.096753,  # STALE
                entry_ts=1776970800000,
                candle_highs=[0.096753, 0.097221, 0.097335,
                              0.097486, 0.097587, 0.097877]
            )
            conn = sqlite3.connect(db)
            results = check_position_sanity(conn)
            assert results[0][0] == "CRITICAL"
            conn.close()
        finally:
            os.unlink(db)

    def test_garbage_entry_price_warns(self):
        """Entry price outside ±10% of 24h candle range — should WARN."""
        db = tempfile.mktemp(suffix=".db")
        try:
            _create_db_with_position(
                db, "BTCUSDT",
                entry_price=100000.0,  # way above 24h range
                peak_price=100500.0,
                entry_ts=1776000000000,
                candle_highs=[51000, 52000, 51500],
                candle_lows=[49500, 50500, 50000]
            )
            conn = sqlite3.connect(db)
            results = check_position_sanity(conn)
            # Should have at least a WARN for garbage entry price
            severities = [r[0] for r in results]
            assert "WARN" in severities or "CRITICAL" in severities
            conn.close()
        finally:
            os.unlink(db)

    def test_stale_candle_data_warns(self):
        """Last candle > 4h old — should WARN about data feed."""
        import time
        db = tempfile.mktemp(suffix=".db")
        try:
            # Candle from 10 hours ago
            old_ts = int((time.time() - 36000) * 1000)
            _create_db_with_position(
                db, "BTCUSDT",
                entry_price=50000.0, peak_price=52000.0,
                entry_ts=old_ts - 3600000,
                candle_highs=[51000, 52000, 51500]
            )
            # Override candle timestamps to be old
            conn = sqlite3.connect(db)
            conn.execute("UPDATE candles SET ts = ?", (old_ts,))
            conn.commit()
            results = check_position_sanity(conn)
            severities = [r[0] for r in results]
            assert "WARN" in severities
            conn.close()
        finally:
            os.unlink(db)