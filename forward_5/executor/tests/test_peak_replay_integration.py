"""
Regression test: Peak price must be updated during gap recovery (is_replay candles).

BUG HISTORY:
  - update_peak() was only called inside _evaluate_symbol(), which is skipped
    for is_replay=True candles. During crash recovery, gap replay candles did
    not update the peak price, causing trailing stops to be calculated against
    a stale peak. This could delay exits or miss stop triggers entirely.

FIX:
  - Moved update_peak() to _on_candle() BEFORE the is_replay check, so peak
    is always current for both live and replay candles.

TEST METHODOLOGY:
  - Calls _on_candle() directly with is_replay=True candles
  - Verifies that peak_price is updated even when trading signals are skipped
  - Verifies that NO new positions are opened on replay candles
  - Uses timestamps within the 2-hour max-age window so candles aren't filtered
"""

import asyncio
import json
import sqlite3
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from paper_engine import (
    PaperTradingEngine, LEVERAGE_TIERS, DEFAULT_LEVERAGE,
    SLIPPAGE_BPS, FEE_RATE, INITIAL_CAPITAL, PAPER_MODE
)
from state_manager import StateManager, GuardState
from risk_guard import RiskGuard


def _make_engine(tmpdir):
    """Create a minimal engine for testing (no Discord, no feed)."""
    db_path = os.path.join(tmpdir, "test_peak_replay.db")
    engine = PaperTradingEngine.__new__(PaperTradingEngine)
    engine.assets = ["BTCUSDT", "DOGEUSDT"]
    engine.state = StateManager(db_path=db_path)
    engine.state.set_start_equity(100.0)
    engine.state.set_equity(100.0)
    engine.state.set_state("peak_equity", 100.0)
    engine.risk = RiskGuard(engine.state)
    engine.signal = MagicMock()
    engine.reporter = MagicMock()
    engine.feed = MagicMock()
    engine._last_candle_hour = {}
    # Set engine start time to NOW so candles aren't filtered as stale
    engine._engine_start_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    engine._last_summary_hour = -1
    engine.db_path = db_path
    return engine


def _make_candle(symbol, close, high, low, ts, is_replay=False):
    """Create a candle dict matching the format from DataFeed."""
    return {
        "symbol": symbol,
        "timestamp": ts,
        "open": close * 0.999,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000.0,
        "is_replay": is_replay,
    }


