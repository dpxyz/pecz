#!/usr/bin/env python3
"""
Walk-Forward Gate for Evolution Candidates

Runs Walk-Forward validation on a candidate strategy.
Used as a quality gate: only candidates that pass WF enter the Hall of Fame.

Usage:
    python3 walk_forward_gate.py --candidate <json_file_or_string>
    python3 walk_forward_gate.py --hof <json_file>   # validate all HOF entries
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

import polars as pl
import numpy as np

RESEARCH_DIR = Path(__file__).parent
sys.path.insert(0, str(RESEARCH_DIR))
sys.path.insert(0, str(RESEARCH_DIR / "backtest"))

from backtest.backtest_engine import BacktestEngine

ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
SYMBOLS = [f"{a}USDT" for a in ASSETS]
DATA_DIR = RESEARCH_DIR / "data"
OUTPUT_DIR = RESEARCH_DIR / "runs" / "walk_forward"


def load_asset_data(symbol: str, timeframe: str = "1h") -> pl.DataFrame:
    """Load data, preferring _full version."""
    for suffix in [f"_{timeframe}_full.parquet", f"_{timeframe}.parquet"]:
        path = DATA_DIR / f"{symbol}{suffix}"
        if path.exists():
            return pl.read_parquet(path)
    raise FileNotFoundError(f"No data for {symbol}")


def build_strategy_func(entry_condition: str):
    """
    Build a strategy function from a DSL entry condition string.
    Uses the strategy_lab module for known strategies, falls back to DSL parser.
    """
    import re

    # Known strategies: use their native implementations
    V17_ENTRY = "close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200"
    
    if entry_condition.strip() == V17_ENTRY:
        from strategy_lab.mean_reversion_bb import mean_reversion_bb_strategy
        return mean_reversion_bb_strategy

    # Generic DSL parser for unknown strategies
    def strategy_func(df: pl.DataFrame, params: dict) -> pl.DataFrame:
        # Compute indicators based on entry condition
        # Parse all referenced indicators
        indicators = {}

        # BB bands: bb_lower_N, bb_upper_N
        for m in re.finditer(r'bb_(lower|upper)_(\d+)', entry_condition):
            period = int(m.group(2))
            key = m.group(0)
            if key not in indicators:
                sma = pl.col('close').rolling_mean(window_size=period, min_periods=period)
                std = pl.col('close').rolling_std(window_size=period, min_periods=period)
                indicators[f'bb_upper_{period}'] = sma + 2.0 * std
                indicators[f'bb_lower_{period}'] = sma - 2.0 * std

        # RSI: rsi_N
        for m in re.finditer(r'rsi_(\d+)', entry_condition):
            period = int(m.group(1))
            key = f'rsi_{period}'
            if key not in indicators:
                delta = pl.col('close').diff()
                gain = pl.when(delta > 0).then(delta).otherwise(0.0)
                loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
                avg_gain = gain.rolling_mean(window_size=period, min_periods=period)
                avg_loss = loss.rolling_mean(window_size=period, min_periods=period)
                rs = avg_gain / pl.when(avg_loss == 0).then(0.0001).otherwise(avg_loss)
                indicators[key] = 100 - (100 / (1 + rs))

        # EMA/SMA: ema_N, sma_N
        for m in re.finditer(r'(ema|sma)_(\d+)', entry_condition):
            kind = m.group(1)
            period = int(m.group(2))
            key = f'{kind}_{period}'
            if key not in indicators:
                indicators[key] = pl.col('close').rolling_mean(window_size=period, min_periods=period)

        # ATR: atr_N
        for m in re.finditer(r'atr_(\d+)', entry_condition):
            period = int(m.group(1))
            key = f'atr_{period}'
            if key not in indicators:
                tr = pl.max_horizontal(
                    (pl.col('high') - pl.col('low')).abs(),
                    (pl.col('high') - pl.col('close').shift(1)).abs(),
                    (pl.col('low') - pl.col('close').shift(1)).abs(),
                )
                indicators[key] = tr.rolling_mean(window_size=period, min_periods=period)

        # Add all indicators as columns
        df = df.with_columns([
            v.alias(k) for k, v in indicators.items()
        ])

        # Build signal from entry condition
        # Replace indicator names with column references in a Polars expression
        cond_str = entry_condition
        # Map to Polars: just use column names directly
        # Simple eval: close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200
        try:
            # Build Polars expression from simple DSL
            signal = _parse_condition(cond_str)
            df = df.with_columns(signal.alias('signal'))
        except Exception:
            # Fallback: no signal
            df = df.with_columns(pl.lit(0).alias('signal'))

        return df

    return strategy_func


def _parse_condition(cond: str):
    """Parse simple DSL condition into Polars expression. Handles AND/OR."""
    cond = cond.strip()
    
    # Handle OR
    if ' OR ' in cond:
        parts = cond.split(' OR ', 1)
        left = _parse_condition(parts[0].strip())
        right = _parse_condition(parts[1].strip())
        return pl.when(left | right).then(1).otherwise(0)
    
    # Handle AND
    if ' AND ' in cond:
        parts = cond.split(' AND ', 1)
        left = _parse_condition(parts[0].strip())
        right = _parse_condition(parts[1].strip())
        return pl.when(left & right).then(1).otherwise(0)
    
    # Single comparison: a < b, a > b
    for op in ['<', '>', '<=', '>=', '==', '!=']:
        if op in cond:
            parts = cond.split(op, 1)
            left_expr = _parse_value(parts[0].strip())
            right_expr = _parse_value(parts[1].strip())
            if op == '<':
                return left_expr < right_expr
            elif op == '>':
                return left_expr > right_expr
            elif op == '<=':
                return left_expr <= right_expr
            elif op == '>=':
                return left_expr >= right_expr
            elif op == '==':
                return left_expr == right_expr
            else:
                return left_expr != right_expr
    
    return pl.lit(False)


def _parse_value(val: str):
    """Parse a value reference into a Polars expression."""
    val = val.strip()
    # Numeric literal
    try:
        return pl.lit(float(val))
    except ValueError:
        pass
    # Column reference
    return pl.col(val)


def run_wf_on_candidate(name: str, entry: str, exit_config: dict,
                          n_windows: int = 5, oos_pct: float = 0.3) -> dict:
    """Run Walk-Forward validation for a candidate strategy."""
    
    strategy_func = build_strategy_func(entry)
    results = {}
    
    for asset in ASSETS:
        symbol = f"{asset}USDT"
        try:
            df = load_asset_data(symbol)
        except FileNotFoundError:
            continue
        
        n_rows = len(df)
        window_size = n_rows // n_windows
        
        oos_metrics = []
        for i in range(n_windows):
            start = i * window_size
            end = min(start + window_size, n_rows)
            train_end = start + int(window_size * (1 - oos_pct))
            
            oos_df = df[train_end:end]
            if len(oos_df) < 50:
                continue
            
            engine = BacktestEngine(data_path=str(DATA_DIR))
            result = engine.run(
                strategy_name=f"WF_{name}",
                strategy_func=strategy_func,
                params={},
                symbol=symbol,
                timeframe="1h",
                exit_config=exit_config,
                df=oos_df,
            )
            
            oos_metrics.append({
                "window": i + 1,
                "net_return": round(result.net_return, 4),
                "trade_count": result.trade_count,
                "max_drawdown": round(result.max_drawdown, 4),
            })
        
        if oos_metrics:
            avg_return = np.mean([m["net_return"] for m in oos_metrics])
            avg_trades = np.mean([m["trade_count"] for m in oos_metrics])
            profitable_windows = sum(1 for m in oos_metrics if m["net_return"] > 0)
            
            results[asset] = {
                "avg_oos_return": round(avg_return, 4),
                "avg_trades": round(avg_trades, 1),
                "profitable_windows": f"{profitable_windows}/{len(oos_metrics)}",
                "windows": oos_metrics,
            }
    
    # Overall scoring
    assets_with_data = len(results)
    profitable_assets = sum(1 for r in results.values() if r["avg_oos_return"] > 0)
    avg_all_return = np.mean([r["avg_oos_return"] for r in results.values()]) if results else 0
    avg_all_trades = np.mean([r["avg_trades"] for r in results.values()]) if results else 0
    
    # Robustness: ≥50% assets profitable in OOS + avg trades ≥3
    robustness = 0
    if assets_with_data > 0:
        profitable_ratio = profitable_assets / assets_with_data
        robustness = profitable_ratio * 70  # max 70 from profitability
        if avg_all_trades >= 3:
            robustness += 30  # max 30 from trade count
        robustness = min(100, round(robustness, 1))
    
    passed = robustness >= 50 and profitable_assets >= 3
    
    return {
        "name": name,
        "entry": entry,
        "exit_config": exit_config,
        "robustness_score": robustness,
        "passed": passed,
        "profitable_assets": f"{profitable_assets}/{assets_with_data}",
        "avg_oos_return": round(avg_all_return, 4),
        "avg_trades": round(avg_all_trades, 1),
        "assets": results,
        "n_windows": n_windows,
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Walk-Forward Gate")
    parser.add_argument("--candidate", help="JSON string or file with {name, entry, exit_config}")
    parser.add_argument("--hof", help="JSON file with hall_of_fame to validate")
    parser.add_argument("--windows", type=int, default=5, help="Number of WF windows")
    args = parser.parse_args()
    
    if args.candidate:
        # Single candidate
        if Path(args.candidate).exists():
            with open(args.candidate) as f:
                c = json.load(f)
        else:
            c = json.loads(args.candidate)
        
        result = run_wf_on_candidate(c["name"], c["entry"], c.get("exit_config", {}), n_windows=args.windows)
        print(json.dumps(result, indent=2))
        
    elif args.hof:
        # Validate all HOF entries
        with open(args.hof) as f:
            data = json.load(f)
        
        hof = data.get("hall_of_fame", data if isinstance(data, list) else [])
        results = []
        for entry in hof:
            print(f"\n🔍 Validating: {entry['name']} (Score: {entry.get('score', '?')})")
            result = run_wf_on_candidate(
                entry["name"],
                entry.get("entry", entry.get("entry_condition", "")),
                entry.get("exit_config", entry.get("exit_rule", {})),
                n_windows=args.windows,
            )
            status = "✅ PASS" if result["passed"] else "❌ FAIL"
            print(f"  {status} — Robustness: {result['robustness_score']}/100 "
                  f"(OOS: {result['avg_oos_return']:+.2f}%, {result['profitable_assets']} profitable)")
            results.append(result)
        
        # Save
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = OUTPUT_DIR / f"wf_gate_{timestamp}.json"
        with open(out_file, 'w') as f:
            json.dump({"timestamp": timestamp, "results": results}, f, indent=2, default=str)
        print(f"\n💾 Saved to {out_file}")
    else:
        parser.print_help()