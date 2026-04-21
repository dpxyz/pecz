"""
Executor V1 — Data Feed
Hybrid: REST polling for candles (reliable on testnet) + WS for live prices.
Testnet WS candle feed is unreliable — we poll the REST API instead.
"""

import asyncio
import json
import time
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone

import requests
import websockets

log = logging.getLogger("data_feed")

WS_URL = "wss://api.hyperliquid.xyz/ws"
WS_URL_TESTNET = "wss://api.hyperliquid-testnet.xyz/ws"
API_URL = "https://api.hyperliquid.xyz"
API_URL_TESTNET = "https://api.hyperliquid-testnet.xyz"

# ⛔ PAPER MODE — use Testnet
try:
    from paper_engine import PAPER_MODE as _PAPER_MODE
    PAPER_MODE = _PAPER_MODE
except ImportError:
    PAPER_MODE = True

INTERVAL = "1h"
POLL_INTERVAL = 60  # seconds between REST candle polls
BACKFILL_HOURS = 48  # how many hours to backfill on startup

# Map our symbols to Hyperliquid coin names
SYMBOL_MAP = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL",
    "AVAXUSDT": "AVAX",
    "DOGEUSDT": "DOGE",
    "ADAUSDT": "ADA",
}


class DataFeed:
    def __init__(self, db_path: str = "executor/state.db",
                 assets: list[str] = None,
                 on_candle=None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.assets = assets or ["BTCUSDT", "ETHUSDT"]
        self.on_candle = on_candle  # async callback(symbol, candle_data)
        self._running = False
        self._last_processed: dict[str, int] = {}  # symbol → last closed candle ts
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_candles_ts
                ON candles(symbol, ts)
            """)

    async def start(self):
        self._running = True
        mode_str = "⛔ TESTNET (Paper)" if PAPER_MODE else "🔴 MAINNET (REAL MONEY)"
        log.info(f"DataFeed starting — {mode_str} — assets: {self.assets}")
        log.info(f"Candle source: REST API polling every {POLL_INTERVAL}s")

        # Backfill recent candles
        await self._backfill()

        # Initialize last-processed pointers from DB
        # Set to last CLOSED candle (before current hour) so we process
        # any missed candles from the gap, not the current partial.
        now_ms = int(time.time() * 1000)
        current_hour = (now_ms // 3600000) * 3600000
        for symbol in self.assets:
            with sqlite3.connect(self.db_path) as conn:
                # Get the last closed candle (before current hour)
                row = conn.execute(
                    "SELECT MAX(ts) FROM candles WHERE symbol = ? AND ts < ?", 
                    (symbol, current_hour)
                ).fetchone()
                if row and row[0]:
                    self._last_processed[symbol] = row[0]
                    log.info(f"  {symbol}: last closed candle at ts={row[0]}")
                else:
                    self._last_processed[symbol] = 0

        # Start polling loop
        while self._running:
            try:
                await self._poll_candles()
            except Exception as e:
                log.error(f"Poll error: {e}")
            if self._running:
                await asyncio.sleep(POLL_INTERVAL)

    async def stop(self):
        self._running = False

    async def _backfill(self):
        """Fetch recent candles via REST API on startup."""
        api_url = API_URL_TESTNET if PAPER_MODE else API_URL
        start_time = int((time.time() - BACKFILL_HOURS * 3600) * 1000)
        total = 0

        for symbol in self.assets:
            coin = SYMBOL_MAP.get(symbol, symbol.replace("USDT", ""))
            try:
                resp = requests.post(f"{api_url}/info", json={
                    "type": "candleSnapshot",
                    "req": {
                        "coin": coin,
                        "interval": INTERVAL,
                        "startTime": start_time,
                    }
                }, timeout=15)
                candles = resp.json()
                count = 0
                for c in candles:
                    ts = int(c["t"])
                    self._store_candle(symbol, ts,
                                       float(c["o"]), float(c["h"]),
                                       float(c["l"]), float(c["c"]),
                                       float(c.get("v", 0)))
                    count += 1
                total += count
                log.info(f"  ✅ {symbol}: {count} candles backfilled")
            except Exception as e:
                log.error(f"  ❌ {symbol}: backfill failed: {e}")

        log.info(f"Backfill complete: {total} candles total")

    async def _poll_candles(self):
        """Poll REST API for latest candles, fire callback for newly closed ones."""
        api_url = API_URL_TESTNET if PAPER_MODE else API_URL
        now_ms = int(time.time() * 1000)
        # Current hour boundary — candles before this are "closed"
        current_hour = (now_ms // 3600000) * 3600000

        for symbol in self.assets:
            coin = SYMBOL_MAP.get(symbol, symbol.replace("USDT", ""))
            try:
                # Fetch last 3 hours of candles
                start_time = current_hour - (3 * 3600000)
                resp = requests.post(f"{api_url}/info", json={
                    "type": "candleSnapshot",
                    "req": {
                        "coin": coin,
                        "interval": INTERVAL,
                        "startTime": start_time,
                    }
                }, timeout=15)
                candles = resp.json()

                for c in candles:
                    ts = int(c["t"])
                    T = int(c["T"])  # close time

                    # Store in DB (upsert)
                    self._store_candle(symbol, ts,
                                       float(c["o"]), float(c["h"]),
                                       float(c["l"]), float(c["c"]),
                                       float(c.get("v", 0)))

                    # Fire callback only for CLOSED candles we haven't processed yet
                    last = self._last_processed.get(symbol, 0)
                    if ts > last and T <= now_ms:
                        self._last_processed[symbol] = ts
                        log.info(f"Closed candle: {symbol} @ {ts} close={float(c['c']):.2f}")

                        if self.on_candle:
                            candle_data = {
                                "symbol": symbol, "timestamp": ts,
                                "open": float(c["o"]), "high": float(c["h"]),
                                "low": float(c["l"]), "close": float(c["c"]),
                                "volume": float(c.get("v", 0)),
                            }
                            await self.on_candle(symbol, candle_data)

            except Exception as e:
                log.error(f"Poll error for {symbol}: {e}")

    def _store_candle(self, symbol, ts, o, h, l, c, v):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO candles (symbol, ts, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (symbol, ts, o, h, l, c, v))

    def get_candles(self, symbol: str, limit: int = 200) -> list[dict]:
        """Fetch last N candles from SQLite (for indicator calculation)."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT ts, open, high, low, close, volume
                FROM candles WHERE symbol = ?
                ORDER BY ts DESC LIMIT ?
            """, (symbol, limit)).fetchall()

        return [{
            "timestamp": r[0], "open": r[1], "high": r[2],
            "low": r[3], "close": r[4], "volume": r[5],
        } for r in reversed(rows)]


# ── Standalone test ──
async def _test():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(message)s",
                        datefmt="%H:%M:%S")

    feed = DataFeed(assets=["BTCUSDT", "ETHUSDT"])

    async def on_candle(symbol, candle):
        log.info(f"📡 {symbol} close={candle['close']:.2f} vol={candle['volume']:.1f}")

    feed.on_candle = on_candle

    try:
        await feed.start()
    except KeyboardInterrupt:
        await feed.stop()

if __name__ == "__main__":
    asyncio.run(_test())