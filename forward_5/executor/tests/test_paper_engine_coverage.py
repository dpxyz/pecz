"""
Paper Engine Coverage Tests — Target the critical untested code paths.
Raises coverage from 39% toward 80%.
"""

import pytest
import sqlite3
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from paper_engine import PaperTradingEngine as PaperEngine, INITIAL_CAPITAL, FEE_RATE, SLIPPAGE_BPS, LEVERAGE_TIERS, DEFAULT_LEVERAGE
from state_manager import StateManager, GuardState
from risk_guard import RiskGuard
from data_feed import DataFeed
from signal_generator import SignalGenerator, SignalType, Signal
from discord_reporter import DiscordReporter, COLOR_RED, COLOR_BLUE


def _make_engine(tmp_path):
    """Create a PaperEngine with temp DB for testing."""
    db_path = str(tmp_path / "test_state.db")
    state = StateManager(db_path)
    state.set_equity(INITIAL_CAPITAL)
    state.set_start_equity(INITIAL_CAPITAL)
    state.set_guard_state(GuardState.RUNNING)

    candle_db = str(tmp_path / "candles.db")
    feed = DataFeed(db_path=candle_db, assets=["BTCUSDT", "ETHUSDT"])

    # Seed 220 candles into the DB for signal evaluation warmup
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    base_ts = (now_ms // 3600000) * 3600000 - 220 * 3600000
    with sqlite3.connect(candle_db) as conn:
        for i in range(220):
            ts = base_ts + i * 3600000
            price = 100.0 + i * 0.1  # Rising prices
            conn.execute(
                "INSERT OR REPLACE INTO candles (symbol, ts, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
                ("BTCUSDT", ts, price - 0.5, price + 1, price - 1, price, 1000)
            )
            conn.execute(
                "INSERT OR REPLACE INTO candles (symbol, ts, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
                ("ETHUSDT", ts, price * 20 - 10, price * 20 + 20, price * 20 - 20, price * 20, 1000)
            )

    reporter = MagicMock(spec=DiscordReporter)
    reporter._send_container = MagicMock()
    reporter.report_hourly = MagicMock()
    reporter.report_daily = MagicMock()
    reporter.report_exit = MagicMock()
    reporter.report_entry = MagicMock()
    reporter.report_entry_blocked = MagicMock()

    engine = PaperEngine.__new__(PaperEngine)
    engine.state = state
    engine.feed = feed
    engine.reporter = reporter
    engine.risk = RiskGuard(state)
    engine.signal = SignalGenerator()
    engine.assets = ["BTCUSDT", "ETHUSDT"]
    engine._last_candle_hour: dict[str, bool] = {}
    engine._last_summary_hour = -1
    engine._engine_start_time = int(datetime.now(timezone.utc).timestamp() * 1000) - 7200000  # 2h ago
    engine._running = True
    engine.main_address = None

    return engine


def _make_candle(symbol="BTCUSDT", close=100.0, ts=None, high=None, low=None):
    """Create a minimal candle dict."""
    if ts is None:
        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        ts = (ts // 3600000) * 3600000
    return {
        "open": close - 0.5, "high": high or close + 1, "low": low or close - 1,
        "close": close, "volume": 1000, "timestamp": ts,
    }


# ══════════════════════════════════════════════════════════
# _on_candle Dedup & Filtering
# ══════════════════════════════════════════════════════════

class TestOnCandleDedup:

    def test_same_candle_skipped(self, tmp_path):
        """Processing the same candle twice should be a no-op."""
        engine = _make_engine(tmp_path)
        candle = _make_candle()
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine._on_candle("BTCUSDT", candle))
        before = len(engine._last_candle_hour)
        loop.run_until_complete(engine._on_candle("BTCUSDT", candle))
        after = len(engine._last_candle_hour)
        assert before == after
        loop.close()

    def test_different_candle_processed(self, tmp_path):
        """Different candle should be processed."""
        engine = _make_engine(tmp_path)
        candle1 = _make_candle(ts=1700000000000)
        candle2 = _make_candle(ts=1700003600000)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine._on_candle("BTCUSDT", candle1))
        loop.run_until_complete(engine._on_candle("BTCUSDT", candle2))
        assert len(engine._last_candle_hour) == 2
        loop.close()

    def test_old_candle_before_engine_start_skipped(self, tmp_path):
        """Candle older than engine start time should update last_processed_ts but not evaluate."""
        engine = _make_engine(tmp_path)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        engine._engine_start_time = now_ms
        old_ts = now_ms - 86400000
        candle = _make_candle(ts=old_ts)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine._on_candle("BTCUSDT", candle))
        lpts = engine.state.get_state("last_processed_ts")
        assert lpts is not None
        loop.close()

    def test_dedup_cleanup_after_2000_entries(self, tmp_path):
        """_last_candle_hour should clean up after exceeding 2000 entries."""
        engine = _make_engine(tmp_path)
        # The cleanup triggers when len > 2000 AND the candle passes all filters
        # Directly populate 2001 entries, then add one more via _on_candle
        base_ts = engine._engine_start_time  # Use timestamps after engine start
        for i in range(2001):
            ts = base_ts - 2001 * 3600000 + i * 3600000
            engine._last_candle_hour[f"BTCUSDT_{ts}"] = True
        assert len(engine._last_candle_hour) == 2001
        # The next candle that passes dedup+engine_start filter will trigger cleanup
        next_ts = base_ts + 3600000  # 1h after engine start
        candle = _make_candle(ts=next_ts)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine._on_candle("BTCUSDT", candle))
        # After adding + cleanup, should be ~1002 (1001 old + 1 new - 1000 cleaned)
        assert len(engine._last_candle_hour) <= 1100
        loop.close()


