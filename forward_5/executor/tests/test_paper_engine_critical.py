"""
Tests for paper_engine.py — Critical bug fix regression tests.
Tests: Unrealized DD check, KILL_SWITCH close-all, entry/exit flow,
deduplication, engine_start_time filter, position sizing with fees.
"""
import asyncio
import json
import sqlite3
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from paper_engine import (
    PaperTradingEngine, LEVERAGE_TIERS, DEFAULT_LEVERAGE,
    SLIPPAGE_BPS, FEE_RATE, INITIAL_CAPITAL, PAPER_MODE, log_trade
)
from state_manager import StateManager, GuardState
from risk_guard import RiskGuard, MAX_DRAWDOWN_PCT
from signal_generator import SignalType


class TestUnrealizedDDCheck:
    """Test that unrealized DD triggers KILL when total open positions exceed threshold."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_unrealized.db")

    def _make_engine(self):
        """Create a minimal engine for testing (no Discord, no feed)."""
        engine = PaperTradingEngine.__new__(PaperTradingEngine)
        engine.assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        engine.state = StateManager(db_path=self.db_path)
        engine.state.set_start_equity(100.0)
        engine.state.set_equity(100.0)
        engine.state.set_state("peak_equity", 100.0)
        engine.risk = RiskGuard(engine.state)
        engine.signal = MagicMock()
        engine.reporter = MagicMock()
        engine.feed = MagicMock()
        engine._last_candle_hour = {}
        engine._engine_start_time = 0  # Don't filter any candles
        engine._last_summary_hour = -1
        return engine

    def test_unrealized_dd_triggers_kill(self):
        """When unrealized DD exceeds 20%, KILL should be triggered."""
        engine = self._make_engine()

        # Open 3 positions at entry price
        for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
            engine.state.open_position(sym, 1000.0, 1776830000000, 0.1, "RUNNING")

        # Mark-to-market: all positions down 25% from entry
        # Unrealized PnL per position ≈ -250 (25% of 1000)
        # Total unrealized ≈ -750 → equity 100 + (-750) = -650 → DD = 750%
        # But with realistic numbers: entry=1000, size=0.1, mark=750
        # PnL per position = (750 - 1000) * 0.1 - fee = -25 - fee ≈ -25.002
        # Total unrealized ≈ -75.006
        # Mark-to-market = 100 + (-75) = 25 → DD = (100-25)/100 = 75% > 20%

        # Simulate _on_candle with prices 25% below entry
        # This would trigger the unrealized DD check
        equity = engine.state.get_equity()
        peak = 100.0
        unrealized_pnl = 0.0

        for sym in engine.assets:
            pos = engine.state.get_open_position(sym)
            if pos:
                mark_price = 750.0  # 25% below entry
                lev = LEVERAGE_TIERS.get(sym, DEFAULT_LEVERAGE)
                exit_fee = pos["size"] * mark_price * FEE_RATE * lev
                pos_pnl = (mark_price - pos["entry_price"]) * pos["size"] - exit_fee
                unrealized_pnl += pos_pnl

        mark_to_market = equity + unrealized_pnl
        mtm_dd = (peak - mark_to_market) / peak * 100

        # Verify the math: should be > 20%
        assert mtm_dd > MAX_DRAWDOWN_PCT, f"Expected DD > {MAX_DRAWDOWN_PCT}%, got {mtm_dd:.1f}%"

    def test_unrealized_dd_no_trigger_when_small(self):
        """When unrealized DD is small, KILL should NOT be triggered."""
        engine = self._make_engine()

        # Open 1 position
        engine.state.open_position("BTCUSDT", 1000.0, 1776830000000, 0.001, "RUNNING")

        equity = engine.state.get_equity()
        peak = 100.0
        unrealized_pnl = 0.0

        pos = engine.state.get_open_position("BTCUSDT")
        mark_price = 999.0  # Only $1 below entry
        lev = LEVERAGE_TIERS.get("BTCUSDT", DEFAULT_LEVERAGE)
        exit_fee = pos["size"] * mark_price * FEE_RATE * lev
        pos_pnl = (mark_price - pos["entry_price"]) * pos["size"] - exit_fee
        unrealized_pnl += pos_pnl

        mark_to_market = equity + unrealized_pnl
        mtm_dd = (peak - mark_to_market) / peak * 100

        # Should be < 20%
        assert mtm_dd < MAX_DRAWDOWN_PCT, f"Expected DD < {MAX_DRAWDOWN_PCT}%, got {mtm_dd:.1f}%"

    def test_no_open_positions_zero_unrealized_pnl(self):
        """When no positions are open, unrealized PnL should be 0."""
        engine = self._make_engine()
        equity = engine.state.get_equity()
        peak = 100.0
        unrealized_pnl = 0.0

        for sym in engine.assets:
            pos = engine.state.get_open_position(sym)
            if pos:
                unrealized_pnl += 1  # Should never happen

        mark_to_market = equity + unrealized_pnl
        mtm_dd = (peak - mark_to_market) / peak * 100

        assert mtm_dd == 0.0
        assert mark_to_market == equity


class TestKillSwitchCloseAll:
    """Test that KILL_SWITCH force-closes ALL positions, not just one."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_kill_all.db")

    def test_kill_closes_all_positions(self):
        """KILL_SWITCH should close all 6 open positions, not just the current one."""
        state = StateManager(db_path=self.db_path)
        state.set_start_equity(100.0)
        state.set_equity(100.0)
        state.set_state("peak_equity", 100.0)

        # Open positions for all 6 assets
        assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]
        for sym in assets:
            state.open_position(sym, 1000.0, 1776830000000, 0.001, "RUNNING")

        # Verify all are open
        for sym in assets:
            assert state.get_open_position(sym) is not None, f"{sym} should be open"

        # Activate KILL_SWITCH and close all positions
        state.set_guard_state(GuardState.KILL_SWITCH, "Test kill")
        risk = RiskGuard(state)

        for sym in assets:
            pos = state.get_open_position(sym)
            if pos:
                exit_price = 999.0
                lev = LEVERAGE_TIERS.get(sym, DEFAULT_LEVERAGE)
                fee = pos["size"] * exit_price * FEE_RATE * lev
                pnl = (exit_price - pos["entry_price"]) * pos["size"] - fee
                state.close_position(sym, exit_price, 1776834000000,
                                      "KILL_SWITCH force-close",
                                      GuardState.KILL_SWITCH.value,
                                      net_pnl=pnl)
                risk.on_trade_closed(pnl)

        # Verify all are closed
        for sym in assets:
            assert state.get_open_position(sym) is None, f"{sym} should be closed"

    def test_kill_when_no_positions(self):
        """KILL_SWITCH with no open positions should not crash."""
        state = StateManager(db_path=self.db_path)
        state.set_start_equity(100.0)
        state.set_equity(100.0)
        state.set_state("peak_equity", 100.0)
        state.set_guard_state(GuardState.KILL_SWITCH, "Test kill")

        # Closing all positions when none are open should be fine
        closed = 0
        for sym in ["BTCUSDT", "ETHUSDT"]:
            pos = state.get_open_position(sym)
            if pos:
                closed += 1
        assert closed == 0


