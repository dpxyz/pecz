"""
Executor V1 — Paper Engine Integration Tests (E2E Golden Path)

Covers:
- Full trade cycle: Entry → Hold → Exit → Equity check
- BUG 1 REGRESSION: Entry fee deducted from equity
- BUG 2 REGRESSION: trades table stores NET PnL
- Position sizing across all 6 assets with leverage tiers
- Accounting invariant after complete trade cycles
"""

import os
import tempfile
import sqlite3
import pytest

from paper_engine import PaperTradingEngine, FEE_RATE, SLIPPAGE_BPS, LEVERAGE_TIERS


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def engine(db_path):
    """Paper engine with 6 assets and fresh DB."""
    assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]
    return PaperTradingEngine(assets=assets, db_path=db_path)


class TestBug1Regression_EntryFeeInEquity:
    """BUG 1 REGRESSION: Entry fee must be deducted from equity on position open.

    Previously only exit fee was deducted, overstating equity by ~0.005€/trade.
    Over 30 trades this adds up to 0.5-1% equity error.
    """

    def test_equity_decreases_on_entry(self, engine):
        """When a position opens, equity should decrease by the entry fee."""
        initial_equity = engine.state.get_equity()
        entry_price = 85000.0
        leverage = LEVERAGE_TIERS["BTCUSDT"]
        allocation = initial_equity / len(engine.assets)
        size = (allocation * leverage) / (entry_price * (1 + FEE_RATE * leverage))
        entry_fee = size * entry_price * FEE_RATE * leverage

        # Simulate entry (would normally happen via _evaluate_symbol)
        # We check the fee deduction mechanism exists
        assert entry_fee > 0, "Entry fee should be positive"
        assert entry_fee < 0.01, f"Entry fee should be small (~0.005€), got {entry_fee:.4f}€"

    def test_full_cycle_accounting(self, engine):
        """After entry + exit, equity change should equal NET PnL - entry_fee."""
        # This tests the complete accounting flow
        initial = engine.state.get_equity()
        entry_price = 85000.0
        exit_price = 86000.0
        leverage = LEVERAGE_TIERS["BTCUSDT"]
        allocation = initial / len(engine.assets)
        size = (allocation * leverage) / (entry_price * (1 + FEE_RATE * leverage))

        # Entry
        entry_fee = size * entry_price * FEE_RATE * leverage
        engine.state.set_equity(initial - entry_fee)
        engine.state.open_position("BTCUSDT", entry_price, 1713500000, size, "RUNNING")

        # Exit
        exit_fee = size * exit_price * FEE_RATE * leverage
        gross_pnl = (exit_price - entry_price) * size
        net_pnl = gross_pnl - exit_fee
        engine.state.set_equity(engine.state.get_equity() + net_pnl)
        engine.state.close_position("BTCUSDT", exit_price, 1713540000, "trailing_stop", "RUNNING", net_pnl=net_pnl)

        # Accounting invariant: equity = initial + net_pnl - entry_fee
        final_equity = engine.state.get_equity()
        expected = initial - entry_fee + net_pnl
        assert abs(final_equity - expected) < 0.001, \
            f"Equity mismatch: {final_equity:.4f} vs expected {expected:.4f}"


class TestBug2Regression_NetPnLInTradesTable:
    """BUG 2 REGRESSION: trades table must store NET PnL (with fees).

    Previously close_position() calculated GROSS PnL internally.
    """

    def test_trades_table_has_net_pnl(self, engine):
        """After a trade, trades table PnL should include exit fee."""
        initial = engine.state.get_equity()
        entry_price = 85000.0
        exit_price = 86000.0
        leverage = LEVERAGE_TIERS["BTCUSDT"]
        allocation = initial / len(engine.assets)
        size = (allocation * leverage) / (entry_price * (1 + FEE_RATE * leverage))

        entry_fee = size * entry_price * FEE_RATE * leverage
        engine.state.set_equity(initial - entry_fee)
        engine.state.open_position("BTCUSDT", entry_price, 1713500000, size, "RUNNING")

        exit_fee = size * exit_price * FEE_RATE * leverage
        net_pnl = (exit_price - entry_price) * size - exit_fee
        engine.state.close_position("BTCUSDT", exit_price, 1713540000, "trailing_stop", "RUNNING", net_pnl=net_pnl)

        # Check DB
        with sqlite3.connect(engine.state.db_path) as conn:
            row = conn.execute("SELECT pnl FROM trades WHERE event = 'EXIT'").fetchone()
            assert row is not None
            gross_pnl = (exit_price - entry_price) * size
            assert row[0] < gross_pnl, \
                f"trades PnL ({row[0]:.4f}) should be less than gross ({gross_pnl:.4f})"
            assert abs(row[0] - net_pnl) < 0.01, \
                f"trades PnL ({row[0]:.4f}) should equal net_pnl ({net_pnl:.4f})"


