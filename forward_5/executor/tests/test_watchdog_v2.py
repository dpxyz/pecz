"""
Tests for Watchdog V2 — Intelligent Guardian
"""
import pytest
import json
import time
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Add executor dir to path
EXECUTOR_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(EXECUTOR_DIR))

import watchdog_v2 as wd


# ── State Persistence ──

class TestState:
    def test_load_state_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wd, "STATE_FILE", tmp_path / "ws.json")
        state = wd.load_state()
        assert state["restart_history"] == []
        assert state["circuit_breaker"] is False
        assert state["consecutive_failures"] == 0

    def test_save_and_load(self, tmp_path, monkeypatch):
        f = tmp_path / "ws.json"
        monkeypatch.setattr(wd, "STATE_FILE", f)
        state = {"restart_history": [12345], "circuit_breaker": False, "consecutive_failures": 0}
        wd.save_state(state)
        loaded = wd.load_state()
        assert loaded["restart_history"] == [12345]
        assert "last_check" in loaded

    def test_load_corrupt_file(self, tmp_path, monkeypatch):
        f = tmp_path / "ws.json"
        f.write_text("NOT JSON!!!")
        monkeypatch.setattr(wd, "STATE_FILE", f)
        state = wd.load_state()
        assert state["restart_history"] == []  # Falls back to default


# ── Process Check ──

class TestProcessCheck:
    def test_no_pid_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wd, "PID_FILE", tmp_path / "nonexistent.pid")
        ok, pid, detail = wd.check_process()
        assert ok is False
        assert pid is None
        assert "No PID" in detail

    def test_dead_pid(self, tmp_path, monkeypatch):
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("99999999")  # Very unlikely PID
        monkeypatch.setattr(wd, "PID_FILE", pid_file)
        ok, pid, detail = wd.check_process()
        assert ok is False

    def test_current_process(self, tmp_path, monkeypatch):
        pid_file = tmp_path / "test.pid"
        pid_file.write_text(str(os.getpid()))  # Our own PID is alive
        monkeypatch.setattr(wd, "PID_FILE", pid_file)
        ok, pid, detail = wd.check_process()
        assert ok is True
        assert pid == os.getpid()


# ── Candle Check ──

