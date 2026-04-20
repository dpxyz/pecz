"""
Executor V1 — Discord Reporter Tests

Covers:
- BUG 3 REGRESSION: format_hourly_status shows ALL 6 assets (not just BTC/ETH)
- Format functions return (header, body, color) tuples
- Color constants are correct
"""

import os
import tempfile
import pytest

from state_manager import StateManager, GuardState
from discord_reporter import (
    format_hourly_status,
    format_entry,
    format_exit,
    format_entry_blocked,
    format_guard_change,
    COLOR_GREEN, COLOR_RED, COLOR_AMBER, COLOR_BLUE, COLOR_GRAY,
)


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def sm(db_path):
    s = StateManager(db_path=db_path)
    s.set_start_equity(100.0)
    s.set_equity(100.0)
    s.set_state("peak_equity", 100.0)
    s.set_state("daily_pnl", 0.0)
    s.set_state("cl_count", 0)
    return s


class TestBug3Regression_AllAssetsInStatus:
    """BUG 3 REGRESSION: Hourly status must show ALL 6 assets.

    Previously only BTC and ETH positions were shown.
    SOL, AVAX, DOGE, ADA were invisible.
    """

    def test_no_positions_shows_none(self, sm):
        header, body, color = format_hourly_status(sm)
        assert "None" in body

    def test_btc_position_shown(self, sm):
        sm.open_position("BTCUSDT", 85000.0, 1713500000, 0.001, "RUNNING")
        header, body, color = format_hourly_status(sm)
        assert "BTC" in body

    def test_eth_position_shown(self, sm):
        sm.open_position("ETHUSDT", 3000.0, 1713500000, 0.01, "RUNNING")
        header, body, color = format_hourly_status(sm)
        assert "ETH" in body

    def test_sol_position_shown(self, sm):
        sm.open_position("SOLUSDT", 150.0, 1713500000, 0.1, "RUNNING")
        header, body, color = format_hourly_status(sm)
        assert "SOL" in body

    def test_avax_position_shown(self, sm):
        sm.open_position("AVAXUSDT", 25.0, 1713500000, 1.0, "RUNNING")
        header, body, color = format_hourly_status(sm)
        assert "AVAX" in body

    def test_doge_position_shown(self, sm):
        sm.open_position("DOGEUSDT", 0.18, 1713500000, 100.0, "RUNNING")
        header, body, color = format_hourly_status(sm)
        assert "DOGE" in body

    def test_ada_position_shown(self, sm):
        sm.open_position("ADAUSDT", 0.45, 1713500000, 50.0, "RUNNING")
        header, body, color = format_hourly_status(sm)
        assert "ADA" in body

    def test_multiple_positions_shown(self, sm):
        sm.open_position("BTCUSDT", 85000.0, 1713500000, 0.001, "RUNNING")
        sm.open_position("SOLUSDT", 150.0, 1713500000, 0.1, "RUNNING")
        sm.open_position("DOGEUSDT", 0.18, 1713500000, 100.0, "RUNNING")
        header, body, color = format_hourly_status(sm)
        assert "BTC" in body
        assert "SOL" in body
        assert "DOGE" in body


class TestFormatFunctions:
    """All format functions take event dicts and return (header, body, color) tuples."""

    def test_format_entry(self):
        result = format_entry({"symbol": "BTCUSDT", "price": 85000, "size": 0.001})
        assert len(result) == 3

    def test_format_exit_winning(self):
        result = format_exit({"symbol": "BTCUSDT", "price": 86000, "pnl": 1.5, "reason": "trailing_stop"})
        assert len(result) == 3

    def test_format_exit_losing(self):
        _, _, color = format_exit({"symbol": "BTCUSDT", "price": 84000, "pnl": -2.0, "reason": "stop_loss"})
        assert color == COLOR_RED

    def test_format_entry_blocked_uses_amber(self):
        """BUG fix: Entry blocked = AMBER (caution), not RED (danger)."""
        _, _, color = format_entry_blocked({"symbol": "BTCUSDT", "reason": "Daily loss 6%"})
        assert color == COLOR_AMBER

    def test_format_guard_change(self):
        result = format_guard_change({"old_state": "RUNNING", "new_state": "STOP_NEW", "reason": "Daily loss 6%"})
        assert len(result) == 3


class TestColorConstants:
    def test_green(self):
        assert COLOR_GREEN == "#22c55e"

    def test_red(self):
        assert COLOR_RED == "#ef4444"

    def test_amber(self):
        assert COLOR_AMBER == "#f59e0b"

    def test_blue(self):
        assert COLOR_BLUE == "#3b82f6"

    def test_gray(self):
        assert COLOR_GRAY == "#6b7280"