#!/usr/bin/env python3
"""
Walk-Forward Validation for V17 (Mean_Reversion_BB)

Tests V17's FIXED parameters across multiple time windows.
No parameter optimization — pure OOS robustness check.

Concept:
- Split data into rolling windows (e.g. 5 windows)
- Each window: run V17 with fixed params on train+OOS
- OOS must be profitable AND not degrade >50% vs IS
- Score: % of windows where OOS is profitable + consistency

Usage:
    python3 run_walk_forward.py
    python3 run_walk_forward.py --assets BTC ETH SOL
    python3 run_walk_forward.py --windows 5
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict

import polars as pl
import numpy as np

# Add parent dirs to path
RESEARCH_DIR = Path(__file__).parent
sys.path.insert(0, str(RESEARCH_DIR))
sys.path.insert(0, str(RESEARCH_DIR / "backtest"))

from backtest.backtest_engine import BacktestEngine
from strategy_lab.mean_reversion_bb import (
    mean_reversion_bb_strategy,
    get_default_params,
    get_v17_exit_config,
)

# Paper trading assets
ALL_ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
DATA_DIR = RESEARCH_DIR / "data"
OUTPUT_DIR = RESEARCH_DIR / "runs" / "walk_forward"


def load_asset_data(symbol: str, timeframe: str = "1h") -> pl.DataFrame:
    """Load data, preferring _full version (more history)."""
    # Try _full first (20k+ rows), then short version
    for suffix in [f"_{timeframe}_full.parquet", f"_{timeframe}.parquet"]:
        path = DATA_DIR / f"{symbol}{suffix}"
        if path.exists():
            return pl.read_parquet(path)
    raise FileNotFoundError(f"No data for {symbol}")


def run_v17_on_window(df: pl.DataFrame, params: dict, exit_config: dict) -> dict:
    """Run V17 strategy on a DataFrame slice and return key metrics."""
    engine = BacktestEngine(data_path=str(DATA_DIR))
    result = engine.run(
        strategy_name="V17_WF",
        strategy_func=mean_reversion_bb_strategy,
        params=params,
        symbol="BTCUSDT",  # dummy — df is provided directly
        timeframe="1h",
        exit_config=exit_config,
        df=df,
    )
    return {
        "net_return": round(result.net_return, 4),
        "trade_count": result.trade_count,
        "max_drawdown": round(result.max_drawdown, 4),
        "profit_factor": round(result.profit_factor, 4),
        "win_rate": round(result.win_rate, 2),
    }


def run_walk_forward(assets: list = None, n_windows: int = 5):
    """Walk-Forward with FIXED V17 parameters — no optimization."""

    if assets is None:
        assets = ALL_ASSETS

    print("=" * 70)
    print("WALK-FORWARD VALIDATION — V17 (FIXED PARAMS)")
    print(f"Entry:  close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200")
    print(f"Exit:   Trail 1.5%, SL 3.0%, MaxHold 36h")
    print(f"Assets: {assets}")
    print(f"Windows: {n_windows}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    params = get_default_params()
    exit_config = get_v17_exit_config()

    results = {}
    passed_count = 0
    total_count = 0

    for asset in assets:
        symbol = f"{asset}USDT"
        print(f"\n{'='*50}")
        print(f"📊 {symbol}")
        print(f"{'='*50}")

        try:
            df = load_asset_data(symbol)
        except FileNotFoundError as e:
            print(f"⚠️  {e}, skipping")
            continue

        n_rows = len(df)
        print(f"  Data: {n_rows:,} rows ({n_rows/24/30:.1f} months)")

        window_size = n_rows // n_windows
        oos_pct = 0.3  # Last 30% of each window = OOS

        is_metrics = []
        oos_metrics = []

        for i in range(n_windows):
            start = i * window_size
            end = min(start + window_size, n_rows)
            train_end = start + int(window_size * (1 - oos_pct))

            train_df = df[start:train_end]
            oos_df = df[train_end:end]

            if len(train_df) < 100 or len(oos_df) < 50:
                print(f"  Window {i+1}: too small ({len(train_df)}/{len(oos_df)}), skipping")
                continue

            is_r = run_v17_on_window(train_df, params, exit_config)
            oos_r = run_v17_on_window(oos_df, params, exit_config)

            # Degradation
            if is_r["net_return"] != 0:
                degradation = (is_r["net_return"] - oos_r["net_return"]) / max(abs(is_r["net_return"]), 0.01)
            else:
                degradation = -1.0 if oos_r["net_return"] < 0 else 0.0

            print(f"  W{i+1}: IS={is_r['net_return']:+.2f}% ({is_r['trade_count']}T) | "
                  f"OOS={oos_r['net_return']:+.2f}% ({oos_r['trade_count']}T) | "
                  f"Deg={degradation*100:.0f}%")

            is_metrics.append(is_r)
            oos_metrics.append({
                **oos_r,
                "degradation": round(degradation, 4),
                "window": i + 1,
            })

        if not oos_metrics:
            print(f"  ⚠️  No valid windows for {symbol}")
            continue

        # Robustness scoring
        n = len(oos_metrics)
        oos_profitable = sum(1 for m in oos_metrics if m["net_return"] > 0)
        low_degradation = sum(1 for m in oos_metrics if m["degradation"] < 0.5)
        all_same_dir = len(set(1 if m["net_return"] > 0 else -1 for m in oos_metrics)) == 1

        score = (oos_profitable / n * 40) + (low_degradation / n * 40) + (10 if all_same_dir else 0)
        score = min(100.0, round(score, 1))

        # Minimum trade filter
        avg_trades = np.mean([m["trade_count"] for m in oos_metrics])
        if avg_trades < 3:
            score = min(score, 30)  # Cap if too few trades in OOS
            print(f"  ⚠️  Low trade count in OOS (avg {avg_trades:.1f}), capping score")

        passed = score >= 50  # ≥50 = pass
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"\n  {status} — Robustness: {score}/100 "
              f"(OOS profitable: {oos_profitable}/{n}, Low deg: {low_degradation}/{n})")

        results[asset] = {
            "robustness_score": score,
            "passed": passed,
            "oos_profitable": oos_profitable,
            "oos_total": n,
            "avg_oos_return": round(np.mean([m["net_return"] for m in oos_metrics]), 4),
            "avg_trades_oos": round(avg_trades, 1),
            "windows": oos_metrics,
        }

        if passed:
            passed_count += 1
        total_count += 1

    # Summary
    print(f"\n{'='*70}")
    print(f"WALK-FORWARD SUMMARY — V17 (FIXED PARAMS)")
    print(f"{'='*70}")
    for asset, r in results.items():
        s = "✅" if r["passed"] else "❌"
        print(f"  {asset}: {r['robustness_score']:.0f}/100 {s} "
              f"(OOS {r['avg_oos_return']:+.2f}%, {r['avg_trades_oos']:.0f} trades)")

    overall_pass = passed_count >= total_count * 0.5
    print(f"\nOverall: {'✅ PASS' if overall_pass else '⚠️ WEAK'} "
          f"({passed_count}/{total_count} assets ≥50 robustness)")

    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"wf_v17_{timestamp}.json"

    summary = {
        "strategy": "V17_MeanReversion_BB",
        "entry": "close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200",
        "exit": exit_config,
        "params": params,
        "timestamp": timestamp,
        "n_windows": n_windows,
        "oos_pct": 0.3,
        "passed_assets": passed_count,
        "total_assets": total_count,
        "overall_pass": overall_pass,
        "assets": results,
    }

    with open(output_file, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n💾 Results saved to: {output_file}")

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Walk-Forward Validation for V17")
    parser.add_argument("--assets", nargs="+", default=None, help="Assets to test")
    parser.add_argument("--windows", type=int, default=5, help="Number of walk-forward windows")
    args = parser.parse_args()

    run_walk_forward(assets=args.assets, n_windows=args.windows)