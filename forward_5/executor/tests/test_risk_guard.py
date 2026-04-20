"""
Executor V1 — Risk Guard Tests

Covers:
- Guard state machine transitions
- Daily loss threshold (reads from trades DB)
- BUG 4 REGRESSION: Daily loss uses current equity (not start_equity)
- Consecutive loss tracking
- Drawdown kill switch
"""

import os
import tempfile
import pytest

from state_manager import StateManager, GuardState
from risk_guard import RiskGuard


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
    return s


@pytest.fixture
def rg(sm):
    return RiskGuard(sm)


class TestGuardStateMachine:
    def test_initial_state_is_running(self, rg, sm):
        assert sm.get_guard_state() == GuardState.RUNNING

    def test_kill_switch_on_max_dd(self, rg, sm):
        """DD > 20% → KILL_SWITCH (no trading at all)."""
        sm.set_equity(75.0)  # 25% drawdown from 100€
        sm.set_state("peak_equity", 100.0)
        allowed, reason = rg.check_all("BTCUSDT")
        assert not allowed
        assert sm.get_guard_state() == GuardState.KILL_SWITCH


class TestBug4Regression_DailyLossDenominator:
    """BUG 4 REGRESSION: Daily loss must use CURRENT equity, not start_equity.

    Previously: daily_loss_pct = abs(daily_pnl) / start_equity
    After profits (equity=150€), a 7€ loss = 7% (start) vs 4.7% (current).
    Using start_equity triggered STOP_NEW too early.
    """

    def test_uses_current_equity_after_profits(self, rg, sm):
        """After profitable trading, daily loss threshold should be harder to trigger."""
        # Simulate profitable trading: equity grew to 150€
        sm.set_equity(150.0)
        # Record a losing trade today in the DB
        sm.close_position("BTCUSDT", 86000.0, 1713540000, "test", "RUNNING", net_pnl=-7.0)
        # Now daily_pnl from DB = -7.0
        # With start_equity: 7/100 = 7% → STOP_NEW (BUG)
        # With current equity: 7/150 = 4.67% → still RUNNING (CORRECT)
        # Note: check_all also checks DD, so we need peak_equity high enough
        sm.set_state("peak_equity", 150.0)
        sm.set_guard_state(GuardState.RUNNING)  # reset
        allowed, reason = rg.check_all("BTCUSDT")
        # 7/150 = 4.67% < 5% → should be allowed
        assert allowed, f"Should NOT trigger STOP_NEW: 7€ loss on 150€ = 4.67%"

    def test_triggers_at_correct_threshold(self, sm, db_path):
        """STOP_NEW should trigger at 5% of CURRENT equity."""
        sm.set_equity(200.0)
        sm.set_state("peak_equity", 200.0)
        sm2 = StateManager(db_path=db_path)
        sm2.set_start_equity(100.0)
        sm2.set_equity(200.0)
        sm2.set_state("peak_equity", 200.0)
        rg2 = RiskGuard(sm2)

        # 11€ loss on 200€ = 5.5% → STOP_NEW
        sm2.open_position("BTCUSDT", 85000.0, 1713500000, 0.001, "RUNNING")
        sm2.close_position("BTCUSDT", 84000.0, 1713540000, "test", "RUNNING", net_pnl=-11.0)
        allowed, _ = rg2.check_all("BTCUSDT")
        assert not allowed, "5.5% of current equity should trigger STOP_NEW"


class TestConsecutiveLosses:
    def test_cl_counter_increments(self, sm):
        """CL counter should increment on losing trade via on_trade_closed."""
        rg = RiskGuard(sm)
        sm.set_state("consecutive_losses", 0)
        rg.on_trade_closed(-1.0)
        assert sm.get_consecutive_losses() >= 1

    def test_cl_counter_resets_on_win(self, sm):
        """CL counter should reset to 0 on a winning trade."""
        sm.set_state("consecutive_losses", 3)
        rg = RiskGuard(sm)
        rg.on_trade_closed(1.0)
        assert sm.get_consecutive_losses() == 0

    def test_cl_pause_at_threshold(self, sm):
        """SOFT_PAUSE should trigger at CL ≥ 5."""
        sm.set_state("consecutive_losses", 5)
        rg = RiskGuard(sm)
        # Note: also checks DD and daily loss, so ensure those pass
        sm.set_state("peak_equity", 100.0)
        allowed, reason = rg.check_all("BTCUSDT")
        assert not allowed
        assert "consecutive" in reason.lower() or sm.get_guard_state() == GuardState.SOFT_PAUSE


class TestDrawdown:
    def test_no_kill_below_20_pct(self, sm):
        """DD at 19% → should not trigger KILL_SWITCH."""
        sm.set_equity(81.0)
        sm.set_state("peak_equity", 100.0)
        rg = RiskGuard(sm)
        # Check that KILL_SWITCH is NOT triggered at 19% DD
        rg.check_all("BTCUSDT")
        # May still be blocked by other guards, but NOT kill switch
        assert sm.get_guard_state() != GuardState.KILL_SWITCH

    def test_kill_above_20_pct(self, sm):
        """DD at 21% → KILL_SWITCH."""
        sm.set_equity(79.0)
        sm.set_state("peak_equity", 100.0)
        rg = RiskGuard(sm)
        rg.check_all("BTCUSDT")
        assert sm.get_guard_state() == GuardState.KILL_SWITCH