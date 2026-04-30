"""Binance funding rate collector."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import aiohttp
import polars as pl

from config import BACKFILL_DAYS, BINANCE_SYMBOLS, DATA_DIR, MAX_RETRIES, RATE_LIMIT_PER_SECOND, RETRY_BASE_DELAY

logger = logging.getLogger(__name__)
BASE_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


async def _fetch_page(session: aiohttp.ClientSession, symbol: str, start_ms: int, end_ms: int | None = None) -> list[dict]:
    params = {"symbol": symbol, "startTime": start_ms, "limit": 1000}
    if end_ms:
        params["endTime"] = end_ms
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(BASE_URL, params=params) as resp:
                if resp.status == 429:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                    continue
                resp.raise_for_status()
                data = await resp.json()
                return data if isinstance(data, list) else []
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                logger.error("BN funding fetch failed for %s: %s", symbol, e)
                return []
            await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    return []


async def fetch_historical(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore) -> pl.DataFrame:
    days = BACKFILL_DAYS["binance_funding"]
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    all_rows: list[dict] = []
    delay = 1.0 / RATE_LIMIT_PER_SECOND

    for symbol in BINANCE_SYMBOLS:
        cursor = start_ms
        asset = symbol.replace("USDT", "")
        while cursor < now_ms:
            async with semaphore:
                page = await _fetch_page(session, symbol, cursor)
            if not page:
                break
            for item in page:
                all_rows.append({
                    "timestamp": datetime.fromtimestamp(item["fundingTime"] / 1000, tz=timezone.utc),
                    "asset": asset,
                    "funding_rate": float(item["fundingRate"]),
                    "mark_price": float(item.get("markPrice", 0.0)),
                })
            if len(page) < 1000:
                break
            cursor = int(page[-1]["fundingTime"]) + 1
            await asyncio.sleep(delay)
        await asyncio.sleep(delay)

    return pl.DataFrame(all_rows) if all_rows else pl.DataFrame(schema={
        "timestamp": pl.Datetime("us", "UTC"), "asset": pl.Utf8,
        "funding_rate": pl.Float64, "mark_price": pl.Float64,
    })


async def fetch_new(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, existing: pl.DataFrame) -> pl.DataFrame:
    if existing.is_empty():
        return await fetch_historical(session, semaphore)
    last_ts = existing.filter(pl.col("asset") == BINANCE_SYMBOLS[0].replace("USDT", "")).select(
        pl.col("timestamp").max()).item()
    start_ms = int(last_ts.timestamp() * 1000) + 1
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    all_rows: list[dict] = []
    delay = 1.0 / RATE_LIMIT_PER_SECOND

    for symbol in BINANCE_SYMBOLS:
        asset = symbol.replace("USDT", "")
        async with semaphore:
            page = await _fetch_page(session, symbol, start_ms)
        for item in page:
            all_rows.append({
                "timestamp": datetime.fromtimestamp(item["fundingTime"] / 1000, tz=timezone.utc),
                "asset": asset,
                "funding_rate": float(item["fundingRate"]),
                "mark_price": float(item.get("markPrice", 0.0)),
            })
        await asyncio.sleep(delay)

    return pl.DataFrame(all_rows) if all_rows else pl.DataFrame()