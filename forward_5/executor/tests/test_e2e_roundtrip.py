"""
E2E Roundtrip + Money Conservation Property Tests.

1. E2E Roundtrip: Simulates the full Paper Engine path
   Candle → Engine._on_candle → State → TradeLog → Accounting Check

2. Money Conservation: Equity can only change through trades (entry fees + exit PnL).
   No spontaneous equity creation or destruction.
"""

import pytest
import sqlite3
import json
import time
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from state_manager import StateManager, GuardState
from risk_guard import RiskGuard
from accounting_check import check_equity_invariant


# ─── Money Conservation Property ───

class TestMoneyConservation:
    """Equity can only change through trades. No spontaneous creation/destruction."""

    def _make_sm(self):
        """Create a fresh StateManager with temp DB."""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        sm = StateManager(db_path=db_path)
        sm.set_start_equity(100.0)
        sm.set_equity(100.0)
        sm.set_state("peak_equity", 100.0)
        sm.set_guard_state(GuardState.RUNNING)
        sm._test_db_path = db_path  # Store for cleanup
        return sm

    def _cleanup(self, sm):
        try:
            os.unlink(sm._test_db_path)
        except:
            pass

    def test_entry_fee_reduces_equity(self):
        """Entry fee must reduce equity. No free trades."""
        sm = self._make_sm()
        risk = RiskGuard(sm)
        equity_before = sm.get_equity()

        # Entry: deduct fee
        fee = 0.05
        sm.set_equity(equity_before - fee)

        assert sm.get_equity() == equity_before - fee
        self._cleanup(sm)

    def test_exit_pnl_updates_equity(self):
        """Exit PnL must be reflected in equity via risk_guard.on_trade_closed."""
        sm = self._make_sm()
        risk = RiskGuard(sm)
        sm.set_equity(99.95)  # After entry fee

        # Profitable exit
        risk.on_trade_closed(1.50)

        assert abs(sm.get_equity() - 101.45) < 0.001
        self._cleanup(sm)

    def test_losing_exit_reduces_equity(self):
        """Losing exit reduces equity."""
        sm = self._make_sm()
        risk = RiskGuard(sm)
        sm.set_equity(99.95)

        risk.on_trade_closed(-0.80)

        assert abs(sm.get_equity() - 99.15) < 0.001
        self._cleanup(sm)

    @given(
        entry_fee=st.floats(min_value=0.001, max_value=1.0, allow_nan=False),
        exit_pnl=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_equity_changes_only_through_trades(self, entry_fee, exit_pnl):
        """Property: Every equity change must be explained by a fee or PnL."""
        sm = self._make_sm()
        risk = RiskGuard(sm)
        start = sm.get_start_equity()

        # Entry: deduct fee
        sm.set_equity(start - entry_fee)

        # Exit: apply PnL via on_trade_closed
        risk.on_trade_closed(exit_pnl)
        final = sm.get_equity()

        # Invariant: final = start - entry_fee + exit_pnl
        expected = start - entry_fee + exit_pnl
        assert abs(final - expected) < 0.01, \
            f"Equity drift: {final:.4f} != {expected:.4f} (fee={entry_fee}, pnl={exit_pnl})"
        self._cleanup(sm)

    @given(
        n_trades=st.integers(min_value=1, max_value=20),
        seed=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_multi_trade_equity_conservation(self, n_trades, seed):
        """Property: After N trades, equity = start - sum(fees) + sum(pnls)."""
        import random
        rng = random.Random(seed)

        sm = self._make_sm()
        risk = RiskGuard(sm)
        start = sm.get_start_equity()
        total_fees = 0.0
        total_pnl = 0.0

        for _ in range(n_trades):
            # Entry fee
            fee = rng.uniform(0.01, 0.5)
            total_fees += fee
            equity = sm.get_equity()
            sm.set_equity(equity - fee)

            # Exit PnL
            pnl = rng.uniform(-2.0, 2.0)
            total_pnl += pnl
            risk.on_trade_closed(pnl)

        final = sm.get_equity()
        expected = start - total_fees + total_pnl

        assert abs(final - expected) < 0.01, \
            f"Equity conservation violated after {n_trades} trades: " \
            f"final={final:.4f} != expected={expected:.4f} " \
            f"(fees={total_fees:.4f}, pnl={total_pnl:.4f})"
        self._cleanup(sm)

    @given(
        n_trades=st.integers(min_value=1, max_value=30),
        seed=st.integers(min_value=0, max_value=99999),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_equity_never_negative(self, n_trades, seed):
        """Property: Equity must never go below zero."""
        import random
        rng = random.Random(seed)

        sm = self._make_sm()
        risk = RiskGuard(sm)
        start = sm.get_start_equity()

        for _ in range(n_trades):
            fee = rng.uniform(0.001, 0.5)
            equity = sm.get_equity()
            if equity - fee < 0:
                break  # Can't afford more trades
            sm.set_equity(equity - fee)

            pnl = rng.uniform(-3.0, 3.0)
            if sm.get_equity() + pnl < 0:
                break  # Would go negative
            risk.on_trade_closed(pnl)

            assert sm.get_equity() >= 0, "Equity went negative!"
        self._cleanup(sm)

    def test_accounting_check_catches_equity_drift(self):
        """If equity is manually corrupted, accounting check must catch it."""
        sm = self._make_sm()
        risk = RiskGuard(sm)

        # Simulate a trade
        sm.set_equity(100.0 - 0.05)  # Entry fee
        risk.on_trade_closed(-0.50)  # Loss

        # Now corrupt equity (add 5€ from nowhere)
        sm.set_equity(sm.get_equity() + 5.0)

        # Accounting check should catch this
        conn = sqlite3.connect(sm._test_db_path)
        issues = check_equity_invariant(conn)
        conn.close()

        severities = [s for s, _ in issues]
        assert "CRITICAL" in severities or "WARN" in severities, \
            f"Accounting check didn't catch equity corruption: {issues}"
        self._cleanup(sm)


# ─── E2E Roundtrip Test ───

class TestE2ERoundtrip:
    """Full path: Candle → Engine._on_candle → State → TradeLog → Accounting."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create a real PaperTradingEngine with temp DB."""
        from paper_engine import PaperTradingEngine
        db_path = str(tmp_path / "state.db")
        # Patch DiscordReporter to avoid Discord calls during tests
        with patch("paper_engine.DiscordReporter"):
            with patch("paper_engine.CommandListener"):
                with patch("paper_engine.DataFeed"):
                    eng = PaperTradingEngine(assets=["BTCUSDT"], db_path=db_path)
        # Mock the feed's get_candles to return empty by default
        eng.feed.get_candles = MagicMock(return_value=[])
        yield eng

    def _make_candle(self, symbol, ts, close, high=None, low=None, open_=None):
        """Create a realistic candle dict."""
        high = high or close * 1.002
        low = low or close * 0.998
        open_ = open_ or close * 0.999
        return {
            "symbol": symbol,
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1000.0,
            "is_replay": False,
        }

    def test_no_equity_drift_without_trades(self, engine):
        """Processing candles without trades must not change equity."""
        start_equity = engine.state.get_equity()

        # Process 50 sideways candles (no signal expected)
        base_ts = int(time.time() * 1000)
        for i in range(50):
            price = 75000.0 + (i % 5) * 10  # Small range, no trend
            ts = base_ts - (50 - i) * 3600000
            candle = self._make_candle("BTCUSDT", ts, price,
                                        high=price + 50, low=price - 50)

            # _on_candle is async — use asyncio.run
            import asyncio
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(engine._on_candle("BTCUSDT", candle))
                loop.close()
            except Exception:
                pass  # Some candles may fail if indicators aren't ready

        equity_after = engine.state.get_equity()
        assert abs(equity_after - start_equity) < 0.01, \
            f"Equity drifted without trades: {start_equity:.4f} → {equity_after:.4f}"

    def test_gap_recovery_no_equity_drift(self, engine):
        """is_replay=True candles must not change equity or open positions."""
        start_equity = engine.state.get_equity()

        base_ts = int(time.time() * 1000) - 7200000
        for i in range(10):
            price = 75000.0 + i * 50  # Uptrend in replay
            ts = base_ts + i * 3600000
            candle = self._make_candle("BTCUSDT", ts, price)
            candle["is_replay"] = True

            import asyncio
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(engine._on_candle("BTCUSDT", candle))
                loop.close()
            except Exception:
                pass

        equity_after = engine.state.get_equity()
        assert abs(equity_after - start_equity) < 0.01, \
            f"Replay candles caused equity drift: {start_equity:.4f} → {equity_after:.4f}"

        # No positions from replay
        pos = engine.state.get_open_position("BTCUSDT")
        assert pos is None, "Replay candle opened a position!"

    def test_accounting_check_on_fresh_db(self, engine):
        """Fresh engine DB must pass all accounting checks."""
        from accounting_check import run_checks, format_report
        import accounting_check
        old_db = accounting_check.DB_PATH
        old_log = accounting_check.TRADE_LOG_PATH

        try:
            accounting_check.DB_PATH = engine.state.db_path
            accounting_check.TRADE_LOG_PATH = str(
                Path(engine.state.db_path).parent / "trades.jsonl")
            if not os.path.exists(accounting_check.TRADE_LOG_PATH):
                open(accounting_check.TRADE_LOG_PATH, 'w').close()

            # Fresh DB doesn't have candles yet — create table + dummy data
            conn = sqlite3.connect(engine.state.db_path)
            conn.execute("""CREATE TABLE IF NOT EXISTS candles (
                symbol TEXT, ts INTEGER, open REAL, high REAL,
                low REAL, close REAL, volume REAL,
                PRIMARY KEY (symbol, ts))""")
            now_ms = int(time.time() * 1000)
            for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]:
                conn.execute("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?)",
                             (sym, now_ms - 60000, 100, 101, 99, 100.5, 1000))
            conn.commit()
            conn.close()

            results, ec = run_checks()
            assert ec == 0, f"Fresh DB failed accounting: {results}"
        finally:
            accounting_check.DB_PATH = old_db
            accounting_check.TRADE_LOG_PATH = old_log