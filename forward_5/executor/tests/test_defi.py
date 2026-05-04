"""
Tests for DeFi Regime Collector
"""

import sqlite3
import time
from pathlib import Path

import pytest

from defi_collector import DeFiCollector, DB_PATH


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_defi.db")


@pytest.fixture
def collector(tmp_db):
    return DeFiCollector(db_path=tmp_db)


class TestDeFiCollector:
    def test_init_creates_db(self, collector, tmp_db):
        """DB and tables created on init."""
        assert Path(tmp_db).exists()
        with sqlite3.connect(tmp_db) as conn:
            tables = {t[0] for t in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            assert "defi_utilization" in tables
            assert "stablecoin_mcap" in tables
            assert "collector_meta" in tables

    def test_store_utilization(self, collector, tmp_db):
        """Pool utilization data is stored."""
        ts = int(time.time() * 1000)
        pools = [
            {
                "protocol": "aave-v3",
                "chain": "ethereum",
                "asset": "USDC",
                "total_supply_usd": 500_000_000,
                "total_borrow_usd": 400_000_000,
                "utilization_pct": 80.0,
                "supply_apy": 2.5,
                "borrow_apy": 4.1,
            },
            {
                "protocol": "aave-v3",
                "chain": "ethereum",
                "asset": "WETH",
                "total_supply_usd": 300_000_000,
                "total_borrow_usd": 150_000_000,
                "utilization_pct": 50.0,
                "supply_apy": 0.5,
                "borrow_apy": 1.2,
            },
        ]
        collector.store_utilization(ts, pools)

        with sqlite3.connect(tmp_db) as conn:
            rows = conn.execute(
                "SELECT asset, utilization_pct FROM defi_utilization WHERE ts = ?",
                (ts,)
            ).fetchall()
            assert len(rows) == 2
            assets = {r[0] for r in rows}
            assert "USDC" in assets
            assert "WETH" in assets

    def test_store_stablecoin_mcap(self, collector, tmp_db):
        """Stablecoin market cap data is stored."""
        ts = int(time.time() * 1000)
        data = [
            {"chain": "solana", "stablecoin_mcap_usd": 2_000_000_000,
             "total_mcap_usd": 100_000_000_000, "stablecoin_share_pct": 2.0},
            {"chain": "ethereum", "stablecoin_mcap_usd": 50_000_000_000,
             "total_mcap_usd": 100_000_000_000, "stablecoin_share_pct": 50.0},
        ]
        collector.store_stablecoin_mcap(ts, data)

        with sqlite3.connect(tmp_db) as conn:
            rows = conn.execute(
                "SELECT chain, stablecoin_share_pct FROM stablecoin_mcap WHERE ts = ?",
                (ts,)
            ).fetchall()
            assert len(rows) == 2

    def test_regime_overheated(self, collector, tmp_db):
        """Regime = OVERHEATED when utilization > 90%."""
        ts = int(time.time() * 1000)
        pools = [
            {"protocol": "aave-v3", "chain": "ethereum", "asset": "USDC",
             "total_supply_usd": 100, "total_borrow_usd": 95,
             "utilization_pct": 95.0, "supply_apy": 0, "borrow_apy": 0},
            {"protocol": "aave-v3", "chain": "ethereum", "asset": "WETH",
             "total_supply_usd": 100, "total_borrow_usd": 92,
             "utilization_pct": 92.0, "supply_apy": 0, "borrow_apy": 0},
        ]
        collector.store_utilization(ts, pools)
        regime = collector.get_regime("ethereum")
        assert regime["regime"] == "OVERHEATED"

    def test_regime_deleveraged(self, collector, tmp_db):
        """Regime = DELEVERAGED when utilization < 30%."""
        ts = int(time.time() * 1000)
        pools = [
            {"protocol": "aave-v3", "chain": "ethereum", "asset": "USDC",
             "total_supply_usd": 100, "total_borrow_usd": 15,
             "utilization_pct": 15.0, "supply_apy": 0, "borrow_apy": 0},
        ]
        collector.store_utilization(ts, pools)
        regime = collector.get_regime("ethereum")
        assert regime["regime"] == "DELEVERAGED"

    def test_regime_normal(self, collector, tmp_db):
        """Regime = NORMAL when utilization 30-90%."""
        ts = int(time.time() * 1000)
        pools = [
            {"protocol": "aave-v3", "chain": "solana", "asset": "USDC",
             "total_supply_usd": 100, "total_borrow_usd": 55,
             "utilization_pct": 55.0, "supply_apy": 0, "borrow_apy": 0},
        ]
        collector.store_utilization(ts, pools)
        regime = collector.get_regime("solana")
        assert regime["regime"] == "NORMAL"

    def test_regime_unknown_no_data(self, collector, tmp_db):
        """Regime = UNKNOWN when no data."""
        regime = collector.get_regime("ethereum")
        assert regime["regime"] == "UNKNOWN"

    def test_health_check(self, collector):
        """Health check returns dict."""
        health = collector.get_health()
        assert "is_healthy" in health
        assert "total_rows" in health

    def test_store_empty_data(self, collector, tmp_db):
        """Empty data doesn't cause errors."""
        collector.store_utilization(0, [])
        collector.store_stablecoin_mcap(0, [])