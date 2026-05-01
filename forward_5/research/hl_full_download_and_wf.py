#!/usr/bin/env python3
"""Complete HL funding + price download, merge, and walk-forward test."""

import json, time, os
import requests
import polars as pl
import numpy as np
from datetime import datetime, timezone

DATA_DIR = "/data/.openclaw/workspace/forward_v5/forward_5/data_collector/data"
RESEARCH_DIR = "/data/.openclaw/workspace/forward_v5/forward_5/research"
ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
HL_API = "https://api.hyperliquid.xyz/info"

def download_funding():
    """Download ALL available funding: earliest chunk + recent chunk to maximize coverage."""
    print("=== Downloading HL Funding History ===")
    all_records = []
    
    # Two passes per asset: earliest possible + recent (mid-2025 onward)
    starts = [1700000000000, 1750000000000]  # Nov 2023, Jun 2025
    
    for asset in ASSETS:
        print(f"  {asset}...")
        asset_records = []
        seen_ts = set()
        
        for start_time in starts:
            cursor = start_time
            while True:
                try:
                    resp = requests.post(HL_API, json={"type": "fundingHistory", "coin": asset, "startTime": cursor}, timeout=30)
                    data = resp.json()
                except Exception as e:
                    print(f"    Error: {e}")
                    break
                
                if not data:
                    break
                
                for rec in data:
                    ts = rec.get("time", rec.get("ts", 0))
                    if ts not in seen_ts:
                        seen_ts.add(ts)
                        asset_records.append({
                            "timestamp": ts,
                            "asset": asset,
                            "funding_rate": float(rec.get("fundingRate", 0)),
                            "premium": float(rec.get("premium", 0)),
                        })
                
                print(f"    Pass start={start_time}: got {len(data)}, total unique: {len(asset_records)}")
                
                if len(data) < 500:
                    break
                cursor = data[-1].get("time", data[-1].get("ts", 0)) + 1
                if len(asset_records) >= 10500:
                    break
                time.sleep(0.25)
        
        print(f"  {asset}: {len(asset_records)} records")
        all_records.extend(asset_records)
    
    df = pl.DataFrame(all_records).unique(subset=["timestamp", "asset"]).sort(["asset", "timestamp"])
    df.write_parquet(f"{DATA_DIR}/hl_funding_full.parquet")
    print(f"Saved {len(df)} total records")
    print(f"  Range: {datetime.fromtimestamp(df['timestamp'].min()/1000, tz=timezone.utc)} to {datetime.fromtimestamp(df['timestamp'].max()/1000, tz=timezone.utc)}")
    return df

def download_prices():
    """Download 1h candles covering the funding range."""
    print("\n=== Downloading HL Price History ===")
    all_candles = []
    seen = set()
    
    # Multiple start points to cover the full range
    starts = [1700000000000, 1730000000000, 1750000000000]
    
    for asset in ASSETS:
        print(f"  {asset}...")
        asset_candles = []
        seen_ts = set()
        
        for start_time in starts:
            cursor = start_time
            while True:
                try:
                    resp = requests.post(HL_API, json={
                        "type": "candleSnapshot",
                        "req": {"coin": asset, "interval": "1h", "startTime": cursor}
                    }, timeout=30)
                    data = resp.json()
                except Exception as e:
                    print(f"    Error: {e}")
                    break
                
                if not data:
                    break
                
                for c in data:
                    ts = int(c["t"])
                    if ts not in seen_ts:
                        seen_ts.add(ts)
                        asset_candles.append({
                            "timestamp": ts,
                            "asset": asset,
                            "open": float(c["o"]),
                            "high": float(c["h"]),
                            "low": float(c["l"]),
                            "close": float(c["c"]),
                            "volume": float(c["v"]),
                        })
                
                print(f"    Pass start={start_time}: got {len(data)}, total unique: {len(asset_candles)}")
                
                if len(data) < 500:
                    break
                cursor = int(data[-1]["T"]) + 1
                time.sleep(0.25)
        
        print(f"  {asset}: {len(asset_candles)} candles")
        all_candles.extend(asset_candles)
    
    if not all_candles:
        print("  ERROR: No price data!")
        return None
    
    df = pl.DataFrame(all_candles).unique(subset=["timestamp", "asset"]).sort(["asset", "timestamp"])
    df.write_parquet(f"{DATA_DIR}/prices_hl_1h.parquet")
    print(f"Saved {len(df)} candles")
    print(f"  Range: {datetime.fromtimestamp(df['timestamp'].min()/1000, tz=timezone.utc)} to {datetime.fromtimestamp(df['timestamp'].max()/1000, tz=timezone.utc)}")
    return df

