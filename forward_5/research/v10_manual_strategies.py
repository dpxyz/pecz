#!/usr/bin/env python3
"""Manual V10 strategy walk-forward test with regime filtering."""

import json
import polars as pl
from pathlib import Path
import numpy as np

DATA_DIR = Path("/data/.openclaw/workspace/forward_v5/forward_5/research/data_v10")
OUTPUT_PATH = Path("/data/.openclaw/workspace/forward_v5/forward_5/research/v10_manual_results.json")

COST_RT = 0.001  # 0.1% round-trip
HOLD_HOURS = 24
N_WINDOWS = 10
TRAIN_WEEKS = 5
TEST_WEEKS = 5
MS_PER_WEEK = 7 * 24 * 3600 * 1000

def load_data(asset: str) -> pl.DataFrame:
    df = pl.read_parquet(DATA_DIR / f"{asset}_1h_full.parquet").sort("timestamp")
    # Replace inf in funding_z with null
    df = df.with_columns(
        pl.when(pl.col("funding_z").is_finite())
        .then(pl.col("funding_z"))
        .otherwise(None)
        .alias("funding_z")
    )
    # Compute 24h forward return
    df = df.with_columns(
        (pl.col("close").shift(-24) / pl.col("close") - 1).alias("ret_24h")
    )
    return df

def get_windows(df: pl.DataFrame):
    t0 = df["timestamp"].min()
    t_end = df["timestamp"].max()
    window_ms = (TRAIN_WEEKS + TEST_WEEKS) * MS_PER_WEEK
    windows = []
    for i in range(N_WINDOWS):
        wt_start = t0 + i * window_ms
        wt_end = wt_start + window_ms
        if wt_end > t_end:
            break
        train_end = wt_start + TRAIN_WEEKS * MS_PER_WEEK
        train = df.filter((pl.col("timestamp") >= wt_start) & (pl.col("timestamp") < train_end))
        test = df.filter((pl.col("timestamp") >= train_end) & (pl.col("timestamp") < wt_end))
        windows.append((train, test))
    return windows

def is_pct(arr, pct):
    s = [x for x in arr if x is not None and np.isfinite(x)]
    if not s:
        return None
    s.sort()
    idx = max(0, min(len(s) - 1, int(len(s) * pct / 100)))
    return s[idx]

def run_strategy(test_df, signal_col, direction, regime_filter, threshold=None, use_cross=False):
    """Returns list of trade net returns."""
    df = test_df.filter(pl.col("ret_24h").is_not_null())
    # Drop rows with null funding_z if that's the signal
    if signal_col == "funding_z":
        df = df.filter(pl.col("funding_z").is_not_null())
    if signal_col == "fund_cross_up":
        df = df.filter(pl.col("fund_cross_up").is_not_null())
    
    # Regime filter
    if regime_filter == "bull":
        df = df.filter(pl.col("bull200") == 1)
    elif regime_filter == "bear":
        df = df.filter(pl.col("bull200") == 0)
    
    if len(df) == 0:
        return []
    
    # Signal filter
    if use_cross:
        entries = df.filter(pl.col(signal_col) == 1)
    elif threshold is not None:
        if direction == "long":
            entries = df.filter(pl.col(signal_col) < threshold)
        else:
            entries = df.filter(pl.col(signal_col) > threshold)
    else:
        entries = df.filter(pl.col(signal_col) == 1)
    
    if len(entries) == 0:
        return []
    
    # De-duplicate: skip entries within 24h of each other
    entries = entries.sort("timestamp")
    trade_rows = []
    last_exit_ts = -999_999_999_999_999
    for row in entries.iter_rows(named=True):
        if row["timestamp"] >= last_exit_ts:
            trade_rows.append(row)
            last_exit_ts = row["timestamp"] + HOLD_HOURS * 3600 * 1000
    
    if not trade_rows:
        return []
    
    trade_returns = []
    for row in trade_rows:
        price_ret = row["ret_24h"]
        if price_ret is None:
            continue
        
        # Direction
        if direction == "short":
            price_ret = -price_ret
        
        # Costs
        net_ret = price_ret - COST_RT
        
        # Funding P&L: contrarian = receive -funding for longs, pay funding for shorts
        # Simplified: use funding at entry time
        fr = row.get("funding_rate", 0.0)
        if fr is None:
            fr = 0.0
        funding_pnl = -fr * HOLD_HOURS
        net_ret += funding_pnl
        
        trade_returns.append(net_ret)
    
    return trade_returns

def evaluate(trades_list, n_windows):
    all_trades = []
    profitable_windows = 0
    valid_windows = 0
    for trades in trades_list:
        valid_windows += 1
        if trades and sum(trades) / len(trades) > 0:
            profitable_windows += 1
        all_trades.extend(trades)
    
    if not all_trades:
        return {"avg_ret_pct": 0, "win_rate_pct": 0, "n_trades": 0, 
                "n_profitable_windows": 0, "robustness_pct": 0}
    
    return {
        "avg_ret_pct": round(sum(all_trades) / len(all_trades) * 100, 4),
        "win_rate_pct": round(sum(1 for t in all_trades if t > 0) / len(all_trades) * 100, 1),
        "n_trades": len(all_trades),
        "n_profitable_windows": profitable_windows,
        "robustness_pct": round(profitable_windows / max(valid_windows, 1) * 100, 0),
    }

