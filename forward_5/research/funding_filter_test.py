#!/usr/bin/env python3
"""
Funding Rate Filter Test — Step 1 of V2 Validation Pipeline

Tests whether skipping trade entries when funding rates are extreme
improves OOS returns of walk-forward validated strategies.

Uses fresh candle data from data_collector (2026-02-26 to 2026-04-30)
overlapping with Hyperliquid funding rate data.
"""

import sys
import json
import numpy as np
import polars as pl
import pandas as pd
from pathlib import Path
from datetime import datetime

RESEARCH_DIR = Path(__file__).parent
sys.path.insert(0, str(RESEARCH_DIR))
sys.path.insert(0, str(RESEARCH_DIR / "backtest"))

from backtest.backtest_engine import BacktestEngine
from walk_forward_gate import build_strategy_func, ASSETS

DATA_DIR = RESEARCH_DIR / "data"
COLLECTOR_DIR = RESEARCH_DIR.parent / "data_collector" / "data"

# ─── Strategies to test ──────────────────────────────────────────────

STRATEGIES = {
    "V32_MR": {
        "entry": "close < bb_lower_14 AND rsi_7 < 25 AND close > ema_50",
        "exit_config": {"trailing_stop_pct": 2.2, "stop_loss_pct": 3.0, "max_hold_bars": 18},
        "type": "MR",
    },
    "BB_RSI_MR": {
        "entry": "close < bb_lower_14 AND rsi_14 < 30",
        "exit_config": {"trailing_stop_pct": 2.0, "stop_loss_pct": 3.0, "max_hold_bars": 24},
        "type": "MR",
    },
    "EMA_Trend": {
        "entry": "close > ema_50 AND close > ema_200 AND adx_14 > 20",
        "exit_config": {"trailing_stop_pct": 2.0, "stop_loss_pct": 3.0, "max_hold_bars": 24},
        "type": "trend",
    },
}

# ─── Load data ────────────────────────────────────────────────────────

def load_candles():
    """Load 1h candles from data_collector prices_1h.parquet, return dict by asset."""
    path = COLLECTOR_DIR / "prices_1h.parquet"
    pdf = pd.read_parquet(path)
    result = {}
    for asset in ASSETS:
        asset_data = pdf[pdf["asset"] == asset].sort_values("timestamp").reset_index(drop=True)
        df = pl.DataFrame({
            "timestamp": asset_data["timestamp"].values,
            "open": asset_data["open"].values.astype(float),
            "high": asset_data["high"].values.astype(float),
            "low": asset_data["low"].values.astype(float),
            "close": asset_data["close"].values.astype(float),
            "volume": asset_data["volume"].values.astype(float),
        })
        # Add hour-rounded timestamp for funding merge
        df = df.with_columns(
            pl.col("timestamp").cast(pl.Datetime("ms")).alias("ts_ms")
        )
        result[asset] = df
    return result


def load_funding():
    """Load HL funding rates, return pandas DataFrame."""
    path = COLLECTOR_DIR / "hl_funding.parquet"
    pdf = pd.read_parquet(path)
    pdf["ts_hour"] = pd.to_datetime(pdf["timestamp"], utc=True).dt.floor("h")
    return pdf


def compute_funding_thresholds(funding_pdf):
    """Compute P10, P50, P75, P90 for each asset's funding rate."""
    stats = {}
    for asset in ASSETS:
        fr = funding_pdf[funding_pdf["asset"] == asset]["funding_rate"]
        stats[asset] = {
            "P10": float(fr.quantile(0.10)),
            "P50": float(fr.quantile(0.50)),
            "P75": float(fr.quantile(0.75)),
            "P90": float(fr.quantile(0.90)),
        }
    return stats


def build_funding_lookup(funding_pdf):
    """Build dict mapping (str hour, asset) -> funding_rate.
    Uses string keys 'YYYY-MM-DD HH:00' to avoid tz mismatches."""
    lookup = {}
    for _, row in funding_pdf.iterrows():
        ts_key = str(row["ts_hour"])[:13]  # '2026-01-30 09'
        key = (ts_key, row["asset"])
        lookup[key] = row["funding_rate"]
    return lookup


