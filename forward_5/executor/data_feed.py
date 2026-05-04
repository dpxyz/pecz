"""
Executor V1 - Data Feed
Hybrid: REST polling for candles (reliable on testnet) + WS for live prices.
Testnet WS candle feed is unreliable - we poll the REST API instead.
"""

from typing import Optional
import asyncio
import time
import sqlite3
import logging
from pathlib import Path

import requests

log = logging.getLogger("data_feed")

WS_URL = "wss://api.hyperliquid.xyz/ws"
WS_URL_TESTNET = "wss://api.hyperliquid-testnet.xyz/ws"
API_URL = "https://api.hyperliquid.xyz"
API_URL_TESTNET = "https://api.hyperliquid-testnet.xyz"

# ⛔ PAPER MODE - use Testnet
try:
    from paper_engine import PAPER_MODE as _PAPER_MODE
    PAPER_MODE = _PAPER_MODE
except ImportError:
    PAPER_MODE = True

INTERVAL = "1h"
POLL_INTERVAL = 60  # seconds between REST candle polls
BACKFILL_HOURS = 240  # 10 days for EMA200 regime detection (need 200+ candles)
MAX_CANDLE_AGE_MS = 2 * 3600 * 1000  # candles older than 2h are stale → skip trading

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
                 assets: Optional[list[str]] = None,
                 on_candle=None,
                 engine_last_processed_ts: Optional[int] = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.assets = assets or ["BTCUSDT", "ETHUSDT"]
        self.on_candle = on_candle  # async callback(symbol, candle_data)
        self._running = False
        self._last_processed: dict[str, int] = {}  # symbol → last closed candle ts
        self._engine_last_processed_ts = engine_last_processed_ts  # for gap recovery
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
        log.info(f"DataFeed starting - {mode_str} - assets: {self.assets}")
        log.info(f"Candle source: REST API polling every {POLL_INTERVAL}s")

        # Backfill recent candles
        await self._backfill()

        # Initialize last-processed pointers from DB
        # GAP RECOVERY: After a crash, the engine may have missed candles.
        # We set _last_processed to the engine's last known state, so that
        # any candles between that timestamp and now get replayed.
        # The engine's _on_candle has dedup protection and won't re-process
        # candles that were already handled.
        #
        # If engine_state_last_ts is provided (from state.db), use it.
        # Otherwise fall back to last DB candle (no gap to replay).
        now_ms = int(time.time() * 1000)
        current_hour = (now_ms // 3600000) * 3600000
        gap_count = 0
        for symbol in self.assets:
            with sqlite3.connect(self.db_path) as conn:
                # Get the last closed candle in the DB (before current hour)
                last_in_db = conn.execute(
                    "SELECT MAX(ts) FROM candles WHERE symbol = ? AND ts < ?",
                    (symbol, current_hour)
                ).fetchone()[0]
                
                if self._engine_last_processed_ts and last_in_db:
                    # There's a gap to replay — start from engine's last processed
                    # Sanity check: don't replay more than 7 days (168h) of candles
                    max_gap_ms = 7 * 24 * 3600 * 1000  # 7 days
                    if (current_hour - self._engine_last_processed_ts) > max_gap_ms:
                        log.warning(f"  {symbol}: Gap too large ({(current_hour - self._engine_last_processed_ts) / 86400000:.0f} days), "
                                   f"starting from recent history instead")
                        self._last_processed[symbol] = last_in_db
                    else:
                        self._last_processed[symbol] = self._engine_last_processed_ts
                        # Count gap candles for logging
                        gap = conn.execute(
                            "SELECT COUNT(*) FROM candles WHERE symbol = ? AND ts > ? AND ts < ?",
                            (symbol, self._engine_last_processed_ts, current_hour)
                        ).fetchone()[0]
                        if gap > 0:
                            log.info(f"  {symbol}: GAP RECOVERY — replaying {gap} candles from ts={self._engine_last_processed_ts}")
                            gap_count += gap
                        else:
                            log.info(f"  {symbol}: up-to-date (last={last_in_db})")
                elif last_in_db:
                    # No engine state — set to last DB candle (no replay)
                    self._last_processed[symbol] = last_in_db
                    log.info(f"  {symbol}: last closed candle at ts={last_in_db}")
                else:
                    self._last_processed[symbol] = 0
                    log.info(f"  {symbol}: no candles in DB")
        
        if gap_count > 0:
            log.info(f"⚠️ GAP RECOVERY: {gap_count} total candles to replay across {len(self.assets)} assets")

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
                # BUG FIX: API can return error dict instead of list
                if not isinstance(candles, list):
                    log.error(f"  ❌ {symbol}: API returned non-list: {candles}")
                    continue
                count = 0
                for c in candles:
                    try:
                        ts = int(c["t"])
                        self._store_candle(symbol, ts,
                                           float(c["o"]), float(c["h"]),
                                           float(c["l"]), float(c["c"]),
                                           float(c.get("v", 0)))
                    except (KeyError, ValueError, TypeError) as e:
                        log.warning(f"  ⚠️ {symbol}: Invalid candle data: {e}")
                        continue
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
        # Current hour boundary - candles before this are "closed"
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

                # BUG FIX: API can return error dict instead of list
                if not isinstance(candles, list):
                    log.error(f"Poll error for {symbol}: API returned non-list")
                    continue

                for c in candles:
                    try:
                        ts = int(c["t"])
                        T = int(c["T"])  # close time
                    except (KeyError, ValueError, TypeError) as e:
                        log.warning(f"⚠️ {symbol}: Invalid candle: {e}")
                        continue

                    # Store in DB (upsert)
                    try:
                        self._store_candle(symbol, ts,
                                           float(c["o"]), float(c["h"]),
                                           float(c["l"]), float(c["c"]),
                                           float(c.get("v", 0)))
                    except (KeyError, ValueError) as e:
                        log.warning(f"⚠️ {symbol}: Invalid candle data: {e}")
                        continue

                    # Fire callback only for CLOSED candles we haven't processed yet
                    last = self._last_processed.get(symbol, 0)
                    if ts >= last and T <= now_ms:
                        self._last_processed[symbol] = ts
                        # Stale candle = older than MAX_CANDLE_AGE_MS → mark as replay
                        # Replay candles warm up indicators but MUST NOT trigger trades
                        is_stale = (now_ms - ts) > MAX_CANDLE_AGE_MS
                        if is_stale:
                            log.debug(f"Replay candle: {symbol} @ {ts} ({(now_ms-ts)/3600000:.0f}h old)")
                        else:
                            log.info(f"Closed candle: {symbol} @ {ts} close={float(c['c']):.2f}")

                        if self.on_candle:
                            candle_data = {
                                "symbol": symbol, "timestamp": ts,
                                "open": float(c["o"]), "high": float(c["h"]),
                                "low": float(c["l"]), "close": float(c["c"]),
                                "volume": float(c.get("v", 0)),
                                "is_replay": is_stale,  # True = gap recovery/backfill, no trades
                            }
                            await self.on_candle(symbol, candle_data)

            except Exception as e:
                log.error(f"Poll error for {symbol}: {e}")

    def _store_candle(self, symbol, ts, o, h, low, c, v):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO candles (symbol, ts, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (symbol, ts, o, h, low, c, v))

    def get_candles(self, symbol: str, limit: int = 200) -> list[dict]:
        """Fetch last N candles from SQLite (for indicator calculation)."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT ts, open, high, low, close, volume
                FROM candles WHERE symbol = ?
                ORDER BY ts DESC LIMIT ?
            """, (symbol, limit)).fetchall()

        return [{
            "symbol": symbol, "timestamp": r[0], "open": r[1], "high": r[2],
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