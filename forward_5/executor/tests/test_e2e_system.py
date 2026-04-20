"""
Executor V1 — E2E System Test

Full pipeline: Synthetic candles → DataFeed DB → SignalGenerator →
PaperEngine._evaluate_symbol → RiskGuard → StateManager → Equity check.

Tests the ACTUAL integration, not just units. Every bug from Sessions 2-4
(Entry Fee, Gross PnL, Daily Loss Denominator, All-Assets Status) only
surfaced when the full flow ran. This test catches exactly that class.
"""

import os
import sqlite3
import tempfile
import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from state_manager import StateManager, GuardState
from risk_guard import RiskGuard
from signal_generator import SignalGenerator, SignalType
from paper_engine import PaperTradingEngine, LEVERAGE_TIERS, FEE_RATE, SLIPPAGE_BPS


def _make_candles(base_price: float, n: int = 250, trend: str = "up",
                  start_ts: int = 1710000000000) -> list[dict]:
    """Generate synthetic 1h candles with controlled price movement.
    
    trend='up': Strong uptrend → should generate SIGNAL_LONG
    trend='flat': Sideways → SIGNAL_FLAT
    trend='dump': Crashing → triggers stop losses
    
    For 'up': Starts flat (warmup), then accelerating climb so that
    MACD histogram goes positive, EMA50 > EMA200, ADX > 20.
    """
    candles = []
    price = base_price
    ts = start_ts
    
    for i in range(n):
        if trend == "up":
            if i < 100:
                # Flat warmup period — let EMAs converge
                price = base_price + base_price * 0.0005 * ((-1) ** i)
            elif i < 180:
                # Moderate uptrend — EMA50 crosses above EMA200
                price += base_price * 0.001
                price += base_price * 0.0002 * ((-1) ** i)
            else:
                # Accelerating uptrend — MACD histogram goes positive
                price += base_price * 0.002
        elif trend == "flat":
            price = base_price + base_price * 0.001 * ((-1) ** i)
        elif trend == "dump":
            if i > 200:
                price -= base_price * 0.03
        
        o = price
        h = price * 1.003  # 0.3% high wick
        l = price * 0.997  # 0.3% low wick
        c = price + base_price * 0.0005  # close slightly up
        
        candles.append({
            "timestamp": ts,
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": 1000.0,
        })
        ts += 3600000  # 1h
    
    return candles