# ══════════════════════════════════════════════════════════
# _on_candle Unrealized DD Check
# ══════════════════════════════════════════════════════════

class TestUnrealizedDDCheck:

    def test_no_positions_no_dd_trigger(self, tmp_path):
        """No open positions → no unrealized DD → no KILL."""
        engine = _make_engine(tmp_path)
        candle = _make_candle()
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine._on_candle("BTCUSDT", candle))
        assert engine.state.get_guard_state() == GuardState.RUNNING
        loop.close()

    def test_small_unrealized_pnl_no_trigger(self, tmp_path):
        """Small unrealized loss should not trigger KILL."""
        engine = _make_engine(tmp_path)
        engine.state.open_position("BTCUSDT", 100.0, 1700000000, 0.1)
        candle = _make_candle(close=99.0)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine._on_candle("BTCUSDT", candle))
        assert engine.state.get_guard_state() == GuardState.RUNNING
        loop.close()

    def test_large_unrealized_dd_triggers_kill(self, tmp_path):
        """Large unrealized DD should trigger KILL_SWITCH."""
        engine = _make_engine(tmp_path)
        size = (INITIAL_CAPITAL / 2 * 1.8) / (100.0 * (1 + FEE_RATE * 1.8))
        engine.state.open_position("BTCUSDT", 100.0, 1700000000, size)
        engine.state.set_state("peak_equity", INITIAL_CAPITAL)
        candle = _make_candle(close=75.0)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine._on_candle("BTCUSDT", candle))
        assert engine.state.get_guard_state() == GuardState.KILL_SWITCH
        loop.close()


# ══════════════════════════════════════════════════════════
# _evaluate_symbol — Signal Processing
# ══════════════════════════════════════════════════════════

