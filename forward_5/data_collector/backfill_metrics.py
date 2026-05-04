#!/usr/bin/env python3
"""Backfill Binance metrics (OI, LS Ratio, Taker Ratio) from Data Vision.

Downloads daily ZIP files from data.binance.vision containing 5-minute
metrics data for each asset. Aggregates to 1h and saves as parquet.

Data Vision metrics CSV schema:
  create_time, symbol, sum_open_interest, sum_open_interest_value,
  count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
  count_long_short_ratio, sum_taker_long_short_vol_ratio

Each daily ZIP has 288 rows (5min x 24h x 60/5).
We aggregate to 1h by taking the last value in each hour window
(snapshot-style, since OI/LS/Taker are point-in-time metrics).
"""

import io
import logging
import zipfile
from pathlib import Path

import polars as pl
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://data.binance.vision/data/futures/um/daily/metrics"
DATA_DIR = Path(__file__).parent.parent / "data"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]


def _list_available_dates(symbol: str, start_date: str = "2024-05-01") -> list[str]:
    """List all available dates for a symbol via S3 pagination."""
    import xml.etree.ElementTree as ET

    all_keys = []
    marker = ""
    base = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
    prefix = f"data/futures/um/daily/metrics/{symbol}/"

    while True:
        url = f"{base}?prefix={prefix}&max-keys=1000"
        if marker:
            url += f"&marker={marker}"
        r = requests.get(url, timeout=30)
        root = ET.fromstring(r.text)
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        keys = [c.text for c in root.findall(".//s3:Contents/s3:Key", ns) if c.text.endswith(".zip")]
        all_keys.extend(keys)
        truncated = root.find(".//s3:IsTruncated", ns)
        if truncated is not None and truncated.text == "true" and keys:
            marker = keys[-1]
        else:
            break

    # Filter by start_date and extract date strings
    dates = []
    for k in all_keys:
        date_str = k.split("-metrics-")[-1].replace(".zip", "")
        if date_str >= start_date:
            dates.append(date_str)
    return sorted(dates)


def _download_day(symbol: str, date_str: str) -> pl.DataFrame | None:
    """Download and parse one day of metrics."""
    url = f"{BASE_URL}/{symbol}/{symbol}-metrics-{date_str}.zip"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            logger.warning("Skip %s %s: HTTP %d", symbol, date_str, r.status_code)
            return None
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            csv_name = f"{symbol}-metrics-{date_str}.csv"
            with zf.open(csv_name) as f:
                df = pl.read_csv(f)
                return df
    except Exception as e:
        logger.warning("Error %s %s: %s", symbol, date_str, e)
        return None


def _aggregate_to_1h(df: pl.DataFrame, asset: str) -> pl.DataFrame:
    """Aggregate 5-min metrics to 1h by taking last value in each hour."""
    df = df.with_columns([
        pl.col("create_time").str.to_datetime("%Y-%m-%d %H:%M:%S", time_zone="UTC").alias("ts"),
    ]).drop("create_time").drop("symbol")

    # Floor to hour and take last value per hour (snapshot)
    df = df.with_columns(pl.col("ts").dt.truncate("1h").alias("hour"))
    df = df.group_by("hour").last().sort("hour")

    df = df.rename({
        "sum_open_interest": "sum_oi",
        "sum_open_interest_value": "sum_oi_value",
        "count_toptrader_long_short_ratio": "toptrader_ls_ratio",
        "sum_toptrader_long_short_ratio": "toptrader_ls_sum",
        "count_long_short_ratio": "ls_ratio",
        "sum_taker_long_short_vol_ratio": "taker_vol_ratio",
    })
    df = df.with_columns(pl.lit(asset).alias("asset"))
    df = df.rename({"hour": "timestamp"})

    return df.select(["timestamp", "asset", "sum_oi", "sum_oi_value",
                      "toptrader_ls_ratio", "ls_ratio", "taker_vol_ratio"])


def backfill_symbol(asset: str, start_date: str = "2024-05-01", output_path: Path | None = None) -> pl.DataFrame:
    """Backfill metrics for one asset."""
    symbol = f"{asset}USDT"
    if output_path is None:
        output_path = DATA_DIR / f"bn_metrics_{asset.lower()}_1h.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Listing dates for %s from %s...", symbol, start_date)
    dates = _list_available_dates(symbol, start_date)
    logger.info("Found %d days for %s (%s to %s)", len(dates), symbol, dates[0] if dates else "?", dates[-1] if dates else "?")

    if not dates:
        return pl.DataFrame()

    all_frames = []
    errors = 0

    for i, date_str in enumerate(dates):
        if (i + 1) % 50 == 0:
            logger.info("  %s: %d/%d downloaded", asset, i + 1, len(dates))
        day_df = _download_day(symbol, date_str)
        if day_df is not None and not day_df.is_empty():
            agg = _aggregate_to_1h(day_df, asset)
            all_frames.append(agg)
        else:
            errors += 1

    if not all_frames:
        logger.error("No data for %s!", asset)
        return pl.DataFrame()

    result = pl.concat(all_frames)
    result = result.unique(subset=["timestamp", "asset"]).sort(["timestamp"])

    result.write_parquet(output_path)
    logger.info("Done %s: %d rows (%d errors), saved to %s", asset, len(result), errors, output_path)
    return result


def backfill_all(start_date: str = "2024-05-01"):
    """Backfill all 6 assets, one at a time."""
    assets = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
    for asset in assets:
        backfill_symbol(asset, start_date)
        logger.info("---")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import sys
    asset = sys.argv[1] if len(sys.argv) > 1 else None
    start = sys.argv[2] if len(sys.argv) > 2 else "2024-05-01"
    if asset:
        backfill_symbol(asset, start)
    else:
        backfill_all(start)