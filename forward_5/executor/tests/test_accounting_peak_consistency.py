"""
Test accounting_check.py — specifically the peak_price consistency invariant.

This test ensures that check_peak_consistency() catches stale peak_price values
that would cause trailing stops to be too wide.
"""

import sqlite3
import tempfile
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from accounting_check import check_peak_consistency


def _create_db_with_position_and_candles(db_path, symbol, entry_price, peak_price,
                                          entry_ts, candle_highs):
    """Create a test DB with a position and candle data."""
    conn = sqlite3.connect(db_path)
    
    # Create tables
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
    
    # Insert position with given peak
    conn.execute(
        "INSERT INTO positions (symbol, state, entry_price, entry_time, peak_price, size) "
        "VALUES (?, 'IN_LONG', ?, ?, ?, 1.0)",
        (symbol, entry_price, entry_ts, peak_price)
    )
    
    # Insert candles with given highs
    for i, high in enumerate(candle_highs):
        ts = entry_ts + (i + 1) * 3600000  # hourly candles
        conn.execute(
            "INSERT INTO candles (symbol, ts, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, 1000)",
            (symbol, ts, high * 0.99, high, high * 0.98, high, )
        )
    
    conn.commit()
    conn.close()
    return db_path


class TestPeakConsistencyCheck:
    """Tests for check_peak_consistency() accounting invariant."""

    def test_peak_at_max_high_ok(self):
        """Peak equals max candle high — should pass."""
        db = tempfile.mktemp(suffix=".db")
        try:
            _create_db_with_position_and_candles(
                db, "BTCUSDT",
                entry_price=50000.0, peak_price=52000.0,
                entry_ts=1776000000000,
                candle_highs=[51000, 52000, 51500]  # max high = 52000
            )
            conn = sqlite3.connect(db)
            results = check_peak_consistency(conn)
            assert results[0][0] == "OK"
            conn.close()
        finally:
            os.unlink(db)

    def test_peak_above_max_high_ok(self):
        """Peak above max candle high (entry candle had higher high) — should pass."""
        db = tempfile.mktemp(suffix=".db")
        try:
            _create_db_with_position_and_candles(
                db, "BTCUSDT",
                entry_price=50000.0, peak_price=53000.0,
                entry_ts=1776000000000,
                candle_highs=[51000, 52000, 51500]  # max high = 52000 < 53000
            )
            conn = sqlite3.connect(db)
            results = check_peak_consistency(conn)
            assert results[0][0] == "OK"
            conn.close()
        finally:
            os.unlink(db)

    def test_stale_peak_critical(self):
        """Peak below max candle high — CRITICAL (stale peak bug!)."""
        db = tempfile.mktemp(suffix=".db")
        try:
            _create_db_with_position_and_candles(
                db, "DOGEUSDT",
                entry_price=0.096103, peak_price=0.096753,  # stale peak
                entry_ts=1776000000000,
                candle_highs=[0.0969, 0.0971, 0.097877]  # max high > peak!
            )
            conn = sqlite3.connect(db)
            results = check_peak_consistency(conn)
            assert results[0][0] == "CRITICAL", f"Should be CRITICAL, got {results[0]}"
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
            results = check_peak_consistency(conn)
            assert results[0][0] == "OK"
            assert "N/A" in results[0][1] or "No open" in results[0][1]
            conn.close()
        finally:
            os.unlink(db)

    def test_exact_doge_bug_scenario(self):
        """Reproduces the exact DOGE stale peak bug from Apr 24, 2026.

        Peak was stuck at 0.096753 (entry candle high) while actual candle
        highs reached 0.097877. This made the trailing stop $0.0948 instead
        of $0.0959 — 1.1 cents too wide.
        """
        db = tempfile.mktemp(suffix=".db")
        try:
            # DOGE position with stale peak
            _create_db_with_position_and_candles(
                db, "DOGEUSDT",
                entry_price=0.096103, peak_price=0.096753,  # STALE
                entry_ts=1776970800000,  # Apr 23 20:00 UTC
                candle_highs=[0.096753, 0.097221, 0.097335,
                              0.097486, 0.097587, 0.097877]
            )
            conn = sqlite3.connect(db)
            results = check_peak_consistency(conn)
            assert results[0][0] == "CRITICAL", \
                "The exact DOGE stale peak bug should be caught as CRITICAL"
            conn.close()
        finally:
            os.unlink(db)