#!/usr/bin/env python3
"""V10 — Proper Hyperliquid 1h Walk-Forward Validation

Compare funding edge on HL 1h vs Binance 8h over the same period.
"""
import json
import numpy as np
import polars as pl
from pathlib import Path
from datetime import datetime, timedelta

DATA_DIR = Path(__file__).resolve().parent.parent / "data_collector" / "data"
OUT_JSON = Path(__file__).resolve().parent / "funding_hl_wf_results.json"

# Cost params
MAKER_RT = 0.0004   # 0.04% round-trip
SLIPPAGE_RT = 0.0006 # 0.06% round-trip
TOTAL_COST_RT = MAKER_RT + SLIPPAGE_RT  # 0.1%

ASSETS = ["ADA", "AVAX", "BTC", "DOGE", "ETH", "SOL"]

def load_hl_data():
    hl = pl.read_parquet(DATA_DIR / "hl_funding.parquet")
    prices = pl.read_parquet(DATA_DIR / "prices_1h.parquet")
    # Round timestamps to hour for join
    hl = hl.with_columns(
        pl.col("timestamp").dt.truncate("1h").alias("ts_hour")
    )
    prices = prices.with_columns(
        pl.col("timestamp").dt.truncate("1h").alias("ts_hour")
    )
    df = hl.join(prices, on=["ts_hour", "asset"], how="inner", suffix="_price")
    df = df.sort(["asset", "ts_hour"])
    return df

def load_bn_data():
    bn = pl.read_parquet(DATA_DIR / "bn_funding.parquet")
    p8 = pl.read_parquet(DATA_DIR / "prices_8h.parquet")
    # prices_8h has ms timestamps
    p8 = p8.with_columns(
        (pl.col("timestamp") * 1_000_000).cast(pl.Datetime("us", "UTC")).alias("timestamp")
    ).drop("timestamp").rename({"timestamp": "timestamp"}) if False else p8
    # Actually let's check the type
    # p8 timestamp is int64 ms. Convert.
    p8 = p8.with_columns(
        pl.from_epoch(pl.col("timestamp"), time_unit="ms").alias("timestamp")
    )
    # BN funding is 8h, round to 8h
    bn = bn.with_columns(pl.col("timestamp").dt.truncate("8h").alias("ts_8h"))
    p8 = p8.with_columns(pl.col("timestamp").dt.truncate("8h").cast(pl.Datetime('us', 'UTC')).alias("ts_8h"))
    df = bn.join(p8.select(["ts_8h", "asset", "open", "high", "low", "close"]), 
                 left_on=["ts_8h", "asset"], right_on=["ts_8h", "asset"], how="inner", suffix="_price")
    df = df.sort(["asset", "ts_8h"])
    return df

def add_ema50(df, time_col="ts_hour"):
    """Add EMA50 of close per asset."""
    # Polars doesn't have EMA, do it manually per group
    assets_data = []
    for asset in ASSETS:
        sub = df.filter(pl.col("asset") == asset).sort(time_col)
        close = sub["close"].to_numpy()
        ema = _ema(close, 50)
        sub = sub.with_columns(pl.Series("ema50", ema))
        assets_data.append(sub)
    return pl.concat(assets_data)

def _ema(arr, span):
    ema = np.full_like(arr, np.nan, dtype=float)
    if len(arr) == 0:
        return ema
    alpha = 2.0 / (span + 1)
    # Start from first non-nan
    first_valid = 0
    for i in range(len(arr)):
        if not np.isnan(arr[i]):
            first_valid = i
            break
    ema[first_valid] = arr[first_valid]
    for i in range(first_valid + 1, len(arr)):
        if not np.isnan(arr[i]):
            if np.isnan(ema[i-1]):
                ema[i] = arr[i]
            else:
                ema[i] = alpha * arr[i] + (1 - alpha) * ema[i-1]
    return ema

def walk_forward_test(df, time_col, window_train_days, window_test_days, n_windows):
    """Run walk-forward test. Returns list of (train_df, test_df) per window."""
    all_times = df[time_col].unique().sort()
    if len(all_times) == 0:
        return []
    
    total_days = window_train_days + window_test_days
    windows = []
    start = all_times[0]
    td = timedelta(days=1)
    
    for w in range(n_windows):
        train_start = start + timedelta(days=w * total_days)
        train_end = train_start + timedelta(days=window_train_days)
        test_start = train_end
        test_end = test_start + timedelta(days=window_test_days)
        
        train_df = df.filter((pl.col(time_col) >= train_start) & (pl.col(time_col) < train_end))
        test_df = df.filter((pl.col(time_col) >= test_start) & (pl.col(time_col) < test_end))
        
        if train_df.height == 0 or test_df.height == 0:
            continue
        windows.append((train_df, test_df))
    
    return windows

