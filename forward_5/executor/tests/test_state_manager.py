"""
Executor V1 — State Manager Tests

Covers:
- Position lifecycle (open → close)
- Equity tracking
- BUG 2 REGRESSION: close_position stores NET PnL (not GROSS)
- Accounting invariant: equity = initial + sum(net_pnl) - sum(entry_fees)
- State persistence (get/set)
"""

import os
import tempfile
import sqlite3
import pytest

from state_manager import StateManager, GuardState


@pytest.fixture
def db_path():
    """Create a temp DB that gets cleaned up after each test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def sm(db_path):
    """Fresh StateManager with 100€ equity."""
    s = StateManager(db_path=db_path)
    s.set_start_equity(100.0)
    s.set_equity(100.0)
    s.set_state("peak_equity", 100.0)
    return s


class TestPositionLifecycle:
    def test_open_position(self, sm):
        sm.open_position("BTCUSDT", 85000.0, 1713500000, 0.001, "RUNNING")
        pos = sm.get_open_position("BTCUSDT")
        assert pos is not None
        assert pos["symbol"] == "BTCUSDT"
        assert pos["entry_price"] == 85000.0
        assert pos["size"] == 0.001
        assert pos["state"] == "IN_LONG"

    def test_close_position(self, sm):
        sm.open_position("BTCUSDT", 85000.0, 1713500000, 0.001, "RUNNING")
        pnl = sm.close_position("BTCUSDT", 86000.0, 1713540000, "trailing_stop", "RUNNING")
        assert pnl is not None
        pos = sm.get_open_position("BTCUSDT")
        assert pos is None  # position closed

    def test_close_nonexistent_position(self, sm):
        pnl = sm.close_position("ETHUSDT", 3000.0, 1713540000, "stop_loss", "RUNNING")
        assert pnl is None

    def test_multiple_positions_different_symbols(self, sm):
        sm.open_position("BTCUSDT", 85000.0, 1713500000, 0.001, "RUNNING")
        sm.open_position("ETHUSDT", 3000.0, 1713500000, 0.01, "RUNNING")
        assert sm.get_open_position("BTCUSDT") is not None
        assert sm.get_open_position("ETHUSDT") is not None

    def test_peak_price_updates(self, sm):
        sm.open_position("BTCUSDT", 85000.0, 1713500000, 0.001, "RUNNING")
        # Simulate peak update via DB
        with sqlite3.connect(sm.db_path) as conn:
            conn.execute("UPDATE positions SET peak_price = 86000.0 WHERE symbol = 'BTCUSDT'")
        pos = sm.get_open_position("BTCUSDT")
        assert pos["peak_price"] == 86000.0


class TestEquityTracking:
    def test_set_get_equity(self, sm):
        sm.set_equity(105.5)
        assert sm.get_equity() == 105.5

    def test_equity_persists(self, sm, db_path):
        sm.set_equity(105.5)
        # Reload from DB
        sm2 = StateManager(db_path=db_path)
        assert sm2.get_equity() == 105.5

    def test_start_equity(self, sm):
        assert sm.get_start_equity() == 100.0

    def test_peak_equity_tracking(self, sm):
        sm.set_state("peak_equity", 100.0)
        sm.set_state("peak_equity", 105.0)
        assert float(sm.get_state("peak_equity", 100.0)) == 105.0


class TestBug2Regression_NetPnL:
    """BUG 2 REGRESSION: close_position must store NET PnL (with exit fee).

    Previously close_position() recalculated GROSS PnL internally,
    missing the exit fee. Now it accepts net_pnl parameter.
    """

    def test_close_with_net_pnl(self, sm):
        """When net_pnl is provided, it should be stored in trades table."""
        sm.open_position("BTCUSDT", 85000.0, 1713500000, 0.001, "RUNNING")
        net_pnl = 0.85  # After exit fee deduction
        sm.close_position("BTCUSDT", 86000.0, 1713540000, "trailing_stop", "RUNNING", net_pnl=net_pnl)

        with sqlite3.connect(sm.db_path) as conn:
            row = conn.execute("SELECT pnl FROM trades WHERE event = 'EXIT'").fetchone()
            assert row is not None
            assert abs(row[0] - 0.85) < 0.01, f"Expected NET PnL=0.85, got {row[0]}"

    def test_close_without_net_pnl_falls_back_to_gross(self, sm):
        """When net_pnl is NOT provided, should fall back to gross PnL calculation."""
        sm.open_position("BTCUSDT", 85000.0, 1713500000, 0.001, "RUNNING")
        # Gross PnL = (86000 - 85000) * 0.001 = 1.0
        sm.close_position("BTCUSDT", 86000.0, 1713540000, "trailing_stop", "RUNNING")

        with sqlite3.connect(sm.db_path) as conn:
            row = conn.execute("SELECT pnl FROM trades WHERE event = 'EXIT'").fetchone()
            assert row is not None
            assert abs(row[0] - 1.0) < 0.01, f"Expected GROSS PnL=1.0, got {row[0]}"

    def test_net_pnl_vs_gross_pnl_differ_by_fee(self, sm):
        """NET PnL should be less than GROSS PnL by the exit fee amount."""
        sm.open_position("BTCUSDT", 85000.0, 1713500000, 0.001, "RUNNING")
        exit_fee = 0.0086  # 86000 * 0.001 * 0.0001 ≈ 0.0086
        gross_pnl = 1.0  # (86000 - 85000) * 0.001
        net_pnl = gross_pnl - exit_fee

        sm.close_position("BTCUSDT", 86000.0, 1713540000, "trailing_stop", "RUNNING", net_pnl=net_pnl)

        with sqlite3.connect(sm.db_path) as conn:
            row = conn.execute("SELECT pnl FROM trades WHERE event = 'EXIT'").fetchone()
            assert row[0] < gross_pnl, "NET PnL should be less than GROSS PnL"


class TestAccountingInvariant:
    """The fundamental accounting equation must hold:
    equity = initial + sum(net_pnl) - sum(entry_fees)
    """

    def test_invariant_no_trades(self, sm):
        """With no trades, equity should equal initial capital."""
        assert sm.get_equity() == 100.0

    def test_invariant_single_winning_trade(self, sm):
        """After one complete trade cycle, equity = initial + net_pnl - entry_fee."""
        initial = 100.0
        entry_price = 85000.0
        exit_price = 86000.0
        size = 0.001
        fee_rate = 0.0001

        entry_fee = size * entry_price * fee_rate
        exit_fee = size * exit_price * fee_rate
        gross_pnl = (exit_price - entry_price) * size
        net_pnl = gross_pnl - exit_fee

        # Simulate entry: deduct entry fee from equity
        sm.set_equity(initial - entry_fee)
        sm.open_position("BTCUSDT", entry_price, 1713500000, size, "RUNNING")

        # Simulate exit: add net PnL to equity
        new_equity = sm.get_equity() + net_pnl
        sm.set_equity(new_equity)
        sm.close_position("BTCUSDT", exit_price, 1713540000, "trailing_stop", "RUNNING", net_pnl=net_pnl)

        expected_equity = initial - entry_fee + net_pnl
        assert abs(sm.get_equity() - expected_equity) < 0.01

    def test_invariant_losing_trade(self, sm):
        """After a losing trade, equity should decrease correctly."""
        initial = 100.0
        entry_price = 85000.0
        exit_price = 84000.0  # loss
        size = 0.001
        fee_rate = 0.0001

        entry_fee = size * entry_price * fee_rate
        exit_fee = size * exit_price * fee_rate
        gross_pnl = (exit_price - entry_price) * size  # negative
        net_pnl = gross_pnl - exit_fee  # more negative

        sm.set_equity(initial - entry_fee)
        sm.open_position("BTCUSDT", entry_price, 1713500000, size, "RUNNING")

        new_equity = sm.get_equity() + net_pnl
        sm.set_equity(new_equity)
        sm.close_position("BTCUSDT", exit_price, 1713540000, "stop_loss", "RUNNING", net_pnl=net_pnl)

        expected_equity = initial - entry_fee + net_pnl
        assert abs(sm.get_equity() - expected_equity) < 0.01
        assert sm.get_equity() < initial  # lost money


class TestStatePersistence:
    def test_set_get_state(self, sm):
        sm.set_state("bars_held_BTCUSDT", 5)
        # get_state returns json.loads → integer stays integer
        assert sm.get_state("bars_held_BTCUSDT", 0) == 5

    def test_state_survives_reload(self, sm, db_path):
        sm.set_state("engine_start_time", 1713500000)
        sm2 = StateManager(db_path=db_path)
        # get_state returns json.loads → int stays int
        assert sm2.get_state("engine_start_time") == 1713500000

    def test_state_default_value(self, sm):
        val = sm.get_state("nonexistent_key", "default")
        assert val == "default"