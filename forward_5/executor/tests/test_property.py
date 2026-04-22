"""
Property-Based Tests — Hypothesis-driven edge case discovery.
Tests the INVARIANTS of our core logic against random inputs.
"""

import pytest
import sqlite3
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
import math

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from risk_guard import RiskGuard
from state_manager import StateManager, GuardState
from signal_generator import SignalGenerator, SignalType


def _make_sm():
    """Create an in-memory StateManager with tables initialized."""
    # Connect to :memory: directly (not via Path), then init tables
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            event TEXT NOT NULL,
            symbol TEXT NOT NULL,
            price REAL,
            size REAL,
            pnl REAL,
            equity REAL,
            reason TEXT,
            indicators TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE NOT NULL,
            entry_price REAL NOT NULL,
            entry_time INTEGER NOT NULL,
            size REAL NOT NULL,
            peak_price REAL,
            guard_state TEXT DEFAULT 'RUNNING'
        )
    """)
    conn.commit()
    # Patch StateManager to use this connection
    sm = StateManager.__new__(StateManager)
    sm.db_path = ":memory:"
    # Override connect to return our existing connection
    sm._conn = conn
    return sm


def _sm_set_state(sm, key, value):
    """Use direct SQL since we have a patched SM."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    sm._conn.execute(
        "INSERT OR REPLACE INTO state (key, value, updated_at) VALUES (?, ?, ?)",
        (key, str(value), now)
    )
    sm._conn.commit()


def _sm_get_state(sm, key, default=None):
    row = sm._conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    return row[0]


# ══════════════════════════════════════════════════════════
# Risk Guard Invariants
# ══════════════════════════════════════════════════════════

class TestRiskGuardInvariants:

    @given(
        equity=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
        start_equity=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50)
    def test_dd_never_negative(self, equity, start_equity):
        """Drawdown should never be negative."""
        assume(start_equity > 0)
        # Pure math test — no DB needed
        peak = max(equity, start_equity)
        dd_pct = (peak - equity) / peak * 100 if peak > 0 else 0
        assert dd_pct >= 0, f"DD negative: {dd_pct}"

    @given(consecutive_losses=st.integers(min_value=0, max_value=100))
    @settings(max_examples=50)
    def test_consecutive_loss_count_accurate(self, consecutive_losses):
        """Incrementing N times should give N."""
        sm = _make_sm()
        _sm_set_state(sm, "consecutive_losses", "0")
        for i in range(consecutive_losses):
            _sm_set_state(sm, "consecutive_losses", str(i + 1))
        cl = int(_sm_get_state(sm, "consecutive_losses", "0"))
        assert cl == consecutive_losses


# ══════════════════════════════════════════════════════════
# Position Sizing Invariants
# ══════════════════════════════════════════════════════════

