"""
Tests for Liquidation Collector + Coinalyze Backfill
"""

import sqlite3
import time
import json
from pathlib import Path

import pytest

from liquidation_collector import LiquidationCollector, DB_PATH
from coinalyze_backfill import CoinalyzeBackfill


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary DB path."""
    return str(tmp_path / "test_liquidations.db")


@pytest.fixture
def collector(tmp_db):
    """Create a collector with temp DB."""
    c = LiquidationCollector(db_path=tmp_db)
    return c


# ── LiquidationCollector Tests ──

class TestLiquidationCollector:
    def test_init_creates_db(self, collector, tmp_db):
        """DB and tables are created on init."""
        assert Path(tmp_db).exists()
        with sqlite3.connect(tmp_db) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t[0] for t in tables}
            assert "liquidation_ticks" in table_names
            assert "liquidation_1h" in table_names
            assert "collector_meta" in table_names

    def test_parse_event_sell_is_long(self, collector):
        """S=SELL means Long liquidation."""
        event = {
            "e": "forceOrder",
            "o": {
                "s": "BTCUSDT",
                "S": "SELL",
                "p": "65000.00",
                "ap": "64995.50",
                "q": "0.5",
                "T": 1700000000000,
            }
        }
        tick = collector._parse_event(event)
        assert tick is not None
        assert tick["symbol"] == "BTCUSDT"
        assert tick["liq_side"] == "long"
        assert tick["notional"] > 0

    def test_parse_event_buy_is_short(self, collector):
        """S=BUY means Short liquidation."""
        event = {
            "o": {
                "s": "ETHUSDT",
                "S": "BUY",
                "p": "3500.00",
                "ap": "3505.00",
                "q": "2.0",
                "T": 1700000060000,
            }
        }
        tick = collector._parse_event(event)
        assert tick is not None
        assert tick["symbol"] == "ETHUSDT"
        assert tick["liq_side"] == "short"

    def test_parse_event_invalid_returns_none(self, collector):
        """Invalid events return None."""
        assert collector._parse_event({}) is None
        assert collector._parse_event({"o": {"s": ""}}) is None
        assert collector._parse_event(None) is None

    def test_store_and_read_tick(self, collector, tmp_db):
        """Tick is stored and readable."""
        tick = {
            "ts": 1700000000000,
            "symbol": "BTCUSDT",
            "liq_side": "long",
            "price": 65000.0,
            "qty": 0.5,
            "notional": 32497.75,
        }
        collector._store_tick(tick)

        with sqlite3.connect(tmp_db) as conn:
            rows = conn.execute("SELECT * FROM liquidation_ticks").fetchall()
            assert len(rows) == 1
            assert rows[0][1] == "BTCUSDT"
            assert rows[0][2] == "long"

    def test_rollup_1h(self, collector, tmp_db):
        """Rollup aggregates ticks into 1h buckets."""
        # Insert ticks for 2 hours
        base_ts = 1700000000000  # hour 0
        for i in range(5):
            collector._store_tick({
                "ts": base_ts + i * 1000,  # same hour
                "symbol": "BTCUSDT",
                "liq_side": "long",
                "price": 65000.0,
                "qty": 1.0,
                "notional": 65000.0,
            })
        for i in range(3):
            collector._store_tick({
                "ts": base_ts + 3600000 + i * 1000,  # next hour
                "symbol": "BTCUSDT",
                "liq_side": "short",
                "price": 64000.0,
                "qty": 0.5,
                "notional": 32000.0,
            })

        collector.rollup_1h()

        with sqlite3.connect(tmp_db) as conn:
            rows = conn.execute(
                "SELECT ts_hour, long_notional, short_notional FROM liquidation_1h ORDER BY ts_hour"
            ).fetchall()
            assert len(rows) >= 1
            # First hour should have long liquidations
            first_hour = [r for r in rows if r[0] == (base_ts // 3600000) * 3600000]
            if first_hour:
                assert first_hour[0][1] > 0  # long_notional

    def test_get_1h(self, collector, tmp_db):
        """get_1h returns aggregate data."""
        # Insert an aggregate row directly
        ts_hour = (int(time.time() * 1000) // 3600000) * 3600000
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "INSERT INTO liquidation_1h (ts_hour, symbol, long_notional, short_notional) "
                "VALUES (?, 'SOLUSDT', 500000, 200000)",
                (ts_hour,)
            )

        data = collector.get_1h("SOLUSDT", hours=24)
        assert len(data) >= 1
        assert data[0]["long_notional"] == 500000

    def test_health_check(self, collector):
        """Health check returns status dict."""
        collector._update_heartbeat()
        health = collector.get_health()
        assert health["status"] == "running"
        assert health["is_healthy"] is True
        assert health["tick_count"] >= 0

    def test_stop_updates_status(self, collector, tmp_db):
        """Stopping collector updates meta status."""
        collector._running = True  # must be running first
        collector._update_heartbeat()
        collector.stop()
        with sqlite3.connect(tmp_db) as conn:
            status = conn.execute(
                "SELECT value FROM collector_meta WHERE key = 'status'"
            ).fetchone()
            assert status[0] == "stopped"


# ── CoinalyzeBackfill Tests ──

class TestCoinalyzeBackfill:
    def test_store_backfill(self, tmp_db):
        """Backfill data is stored correctly."""
        backfill = CoinalyzeBackfill(api_key="test_key", db_path=tmp_db)

        data = [
            {"ts_hour": 1700000000000, "long_notional": 100000, "short_notional": 50000,
             "long_count": 0, "short_count": 0},
            {"ts_hour": 1700003600000, "long_notional": 200000, "short_notional": 80000,
             "long_count": 0, "short_count": 0},
        ]

        backfill.store_backfill("BTCUSDT", data)

        with sqlite3.connect(tmp_db) as conn:
            rows = conn.execute(
                "SELECT ts_hour, long_notional, source FROM liquidation_1h WHERE symbol = 'BTCUSDT' ORDER BY ts_hour"
            ).fetchall()
            assert len(rows) == 2
            assert rows[0][1] == 100000
            assert rows[0][2] == "coinalyze"

    def test_store_empty_data(self, tmp_db):
        """Empty data list doesn't cause errors."""
        backfill = CoinalyzeBackfill(api_key="test_key", db_path=tmp_db)
        backfill.store_backfill("BTCUSDT", [])  # should not raise

    def test_coinalyze_not_overwrite_live(self, tmp_db):
        """Coinalyze backfill doesn't overwrite live WS data."""
        collector = LiquidationCollector(db_path=tmp_db)

        # Insert "live" data
        ts_hour = 1700000000000
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "INSERT INTO liquidation_1h (ts_hour, symbol, long_notional, short_notional, source) "
                "VALUES (?, 'BTCUSDT', 999999, 888888, 'binance')",
                (ts_hour,)
            )

        # Try to backfill same hour with different data
        backfill = CoinalyzeBackfill(api_key="test_key", db_path=tmp_db)
        data = [{"ts_hour": ts_hour, "long_notional": 100, "short_notional": 50,
                 "long_count": 0, "short_count": 0}]
        backfill.store_backfill("BTCUSDT", data)

        # Live data should be preserved
        with sqlite3.connect(tmp_db) as conn:
            row = conn.execute(
                "SELECT long_notional, source FROM liquidation_1h WHERE ts_hour = ? AND symbol = 'BTCUSDT'",
                (ts_hour,)
            ).fetchone()
            assert row[0] == 999999  # not overwritten