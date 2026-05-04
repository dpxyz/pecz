#!/usr/bin/env python3
"""
Foundry V13b — 8h Funding Parameter Sweep

Entry: only at 8h funding rate timestamps (00:00, 08:00, 16:00 UTC)
Exit: managed hourly (trailing stop, SL, max hold)
Data: HL Funding Full (1h → resample to 8h) + Prices All 1h

Key insight from V13: 1h funding fires too often → overtrading.
8h funding = real exchange funding intervals = higher quality signals.
"""

import json, sys, time, os
from pathlib import Path
from datetime import datetime, timezone
from copy import deepcopy

import polars as pl
import numpy as np

RESEARCH_DIR = Path(__file__).parent
DATA_DIR = Path(__file__).parent.parent / "data_collector" / "data"
OUTPUT = RESEARCH_DIR / "funding_sweep_v13b_results.json"

ASSETS = ["BTC", "ETH", "SOL"]

# ============================================================================
# DATA PREPARATION
# ============================================================================

def prepare_data() -> dict:
    """Load and merge 8h funding + 1h prices per asset."""
    
    # Load HL Funding (1h resolution, 2.5 years)
    df_fund = pl.read_parquet(DATA_DIR / "hl_funding_full.parquet")
    
    # Resample to 8h: keep only 00:00, 08:00, 16:00 UTC
    EIGHT_H_MS = 8 * 3600 * 1000
    df_fund = df_fund.with_columns(
        (pl.col("timestamp") // EIGHT_H_MS * EIGHT_H_MS).alias("ts8h")
    )
    # Keep the LAST funding rate in each 8h window (closest to settlement)
    df_fund_8h = df_fund.sort(["asset", "ts8h"]).group_by(["asset", "ts8h"]).last()
    df_fund_8h = df_fund_8h.select(["ts8h", "asset", "funding_rate"]).rename({"ts8h": "timestamp"})
    
    # Load prices 1h
    df_price = pl.read_parquet(DATA_DIR / "prices_all_1h.parquet")
    
    result = {}
    for asset in ASSETS:
        # Filter asset data
        fund_a = df_fund_8h.filter(pl.col("asset") == asset).sort("timestamp")
        price_a = df_price.filter(pl.col("asset") == asset).sort("timestamp")
        
        # Compute price indicators on 1h data
        price_a = compute_indicators(price_a)
        
        # Join: funding on 8h boundaries, forward-fill between
        # First join funding to matching 8h price bars
        price_a = price_a.with_columns(
            (pl.col("timestamp") // EIGHT_H_MS * EIGHT_H_MS).alias("ts8h")
        )
        joined = price_a.join(
            fund_a.select(["timestamp", "funding_rate"]).rename({"timestamp": "ts8h_join"}),
            left_on="ts8h",
            right_on="ts8h_join",
            how="left"
        )
        
        # Forward-fill funding_rate within each 8h window
        joined = joined.sort("timestamp").with_columns(
            pl.col("funding_rate").forward_fill().alias("funding_rate_ff")
        )
        
        # Compute funding_z from 8h rates (rolling 7-day window = 21 rates)
        # We only compute z-score at 8h boundaries where we have actual rates
        fund_rates = fund_a["funding_rate"].to_numpy()
        fund_ts = fund_a["timestamp"].to_numpy()
        
        # Compute rolling z-scores for funding
        WINDOW = 21  # 7 days × 3 rates/day
        fund_z_map = {}
        for i in range(WINDOW, len(fund_rates)):
            window = fund_rates[i-WINDOW:i]
            mean = np.mean(window)
            std = np.std(window)
            if std > 0:
                z = (fund_rates[i] - mean) / std
            else:
                z = 0.0
            fund_z_map[fund_ts[i]] = z
        
        # Map funding_z to 8h timestamps in the joined data
        # At each 8h boundary, set funding_z; between boundaries, carry forward
        joined = joined.with_columns(
            pl.col("ts8h").map_elements(
                lambda ts: fund_z_map.get(ts, None),
                return_dtype=pl.Float64
            ).alias("funding_z_raw")
        )
        joined = joined.with_columns(
            pl.col("funding_z_raw").forward_fill().alias("funding_z")
        )
        
        # Mark 8h bars (where funding actually updates) — ENTRY only here
        joined = joined.with_columns(
            pl.col("funding_z_raw").is_not_null().alias("is_funding_bar")
        )
        
        # Drop NaN rows at start
        joined = joined.drop_nulls(subset=["funding_z", "ema200", "ema50"])
        
        result[asset] = joined
        print(f"  {asset}: {len(result[asset])} rows, {sum(result[asset]['is_funding_bar'].to_list())} funding bars")
    
    return result


def compute_indicators(df: pl.DataFrame) -> pl.DataFrame:
    """Compute EMA50, EMA200, vol_ratio on 1h price data."""
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy()
    
    # EMAs
    ema50 = _ema(close, 50)
    ema200 = _ema(close, 200)
    
    # Vol ratio (current volume / 24h average)
    vol_sma24 = _sma(volume, 24)
    vol_ratio = np.where(vol_sma24 > 0, volume / vol_sma24, 1.0)
    
    df = df.with_columns([
        pl.Series("ema50", ema50),
        pl.Series("ema200", ema200),
        pl.Series("vol_ratio", vol_ratio),
    ])
    
    # bull200: close > ema200
    df = df.with_columns(
        (pl.col("close") > pl.col("ema200")).cast(pl.Int8).alias("bull200")
    )
    # bull50: close > ema50
    df = df.with_columns(
        (pl.col("close") > pl.col("ema50")).cast(pl.Int8).alias("bull50")
    )
    
    return df


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    result = np.full_like(data, np.nan, dtype=float)
    if len(data) < period:
        return result
    sma = np.mean(data[:period])
    result[period - 1] = sma
    k = 2 / (period + 1)
    for i in range(period, len(data)):
        result[i] = data[i] * k + result[i-1] * (1 - k)
    return result


def _sma(data: np.ndarray, period: int) -> np.ndarray:
    result = np.full_like(data, np.nan, dtype=float)
    if len(data) < period:
        return result
    cumsum = np.cumsum(data)
    for i in range(period - 1, len(data)):
        if i == period - 1:
            result[i] = cumsum[i] / period
        else:
            result[i] = (cumsum[i] - cumsum[i - period]) / period
    return result


# ============================================================================
# SIMPLIFIED BACKTESTER — 8h Entry, 1h Exit Management
# ============================================================================

def simulate_strategy(
    df: pl.DataFrame,
    entry_z_low: float,
    entry_z_high: float,
    require_bull200: bool,
    require_bull50: bool,
    require_vol: float,  # 0 = no vol filter
    stop_loss_pct: float,
    trailing_stop_pct: float,
    max_hold_bars: int,
    fee_pct: float = 0.05,  # 0.05% per side (maker)
    slippage_pct: float = 0.03,  # 0.03% per side
) -> dict:
    """
    Simulate strategy with 8h entry signals and 1h exit management.
    Entry only at funding bars (8h boundaries).
    """
    rows = df.to_dicts()
    n = len(rows)
    
    trades = []
    equity = 10000.0
    in_position = False
    entry_price = 0.0
    entry_bar = 0
    highest_since_entry = 0.0
    trade_pnl = 0.0
    
    for i in range(n):
        r = rows[i]
        
        # --- EXIT MANAGEMENT (every bar while in position) ---
        if in_position:
            # Stop loss
            if r["low"] <= entry_price * (1 - stop_loss_pct / 100):
                exit_price = entry_price * (1 - stop_loss_pct / 100)
                gross_pnl = (exit_price - entry_price) / entry_price
                net_pnl = gross_pnl - (fee_pct + slippage_pct) * 2 / 100
                trades.append(net_pnl * 100)
                equity *= (1 + net_pnl)
                in_position = False
                continue
            
            # Trailing stop
            if r["high"] > highest_since_entry:
                highest_since_entry = r["high"]
            if r["close"] <= highest_since_entry * (1 - trailing_stop_pct / 100):
                exit_price = r["close"]
                gross_pnl = (exit_price - entry_price) / entry_price
                net_pnl = gross_pnl - (fee_pct + slippage_pct) * 2 / 100
                trades.append(net_pnl * 100)
                equity *= (1 + net_pnl)
                in_position = False
                continue
            
            # Max hold
            if i - entry_bar >= max_hold_bars:
                exit_price = r["close"]
                gross_pnl = (exit_price - entry_price) / entry_price
                net_pnl = gross_pnl - (fee_pct + slippage_pct) * 2 / 100
                trades.append(net_pnl * 100)
                equity *= (1 + net_pnl)
                in_position = False
                continue
        
        # --- ENTRY (only at 8h funding bars) ---
        if not in_position and r.get("is_funding_bar", False):
            fz = r.get("funding_z")
            if fz is None or not np.isfinite(fz):
                continue
            
            # Check entry conditions
            entry_ok = True
            
            # Funding z range
            if fz < entry_z_low or fz >= entry_z_high:
                entry_ok = False
            
            # Bull200 filter
            if require_bull200 and not r.get("bull200", 0):
                entry_ok = False
            
            # Bull50 filter
            if require_bull50 and not r.get("bull50", 0):
                entry_ok = False
            
            # Volume filter
            if require_vol > 0 and r.get("vol_ratio", 1) < require_vol:
                entry_ok = False
            
            if entry_ok:
                entry_price = r["close"] * (1 + slippage_pct / 100)
                entry_bar = i
                highest_since_entry = r["high"]
                in_position = True
    
    # Compute metrics
    if not trades:
        return {"net_return": 0, "trade_count": 0, "win_rate": 0, "max_dd": 0, "avg_pnl": 0}
    
    wins = sum(1 for t in trades if t > 0)
    cum_pnl = sum(trades)
    
    # Max drawdown
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
# GRID DEFINITION
# ============================================================================

# Signal types: (z_low, z_high, require_bull200, require_bull50, require_vol, label)
SIGNAL_TYPES = []

# Type 1: Bear extreme (any regime, z very negative)
for z in [-0.5, -0.8, -1.0, -1.2, -1.5, -2.0, -2.5]:
    SIGNAL_TYPES.append((z, 0, False, False, 0, f"bear_z<{z}"))

# Type 2: Bull pullback (z mildly negative, in uptrend)
for z_low in [-1.5, -1.0, -0.8, -0.5, -0.3]:
    for z_high in [-0.2, -0.1, 0.0]:
        if z_low < z_high:
            SIGNAL_TYPES.append((z_low, z_high, True, False, 0, f"bullPB_z[{z_low},{z_high}]"))

# Type 3: Bull pullback + vol
for z_low in [-1.0, -0.5]:
    for z_high in [-0.2, -0.1]:
        if z_low < z_high:
            for vol in [1.3, 1.5, 2.0]:
                SIGNAL_TYPES.append((z_low, z_high, True, False, vol, f"bullPB_vol_z[{z_low},{z_high}]_v>{vol}"))

# Type 4: Bull50 pullback
for z in [-0.5, -0.8, -1.0, -1.5]:
    SIGNAL_TYPES.append((z, 0, False, True, 0, f"bull50_z<{z}"))

# Exit configs: (sl, trail, max_hold, label)
EXIT_CONFIGS = [
    (3.0, 2.0, 8, "8h_SL3_T2"),
    (4.0, 2.5, 24, "24h_SL4_T2.5"),
    (5.0, 3.0, 24, "24h_SL5_T3"),
    (5.0, 3.0, 48, "48h_SL5_T3"),
    (6.0, 4.0, 48, "48h_SL6_T4"),
    (6.0, 4.0, 72, "72h_SL6_T4"),
    (5.0, 0, 24, "24h_SL5_notrail"),   # no trailing, just hold + SL
    (5.0, 0, 48, "48h_SL5_notrail"),
]


# ============================================================================
# WALK-FORWARD VALIDATION
# ============================================================================

def walk_forward_test(df: pl.DataFrame, signal_type: tuple, exit_config: tuple,
                       n_windows: int = 10) -> dict:
    """Run walk-forward validation."""
    z_low, z_high, bull200, bull50, vol, label = signal_type
    sl, trail, max_hold, exit_label = exit_config
    
    n_rows = len(df)
    window_size = n_rows // n_windows
    
    oos_returns = []
    oos_trades = []
    
    for w in range(n_windows):
        start = w * window_size
        train_end = start + int(window_size * 0.7)
        test_end = min(start + window_size, n_rows)
        
        train_df = df[start:train_end]
        test_df = df[train_end:test_end]
        
        if len(test_df) < 50:
            continue
        
        # Train: just count trades (no parameter fitting for now)
        # Test: simulate
        result = simulate_strategy(
            test_df, z_low, z_high, bull200, bull50, vol,
            sl, trail if trail > 0 else 999, max_hold
        )
        
        oos_returns.append(result["net_return"])
        oos_trades.append(result["trade_count"])
    
    if not oos_returns:
        return {"robustness": 0, "passed": False, "avg_oos": 0, "profitable_windows": "0/0"}
    
    profitable = sum(1 for r in oos_returns if r > 0)
    total_windows = len(oos_returns)
    avg_oos = np.mean(oos_returns)
    avg_trades = np.mean(oos_trades)
    
    # Robustness: % of profitable OOS windows
    robustness = round(profitable / total_windows * 100, 1)
    passed = robustness >= 70 and avg_oos > 0
    
    return {
        "robustness": robustness,
        "passed": passed,
        "avg_oos": round(float(avg_oos), 4),
        "avg_trades": round(float(avg_trades), 1),
        "profitable_windows": f"{profitable}/{total_windows}",
        "oos_returns": [round(r, 2) for r in oos_returns],
    }


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 60)
    print("Foundry V13b — 8h Funding Sweep")
    print("=" * 60)
    
    print("\n📊 Loading data...")
    data = prepare_data()
    
    total = len(SIGNAL_TYPES) * len(ASSETS) * len(EXIT_CONFIGS)
    print(f"\n📊 Grid: {len(SIGNAL_TYPES)} signals × {len(ASSETS)} assets × {len(EXIT_CONFIGS)} exits = {total} backtests")
    
    results = []
    count = 0
    start_time = time.time()
    
    for sig in SIGNAL_TYPES:
        z_low, z_high, bull200, bull50, vol, label = sig
        for asset in ASSETS:
            df = data[asset]
            for exit_cfg in EXIT_CONFIGS:
                sl, trail, max_hold, exit_label = exit_cfg
                
                count += 1
                if count % 200 == 0:
                    elapsed = time.time() - start_time
                    rate = count / elapsed
                    eta = (total - count) / rate
                    print(f"  [{count}/{total}] {rate:.0f}/s ETA={eta:.0f}s")
                
                r = simulate_strategy(
                    df, z_low, z_high, bull200, bull50, vol,
                    sl, trail if trail > 0 else 999, max_hold
                )
                
                results.append({
                    "signal": label,
                    "asset": asset,
                    "exit": exit_label,
                    "z_low": z_low,
                    "z_high": z_high,
                    "bull200": bull200,
                    "bull50": bull50,
                    "vol": vol,
                    "sl": sl,
                    "trail": trail,
                    "max_hold": max_hold,
                    **r,
                })
    
    elapsed = time.time() - start_time
    print(f"\n✅ Done: {count} backtests in {elapsed:.1f}s")
    
    # Filter & Rank
    valid = [r for r in results if r["trade_count"] >= 3]
    profitable = [r for r in valid if r["net_return"] > 0]
    profitable.sort(key=lambda x: x["net_return"], reverse=True)
    
    print(f"\n📊 Results: {len(results)} total | {len(valid)} valid (≥3 trades) | {len(profitable)} profitable")
    
    if profitable:
        print(f"\n  Top 20:")
        for i, r in enumerate(profitable[:20]):
            print(f"  {i+1:2d}. {r['signal']:30s} {r['asset']:4s} {r['exit']:16s} | "
                  f"ret={r['net_return']:+7.2f}% trades={r['trade_count']:3d} wr={r['win_rate']:5.1f}% dd={r['max_dd']:5.1f}%")
    else:
        print("\n  ❌ No profitable strategies found")
    
    # Walk-Forward on top candidates
    # Deduplicate: best exit per signal+asset
    seen = set()
    wf_candidates = []
    for r in profitable:
        key = f"{r['signal']}|{r['asset']}"
        if key not in seen:
            seen.add(key)
            wf_candidates.append(r)
        if len(wf_candidates) >= 20:
            break
    
    if wf_candidates:
        print(f"\n📊 Walk-Forward: top {len(wf_candidates)} unique candidates")
        
        wf_results = []
        for i, r in enumerate(wf_candidates):
            sig_type = (r["z_low"], r["z_high"], r["bull200"], r["bull50"], r["vol"], r["signal"])
            exit_cfg = (r["sl"], r["trail"], r["max_hold"], r["exit"])
            
            wf = walk_forward_test(data[r["asset"]], sig_type, exit_cfg)
            r["wf"] = wf
            r["wf_robustness"] = wf["robustness"]
            r["wf_passed"] = wf["passed"]
            r["wf_avg_oos"] = wf["avg_oos"]
            wf_results.append(r)
            
            status = "✅" if wf["passed"] else "❌"
            print(f"  {status} {r['signal']:30s} {r['asset']:4s} | R={wf['robustness']:.0f} OOS={wf['avg_oos']:+.2f}% wins={wf['profitable_windows']}")
        
        passed = [r for r in wf_results if r["wf_passed"]]
        print(f"\n{'='*60}")
        print(f"FINAL: {len(profitable)} profitable IS | {len(wf_results)} WF-tested | {len(passed)} WF-passed")
        print(f"{'='*60}")
    else:
        passed = []
        wf_results = []
    
    # Save
    output = {
        "version": "V13b",
        "timestamp": datetime.now().isoformat(),
        "grid_total": len(results),
        "grid_valid": len(valid),
        "grid_profitable": len(profitable),
        "wf_tested": len(wf_results),
        "wf_passed": len(passed),
        "top_is": [
            {k: v for k, v in r.items() if k != "wf"}
            for r in profitable[:50]
        ],
        "wf_results": [
            {
                "signal": r["signal"],
                "asset": r["asset"],
                "exit": r["exit"],
                "is_return": r["net_return"],
                "is_trades": r["trade_count"],
                "wf_robustness": r.get("wf_robustness"),
                "wf_passed": r.get("wf_passed"),
                "wf_avg_oos": r.get("wf_avg_oos"),
                "wf_detail": r.get("wf", {}),
            }
            for r in wf_results
        ],
    }
    
    with open(OUTPUT, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n💾 Saved to {OUTPUT}")
    
    return output


if __name__ == "__main__":
    main()