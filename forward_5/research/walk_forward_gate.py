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


# ─── Strategy Function Builder ───────────────────────────────────────

# Known native strategies — always parseable, high-fidelity
NATIVE_STRATEGIES = {
    "close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200": "mean_reversion_bb",
}

# Only these indicator types can be parsed by the DSL parser
SIMPLE_INDICATORS = {'close', 'open', 'high', 'low', 'volume'}
SIMPLE_PREFIXES = ['bb_lower_', 'bb_upper_', 'bb_width_', 'bb_mid_', 'rsi_', 'ema_', 'sma_', 'zscore_']
# Complex indicators: macd, adx, atr, stochastic, z-score → NEEDS_MANUAL_REVIEW


def build_strategy_func(entry_condition: str):
    """
    Build a strategy function from a DSL entry condition string.
    Returns (strategy_func, parseable_bool) tuple.
    
    Native strategies use their Python implementation.
    Simple DSL (BB, RSI, EMA, SMA) gets parsed automatically.
    Complex DSL (MACD, ADX, etc.) → NEEDS_MANUAL_REVIEW.
    """
    import re

    # 1) Native strategies: exact match → use Python implementation
    native_name = NATIVE_STRATEGIES.get(entry_condition.strip())
    if native_name == "mean_reversion_bb":
        from strategy_lab.mean_reversion_bb import mean_reversion_bb_strategy
        return mean_reversion_bb_strategy, True

    # 2) Check if entry uses only simple (parseable) indicators
    cond_lower = entry_condition.lower()
    tokens = re.findall(r'[a-z_]+\d*', cond_lower)
    for t in tokens:
        if t in ('and', 'or', 'not', '') or t in SIMPLE_INDICATORS:
            continue
        if any(t.startswith(p) for p in SIMPLE_PREFIXES):
            continue
        # Unknown/complex indicator → cannot parse reliably
        return None, False

    # 3) Simple DSL parser (BB, RSI, EMA, SMA, ZScore, bb_width)
    def strategy_func(df: pl.DataFrame, params: dict) -> pl.DataFrame:
        indicators = {}

        # BB bands: bb_lower_N, bb_upper_N, bb_width_N, bb_mid_N
        for m in re.finditer(r'bb_(lower|upper|mid|width)_(\d+)', entry_condition):
            kind = m.group(1)
            period = int(m.group(2))
            key = m.group(0)
            if f'bb_upper_{period}' not in indicators:
                sma = pl.col('close').rolling_mean(window_size=period, min_periods=period)
                std = pl.col('close').rolling_std(window_size=period, min_periods=period)
                indicators[f'bb_upper_{period}'] = sma + 2.0 * std
                indicators[f'bb_lower_{period}'] = sma - 2.0 * std
                indicators[f'bb_mid_{period}'] = sma
                indicators[f'bb_width_{period}'] = (4.0 * std) / pl.when(sma == 0).then(0.001).otherwise(sma)

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

        # ZScore: zscore_N
        for m in re.finditer(r'zscore_(\d+)', entry_condition):
            period = int(m.group(1))
            key = f'zscore_{period}'
            if key not in indicators:
                sma = pl.col('close').rolling_mean(window_size=period, min_periods=period)
                std = pl.col('close').rolling_std(window_size=period, min_periods=period)
                indicators[key] = (pl.col('close') - sma) / pl.when(std == 0).then(0.001).otherwise(std)

        # EMA/SMA: ema_N, sma_N
        for m in re.finditer(r'(ema|sma)_(\d+)', entry_condition):
            kind = m.group(1)
            period = int(m.group(2))
            key = f'{kind}_{period}'
            if key not in indicators:
                indicators[key] = pl.col('close').rolling_mean(window_size=period, min_periods=period)

        # Add all indicators as columns
        df = df.with_columns([v.alias(k) for k, v in indicators.items()])

        # Build signal: split AND conditions, evaluate each as boolean, combine
        conditions = [c.strip() for c in entry_condition.split(' AND ')]
        signal = pl.lit(True)
        for cond in conditions:
            signal = signal & _parse_simple_condition(cond)
        df = df.with_columns((pl.when(signal).then(1).otherwise(0)).alias('signal'))

        return df

    return strategy_func, True


def _parse_simple_condition(cond: str):
    """Parse a single comparison like 'close < bb_lower_20' into a Polars boolean expression."""
    for op in ['<=', '>=', '!=', '==', '<', '>']:
        if op in cond:
            parts = cond.split(op, 1)
            left = _parse_value(parts[0].strip())
            right = _parse_value(parts[1].strip())
            if op == '<=': return left <= right
            if op == '>=': return left >= right
            if op == '!=': return left != right
            if op == '==': return left == right
            if op == '<': return left < right
            if op == '>': return left > right
    return pl.lit(False)


def _parse_value(val: str):
    """Parse a value reference into a Polars expression."""
    val = val.strip()
    try:
        return pl.lit(float(val))
    except ValueError:
        return pl.col(val)


# ─── Walk-Forward Runner ──────────────────────────────────────────────