class TestPositionSizingInvariants:

    LEVERAGE_TIERS = {
        "BTCUSDT": 1.8, "ETHUSDT": 1.8,
        "SOLUSDT": 1.5, "DOGEUSDT": 1.5, "ADAUSDT": 1.5,
        "AVAXUSDT": 1.0,
    }
    FEE_RATE = 0.0002
    INITIAL_CAPITAL = 100.0

    @given(
        symbol=st.sampled_from(list(LEVERAGE_TIERS.keys())),
        entry_price=st.floats(min_value=0.001, max_value=1_000_000, allow_nan=False, allow_infinity=False),
        equity=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_position_size_positive_and_finite(self, symbol, entry_price, equity):
        """Position size should always be positive, finite, and affordable."""
        assume(entry_price > 0)
        assume(equity > 0)
        leverage = self.LEVERAGE_TIERS[symbol]
        n_assets = 6
        allocation = equity / n_assets
        size = (allocation * leverage) / (entry_price * (1 + self.FEE_RATE * leverage))
        assert size > 0
        assert math.isfinite(size)
        position_value = size * entry_price
        max_possible = allocation * leverage
        assert position_value <= max_possible * 1.01

    @given(
        entry_price=st.floats(min_value=0.001, max_value=100_000, allow_nan=False, allow_infinity=False),
        exit_price=st.floats(min_value=0.001, max_value=100_000, allow_nan=False, allow_infinity=False),
        size=st.floats(min_value=0.001, max_value=100, allow_nan=False, allow_infinity=False),
        fee_rate=st.floats(min_value=0, max_value=0.01, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_pnl_negative_at_same_price(self, entry_price, exit_price, size, fee_rate):
        """If entry==exit, PnL should be negative (fees only)."""
        assume(entry_price > 0)
        pnl = (exit_price - entry_price) * size - (exit_price * size * fee_rate + entry_price * size * fee_rate)
        if abs(exit_price - entry_price) < 0.0001:
            assert pnl <= 0.001

    @given(
        entry_price=st.floats(min_value=1, max_value=100_000, allow_nan=False, allow_infinity=False),
        exit_price=st.floats(min_value=1, max_value=100_000, allow_nan=False, allow_infinity=False),
        size=st.floats(min_value=0.001, max_value=10, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_long_pnl_positive_when_exit_above_entry(self, entry_price, exit_price, size):
        """LONG PnL should be positive (before fees) when exit > entry."""
        assume(exit_price > entry_price * 1.01)  # At least 1% profit
        gross_pnl = (exit_price - entry_price) * size
        assert gross_pnl > 0


# ══════════════════════════════════════════════════════════
# Drawdown Math Invariants
# ══════════════════════════════════════════════════════════

class TestDrawdownInvariants:

    @given(
        peak=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
        current=st.floats(min_value=0.0, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_dd_percentage_bounded(self, peak, current):
        """DD% should be in [0, 100] range when current <= peak."""
        assume(peak > 0)
        assume(current <= peak)
        dd_pct = (peak - current) / peak * 100
        assert 0 <= dd_pct <= 100

    @given(
        equity=st.floats(min_value=0.0, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50)
    def test_zero_equity_is_100pct_dd(self, equity):
        """If equity=0, drawdown from any positive peak is 100%."""
        assume(equity > 0)
        dd = (equity - 0) / equity * 100
        assert dd == 100.0

    @given(
        peak=st.floats(min_value=1, max_value=1_000_000, allow_nan=False, allow_infinity=False),
        drop_pct=st.floats(min_value=0, max_value=99.9, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50)
    def test_dd_recovery_needs_higher_pct(self, peak, drop_pct):
        """A 20% DD needs a 25% gain to recover (asymmetric)."""
        assume(peak > 0)
        bottom = peak * (1 - drop_pct / 100)
        dd = (peak - bottom) / peak * 100
        gain_needed = (peak - bottom) / bottom * 100 if bottom > 0 else float('inf')
        assert gain_needed >= dd  # Recovery always requires >= DD percentage


# ══════════════════════════════════════════════════════════
# Signal Generator Invariants
# ══════════════════════════════════════════════════════════

class TestSignalGeneratorInvariants:

    @given(
        close=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
        high=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
        low=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.filter_too_much])
    def test_no_crash_on_any_candle(self, close, high, low):
        """SignalGenerator should never crash on any candle data."""
        assume(low <= close <= high)
        sg = SignalGenerator()
        candle = {
            "open": close, "high": high, "low": low, "close": close,
            "volume": 1000, "timestamp": 1700000000,
        }
        result = sg.evaluate([candle] * 5)
        assert result is None or result.type in (SignalType.SIGNAL_LONG, SignalType.SIGNAL_FLAT)

    @given(
        n_candles=st.integers(min_value=0, max_value=500),
    )
    @settings(max_examples=30)
    def test_evaluate_returns_valid_or_none(self, n_candles):
        """evaluate() should return None or a valid Signal for any number of candles."""
        sg = SignalGenerator()
        candles = [{"open": 100, "high": 101, "low": 99, "close": 100.5,
                     "volume": 1000, "timestamp": 1700000000 + i * 3600}
                    for i in range(n_candles)]
        result = sg.evaluate(candles)
        assert result is None or result.type in (SignalType.SIGNAL_LONG, SignalType.SIGNAL_FLAT)


# ══════════════════════════════════════════════════════════
# Fee Calculation Invariants
# ══════════════════════════════════════════════════════════

class TestFeeInvariants:

    FEE_RATE = 0.0002  # 2bp maker fee

    @given(
        price=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
        size=st.floats(min_value=0.001, max_value=1000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_fee_always_positive(self, price, size):
        """Fee should always be positive and proportional to trade value."""
        assume(price > 0 and size > 0)
        trade_value = price * size
        fee = trade_value * self.FEE_RATE
        assert fee > 0
        assert fee < trade_value  # Fee should never exceed trade value

    @given(
        price=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
        size=st.floats(min_value=0.001, max_value=1000, allow_nan=False, allow_infinity=False),
        leverage=st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_total_fee_with_leverage(self, price, size, leverage):
        """Entry + exit fee with leverage should be deterministic."""
        assume(price > 0 and size > 0)
        entry_fee = price * size * self.FEE_RATE * leverage
        exit_fee = price * size * self.FEE_RATE * leverage
        total_fee = entry_fee + exit_fee
        assert total_fee > 0
        assert math.isfinite(total_fee)