STRATEGIES = [
    {"name": "BTC_Long_P10", "asset": "BTCUSDT", "direction": "long",
     "signal": "funding_z", "use_pct": True, "pct": 10},
    {"name": "SOL_Long_z-2", "asset": "SOLUSDT", "direction": "long",
     "signal": "funding_z", "threshold": -2, "use_pct": False},
    {"name": "AVAX_Long_z-1", "asset": "AVAXUSDT", "direction": "long",
     "signal": "funding_z", "threshold": -1, "use_pct": False},
    {"name": "ETH_Shift", "asset": "ETHUSDT", "direction": "long",
     "signal": "fund_cross_up", "use_cross": True},
    {"name": "ADA_Short_P90", "asset": "ADAUSDT", "direction": "short",
     "signal": "funding_z", "use_pct": True, "pct": 90},
]

def main():
    results = {}
    
    # Preload all data
    all_data = {}
    for strat in STRATEGIES:
        if strat["asset"] not in all_data:
            all_data[strat["asset"]] = load_data(strat["asset"])
    
    all_windows = {}
    for asset, df in all_data.items():
        all_windows[asset] = get_windows(df)
    
    for strat in STRATEGIES:
        print(f"\n{'='*60}")
        print(f"Strategy: {strat['name']} ({strat['direction']})")
        print(f"{'='*60}")
        
        windows = all_windows[strat["asset"]]
        print(f"  {len(windows)} WF windows available")
        
        for regime in ["full", "bull", "bear"]:
            window_trades = []
            for train_df, test_df in windows:
                threshold = strat.get("threshold")  # None for cross strategies
                if strat.get("use_pct"):
                    arr = train_df["funding_z"].drop_nulls().to_list()
                    # Filter inf
                    arr = [x for x in arr if np.isfinite(x)]
                    threshold = is_pct(arr, strat["pct"])
                    if threshold is None:
                        window_trades.append([])
                        continue
                
                trades = run_strategy(
                    test_df, strat["signal"], strat["direction"], regime,
                    threshold, strat.get("use_cross", False),
                )
                window_trades.append(trades)
            
            metrics = evaluate(window_trades, len(windows))
            key = f"{strat['name']}_{regime}"
            results[key] = metrics
            print(f"  {regime:5s}: avg={metrics['avg_ret_pct']:+.4f}%  WR={metrics['win_rate_pct']:.1f}%  "
                  f"N={metrics['n_trades']:4d}  profitable_wins={metrics['n_profitable_windows']}/{len(windows)}  "
                  f"robustness={metrics['robustness_pct']:.0f}%")
    
    # Portfolio combination
    print(f"\n{'='*60}")
    print("PORTFOLIO (equal-weight per strategy per window)")
    print(f"{'='*60}")
    
    for regime in ["full", "bull", "bear"]:
        # Per-window: average strategy returns, then check if window profitable
        window_combined_avgs = []
        all_trades = []
        
        n_w = len(list(all_windows.values())[0])
        for w_idx in range(n_w):
            strat_window_avgs = []
            for strat in STRATEGIES:
                windows = all_windows[strat["asset"]]
                if w_idx >= len(windows):
                    continue
                train_df, test_df = windows[w_idx]
                threshold = strat.get("threshold")
                if strat.get("use_pct"):
                    arr = train_df["funding_z"].drop_nulls().to_list()
                    arr = [x for x in arr if np.isfinite(x)]
                    threshold = is_pct(arr, strat["pct"])
                    if threshold is None:
                        continue
                
                trades = run_strategy(
                    test_df, strat["signal"], strat["direction"], regime,
                    threshold, strat.get("use_cross", False),
                )
                all_trades.extend(trades)
                if trades:
                    strat_window_avgs.append(sum(trades) / len(trades))
            
            if strat_window_avgs:
                window_combined_avgs.append(sum(strat_window_avgs) / len(strat_window_avgs))
        
        if not all_trades:
            print(f"  {regime:5s}: No trades")
            results[f"PORTFOLIO_{regime}"] = {"avg_ret_pct": 0, "win_rate_pct": 0, "n_trades": 0, "robustness_pct": 0}
            continue
        
        profitable_windows = sum(1 for a in window_combined_avgs if a > 0)
        metrics = {
            "avg_ret_pct": round(sum(all_trades) / len(all_trades) * 100, 4),
            "win_rate_pct": round(sum(1 for t in all_trades if t > 0) / len(all_trades) * 100, 1),
            "n_trades": len(all_trades),
            "n_profitable_windows": profitable_windows,
            "n_windows": len(window_combined_avgs),
            "robustness_pct": round(profitable_windows / max(len(window_combined_avgs), 1) * 100, 0),
        }
        results[f"PORTFOLIO_{regime}"] = metrics
        print(f"  {regime:5s}: avg={metrics['avg_ret_pct']:+.4f}%  WR={metrics['win_rate_pct']:.1f}%  "
              f"N={metrics['n_trades']:4d}  profitable_wins={profitable_windows}/{len(window_combined_avgs)}  "
              f"robustness={metrics['robustness_pct']:.0f}%")
    
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()