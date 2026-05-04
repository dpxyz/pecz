"""
Binance Liquidation WebSocket Collector

Collects real-time liquidation events from Binance USDS-M Futures
via the all-market stream !forceOrder@arr and stores them in SQLite.

Known limitations:
- Only 1 event per second per symbol (largest liquidation)
- Smaller liquidations are missed → totals are underestimated
- S=SELL = Long liquidation, S=BUY = Short liquidation

Data flow:
  Binance WS → parse → SQLite (tick-level) → 1h aggregate rollup

Reference: deep_research_liquidations.txt Section 1+4
"""

import asyncio
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

import websockets

log = logging.getLogger("liq_collector")

# ── Config ──

BINANCE_WS_URL = "wss://fstream.binance.com/ws/!forceOrder@arr"
DB_PATH = "data/liquidations/liquidations.db"
RECONNECT_DELAY = 5  # seconds, exponential backoff base
MAX_RECONNECT_DELAY = 300  # 5 minutes max
ROLLUP_INTERVAL = 3600  # 1 hour aggregates


class LiquidationCollector:
    """Collects Binance futures liquidation events via WebSocket."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._running = False
        self._reconnect_delay = RECONNECT_DELAY
        self._last_event_ts: dict[str, int] = {}  # per-symbol heartbeat

        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create tables if not exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS liquidation_ticks (
                    ts INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    liq_side TEXT NOT NULL,  -- 'long' or 'short'
                    price REAL NOT NULL,
                    qty REAL NOT NULL,
                    notional REAL NOT NULL,
                    source TEXT DEFAULT 'binance',
                    PRIMARY KEY (ts, symbol, liq_side, price, qty)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_liq_ts_sym
                ON liquidation_ticks(ts, symbol)
            """)
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_liq1h_ts_sym
                ON liquidation_1h(ts_hour, symbol)
            """)
            # Metadata table for health monitoring
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collector_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

    def _parse_event(self, event: dict) -> Optional[dict]:
        """Parse a single forceOrder event from Binance."""
        try:
            if not event or not isinstance(event, dict):
                return None
            o = event.get("o", event)
            symbol = o.get("s", "")
            side = o.get("S", "")
            price = float(o.get("p", 0))
            avg_price = float(o.get("ap", 0))
            qty = float(o.get("q", 0))
            event_time = int(o.get("T", 0))  # trade time in ms

            if not symbol or not side or event_time == 0:
                return None

            # S=SELL → Long liquidation (closing long via sell)
            # S=BUY → Short liquidation (closing short via buy)
            liq_side = "long" if side == "SELL" else "short"
            notional = qty * avg_price if avg_price > 0 else qty * price

            return {
                "ts": event_time,
                "symbol": symbol,
                "liq_side": liq_side,
                "price": avg_price if avg_price > 0 else price,
                "qty": qty,
                "notional": notional,
            }
        except (KeyError, ValueError, TypeError) as e:
            log.warning(f"Failed to parse liquidation event: {e}")
            return None

    def _store_tick(self, tick: dict):
        """Store a single liquidation tick."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO liquidation_ticks (ts, symbol, liq_side, price, qty, notional, source) "
                "VALUES (?, ?, ?, ?, ?, ?, 'binance')",
                (tick["ts"], tick["symbol"], tick["liq_side"],
                 tick["price"], tick["qty"], tick["notional"])
            )

    def _update_heartbeat(self):
        """Update collector heartbeat for health monitoring."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO collector_meta (key, value) VALUES (?, ?)",
                ("last_heartbeat", str(int(time.time() * 1000)))
            )
            conn.execute(
                "INSERT OR REPLACE INTO collector_meta (key, value) VALUES (?, ?)",
                ("status", "running")
            )

    async def _run_websocket(self):
        """Connect to Binance WS and process events."""
        log.info(f"Connecting to Binance liquidation stream: {BINANCE_WS_URL}")
        try:
            async with websockets.connect(
                BINANCE_WS_URL,
                ping_interval=20,
                ping_timeout=60,
                close_timeout=5,
            ) as ws:
                log.info("✅ Connected to Binance liquidation stream")
                self._reconnect_delay = RECONNECT_DELAY  # reset on success

                async for message in ws:
                    if not self._running:
                        break

                    try:
                        events = json.loads(message)
                        # !forceOrder@arr sends a list, but sometimes single event
                        if isinstance(events, dict):
                            events = [events]

                        for event in events:
                            tick = self._parse_event(event)
                            if tick:
                                self._store_tick(tick)
                                self._last_event_ts[tick["symbol"]] = tick["ts"]

                                # Log significant liquidations (> $100k)
                                if tick["notional"] > 100_000:
                                    log.info(
                                        f"🔥 Large liquidation: {tick['symbol']} {tick['liq_side']} "
                                        f"${tick['notional']:,.0f} @ {tick['price']:.2f}"
                                    )

                        self._update_heartbeat()

                    except json.JSONDecodeError as e:
                        log.warning(f"JSON decode error: {e}")
                        continue

        except websockets.ConnectionClosed as e:
            log.warning(f"WebSocket closed: {e.code} {e.reason}")
        except Exception as e:
            log.error(f"WebSocket error: {e}")

    async def run(self):
        """Main loop with reconnection logic."""
        self._running = True
        log.info("LiquidationCollector starting...")

        while self._running:
            await self._run_websocket()

            if self._running:
                log.info(f"Reconnecting in {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, MAX_RECONNECT_DELAY
                )

        # Mark as stopped
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO collector_meta (key, value) VALUES (?, ?)",
                ("status", "stopped")
            )
        log.info("LiquidationCollector stopped")

    def stop(self):
        """Gracefully stop the collector."""
        self._running = False
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO collector_meta (key, value) VALUES (?, ?)",
                ("status", "stopped")
            )
        log.info("LiquidationCollector stopped")

    def rollup_1h(self):
        """Roll up tick-level data to 1h aggregates.

        Called periodically (e.g., hourly via cron) to compute
        per-symbol, per-side liquidation volumes.
        """
        with sqlite3.connect(self.db_path) as conn:
            # Find last rolled-up hour
            last_hour = conn.execute(
                "SELECT COALESCE(MAX(ts_hour), 0) FROM liquidation_1h"
            ).fetchone()[0]

            # Get unrolled ticks
            ticks = conn.execute(
                "SELECT ts, symbol, liq_side, notional, COUNT(*) as cnt "
                "FROM liquidation_ticks WHERE ts > ? "
                "GROUP BY (ts / 3600000), symbol, liq_side",
                (last_hour,)
            ).fetchall()

            if not ticks:
                log.debug("No new ticks to roll up")
                return

            for ts_ms, symbol, liq_side, notional, count in ticks:
                ts_hour = (ts_ms // 3600000) * 3600000  # round down to hour

                if liq_side == "long":
                    conn.execute(
                        "INSERT INTO liquidation_1h (ts_hour, symbol, long_notional, long_count) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(ts_hour, symbol) DO UPDATE SET "
                        "long_notional = long_notional + ?, long_count = long_count + ?",
                        (ts_hour, symbol, notional, count, notional, count)
                    )
                else:
                    conn.execute(
                        "INSERT INTO liquidation_1h (ts_hour, symbol, short_notional, short_count) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(ts_hour, symbol) DO UPDATE SET "
                        "short_notional = short_notional + ?, short_count = short_count + ?",
                        (ts_hour, symbol, notional, count, notional, count)
                    )

            log.info(f"Rolled up {len(ticks)} groups to 1h aggregates (since {last_hour})")

    def get_1h(self, symbol: str, hours: int = 168) -> list[dict]:
        """Get 1h liquidation aggregates for a symbol.

        Args:
            symbol: e.g. 'BTCUSDT'
            hours: number of hours to look back (default 168 = 7 days)

        Returns:
            List of dicts with ts_hour, long_notional, short_notional, long_count, short_count
        """
        cutoff = int(time.time() * 1000) - hours * 3600000
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT ts_hour, long_notional, short_notional, long_count, short_count "
                "FROM liquidation_1h WHERE symbol = ? AND ts_hour >= ? "
                "ORDER BY ts_hour",
                (symbol, cutoff)
            ).fetchall()
            return [
                {
                    "ts_hour": r[0],
                    "long_notional": r[1],
                    "short_notional": r[2],
                    "long_count": r[3],
                    "short_count": r[4],
                }
                for r in rows
            ]

    def get_health(self) -> dict:
        """Get collector health status."""
        with sqlite3.connect(self.db_path) as conn:
            status = conn.execute(
                "SELECT value FROM collector_meta WHERE key = 'status'"
            ).fetchone()
            last_hb = conn.execute(
                "SELECT value FROM collector_meta WHERE key = 'last_heartbeat'"
            ).fetchone()
            tick_count = conn.execute(
                "SELECT COUNT(*) FROM liquidation_ticks"
            ).fetchone()[0]
            agg_count = conn.execute(
                "SELECT COUNT(*) FROM liquidation_1h"
            ).fetchone()[0]
            last_tick = conn.execute(
                "SELECT MAX(ts) FROM liquidation_ticks"
            ).fetchone()[0]

        now_ms = int(time.time() * 1000)
        hb_age_ms = now_ms - int(last_hb[0]) if last_hb and last_hb[0] else None

        return {
            "status": status[0] if status else "unknown",
            "last_heartbeat_ms_ago": hb_age_ms,
            "tick_count": tick_count,
            "aggregate_count": agg_count,
            "last_tick_ts": last_tick,
            "is_healthy": hb_age_ms is not None and hb_age_ms < 300000,  # 5 min
        }


def main():
    """Run the liquidation collector as a standalone daemon."""
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    collector = LiquidationCollector()

    # Rollup on startup
    collector.rollup_1h()

    try:
        asyncio.run(collector.run())
    except KeyboardInterrupt:
        log.info("Interrupted, stopping...")
        collector.stop()


if __name__ == "__main__":
    main()