def ts_to_hour_key(ts_val):
    """Convert a timestamp to hour key string for lookup."""
    ts = pd.Timestamp(ts_val)
    if ts.tzinfo is None:
        ts = ts.tz_localize('UTC')
    return str(ts.floor('h'))[:13]  # '2026-01-30 09'


# ─── Walk-Forward with Funding Filter ─────────────────────────────────

def run_wf_with_filter(asset, all_candles, strategy_func, exit_config,
                       funding_lookup, filter_variant, threshold_stats,
                       n_windows=5, oos_pct=0.3):
    """
    Walk-forward test with funding rate filter on entry signals.
    Uses 5 windows (not 10) since we only have ~1500 bars.
    Computes indicators on full data, then evaluates OOS windows.
    """
    n_rows = len(all_candles)
    window_size = n_rows // n_windows
    
    # Compute signals on FULL data (so indicators have full warmup)
    try:
        df_full = strategy_func(all_candles, {})
    except Exception as e:
        print(f"  Warning: strategy error: {e}")
        return 0.0, 0, 0
    
    if "signal" not in df_full.columns:
        return 0.0, 0, 0
    
    oos_returns = []
    total_trades = 0
    total_skipped = 0
    
    for i in range(n_windows):
        start = i * window_size
        end = min(start + window_size, n_rows)
        train_end = start + int(window_size * (1 - oos_pct))
        
        # OOS slice from the FULL signal-computed dataframe
        oos_df = df_full.slice(train_end, end - train_end)
        if len(oos_df) < 20:
            continue
        
        # Apply funding filter: zero out signals where funding exceeds threshold
        skipped = 0
        if filter_variant and funding_lookup:
            threshold = threshold_stats[asset][filter_variant]
            signals = oos_df["signal"].to_numpy().copy()
            
            for idx in range(len(signals)):
                if signals[idx] == 1:
                    ts_val = oos_df["timestamp"][idx]
                    hour_key = ts_to_hour_key(ts_val)
                    fr = funding_lookup.get((hour_key, asset), None)
                    if fr is not None and fr > threshold:
                        signals[idx] = 0
                        skipped += 1
            
            total_skipped += skipped
            oos_df = oos_df.with_columns(
                pl.Series("signal", signals, dtype=pl.Int64)
            )
        
        # Run backtest on OOS window
        engine = BacktestEngine(data_path=str(DATA_DIR))
        
        # Create a strategy function that just returns the pre-computed signals
        def make_pass_through(oos_data):
            def pass_through(df, params):
                return oos_data
            return pass_through
        
        result = engine.run(
            strategy_name="funding_test",
            strategy_func=make_pass_through(oos_df),
            params={},
            symbol=f"{asset}USDT",
            timeframe="1h",
            exit_config=exit_config,
            df=oos_df,
        )
        
        if result.trade_count > 0 or result.net_return != 0:
            oos_returns.append(result.net_return)
        total_trades += result.trade_count
    
    avg_return = np.mean(oos_returns) if oos_returns else 0.0
    return avg_return, total_trades, total_skipped


