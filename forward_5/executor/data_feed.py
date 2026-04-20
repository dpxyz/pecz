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
# IMPORTANT: Import PAPER_MODE from paper_engine to stay in sync
try:
    from paper_engine import PAPER_MODE as _PAPER_MODE
    PAPER_MODE = _PAPER_MODE
except ImportError:
    PAPER_MODE = True  # Fallback: always paper unless explicitly loaded

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
        # Hyperliquid WS message formats:
        #   Subscription response: {"channel": "subscriptionResponse", "data": {...}}
        #   Candle update: {"channel": "candle", "data": {"t": 1776682800000, "T": 1776686399999, "s": "BTC", "i": "1h", "o": "75303.0", "c": "75364.0", "h": "75473.0", "l": "75228.0", "v": "0.26901", "n": 246}}
        #   Error: {"channel": "error", "data": "..."}
        #
        # Key insight: Hyperliquid sends PARTIAL candle updates throughout the hour.
        #   - t = open time, T = close time, s = symbol, i = interval
        #   - o/c/h/l/v are STRINGS, not numbers
        #   - n = number of trades (tick count)
        #   - Multiple updates per hour (not just on close)
        #   - We must ONLY process CLOSED candles (t < current hour start)

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

        # ── Parse Hyperliquid candle format ──
        # Symbol: "s" field (e.g. "BTC"), not "coin"
        coin = data.get("s", "")
        # Reverse-map coin to our symbol
        symbol = None
        for s, c in SYMBOL_MAP.items():
            if c == coin:
                symbol = s
                break
        if not symbol:
            symbol = coin + "USDT" if coin else None
        if not symbol:
            return

        # Candle fields are flat in data, not in a "candle" array
        # All price/volume fields are STRINGS
        t_str = data.get("t")   # open time (ms epoch)
        T_str = data.get("T")   # close time (ms epoch)
        o_str = data.get("o")   # open price
        c_str = data.get("c")   # close price
        h_str = data.get("h")   # high price
        l_str = data.get("l")   # low price
        v_str = data.get("v")   # volume

        if not t_str or not c_str:
            return

        try:
            ts = int(t_str)
            o = float(o_str)
            h = float(h_str)
            low = float(l_str)
            c = float(c_str)
            v = float(v_str) if v_str else 0.0
        except (ValueError, TypeError) as e:
            log.warning(f"Failed to parse candle fields: {e}")
            return

        # ── CRITICAL: Only process CLOSED candles ──
        # Hyperliquid sends partial updates throughout the hour.
        # We must only evaluate signals on COMPLETE candles.
        # A candle is "closed" if its close time (T) is in the past.
        now_ms = int(time.time() * 1000)
        candle_close_time = int(data.get("T", ts + 3600000))  # fallback: +1h

        if candle_close_time > now_ms:
            # This is a PARTIAL (in-progress) candle — update DB but don't signal
            self._store_candle(symbol, ts, o, h, low, c, v)
            log.debug(f"Partial candle: {symbol} @ {ts} close={c:.2f} (closing at {candle_close_time})")
            return

        # CLOSED candle — store and signal
        self._store_candle(symbol, ts, o, h, low, c, v)
        log.info(f"Closed candle: {symbol} @ {ts} close={c:.2f}")

        # Callback
        if self.on_candle:
            candle_data = {
                "symbol": symbol, "timestamp": ts,
                "open": o, "high": h, "low": low, "close": c, "volume": v,
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