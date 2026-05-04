#!/usr/bin/env python3
"""
Foundry V13 — Deep Funding Parameter Sweep

Systematic grid search over proven funding-based signal types.
No LLM guessing — deterministic parameter exploration on 2.5 years of data.

Data: data_v10/*.parquet (20k rows/asset, 2.5 years, 1h candles with indicators pre-computed)
"""

import json, sys, time, itertools, os
from pathlib import Path
from datetime import datetime
from copy import deepcopy

import polars as pl
import numpy as np

RESEARCH_DIR = Path(__file__).parent
sys.path.insert(0, str(RESEARCH_DIR))
sys.path.insert(0, str(RESEARCH_DIR / "backtest"))

from backtest.backtest_engine import BacktestEngine
from walk_forward_gate import build_strategy_func, load_asset_data

DATA_DIR = RESEARCH_DIR / "data_v10"
OUTPUT = RESEARCH_DIR / "funding_sweep_v13_results.json"

ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# ============================================================================
# GRID DEFINITION
# ============================================================================

# Signal types: entry conditions as DSL strings
# Each has a list of parameterized variants
SIGNAL_VARIANTS = []

# Type 1: Bear extreme (shorts pay longs)
for z in [-0.5, -0.8, -1.0, -1.2, -1.5, -2.0, -2.5]:
    SIGNAL_VARIANTS.append(("bear_extreme", f"funding_z < {z}", {"z_thresh": z}))

# Type 2: Bull pullback (negative funding in uptrend)
for z_low in [-1.5, -1.0, -0.8, -0.5, -0.3]:
    for z_high in [-0.2, -0.1, 0.0]:
        if z_low < z_high:  # valid range
            SIGNAL_VARIANTS.append(("bull_pullback",
                f"funding_z > {z_low} AND funding_z < {z_high} AND bull200 == 1",
                {"z_low": z_low, "z_high": z_high}))

# Type 3: Bull pullback + vol confirmation
for z_high in [-0.2, -0.1]:
    for z_low in [-1.0, -0.5]:
        for vol in [1.3, 1.5, 2.0]:
            SIGNAL_VARIANTS.append(("bull_pullback_vol",
                f"funding_z > {z_low} AND funding_z < {z_high} AND bull200 == 1 AND vol_ratio > {vol}",
                {"z_low": z_low, "z_high": z_high, "vol": vol}))

# Type 4: Bull50 pullback (shorter-term uptrend)
for z in [-0.2, -0.5, -0.8, -1.0]:
    SIGNAL_VARIANTS.append(("bull50_pullback",
        f"funding_z < {z} AND bull50 == 1",
        {"z_thresh": z}))

# Type 5: Squeeze + negative funding
for z in [-0.5, -0.8, -1.0, -1.5]:
    SIGNAL_VARIANTS.append(("squeeze_funding",
        f"funding_z < {z} AND squeeze == 1",
        {"z_thresh": z}))

# Type 6: Bear extreme + FGI fear
for z in [-0.8, -1.0, -1.5]:
    for fgi in [25, 30, 40]:
        SIGNAL_VARIANTS.append(("bear_fgi",
            f"funding_z < {z} AND ((d.get('fgi') or 999) < {fgi})",
            {"z_thresh": z, "fgi_thresh": fgi}))

# Type 7: Funding cross down (rate just turned negative)
SIGNAL_VARIANTS.append(("fund_cross_down", "fund_cross_down == 1 AND bull200 == 1", {}))
SIGNAL_VARIANTS.append(("fund_cross_down_bear", "fund_cross_down == 1", {}))

# Exit configurations
EXIT_CONFIGS = {
    "tight_24h":  {"trailing_stop_pct": 1.5, "stop_loss_pct": 2.5, "max_hold_bars": 24},
    "medium_24h": {"trailing_stop_pct": 2.5, "stop_loss_pct": 4.0, "max_hold_bars": 24},
    "wide_24h":   {"trailing_stop_pct": 4.0, "stop_loss_pct": 6.0, "max_hold_bars": 24},
    "hold_8h":    {"trailing_stop_pct": 2.0, "stop_loss_pct": 3.0, "max_hold_bars": 8},
    "hold_48h":   {"trailing_stop_pct": 3.0, "stop_loss_pct": 5.0, "max_hold_bars": 48},
    "hold_72h":   {"trailing_stop_pct": 4.0, "stop_loss_pct": 6.0, "max_hold_bars": 72},
    "notrail_24h": {"stop_loss_pct": 5.0, "max_hold_bars": 24},  # no trailing, just hold + SL
    "notrail_48h": {"stop_loss_pct": 5.0, "max_hold_bars": 48},
}

print(f"Signal variants: {len(SIGNAL_VARIANTS)}")
print(f"Exit configs: {len(EXIT_CONFIGS)}")
print(f"Assets: {len(ASSETS)}")
print(f"Total grid: {len(SIGNAL_VARIANTS) * len(ASSETS) * len(EXIT_CONFIGS)}")


