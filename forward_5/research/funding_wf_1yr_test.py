"""Walk-Forward test for Funding Rate strategy — 1 year, 10 non-overlapping windows."""
import json
import polars as pl
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path("/data/.openclaw/workspace/forward_v5/forward_5/data_collector/data")
OUT_DIR = Path("/data/.openclaw/workspace/forward_v5/forward_5/research")

# ── Load data ──────────────────────────────────────────────────────────
print("Loading data...")
df_fund = pl.read_parquet(DATA_DIR / "bn_funding_1yr.parquet")
df_price = pl.read_parquet(DATA_DIR / "prices_8h.parquet")

# Round funding timestamps to 8h boundaries for join
EIGHT_H_MS = 8 * 3600 * 1000
df_fund = df_fund.with_columns(
    (pl.col("timestamp") // EIGHT_H_MS * EIGHT_H_MS).alias("ts8h")
)
df_price = df_price.with_columns(
    (pl.col("timestamp") // EIGHT_H_MS * EIGHT_H_MS).alias("ts8h")
)

# Join funding + price
df = df_fund.join(
    df_price.select(["ts8h", "asset", "open", "high", "low", "close", "volume"]),
    on=["ts8h", "asset"],
    how="inner"
).sort(["asset", "ts8h"])

print(f"Joined data: {len(df)} rows, assets: {df['asset'].unique().to_list()}")

# ── Walk-Forward Setup ─────────────────────────────────────────────────
WINDOW_WEEKS = 10  # 5 train + 5 test
WEEK_MS = 7 * 24 * 3600 * 1000
WINDOW_MS = WINDOW_WEEKS * WEEK_MS
TRAIN_WEEKS = 5
TRAIN_MS = TRAIN_WEEKS * WEEK_MS

ASSETS = df["asset"].unique().to_list()
PERCENTILES = [5, 10, 25, 50, 75, 90, 95]
HOLD_PERIODS = {"8h": 1, "24h": 3, "48h": 6}  # number of 8h bars
SL_PCT = 3.0  # stop loss %
COST_FEE = 0.04  # maker entry+exit %
COST_SLIP = 0.06  # slippage entry+exit %

# Time range
ts_min = df["ts8h"].min()
ts_max = df["ts8h"].max()

# Build non-overlapping windows
windows = []
cursor = ts_min
win_id = 0
while cursor + WINDOW_MS <= ts_max + EIGHT_H_MS:  # allow slight overflow
    train_start = cursor
    train_end = cursor + TRAIN_MS
    test_start = train_end
    test_end = cursor + WINDOW_MS
    windows.append({
        "win_id": win_id,
        "train_start": train_start,
        "train_end": train_end,
        "test_start": test_start,
        "test_end": test_end,
    })
    win_id += 1
    cursor += WINDOW_MS  # non-overlapping!

print(f"Time range: {datetime.fromtimestamp(ts_min/1000)} to {datetime.fromtimestamp(ts_max/1000)}")
print(f"Walk-Forward windows: {len(windows)}")
for w in windows:
    print(f"  W{w['win_id']}: train {datetime.fromtimestamp(w['train_start']/1000).date()} - {datetime.fromtimestamp(w['train_end']/1000).date()}, "
          f"test {datetime.fromtimestamp(w['test_start']/1000).date()} - {datetime.fromtimestamp(w['test_end']/1000).date()}")

# ── Core strategy logic ────────────────────────────────────────────────
def compute_percentiles(train_df: pl.DataFrame, asset: str) -> dict:
    """Compute funding rate percentiles per asset from training data."""
    asset_train = train_df.filter(pl.col("asset") == asset)
    rates = asset_train["funding_rate"].to_numpy()
    if len(rates) < 10:
        return {}
    return {f"P{p}": float(np.percentile(rates, p)) for p in PERCENTILES}

def simulate_trades(test_df: pl.DataFrame, asset: str, pctls: dict,
                    direction: str, threshold_key: str, hold_bars: int,
                    train_fund_rates: np.ndarray) -> list:
    """Simulate trades for a single asset in a test period."""
    asset_test = test_df.filter(pl.col("asset") == asset).sort("ts8h")
    if len(asset_test) == 0:
        return []
    
    rows = asset_test.to_dicts()
    threshold = pctls.get(threshold_key)
    if threshold is None:
        return []
    
    trades = []
    i = 0
    while i < len(rows) - hold_bars:
        row = rows[i]
        fr = row["funding_rate"]
        
        # Check entry condition
        enter = False
        if direction == "long" and fr < threshold:
            enter = True
        elif direction == "short" and fr > threshold:
            enter = True
        
        if not enter:
            i += 1
            continue
        
        entry_price = row["close"]
        # Simulate hold with stop loss
        hit_sl = False
        exit_price = None
        exit_bar = None
        
        for h in range(1, hold_bars + 1):
            if i + h >= len(rows):
                break
            bar = rows[i + h]
            # Check stop loss
            if direction == "long":
                if bar["low"] < entry_price * (1 - SL_PCT / 100):
                    hit_sl = True
                    exit_price = entry_price * (1 - SL_PCT / 100)
                    exit_bar = i + h
                    break
            else:  # short
                if bar["high"] > entry_price * (1 + SL_PCT / 100):
                    hit_sl = True
                    exit_price = entry_price * (1 + SL_PCT / 100)
                    exit_bar = i + h
                    break
        
        if exit_price is None:
            # Hold to end of period
            if i + hold_bars < len(rows):
                exit_price = rows[i + hold_bars]["close"]
                exit_bar = i + hold_bars
            else:
                i += 1
                continue
        
        # Calculate return
        if direction == "long":
            raw_return = (exit_price - entry_price) / entry_price
        else:
            raw_return = (entry_price - exit_price) / entry_price
        
        # Funding cost/benefit
        # For longs: pay funding if positive, receive if negative
        # For shorts: receive funding if positive, pay if negative
        funding_payment = 0.0
        for h in range(hold_bars):
            if i + h < len(rows):
                fr_h = rows[i + h]["funding_rate"]
                if direction == "long":
                    funding_payment += fr_h  # long pays positive, receives negative
                else:
                    funding_payment -= fr_h  # short receives positive, pays negative
        
        # Net cost = fee + slippage - funding_benefit
        # For longs with negative funding: funding is a benefit (reduces cost)
        # funding_payment is positive = cost, negative = benefit for longs
        total_cost_pct = (COST_FEE + COST_SLIP) / 100
        
        net_return = raw_return - total_cost_pct
        # Adjust for funding: longs benefit from negative funding
        # funding_payment > 0 means we paid more, < 0 means we received
        net_return -= funding_payment  # if we paid funding, subtract; if received, add (subtract negative)
        
        trades.append({
            "raw_return": raw_return,
            "net_return": net_return,
            "funding_payment": funding_payment,
            "hit_sl": hit_sl,
            "entry_time": row["ts8h"],
            "exit_time": rows[exit_bar]["ts8h"] if exit_bar else row["ts8h"],
        })
        
        i += hold_bars  # skip ahead (non-overlapping trades)
    
    return trades

def random_baseline(test_df: pl.DataFrame, asset: str, n_trades: int,
                    hold_bars: int, n_iter: int = 100) -> float:
    """Generate random baseline with same trade frequency."""
    asset_test = test_df.filter(pl.col("asset") == asset).sort("ts8h")
    if len(asset_test) == 0 or n_trades == 0:
        return 0.0
    
    rows = asset_test.to_dicts()
    total_cost_pct = (COST_FEE + COST_SLIP) / 100
    
    all_returns = []
    for _ in range(n_iter):
        # Random entry points
        valid_starts = list(range(len(rows) - hold_bars))
        if len(valid_starts) == 0:
            continue
        indices = np.random.choice(valid_starts, size=min(n_trades, len(valid_starts)), replace=False)
        indices.sort()
        
        iter_returns = []
        for idx in indices:
            entry_price = rows[idx]["close"]
            exit_idx = min(idx + hold_bars, len(rows) - 1)
            exit_price = rows[exit_idx]["close"]
            raw_ret = (exit_price - entry_price) / entry_price
            net_ret = raw_ret - total_cost_pct
            iter_returns.append(net_ret)
        
        if iter_returns:
            all_returns.append(np.mean(iter_returns))
    
    return float(np.mean(all_returns)) if all_returns else 0.0

# ── Run Walk-Forward ───────────────────────────────────────────────────
print("\n" + "="*80)
print("WALK-FORWARD TEST: Funding Rate Strategy (1 Year)")
print("="*80)

all_results = []
regime_results = []

for w in windows:
    print(f"\n--- Window {w['win_id']} ---")
    train_df = df.filter((pl.col("ts8h") >= w["train_start"]) & (pl.col("ts8h") < w["train_end"]))
    test_df = df.filter((pl.col("ts8h") >= w["test_start"]) & (pl.col("ts8h") < w["test_end"]))
    
    for asset in ASSETS:
        pctls = compute_percentiles(train_df, asset)
        if not pctls:
            continue
        
        train_fund = train_df.filter(pl.col("asset") == asset)["funding_rate"].to_numpy()
        
        # Test configurations: (direction, threshold_key, hold_label, hold_bars)
        configs = []
        for hold_label, hold_bars in HOLD_PERIODS.items():
            configs.append(("long", "P10", hold_label, hold_bars))
            configs.append(("long", "P05", hold_label, hold_bars))
            configs.append(("short", "P90", hold_label, hold_bars))
            configs.append(("short", "P95", hold_label, hold_bars))
        
        for direction, threshold_key, hold_label, hold_bars in configs:
            trades = simulate_trades(test_df, asset, pctls, direction, threshold_key, hold_bars, train_fund)
            if not trades:
                continue
            
            n_trades = len(trades)
            win_rate = sum(1 for t in trades if t["net_return"] > 0) / n_trades
            avg_ret = np.mean([t["net_return"] for t in trades])
            total_oos = sum(t["net_return"] for t in trades)
            avg_funding = np.mean([t["funding_payment"] for t in trades])
            sl_rate = sum(1 for t in trades if t["hit_sl"]) / n_trades
            
            # Random baseline
            rand_avg = random_baseline(test_df, asset, n_trades, hold_bars)
            
            # Determine quarter for regime analysis
            test_start_dt = datetime.fromtimestamp(w["test_start"] / 1000)
            quarter = f"Q{(test_start_dt.month - 1) // 3 + 1} {test_start_dt.year}"
            
            result = {
                "window": w["win_id"],
                "asset": asset,
                "direction": direction,
                "threshold": threshold_key,
                "hold": hold_label,
                "n_trades": n_trades,
                "win_rate": round(win_rate, 4),
                "avg_net_return": round(avg_ret, 6),
                "total_oos_return": round(total_oos, 6),
                "avg_funding_payment": round(avg_funding, 6),
                "sl_rate": round(sl_rate, 4),
                "random_avg_return": round(rand_avg, 6),
                "edge_vs_random": round(avg_ret - rand_avg, 6),
                "quarter": quarter,
                "train_start": w["train_start"],
                "test_start": w["test_start"],
            }
            all_results.append(result)
            regime_results.append(result)
            
            if n_trades >= 3:
                print(f"  {asset} {direction} {threshold_key} {hold_label}: "
                      f"n={n_trades} win={win_rate:.1%} avg={avg_ret:.4%} vs_rand={avg_ret-rand_avg:.4%} sl={sl_rate:.1%}")

# ── Summary Tables ─────────────────────────────────────────────────────
print("\n" + "="*80)
print("AGGREGATE RESULTS BY CONFIGURATION")
print("="*80)

# Group by (direction, threshold, hold)
from collections import defaultdict
groups = defaultdict(list)
for r in all_results:
    key = (r["direction"], r["threshold"], r["hold"])
    groups[key].append(r)

print(f"\n{'Config':<25} {'Trades':>6} {'Win%':>7} {'Avg Net%':>10} {'vs Rand%':>10} {'SL%':>6} {'W≥5':>4}")
print("-" * 75)
for key in sorted(groups.keys()):
    direction, threshold, hold = key
    results = groups[key]
    total_trades = sum(r["n_trades"] for r in results)
    weighted_wins = sum(r["win_rate"] * r["n_trades"] for r in results) / max(total_trades, 1)
    avg_ret = np.mean([r["avg_net_return"] for r in results])
    avg_edge = np.mean([r["edge_vs_random"] for r in results])
    avg_sl = np.mean([r["sl_rate"] for r in results])
    sufficient = sum(1 for r in results if r["n_trades"] >= 5)
    
    label = f"{direction} {threshold} {hold}"
    print(f"{label:<25} {total_trades:>6} {weighted_wins:>6.1%} {avg_ret:>9.4%} {avg_edge:>9.4%} {avg_sl:>5.1%} {sufficient:>4}")

# Per-asset summary
print(f"\n{'Asset':>8} {'Config':<25} {'Trades':>6} {'Win%':>7} {'Avg Net%':>10} {'vs Rand%':>10}")
print("-" * 75)
for asset in ASSETS:
    for key in sorted(groups.keys()):
        direction, threshold, hold = key
        results = [r for r in groups[key] if r["asset"] == asset]
        if not results:
            continue
        total_trades = sum(r["n_trades"] for r in results)
        avg_ret = np.mean([r["avg_net_return"] for r in results])
        avg_edge = np.mean([r["edge_vs_random"] for r in results])
        label = f"{direction} {threshold} {hold}"
        print(f"{asset:>8} {label:<25} {total_trades:>6} {np.mean([r['win_rate'] for r in results]):>6.1%} {avg_ret:>9.4%} {avg_edge:>9.4%}")

# ── Regime Analysis ───────────────────────────────────────────────────
print("\n" + "="*80)
print("REGIME ANALYSIS (Per Quarter)")
print("="*80)

quarter_groups = defaultdict(list)
for r in regime_results:
    quarter_groups[r["quarter"]].append(r)

print(f"\n{'Quarter':<12} {'Config':<25} {'Trades':>6} {'Avg Net%':>10} {'vs Rand%':>10}")
print("-" * 60)
for q in sorted(quarter_groups.keys()):
    qresults = quarter_groups[q]
    # Overall per quarter
    total_trades = sum(r["n_trades"] for r in qresults)
    avg_ret = np.mean([r["avg_net_return"] for r in qresults])
    avg_edge = np.mean([r["edge_vs_random"] for r in qresults])
    print(f"{q:<12} {'ALL':<25} {total_trades:>6} {avg_ret:>9.4%} {avg_edge:>9.4%}")
    
    # Per config
    cfg_groups = defaultdict(list)
    for r in qresults:
        cfg_groups[(r["direction"], r["threshold"], r["hold"])].append(r)
    for key in sorted(cfg_groups.keys()):
        direction, threshold, hold = key
        cfg_results = cfg_groups[key]
        t = sum(r["n_trades"] for r in cfg_results)
        ret = np.mean([r["avg_net_return"] for r in cfg_results])
        edge = np.mean([r["edge_vs_random"] for r in cfg_results])
        label = f"  {direction} {threshold} {hold}"
        if t > 0:
            print(f"{'':12} {label:<25} {t:>6} {ret:>9.4%} {edge:>9.4%}")

# ── Kill Criterion ────────────────────────────────────────────────────
print("\n" + "="*80)
print("KILL CRITERION CHECK")
print("="*80)

# Best configs
best_configs = []
for key in sorted(groups.keys()):
    results = groups[key]
    avg_edge = np.mean([r["edge_vs_random"] for r in results])
    total_trades = sum(r["n_trades"] for r in results)
    avg_ret = np.mean([r["avg_net_return"] for r in results])
    # Annualized: avg per-trade * estimated trades per year
    # ~3 funding periods/day * 365 = ~1095 entries/year, but only P10 triggers
    # Rough: trades per window * 10 windows/year
    trades_per_year = total_trades  # already ~1 year of data
    annualized_edge = avg_ret * (total_trades / max(len(results), 1)) if total_trades > 0 else 0
    
    direction, threshold, hold = key
    best_configs.append({
        "config": f"{direction} {threshold} {hold}",
        "avg_net_return": avg_ret,
        "avg_edge_vs_random": avg_edge,
        "total_trades": total_trades,
        "annualized_approx": annualized_edge,
    })

best_configs.sort(key=lambda x: x["avg_edge_vs_random"], reverse=True)
print(f"\n{'Config':<25} {'Avg Net%':>10} {'vs Rand%':>10} {'Trades':>7} {'Ann.Edge':>10}")
print("-" * 65)
for bc in best_configs[:15]:
    print(f"{bc['config']:<25} {bc['avg_net_return']:>9.4%} {bc['avg_edge_vs_random']:>9.4%} {bc['total_trades']:>7} {bc['annualized_approx']:>9.4%}")

# Kill criterion: is net edge > 0.3% annualized?
top_edge = best_configs[0]["annualized_approx"] if best_configs else 0
print(f"\nKill Criterion: Net edge annualized > 0.3%?")
print(f"  Top config annualized edge: {top_edge:.4%}")
print(f"  Result: {'✅ PASS — Edge survives' if top_edge > 0.003 else '❌ FAIL — Edge too thin'}")

# ── Data Quality ──────────────────────────────────────────────────────
print("\n" + "="*80)
print("DATA QUALITY")
print("="*80)
sufficient_windows = sum(1 for r in all_results if r["n_trades"] >= 5)
total_configs = len(all_results)
print(f"Total (asset,window,config) combos: {total_configs}")
print(f"Combos with ≥5 trades: {sufficient_windows} ({sufficient_windows/max(total_configs,1):.1%})")

# ── Save Results ───────────────────────────────────────────────────────
output = {
    "all_results": all_results,
    "best_configs": best_configs,
    "kill_criterion": {
        "top_annualized_edge": top_edge,
        "threshold": 0.003,
        "pass": top_edge > 0.003,
    },
    "data_quality": {
        "total_combos": total_configs,
        "sufficient_trades": sufficient_windows,
    },
}
with open(OUT_DIR / "funding_wf_1yr_results.json", "w") as f:
    json.dump(output, f, indent=2, default=str)
print(f"\nResults saved to {OUT_DIR / 'funding_wf_1yr_results.json'}")