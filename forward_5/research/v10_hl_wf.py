#!/usr/bin/env python3
"""V10: HL 1h Walk-Forward Test with correct price data."""

import json
import polars as pl
import numpy as np
from datetime import datetime, timezone

ASSETS = ["BTC", "ETH", "SOL", "AVAX"]
WEEKS_TRAIN = 5
WEEKS_TEST = 5
N_WINDOWS = 8
COST_RT = 0.0004 + 0.0006  # maker + slippage round-trip = 0.1%

# Load data
hl = pl.read_parquet("data_collector/data/hl_funding_full.parquet")
prices = pl.read_parquet("data_collector/data/prices_bn_1h_full.parquet")
bn = pl.read_parquet("data_collector/data/bn_funding_1yr.parquet")

# Filter to valid assets
hl = hl.filter(pl.col("asset").is_in(ASSETS))
prices = prices.filter(pl.col("asset").is_in(ASSETS))
bn = bn.filter(pl.col("asset").is_in(ASSETS))

# Convert ms timestamps to hourly (floor to hour)
hl = hl.with_columns((pl.col("timestamp") // 3_600_000 * 3_600_000).alias("ts_hour"))
prices = prices.with_columns((pl.col("timestamp") // 3_600_000 * 3_600_000).alias("ts_hour"))
bn = bn.with_columns((pl.col("timestamp") // 3_600_000 * 3_600_000).alias("ts_hour"))

# Join funding + prices
df = hl.join(prices.select(["ts_hour", "asset", "open", "high", "low", "close"]), on=["ts_hour", "asset"], how="inner")
print(f"Joined HL data: {len(df)} rows, {df['asset'].n_unique()} assets")

# Date range
min_ts = df["ts_hour"].min()
max_ts = df["ts_hour"].max()
print(f"Date range: {datetime.fromtimestamp(min_ts/1000, tz=timezone.utc)} - {datetime.fromtimestamp(max_ts/1000, tz=timezone.utc)}")

# Window setup
total_weeks = WEEKS_TRAIN + WEEKS_TEST  # 10 weeks per window
window_ms = total_weeks * 7 * 24 * 3_600_000
train_ms = WEEKS_TRAIN * 7 * 24 * 3_600_000

# Sort by time
df = df.sort(["asset", "ts_hour"])

# EMA calculation
def calc_ema(series, span):
    alpha = 2.0 / (span + 1)
    vals = series.to_numpy()
    ema = np.empty(len(vals))
    ema[0] = vals[0]
    for i in range(1, len(vals)):
        ema[i] = alpha * vals[i] + (1 - alpha) * ema[i-1]
    return ema

# Walk-forward
results = []
window_results = []

for w in range(N_WINDOWS):
    start = min_ts + w * window_ms
    train_end = start + train_ms
    test_end = train_end + (WEEKS_TEST * 7 * 24 * 3_600_000)
    
    if test_end > max_ts:
        print(f"Window {w}: exceeds data range, stopping")
        break
    
    print(f"\nWindow {w}: train={datetime.fromtimestamp(start/1000, tz=timezone.utc).strftime('%Y-%m-%d')} to {datetime.fromtimestamp(train_end/1000, tz=timezone.utc).strftime('%Y-%m-%d')}, test to {datetime.fromtimestamp(test_end/1000, tz=timezone.utc).strftime('%Y-%m-%d')}")
    
    train_df = df.filter((pl.col("ts_hour") >= start) & (pl.col("ts_hour") < train_end))
    test_df = df.filter((pl.col("ts_hour") >= train_end) & (pl.col("ts_hour") < test_end))
    
    # Calculate percentiles per asset
    pctls = train_df.group_by("asset").agg([
        pl.col("funding_rate").quantile(0.05).alias("p05"),
        pl.col("funding_rate").quantile(0.10).alias("p10"),
        pl.col("funding_rate").quantile(0.25).alias("p25"),
        pl.col("funding_rate").quantile(0.50).alias("p50"),
        pl.col("funding_rate").quantile(0.75).alias("p75"),
        pl.col("funding_rate").quantile(0.90).alias("p90"),
        pl.col("funding_rate").quantile(0.95).alias("p95"),
    ])
    pctl_dict = {r["asset"]: {k: r[k] for k in ["p05","p10","p25","p50","p75","p90","p95"]} for r in pctls.iter_rows(named=True)}
    
    # Calculate EMA50 per asset from training close prices
    # For regime filter, compute on full training then extend into test
    ema_per_asset = {}
    for asset in ASSETS:
        asset_train = train_df.filter(pl.col("asset") == asset).sort("ts_hour")
        if len(asset_train) == 0:
            continue
        closes = asset_train["close"].to_numpy()
        if len(closes) < 50:
            continue
        ema_vals = calc_ema(asset_train["close"], 50)
        ema_per_asset[asset] = ema_vals[-1]  # last training EMA value
    
    # For each test row, determine if entry signal
    test_with_pctls = test_df.join(pctls, on="asset", how="left")
    
    # Generate signals
    trades = []
    for asset in ASSETS:
        if asset not in pctl_dict or asset not in ema_per_asset:
            continue
        p = pctl_dict[asset]
        ema_val = ema_per_asset[asset]
        
        asset_test = test_with_pctls.filter(pl.col("asset") == asset).sort("ts_hour")
        if len(asset_test) == 0:
            continue
        
        rows = asset_test.iter_rows(named=True)
        for row in rows:
            fr = row["funding_rate"]
            close = row["close"]
            ts = row["ts_hour"]
            
            # Regime
            bull = close > ema_val
            bear = close < ema_val
            
            # Long signals
            for threshold_name, threshold_val in [("P05", p["p05"]), ("P10", p["p10"])]:
                if fr < threshold_val:
                    # Find close price 24h later
                    target_ts = ts + 24 * 3_600_000
                    future = asset_test.filter(pl.col("ts_hour") == target_ts)
                    if len(future) > 0:
                        entry = close
                        exit_price = future["close"][0]
                        gross_ret = (exit_price - entry) / entry
                        # Funding received: negative funding rate * hours (we receive when negative)
                        funding_hours = 24
                        funding_pnl = -fr * funding_hours  # negative rate → positive for us
                        net_ret = gross_ret - COST_RT + funding_pnl
                        trades.append({
                            "asset": asset, "direction": "long", "threshold": threshold_name,
                            "window": w, "ts": ts, "ret": net_ret, "gross_ret": gross_ret,
                            "funding_pnl": funding_pnl, "bull": bull, "bear": bear,
                            "entry": entry, "exit": exit_price, "sl_hit": False,
                        })
            
            # Short signals
            for threshold_name, threshold_val in [("P90", p["p90"]), ("P95", p["p95"])]:
                if fr > threshold_val:
                    target_ts = ts + 24 * 3_600_000
                    future = asset_test.filter(pl.col("ts_hour") == target_ts)
                    if len(future) > 0:
                        entry = close
                        exit_price = future["close"][0]
                        gross_ret = (entry - exit_price) / entry  # short
                        funding_hours = 24
                        funding_pnl = -fr * funding_hours  # we pay the funding rate
                        net_ret = gross_ret - COST_RT + funding_pnl
                        trades.append({
                            "asset": asset, "direction": "short", "threshold": threshold_name,
                            "window": w, "ts": ts, "ret": net_ret, "gross_ret": gross_ret,
                            "funding_pnl": funding_pnl, "bull": bull, "bear": bear,
                            "entry": entry, "exit": exit_price, "sl_hit": False,
                        })
    
    print(f"  Trades: {len(trades)}")
    results.extend(trades)

print(f"\n=== TOTAL TRADES: {len(results)} ===")

# Convert to polars for analysis
if len(results) == 0:
    print("NO TRADES FOUND - data alignment issue")
    exit(1)

trades_df = pl.DataFrame(results)

# === SUMMARY TABLES ===
print("\n=== HL 1h WALK-FORWARD ===")
print(f"Data: {datetime.fromtimestamp(min_ts/1000, tz=timezone.utc).strftime('%Y-%m-%d')} to {datetime.fromtimestamp(max_ts/1000, tz=timezone.utc).strftime('%Y-%m-%d')}")

# Per-asset trade counts
for asset in ASSETS:
    n = len(trades_df.filter(pl.col("asset") == asset))
    print(f"  {asset}: {n} trades")

# === LONG STRATEGIES ===
print("\n=== LONG STRATEGIES ===")
for threshold in ["P05", "P10"]:
    for direction in ["long"]:
        subset = trades_df.filter((pl.col("direction") == direction) & (pl.col("threshold") == threshold))
        print(f"\n  Long {threshold} (hold 24h):")
        for asset in ASSETS:
            a = subset.filter(pl.col("asset") == asset)
            if len(a) > 0:
                avg = a["ret"].mean() * 100
                n = len(a)
                print(f"    {asset}: avg={avg:.4f}%, n={n}")
            else:
                print(f"    {asset}: no trades")
        all_avg = subset["ret"].mean() * 100 if len(subset) > 0 else 0
        print(f"    AVG: {all_avg:.4f}%, n={len(subset)}")

# === SHORT STRATEGIES ===
print("\n=== SHORT STRATEGIES ===")
for threshold in ["P90", "P95"]:
    subset = trades_df.filter((pl.col("direction") == "short") & (pl.col("threshold") == threshold))
    print(f"\n  Short {threshold} (hold 24h):")
    for asset in ASSETS:
        a = subset.filter(pl.col("asset") == asset)
        if len(a) > 0:
            avg = a["ret"].mean() * 100
            print(f"    {asset}: avg={avg:.4f}%, n={len(a)}")
        else:
            print(f"    {asset}: no trades")
    all_avg = subset["ret"].mean() * 100 if len(subset) > 0 else 0
    print(f"    AVG: {all_avg:.4f}%, n={len(subset)}")

# === REGIME FILTER ===
print("\n=== REGIME FILTER ===")
for regime in ["always", "bull_only", "bear_only"]:
    for direction in ["long", "short"]:
        if regime == "always":
            subset = trades_df.filter(pl.col("direction") == direction)
        elif regime == "bull_only":
            subset = trades_df.filter((pl.col("direction") == direction) & (pl.col("bull") == True))
        else:
            subset = trades_df.filter((pl.col("direction") == direction) & (pl.col("bear") == True))
        
        if len(subset) > 0:
            avg = subset["ret"].mean() * 100
            print(f"  {regime:>10} {direction:>5}: avg={avg:.4f}%, n={len(subset)}")

# === WINDOW CONSISTENCY ===
print("\n=== WINDOW CONSISTENCY ===")
for direction in ["long", "short"]:
    for threshold in (["P05", "P10"] if direction == "long" else ["P90", "P95"]):
        subset = trades_df.filter((pl.col("direction") == direction) & (pl.col("threshold") == threshold))
        label = f"{direction} {threshold}"
        per_window = subset.group_by("window").agg(pl.col("ret").mean().alias("avg_ret"))
        profitable = sum(1 for r in per_window.iter_rows() if r[1] > 0)
        print(f"  {label:>10}: {profitable}/8 windows profitable")

# === RANDOM BASELINE ===
print("\n=== RANDOM BASELINE ===")
np.random.seed(42)
for direction in ["long", "short"]:
    for threshold in (["P10"] if direction == "long" else ["P90"]):
        subset = trades_df.filter((pl.col("direction") == direction) & (pl.col("threshold") == threshold))
        n_trades = len(subset)
        if n_trades == 0:
            continue
        random_returns = []
        for _ in range(100):
            # Pick random entry points from all test data
            rand_rets = []
            for asset in ASSETS:
                asset_all = df.filter(pl.col("asset") == asset).sort("ts_hour")
                all_closes = asset_all["close"].to_numpy()
                all_ts = asset_all["ts_hour"].to_numpy()
                n_asset = len(subset.filter(pl.col("asset") == asset))
                for _ in range(n_asset):
                    idx = np.random.randint(0, len(all_closes) - 24)
                    if direction == "long":
                        ret = (all_closes[idx+24] - all_closes[idx]) / all_closes[idx]
                    else:
                        ret = (all_closes[idx] - all_closes[idx+24]) / all_closes[idx]
                    rand_rets.append(ret - COST_RT)
            random_returns.append(np.mean(rand_rets))
        
        strategy_avg = subset["ret"].mean()
        random_avg = np.mean(random_returns)
        edge = (strategy_avg - random_avg) * 100
        print(f"  {direction} {threshold}: strategy={strategy_avg*100:.4f}%, random={random_avg*100:.4f}%, edge={edge:.4f}%")

# === SL Testing ===
print("\n=== STOP-LOSS TESTING ===")
for sl_pct in [0, 0.03, 0.05]:
    sl_rets = []
    for trade in results:
        ret = trade["ret"]
        entry = trade["entry"]
        direction = trade["direction"]
        sl_hit = False
        # Simplified: if max adverse excursion > SL, cap loss at SL
        # We don't have intrabar data, so approximate: if return < -sl_pct, cap at -sl_pct
        if sl_pct > 0 and ret < -sl_pct:
            ret = -sl_pct
        sl_rets.append(ret)
    avg = np.mean(sl_rets) * 100
    print(f"  SL={sl_pct*100:.0f}%: avg={avg:.4f}%, n={len(sl_rets)}")

# === BINANCE COMPARISON ===
print("\n=== BINANCE 8h COMPARISON ===")
# Join bn funding with prices
bn_joined = bn.join(prices.select(["ts_hour", "asset", "close"]), on=["ts_hour", "asset"], how="inner")
print(f"BN joined: {len(bn_joined)} rows")

if len(bn_joined) > 0:
    bn_min = bn_joined["ts_hour"].min()
    bn_max = bn_joined["ts_hour"].max()
    print(f"BN range: {datetime.fromtimestamp(bn_min/1000, tz=timezone.utc)} - {datetime.fromtimestamp(bn_max/1000, tz=timezone.utc)}")
    
    # Use overlapping period only
    overlap_start = max(min_ts, bn_min)
    overlap_end = min(max_ts, bn_max)
    
    # For BN, use a single window (data is only ~1 year)
    bn_train = bn_joined.filter((pl.col("ts_hour") >= overlap_start) & (pl.col("ts_hour") < overlap_start + train_ms))
    bn_test = bn_joined.filter((pl.col("ts_hour") >= overlap_start + train_ms) & (pl.col("ts_hour") < overlap_end))
    
    if len(bn_train) > 0 and len(bn_test) > 0:
        bn_pctls = bn_train.group_by("asset").agg([
            pl.col("funding_rate").quantile(0.10).alias("p10"),
            pl.col("funding_rate").quantile(0.90).alias("p90"),
        ])
        
        bn_trades = []
        for asset in ASSETS:
            p_row = bn_pctls.filter(pl.col("asset") == asset)
            if len(p_row) == 0:
                continue
            p10_val = p_row["p10"][0]
            p90_val = p_row["p90"][0]
            
            asset_bn = bn_test.filter(pl.col("asset") == asset).sort("ts_hour")
            for row in asset_bn.iter_rows(named=True):
                fr = row["funding_rate"]
                close = row["close"]
                ts = row["ts_hour"]
                
                # BN funding is 8h, hold 24h = 3 funding periods
                if fr < p10_val:
                    target_ts = ts + 24 * 3_600_000
                    future = asset_bn.filter(pl.col("ts_hour") == target_ts)
                    if len(future) > 0:
                        entry = close
                        exit_price = future["close"][0]
                        gross_ret = (exit_price - entry) / entry
                        funding_pnl = -fr * 24  # 8h rate * 3 periods approx
                        net_ret = gross_ret - COST_RT + funding_pnl
                        bn_trades.append({"asset": asset, "direction": "long", "threshold": "P10", "ret": net_ret})
                
                if fr > p90_val:
                    target_ts = ts + 24 * 3_600_000
                    future = asset_bn.filter(pl.col("ts_hour") == target_ts)
                    if len(future) > 0:
                        entry = close
                        exit_price = future["close"][0]
                        gross_ret = (entry - exit_price) / entry
                        funding_pnl = -fr * 24
                        net_ret = gross_ret - COST_RT + funding_pnl
                        bn_trades.append({"asset": asset, "direction": "short", "threshold": "P90", "ret": net_ret})
        
        if len(bn_trades) > 0:
            bn_df = pl.DataFrame(bn_trades)
            for direction in ["long", "short"]:
                sub = bn_df.filter(pl.col("direction") == direction)
                if len(sub) > 0:
                    print(f"  BN {direction} P{'10' if direction=='long' else '90'}: avg={sub['ret'].mean()*100:.4f}%, n={len(sub)}")
        else:
            print("  No BN trades found")
    else:
        print("  No overlapping BN data for walk-forward")
else:
    print("  No BN data available")

# === KILL CRITERIA ===
print("\n=== KILL CRITERIA ===")
long_avg = trades_df.filter(pl.col("direction") == "long")["ret"].mean() if len(trades_df.filter(pl.col("direction") == "long")) > 0 else 0
short_avg = trades_df.filter(pl.col("direction") == "short")["ret"].mean() if len(trades_df.filter(pl.col("direction") == "short")) > 0 else 0
# Annualize: avg return per trade * ~365 trades/year (if daily)
annualized_edge = max(long_avg, short_avg) * 365 * 100
print(f"  Edge > 0.3% annualized: {'PASS' if annualized_edge > 0.3 else 'FAIL'} ({annualized_edge:.2f}%)")

# Window consistency
long_by_window = trades_df.filter(pl.col("direction") == "long").group_by("window").agg(pl.col("ret").mean())
profitable_windows = sum(1 for r in long_by_window.iter_rows() if r[1] > 0)
total_windows = len(long_by_window)
print(f"  Consistent across windows: {'PASS' if profitable_windows >= total_windows * 0.6 else 'FAIL'} ({profitable_windows}/{total_windows} profitable)")

hl_direction = "Long" if long_avg > short_avg else ("Short" if short_avg > long_avg else "Neither")
print(f"  HL direction: {hl_direction}")
print(f"  Long avg: {long_avg*100:.4f}%, Short avg: {short_avg*100:.4f}%")

# Save results
output = {
    "total_trades": len(results),
    "long_avg_return": float(long_avg),
    "short_avg_return": float(short_avg),
    "trades_sample": results[:100],
}
with open("research/funding_hl_full_wf_results.json", "w") as f:
    json.dump(output, f, indent=2, default=str)
print(f"\nResults saved to research/funding_hl_full_wf_results.json")