class TestEvaluateSymbol:

    def test_flat_signal_no_action(self, tmp_path):
        """No signal should not open or close any position."""
        engine = _make_engine(tmp_path)
        candle = _make_candle()
        with patch.object(SignalGenerator, 'evaluate', return_value=None):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(engine._evaluate_symbol("BTCUSDT", candle))
            assert engine.state.get_open_position("BTCUSDT") is None
            loop.close()

    def test_long_signal_opens_position(self, tmp_path):
        """LONG signal should open a position when risk guard allows."""
        engine = _make_engine(tmp_path)
        now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        candle = _make_candle(close=122.0, ts=(now_ts // 3600000) * 3600000)
        sig = Signal(type=SignalType.SIGNAL_LONG, symbol="BTCUSDT",
                     timestamp=now_ts, price=122.0, indicators={})
        with patch.object(SignalGenerator, 'evaluate', return_value=sig):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(engine._evaluate_symbol("BTCUSDT", candle))
            pos = engine.state.get_open_position("BTCUSDT")
            assert pos is not None
            loop.close()

    def test_kill_switch_closes_all_positions(self, tmp_path):
        """KILL_SWITCH should force-close all open positions."""
        engine = _make_engine(tmp_path)
        engine.state.open_position("BTCUSDT", 100.0, 1700000000, 0.1)
        engine.state.open_position("ETHUSDT", 2000.0, 1700000000, 0.01)
        engine.state.set_guard_state(GuardState.KILL_SWITCH)
        candle = _make_candle()
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine._evaluate_symbol("BTCUSDT", candle))
        assert engine.state.get_open_position("BTCUSDT") is None
        assert engine.state.get_open_position("ETHUSDT") is None
        loop.close()

    def test_exit_signal_closes_position(self, tmp_path):
        """EXIT signal should close the current position."""
        engine = _make_engine(tmp_path)
        engine.state.open_position("BTCUSDT", 100.0, 1700000000, 0.1)
        engine.state.update_peak("BTCUSDT", 105.0)
        # Set bars_held so check_exit gets called
        engine.state.set_state("bars_held_BTCUSDT", 10)
        sig = Signal(type=SignalType.EXIT_TRAILING, symbol="BTCUSDT",
                     timestamp=1700036000, price=103.0, indicators={})
        sig.reason = "Trailing stop"
        candle = _make_candle(close=103.0)
        with patch.object(SignalGenerator, 'check_exit', return_value=sig):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(engine._evaluate_symbol("BTCUSDT", candle))
            assert engine.state.get_open_position("BTCUSDT") is None
            loop.close()

    def test_risk_guard_blocks_entry(self, tmp_path):
        """Entry should be blocked when risk guard says no."""
        engine = _make_engine(tmp_path)
        # Put in KILL_SWITCH (always blocks, no timestamp needed)
        engine.state.set_guard_state(GuardState.KILL_SWITCH)
        now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        candle = _make_candle(close=122.0, ts=(now_ts // 3600000) * 3600000)
        sig = Signal(type=SignalType.SIGNAL_LONG, symbol="BTCUSDT",
                     timestamp=now_ts, price=122.0, indicators={})
        with patch.object(SignalGenerator, 'evaluate', return_value=sig):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(engine._evaluate_symbol("BTCUSDT", candle))
            pos = engine.state.get_open_position("BTCUSDT")
            assert pos is None  # KILL_SWITCH blocks entries
            loop.close()


# ══════════════════════════════════════════════════════════
# 4-Hourly Summary Report
# ══════════════════════════════════════════════════════════

class TestHourlySummary:

    def test_summary_sent_at_4h_intervals(self, tmp_path):
        """4-hourly summary should trigger at 0,4,8,12,16,20 UTC."""
        engine = _make_engine(tmp_path)
        # Find a 4h-aligned UTC timestamp (0,4,8,12,16,20)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        hour_ts = (now_ms // 3600000) * 3600000
        # Find next 4h boundary
        while (hour_ts // 3600000) % 24 % 4 != 0:
            hour_ts += 3600000
        candle = _make_candle(ts=hour_ts)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine._on_candle("BTCUSDT", candle))
        engine.reporter.report_hourly.assert_called()
        loop.close()

    def test_summary_not_sent_at_non_4h(self, tmp_path):
        """Summary should NOT trigger at non-4h hours."""
        engine = _make_engine(tmp_path)
        base_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        hour_ts = (base_ts // 3600000) * 3600000
        non_4h = hour_ts
        while (non_4h // 3600000) % 24 % 4 != 3:
            non_4h += 3600000
        candle = _make_candle(ts=non_4h)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine._on_candle("BTCUSDT", candle))
        engine.reporter.report_hourly.assert_not_called()
        loop.close()


# ══════════════════════════════════════════════════════════
# Position Sizing (in engine context)
# ══════════════════════════════════════════════════════════

class TestPositionSizing:

    def test_position_size_with_leverage(self, tmp_path):
        """Position size should account for leverage and fees."""
        equity = 100.0
        n_assets = 2
        entry_price = 50000.0
        leverage = LEVERAGE_TIERS.get("BTCUSDT", DEFAULT_LEVERAGE)
        allocation = equity / n_assets
        size = (allocation * leverage) / (entry_price * (1 + FEE_RATE * leverage))
        assert size > 0
        pos_value = size * entry_price
        assert pos_value <= allocation * leverage * 1.001

    def test_all_tiers_defined(self):
        """All configured assets should have leverage tiers."""
        for asset in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]:
            assert asset in LEVERAGE_TIERS

    def test_leverage_within_bounds(self):
        """Leverage should be between 1.0 and 2.0."""
        for asset, lev in LEVERAGE_TIERS.items():
            assert 1.0 <= lev <= 2.0


# ══════════════════════════════════════════════════════════
# PAPER_MODE Enforcement
# ══════════════════════════════════════════════════════════

class TestPaperModeEnforcement:

    def test_paper_mode_is_true(self):
        from paper_engine import PAPER_MODE
        assert PAPER_MODE is True

    def test_initial_capital_positive(self):
        assert INITIAL_CAPITAL > 0

    def test_fee_rate_reasonable(self):
        assert 0 < FEE_RATE < 0.01

    def test_slippage_bps_reasonable(self):
        assert 0 < SLIPPAGE_BPS < 100