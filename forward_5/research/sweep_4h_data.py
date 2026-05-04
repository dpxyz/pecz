"""
Phase 1.1: 4h Funding Sweep — Data Aggregation

The 4h timeframe is mathematically aligned with 8h funding epochs:
- 8h epoch → 2 updates at 4h intervals
- 1h bars are MISALIGNED (3 updates per epoch, phase drift)
- 4h bars give exactly 2 observations per funding period

This module:
1. Loads 1h price data + 8h funding data
2. Aggregates to 4h bars
3. Aligns funding rates to 4h timestamps
4. Computes indicators (EMA50, EMA200, z-scores, etc.)
5. Outputs clean 4h dataset for the sweep
"""

import logging
from pathlib import Path
from dataclasses import dataclass

import numpy as np
import polars as pl

log = logging.getLogger("sweep_4h")

DATA_DIR = Path(__file__).parent.parent / "data_collector" / "data"
ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]

# 4h bar interval in milliseconds
FOUR_H_MS = 4 * 3600 * 1000
EIGHT_H_MS = 8 * 3600 * 1000


@dataclass
class AssetData4h:
    """4h aggregated data for one asset."""
    asset: str
    df: pl.DataFrame  # 4h OHLCV + funding + indicators
    n_bars: int
    start_date: str
    end_date: str


