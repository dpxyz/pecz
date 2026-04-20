"""
Executor V1 — Data Feed
Connects to Hyperliquid WebSocket, subscribes to 1h candles,
buffers last 200 bars, persists to SQLite.
"""

import asyncio
import json
import time
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone

import websockets

log = logging.getLogger("data_feed")

WS_URL = "wss://api.hyperliquid.xyz/ws"
WS_URL_TESTNET = "wss://api.hyperliquid-testnet.xyz/ws"
RECONNECT_DELAY = 1  # seconds, doubles on each failure
MAX_RECONNECT_DELAY = 60

# ⛔ PAPER MODE — use Testnet WebSocket
# When PAPER_MODE=True, connect to Testnet (fake money)
# When PAPER_MODE=False, connect to Mainnet (REAL MONEY)
PAPER_MODE = True  # MUST match paper_engine.py PAPER_MODE

# Hyperliquid candle intervals
INTERVAL = "1h"

# Map our symbols to Hyperliquid coin names
SYMBOL_MAP = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL",
    "AVAXUSDT": "AVAX",
    "DOGEUSDT": "DOGE",  # Replaces LINK (not on Testnet)
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
        self._ws = None
        self._running = False
        self._reconnect_delay = RECONNECT_DELAY
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
        log.info(f"DataFeed starting — assets: {self.assets}")
        while self._running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                log.error(f"WebSocket error: {e}")
            if self._running:
                # Testnet WS drops after ~60s idle — expected, not an error
                log.debug(f"Reconnecting in {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, MAX_RECONNECT_DELAY)

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()

    async def _connect_and_listen(self):
        ws_url = WS_URL_TESTNET if PAPER_MODE else WS_URL
        mode_str = "⛔ TESTNET (Paper)" if PAPER_MODE else "🔴 MAINNET (REAL MONEY)"
        # Testnet WS drops idle connections — suppress noisy reconnect logs
        log.info(f"Connecting to {mode_str}: {ws_url}")
        async with websockets.connect(
            ws_url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            self._ws = ws
            self._reconnect_delay = RECONNECT_DELAY
            log.info("WebSocket connected ✅")

            # Subscribe to all assets using correct Hyperliquid WS format
            for symbol in self.assets:
                coin = SYMBOL_MAP.get(symbol, symbol.replace("USDT", ""))
                sub = {
                    "method": "subscribe",
                    "subscription": {
                        "type": "candle",
                        "coin": coin,
                        "interval": INTERVAL,
                    },
                }
                await ws.send(json.dumps(sub))
                log.info(f"Subscribed: {symbol} ({coin}) 1h candles")

            async for raw_msg in ws:
                msg = json.loads(raw_msg)
                await self._handle_message(msg)

    async def _handle_message(self, msg):
        # Hyperliquid WS message format:
        #   {"channel": "candle", "data": {"coin": "BTC", "candle": [t, o, h, l, c, v]}}
        #   {"channel": "subscriptionResponse", "data": {...}}
        #   {"channel": "error", "data": "..."}
        channel = msg.get("channel", "")

        # Log subscription confirmations
        if channel == "subscriptionResponse":
            log.debug(f"Subscription confirmed: {msg.get('data', {})}")
            return

        # Log errors
        if channel == "error":
            log.error(f"WS error: {msg.get('data', '')}")
            return

        # Only handle candle messages
        if channel != "candle":
            return

        data = msg.get("data", {})
        coin = data.get("coin", "")
        # Reverse-map coin to our symbol
        symbol = None
        for s, c in SYMBOL_MAP.items():
            if c == coin:
                symbol = s
                break
        if not symbol:
            symbol = coin + "USDT"

        # Hyperliquid candle format: [t, o, h, l, c, v]
        candle = data.get("candle", [])
        if not candle or len(candle) < 6:
            return

        ts, o, h, l, c, v = candle[0], float(candle[1]), float(candle[2]), \
                              float(candle[3]), float(candle[4]), float(candle[5])

        # Store
        self._store_candle(symbol, ts, o, h, l, c, v)

        # Callback
        if self.on_candle:
            candle_data = {
                "symbol": symbol, "timestamp": ts,
                "open": o, "high": h, "low": l, "close": c, "volume": v,
            }
            await self.on_candle(symbol, candle_data)

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