def merge_funding():
    print("\n=== Merging Funding Data ===")
    full_df = pl.read_parquet(f"{DATA_DIR}/hl_funding_full.parquet")
    
    try:
        coll_df = pl.read_parquet(f"{DATA_DIR}/hl_funding.parquet")
        print(f"  Collector: {len(coll_df)} records")
        
        # Convert collector timestamp to Int64 ms
        if coll_df["timestamp"].dtype.is_datetime():
            coll_df = coll_df.with_columns(
                (pl.col("timestamp").dt.timestamp("ms")).alias("timestamp")
            )
        else:
            coll_df = coll_df.with_columns(pl.col("timestamp").cast(pl.Int64))
        
        # Ensure same columns
        cols = ["timestamp", "asset", "funding_rate", "premium"]
        full_sel = full_df.select(cols)
        coll_sel = coll_df.select(cols)
        
        combined = pl.concat([full_sel, coll_sel])
        combined = combined.unique(subset=["timestamp", "asset"]).sort(["asset", "timestamp"])
        print(f"  Combined: {len(combined)} (was {len(full_df)} + {len(coll_df)})")
        combined.write_parquet(f"{DATA_DIR}/hl_funding_full.parquet")
        return combined
    except Exception as e:
        print(f"  Merge error: {e}")
        return full_df

