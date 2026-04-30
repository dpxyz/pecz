#!/usr/bin/env python3
"""Walk-forward test: Does Funding Rate alone have predictive power?"""

import json
import random
from pathlib import Path
import polars as pl
import numpy as np

random.seed(42)
np.random.seed(42)

DATA_DIR = Path(__file__).parent.parent / "data_collector" / "data"
OUTPUT_PATH = Path(__file__).parent / "funding_standalone_results.json"

# --- Config ---
TRAIN_DAYS = 6
TEST_DAYS = 6
N_WINDOWS = 10
HOLD_HOURS = [4, 8, 24]
STOP_LOSS = 0.03
LONG_PERCENTILES = [10, 5, 1]   # funding < threshold → go long
SHORT_PERCENTILES = [90, 95, 99] # funding > threshold → go short
MIN_TRADES = 5
N_RANDOM_SAMPLES = 1000

def load_data():
    funding = pl.read_parquet(DATA_DIR / "hl_funding.parquet")
    prices = pl.read_parquet(DATA_DIR / "prices_1h.parquet")
    
    # Truncate timestamps to hour for join
    funding = funding.with_columns(
        ts=pl.col("timestamp").dt.truncate("1h")
    ).drop("timestamp").rename({"ts": "timestamp"})
    prices = prices.with_columns(
        ts=pl.col("timestamp").dt.truncate("1h")
    ).drop("timestamp").rename({"ts": "timestamp"})
    
    # Join
    df = funding.join(prices, on=["timestamp", "asset"], how="inner")
    df = df.sort(["asset", "timestamp"])
    return df

def get_windows(df):
    """Generate walk-forward windows."""
    from datetime import datetime, timezone, timedelta
    base = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    windows = []
    for i in range(N_WINDOWS):
        train_start = base + timedelta(days=TRAIN_DAYS * i)
        train_end = train_start + timedelta(days=TRAIN_DAYS)
        test_start = train_end
        test_end = test_start + timedelta(days=TEST_DAYS)
        windows.append((train_start, train_end, test_start, test_end))
    return windows

def calc_thresholds(train_df, asset):
    """Calculate per-asset percentile thresholds from training data."""
    asset_data = train_df.filter(pl.col("asset") == asset)
    fr = asset_data["funding_rate"].to_numpy()
    if len(fr) < 10:
        return None, None
    long_thresh = {p: np.percentile(fr, p) for p in LONG_PERCENTILES}
    short_thresh = {p: np.percentile(fr, p) for p in SHORT_PERCENTILES}
    return long_thresh, short_thresh

def simulate_trades(test_df, asset, threshold, direction, hold_hours):
    """Simulate trades for one (asset, threshold, direction, hold_period)."""
    asset_data = test_df.filter(pl.col("asset") == asset).sort("timestamp")
    if len(asset_data) == 0:
        return []
    
    ts = asset_data["timestamp"].to_numpy()
    closes = asset_data["close"].to_numpy()
    funding = asset_data["funding_rate"].to_numpy()
    
    trades = []
    for i in range(len(ts)):
        if direction == "long":
            signal = funding[i] < threshold
        else:
            signal = funding[i] > threshold
        
        if not signal:
            continue
        
        entry_price = closes[i]
        entry_idx = i
        
        # Find exit: hold_hours bars later, or stop loss hit
        exit_idx = min(i + hold_hours, len(closes) - 1)
        stopped = False
        for j in range(i + 1, exit_idx + 1):
            if direction == "long":
                if closes[j] < entry_price * (1 - STOP_LOSS):
                    exit_idx = j
                    stopped = True
                    break
            else:
                if closes[j] > entry_price * (1 + STOP_LOSS):
                    exit_idx = j
                    stopped = True
                    break
        
        exit_price = closes[exit_idx]
        if direction == "long":
            ret = (exit_price - entry_price) / entry_price
        else:
            ret = (entry_price - exit_price) / entry_price
        
        trades.append(ret)
    
    return trades

def calc_metrics(trades):
    if not trades or len(trades) < MIN_TRADES:
        return None
    arr = np.array(trades)
    n = len(arr)
    wins = (arr > 0).sum()
    win_rate = wins / n
    avg_ret = arr.mean()
    total_ret = arr.sum()
    # Sharpe (annualized, assuming ~8760h/year)
    if arr.std() > 0:
        sharpe = (avg_ret / arr.std()) * np.sqrt(8760 / 1)  # per-trade, rough
    else:
        sharpe = 0.0
    # Max drawdown of cumulative returns
    cum = np.cumsum(arr)
    running_max = np.maximum.accumulate(cum)
    dd = running_max - cum
    max_dd = dd.max() if len(dd) > 0 else 0.0
    return {
        "trades": n,
        "win_rate": float(win_rate),
        "avg_return": float(avg_ret),
        "total_return": float(total_ret),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_dd),
    }