def compute_percentiles(train_df, funding_col="funding_rate"):
    """Compute per-asset funding percentiles from training data."""
    percs = {}
    for asset in ASSETS:
        sub = train_df.filter(pl.col("asset") == asset)
        if sub.height < 10:
            percs[asset] = None
            continue
        rates = sub[funding_col].drop_nulls().to_numpy()
        if len(rates) < 10:
            percs[asset] = None
            continue
        percs[asset] = {
            "P05": np.percentile(rates, 5),
            "P10": np.percentile(rates, 10),
            "P25": np.percentile(rates, 25),
            "P50": np.percentile(rates, 50),
            "P75": np.percentile(rates, 75),
            "P90": np.percentile(rates, 90),
            "P95": np.percentile(rates, 95),
        }
    return percs

def simulate_trades(test_df, percs, direction, threshold, hold_hours, sl_pct, 
                    regime_filter, time_col, funding_col="funding_rate"):
    """
    Simulate trades on test data.
    direction: "long" or "short"
    threshold: e.g. "P10" for long (enter when funding < P10), "P90" for short
    hold_hours: number of hours to hold
    sl_pct: stop loss percent (0 = no SL)
    regime_filter: "always", "bull_only", "bear_only"
    """
    trades = []
    
    for asset in ASSETS:
        if percs.get(asset) is None:
            continue
        thresh_val = percs[asset][threshold]
        
        sub = test_df.filter(pl.col("asset") == asset).sort(time_col)
        if sub.height < 2:
            continue
        
        rows = sub.iter_rows(named=True)
        rows_list = list(rows)
        n = len(rows_list)
        
        i = 0
        while i < n:
            row = rows_list[i]
            funding = row[funding_col]
            close = row["close"]
            ema50 = row.get("ema50")
            
            # Entry condition
            enter = False
            if direction == "long" and funding is not None and funding < thresh_val:
                enter = True
            elif direction == "short" and funding is not None and funding > thresh_val:
                enter = True
            
            if not enter:
                i += 1
                continue
            
            # Regime filter
            if regime_filter == "bull_only" and (ema50 is None or close < ema50):
                i += 1
                continue
            if regime_filter == "bear_only" and (ema50 is None or close >= ema50):
                i += 1
                continue
            
            entry_price = close
            entry_time = row[time_col]
            
            # Find exit price after hold_hours
            exit_idx = min(i + hold_hours, n - 1)
            
            # Check SL along the way
            hit_sl = False
            exit_price = rows_list[exit_idx]["close"]
            
            if sl_pct > 0:
                for j in range(i + 1, exit_idx + 1):
                    if j >= n:
                        break
                    low = rows_list[j]["low"] if rows_list[j]["low"] is not None else rows_list[j]["close"]
                    high = rows_list[j]["high"] if rows_list[j]["high"] is not None else rows_list[j]["close"]
                    
                    if direction == "long":
                        if low <= entry_price * (1 - sl_pct / 100):
                            exit_price = entry_price * (1 - sl_pct / 100)
                            hit_sl = True
                            break
                    else:
                        if high >= entry_price * (1 + sl_pct / 100):
                            exit_price = entry_price * (1 + sl_pct / 100)
                            hit_sl = True
                            break
            
            # Calculate return
            if direction == "long":
                gross_ret = (exit_price - entry_price) / entry_price
            else:
                gross_ret = (entry_price - exit_price) / entry_price
            
            # Funding payment cost (for short: you receive funding if negative, pay if positive)
            # On HL, if you're short and funding > 0, you PAY funding to longs
            # If short and funding < 0, you RECEIVE funding
            funding_cost = 0.0
            for j in range(i, exit_idx):
                if j >= n:
                    break
                fr = rows_list[j].get(funding_col, 0) or 0
                if direction == "short":
                    funding_cost -= fr  # short pays positive funding, receives negative
                else:
                    funding_cost += fr  # long receives positive funding, pays negative
            
            net_ret = gross_ret - TOTAL_COST_RT + funding_cost
            
            trades.append({
                "asset": asset,
                "entry_time": str(entry_time),
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_ret": gross_ret,
                "funding_cost": funding_cost,
                "net_ret": net_ret,
                "hit_sl": hit_sl,
            })
            
            # Skip to after exit
            i = exit_idx + 1
    
    return trades