def run_wf_on_candidate(name: str, entry: str, exit_config: dict,
                          n_windows: int = 5, oos_pct: float = 0.3) -> dict:
    """Run Walk-Forward validation for a candidate strategy."""
    
    strategy_func, parseable = build_strategy_func(entry)
    
    if not parseable or strategy_func is None:
        # Cannot parse this strategy — mark as NEEDS_MANUAL_REVIEW
        return {
            "name": name,
            "entry": entry,
            "exit_config": exit_config,
            "robustness_score": 0.0,
            "passed": False,
            "profitable_assets": "0/0",
            "avg_oos_return": 0.0,
            "avg_trades": 0.0,
            "assets": {},
            "n_windows": n_windows,
            "timestamp": datetime.now().isoformat(),
            "wf_status": "NEEDS_MANUAL_REVIEW",
            "wf_reason": f"DSL parser cannot handle: {entry[:80]}",
            "is_score": 0.0,
            "tier": "needs_review",
        }
    
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
            profitable_windows = sum(1 for m in oos_metrics if m["net_return"] > 0)
            avg_return = np.mean([m["net_return"] for m in oos_metrics])
            avg_trades = np.mean([m["trade_count"] for m in oos_metrics])
            avg_dd = np.mean([m["max_drawdown"] for m in oos_metrics])
            results[asset] = {
                "avg_oos_return": round(avg_return, 4),
                "avg_trades": round(avg_trades, 1),
                "avg_drawdown": round(avg_dd, 4),
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
    wf_status = "PASS" if passed else "FAIL"

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
        "wf_status": wf_status,
        "is_score": 0.0,
        "tier": "overfitted",  # will be overwritten by caller
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Walk-Forward Gate for Strategy Candidates")
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
        # Validate all HOF entries + V17 benchmark
        with open(args.hof) as f:
            data = json.load(f)
        
        hof = data.get("hall_of_fame", data if isinstance(data, list) else [])
        
        # Always include V17 benchmark in WF validation
        V17 = {
            "name": "V17_Mid_Target_Exit",
            "entry_condition": "close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200",
            "exit_config": {"trailing_stop_pct": 1.5, "stop_loss_pct": 3.0, "max_hold_bars": 36},
            "score": 4.88,
        }
        
        # Check if V17 is already in HOF
        v17_in_hof = any(e.get("name") == "V17_Mid_Target_Exit" for e in hof)
        if not v17_in_hof:
            hof.insert(0, V17)  # Always test V17
        
        results = []
        for entry in hof:
            is_score = entry.get("score", 0)
            print(f"\n🔍 Validating: {entry['name']} (IS-Score: {is_score})")
            result = run_wf_on_candidate(
                entry["name"],
                entry.get("entry", entry.get("entry_condition", "")),
                entry.get("exit_config", entry.get("exit_rule", {})),
                n_windows=args.windows,
            )
            result["is_score"] = is_score
            # Tier assignment: WF result only, IS is just context
            if result.get("wf_status") == "NEEDS_MANUAL_REVIEW":
                result["tier"] = "needs_review"
            elif result["passed"]:
                result["tier"] = "wf_passed"  # sorted later by robustness_score
            else:
                result["tier"] = "overfitted"
            
            tier = result["tier"]
            status = "✅ PASS" if result["passed"] else ("⚠️ REVIEW" if result.get("wf_status") == "NEEDS_MANUAL_REVIEW" else "❌ FAIL")
            print(f"  {status} [{tier.upper()}] — Robustness: {result['robustness_score']}/100 "
                  f"(OOS: {result['avg_oos_return']:+.2f}%, {result['profitable_assets']} profitable)")
            results.append(result)
        
        # Sort WF-passed by robustness_score (best first)
        wf_passed = sorted(
            [r for r in results if r["passed"]],
            key=lambda r: r["robustness_score"], reverse=True
        )
        # Best WF-passed = Champion, rest = Robust
        if len(wf_passed) >= 1:
            wf_passed[0]["tier"] = "champion"  # best robustness = champion
            for r in wf_passed[1:]:
                r["tier"] = "robust"  # other WF-passed = robust
        needs_review = [r for r in results if r.get("wf_status") == "NEEDS_MANUAL_REVIEW"]
        overfitted = [r for r in results if not r["passed"] and r.get("wf_status") != "NEEDS_MANUAL_REVIEW"]
        
        print(f"\n{'='*50}")
        print(f"WF GATE SUMMARY: {len(wf_passed)}/{len(results)} passed")
        if needs_review:
            print(f"📋 NEEDS MANUAL REVIEW: {len(needs_review)} strategies")
            for r in needs_review:
                print(f"   {r['name']}: {r.get('wf_reason', 'complex DSL')}")
        if wf_passed:
            print(f"🎉 CHAMPION (best WF-robustness):")
            print(f"   {wf_passed[0]['name']}: WF={wf_passed[0]['robustness_score']}/100, "
                  f"IS={wf_passed[0]['is_score']:.2f}, OOS={wf_passed[0]['avg_oos_return']:+.2f}%")
            if len(wf_passed) > 1:
                print(f"✅ ROBUST (WF-passed, ranked):")
                for r in wf_passed[1:]:
                    print(f"   {r['name']}: WF={r['robustness_score']}/100, IS={r['is_score']:.2f}")
        else:
            print(f"⚠️  No WF-passed candidates. All overfitted.")
        print(f"❌ OVERFITTED: {len(overfitted)}")
        
        # Save
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = OUTPUT_DIR / f"wf_gate_{timestamp}.json"
        with open(out_file, 'w') as f:
            json.dump({"timestamp": timestamp, "results": results, "v17_always_tested": True}, f, indent=2, default=str)
        print(f"\n💾 Saved to {out_file}")
    else:
        parser.print_help()