# ============================================================================
# DATA LOADING
# ============================================================================

def load_data(symbol: str) -> pl.DataFrame:
    path = DATA_DIR / f"{symbol}_1h_full.parquet"
    if not path.exists():
        return pl.DataFrame()
    df = pl.read_parquet(path)
    # Filter infinite funding_z
    df = df.filter(pl.col("funding_z").is_finite() | pl.col("funding_z").is_null())
    return df


# ============================================================================
# BACKTEST
# ============================================================================

def run_backtest(df: pl.DataFrame, entry: str, exit_config: dict) -> dict:
    """Run single backtest. Returns metrics dict."""
    strategy_func, parseable = build_strategy_func(entry)
    if not parseable or strategy_func is None:
        return {"error": "unparseable", "net_return": -999, "trade_count": 0}

    try:
        engine = BacktestEngine(data_path=str(DATA_DIR))
        result = engine.run(
            strategy_name="sweep",
            strategy_func=strategy_func,
            params={},
            symbol="BTCUSDT",
            timeframe="1h",
            exit_config=exit_config,
            df=df,
        )
        return {
            "net_return": round(float(result.net_return), 4),
            "trade_count": result.trade_count,
            "max_drawdown": round(float(result.max_drawdown), 4),
            "win_rate": round(float(result.win_rate), 2),
            "sharpe": round(float(result.sharpe_ratio), 4) if result.trade_count > 0 else 0,
            "error": None,
        }
    except Exception as e:
        return {"error": str(e), "net_return": -999, "trade_count": 0}


# ============================================================================
# WALK-FORWARD
# ============================================================================

