"""Binance Klines historical collector with taker buy volume.

Binance Futures klines provide taker_buy_base_asset_volume (field 9)
and taker_buy_quote_asset_volume (field 10), enabling Taker Buy/Sell
Ratio reconstruction: R = V_buy / (V_total - V_buy)

API returns up to 1500 candles per request. We paginate backwards from
now to fill historical gaps, or forward from existing data for updates.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import aiohttp
import polars as pl

from config import BINANCE_SYMBOLS, MAX_RETRIES, RATE_LIMIT_PER_SECOND, RETRY_BASE_DELAY

logger = logging.getLogger(__name__)

BASE_URL = "https://fapi.binance.com/fapi/v1/klines"

# Kline response fields:
# 0=open_time, 1=open, 2=high, 3=low, 4=close, 5=volume,
# 6=close_time, 7=quote_volume, 8=trades,
# 9=taker_buy_base_asset_volume, 10=taker_buy_quote_asset_volume,
# 11=ignore

SYMBOL_MAP = {s: s for s in BINANCE_SYMBOLS}  # BTCUSDT -> BTCUSDT

DAYS_PER_ASSET = 365  # Default backfill depth


async def _fetch_page(
    session: aiohttp.ClientSession,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int | None = None,
    limit: int = 1500,
) -> list[list]:
    """Fetch one page of klines from Binance."""
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "limit": limit,
    }
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
                logger.error("BN klines fetch failed %s %s: %s", symbol, interval, e)
                return []
            await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    return []


def _parse_klines(rows: list[list], asset: str) -> list[dict]:
    """Parse raw kline rows into dicts."""
    result = []
    for r in rows:
        result.append({
            "timestamp": int(r[0]),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": float(r[5]),
            "quote_volume": float(r[7]),
            "trades": int(r[8]),
            "taker_buy_vol": float(r[9]),
            "taker_buy_quote_vol": float(r[10]),
            "asset": asset,
        })
    return result


async def fetch_historical(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    interval: str = "1h",
    days: int = DAYS_PER_ASSET,
) -> pl.DataFrame:
    """Backfill klines with taker volume for all assets."""
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    all_rows: list[dict] = []
    delay = 1.0 / RATE_LIMIT_PER_SECOND

    for symbol in BINANCE_SYMBOLS:
        asset = symbol.replace("USDT", "")
        cursor = start_ms
        logger.info("BN klines backfill %s %s: from %s", asset, interval,
                     datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).date())

        while cursor < now_ms:
            async with semaphore:
                page = await _fetch_page(session, symbol, interval, cursor)
            if not page:
                break
            all_rows.extend(_parse_klines(page, asset))
            if len(page) < 1500:
                break
            cursor = int(page[-1][0]) + 1  # next ms after last candle
            await asyncio.sleep(delay)
        await asyncio.sleep(delay)

    if not all_rows:
        return pl.DataFrame(schema={
            "timestamp": pl.Int64, "open": pl.Float64, "high": pl.Float64,
            "low": pl.Float64, "close": pl.Float64, "volume": pl.Float64,
            "quote_volume": pl.Float64, "trades": pl.Int32,
            "taker_buy_vol": pl.Float64, "taker_buy_quote_vol": pl.Float64,
            "asset": pl.Utf8,
        })

    df = pl.DataFrame(all_rows)
    # Deduplicate and sort
    df = df.unique(subset=["timestamp", "asset"]).sort(["asset", "timestamp"])
    # Compute taker ratio for consistency with fetch_new
    df = compute_taker_ratio(df)
    logger.info("BN klines: %d rows total across %d assets", len(df), df["asset"].n_unique())
    return df


async def fetch_new(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    existing: pl.DataFrame,
    interval: str = "1h",
) -> pl.DataFrame:
    """Fetch new klines since last existing timestamp."""
    if existing.is_empty():
        return await fetch_historical(session, semaphore, interval)

    all_rows: list[dict] = []
    delay = 1.0 / RATE_LIMIT_PER_SECOND
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    for symbol in BINANCE_SYMBOLS:
        asset = symbol.replace("USDT", "")
        asset_df = existing.filter(pl.col("asset") == asset)
        if asset_df.is_empty():
            continue
        last_ts = asset_df.select(pl.col("timestamp").max()).item()
        cursor = int(last_ts) + 1

        while cursor < now_ms:
            async with semaphore:
                page = await _fetch_page(session, symbol, interval, cursor)
            if not page:
                break
            all_rows.extend(_parse_klines(page, asset))
            if len(page) < 1500:
                break
            cursor = int(page[-1][0]) + 1
            await asyncio.sleep(delay)
        await asyncio.sleep(delay)

    if not all_rows:
        return pl.DataFrame()

    df = pl.DataFrame(all_rows).unique(subset=["timestamp", "asset"]).sort(["asset", "timestamp"])
    return compute_taker_ratio(df)


def compute_taker_ratio(df: pl.DataFrame) -> pl.DataFrame:
    """Compute taker buy/sell ratio from kline data.
    
    R = V_taker_buy / (V_total - V_taker_buy)
    
    Returns df with added column 'taker_buy_sell_ratio'.
    """
    return df.with_columns([
        (pl.col("taker_buy_vol") / (pl.col("volume") - pl.col("taker_buy_vol")))
        .alias("taker_buy_sell_ratio")
    ])