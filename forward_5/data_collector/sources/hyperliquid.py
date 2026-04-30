"""Hyperliquid funding rate collector."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import polars as pl

from config import ASSETS, BACKFILL_DAYS, DATA_DIR, MAX_RETRIES, RATE_LIMIT_PER_SECOND, RETRY_BASE_DELAY

logger = logging.getLogger(__name__)
ENDPOINT = "https://api.hyperliquid.xyz/info"
PAGE_LIMIT = 500  # max items per request


async def _fetch_page(session: aiohttp.ClientSession, coin: str, start_ms: int) -> list[dict]:
    payload = {"type": "fundingHistory", "coin": coin, "startTime": start_ms}
    for attempt in range(MAX_RETRIES):
        try:
            async with session.post(ENDPOINT, json=payload) as resp:
                if resp.status == 429:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning("HL 429 for %s, retrying in %.1fs", coin, delay)
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                data = await resp.json()
                return data if isinstance(data, list) else []
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                logger.error("HL funding fetch failed for %s: %s", coin, e)
                return []
            await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    return []


async def fetch_historical(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore) -> pl.DataFrame:
    days = BACKFILL_DAYS["hyperliquid"]
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    all_rows: list[dict] = []
    delay = 1.0 / RATE_LIMIT_PER_SECOND

    for coin in ASSETS:
        cursor = start_ms
        while True:
            async with semaphore:
                page = await _fetch_page(session, coin, cursor)
            if not page:
                break
            for item in page:
                all_rows.append({
                    "timestamp": datetime.fromtimestamp(item["time"] / 1000, tz=timezone.utc),
                    "asset": coin,
                    "funding_rate": float(item["fundingRate"]),
                    "premium": float(item.get("premium", 0.0)),
                })
            if len(page) < PAGE_LIMIT:
                break
            cursor = page[-1]["time"] + 1
            await asyncio.sleep(delay)
        await asyncio.sleep(delay)

    return pl.DataFrame(all_rows) if all_rows else pl.DataFrame(schema={
        "timestamp": pl.Datetime("us", "UTC"), "asset": pl.Utf8,
        "funding_rate": pl.Float64, "premium": pl.Float64,
    })


async def fetch_new(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, existing: pl.DataFrame) -> pl.DataFrame:
    if existing.is_empty():
        return await fetch_historical(session, semaphore)
    last_ts = existing.filter(pl.col("asset") == ASSETS[0]).select(pl.col("timestamp").max()).item()
    start_ms = int(last_ts.timestamp() * 1000) + 1
    all_rows: list[dict] = []
    delay = 1.0 / RATE_LIMIT_PER_SECOND

    for coin in ASSETS:
        async with semaphore:
            page = await _fetch_page(session, coin, start_ms)
        for item in page:
            all_rows.append({
                "timestamp": datetime.fromtimestamp(item["time"] / 1000, tz=timezone.utc),
                "asset": coin,
                "funding_rate": float(item["fundingRate"]),
                "premium": float(item.get("premium", 0.0)),
            })
        await asyncio.sleep(delay)

    return pl.DataFrame(all_rows) if all_rows else pl.DataFrame()