def random_baseline(test_df, direction, threshold_name, hold_hours, sl_pct, 
                    regime_filter, time_col, n_trades_per_asset, n_iters=100, funding_col="funding_rate"):
    """Generate random entries with same frequency, measure returns."""
    random_returns = []
    
    for asset in ASSETS:
        sub = test_df.filter(pl.col("asset") == asset).sort(time_col)
        if sub.height < hold_hours + 1:
            continue
        rows_list = list(sub.iter_rows(named=True))
        n = len(rows_list)
        
        # Determine eligible entry indices
        eligible = []
        for i in range(n - hold_hours):
            eligible.append(i)
        
        if len(eligible) < n_trades_per_asset:
            continue
        
        iter_rets = []
        for _ in range(n_iters):
            indices = np.random.choice(eligible, size=min(n_trades_per_asset, len(eligible)), replace=False)
            rets = []
            for i in indices:
                entry_price = rows_list[i]["close"]
                exit_idx = min(i + hold_hours, n - 1)
                exit_price = rows_list[exit_idx]["close"]
                
                if direction == "long":
                    ret = (exit_price - entry_price) / entry_price
                else:
                    ret = (entry_price - exit_price) / entry_price
                
                ret -= TOTAL_COST_RT
                rets.append(ret)
            iter_rets.append(np.mean(rets) if rets else 0)
        
        random_returns.extend(iter_rets)
    
    return random_returns