def random_baseline(test_df, asset, hold_hours, n_trades, n_samples=N_RANDOM_SAMPLES):
    """Generate random entry baseline."""
    asset_data = test_df.filter(pl.col("asset") == asset).sort("timestamp")
    if len(asset_data) == 0:
        return 0.0
    closes = asset_data["close"].to_numpy()
    max_entry = len(closes) - hold_hours - 1
    if max_entry <= 0 or n_trades <= 0:
        return 0.0
    
    random_returns = []
    for _ in range(n_samples):
        indices = random.sample(range(max_entry), min(n_trades, max_entry))
        rets = []
        for i in indices:
            entry = closes[i]
            exit_idx = min(i + hold_hours, len(closes) - 1)
            exit_p = closes[exit_idx]
            # Check stop loss
            for j in range(i + 1, exit_idx + 1):
                if closes[j] < entry * (1 - STOP_LOSS):
                    exit_p = entry * (1 - STOP_LOSS)
                    break
            rets.append((exit_p - entry) / entry)
        random_returns.append(np.mean(rets))
    return float(np.mean(random_returns))

def buy_and_hold(test_df, asset):
    """Buy and hold return for the test period."""
    asset_data = test_df.filter(pl.col("asset") == asset).sort("timestamp")
    if len(asset_data) < 2:
        return 0.0
    closes = asset_data["close"].to_numpy()
    return float((closes[-1] - closes[0]) / closes[0])