# ─── Main ─────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("FUNDING RATE FILTER TEST — V2 Validation Step 1")
    print("=" * 70)
    
    # Load data
    print("\n[1] Loading candle data...")
    candles = load_candles()
    for asset, df in candles.items():
        print(f"  {asset}: {len(df)} bars")
    
    print("\n[2] Loading funding data...")
    funding_pdf = load_funding()
    funding_lookup = build_funding_lookup(funding_pdf)
    print(f"  {len(funding_lookup)} lookup entries")
    
    print("\n[3] Computing funding rate thresholds...")
    threshold_stats = compute_funding_thresholds(funding_pdf)
    for asset, stats in threshold_stats.items():
        print(f"  {asset}: P10={stats['P10']:.6f} P50={stats['P50']:.6f} "
              f"P75={stats['P75']:.6f} P90={stats['P90']:.6f}")
    
    # Run tests
    filter_variants = [None, "P90", "P75", "P50"]
    results = []
    
    for strat_name, strat_config in STRATEGIES.items():
        print(f"\n{'='*70}")
        print(f"Strategy: {strat_name}")
        print(f"  Entry: {strat_config['entry']}")
        print(f"  Type: {strat_config['type']}")
        
        strategy_func, parseable = build_strategy_func(
            strat_config["entry"],
            exit_condition=strat_config["exit_config"].get("exit_condition")
        )
        if not parseable:
            print(f"  SKIP: DSL cannot parse this strategy")
            continue
        
        for asset in ASSETS:
            symbol = f"{asset}USDT"
            if asset not in candles:
                continue
            
            asset_candles = candles[asset]
            print(f"\n  {asset} ({len(asset_candles)} bars):")
            
            for fv in filter_variants:
                label = fv if fv else "None"
                avg_return, trades, skipped = run_wf_with_filter(
                    asset, asset_candles, strategy_func,
                    strat_config["exit_config"], funding_lookup,
                    fv, threshold_stats
                )
                
                results.append({
                    "strategy": strat_name,
                    "asset": asset,
                    "filter": label,
                    "oos_return": round(avg_return, 6),
                    "trades": trades,
                    "skipped": skipped,
                })
                
                print(f"    Filter={label:4s}: OOS={avg_return:+.4f}% | Trades={trades:3d} | Skipped={skipped:3d}")
    
    # Save results
    out_path = RESEARCH_DIR / "funding_filter_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")
    
    # ─── Summary ──────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("SUMMARY: Strategy × Filter (averaged across assets)")
    print(f"{'='*70}")
    print(f"{'Strategy':<15} {'Filter':<6} {'OOS Return':>11} {'Trades':>7} {'Skipped':>8} {'Improvement':>12}")
    print("-" * 70)
    
    # Aggregate per strategy+filter across assets
    agg = {}
    for r in results:
        key = (r["strategy"], r["filter"])
        if key not in agg:
            agg[key] = {"returns": [], "trades": 0, "skipped": 0}
        agg[key]["returns"].append(r["oos_return"])
        agg[key]["trades"] += r["trades"]
        agg[key]["skipped"] += r["skipped"]
    
    baselines = {}
    for (strat, fv), data in agg.items():
        if fv == "None":
            baselines[strat] = np.mean(data["returns"])
    
    improvement_found = False
    for strat_name in STRATEGIES:
        baseline = baselines.get(strat_name, 0)
        for fv in [None, "P90", "P75", "P50"]:
            label = fv if fv else "None"
            key = (strat_name, label)
            if key not in agg:
                continue
            data = agg[key]
            avg_ret = np.mean(data["returns"])
            improvement = avg_ret - baseline if label != "None" else 0
            imp_str = f"{improvement:+.4f}%" if label != "None" else "baseline"
            if label != "None" and improvement >= 0.005:
                improvement_found = True
            print(f"{strat_name:<15} {label:<6} {avg_ret:>+10.4f}% {data['trades']:>7d} {data['skipped']:>8d} {imp_str:>12}")
    
    print(f"\n{'='*70}")
    if improvement_found:
        print("✅ At least one filter variant improves OOS by ≥0.5% for some strategy")
    else:
        print("❌ KILL CRITERION: No filter variant improves OOS by ≥0.5% for ANY strategy")
        print("   Funding rate filter does NOT provide meaningful improvement.")
    print(f"{'='*70}")
    
    # Also print per-asset detail for MR strategies on most promising assets
    print(f"\n{'='*70}")
    print("PER-ASSET DETAIL (MR strategies)")
    print(f"{'='*70}")
    for r in results:
        if r["strategy"] in ["V32_MR", "BB_RSI_MR"]:
            print(f"  {r['strategy']:15s} {r['asset']:5s} Filter={r['filter']:4s} "
                  f"OOS={r['oos_return']:+.4f}% Trades={r['trades']:3d} Skipped={r['skipped']:3d}")


if __name__ == "__main__":
    main()