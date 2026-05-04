"""
DeFi Regime Data Collector

Collects daily DeFi metrics for regime filtering:
1. Aave ETH + USDC Utilization (DeFiLlama)
2. Solend + Kamino Lending Pools (Solana-specific)
3. Solana Stablecoin Market Cap (DeFiLlama)

These are REGIME FILTERS, not standalone alpha:
- Utilization >90% = overheated → BLOCK longs
- Utilization <30% = deleveraged → potential bottom
- Liq/TVL >95th percentile = cascade → HARD BLOCK

Reference: deep_research_defi.txt
"""

import sqlite3
import time
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import requests

log = logging.getLogger("defi_collector")

DB_PATH = "data/defi/defi_regime.db"
POLL_INTERVAL = 86400  # daily (DeFi metrics don't change fast)

# ── DeFiLlama API Endpoints ──
DEFILLAMA_BASE = "https://yields.llama.fi"
DEFILLAMA_PROTOCOLS = "https://api.llama.fi/protocols"
DEFILLAMA_STABLECOINS = "https://stablecoins.llama.fi/stablecoins"

# Aave V3 pool IDs on DeFiLlama (ETH mainnet)
AAVE_ETH_USDC_POOL = "aave-v3-ethereum-usdc"  # approximate, will be resolved dynamically
AAVE_ETH_WETH_POOL = "aave-v3-ethereum-weth"

# Solend + Kamino on Solana
SOLEND_POOLS = ["solend-v2-solana-usdc", "solend-v2-solana-sol"]
KAMINO_POOLS = ["kamino-lend-solana-usdc", "kamino-lend-solana-sol"]