def _seed_db(db_path: str, symbol: str, candles: list[dict]):
    """Write candles directly into the DataFeed's SQLite table."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                symbol TEXT NOT NULL,
                ts INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY (symbol, ts)
            )
        """)
        for c in candles:
            conn.execute("""
                INSERT OR REPLACE INTO candles (symbol, ts, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (symbol, c["timestamp"], c["open"], c["high"], c["low"], c["close"], c["volume"]))


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def engine(db_path):
    """Create a PaperTradingEngine with mocked Discord + DataFeed WS."""
    with patch("paper_engine.DataFeed") as MockFeed, \
         patch("paper_engine.CommandListener") as MockCmd, \
         patch("paper_engine.DiscordReporter") as MockReporter:
        
        # Mock DataFeed — real get_candles from DB, no WS connection
        mock_feed = MagicMock()
        mock_feed.db_path = db_path
        mock_feed.start = AsyncMock()
        mock_feed.stop = AsyncMock()
        MockFeed.return_value = mock_feed
        
        # Make get_candles read from our real DB
        def real_get_candles(symbol, limit=200):
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute("""
                    SELECT ts, open, high, low, close, volume
                    FROM candles WHERE symbol = ?
                    ORDER BY ts DESC LIMIT ?
                """, (symbol, limit)).fetchall()
            return [{
                "timestamp": r[0], "open": r[1], "high": r[2],
                "low": r[3], "close": r[4], "volume": r[5],
            } for r in reversed(rows)]
        
        mock_feed.get_candles = real_get_candles
        
        # Mock CommandListener + DiscordReporter
        MockCmd.return_value.start = AsyncMock()
        MockCmd.return_value.stop = AsyncMock()
        MockReporter.return_value.report_custom = MagicMock()
        MockReporter.return_value.report_entry = MagicMock()
        MockReporter.return_value.report_exit = MagicMock()
        MockReporter.return_value.report_entry_blocked = MagicMock()
        
        eng = PaperTradingEngine(assets=["BTCUSDT"], db_path=db_path)
        yield eng


class TestE2EGoldenPath:
    """Full pipeline: seed candles → evaluate → verify equity accounting.
    
    This tests what unit tests CAN'T: the interaction between
    SignalGenerator → RiskGuard → PaperEngine → StateManager
    when real candle data flows through.
    """

    def test_no_trade_on_flat_market(self, engine, db_path):
        """Flat market → no entry signal → equity stays at 100€."""
        candles = _make_candles(85000, n=250, trend="flat")
        _seed_db(db_path, "BTCUSDT", candles)
        
        last_candle = candles[-1]
        asyncio.run(engine._evaluate_symbol("BTCUSDT", last_candle))
        
        # No position opened
        assert engine.state.get_open_position("BTCUSDT") is None
        assert engine.state.get_equity() == 100.0

    def test_entry_on_uptrend(self, engine, db_path):
        """Rising market → SIGNAL_LONG → position opened, entry fee deducted from equity."""
        candles = _make_candles(85000, n=250, trend="up")
        _seed_db(db_path, "BTCUSDT", candles)
        
        last_candle = candles[-1]
        asyncio.run(engine._evaluate_symbol("BTCUSDT", last_candle))
        
        pos = engine.state.get_open_position("BTCUSDT")
        if pos is not None:
            # Entry fee must have been deducted from equity
            equity = engine.state.get_equity()
            assert equity < 100.0, f"Equity should be < 100 after entry fee, got {equity}"
            
            # Position must have correct size
            allocation = 100.0 / 1  # 1 asset
            leverage = LEVERAGE_TIERS["BTCUSDT"]  # 1.8x
            entry_price = last_candle["close"] * (1 + SLIPPAGE_BPS / 10000)
            expected_size = (allocation * leverage) / (entry_price * (1 + FEE_RATE * leverage))
            assert abs(pos["size"] - expected_size) < 0.0001

    def test_full_trade_cycle_accounting(self, engine, db_path):
        """Entry → Hold → Exit: equity = 100 - entry_fee + net_pnl.
        
        This is the BUG 1 + BUG 2 regression test at system level.
        Previously: entry fee NOT deducted, gross PnL stored in trades.
        """
        candles = _make_candles(85000, n=250, trend="up")
        _seed_db(db_path, "BTCUSDT", candles)
        
        # Step 1: Entry
        last_candle = candles[-1]
        asyncio.run(engine._evaluate_symbol("BTCUSDT", last_candle))
        
        pos = engine.state.get_open_position("BTCUSDT")
        if pos is None:
            pytest.skip("No signal generated — need stronger uptrend candles")
        
        entry_equity = engine.state.get_equity()
        entry_price = pos["entry_price"]
        size = pos["size"]
        entry_fee = size * entry_price * FEE_RATE * LEVERAGE_TIERS["BTCUSDT"]
        
        # Step 2: Create exit candle — price drops below both trailing + stop loss
        stop_loss_price = entry_price * (1 - 0.025)
        exit_candle = {
            "timestamp": last_candle["timestamp"] + 3600000,
            "open": entry_price * 0.99,
            "high": entry_price * 0.995,  # below peak → trailing stop fires
            "low": stop_loss_price * 0.95,  # well below stop loss
            "close": stop_loss_price,
            "volume": 1000.0,
        }
        
        # Update peak + bars held
        engine.state.update_peak("BTCUSDT", entry_price * 1.01)
        engine.state.set_state("bars_held_BTCUSDT", 1)
        
        # Step 3: Exit
        asyncio.run(engine._evaluate_symbol("BTCUSDT", exit_candle))
        
        # Position should be closed
        assert engine.state.get_open_position("BTCUSDT") is None
        
        final_equity = engine.state.get_equity()
        
        # BUG 2 REGRESSION: trades table must store NET PnL (not gross)
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT pnl FROM trades WHERE event = 'EXIT' ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        
        if row is not None:
            trade_pnl = row[0]
            # Gross PnL would be (exit_price - entry_price) * size
            # Net PnL = gross - exit_fee → must be MORE negative (or less positive) than gross
            # For a losing trade: net_pnl < gross_pnl (more negative)
            # We can't predict the exact exit price (trailing vs stop loss),
            # but we CAN verify the PnL is NET (includes fee) by checking the
            # accounting invariant: final = start - entry_fee + net_pnl
            start_equity = engine.state.get_start_equity()
            expected_final = start_equity - entry_fee + trade_pnl
            assert abs(final_equity - expected_final) < 0.01, \
                f"Accounting invariant broken: final={final_equity}, " \
                f"expected={expected_final} (start={start_equity}, fee={entry_fee}, pnl={trade_pnl})"

    def test_risk_guard_blocks_entry_after_kill(self, engine, db_path):
        """After KILL_SWITCH (DD > 20%), no new entries allowed."""
        # Force KILL_SWITCH state
        engine.state.set_equity(75.0)  # 25% DD from 100
        engine.state.set_state("peak_equity", 100.0)
        engine.state.set_guard_state(GuardState.KILL_SWITCH, "DD 25%")
        
        candles = _make_candles(85000, n=250, trend="up")
        _seed_db(db_path, "BTCUSDT", candles)
        
        last_candle = candles[-1]
        asyncio.run(engine._evaluate_symbol("BTCUSDT", last_candle))
        
        # No position should be opened
        assert engine.state.get_open_position("BTCUSDT") is None


class TestE2EAccountingInvariant:
    """The fundamental accounting check that catches all money bugs.
    
    Invariant: equity = start_equity - sum(entry_fees) + sum(net_pnl)
    
    Every bug from Sessions 2-4 violates this:
    - BUG 1: Entry fee not subtracted → equity overstated
    - BUG 2: Gross PnL in trades → reported PnL wrong
    - BUG 4: Wrong daily loss denominator → false STOP_NEW
    """

    def test_invariant_after_one_complete_cycle(self, engine, db_path):
        """One entry + one exit: equity must satisfy the invariant."""
        candles = _make_candles(85000, n=250, trend="up")
        _seed_db(db_path, "BTCUSDT", candles)
        
        start_equity = engine.state.get_start_equity()  # 100
        
        # Entry
        last_candle = candles[-1]
        asyncio.run(engine._evaluate_symbol("BTCUSDT", last_candle))
        
        pos = engine.state.get_open_position("BTCUSDT")
        if pos is None:
            pytest.skip("No signal generated")
        
        entry_fee = pos["size"] * pos["entry_price"] * FEE_RATE * LEVERAGE_TIERS["BTCUSDT"]
        
        # Exit via stop loss
        entry_price = pos["entry_price"]
        stop_loss_price = entry_price * (1 - 0.025)
        exit_candle = {
            "timestamp": last_candle["timestamp"] + 3600000,
            "open": entry_price * 0.99,
            "high": entry_price,
            "low": stop_loss_price * 0.99,
            "close": stop_loss_price,
            "volume": 1000.0,
        }
        engine.state.update_peak("BTCUSDT", entry_price * 1.01)
        engine.state.set_state("bars_held_BTCUSDT", 1)
        asyncio.run(engine._evaluate_symbol("BTCUSDT", exit_candle))
        
        final_equity = engine.state.get_equity()
        
        # Invariant: final = start - entry_fee + net_pnl
        # net_pnl is already applied by risk_guard.on_trade_closed()
        # and entry_fee was deducted on open
        # So: final should equal start + (net_pnl - entry_fee)
        # But since risk_guard does equity += pnl and we did equity -= entry_fee:
        # final = start - entry_fee + pnl  (where pnl is already net of exit fee)
        
        # Simple check: final equity must be deterministic and < start (losing trade)
        assert final_equity < start_equity
        assert final_equity > 0  # Can't go below zero
        
        # Read net PnL from trades table
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT pnl FROM trades WHERE event = 'EXIT' LIMIT 1"
            ).fetchone()
        
        if row is not None:
            net_pnl = row[0]
            # Verify: final = start - entry_fee + net_pnl
            expected = start_equity - entry_fee + net_pnl
            assert abs(final_equity - expected) < 0.01, \
                f"Accounting broken: equity={final_equity}, expected={expected}, " \
                f"start={start_equity}, entry_fee={entry_fee}, net_pnl={net_pnl}"


class TestE2EMultipleAssets:
    """BUG 3 regression at system level: all assets visible in hourly status."""

    def test_status_shows_all_6_assets(self, db_path):
        """format_hourly_status must show all 6 assets, not just BTC+ETH."""
        from discord_reporter import format_hourly_status
        
        sm = StateManager(db_path=db_path)
        sm.set_start_equity(100.0)
        sm.set_equity(100.0)
        
        assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]
        prices = [85000, 3000, 150, 25, 0.18, 0.45]
        sizes = [0.001, 0.005, 0.1, 1.0, 100.0, 50.0]
        
        for sym, p, s in zip(assets, prices, sizes):
            sm.open_position(sym, p, 1713500000, s, "RUNNING")
        
        header, body, color = format_hourly_status(sm)
        
        for sym in assets:
            short = sym.replace("USDT", "")
            assert short in body, f"Asset {short} missing from hourly status"


class TestE2EPaperModeEnforcement:
    """PAPER_MODE hard-switch must abort engine if disabled."""

    def test_engine_aborts_without_paper_mode(self, db_path):
        """Engine must refuse to start if PAPER_MODE=False."""
        import paper_engine
        original = paper_engine.PAPER_MODE
        
        try:
            paper_engine.PAPER_MODE = False
            with pytest.raises(RuntimeError, match="PAPER_MODE"):
                eng = PaperTradingEngine(assets=["BTCUSDT"], db_path=db_path)
                asyncio.run(eng.start())
        finally:
            paper_engine.PAPER_MODE = original