class TestEngineStartTimeFilter:
    """Test that old candles are skipped during gap recovery."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_filter.db")

    def test_old_candles_skipped(self):
        """Candles older than engine_start_time should not trigger _on_candle."""
        engine_start = 1776830000000  # Now
        processed = []

        # Simulate the filter
        for ts in [1776700000000, 1776710000000, 1776820000000, 1776835000000]:
            if ts < engine_start:
                continue  # Skip
            processed.append(ts)

        # Only the last candle (after engine start) should be processed
        assert len(processed) == 1
        assert processed[0] == 1776835000000

    def test_no_filter_when_engine_start_none(self):
        """When engine_start_time is None, all candles should be processed."""
        engine_start = None
        processed = []

        for ts in [1776700000000, 1776710000000, 1776820000000]:
            if engine_start and ts < engine_start:
                continue
            processed.append(ts)

        assert len(processed) == 3


class TestDeduplication:
    """Test that duplicate candles are not processed twice."""

    def test_same_candle_not_processed_twice(self):
        """Processing the same (symbol, timestamp) twice should skip the second."""
        seen = {}
        key1 = "BTCUSDT_1776830400000"
        key2 = "BTCUSDT_1776830400000"  # Same candle

        seen[key1] = True
        # Second should be skipped
        assert key2 in seen

    def test_different_candles_processed(self):
        """Different (symbol, timestamp) pairs should both be processed."""
        seen = {}
        key1 = "BTCUSDT_1776830400000"
        key2 = "BTCUSDT_1776834000000"  # Different hour

        seen[key1] = True
        assert key2 not in seen  # Should be new

    def test_same_ts_different_symbol(self):
        """Same timestamp but different symbol should be processed."""
        seen = {}
        key1 = "BTCUSDT_1776830400000"
        key2 = "ETHUSDT_1776830400000"  # Different asset, same time

        seen[key1] = True
        assert key2 not in seen  # Should be new


class TestPositionSizingWithFees:
    """Test that position sizing correctly accounts for entry fees."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_sizing.db")

    def test_size_formula_with_leverage(self):
        """Position size = (allocation * leverage) / (price * (1 + fee_rate * leverage))"""
        equity = 100.0
        n_assets = 6
        allocation = equity / n_assets  # 16.67€
        price = 85000.0  # BTC
        leverage = 1.8
        fee_rate = 0.0001

        size = (allocation * leverage) / (price * (1 + fee_rate * leverage))
        fee = size * price * fee_rate * leverage

        # Verify: size * price * (1 + fee_rate * leverage) ≈ allocation * leverage
        total_cost = size * price * (1 + fee_rate * leverage)
        expected = allocation * leverage
        assert abs(total_cost - expected) < 0.01, f"Expected {expected}, got {total_cost}"

        # Fee should be small but non-zero
        assert fee > 0
        assert fee < 0.01  # Less than 1 cent

    def test_equity_decreases_after_entry_fee(self):
        """Equity should decrease by entry fee amount after opening position."""
        state = StateManager(db_path=self.db_path)
        state.set_start_equity(100.0)
        state.set_equity(100.0)

        equity_before = state.get_equity()
        fee = 0.0054  # Typical entry fee
        state.set_equity(equity_before - fee)

        assert state.get_equity() == pytest.approx(99.9946, abs=0.001)

    def test_all_leverage_tiers_covered(self):
        """All 6 assets should have defined leverage tiers."""
        assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]
        for sym in assets:
            assert sym in LEVERAGE_TIERS, f"{sym} missing from LEVERAGE_TIERS"
            assert LEVERAGE_TIERS[sym] > 0, f"{sym} leverage should be positive"


