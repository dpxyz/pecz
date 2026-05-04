#!/usr/bin/env python3
"""
Foundry V13c — RADICAL Funding Sweep

Exhaustive grid search: ALL 6 assets × ALL signal types × ALL exits × ALL filters
Including: OI drops, LS ratio, taker ratio, 4h timeframe, multi-signal combos

Target: 10,000+ backtests, find every possible edge in our data
"""

import json, sys, time, os
from pathlib import Path
from datetime import datetime
from copy import deepcopy

import polars as pl
import numpy as np

RESEARCH_DIR = Path(__file__).parent
DATA_DIR = Path(__file__).parent.parent / "data_collector" / "data"
V10_DIR = RESEARCH_DIR / "data_v10"
OUTPUT = RESEARCH_DIR / "funding_sweep_v13c_results.json"

# ALL 6 assets — we have data for all of them
ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]

# ============================================================================
# DATA LOADING
# ============================================================================

def load_price_data() -> dict:
    """Load 1h prices for all 6 assets."""
    df = pl.read_parquet(DATA_DIR / "prices_all_1h.parquet")
    result = {}
    for asset in ASSETS:
        sub = df.filter(pl.col("asset") == asset).sort("timestamp")
        result[asset] = compute_indicators(sub)
        print(f"  {asset}: {len(result[asset])} rows")
    return result