class TestPeakUpdateOnReplayCandles:
    """Peak price must be updated for ALL candles, including is_replay=True.

    This is the critical regression test for the peak staleness bug.
    Without the fix, peak_price would remain stuck at entry value during
    gap recovery, making trailing stops dangerously wide.
    """

    def test_replay_candle_updates_peak(self):
        """A replay candle with a higher high MUST update peak_price."""
        tmpdir = tempfile.mkdtemp()
        engine = _make_engine(tmpdir)
        now = datetime.now(timezone.utc)

        # Open a LONG position with initial peak at entry
        ts = int(now.timestamp() * 1000)
        engine.state.open_position("BTCUSDT", 50000.0, ts, 0.002, "RUNNING")
        engine.state.update_peak("BTCUSDT", 50000.0)

        # Simulate a replay candle with high = 51000 (higher than current peak)
        replay_candle = _make_candle(
            "BTCUSDT", close=50800.0, high=51000.0, low=50500.0,
            ts=ts + 3600000,  # 1 hour later (within 2h window)
            is_replay=True
        )

        asyncio.new_event_loop().run_until_complete(
            engine._on_candle("BTCUSDT", replay_candle)
        )

        pos = engine.state.get_open_position("BTCUSDT")
        assert pos["peak_price"] == 51000.0, \
            f"Peak should be 51000 (replay candle high), got {pos['peak_price']}"

    def test_replay_candle_does_not_open_new_position(self):
        """A replay candle must NOT trigger new entries."""
        tmpdir = tempfile.mkdtemp()
        engine = _make_engine(tmpdir)
        now = datetime.now(timezone.utc)

        # No open position initially
        assert engine.state.get_open_position("BTCUSDT") is None

        replay_candle = _make_candle(
            "BTCUSDT", close=50000.0, high=50200.0, low=49800.0,
            ts=int(now.timestamp() * 1000),
            is_replay=True
        )

        asyncio.new_event_loop().run_until_complete(
            engine._on_candle("BTCUSDT", replay_candle)
        )

        # NO new position should be opened on replay candle
        pos = engine.state.get_open_position("BTCUSDT")
        assert pos is None, "Replay candle must NOT open new positions"

    def test_peak_never_decreases(self):
        """Peak price must be monotonically increasing — it never decreases."""
        tmpdir = tempfile.mkdtemp()
        engine = _make_engine(tmpdir)
        now = datetime.now(timezone.utc)
        ts = int(now.timestamp() * 1000)

        engine.state.open_position("BTCUSDT", 50000.0, ts, 0.002, "RUNNING")
        engine.state.update_peak("BTCUSDT", 52000.0)

        # Live candle with lower high — peak should stay at 52000
        lower_candle = _make_candle(
            "BTCUSDT", close=50500.0, high=51000.0, low=50000.0,
            ts=ts + 3600000,
            is_replay=False
        )

        asyncio.new_event_loop().run_until_complete(
            engine._on_candle("BTCUSDT", lower_candle)
        )

        pos = engine.state.get_open_position("BTCUSDT")
        assert pos["peak_price"] == 52000.0, \
            f"Peak should stay at 52000 (not decrease to 51000), got {pos['peak_price']}"

    def test_gap_recovery_peak_sequence(self):
        """Simulate full gap recovery: 5 replay candles, then 1 live candle.

        Peak must track the highest high across ALL candles (replay + live).
        This is the EXACT scenario that caused the original bug.
        """
        tmpdir = tempfile.mkdtemp()
        engine = _make_engine(tmpdir)
        now = datetime.now(timezone.utc)
        base_ts = int(now.timestamp() * 1000)

        # Open position at entry price 50000
        engine.state.open_position("BTCUSDT", 50000.0, base_ts, 0.002, "RUNNING")
        engine.state.update_peak("BTCUSDT", 50000.0)

        # Simulate gap recovery: 5 hourly replay candles with rising highs
        # Use timestamps starting 1h ago so they're within the 2h max-age window
        replay_highs = [50500, 51000, 51800, 52200, 52500]
        for i, high in enumerate(replay_highs):
            # Start from 1h ago, each candle 1h apart — all within 2h window
            candle_ts = base_ts + (i + 1) * 3600000  # future timestamps
            candle = _make_candle(
                "BTCUSDT",
                close=high - 200,
                high=float(high),
                low=float(high) - 500,
                ts=candle_ts,
                is_replay=True
            )
            asyncio.new_event_loop().run_until_complete(
                engine._on_candle("BTCUSDT", candle)
            )

        # After all replay candles, peak should be at the highest high
        pos = engine.state.get_open_position("BTCUSDT")
        assert pos["peak_price"] == 52500.0, \
            f"After replay sequence, peak should be 52500, got {pos['peak_price']}"

        # Live candle with a lower high — peak stays at 52500
        live_candle = _make_candle(
            "BTCUSDT",
            close=52300.0,
            high=52400.0,
            low=52100.0,
            ts=base_ts + 6 * 3600000,
            is_replay=False
        )
        asyncio.new_event_loop().run_until_complete(
            engine._on_candle("BTCUSDT", live_candle)
        )

        pos = engine.state.get_open_position("BTCUSDT")
        assert pos["peak_price"] == 52500.0, \
            f"Peak should stay at 52500 (never decreases), got {pos['peak_price']}"

    def test_trailing_stop_uses_correct_peak_after_recovery(self):
        """Trailing stop must be calculated against the CORRECT (highest) peak,
        not a stale entry-time peak.

        This was the original impact of the bug: DOGE LONG @ 0.0961 with
        stale peak at 0.0968 instead of actual peak 0.0979.
        Correct stop: 0.0979 × 0.98 = 0.0959
        Buggy stop:   0.0968 × 0.98 = 0.0948 (1.1¢ too low)
        """
        tmpdir = tempfile.mkdtemp()
        engine = _make_engine(tmpdir)
        now = datetime.now(timezone.utc)
        base_ts = int(now.timestamp() * 1000)

        # Open DOGE position (similar to the real bug)
        engine.state.open_position("DOGEUSDT", 0.096103, base_ts, 254.68, "RUNNING")
        # Initial peak = entry candle high (what it WAS before the fix)
        engine.state.update_peak("DOGEUSDT", 0.096753)

        # Replay candles push price higher (the actual scenario from Apr 23-24)
        replay_highs = [0.096900, 0.097100, 0.097400, 0.097700, 0.097877]
        for i, high in enumerate(replay_highs):
            candle = _make_candle(
                "DOGEUSDT",
                close=high - 0.0002,
                high=high,
                low=high - 0.001,
                ts=base_ts + (i + 1) * 3600000,
                is_replay=True
            )
            asyncio.new_event_loop().run_until_complete(
                engine._on_candle("DOGEUSDT", candle)
            )

        pos = engine.state.get_open_position("DOGEUSDT")

        # CORRECT: peak should be 0.097877 (highest replay candle high)
        # BUGGY (before fix): peak would be stuck at 0.096753 (entry candle high)
        assert pos["peak_price"] == pytest.approx(0.097877, abs=0.0001), \
            f"Peak should track highest replay high (0.097877), got {pos['peak_price']:.6f}"

        # CORRECT trailing stop: 0.097877 × 0.98 = 0.095919
        # BUGGY trailing stop: 0.096753 × 0.98 = 0.094818
        # Difference: 0.095919 - 0.094818 = 0.001101 (about 1.1 cents)
        correct_stop = pos["peak_price"] * 0.98
        buggy_stop = 0.096753 * 0.98
        assert correct_stop > buggy_stop, \
            f"Correct stop ({correct_stop:.6f}) must be higher than buggy stop ({buggy_stop:.6f})"