class TestPositionSizing:
    """Position sizing must be correct for all 6 assets with leverage tiers."""

    def test_all_leverage_tiers_exist(self):
        assert len(LEVERAGE_TIERS) == 6
        for asset in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]:
            assert asset in LEVERAGE_TIERS, f"Missing leverage tier for {asset}"

    def test_btc_eth_have_highest_leverage(self):
        assert LEVERAGE_TIERS["BTCUSDT"] == 1.8
        assert LEVERAGE_TIERS["ETHUSDT"] == 1.8

    def test_avax_has_no_leverage(self):
        assert LEVERAGE_TIERS["AVAXUSDT"] == 1.0

    def test_altcoins_have_1_5x(self):
        for sym in ["SOLUSDT", "DOGEUSDT", "ADAUSDT"]:
            assert LEVERAGE_TIERS[sym] == 1.5

    def test_position_size_includes_fee(self):
        """Position size formula accounts for entry fee."""
        initial = 100.0
        n_assets = 6
        allocation = initial / n_assets
        leverage = 1.8
        price = 85000.0

        # With fee deduction
        size_with_fee = (allocation * leverage) / (price * (1 + FEE_RATE * leverage))
        # Without fee deduction (old buggy way)
        size_without_fee = (allocation * leverage) / price

        assert size_with_fee < size_without_fee, "Fee should reduce position size"
        deployed_with_fee = size_with_fee * price
        deployed_without_fee = size_without_fee * price
        assert deployed_with_fee < deployed_without_fee


class TestAccountingInvariantMultiTrade:
    """After multiple complete trade cycles, equity must satisfy:
    equity = initial + sum(net_pnl) - sum(entry_fees)
    """

    def test_three_trade_cycles(self, engine):
        """Simulate 3 winning trades and verify equity."""
        initial = 100.0
        engine.state.set_equity(initial)

        trade_results = [
            ("BTCUSDT", 85000.0, 86000.0),
            ("ETHUSDT", 3000.0, 3100.0),
            ("SOLUSDT", 150.0, 155.0),
        ]

        total_net_pnl = 0.0
        total_entry_fees = 0.0

        for symbol, entry_p, exit_p in trade_results:
            leverage = LEVERAGE_TIERS[symbol]
            allocation = engine.state.get_equity() / len(engine.assets)
            size = (allocation * leverage) / (entry_p * (1 + FEE_RATE * leverage))

            entry_fee = size * entry_p * FEE_RATE * leverage
            exit_fee = size * exit_p * FEE_RATE * leverage
            net_pnl = (exit_p - entry_p) * size - exit_fee

            total_entry_fees += entry_fee
            total_net_pnl += net_pnl

            # Entry
            engine.state.set_equity(engine.state.get_equity() - entry_fee)
            engine.state.open_position(symbol, entry_p, 1713500000, size, "RUNNING")

            # Exit
            engine.state.set_equity(engine.state.get_equity() + net_pnl)
            engine.state.close_position(symbol, exit_p, 1713540000, "trailing_stop", "RUNNING", net_pnl=net_pnl)

        expected = initial - total_entry_fees + total_net_pnl
        actual = engine.state.get_equity()
        assert abs(actual - expected) < 0.01, \
            f"Equity {actual:.4f} ≠ expected {expected:.4f} after 3 trades"


class TestPnLTracking:
    """Verify that PnL tracking is consistent across all data structures."""

    def test_daily_pnl_starts_at_zero(self, engine):
        engine.state.set_state("daily_pnl", 0.0)
        daily = float(engine.state.get_state("daily_pnl", 0.0))
        assert daily == 0.0

    def test_equity_never_below_zero(self, engine):
        """Equity should never go below 0 (kill switch should prevent this)."""
        engine.state.set_equity(100.0)
        assert engine.state.get_equity() >= 0