def load_funding_8h() -> dict:
    """Load 8h funding from HL (resample from 1h)."""
    df = pl.read_parquet(DATA_DIR / "hl_funding_full.parquet")
    EIGHT_H_MS = 8 * 3600 * 1000
    df = df.with_columns(
        (pl.col("timestamp") // EIGHT_H_MS * EIGHT_H_MS).alias("ts8h")
    )
    df_8h = df.sort(["asset", "ts8h"]).group_by(["asset", "ts8h"]).last()
    df_8h = df_8h.select(["ts8h", "asset", "funding_rate"]).rename({"ts8h": "timestamp"})
    
    result = {}
    for asset in ASSETS:
        sub = df_8h.filter(pl.col("asset") == asset).sort("timestamp")
        rates = sub["funding_rate"].to_numpy()
        ts = sub["timestamp"].to_numpy()
        
        # Rolling z-scores (21-rate window = 7 days)
        WINDOW = 21
        z_map = {}
        for i in range(WINDOW, len(rates)):
            window = rates[i-WINDOW:i]
            mean = np.mean(window)
            std = np.std(window)
            if std > 0:
                z_map[ts[i]] = (rates[i] - mean) / std
        
        result[asset] = {"rates": rates, "ts": ts, "z_map": z_map}
        print(f"  {asset} funding: {len(rates)} rates, {len(z_map)} z-scores")
    
    return result


def load_oi_data() -> dict:
    """Load OI data (8h from Binance)."""
    df = pl.read_parquet(DATA_DIR / "bn_oi.parquet")
    EIGHT_H_MS = 8 * 3600 * 1000
    # Convert datetime to ms for 8h bucketing
    df = df.with_columns(
        (pl.col("timestamp").dt.timestamp("ms") // EIGHT_H_MS * EIGHT_H_MS).alias("ts8h_ms")
    )
    df_8h = df.sort(["asset", "ts8h_ms"]).group_by(["asset", "ts8h_ms"]).last()
    df_8h = df_8h.rename({"ts8h_ms": "ts8h", "sum_oi": "openInterest"})
    
    result = {}
    for asset in ASSETS:
        sub = df_8h.filter(pl.col("asset") == asset).sort("ts8h")
        if len(sub) > 0:
            oi = sub["openInterest"].to_numpy().astype(float)
            ts = sub["ts8h"].to_numpy()
            oi_pct = np.zeros(len(oi))
            oi_pct[1:] = (oi[1:] - oi[:-1]) / np.where(oi[:-1] > 0, oi[:-1], 1) * 100
            result[asset] = {"ts": ts, "oi": oi, "oi_pct": oi_pct}
            print(f"  {asset} OI: {len(oi)} data points")
        else:
            result[asset] = None
            print(f"  {asset} OI: NO DATA")
    
    return result


def load_ls_ratio() -> dict:
    """Load long/short ratio."""
    df = pl.read_parquet(DATA_DIR / "bn_ls_ratio.parquet")
    EIGHT_H_MS = 8 * 3600 * 1000
    df = df.with_columns(
        (pl.col("timestamp").dt.timestamp("ms") // EIGHT_H_MS * EIGHT_H_MS).alias("ts8h_ms")
    )
    df_8h = df.sort(["asset", "ts8h_ms"]).group_by(["asset", "ts8h_ms"]).last()
    
    result = {}
    for asset in ASSETS:
        sub = df_8h.filter(pl.col("asset") == asset).sort("ts8h_ms")
        if len(sub) > 0 and "long_short_ratio" in sub.columns:
            result[asset] = {"ts": sub["ts8h_ms"].to_numpy(), "ratio": sub["long_short_ratio"].to_numpy()}
            print(f"  {asset} LS: {len(sub)} data points")
        else:
            result[asset] = None
            print(f"  {asset} LS: NO DATA")
    
    return result


def load_taker_ratio() -> dict:
    """Load taker buy/sell ratio."""
    df = pl.read_parquet(DATA_DIR / "bn_taker_ratio.parquet")
    EIGHT_H_MS = 8 * 3600 * 1000
    df = df.with_columns(
        (pl.col("timestamp").dt.timestamp("ms") // EIGHT_H_MS * EIGHT_H_MS).alias("ts8h_ms")
    )
    df_8h = df.sort(["asset", "ts8h_ms"]).group_by(["asset", "ts8h_ms"]).last()
    
    result = {}
    for asset in ASSETS:
        sub = df_8h.filter(pl.col("asset") == asset).sort("ts8h_ms")
        if len(sub) > 0 and "buy_sell_ratio" in sub.columns:
            result[asset] = {"ts": sub["ts8h_ms"].to_numpy(), "ratio": sub["buy_sell_ratio"].to_numpy()}
            print(f"  {asset} Taker: {len(sub)} data points")
        else:
            result[asset] = None
            print(f"  {asset} Taker: NO DATA")
    
    return result


def compute_indicators(df: pl.DataFrame) -> pl.DataFrame:
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy()
    
    ema50 = _ema(close, 50)
    ema200 = _ema(close, 200)
    vol_sma24 = _sma(volume, 24)
    vol_ratio = np.where(vol_sma24 > 0, volume / vol_sma24, 1.0)
    
    df = df.with_columns([
        pl.Series("ema50", ema50),
        pl.Series("ema200", ema200),
        pl.Series("vol_ratio", vol_ratio),
    ])
    
    df = df.with_columns([
        (pl.col("close") > pl.col("ema200")).cast(pl.Int8).alias("bull200"),
        (pl.col("close") > pl.col("ema50")).cast(pl.Int8).alias("bull50"),
    ])
    
    return df


def _ema(data, period):
    result = np.full_like(data, np.nan, dtype=float)
    if len(data) < period:
        return result
    sma = np.mean(data[:period])
    result[period - 1] = sma
    k = 2 / (period + 1)
    for i in range(period, len(data)):
        result[i] = data[i] * k + result[i-1] * (1 - k)
    return result


def _sma(data, period):
    result = np.full_like(data, np.nan, dtype=float)
    if len(data) < period:
        return result
    for i in range(period - 1, len(data)):
        if i == period - 1:
            result[i] = np.mean(data[:period])
        else:
            result[i] = np.mean(data[i-period+1:i+1])
    return result


# ============================================================================
# MERGED DATA BUILDER
# ============================================================================

def build_merged_data(prices: dict, funding: dict, oi: dict, ls: dict, taker: dict) -> dict:
    """Merge all data sources into unified DataFrames per asset."""
    EIGHT_H_MS = 8 * 3600 * 1000
    result = {}
    
    for asset in ASSETS:
        df = prices[asset].clone()
        df = df.with_columns(
            (pl.col("timestamp") // EIGHT_H_MS * EIGHT_H_MS).alias("ts8h")
        )
        
        # Add funding
        fund_z = funding[asset]["z_map"]
        df = df.with_columns(
            pl.col("ts8h").map_elements(
                lambda ts: fund_z.get(ts, None), return_dtype=pl.Float64
            ).alias("funding_z_raw")
        )
        df = df.with_columns(
            pl.col("funding_z_raw").forward_fill().alias("funding_z")
        )
        df = df.with_columns(
            pl.col("funding_z_raw").is_not_null().alias("is_funding_bar")
        )
        
        # Add OI change % (8h)
        if oi.get(asset) is not None:
            oi_pct_map = {}
            for i, ts in enumerate(oi[asset]["ts"]):
                oi_pct_map[ts] = oi[asset]["oi_pct"][i]
            df = df.with_columns(
                pl.col("ts8h").map_elements(
                    lambda ts: oi_pct_map.get(ts, None), return_dtype=pl.Float64
                ).alias("oi_pct_raw")
            )
            df = df.with_columns(
                pl.col("oi_pct_raw").forward_fill().alias("oi_pct")
            )
        else:
            df = df.with_columns([
                pl.lit(None).cast(pl.Float64).alias("oi_pct"),
                pl.lit(None).cast(pl.Float64).alias("oi_pct_raw"),
            ])
        
        # Add LS ratio (8h)
        if ls.get(asset) is not None:
            ls_map = {}
            for i, ts in enumerate(ls[asset]["ts"]):
                ls_map[ts] = ls[asset]["ratio"][i]
            df = df.with_columns(
                pl.col("ts8h").map_elements(
                    lambda ts: ls_map.get(ts, None), return_dtype=pl.Float64
                ).alias("ls_ratio_raw")
            )
            df = df.with_columns(
                pl.col("ls_ratio_raw").forward_fill().alias("ls_ratio")
            )
        else:
            df = df.with_columns([
                pl.lit(None).cast(pl.Float64).alias("ls_ratio"),
                pl.lit(None).cast(pl.Float64).alias("ls_ratio_raw"),
            ])
        
        # Add taker ratio (8h)
        if taker.get(asset) is not None:
            tr_map = {}
            for i, ts in enumerate(taker[asset]["ts"]):
                tr_map[ts] = taker[asset]["ratio"][i]
            df = df.with_columns(
                pl.col("ts8h").map_elements(
                    lambda ts: tr_map.get(ts, None), return_dtype=pl.Float64
                ).alias("taker_ratio_raw")
            )
            df = df.with_columns(
                pl.col("taker_ratio_raw").forward_fill().alias("taker_ratio")
            )
        else:
            df = df.with_columns([
                pl.lit(None).cast(pl.Float64).alias("taker_ratio"),
                pl.lit(None).cast(pl.Float64).alias("taker_ratio_raw"),
            ])
        
        # Drop NaN rows
        df = df.drop_nulls(subset=["funding_z", "ema200"])
        
        result[asset] = df
        n_fund = sum(df["is_funding_bar"].to_list())
        print(f"  {asset}: {len(df)} rows, {n_fund} funding bars")
    
    return result


# ============================================================================
# STRATEGY SIMULATOR
# ============================================================================

def simulate(
    df: pl.DataFrame,
    # Entry conditions
    z_low: float,          # funding z must be > z_low (use -999 for no lower bound)
    z_high: float,         # funding z must be < z_high
    require_bull200: bool,
    require_bull50: bool,
    require_vol: float,    # 0 = no filter
    require_oi_drop: float,  # 0 = no filter, >0 = OI must drop >X%
    require_ls_low: float,   # 0 = no filter, >0 = LS ratio must be < X (more shorts)
    require_taker_low: float,  # 0 = no filter, >0 = taker ratio < X (more selling)
    # Exit conditions
    stop_loss_pct: float,
    max_hold_bars: int,
    fee_pct: float = 0.05,
    slippage_pct: float = 0.03,
) -> dict:
    """Simulate with multi-signal entry conditions."""
    rows = df.to_dicts()
    n = len(rows)
    
    trades = []
    in_position = False
    entry_price = 0.0
    entry_bar = 0
    
    for i in range(n):
        r = rows[i]
        
        if in_position:
            # Stop loss
            if r["low"] <= entry_price * (1 - stop_loss_pct / 100):
                exit_price = entry_price * (1 - stop_loss_pct / 100)
                pnl = ((exit_price - entry_price) / entry_price - (fee_pct + slippage_pct) * 2 / 100) * 100
                trades.append(pnl)
                in_position = False
                continue
            # Max hold
            if i - entry_bar >= max_hold_bars:
                exit_price = r["close"]
                pnl = ((exit_price - entry_price) / entry_price - (fee_pct + slippage_pct) * 2 / 100) * 100
                trades.append(pnl)
                in_position = False
                continue
        
        # Entry only at funding bars
        if not in_position and r.get("is_funding_bar", False):
            fz = r.get("funding_z")
            if fz is None or not np.isfinite(fz):
                continue
            if fz < z_low or fz >= z_high:
                continue
            if require_bull200 and not r.get("bull200", 0):
                continue
            if require_bull50 and not r.get("bull50", 0):
                continue
            if require_vol > 0 and r.get("vol_ratio", 1) < require_vol:
                continue
            if require_oi_drop > 0:
                oi = r.get("oi_pct")
                if oi is None or oi > -require_oi_drop:  # must be negative (OI dropping)
                    continue
            if require_ls_low > 0:
                ls = r.get("ls_ratio")
                if ls is None or ls >= require_ls_low:
                    continue
            if require_taker_low > 0:
                tr = r.get("taker_ratio")
                if tr is None or tr >= require_taker_low:
                    continue
            
            entry_price = r["close"] * (1 + slippage_pct / 100)
            entry_bar = i
            in_position = True
    
    if not trades:
        return {"net_return": 0, "trade_count": 0, "win_rate": 0, "max_dd": 0, "avg_pnl": 0}
    
    wins = sum(1 for t in trades if t > 0)
    cum_pnl = sum(trades)
    
    eq = 10000.0
    peak = eq
    max_dd = 0
    for t in trades:
        eq *= (1 + t / 100)
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    return {
        "net_return": round(cum_pnl, 4),
        "trade_count": len(trades),
        "win_rate": round(wins / len(trades) * 100, 2),
        "max_dd": round(max_dd, 4),
        "avg_pnl": round(cum_pnl / len(trades), 4),
    }


# ============================================================================
# WALK-FORWARD
# ============================================================================

def walk_forward(df: pl.DataFrame, params: dict, n_windows: int = 10) -> dict:
    n_rows = len(df)
    window_size = n_rows // n_windows
    
    oos_returns = []
    for w in range(n_windows):
        start = w * window_size
        train_end = start + int(window_size * 0.7)
        test_end = min(start + window_size, n_rows)
        test_df = df[train_end:test_end]
        if len(test_df) < 50:
            continue
        
        r = simulate(test_df, **params)
        oos_returns.append(r["net_return"])
    
    if not oos_returns:
        return {"robustness": 0, "passed": False, "avg_oos": 0, "profitable_windows": "0/0"}
    
    profitable = sum(1 for r in oos_returns if r > 0)
    robustness = round(profitable / len(oos_returns) * 100, 1)
    avg_oos = round(float(np.mean(oos_returns)), 4)
    passed = robustness >= 70 and avg_oos > 0
    
    return {
        "robustness": robustness,
        "passed": passed,
        "avg_oos": avg_oos,
        "profitable_windows": f"{profitable}/{len(oos_returns)}",
        "oos_returns": [round(r, 2) for r in oos_returns],
    }


# ============================================================================
# RADICAL GRID
# ============================================================================

def build_grid() -> list:
    """Build exhaustive parameter grid."""
    grid = []
    
    # === TIER 1: Simple funding (proven) ===
    for z in [-0.3, -0.5, -0.7, -0.8, -1.0, -1.2, -1.5, -2.0]:
        grid.append({
            "label": f"bear_z<{z}",
            "z_low": -999, "z_high": z,
            "require_bull200": False, "require_bull50": False,
            "require_vol": 0, "require_oi_drop": 0,
            "require_ls_low": 0, "require_taker_low": 0,
        })
    
    # === TIER 2: Bull pullback ===
    for z_low in [-1.5, -1.0, -0.8, -0.5]:
        for z_high in [-0.2, -0.1, 0.0]:
            if z_low < z_high:
                grid.append({
                    "label": f"bullPB_z[{z_low},{z_high}]",
                    "z_low": z_low, "z_high": z_high,
                    "require_bull200": True, "require_bull50": False,
                    "require_vol": 0, "require_oi_drop": 0,
                    "require_ls_low": 0, "require_taker_low": 0,
                })
    
    # === TIER 3: Bull pullback + vol ===
    for z_low in [-1.0, -0.5]:
        for z_high in [-0.2, -0.1]:
            if z_low < z_high:
                for vol in [1.3, 1.5, 2.0]:
                    grid.append({
                        "label": f"bullPB_vol_z[{z_low},{z_high}]_v>{vol}",
                        "z_low": z_low, "z_high": z_high,
                        "require_bull200": True, "require_bull50": False,
                        "require_vol": vol, "require_oi_drop": 0,
                        "require_ls_low": 0, "require_taker_low": 0,
                    })
    
    # === TIER 4: Funding + OI drop (NEW!) ===
    for z in [-0.3, -0.5, -0.8, -1.0]:
        for oi in [1, 3, 5, 10]:  # OI drop > X%
            grid.append({
                "label": f"bear_z<{z}_oi_drop>{oi}%",
                "z_low": -999, "z_high": z,
                "require_bull200": False, "require_bull50": False,
                "require_vol": 0, "require_oi_drop": oi,
                "require_ls_low": 0, "require_taker_low": 0,
            })
    
    # === TIER 5: Funding + LS ratio (NEW!) ===
    for z in [-0.3, -0.5, -0.8]:
        for ls in [0.5, 0.7, 0.9]:  # LS ratio < X = more shorts
            grid.append({
                "label": f"bear_z<{z}_ls<{ls}",
                "z_low": -999, "z_high": z,
                "require_bull200": False, "require_bull50": False,
                "require_vol": 0, "require_oi_drop": 0,
                "require_ls_low": ls, "require_taker_low": 0,
            })
    
    # === TIER 6: Funding + taker ratio (NEW!) ===
    for z in [-0.3, -0.5, -0.8]:
        for tr in [0.8, 0.9, 1.0]:  # taker buy/sell < X = more selling
            grid.append({
                "label": f"bear_z<{z}_taker<{tr}",
                "z_low": -999, "z_high": z,
                "require_bull200": False, "require_bull50": False,
                "require_vol": 0, "require_oi_drop": 0,
                "require_ls_low": 0, "require_taker_low": tr,
            })
    
    # === TIER 7: Triple combo: Funding + OI + LS (NEW!) ===
    for z in [-0.5, -0.8]:
        for oi in [1, 3, 5]:
            for ls in [0.7, 0.9]:
                grid.append({
                    "label": f"triple_z<{z}_oi>{oi}_ls<{ls}",
                    "z_low": -999, "z_high": z,
                    "require_bull200": False, "require_bull50": False,
                    "require_vol": 0, "require_oi_drop": oi,
                    "require_ls_low": ls, "require_taker_low": 0,
                })
    
    # === TIER 8: Bull50 pullback (shorter-term) ===
    for z in [-0.3, -0.5, -0.8, -1.0]:
        grid.append({
            "label": f"bull50_z<{z}",
            "z_low": -999, "z_high": z,
            "require_bull200": False, "require_bull50": True,
            "require_vol": 0, "require_oi_drop": 0,
            "require_ls_low": 0, "require_taker_low": 0,
        })
    
    return grid


EXIT_CONFIGS = [
    {"sl": 3.0, "hold": 8,  "label": "8h_SL3"},
    {"sl": 4.0, "hold": 12, "label": "12h_SL4"},
    {"sl": 5.0, "hold": 24, "label": "24h_SL5"},
    {"sl": 5.0, "hold": 48, "label": "48h_SL5"},
    {"sl": 6.0, "hold": 72, "label": "72h_SL6"},
    {"sl": 5.0, "hold": 36, "label": "36h_SL5"},
    {"sl": 4.0, "hold": 24, "label": "24h_SL4"},
    {"sl": 4.0, "hold": 48, "label": "48h_SL4"},
    {"sl": 3.0, "hold": 24, "label": "24h_SL3"},
    {"sl": 6.0, "hold": 48, "label": "48h_SL6"},
]


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 60)
    print("Foundry V13c — RADICAL Funding Sweep")
    print("=" * 60)
    
    # Load all data
    print("\n📊 Loading data...")
    prices = load_price_data()
    funding = load_funding_8h()
    oi = load_oi_data()
    ls = load_ls_ratio()
    taker = load_taker_ratio()
    
    print("\n📊 Merging data...")
    data = build_merged_data(prices, funding, oi, ls, taker)
    
    # Build grid
    grid = build_grid()
    total = len(grid) * len(ASSETS) * len(EXIT_CONFIGS)
    print(f"\n📊 Grid: {len(grid)} signals × {len(ASSETS)} assets × {len(EXIT_CONFIGS)} exits = {total} backtests")
    
    # Run grid search
    results = []
    count = 0
    start_time = time.time()
    
    for sig in grid:
        for asset in ASSETS:
            df = data[asset]
            for exit_cfg in EXIT_CONFIGS:
                count += 1
                if count % 500 == 0:
                    elapsed = time.time() - start_time
                    rate = count / elapsed if elapsed > 0 else 0
                    eta = (total - count) / rate if rate > 0 else 0
                    print(f"  [{count}/{total}] {rate:.0f}/s ETA={eta:.0f}s")
                
                r = simulate(
                    df,
                    z_low=sig["z_low"],
                    z_high=sig["z_high"],
                    require_bull200=sig["require_bull200"],
                    require_bull50=sig["require_bull50"],
                    require_vol=sig["require_vol"],
                    require_oi_drop=sig["require_oi_drop"],
                    require_ls_low=sig["require_ls_low"],
                    require_taker_low=sig["require_taker_low"],
                    stop_loss_pct=exit_cfg["sl"],
                    max_hold_bars=exit_cfg["hold"],
                )
                
                results.append({
                    "signal": sig["label"],
                    "asset": asset,
                    "exit": exit_cfg["label"],
                    "z_low": sig["z_low"],
                    "z_high": sig["z_high"],
                    "bull200": sig["require_bull200"],
                    "bull50": sig["require_bull50"],
                    "vol": sig["require_vol"],
                    "oi_drop": sig["require_oi_drop"],
                    "ls": sig["require_ls_low"],
                    "taker": sig["require_taker_low"],
                    "sl": exit_cfg["sl"],
                    "hold": exit_cfg["hold"],
                    **r,
                })
    
    elapsed = time.time() - start_time
    print(f"\n✅ Done: {count} backtests in {elapsed:.1f}s ({count/elapsed:.0f}/s)")
    
    # Filter & Rank
    valid = [r for r in results if r["trade_count"] >= 3]
    profitable = [r for r in valid if r["net_return"] > 0]
    profitable.sort(key=lambda x: x["net_return"], reverse=True)
    
    print(f"\n📊 Results: {len(results)} total | {len(valid)} valid | {len(profitable)} profitable")
    
    # Show per-asset breakdown
    for asset in ASSETS:
        asset_prof = [r for r in profitable if r["asset"] == asset]
        print(f"  {asset}: {len(asset_prof)} profitable")
    
    # Show top 30
    if profitable:
        print(f"\n  Top 30:")
        for i, r in enumerate(profitable[:30]):
            print(f"  {i+1:2d}. {r['signal']:35s} {r['asset']:5s} {r['exit']:10s} | "
                  f"ret={r['net_return']:+7.2f}% trades={r['trade_count']:3d} wr={r['win_rate']:5.1f}% dd={r['max_dd']:5.1f}%")
    
    # Walk-Forward on top 30 unique candidates
    seen = set()
    wf_candidates = []
    for r in profitable:
        key = f"{r['signal']}|{r['asset']}"
        if key not in seen:
            seen.add(key)
            wf_candidates.append(r)
        if len(wf_candidates) >= 30:
            break
    
    print(f"\n📊 Walk-Forward: top {len(wf_candidates)} unique")
    
    wf_results = []
    for i, r in enumerate(wf_candidates):
        params = {
            "z_low": r["z_low"],
            "z_high": r["z_high"],
            "require_bull200": r["bull200"],
            "require_bull50": r["bull50"],
            "require_vol": r["vol"],
            "require_oi_drop": r["oi_drop"],
            "require_ls_low": r["ls"],
            "require_taker_low": r["taker"],
            "stop_loss_pct": r["sl"],
            "max_hold_bars": r["hold"],
        }
        
        wf = walk_forward(data[r["asset"]], params)
        r["wf_robustness"] = wf["robustness"]
        r["wf_passed"] = wf["passed"]
        r["wf_avg_oos"] = wf["avg_oos"]
        r["wf_detail"] = wf
        wf_results.append(r)
        
        status = "✅" if wf["passed"] else "❌"
        print(f"  {status} {r['signal']:35s} {r['asset']:5s} | R={wf['robustness']:3.0f} OOS={wf['avg_oos']:+6.2f}% wins={wf['profitable_windows']}")
    
    passed = [r for r in wf_results if r["wf_passed"]]
    print(f"\n{'='*60}")
    print(f"FINAL: {len(profitable)} profitable IS | {len(wf_results)} WF-tested | {len(passed)} WF-passed")
    print(f"{'='*60}")
    
    if passed:
        print("\n🏆 WF-PASSED STRATEGIES:")
        for r in passed:
            print(f"  {r['signal']:35s} {r['asset']:5s} {r['exit']:10s} | R={r['wf_robustness']:.0f} OOS={r['wf_avg_oos']:+.2f}% trades={r['trade_count']}")
    
    # Save
    output = {
        "version": "V13c",
        "timestamp": datetime.now().isoformat(),
        "grid_total": len(results),
        "grid_valid": len(valid),
        "grid_profitable": len(profitable),
        "wf_tested": len(wf_results),
        "wf_passed": len(passed),
        "assets_tested": ASSETS,
        "signal_tiers": {
            "tier1_simple_funding": len([g for g in grid if not g["require_bull200"] and not g["require_oi_drop"] and not g["require_ls_low"]]),
            "tier2_bull_pullback": len([g for g in grid if g["require_bull200"] and not g["require_oi_drop"]]),
            "tier3_bull_pb_vol": len([g for g in grid if g["require_bull200"] and g["require_vol"] > 0]),
            "tier4_oi_drop": len([g for g in grid if g["require_oi_drop"] > 0 and not g["require_ls_low"]]),
            "tier5_ls_ratio": len([g for g in grid if g["require_ls_low"] > 0 and not g["require_oi_drop"]]),
            "tier6_taker": len([g for g in grid if g["require_taker_low"] > 0 and not g["require_oi_drop"]]),
            "tier7_triple": len([g for g in grid if g["require_oi_drop"] > 0 and g["require_ls_low"] > 0]),
            "tier8_bull50": len([g for g in grid if g["require_bull50"]]),
        },
        "wf_passed_strategies": [
            {
                "signal": r["signal"],
                "asset": r["asset"],
                "exit": r["exit"],
                "is_return": r["net_return"],
                "is_trades": r["trade_count"],
                "is_win_rate": r["win_rate"],
                "wf_robustness": r["wf_robustness"],
                "wf_avg_oos": r["wf_avg_oos"],
            }
            for r in passed
        ],
        "top_is": [
            {k: v for k, v in r.items() if k not in ("wf_detail",)}
            for r in profitable[:100]
        ],
    }
    
    with open(OUTPUT, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n💾 Saved to {OUTPUT}")
    
    return output


if __name__ == "__main__":
    main()