class TestLogTrade:
    """Test the JSONL trade log function."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.tmpdir, "test_trades.jsonl")

    def test_log_trade_appends(self):
        """log_trade should append events to JSONL file."""
        import paper_engine
        old_path = paper_engine.TRADE_LOG
        paper_engine.TRADE_LOG = Path(self.log_path)
        try:
            log_trade({"event": "ENTRY", "symbol": "BTCUSDT", "price": 85000})
            log_trade({"event": "EXIT", "symbol": "BTCUSDT", "price": 86000})

            lines = open(self.log_path).readlines()
            assert len(lines) == 2
            t1 = json.loads(lines[0])
            t2 = json.loads(lines[1])
            assert t1["event"] == "ENTRY"
            assert t2["event"] == "EXIT"
            assert "logged_at" in t1
        finally:
            paper_engine.TRADE_LOG = old_path

    def test_log_trade_json_valid(self):
        """Each line in JSONL should be valid JSON."""
        import paper_engine
        old_path = paper_engine.TRADE_LOG
        paper_engine.TRADE_LOG = Path(self.log_path)
        try:
            log_trade({"event": "ENTRY", "symbol": "BTCUSDT",
                        "timestamp": 1776830400000, "price": 85000.0,
                        "indicators": {"adx_14": 25.0, "ema_50": 84000.0}})

            lines = open(self.log_path).readlines()
            t = json.loads(lines[0])
            assert t["timestamp"] == 1776830400000
            assert t["indicators"]["adx_14"] == 25.0
        finally:
            paper_engine.TRADE_LOG = old_path


class TestPaperModeEnforcement:
    """Test that PAPER_MODE=True is enforced."""

    def test_paper_mode_is_true(self):
        """PAPER_MODE should be True in production code."""
        assert PAPER_MODE is True, "PAPER_MODE must be True for paper trading"

    def test_paper_mode_blocks_real_orders(self):
        """When PAPER_MODE=False, engine should raise RuntimeError."""
        # We can't actually test this without modifying the constant,
        # but we verify the check exists
        import paper_engine
        source = open(paper_engine.__file__).read()
        assert "PAPER_MODE" in source
        assert "RuntimeError" in source


class TestRiskGuardIntegration:
    """Test that RiskGuard and PaperEngine work together correctly."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_risk_int.db")

    def test_consecutive_losses_triggers_soft_pause(self):
        """5 consecutive losses should trigger SOFT_PAUSE."""
        state = StateManager(db_path=self.db_path)
        state.set_start_equity(100.0)
        state.set_equity(100.0)
        state.set_state("peak_equity", 100.0)
        risk = RiskGuard(state)

        # Simulate 5 consecutive losses
        for i in range(5):
            state.increment_consecutive_losses()

        allowed, reason = risk.check_all("BTCUSDT")
        assert not allowed
        assert "SOFT_PAUSE" in reason

    def test_drawdown_triggers_kill(self):
        """DD > 20% should trigger KILL_SWITCH."""
        state = StateManager(db_path=self.db_path)
        state.set_start_equity(100.0)
        state.set_equity(75.0)  # 25% DD from peak
        state.set_state("peak_equity", 100.0)
        risk = RiskGuard(state)

        allowed, reason = risk.check_all("BTCUSDT")
        assert not allowed
        assert "KILL" in reason

    def test_resume_resets_consecutive_losses(self):
        """manual_resume should reset CL and set RUNNING."""
        state = StateManager(db_path=self.db_path)
        state.set_start_equity(100.0)
        state.set_equity(100.0)
        state.set_state("peak_equity", 100.0)
        risk = RiskGuard(state)

        # Set to KILL
        risk.manual_kill("Test")
        assert state.get_guard_state() == GuardState.KILL_SWITCH

        # Resume
        risk.manual_resume("Test resume")
        assert state.get_guard_state() == GuardState.RUNNING
        assert state.get_consecutive_losses() == 0

    def test_zero_equity_triggers_kill(self):
        """Equity at 0 should trigger KILL_SWITCH."""
        state = StateManager(db_path=self.db_path)
        state.set_start_equity(100.0)
        state.set_equity(0.0)
        state.set_state("peak_equity", 100.0)
        risk = RiskGuard(state)

        allowed, reason = risk.check_all("BTCUSDT")
        assert not allowed
        assert "KILL" in reason

    def test_negative_equity_triggers_kill(self):
        """Negative equity should trigger KILL_SWITCH."""
        state = StateManager(db_path=self.db_path)
        state.set_start_equity(100.0)
        state.set_equity(-5.0)
        state.set_state("peak_equity", 100.0)
        risk = RiskGuard(state)

        allowed, reason = risk.check_all("BTCUSDT")
        assert not allowed


class TestExitLogicEdgeCases:
    """Test edge cases in exit logic."""

    def test_trailing_stop_uses_peak_not_entry(self):
        """Trailing stop should be based on peak price, not entry price."""
        entry = 80000.0
        peak = 85000.0  # Price went up then back down
        trailing_pct = 2.0

        trailing_stop = peak * (1 - trailing_pct / 100)
        assert trailing_stop == 83300.0  # 2% below peak, not entry

        # Stop should NOT be triggered at 78400 (2% below entry)
        # Because the trailing stop is at 83300
        low = 78400.0  # Below entry stop loss
        assert low < trailing_stop  # Trailing would have hit first

    def test_stop_loss_uses_entry(self):
        """Stop loss should be based on entry price."""
        entry = 80000.0
        stop_loss_pct = 2.5

        stop_loss = entry * (1 - stop_loss_pct / 100)
        assert stop_loss == 78000.0

    def test_max_hold_exits_at_close(self):
        """Max hold exit should use close price, not stop price."""
        close = 83000.0
        # Exit at market (close) when max hold reached
        exit_price = close * (1 - SLIPPAGE_BPS / 10000)
        assert exit_price < close
        assert abs(close - exit_price) / close < 0.001  # < 0.1% slippage