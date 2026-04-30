"""Fear & Greed Index collector."""

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp
import polars as pl

from config import MAX_RETRIES, RETRY_BASE_DELAY

logger = logging.getLogger(__name__)
BASE_URL = "https://api.alternative.me/fng/"


async def _fetch(session: aiohttp.ClientSession, limit: int = 0) -> dict:
    params = {"limit": limit, "format": "json"}
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(BASE_URL, params=params) as resp:
                if resp.status == 429:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                    continue
                resp.raise_for_status()
                return await resp.json()
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                logger.error("F&G fetch failed: %s", e)
                return {}
            await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    return {}


async def fetch_historical(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore) -> pl.DataFrame:
    async with semaphore:
        data = await _fetch(session, limit=0)
    if not data or "data" not in data:
        return pl.DataFrame(schema={
            "timestamp": pl.Datetime("us", "UTC"), "value": pl.Int64, "classification": pl.Utf8,
        })
    rows = []
    for item in data["data"]:
        rows.append({
            "timestamp": datetime.fromtimestamp(int(item["timestamp"]), tz=timezone.utc),
            "value": int(item["value"]),
            "classification": item["value_classification"],
        })
    return pl.DataFrame(rows)


async def fetch_new(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, existing: pl.DataFrame) -> pl.DataFrame:
    if existing.is_empty():
        return await fetch_historical(session, semaphore)
    # Just re-fetch all — F&G is small and daily
    return await fetch_historical(session, semaphore)