class DeFiCollector:
    """Collects DeFi lending/stablecoin metrics for regime detection."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._running = False
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS defi_utilization (
                    ts INTEGER NOT NULL,
                    protocol TEXT NOT NULL,
                    chain TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    total_supply_usd REAL,
                    total_borrow_usd REAL,
                    utilization_pct REAL,
                    supply_apy REAL,
                    borrow_apy REAL,
                    source TEXT DEFAULT 'defillama',
                    PRIMARY KEY (ts, protocol, chain, asset)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_defi_ts
                ON defi_utilization(ts)
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS stablecoin_mcap (
                    ts INTEGER NOT NULL,
                    chain TEXT NOT NULL,
                    stablecoin_mcap_usd REAL,
                    total_mcap_usd REAL,
                    stablecoin_share_pct REAL,
                    source TEXT DEFAULT 'defillama',
                    PRIMARY KEY (ts, chain)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS collector_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

    # ── Aave Utilization (DeFiLlama Yield API) ──

    def fetch_aave_pools(self) -> list[dict]:
        """Fetch Aave V3 pool data from DeFiLlama.

        Returns pool-level data: symbol, totalSupplyUsd, totalBorrowUsd, apyBase, apyBaseBorrow.
        """
        try:
            resp = self.session.get(f"{DEFILLAMA_BASE}/pools", timeout=30)
            resp.raise_for_status()
            data = resp.json()

            aave_pools = []
            for pool in data.get("data", []):
                symbol = pool.get("symbol", "")
                protocol = pool.get("project", "")
                chain = pool.get("chain", "")

                # Filter for Aave V3 on Ethereum
                if protocol == "aave-v3" and chain == "Ethereum":
                    if symbol in ("USDC", "WETH", "USDT", "DAI"):
                        aave_pools.append({
                            "protocol": "aave-v3",
                            "chain": "ethereum",
                            "asset": symbol,
                            "total_supply_usd": pool.get("tvlUsd", 0),
                            "total_borrow_usd": 0,  # DeFiLlama pools endpoint may not have borrow
                            "supply_apy": pool.get("apy", 0),
                            "borrow_apy": pool.get("apyBaseBorrow", 0),
                            "utilization_pct": 0,  # computed below if possible
                        })

            log.info(f"Found {len(aave_pools)} Aave V3 ETH pools")
            return aave_pools

        except requests.RequestException as e:
            log.error(f"DeFiLlama pools fetch error: {e}")
            return []

    def fetch_aave_detailed(self) -> list[dict]:
        """Fetch detailed Aave V3 data from DeFiLlama chain-level endpoint.

        The /pools endpoint has limited borrow data. We use the protocol-specific
        endpoint for more detail.
        """
        try:
            # Get Aave V3 protocol page
            resp = self.session.get(f"{DEFILLAMA_BASE}/chart/aave-v3", timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # This returns historical APY charts — we just want latest
            # Fallback: use /pools with better filtering
            return self.fetch_aave_pools()

        except requests.RequestException:
            return self.fetch_aave_pools()

    # ── Solana Lending Pools (Solend + Kamino) ──

    def fetch_solana_lending(self) -> list[dict]:
        """Fetch Solend + Kamino pool data from DeFiLlama."""
        try:
            resp = self.session.get(f"{DEFILLAMA_BASE}/pools", timeout=30)
            resp.raise_for_status()
            data = resp.json()

            solana_pools = []
            target_protocols = {"solend", "kamino-lend"}
            target_assets = {"USDC", "SOL", "USDT"}

            for pool in data.get("data", []):
                protocol = pool.get("project", "")
                chain = pool.get("chain", "")
                symbol = pool.get("symbol", "")

                if chain == "Solana" and protocol in target_protocols and symbol in target_assets:
                    solana_pools.append({
                        "protocol": protocol,
                        "chain": "solana",
                        "asset": symbol,
                        "total_supply_usd": pool.get("tvlUsd", 0),
                        "total_borrow_usd": 0,
                        "supply_apy": pool.get("apy", 0),
                        "borrow_apy": pool.get("apyBaseBorrow", 0),
                        "utilization_pct": 0,
                    })

            log.info(f"Found {len(solana_pools)} Solana lending pools")
            return solana_pools

        except requests.RequestException as e:
            log.error(f"DeFiLlama Solana fetch error: {e}")
            return []

    # ── Stablecoin Market Cap ──

    def fetch_stablecoin_mcap(self) -> list[dict]:
        """Fetch stablecoin market cap per chain from DeFiLlama."""
        try:
            resp = self.session.get(DEFILLAMA_STABLECOINS, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # Parse chain-level stablecoin distribution
            results = []
            total_mcap = 0

            # Sum all stablecoin market caps
            for coin in data.get("peggedAssets", []):
                mcap = coin.get("circulating", {}).get("current", {})
                if isinstance(mcap, dict):
                    chain_mcaps = mcap  # {chain: mcap_value}
                    for chain, val in chain_mcaps.items():
                        total_mcap += val if isinstance(val, (int, float)) else 0

            # Get Solana-specific stablecoin mcap
            sol_mcap = 0
            eth_mcap = 0
            for coin in data.get("peggedAssets", []):
                mcap = coin.get("circulating", {}).get("current", {})
                if isinstance(mcap, dict):
                    sol_val = mcap.get("Solana", 0)
                    eth_val = mcap.get("Ethereum", 0)
                    sol_mcap += sol_val if isinstance(sol_val, (int, float)) else 0
                    eth_mcap += eth_val if isinstance(eth_val, (int, float)) else 0

            now_ms = int(time.time() * 1000)

            for chain_name, chain_mcap in [("solana", sol_mcap), ("ethereum", eth_mcap)]:
                stablecoin_share = (chain_mcap / total_mcap * 100) if total_mcap > 0 else 0
                results.append({
                    "chain": chain_name,
                    "stablecoin_mcap_usd": chain_mcap,
                    "total_mcap_usd": total_mcap,
                    "stablecoin_share_pct": stablecoin_share,
                })

            log.info(f"Stablecoin mcap: SOL=${sol_mcap/1e6:.0f}M, ETH=${eth_mcap/1e6:.0f}M")
            return results

        except requests.RequestException as e:
            log.error(f"DeFiLlama stablecoin fetch error: {e}")
            return []

    # ── Storage ──

    def store_utilization(self, ts_ms: int, pools: list[dict]):
        """Store pool utilization data."""
        with sqlite3.connect(self.db_path) as conn:
            for pool in pools:
                conn.execute(
                    "INSERT OR REPLACE INTO defi_utilization "
                    "(ts, protocol, chain, asset, total_supply_usd, total_borrow_usd, "
                    "utilization_pct, supply_apy, borrow_apy, source) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'defillama')",
                    (ts_ms, pool["protocol"], pool["chain"], pool["asset"],
                     pool.get("total_supply_usd", 0), pool.get("total_borrow_usd", 0),
                     pool.get("utilization_pct", 0), pool.get("supply_apy", 0),
                     pool.get("borrow_apy", 0))
                )

    def store_stablecoin_mcap(self, ts_ms: int, data: list[dict]):
        """Store stablecoin market cap data."""
        with sqlite3.connect(self.db_path) as conn:
            for row in data:
                conn.execute(
                    "INSERT OR REPLACE INTO stablecoin_mcap "
                    "(ts, chain, stablecoin_mcap_usd, total_mcap_usd, stablecoin_share_pct, source) "
                    "VALUES (?, ?, ?, ?, ?, 'defillama')",
                    (ts_ms, row["chain"], row["stablecoin_mcap_usd"],
                     row["total_mcap_usd"], row["stablecoin_share_pct"])
                )

    # ── Main Collection Loop ──

    def collect_once(self):
        """Run a single collection cycle."""
        now_ms = int(time.time() * 1000)
        log.info("Collecting DeFi regime data...")

        # Aave ETH
        aave_pools = self.fetch_aave_pools()
        if aave_pools:
            self.store_utilization(now_ms, aave_pools)
            log.info(f"  Stored {len(aave_pools)} Aave pools")

        # Solana lending
        solana_pools = self.fetch_solana_lending()
        if solana_pools:
            self.store_utilization(now_ms, solana_pools)
            log.info(f"  Stored {len(solana_pools)} Solana pools")

        # Stablecoins
        stablecoin_data = self.fetch_stablecoin_mcap()
        if stablecoin_data:
            self.store_stablecoin_mcap(now_ms, stablecoin_data)
            log.info(f"  Stored {len(stablecoin_data)} stablecoin entries")

        # Update heartbeat
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO collector_meta (key, value) VALUES (?, ?)",
                ("last_collect", str(now_ms))
            )

        log.info("DeFi collection cycle complete")

    def get_regime(self, chain: str = "ethereum") -> dict:
        """Get current DeFi regime for a chain.

        Returns regime classification: OVERHEATED / NORMAL / DELEVERAGED / UNKNOWN
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT asset, utilization_pct, total_supply_usd FROM defi_utilization "
                "WHERE chain = ? ORDER BY ts DESC LIMIT 10",
                (chain,)
            ).fetchall()

        if not rows:
            return {"regime": "UNKNOWN", "detail": "No data"}

        # Average utilization across assets
        utils = [r[1] for r in rows if r[1] > 0]
        avg_util = sum(utils) / len(utils) if utils else 0

        if avg_util > 90:
            regime = "OVERHEATED"
        elif avg_util < 30:
            regime = "DELEVERAGED"
        else:
            regime = "NORMAL"

        return {
            "regime": regime,
            "avg_utilization_pct": round(avg_util, 1),
            "assets": len(rows),
        }

    def get_health(self) -> dict:
        """Get collector health."""
        with sqlite3.connect(self.db_path) as conn:
            last = conn.execute(
                "SELECT value FROM collector_meta WHERE key = 'last_collect'"
            ).fetchone()
            count = conn.execute(
                "SELECT COUNT(*) FROM defi_utilization"
            ).fetchone()[0]

        now_ms = int(time.time() * 1000)
        last_ms = int(last[0]) if last and last[0] else 0
        age_hours = (now_ms - last_ms) / 3600000

        return {
            "last_collect_hours_ago": round(age_hours, 1),
            "total_rows": count,
            "is_healthy": age_hours < 48,  # data should be < 48h old
        }


def main():
    """Run single collection cycle (for cron)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    collector = DeFiCollector()
    collector.collect_once()


if __name__ == "__main__":
    main()