def run_all():
    print("Loading HL 1h data...")
    hl_df = load_hl_data()
    print(f"HL joined data: {hl_df.height} rows, {hl_df['ts_hour'].min()} - {hl_df['ts_hour'].max()}")
    
    # Data range per asset
    for a in ASSETS:
        sub = hl_df.filter(pl.col("asset") == a)
        print(f"  {a}: {sub.height} rows")
    
    # Add EMA50
    print("Adding EMA50...")
    hl_df = add_ema50(hl_df, "ts_hour")
    
    # Walk-forward windows
    print("Setting up walk-forward windows (14d train + 7d test, 5 windows)...")
    windows = walk_forward_test(hl_df, "ts_hour", 14, 7, 5)
    print(f"Got {len(windows)} windows with data")
    for i, (train, test) in enumerate(windows):
        print(f"  Window {i}: train {train['ts_hour'].min()}-{train['ts_hour'].max()}, test {test['ts_hour'].min()}-{test['ts_hour'].max()}")
    
    if len(windows) < 2:
        print("WARNING: Insufficient data for proper WF. Need at least 2 windows (42 days).")
    
    # Strategy configs
    configs = [
        # (direction, threshold, hold_hours, label)
        ("long", "P10", 4, "Long_P10_4h"),
        ("long", "P10", 8, "Long_P10_8h"),
        ("long", "P10", 24, "Long_P10_24h"),
        ("long", "P05", 24, "Long_P05_24h"),
        ("short", "P90", 4, "Short_P90_4h"),
        ("short", "P90", 8, "Short_P90_8h"),
        ("short", "P90", 24, "Short_P90_24h"),
        ("short", "P95", 24, "Short_P95_24h"),
    ]
    
    sl_configs = [0, 3, 5]  # no SL, 3%, 5%
    regime_configs = ["always", "bull_only", "bear_only"]
    
    all_results = {}
    
    print("\n=== Running HL Walk-Forward Tests ===")
    for direction, threshold, hold_h, label in configs:
        for sl in sl_configs:
            for regime in regime_configs:
                key = f"{label}_SL{sl}_{regime}"
                all_trades = []
                percs_all = []
                
                for train_df, test_df in windows:
                    percs = compute_percentiles(train_df)
                    percs_all.append(percs)
                    trades = simulate_trades(
                        test_df, percs, direction, threshold, hold_h, sl, regime, "ts_hour"
                    )
                    all_trades.extend(trades)
                
                if not all_trades:
                    all_results[key] = {"n_trades": 0, "avg_net_ret": None, "avg_gross_ret": None}
                    continue
                
                n_trades = len(all_trades)
                avg_gross = np.mean([t["gross_ret"] for t in all_trades])
                avg_net = np.mean([t["net_ret"] for t in all_trades])
                avg_funding = np.mean([t["funding_cost"] for t in all_trades])
                sl_hit_rate = np.mean([t["hit_sl"] for t in all_trades])
                
                # Per-asset breakdown
                per_asset = {}
                for a in ASSETS:
                    at = [t for t in all_trades if t["asset"] == a]
                    if at:
                        per_asset[a] = {
                            "n": len(at),
                            "avg_net": np.mean([t["net_ret"] for t in at]),
                            "avg_gross": np.mean([t["gross_ret"] for t in at]),
                        }
                
                # Random baseline
                total_n_per_asset = max(1, n_trades // max(1, len([a for a in ASSETS if percs_all[0].get(a) is not None])))
                random_rets = random_baseline(
                    pl.concat([t for _, t in windows]),
                    direction, threshold, hold_h, sl, regime, "ts_hour",
                    n_trades_per_asset=total_n_per_asset, n_iters=100
                )
                random_mean = np.mean(random_rets) if random_rets else 0
                edge_vs_random = avg_net - random_mean
                
                all_results[key] = {
                    "n_trades": n_trades,
                    "avg_gross_ret": avg_gross,
                    "avg_net_ret": avg_net,
                    "avg_funding_cost": avg_funding,
                    "sl_hit_rate": sl_hit_rate,
                    "random_mean": random_mean,
                    "edge_vs_random": edge_vs_random,
                    "per_asset": per_asset,
                }
                
                print(f"  {key}: n={n_trades}, net={avg_net:.4%}, gross={avg_gross:.4%}, "
                      f"SL={sl_hit_rate:.0%}, edge_vs_rand={edge_vs_random:.4%}")
    
    # === Binance comparison ===
    print("\n=== Loading Binance 8h data for comparison ===")
    try:
        bn_df = load_bn_data()
        print(f"BN joined data: {bn_df.height} rows, {bn_df['ts_8h'].min()}-{bn_df['ts_8h'].max()}")
        bn_df = add_ema50(bn_df, "ts_8h")
        
        # Use same date range as HL test period
        hl_min = hl_df["ts_hour"].min()
        hl_max = hl_df["ts_hour"].max()
        bn_overlap = bn_df.filter(
            (pl.col("ts_8h") >= hl_min) & (pl.col("ts_8h") <= hl_max)
        )
        print(f"BN overlapping period: {bn_overlap.height} rows")
        
        # For BN, use same WF structure but 8h means ~3 candles/day
        # 14 days = 42 candles train, 7 days = 21 candles test
        bn_windows = walk_forward_test(bn_overlap, "ts_8h", 14, 7, 5)
        print(f"BN windows: {len(bn_windows)}")
        
        bn_results = {}
        for direction, threshold, hold_h, label in configs:
            # Convert hold_h to 8h candles
            hold_8h = max(1, hold_h // 8)
            label_bn = f"BN_{label}_hold{hold_h}h"
            
            all_trades = []
            for train_df, test_df in bn_windows:
                percs = compute_percentiles(train_df)
                trades = simulate_trades(
                    test_df, percs, direction, threshold, hold_8h, 0, "always", "ts_8h"
                )
                all_trades.extend(trades)
            
            if all_trades:
                avg_net = np.mean([t["net_ret"] for t in all_trades])
                avg_gross = np.mean([t["gross_ret"] for t in all_trades])
                bn_results[label_bn] = {
                    "n_trades": len(all_trades),
                    "avg_net_ret": avg_net,
                    "avg_gross_ret": avg_gross,
                }
                print(f"  {label_bn}: n={len(all_trades)}, net={avg_net:.4%}, gross={avg_gross:.4%}")
            else:
                bn_results[label_bn] = {"n_trades": 0}
                print(f"  {label_bn}: no trades")
    except Exception as e:
        print(f"BN comparison failed: {e}")
        bn_results = {"error": str(e)}
    
    # === Summary ===
    print("\n" + "="*60)
    print("=== HL 1h WALK-FORWARD RESULTS ===")
    data_days = (hl_df["ts_hour"].max() - hl_df["ts_hour"].min()).days
    print(f"Data range: {data_days} days, {len(windows)} windows")
    
    print("\n--- Key configs (no SL, always regime) ---")
    for direction, threshold, hold_h, label in configs:
        key = f"{label}_SL0_always"
        r = all_results.get(key, {})
        if r.get("n_trades", 0) > 0:
            print(f"  {label}: n={r['n_trades']}, net={r['avg_net_ret']:.4%}, "
                  f"edge_vs_rand={r['edge_vs_random']:.4%}")
    
    print("\n=== REGIME FILTER ON HL ===")
    for regime in ["always", "bull_only", "bear_only"]:
        print(f"  {regime}:")
        for direction, threshold, hold_h, label in configs:
            key = f"{label}_SL0_{regime}"
            r = all_results.get(key, {})
            if r.get("n_trades", 0) > 0:
                print(f"    {label}: net={r['avg_net_ret']:.4%}")
    
    print("\n=== SL COMPARISON (always regime) ===")
    for sl in [0, 3, 5]:
        print(f"  SL={sl}%:")
        for direction, threshold, hold_h, label in configs:
            key = f"{label}_SL{sl}_always"
            r = all_results.get(key, {})
            if r.get("n_trades", 0) > 0:
                print(f"    {label}: net={r['avg_net_ret']:.4%}, SL_hit={r['sl_hit_rate']:.0%}")
    
    if not isinstance(bn_results, dict) or "error" not in bn_results:
        print("\n=== BINANCE vs HYPERLIQUID (overlapping period) ===")
        for direction, threshold, hold_h, label in configs:
            hl_key = f"{label}_SL0_always"
            bn_key = f"BN_{label}_hold{hold_h}h"
            hl_r = all_results.get(hl_key, {})
            bn_r = bn_results.get(bn_key, {})
            hl_net = hl_r.get("avg_net_ret", None)
            bn_net = bn_r.get("avg_net_ret", None)
            if hl_net is not None or bn_net is not None:
                hl_s = f"{hl_net:.4%}" if hl_net is not None else "N/A"
                bn_s = f"{bn_net:.4%}" if bn_net is not None else "N/A"
                print(f"  {label}: HL={hl_s}, BN={bn_s}")
    
    # Verdict
    print("\n=== VERDICT ===")
    # Check best configs
    best_hl_edge = 0
    best_config = ""
    for direction, threshold, hold_h, label in configs:
        for regime in ["always", "bull_only", "bear_only"]:
            for sl in [0, 3, 5]:
                key = f"{label}_SL{sl}_{regime}"
                r = all_results.get(key, {})
                if r.get("edge_vs_random") is not None and r["n_trades"] >= 5:
                    if r["edge_vs_random"] > best_hl_edge:
                        best_hl_edge = r["edge_vs_random"]
                        best_config = key
    
    # Annualize: per-trade edge * trades per year
    # Rough: if avg 1 trade/day per asset * 6 assets = ~6 trades/day * 365 = 2190 trades/year
    # But more realistically, fewer trades. Let's compute from actual data.
    total_days = data_days
    total_trades_best = all_results.get(best_config, {}).get("n_trades", 0)
    trades_per_day = total_trades_best / max(1, total_days) if total_days > 0 else 0
    annualized_edge = best_hl_edge * trades_per_day * 365 * 100  # in %
    
    edge_exists = annualized_edge > 0.3
    
    if edge_exists:
        print(f"Edge exists on HL: YES")
        print(f"Best config: {best_config}")
        print(f"Per-trade edge vs random: {best_hl_edge:.4%}")
        print(f"Annualized edge: {annualized_edge:.2f}%")
        print(f"Kill criterion (edge > 0.3% ann.): PASS")
    else:
        print(f"Edge exists on HL: NO (or marginal)")
        print(f"Best config: {best_config}")
        print(f"Per-trade edge vs random: {best_hl_edge:.4%}")
        print(f"Annualized edge: {annualized_edge:.2f}%")
        if total_days < 60:
            print(f"Likely reason: Data too short ({total_days} days, need 180+)")
        elif best_hl_edge < 0:
            print("Likely reason: HL funding dynamics differ from Binance")
        else:
            print("Likely reason: Edge exists but too small after costs")
        print(f"Kill criterion (edge > 0.3% ann.): {'PASS' if edge_exists else 'FAIL'}")
    
    # Save results
    # Convert numpy types for JSON
    def convert(obj):
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        raise TypeError(f"Not serializable: {type(obj)}")
    
    output = {
        "hl_results": all_results,
        "bn_results": bn_results,
        "data_days": data_days,
        "n_windows": len(windows),
        "best_config": best_config,
        "best_edge_vs_random": float(best_hl_edge),
        "annualized_edge_pct": float(annualized_edge),
        "edge_exists": edge_exists,
        "kill_criterion": "PASS" if edge_exists else "FAIL",
    }
    
    with open(OUT_JSON, "w") as f:
        json.dump(output, f, indent=2, default=convert)
    print(f"\nResults saved to {OUT_JSON}")

if __name__ == "__main__":
    np.random.seed(42)
    run_all()