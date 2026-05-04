#!/usr/bin/env python3
"""V2 Data Collector — backfill, live, and status modes."""

import asyncio
import logging
import sys
from pathlib import Path
from signal import SIGINT, SIGTERM

import aiohttp
import polars as pl

from config import DATA_DIR, POLL_INTERVAL, RATE_LIMIT_PER_SECOND
from sources import hyperliquid, binance_funding, binance_oi, binance_ls_ratio, binance_taker, fear_greed, binance_klines

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("collector")

SOURCES = {
    "hl_funding": (hyperliquid, "hl_funding.parquet"),
    "bn_funding": (binance_funding, "bn_funding.parquet"),
    "bn_oi": (binance_oi, "bn_oi.parquet"),
    "bn_ls_ratio": (binance_ls_ratio, "bn_ls_ratio.parquet"),
    "bn_taker_ratio": (binance_taker, "bn_taker_ratio.parquet"),
    "fear_greed": (fear_greed, "fear_greed.parquet"),
    "bn_klines": (binance_klines, "bn_klines_1h.parquet"),
}


def _load_existing(name: str) -> pl.DataFrame:
    path = DATA_DIR / SOURCES[name][1]
    if path.exists():
        return pl.read_parquet(path)
    return pl.DataFrame()


def _save(df: pl.DataFrame, name: str):
    if df.is_empty():
        return
    path = DATA_DIR / SOURCES[name][1]
    existing = _load_existing(name)
    if not existing.is_empty():
        # Deduplicate on timestamp + asset
        if "asset" in df.columns:
            df = existing.vstack(df).unique(subset=["timestamp", "asset"])
        else:
            df = existing.vstack(df).unique(subset=["timestamp"])
    df.write_parquet(path)
    logger.info("Saved %s: %d rows → %s", name, len(df), path)


async def backfill():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(RATE_LIMIT_PER_SECOND)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for name, (module, _) in SOURCES.items():
            tasks.append(_backfill_source(name, module, session, semaphore))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for name, result in zip(SOURCES, results):
            if isinstance(result, Exception):
                logger.error("Backfill %s failed: %s", name, result)
            else:
                _save(result, name)


async def _backfill_source(name: str, module, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore) -> pl.DataFrame:
    logger.info("Backfilling %s...", name)
    return await module.fetch_historical(session, semaphore)


async def live():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(RATE_LIMIT_PER_SECOND)
    logger.info("Starting live mode, polling every %ds", POLL_INTERVAL)
    stop = asyncio.Event()

    async def _shutdown():
        stop.set()

    import signal as _signal
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(_signal.SIGINT, lambda: asyncio.create_task(_shutdown()))
    loop.add_signal_handler(_signal.SIGTERM, lambda: asyncio.create_task(_shutdown()))

    async with aiohttp.ClientSession() as session:
        while not stop.is_set():
            logger.info("Live poll starting...")
            for name, (module, _) in SOURCES.items():
                try:
                    existing = _load_existing(name)
                    new_data = await module.fetch_new(session, semaphore, existing)
                    if not new_data.is_empty():
                        _save(new_data, name)
                except Exception as e:
                    logger.error("Live poll %s error: %s", name, e)
            logger.info("Live poll done, sleeping %ds", POLL_INTERVAL)
            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass


def status():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("\n=== Data Collector Status ===\n")
    for name, (_, filename) in SOURCES.items():
        path = DATA_DIR / filename
        if not path.exists():
            print(f"  {name}: ❌ no data")
            continue
        df = pl.read_parquet(path)
        if df.is_empty():
            print(f"  {name}: ❌ empty")
            continue
        ts_min = df.select(pl.col("timestamp").min()).item()
        ts_max = df.select(pl.col("timestamp").max()).item()
        n_rows = len(df)
        assets = df["asset"].n_unique() if "asset" in df.columns else 1
        print(f"  {name}: ✅ {n_rows:,} rows, {assets} assets")
        print(f"         {ts_min} → {ts_max}")
    print()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 collector.py <backfill|live|status>")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "backfill":
        await backfill()
    elif cmd == "live":
        await live()
    elif cmd == "status":
        status()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())