def aggregate_1h_to_4h(df_1h: pl.DataFrame) -> pl.DataFrame:
    """Aggregate 1h bars into 4h bars.
    
    Groups by 4h windows, creates OHLCV from the 4 constituent 1h bars.
    """
    # Bucket timestamps into 4h windows
    df = df_1h.with_columns(
        (pl.col("timestamp") // FOUR_H_MS * FOUR_H_MS).alias("ts4h")
    )
    
    # Aggregate OHLCV
    df_4h = df.sort(["asset", "ts4h"]).group_by(["asset", "ts4h"]).agg([
        pl.col("open").first().alias("open"),
        pl.col("high").max().alias("high"),
        pl.col("low").min().alias("low"),
        pl.col("close").last().alias("close"),
        pl.col("volume").sum().alias("volume"),
    ]).sort(["asset", "ts4h"])
    
    # Rename for consistency
    df_4h = df_4h.rename({"ts4h": "timestamp"})
    
    return df_4h


def align_funding_to_4h(funding_df: pl.DataFrame) -> pl.DataFrame:
    """Align 8h funding data to 4h timestamps.
    
    Each 8h funding rate applies to the 4h bars within that epoch.
    We forward-fill: the rate at T applies to bars T and T+4h.
    """
    # Bucket into 8h epochs, then expand to 4h
    df = funding_df.with_columns(
        (pl.col("timestamp") // EIGHT_H_MS * EIGHT_H_MS).alias("epoch8h")
    )
    
    # For each 8h epoch, create two 4h entries
    result_rows = []
    for row in df.iter_rows(named=True):
        epoch = row["epoch8h"]
        rate = row["funding_rate"]
        asset = row["asset"]
        # 4h bar at start of epoch
        result_rows.append({"timestamp": epoch, "asset": asset, "funding_rate": rate})
        # 4h bar at mid-epoch (+4h)
        result_rows.append({"timestamp": epoch + FOUR_H_MS, "asset": asset, "funding_rate": rate})
    
    return pl.DataFrame(result_rows).sort(["asset", "timestamp"])


def compute_4h_indicators(df: pl.DataFrame) -> pl.DataFrame:
    """Compute trading indicators on 4h data."""
    close = df["close"].to_numpy().astype(float)
    volume = df["volume"].to_numpy().astype(float)
    
    # EMAs
    ema50 = _ema(close, 12)   # 12 bars = 2 days on 4h
    ema200 = _ema(close, 50)   # 50 bars = ~8 days on 4h
    
    # Volume SMA
    vol_sma = _sma(volume, 12)
    vol_ratio = np.where(vol_sma > 0, volume / vol_sma, 1.0)
    
    # Add indicator columns first (can't reference new cols in same with_columns)
    df = df.with_columns([
        pl.Series("ema50", ema50),
        pl.Series("ema200", ema200),
        pl.Series("vol_ratio", vol_ratio),
    ])
    
    # Now add derived columns that reference the new ones
    df = df.with_columns([
        (pl.col("close") > pl.col("ema200")).cast(pl.Int8).alias("bull200"),
        (pl.col("close") > pl.col("ema50")).cast(pl.Int8).alias("bull50"),
    ])
    
    return df


def compute_funding_zscores(df: pl.DataFrame, window: int = 42) -> pl.DataFrame:
    """Compute rolling z-scores for funding rate on 4h data.
    
    window=42 bars = 7 days on 4h timeframe.
    """
    if "funding_rate" not in df.columns:
        return df
    
    rates = df["funding_rate"].to_numpy().astype(float)
    n = len(rates)
    z_scores = np.full(n, np.nan)
    
    for i in range(window, n):
        w = rates[i - window:i]
        mean = np.nanmean(w)
        std = np.nanstd(w)
        if std > 0:
            z_scores[i] = (rates[i] - mean) / std
    
    df = df.with_columns([
        pl.Series("funding_z", z_scores),
        pl.Series("funding_rate", rates),
    ])
    
    return df


def load_asset_data_4h(asset: str) -> AssetData4h:
    """Load and prepare 4h data for a single asset."""
    log.info(f"Loading 4h data for {asset}...")
    
    # Load 1h prices
    prices_path = DATA_DIR / "prices_all_1h.parquet"
    if not prices_path.exists():
        prices_path = DATA_DIR / "prices_1h.parquet"
    
    prices = pl.read_parquet(prices_path)
    asset_prices = prices.filter(pl.col("asset") == asset).sort("timestamp")
    
    if len(asset_prices) == 0:
        raise ValueError(f"No price data for {asset}")
    
    # Aggregate to 4h
    df_4h = aggregate_1h_to_4h(asset_prices)
    log.info(f"  {asset}: {len(asset_prices)} 1h bars → {len(df_4h)} 4h bars")
    
    # Load funding data
    funding_path = DATA_DIR / "hl_funding_full.parquet"
    if not funding_path.exists():
        funding_path = DATA_DIR / "hl_funding.parquet"
    
    funding = pl.read_parquet(funding_path)
    asset_funding = funding.filter(pl.col("asset") == asset).sort("timestamp")
    
    if len(asset_funding) > 0:
        # Aggregate funding to 4h buckets (one rate per 4h bar)
        fund_4h = asset_funding.with_columns(
            (pl.col("timestamp") // FOUR_H_MS * FOUR_H_MS).alias("ts4h")
        ).group_by("ts4h").agg(
            pl.col("funding_rate").last()
        ).sort("ts4h").rename({"ts4h": "timestamp"})
        
        # Use asof join for nearest-timestamp matching (avoids duplicates)
        df_4h = df_4h.sort("timestamp").join_asof(
            fund_4h.sort("timestamp"),
            on="timestamp",
            strategy="backward"  # use last known funding rate
        )
        # Forward-fill any remaining gaps
        df_4h = df_4h.sort("timestamp").with_columns(
            pl.col("funding_rate").forward_fill()
        )
        log.info(f"  {asset}: funding aligned ({len(asset_funding)} 8h rates → {len(fund_4h)} 4h entries)")
    else:
        log.warning(f"  {asset}: NO funding data available")
        df_4h = df_4h.with_columns(pl.lit(None).cast(pl.Float64).alias("funding_rate"))
    
    # Compute indicators BEFORE dropping NaN (avoids shape mismatch)
    df_4h = compute_4h_indicators(df_4h)
    df_4h = compute_funding_zscores(df_4h, window=42)
    
    # Drop rows where essential columns are NaN (warmup + no price data)
    n_before = len(df_4h)
    df_4h = df_4h.filter(pl.col("close").is_not_null())
    # Forward-fill any remaining indicator NaN
    df_4h = df_4h.sort("timestamp").with_columns([
        pl.col("ema50").forward_fill(),
        pl.col("ema200").forward_fill(),
        pl.col("bull200").forward_fill(),
        pl.col("bull50").forward_fill(),
    ])
    n_after = len(df_4h)
    log.info(f"  {asset}: {n_before} → {n_after} bars after dropping NaN warmup")
    
    ts = df_4h["timestamp"].to_numpy()
    from datetime import datetime, timezone
    start = datetime.fromtimestamp(ts.min() / 1e6 if ts.min() > 1e15 else ts.min() / 1e3, tz=timezone.utc)
    end = datetime.fromtimestamp(ts.max() / 1e6 if ts.max() > 1e15 else ts.max() / 1e3, tz=timezone.utc)
    
    return AssetData4h(
        asset=asset,
        df=df_4h,
        n_bars=n_after,
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
    )


def load_all_4h() -> dict[str, AssetData4h]:
    """Load 4h data for all 6 assets."""
    results = {}
    for asset in ASSETS:
        try:
            results[asset] = load_asset_data_4h(asset)
            d = results[asset]
            log.info(f"✅ {asset}: {d.n_bars} bars ({d.start_date} → {d.end_date})")
        except Exception as e:
            log.error(f"❌ {asset}: {e}")
    return results


# ── Helpers ──

def _ema(data: np.ndarray, period: int) -> np.ndarray:
    result = np.full_like(data, np.nan, dtype=float)
    if len(data) < period:
        return result
    sma = np.mean(data[:period])
    result[period - 1] = sma
    k = 2 / (period + 1)
    for i in range(period, len(data)):
        result[i] = data[i] * k + result[i - 1] * (1 - k)
    return result


def _sma(data: np.ndarray, period: int) -> np.ndarray:
    result = np.full_like(data, np.nan, dtype=float)
    if len(data) < period:
        return result
    # Use rolling mean calculation (correct for all lengths)
    for i in range(period - 1, len(data)):
        result[i] = np.mean(data[i - period + 1:i + 1])
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
    data = load_all_4h()
    for asset, d in data.items():
        print(f"\n{asset}: {d.n_bars} bars, {d.start_date} → {d.end_date}")
        print(d.df.head(3))