"""
Coinalyze Liquidation History Backfill

Fetches historical liquidation data from Coinalyze's free API
to bootstrap the 1h aggregate table with ~60 days of intraday data.

API docs: https://api.coinalyze.net/v1/doc/
Endpoint: /liquidation-history
Rate limit: 30 req/min (free tier)
Retention: 1500-2000 datapoints intraday, daily unlimited
"""

import sqlite3
import time
import logging
from typing import Optional
from pathlib import Path

import requests

log = logging.getLogger("coinalyze_backfill")

COINALYZE_API_URL = "https://api.coinalyze.net/v1/liquidation-history"
DB_PATH = "data/liquidations/liquidations.db"

# Coinalyze symbols map (their format)
SYMBOL_MAP = {
    "BTCUSDT": "BTCUSDT_PERP.A",
    "ETHUSDT": "ETHUSDT_PERP.A",
    "SOLUSDT": "SOLUSDT_PERP.A",
    "AVAXUSDT": "AVAXUSDT_PERP.A",
    "DOGEUSDT": "DOGEUSDT_PERP.A",
    "ADAUSDT": "ADAUSDT_PERP.A",
}

# Intervals: Coinalyze supports 1min, 5min, 15min, 30min, 1hour, 2hour, 4hour, 6hour, 12hour, daily
# We use 1hour for backfill (gives ~60 days of history)
INTERVAL = "1hour"


class CoinalyzeBackfill:
    """Backfill liquidation data from Coinalyze API."""

    def __init__(self, api_key: str, db_path: str = DB_PATH):
        self.api_key = api_key
        self.db_path = db_path
        self.session = requests.Session()
        self.session.headers.update({"Api-Key": api_key})

        # Ensure directory and tables exist
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create tables if not exist (same schema as LiquidationCollector)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS liquidation_1h (
                    ts_hour INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    long_notional REAL NOT NULL DEFAULT 0,
                    short_notional REAL NOT NULL DEFAULT 0,
                    long_count INTEGER NOT NULL DEFAULT 0,
                    short_count INTEGER NOT NULL DEFAULT 0,
                    source TEXT DEFAULT 'binance',
                    PRIMARY KEY (ts_hour, symbol)
                )
            """)

    def fetch_liquidation_history(
        self, symbol: str, interval: str = INTERVAL, days: int = 60
    ) -> list[dict]:
        """Fetch liquidation history for a symbol.

        Args:
            symbol: Coinalyze symbol (e.g. 'BTCUSDT_PERP.A')
            interval: time interval
            days: how many days back

        Returns:
            List of dicts with ts, long_notional, short_notional
        """
        from_ts = int(time.time()) - days * 86400
        to_ts = int(time.time())

        params = {
            "symbols": symbol,
            "interval": interval,
            "from": from_ts,
            "to": to_ts,
        }

        log.info(f"Fetching Coinalyze liquidations: {symbol} {interval} last {days}d")
        try:
            resp = self.session.get(COINALYZE_API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if not data or not isinstance(data, list):
                log.warning(f"No data returned for {symbol}")
                return []

            results = []
            for item in data:
                # Coinalyze returns: t (timestamp), l (long liq volume), s (short liq volume)
                ts = item.get("t", 0)
                long_vol = float(item.get("l", 0))
                short_vol = float(item.get("s", 0))

                if ts > 0:
                    results.append({
                        "ts_hour": ts * 1000,  # convert to ms
                        "long_notional": long_vol,
                        "short_notional": short_vol,
                        "long_count": 0,  # Coinalyze doesn't provide count
                        "short_count": 0,
                    })

            log.info(f"  Got {len(results)} data points for {symbol}")
            return results

        except requests.RequestException as e:
            log.error(f"Coinalyze API error for {symbol}: {e}")
            return []

    def store_backfill(self, binance_symbol: str, data: list[dict]):
        """Store backfilled data into liquidation_1h table.

        Marks source as 'coinalyze' to distinguish from live WS data.
        """
        if not data:
            return

        with sqlite3.connect(self.db_path) as conn:
            for row in data:
                conn.execute(
                    "INSERT INTO liquidation_1h "
                    "(ts_hour, symbol, long_notional, short_notional, long_count, short_count, source) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'coinalyze') "
                    "ON CONFLICT(ts_hour, symbol) DO UPDATE SET "
                    "long_notional = CASE WHEN source = 'coinalyze' THEN excluded.long_notional ELSE long_notional END, "
                    "short_notional = CASE WHEN source = 'coinalyze' THEN excluded.short_notional ELSE short_notional END, "
                    "source = COALESCE(source, 'coinalyze')",
                    (
                        row["ts_hour"],
                        binance_symbol,
                        row["long_notional"],
                        row["short_notional"],
                        row["long_count"],
                        row["short_count"],
                    )
                )

        log.info(f"Stored {len(data)} backfill rows for {binance_symbol}")

    def run(self, symbols: Optional[list[str]] = None, days: int = 60):
        """Run backfill for all configured symbols.

        Args:
            symbols: list of Binance symbols. Defaults to SYMBOL_MAP keys.
            days: days of history to fetch.
        """
        symbols = symbols or list(SYMBOL_MAP.keys())

        for binance_sym in symbols:
            coinalyze_sym = SYMBOL_MAP.get(binance_sym)
            if not coinalyze_sym:
                log.warning(f"No Coinalyze mapping for {binance_sym}")
                continue

            data = self.fetch_liquidation_history(coinalyze_sym, days=days)
            self.store_backfill(binance_sym, data)

            # Rate limit: 30 req/min → 2 sec delay between requests
            time.sleep(2)

        log.info("Coinalyze backfill complete")


def main():
    """Run backfill as standalone script."""
    import os
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    api_key = os.environ.get("COINALYZE_API_KEY", "")
    if not api_key:
        print("ERROR: COINALYZE_API_KEY environment variable not set")
        print("Get a free API key at https://coinalyze.net/")
        sys.exit(1)

    backfill = CoinalyzeBackfill(api_key)
    backfill.run()


if __name__ == "__main__":
    main()