def main():
    print("Loading data...")
    df = load_data()
    assets = df["asset"].unique().sort().to_list()
    print(f"Assets: {assets}")
    print(f"Data range: {df['timestamp'].min()} - {df['timestamp'].max()}")
    print(f"Total rows: {len(df)}")
    
    windows = get_windows(df)
    
    # Aggregate results across windows
    results = {}  # key = (asset, direction, percentile, hold_hours)
    
    for w_idx, (train_start, train_end, test_start, test_end) in enumerate(windows):
        print(f"\n--- Window {w_idx+1}/{N_WINDOWS} ---")
        print(f"  Train: {train_start} - {train_end}")
        print(f"  Test:  {test_start} - {test_end}")
        
        train_df = df.filter(
            (pl.col("timestamp") >= train_start) & (pl.col("timestamp") < train_end)
        )
        test_df = df.filter(
            (pl.col("timestamp") >= test_start) & (pl.col("timestamp") < test_end)
        )
        
        for asset in assets:
            long_thresh, short_thresh = calc_thresholds(train_df, asset)
            if long_thresh is None:
                continue
            
            # Long entries
            for p, thresh in long_thresh.items():
                for hold in HOLD_HOURS:
                    trades = simulate_trades(test_df, asset, thresh, "long", hold)
                    key = (asset, "long", p, hold)
                    if key not in results:
                        results[key] = {"trades_all": [], "window_trades": {}}
                    results[key]["trades_all"].extend(trades)
                    results[key]["window_trades"][w_idx] = len(trades)
            
            # Short entries
            for p, thresh in short_thresh.items():
                for hold in HOLD_HOURS:
                    trades = simulate_trades(test_df, asset, thresh, "short", hold)
                    key = (asset, "short", p, hold)
                    if key not in results:
                        results[key] = {"trades_all": [], "window_trades": {}}
                    results[key]["trades_all"].extend(trades)
                    results[key]["window_trades"][w_idx] = len(trades)
    
    # Calculate metrics and baselines
    print("\n\n=== FUNDING RATE STANDALONE WALK-FORWARD RESULTS ===\n")
    
    output_results = []
    
    # We need test_df per window for baselines — recompute per asset globally
    # For random baseline, use full test period
    from datetime import datetime, timezone
    test_cutoff = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    full_test = df.filter(pl.col("timestamp") >= test_cutoff)
    
    for direction in ["long", "short"]:
        if direction == "long":
            print("LONG ENTRIES (Funding < threshold → go long, exit after hold period)")
            percentiles = LONG_PERCENTILES
        else:
            print("SHORT ENTRIES (Funding > threshold → go short, exit after hold period)")
            percentiles = SHORT_PERCENTILES
        
        header = f"{'Asset':<6} | {'Thresh':<6} | {'Hold':<4} | {'Trades':>6} | {'Win%':>5} | {'Avg Ret':>8} | {'OOS Tot':>8} | {'vs Rand':>8} | {'vs Hold':>8}"
        print(header)
        print("-" * len(header))
        
        for asset in assets:
            hold_ret = buy_and_hold(full_test, asset)
            
            for p in percentiles:
                for hold in HOLD_HOURS:
                    key = (asset, direction, p, hold)
                    if key not in results:
                        continue
                    all_trades = results[key]["trades_all"]
                    metrics = calc_metrics(all_trades)
                    if metrics is None:
                        n_trades = len(all_trades)
                        print(f"{asset:<6} | P{p:<4} | {hold}h   | {n_trades:>6} |   INSUFFICIENT DATA (needs {MIN_TRADES})")
                        continue
                    
                    # Random baseline
                    rand_avg = random_baseline(full_test, asset, hold, metrics["trades"])
                    vs_random = metrics["avg_return"] - rand_avg
                    vs_hold = metrics["total_return"] - hold_ret
                    
                    print(f"{asset:<6} | P{p:<4} | {hold}h   | {metrics['trades']:>6} | {metrics['win_rate']*100:>4.1f}% | {metrics['avg_return']*100:>+7.3f}% | {metrics['total_return']*100:>+7.3f}% | {vs_random*100:>+7.3f}% | {vs_hold*100:>+7.3f}%")
                    
                    output_results.append({
                        "asset": asset,
                        "direction": direction,
                        "threshold_percentile": p,
                        "hold_hours": hold,
                        "trades": metrics["trades"],
                        "win_rate": metrics["win_rate"],
                        "avg_return": metrics["avg_return"],
                        "total_return": metrics["total_return"],
                        "sharpe": metrics["sharpe"],
                        "max_drawdown": metrics["max_drawdown"],
                        "vs_random": vs_random,
                        "vs_hold": vs_hold,
                        "window_trades": results[key]["window_trades"],
                    })
        print()
    
    # Summary
    long_vs_random = [r["vs_random"] for r in output_results if r["direction"] == "long"]
    short_vs_random = [r["vs_random"] for r in output_results if r["direction"] == "short"]
    
    long_avg_improvement = np.mean(long_vs_random) if long_vs_random else 0
    short_avg_improvement = np.mean(short_vs_random) if short_vs_random else 0
    
    long_pass = long_avg_improvement > 0.001  # >0.1% avg improvement
    short_pass = short_avg_improvement > 0.001
    
    print("SUMMARY: Does Funding Rate have standalone predictive power?")
    print(f"- Long at low funding: {'PASS' if long_pass else 'FAIL'} — average improvement vs random: {long_avg_improvement*100:+.3f}%")
    print(f"- Short at high funding: {'PASS' if short_pass else 'FAIL'} — average improvement vs random: {short_avg_improvement*100:+.3f}%")
    
    # Correlation check: funding rate vs subsequent return
    corr_results = {}
    for asset in assets:
        asset_data = full_test.filter(pl.col("asset") == asset).sort("timestamp")
        fr = asset_data["funding_rate"].to_numpy()
        closes = asset_data["close"].to_numpy()
        if len(fr) < 24:
            continue
        # 4h forward return
        fwd4 = np.array([(closes[i+4] - closes[i])/closes[i] if i+4 < len(closes) else np.nan for i in range(len(closes))])
        valid = ~(np.isnan(fr) | np.isnan(fwd4))
        if valid.sum() > 10:
            corr = np.corrcoef(fr[valid], fwd4[valid])[0, 1]
            corr_results[asset] = corr
            print(f"  Correlation(funding, 4h-fwd-return) {asset}: {corr:.4f}")
    
    avg_corr = np.mean(list(corr_results.values())) if corr_results else 0
    kill_pass = abs(avg_corr) > 0.05
    print(f"- Kill criterion (|correlation| > 0.05): {'PASS' if kill_pass else 'FAIL'} (avg |corr| = {abs(avg_corr):.4f})")
    
    # Save
    output = {
        "results": output_results,
        "summary": {
            "long_pass": long_pass,
            "short_pass": short_pass,
            "long_avg_vs_random": float(long_avg_improvement),
            "short_avg_vs_random": float(short_avg_improvement),
            "avg_correlation": float(avg_corr),
            "kill_criterion_pass": kill_pass,
            "correlations": corr_results,
        }
    }
    
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()