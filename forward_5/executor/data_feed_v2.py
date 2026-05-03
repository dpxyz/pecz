"""
Executor V2 — Data Feed with Funding Rate + OI + FGI + DXY
Extends V1 DataFeed with:
- Funding rate polling (Binance 8h)
- Z-score calculation (rolling 168h window)
- Regime detection (bull200 = close > ema200)
- Open Interest (Binance, hourly)
- Fear & Greed Index (Alternative.me, daily)
- DXY Dollar Index (Yahoo Finance, daily)
"""

from typing import Optional
import asyncio
import time
import sqlite3
import logging
from pathlib import Path

import requests

from data_feed import DataFeed, SYMBOL_MAP, PAPER_MODE, API_URL, API_URL_TESTNET

log = logging.getLogger("data_feed_v2")

# Funding rate polling interval
FUNDING_POLL_INTERVAL = 300  # 5 minutes
FUNDING_WINDOW = 168  # 168 hours = 7 days, for z-score calculation
OI_POLL_INTERVAL = 3600  # 1 hour
FGI_POLL_INTERVAL = 3600  # 1 hour (API updates daily)
FGI_API_URL = "https://api.alternative.me/fng/"
DXY_POLL_INTERVAL = 3600  # 1 hour

# Active V2 assets (only these get funding signals)
V2_ACTIVE_ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]  # V11 WF Gate passed; AVAX/DOGE failed gate (bear-only, 0 trades in bull)