class TestCandleCheck:
    def test_no_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wd, "DB_PATH", tmp_path / "nonexistent.db")
        ok, age, detail = wd.check_candles()
        assert ok is False

    def test_fresh_candle(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr(wd, "DB_PATH", db_path)
        # Temporarily increase threshold so any recent candle is "fresh"
        original_max = wd.MAX_CANDLE_AGE_HOURS
        monkeypatch.setattr(wd, "MAX_CANDLE_AGE_HOURS", 10.0)
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE candles (ts INTEGER)")
        # Insert a candle from 1h ago (previous hour, definitely closed)
        ts = int(time.time() * 1000) - 3600000
        ts = (ts // 3600000) * 3600000  # Hour boundary
        conn.execute("INSERT INTO candles VALUES (?)", (ts,))
        conn.commit()
        conn.close()
        ok, age, detail = wd.check_candles()
        assert ok is True
        assert age < 10.0  # Fresh within our test threshold

    def test_stale_candle(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr(wd, "DB_PATH", db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE candles (ts INTEGER)")
        # Insert a candle from 5h ago
        ts = int(time.time() * 1000) - 18000000
        ts = (ts // 3600000) * 3600000
        conn.execute("INSERT INTO candles VALUES (?)", (ts,))
        conn.commit()
        conn.close()
        ok, age, detail = wd.check_candles()
        assert ok is False
        assert age > wd.MAX_CANDLE_AGE_HOURS


# ── DB Integrity Check ──

class TestDBIntegrity:
    def test_no_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wd, "DB_PATH", tmp_path / "nonexistent.db")
        ok, detail = wd.check_db_integrity()
        assert ok is False

    def test_healthy_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr(wd, "DB_PATH", db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE candles (ts INTEGER)")
        conn.execute("INSERT INTO candles VALUES (1)")
        conn.commit()
        conn.close()
        ok, detail = wd.check_db_integrity()
        assert ok is True
        assert "1 candles" in detail


# ── Crash Loop Detection ──

class TestCrashLoop:
    def test_no_history(self):
        state = {"restart_history": []}
        is_cl, count = wd.check_crash_loop(state)
        assert is_cl is False
        assert count == 0

    def test_below_threshold(self):
        now_ms = int(time.time() * 1000)
        state = {"restart_history": [now_ms - 60000, now_ms - 30000]}  # 2 recent
        is_cl, count = wd.check_crash_loop(state)
        assert is_cl is False
        assert count == 2

    def test_crash_loop_detected(self):
        now_ms = int(time.time() * 1000)
        state = {"restart_history": [
            now_ms - 120000,
            now_ms - 60000,
            now_ms - 30000,
        ]}  # 3 recent = threshold
        is_cl, count = wd.check_crash_loop(state)
        assert is_cl is True
        assert count == 3

    def test_old_restarts_ignored(self):
        now_ms = int(time.time() * 1000)
        state = {"restart_history": [
            now_ms - 2000000,  # 33min ago, outside window
            now_ms - 60000,
            now_ms - 30000,
        ]}
        is_cl, count = wd.check_crash_loop(state)
        assert is_cl is False  # Only 2 in window
        assert count == 2


# ── Error Classification ──

class TestErrorClassification:
    def test_db_corrupt_takes_priority(self):
        result = wd.classify_error(True, True, False)
        assert result == wd.ERR_DB_CORRUPT

    def test_process_dead_no_candles(self):
        result = wd.classify_error(False, False, True)
        assert result == wd.ERR_PROCESS_DEAD

    def test_candles_stale_process_alive(self):
        result = wd.classify_error(True, False, True)
        assert result == wd.ERR_CANDLES_STALE

    def test_all_ok(self):
        result = wd.classify_error(True, True, True)
        assert result is None


# ── Log Extraction ──

class TestLogExtraction:
    def test_no_log_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wd, "LOG_FILE", tmp_path / "nonexistent.log")
        result = wd.extract_last_errors(tmp_path / "nonexistent.log")
        assert "No log file" in result

    def test_extracts_and_highlights(self, tmp_path):
        log_path = tmp_path / "test.log"
        log_path.write_text("\n".join([
            "09:00 normal line 1",
            "09:01 normal line 2",
            "09:02 ERROR: connection timeout",
            "09:03 normal line 3",
            "09:04 Traceback (most recent call)",
            "09:05 normal line 4",
        ]))
        result = wd.extract_last_errors(log_path, 6)
        assert "▶" in result  # Error lines are highlighted
        assert "ERROR" in result

    def test_truncates_long_log(self, tmp_path):
        log_path = tmp_path / "test.log"
        lines = [f"09:{i:02d} normal line {i}" for i in range(100)]
        log_path.write_text("\n".join(lines))
        result = wd.extract_last_errors(log_path, 10)
        # Should only have last 15 lines max
        assert len(result.split("\n")) <= 17  # 15 + some margin


# ── Format Alert ──

class TestFormatAlert:
    def test_basic_alert(self):
        msg = wd.format_alert(wd.ERR_PROCESS_DEAD, "Process died", "last log line")
        assert "PROCESS_DEAD" in msg
        assert "Process died" in msg

    def test_circuit_breaker_alert(self):
        msg = wd.format_alert(wd.ERR_CRASH_LOOP, "3 restarts", "log", circuit_breaker=True)
        assert "CIRCUIT BREAKER" in msg

    def test_with_pytest_result(self):
        msg = wd.format_alert(wd.ERR_CANDLES_STALE, "No data", "log",
                             pytest_result=(False, "2 tests failed"))
        assert "❌" in msg
        assert "2 tests" in msg

    def test_with_attempt(self):
        msg = wd.format_alert(wd.ERR_PROCESS_DEAD, "Process died", "log",
                             attempt=2, max_attempts=3)
        assert "2/3" in msg


# ── Circuit Breaker Clear ──

class TestCircuitBreakerClear:
    def test_clear_resets_state(self, tmp_path, monkeypatch):
        f = tmp_path / "ws.json"
        monkeypatch.setattr(wd, "STATE_FILE", f)
        state = {
            "circuit_breaker": True,
            "circuit_breaker_since": "2026-04-21T08:00:00Z",
            "restart_history": [1, 2, 3],
            "consecutive_failures": 5,
        }
        f.write_text(json.dumps(state))
        wd.clear_circuit_breaker()
        loaded = wd.load_state()
        assert loaded["circuit_breaker"] is False
        assert loaded["restart_history"] == []
        assert loaded["consecutive_failures"] == 0


import os