def run_walk_forward(entry: str, exit_config: dict, symbol: str, n_windows: int = 10) -> dict:
    """Run WF validation using existing gate."""
    from walk_forward_gate import run_wf_on_candidate, ASSETS as WF_ASSETS
    
    asset = symbol.replace("USDT", "")
    try:
        result = run_wf_on_candidate(
            name=f"v13_{entry[:30]}",
            entry=entry,
            exit_config=exit_config,
            n_windows=n_windows,
            target_assets=[asset],
        )
        return result
    except Exception as e:
        return {"error": str(e), "robustness_score": 0, "passed": False, "avg_oos_return": 0}


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def main():
    print("=" * 60)
    print("Foundry V13 — Deep Funding Parameter Sweep")
    print("=" * 60)
    
    # Load data
    data_cache = {}
    for sym in ASSETS:
        data_cache[sym] = load_data(sym)
        print(f"  {sym}: {len(data_cache[sym])} rows")
    
    # Phase 1: Grid Search
    total = len(SIGNAL_VARIANTS) * len(ASSETS) * len(EXIT_CONFIGS)
    print(f"\n📊 Phase 1: Grid Search ({total} backtests)")
    
    results = []
    count = 0
    start = time.time()
    
    for sig_type, entry, sig_params in SIGNAL_VARIANTS:
        for sym in ASSETS:
            df = data_cache[sym]
            if len(df) == 0:
                continue
            for exit_name, exit_config in EXIT_CONFIGS.items():
                count += 1
                if count % 200 == 0:
                    elapsed = time.time() - start
                    rate = count / elapsed if elapsed > 0 else 0
                    eta = (total - count) / rate if rate > 0 else 0
                    print(f"  [{count}/{total}] {rate:.0f}/s ETA={eta:.0f}s")
                
                bt = run_backtest(df, entry, exit_config)
                results.append({
                    "signal_type": sig_type,
                    "entry": entry,
                    "params": sig_params,
                    "asset": sym,
                    "exit_config": exit_name,
                    **bt,
                })
    
    elapsed = time.time() - start
    print(f"  ✅ Done: {count} backtests in {elapsed:.1f}s ({count/elapsed:.0f}/s)")
    
    # Phase 2: Filter & Rank
    print(f"\n📊 Phase 2: Filter & Rank")
    
    # Filter: need at least 5 trades and positive return
    valid = [r for r in results if r["error"] is None and r["trade_count"] >= 5]
    profitable = [r for r in valid if r["net_return"] > 0]
    
    print(f"  Total: {len(results)} | Valid (≥5 trades): {len(valid)} | Profitable: {len(profitable)}")
    
    # Rank by composite: net_return (60%) + sharpe (20%) + win_rate/100 (10%) - dd/100 (10%)
    for r in profitable:
        r["score"] = (
            r["net_return"] * 0.6 +
            r["sharpe"] * 20 +
            r["win_rate"] / 100 * 10 -
            r["max_drawdown"] / 100 * 10
        )
    
    profitable.sort(key=lambda x: x["score"], reverse=True)
    
    # Show top 20
    print(f"\n  Top 20 IS Results:")
    for i, r in enumerate(profitable[:20]):
        print(f"  {i+1:2d}. {r['signal_type']:18s} {r['asset']:8s} {r['exit_config']:12s} | "
              f"ret={r['net_return']:+7.2f}% trades={r['trade_count']:3d} wr={r['win_rate']:5.1f}% dd={r['max_drawdown']:5.1f}% sharpe={r['sharpe']:5.2f}")
    
    # Phase 3: Walk-Forward on top candidates
    # Deduplicate: unique entry+asset combos (best exit per combo)
    seen = set()
    unique_candidates = []
    for r in profitable:
        key = f"{r['entry']}|{r['asset']}"
        if key not in seen:
            seen.add(key)
            unique_candidates.append(r)
        if len(unique_candidates) >= 20:
            break
    
    print(f"\n📊 Phase 3: Walk-Forward (top {len(unique_candidates)} unique)")
    
    wf_results = []
    for i, r in enumerate(unique_candidates):
        exit_config = EXIT_CONFIGS[r["exit_config"]]
        sym = r["asset"]
        print(f"  [{i+1}/{len(unique_candidates)}] {r['signal_type']} {sym} {r['exit_config']} | IS ret={r['net_return']:+.2f}%")
        
        wf = run_walk_forward(r["entry"], exit_config, sym, n_windows=10)
        r["wf"] = wf
        r["wf_robustness"] = wf.get("robustness_score", 0)
        r["wf_passed"] = wf.get("passed", False)
        r["wf_avg_oos"] = wf.get("avg_oos_return", 0)
        wf_results.append(r)
        
        status = "✅ PASS" if r["wf_passed"] else "❌ FAIL"
        print(f"       {status} robustness={r['wf_robustness']:.0f} OOS={r['wf_avg_oos']:+.2%}")
    
    # Summary
    passed = [r for r in wf_results if r.get("wf_passed")]
    print(f"\n{'='*60}")
    print(f"FINAL: {len(profitable)} profitable IS | {len(wf_results)} WF-tested | {len(passed)} WF-passed")
    print(f"{'='*60}")
    
    # Save results
    output = {
        "version": "V13",
        "timestamp": datetime.now().isoformat(),
        "grid_total": len(results),
        "grid_valid": len(valid),
        "grid_profitable": len(profitable),
        "wf_tested": len(wf_results),
        "wf_passed": len(passed),
        "top_is": [
            {
                "rank": i+1,
                "signal_type": r["signal_type"],
                "entry": r["entry"],
                "asset": r["asset"],
                "exit_config": r["exit_config"],
                "net_return": r["net_return"],
                "trade_count": r["trade_count"],
                "win_rate": r["win_rate"],
                "max_drawdown": r["max_drawdown"],
                "sharpe": r["sharpe"],
                "score": r.get("score", 0),
                "wf_robustness": r.get("wf_robustness"),
                "wf_passed": r.get("wf_passed"),
                "wf_avg_oos": r.get("wf_avg_oos"),
            }
            for i, r in enumerate(profitable[:50])
        ],
        "wf_results": [
            {
                "signal_type": r["signal_type"],
                "entry": r["entry"],
                "asset": r["asset"],
                "exit_config": r["exit_config"],
                "is_return": r["net_return"],
                "wf_robustness": r.get("wf_robustness"),
                "wf_passed": r.get("wf_passed"),
                "wf_avg_oos": r.get("wf_avg_oos"),
            }
            for r in wf_results
        ],
    }
    
    with open(OUTPUT, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n💾 Results saved to {OUTPUT}")
    
    # Discord report
    try:
        import requests
        from run_foundry_v12 import send_discord_report as send_report
        lines = ["🔬 **Foundry V13 — Funding Sweep**\n"]
        lines.append(f"Grid: {len(results)} tests → {len(profitable)} profitable IS → {len(passed)} WF-passed\n")
        
        if profitable:
            lines.append("**Top 5 IS:**")
            for i, r in enumerate(profitable[:5]):
                lines.append(f"{i+1}. `{r['signal_type']}` {r['asset']} {r['exit_config']} | "
                           f"Ret: {r['net_return']:+.1f}% | Trades: {r['trade_count']} | WR: {r['win_rate']:.0f}%")
        
        if passed:
            lines.append(f"\n✅ **WF Passed: {len(passed)}**")
            for r in passed:
                lines.append(f"  `{r['signal_type']}` {r['asset']} | R={r['wf_robustness']:.0f} OOS={r['wf_avg_oos']:+.2%}")
        else:
            lines.append(f"\n❌ **0 WF-passed** — no robust strategies found")
        
        # Try OpenClaw message API
        msg = "\n".join(lines)
        # Send via message tool is not available here, save for reporting
        print(f"\nDiscord message ready ({len(msg)} chars)")
    except ImportError:
        pass


if __name__ == "__main__":
    main()