def walk_forward(funding_df, price_df):
    print("\n=== Walk-Forward Test ===")
    
    funding = funding_df.with_columns((pl.col("timestamp") / 3_600_000).cast(pl.Int64).alias("hour_bucket"))
    prices = price_df.with_columns((pl.col("timestamp") / 3_600_000).cast(pl.Int64).alias("hour_bucket"))
    prices_small = prices.select(["hour_bucket", "asset", "close"]).rename({"close": "price_close"})
    
    data = funding.join(prices_small, on=["hour_bucket", "asset"], how="left")
    
    has_prices = data["price_close"].null_count() < len(data)
    print(f"  Rows with prices: {len(data) - data['price_close'].null_count()}/{len(data)}")
    
    if not has_prices:
        # Filter to only rows with prices
        data_with_prices = data.drop_nulls("price_close")
        if len(data_with_prices) < 100:
            print("  ERROR: Almost no overlapping data!")
            return None
        print(f"  Using {len(data_with_prices)} rows with price data")
        data = data_with_prices
    
    # EMA50 per asset
    ema_records = []
    for asset in ASSETS:
        ad = data.filter(pl.col("asset") == asset).sort("timestamp").drop_nulls("price_close")
        if len(ad) < 100:
            continue
        closes = ad["price_close"].to_numpy()
        ts = ad["timestamp"].to_numpy()
        alpha = 2 / 51
        ema = np.empty(len(closes))
        ema[0] = closes[0]
        for i in range(1, len(closes)):
            ema[i] = alpha * closes[i] + (1 - alpha) * ema[i-1]
        ema_records.append(pl.DataFrame({"timestamp": ts, "asset": asset, "ema50": ema}))
    
    if ema_records:
        data = data.join(pl.concat(ema_records), on=["timestamp", "asset"], how="left")
    else:
        print("  No EMA data possible")
        return None
    
    min_ts = data["timestamp"].min()
    max_ts = data["timestamp"].max()
    total_hours = (max_ts - min_ts) / 3_600_000
    total_weeks = total_hours / 168
    print(f"  Span: {total_weeks:.1f} weeks")
    print(f"  From: {datetime.fromtimestamp(min_ts/1000, tz=timezone.utc)}")
    print(f"  To: {datetime.fromtimestamp(max_ts/1000, tz=timezone.utc)}")
    
    window_hours = 10 * 168
    train_hours = 5 * 168
    test_hours = 5 * 168
    n_windows = min(int(total_hours // window_hours), 10)
    if n_windows < 3:
        print(f"  Only {n_windows} windows - using all available")
    print(f"  {n_windows} non-overlapping windows (5w train + 5w test)")
    
    strategies = [
        ("Long_P10_24h", "long", 10, 24),
        ("Short_P90_24h", "short", 90, 24),
        ("Long_P05_24h", "long", 5, 24),
        ("Short_P95_24h", "short", 95, 24),
    ]
    sl_levels = [None, 0.03, 0.05]
    regime_modes = ["always", "bull_only", "bear_only"]
    costs_rt = 0.001
    
    results = {}
    
    # Pre-sort data by asset+timestamp for faster lookups
    for strat_name, direction, percentile, hold_hours in strategies:
        for sl in sl_levels:
            for regime in regime_modes:
                config_key = f"{strat_name}_sl{sl}_regime-{regime}"
                window_results = []
                
                for w in range(n_windows):
                    w_start = min_ts + w * window_hours * 3_600_000
                    train_start = w_start
                    train_end = w_start + train_hours * 3_600_000
                    test_start = train_end
                    test_end = test_start + test_hours * 3_600_000
                    
                    train_data = data.filter((pl.col("timestamp") >= train_start) & (pl.col("timestamp") < train_end))
                    test_data = data.filter((pl.col("timestamp") >= test_start) & (pl.col("timestamp") < test_end))
                    
                    thresholds = {}
                    for asset in ASSETS:
                        at = train_data.filter(pl.col("asset") == asset)
                        if len(at) < 10:
                            continue
                        thresholds[asset] = np.percentile(at["funding_rate"].to_numpy(), percentile)
                    
                    trades = []
                    for asset in ASSETS:
                        if asset not in thresholds:
                            continue
                        at = test_data.filter(pl.col("asset") == asset).sort("timestamp")
                        if len(at) < hold_hours + 1:
                            continue
                        
                        ts_arr = at["timestamp"].to_numpy()
                        fr_arr = at["funding_rate"].to_numpy()
                        pc_arr = at["price_close"].to_numpy()
                        ema_arr = at["ema50"].to_numpy()
                        threshold = thresholds[asset]
                        
                        for i in range(len(ts_arr) - hold_hours):
                            if regime == "bull_only" and (np.isnan(pc_arr[i]) or np.isnan(ema_arr[i]) or pc_arr[i] < ema_arr[i]):
                                continue
                            if regime == "bear_only" and (np.isnan(pc_arr[i]) or np.isnan(ema_arr[i]) or pc_arr[i] >= ema_arr[i]):
                                continue
                            
                            signal = (direction == "long" and fr_arr[i] < threshold) or (direction == "short" and fr_arr[i] > threshold)
                            if not signal:
                                continue
                            
                            if np.isnan(pc_arr[i]) or np.isnan(pc_arr[i + hold_hours]):
                                continue
                            
                            ep, xp = pc_arr[i], pc_arr[i + hold_hours]
                            raw_ret = (xp - ep) / ep if direction == "long" else (ep - xp) / ep
                            fund_pay = np.sum(fr_arr[i:i + hold_hours]) * (1 if direction == "long" else -1)
                            
                            sl_hit = False
                            if sl is not None:
                                for j in range(i, i + hold_hours):
                                    if np.isnan(pc_arr[j]):
                                        continue
                                    pct = (pc_arr[j] - ep) / ep
                                    if direction == "long" and pct < -sl:
                                        sl_hit = True; raw_ret = -sl; break
                                    elif direction == "short" and pct > sl:
                                        sl_hit = True; raw_ret = -sl; break
                            
                            net_ret = raw_ret + fund_pay - costs_rt
                            trades.append(net_ret)
                    
                    n = len(trades)
                    if n > 0:
                        arr = np.array(trades)
                        window_results.append({
                            "window": w, "n_trades": n,
                            "mean_net_return": float(arr.mean()),
                            "total_net_return": float(arr.sum()),
                            "win_rate": float((arr > 0).mean()),
                        })
                    else:
                        window_results.append({"window": w, "n_trades": 0, "mean_net_return": 0, "total_net_return": 0, "win_rate": 0})
                
                total_trades = sum(r["n_trades"] for r in window_results)
                total_ret = sum(r["total_net_return"] for r in window_results)
                consistent = sum(1 for r in window_results if r["total_net_return"] > 0)
                ann = total_ret * (52 / (n_windows * 5)) if n_windows > 0 else 0
                
                results[config_key] = {
                    "total_trades": total_trades,
                    "total_net_return": float(total_ret),
                    "annualized_return": float(ann),
                    "consistent_windows": consistent,
                    "total_windows": n_windows,
                    "consistency_pct": float(consistent / n_windows * 100),
                    "per_window": window_results,
                }
                print(f"  {config_key}: trades={total_trades}, total={total_ret:.4f}, ann={ann:.4f}, consistency={consistent}/{n_windows}")
    
    # Random baselines
    print("\n  Random baselines...")
    for direction in ["long", "short"]:
        rand_totals = []
        for _ in range(100):
            it_ret = 0
            for w in range(n_windows):
                w_start = min_ts + w * window_hours * 3_600_000
                test_s = w_start + train_hours * 3_600_000
                test_e = test_s + test_hours * 3_600_000
                td = data.filter((pl.col("timestamp") >= test_s) & (pl.col("timestamp") < test_e))
                for asset in ASSETS:
                    at = td.filter(pl.col("asset") == asset).sort("timestamp").drop_nulls("price_close")
                    if len(at) < 34:
                        continue
                    pc = at["price_close"].to_numpy()
                    n_pick = min(10, len(pc) - 24)
                    if n_pick <= 0:
                        continue
                    indices = np.random.choice(len(pc) - 24, size=n_pick, replace=False)
                    for idx in indices:
                        ret = (pc[idx+24] - pc[idx]) / pc[idx] if direction == "long" else (pc[idx] - pc[idx+24]) / pc[idx]
                        it_ret += ret - costs_rt
            rand_totals.append(it_ret)
        
        rm = np.mean(rand_totals)
        ra = rm * (52 / (n_windows * 5))
        results[f"random_{direction}_24h"] = {"mean_total_return": float(rm), "annualized": float(ra)}
        print(f"  random_{direction}: mean={rm:.4f}, ann={ra:.4f}")
    
    # Kill criterion
    cfgs = {k: v for k, v in results.items() if "annualized_return" in v and v.get("total_trades", 0) > 20}
    if cfgs:
        best = max(v["annualized_return"] for v in cfgs.values())
        kill = "PASS" if best > 0.003 else "FAIL"
    else:
        best = 0; kill = "FAIL"
    print(f"\n  KILL CRITERION: best ann={best:.4f} → {kill}")
    
    long_anns = [v["annualized_return"] for k, v in results.items() if "annualized_return" in v and "Long" in k and v.get("total_trades", 0) > 20]
    short_anns = [v["annualized_return"] for k, v in results.items() if "annualized_return" in v and "Short" in k and v.get("total_trades", 0) > 20]
    la = np.mean(long_anns) if long_anns else 0
    sa = np.mean(short_anns) if short_anns else 0
    print(f"  Long avg: {la:.4f}, Short avg: {sa:.4f}")
    print(f"  Both work: {'YES' if la > 0.001 and sa > 0.001 else 'NO'}")
    
    results["meta"] = {
        "n_windows": n_windows, "total_weeks": total_weeks,
        "kill_criterion": kill, "best_annualized": float(best),
        "long_avg_annualized": float(la), "short_avg_annualized": float(sa),
        "both_directions": bool(la > 0.001 and sa > 0.001),
    }
    
    out = f"{RESEARCH_DIR}/funding_hl_full_wf_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to {out}")
    return results

if __name__ == "__main__":
    np.random.seed(42)
    
    # Step 1: Download full funding (with recent pass)
    funding_path = f"{DATA_DIR}/hl_funding_full.parquet"
    if os.path.exists(funding_path):
        # Re-download to get recent data too
        funding_df = download_funding()
    else:
        funding_df = download_funding()
    
    # Step 2: Download prices (with multiple start points)
    price_path = f"{DATA_DIR}/prices_hl_1h.parquet"
    if os.path.exists(price_path):
        price_df = pl.read_parquet(price_path)
        print(f"Loaded {len(price_df)} existing price candles")
        # Re-download to get broader coverage
        price_df = download_prices()
    else:
        price_df = download_prices()
    
    if price_df is None:
        print("FATAL: No price data")
        exit(1)
    
    # Step 3: Merge
    funding_df = merge_funding()
    
    # Step 4: WF test
    results = walk_forward(funding_df, price_df)
    
    print("\n=== DONE ===")