class DataFeedV2(DataFeed):
    """V2 DataFeed: candles + funding + OI + FGI + DXY."""

    def __init__(self, db_path: str = "executor/state.db",
                 assets: Optional[list[str]] = None,
                 on_candle=None,
                 engine_last_processed_ts: Optional[int] = None):
        assets = assets or V2_ACTIVE_ASSETS
        super().__init__(db_path=db_path, assets=assets, on_candle=on_candle,
                         engine_last_processed_ts=engine_last_processed_ts)

        self._funding_data: dict[str, list[dict]] = {}
        self._funding_z: dict[str, Optional[float]] = {}
        self._bull200: dict[str, bool] = {}
        # Store engine's original callback before replacing with V2 wrapper
        self.on_candle = self._on_candle_v2  # V2: compute regime BEFORE engine callback
        self._original_on_candle = on_candle  # engine's callback
        self._oi_data: dict[str, float] = {}
        self._oi_prev: dict[str, float] = {}
        self._oi_drop_pct: dict[str, float] = {}
        self._fgi: Optional[int] = None
        self._fgi_class: Optional[str] = None
        self._dxy: Optional[float] = None
        self._dxy_5d_chg: Optional[float] = None

        self._init_funding_db()

    def _compute_initial_regime(self):
        """Compute bull200 from existing candle data after backfill."""
        for symbol in self.assets:
            candles = self.get_candles(symbol, limit=210)
            if len(candles) >= 200:
                import polars as pl
                closes = pl.Series([c["close"] for c in candles])
                ema_200 = closes.ewm_mean(alpha=2/201, min_samples=200)
                current_ema200 = ema_200[-1]
                if current_ema200 is not None:
                    self._bull200[symbol] = closes[-1] > current_ema200
                    log.info(f"  📊 {symbol}: initial regime={'bull200' if self._bull200[symbol] else 'bear'} (close={closes[-1]:.2f}, ema200={current_ema200:.2f})")

    def _init_funding_db(self):
        """Create all V2 tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS funding_rates (
                    symbol TEXT NOT NULL, ts INTEGER NOT NULL,
                    funding_rate REAL NOT NULL, source TEXT DEFAULT 'binance',
                    PRIMARY KEY (symbol, ts))
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_funding_ts ON funding_rates(symbol, ts)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS open_interest (
                    symbol TEXT NOT NULL, ts INTEGER NOT NULL,
                    oi_contracts REAL NOT NULL, oi_value_usd REAL,
                    source TEXT DEFAULT 'binance', PRIMARY KEY (symbol, ts))
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_oi_ts ON open_interest(symbol, ts)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS fear_greed (
                    ts INTEGER PRIMARY KEY, value INTEGER NOT NULL,
                    classification TEXT NOT NULL)
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS dxy_daily (
                    ts INTEGER PRIMARY KEY, dxy_close REAL NOT NULL,
                    dxy_5d_chg REAL)
            """)

    async def start(self):
        """Start all polling loops."""
        self._running = True
        mode_str = "⛔ TESTNET (Paper)" if PAPER_MODE else "🔴 MAINNET (REAL MONEY)"
        log.info(f"DataFeedV2 starting - {mode_str} - assets: {self.assets}")
        log.info(f"  Candle source: REST API polling every 60s")
        log.info(f"  Funding source: Binance API polling every {FUNDING_POLL_INTERVAL}s")

        await self._backfill()
        await self._backfill_funding()
        self._compute_initial_regime()  # Now we have 200+ candles for EMA200

        await asyncio.gather(
            self._poll_loop(),
            self._funding_poll_loop(),
            self._oi_poll_loop(),
            self._fgi_poll_loop(),
            self._dxy_poll_loop(),
        )

    # ── Getters ──

    def get_funding_z(self, symbol: str) -> Optional[float]:
        return self._funding_z.get(symbol)

    def get_regime(self, symbol: str) -> Optional[bool]:
        return self._bull200.get(symbol)

    def get_oi(self, symbol: str) -> Optional[float]:
        return self._oi_data.get(symbol)

    def get_oi_drop(self, symbol: str) -> Optional[float]:
        return self._oi_drop_pct.get(symbol)

    def get_fgi(self) -> Optional[int]:
        return self._fgi

    def get_fgi_class(self) -> Optional[str]:
        return self._fgi_class

    def get_dxy(self) -> Optional[float]:
        return self._dxy

    def get_dxy_5d_chg(self) -> Optional[float]:
        return self._dxy_5d_chg

    # ── Candle Polling (inherited from V1) ──

    async def _poll_loop(self):
        """V1-style candle polling loop."""
        now_ms = int(time.time() * 1000)
        current_hour = (now_ms // 3600000) * 3600000
        for symbol in self.assets:
            with sqlite3.connect(self.db_path) as conn:
                last_in_db = conn.execute(
                    "SELECT MAX(ts) FROM candles WHERE symbol = ? AND ts < ?",
                    (symbol, current_hour)).fetchone()[0]
                if last_in_db:
                    self._last_processed[symbol] = last_in_db
                else:
                    self._last_processed[symbol] = 0
        while self._running:
            try:
                await self._poll_candles()
            except Exception as e:
                log.error(f"Candle poll error: {e}")
            if self._running:
                await asyncio.sleep(60)

    # ── Funding Rate ──

    async def _funding_poll_loop(self):
        while self._running:
            try:
                await self._poll_funding()
            except Exception as e:
                log.error(f"Funding poll error: {e}")
            if self._running:
                await asyncio.sleep(FUNDING_POLL_INTERVAL)

    async def _backfill_funding(self):
        log.info("Backfilling funding rates from Binance...")
        start_ms = int((time.time() - FUNDING_WINDOW * 3600) * 1000)
        total = 0
        for symbol in self.assets:
            try:
                resp = requests.get(
                    "https://fapi.binance.com/fapi/v1/fundingRate",
                    params={"symbol": symbol, "startTime": start_ms, "limit": 1000},
                    timeout=15)
                data = resp.json()
                if not isinstance(data, list):
                    log.error(f"Funding backfill failed for {symbol}")
                    continue
                count = 0
                with sqlite3.connect(self.db_path) as conn:
                    for item in data:
                        ts = int(item["fundingTime"])
                        rate = float(item["fundingRate"])
                        conn.execute(
                            "INSERT OR REPLACE INTO funding_rates (symbol, ts, funding_rate, source) VALUES (?, ?, ?, 'binance')",
                            (symbol, ts, rate))
                        count += 1
                total += count
                log.info(f"  ✅ {symbol}: {count} funding rates backfilled")
            except Exception as e:
                log.error(f"  ❌ {symbol}: funding backfill failed: {e}")
        log.info(f"Funding backfill complete: {total} rates total")
        self._update_funding_zscores()

    async def _poll_funding(self):
        for symbol in self.assets:
            try:
                resp = requests.get(
                    "https://fapi.binance.com/fapi/v1/fundingRate",
                    params={"symbol": symbol, "limit": 1}, timeout=15)
                data = resp.json()
                if not isinstance(data, list) or len(data) == 0:
                    continue
                item = data[0]
                ts = int(item["fundingTime"])
                rate = float(item["fundingRate"])
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO funding_rates (symbol, ts, funding_rate, source) VALUES (?, ?, ?, 'binance')",
                        (symbol, ts, rate))
                log.info(f"💰 {symbol}: funding_rate={rate:.6f} @ {ts}")
            except Exception as e:
                log.error(f"Funding poll error for {symbol}: {e}")
        self._update_funding_zscores()

    def _update_funding_zscores(self):
        window_ms = FUNDING_WINDOW * 3600 * 1000
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - window_ms
        for symbol in self.assets:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT ts, funding_rate FROM funding_rates WHERE symbol = ? AND ts >= ? ORDER BY ts ASC",
                    (symbol, cutoff)).fetchall()
            if len(rows) < 10:
                log.warning(f"⚠️ {symbol}: Only {len(rows)} funding rates for z-score")
                self._funding_z[symbol] = None
                continue
            rates = [r[1] for r in rows]
            mean_rate = sum(rates) / len(rates)
            std_rate = (sum((r - mean_rate) ** 2 for r in rates) / len(rates)) ** 0.5
            if std_rate < 1e-10:
                self._funding_z[symbol] = 0.0
            else:
                z = (rates[-1] - mean_rate) / std_rate
                self._funding_z[symbol] = round(z, 4)
            log.info(f"  {symbol}: z={self._funding_z[symbol]:.4f} (rate={rates[-1]:.6f}, mean={mean_rate:.6f}, std={std_rate:.6f}, n={len(rows)})")

    # ── Open Interest ──

    async def _oi_poll_loop(self):
        await self._backfill_oi()
        while self._running:
            try:
                await asyncio.sleep(OI_POLL_INTERVAL)
                await self._poll_oi()
            except Exception as e:
                log.error(f"OI poll error: {e}")

    async def _backfill_oi(self):
        log.info("Backfilling Open Interest from Binance...")
        for symbol in self.assets:
            try:
                resp = requests.get(
                    "https://fapi.binance.com/futures/data/openInterestHist",
                    params={"symbol": symbol, "period": "1h", "limit": 500},
                    timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                data = resp.json()
                if not isinstance(data, list):
                    log.error(f"OI backfill failed for {symbol}")
                    continue
                count = 0
                with sqlite3.connect(self.db_path) as conn:
                    for item in data:
                        ts = int(item["timestamp"])
                        oi = float(item["sumOpenInterest"])
                        oi_val = float(item.get("sumOpenInterestValue", 0))
                        conn.execute(
                            "INSERT OR REPLACE INTO open_interest (symbol, ts, oi_contracts, oi_value_usd, source) VALUES (?, ?, ?, ?, 'binance')",
                            (symbol, ts, oi, oi_val))
                        count += 1
                if data:
                    self._oi_data[symbol] = float(data[-1]["sumOpenInterest"])
                log.info(f"  ✅ {symbol}: {count} OI data points backfilled")
            except Exception as e:
                log.error(f"  ❌ {symbol}: OI backfill failed: {e}")

    async def _poll_oi(self):
        for symbol in self.assets:
            try:
                resp = requests.get(
                    "https://fapi.binance.com/fapi/v1/openInterest",
                    params={"symbol": symbol}, timeout=15,
                    headers={"User-Agent": "Mozilla/5.0"})
                data = resp.json()
                if not isinstance(data, dict) or "openInterest" not in data:
                    continue
                oi = float(data["openInterest"])
                ts = int(time.time() * 1000)
                prev_oi = self._oi_data.get(symbol)
                if prev_oi and prev_oi > 0:
                    drop_pct = (oi - prev_oi) / prev_oi * 100
                    self._oi_drop_pct[symbol] = round(drop_pct, 2)
                    if abs(drop_pct) > 3:
                        log.info(f"📊 {symbol}: OI change {drop_pct:+.1f}% ({prev_oi:,.0f} → {oi:,.0f})")
                self._oi_data[symbol] = oi
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO open_interest (symbol, ts, oi_contracts, oi_value_usd, source) VALUES (?, ?, ?, 0, 'binance')",
                        (symbol, ts, oi))
                log.debug(f"📊 {symbol}: OI={oi:,.0f} contracts")
            except Exception as e:
                log.error(f"OI poll error for {symbol}: {e}")

    # ── Fear & Greed ──

    async def _fgi_poll_loop(self):
        await self._poll_fgi()
        while self._running:
            try:
                await asyncio.sleep(FGI_POLL_INTERVAL)
                await self._poll_fgi()
            except Exception as e:
                log.error(f"FGI poll error: {e}")

    async def _poll_fgi(self):
        try:
            resp = requests.get(FGI_API_URL, params={"limit": 3}, timeout=10)
            data = resp.json()
            if "data" not in data or len(data["data"]) == 0:
                log.warning("FGI: No data returned")
                return
            current = data["data"][0]
            self._fgi = int(current["value"])
            self._fgi_class = current["value_classification"]
            ts = int(current["timestamp"])
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO fear_greed (ts, value, classification) VALUES (?, ?, ?)",
                    (ts, self._fgi, self._fgi_class))
            log.info(f"😱 FGI: {self._fgi} ({self._fgi_class})")
        except Exception as e:
            log.error(f"FGI poll failed: {e}")

    # ── DXY (Dollar Index) ──

    async def _dxy_poll_loop(self):
        await self._poll_dxy()
        while self._running:
            try:
                await asyncio.sleep(DXY_POLL_INTERVAL)
                await self._poll_dxy()
            except Exception as e:
                log.error(f"DXY poll error: {e}")

    async def _poll_dxy(self):
        try:
            import yfinance as yf
            dxy = yf.Ticker("DX-Y.NYB")
            hist = dxy.history(period="5d")
            if len(hist) < 2:
                log.warning("DXY: insufficient data")
                return
            current = float(hist["Close"].iloc[-1])
            prev_5d = float(hist["Close"].iloc[0])
            chg_5d = (current - prev_5d) / prev_5d * 100
            ts = int(hist.index[-1].timestamp() * 1000)
            self._dxy = current
            self._dxy_5d_chg = round(chg_5d, 2)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO dxy_daily (ts, dxy_close, dxy_5d_chg) VALUES (?, ?, ?)",
                    (ts, current, self._dxy_5d_chg))
            log.info(f"💵 DXY: {current:.2f} (5d: {chg_5d:+.2f}%)")
        except Exception as e:
            log.error(f"DXY poll failed: {e}")

    # ── Regime Detection ──

    async def _on_candle_v2(self, symbol: str, candle: dict):
        """V2 candle callback: compute regime THEN forward to engine."""
        # Update regime detection
        candles = self.get_candles(symbol, limit=210)
        n_candles = len(candles)
        if n_candles >= 200:
            import polars as pl
            closes = pl.Series([c["close"] for c in candles])
            ema_200 = closes.ewm_mean(alpha=2 / 201, min_samples=200)
            current_close = closes[-1]
            current_ema200 = ema_200[-1]
            if current_ema200 is not None:
                self._bull200[symbol] = current_close > current_ema200
                log.info(f"  📊 {symbol}: regime={'bull200' if self._bull200[symbol] else 'bear'} (close={current_close:.2f}, ema200={current_ema200:.2f}, candles={n_candles})")
            else:
                log.warning(f"  ⚠️ {symbol}: EMA200 is None despite {n_candles} candles")
        else:
            log.warning(f"  ⚠️ {symbol}: only {n_candles} candles, need 200 for regime")

        # Forward to engine
        if self._original_on_candle:
            await self._original_on_candle(symbol, candle)


async def _test():
    """Quick test of V2 DataFeed."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    feed = DataFeedV2(assets=V2_ACTIVE_ASSETS)
    await feed._backfill_funding()
    for symbol in V2_ACTIVE_ASSETS:
        z = feed.get_funding_z(symbol)
        regime = feed.get_regime(symbol)
        print(f"  {symbol}: z={z}, bull200={regime}")


if __name__ == "__main__":
    asyncio.run(_test())