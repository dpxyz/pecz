"""
Regression tests for V2 Pipeline bugs found 2026-05-03.

Bug 1: get_candles() missing 'symbol' field — SignalGeneratorV2 uses
       last_candle.get('symbol', 'UNKNOWN') to route signals, but DataFeed.get_candles()
       never included the symbol field, causing ALL signals to evaluate as 'UNKNOWN'
       and produce SIGNAL_FLAT with reason 'no V2 signal (BTC/ETH/SOL only)'.

Bug 2: EMA200 regime not computed — backfill only fetched 48h (49 candles),
       but EMA200 needs 200+. Also _compute_initial_regime() ran in __init__
       before backfill, so bull200 was always None.

Bug 3: _on_candle_v2 never called — DataFeedV2.__init__ set self.on_candle
       to the engine callback AFTER the base class stored it, but the base
       _poll_candles called self.on_candle which was the engine callback directly,
       bypassing the V2 regime computation.
"""

import sqlite3
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_feed import DataFeed, BACKFILL_HOURS


class TestBug1GetCandlesMissingSymbol:
    """Bug: get_candles() returned dicts without 'symbol' field.

    This caused SignalGeneratorV2.evaluate() to see symbol='UNKNOWN'
    and skip all BTC/ETH/SOL signal logic.
    """

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_feed.db")
        self.feed = DataFeed(db_path=self.db_path, assets=["BTCUSDT"])
        # Insert test candles
        with sqlite3.connect(self.db_path) as conn:
            for i in range(10):
                ts = 1700000000000 + i * 3600000
                conn.execute(
                    "INSERT OR IGNORE INTO candles (symbol, ts, open, high, low, close, volume) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("BTCUSDT", ts, 50000 + i, 50100 + i, 49900 + i, 50000 + i, 100),
                )

    def test_get_candles_includes_symbol_field(self):
        """get_candles() must include 'symbol' in every candle dict."""
        candles = self.feed.get_candles("BTCUSDT", limit=10)
        assert len(candles) == 10
        for c in candles:
            assert "symbol" in c, f"Candle missing 'symbol' key: {c.keys()}"
            assert c["symbol"] == "BTCUSDT"

    def test_get_candles_symbol_matches_parameter(self):
        """The symbol field in candles must match the requested symbol."""
        # Add ETH candles too
        with sqlite3.connect(self.db_path) as conn:
            for i in range(5):
                ts = 1700000000000 + i * 3600000
                conn.execute(
                    "INSERT OR IGNORE INTO candles (symbol, ts, open, high, low, close, volume) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("ETHUSDT", ts, 3000 + i, 3100 + i, 2900 + i, 3000 + i, 200),
                )
        eth_candles = self.feed.get_candles("ETHUSDT", limit=5)
        for c in eth_candles:
            assert c["symbol"] == "ETHUSDT"


class TestBug2BackfillHoursEnoughForEMA200:
    """Bug: BACKFILL_HOURS was 48, giving only ~49 candles.
    EMA200 needs 200+ candles. Now BACKFILL_HOURS=240 (10 days).
    """

    def test_backfill_hours_sufficient_for_ema200(self):
        """BACKFILL_HOURS must be >= 200 to provide enough candles for EMA200."""
        # 1h candles * BACKFILL_HOURS = number of candles
        # Need at least 200 for EMA200 warmup
        assert BACKFILL_HOURS >= 200, (
            f"BACKFILL_HOURS={BACKFILL_HOURS} too low for EMA200. "
            f"Need >= 200 (currently {BACKFILL_HOURS})."
        )

    def test_get_candles_limit_210(self):
        """get_candles() with limit=210 should return candles with symbol field."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_feed.db")
        self.feed = DataFeed(db_path=self.db_path, assets=["SOLUSDT"])
        with sqlite3.connect(self.db_path) as conn:
            for i in range(220):
                ts = 1700000000000 + i * 3600000
                conn.execute(
                    "INSERT OR IGNORE INTO candles (symbol, ts, open, high, low, close, volume) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("SOLUSDT", ts, 25 + i * 0.01, 25.5 + i * 0.01,
                     24.5 + i * 0.01, 25 + i * 0.01, 1000),
                )
        candles = self.feed.get_candles("SOLUSDT", limit=210)
        assert len(candles) == 210
        assert candles[0]["symbol"] == "SOLUSDT"
        assert candles[-1]["symbol"] == "SOLUSDT"


class TestBug3OnCandleV2Routing:
    """Bug: DataFeedV2._on_candle_v2 was never called because the base class
    stored self.on_candle = engine_callback, and V2's __init__ didn't replace it
    with its own wrapper until AFTER super().__init__ had already stored it.

    The fix: DataFeedV2.__init__ now sets self.on_candle = self._on_candle_v2
    and stores the original in self._original_on_candle.
    """

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_feed_v2.db")

    def test_on_candle_is_v2_wrapper(self):
        """DataFeedV2.on_candle must be _on_candle_v2, not the raw engine callback."""
        from data_feed_v2 import DataFeedV2

        async def dummy_engine_callback(symbol, candle):
            pass

        feed = DataFeedV2(db_path=self.db_path, assets=["BTCUSDT"],
                         on_candle=dummy_engine_callback)

        assert feed.on_candle == feed._on_candle_v2, (
            "DataFeedV2.on_candle must point to _on_candle_v2 for regime computation"
        )

    def test_original_on_candle_preserved(self):
        """The engine's original callback must be stored in _original_on_candle."""
        from data_feed_v2 import DataFeedV2

        async def dummy_engine_callback(symbol, candle):
            pass

        feed = DataFeedV2(db_path=self.db_path, assets=["BTCUSDT"],
                         on_candle=dummy_engine_callback)

        assert feed._original_on_candle == dummy_engine_callback, (
            "_original_on_candle must store the engine's callback"
        )

    def test_bull200_dict_exists(self):
        """DataFeedV2 must have _bull200 dict initialized (even if empty before backfill)."""
        from data_feed_v2 import DataFeedV2

        feed = DataFeedV2(db_path=self.db_path, assets=["BTCUSDT"])

        assert hasattr(feed, "_bull200"), "_bull200 dict must exist"
        assert isinstance(feed._bull200, dict), "_bull200 must be a dict"

    def test_get_regime_returns_none_before_backfill(self):
        """get_regime() returns None when no regime data computed yet."""
        from data_feed_v2 import DataFeedV2

        feed = DataFeedV2(db_path=self.db_path, assets=["BTCUSDT"])

        result = feed.get_regime("BTCUSDT")
        assert result is None, "get_regime should return None before regime is computed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])