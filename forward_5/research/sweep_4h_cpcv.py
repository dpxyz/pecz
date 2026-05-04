"""
Phase 1.1: CPCV validation for DSR-passed 4h sweep signals.

Combinatorial Purged Cross-Validation (López de Prado):
- Splits data into N groups, tests all C(N, k) combinations
- Each combination = one backtest path
- PBO (Probability of Backtest Overfitting) = fraction of OOS losses
- Purging + Embargo prevent data leakage between train/test
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent / "executor"))

from cpcv import CPCVConfig, CPCVResult, generate_cpcv_paths, evaluate_cpcv_equity
from sweep_4h_data import load_all_4h
from sweep_4h_signals import SignalHypothesis
from sweep_4h_engine import run_backtest, BacktestResult

log = logging.getLogger("sweep_4h_cpcv")

RESULTS_DIR = Path(__file__).parent / "results"


def run_cpcv_for_signal(data, hyp: SignalHypothesis, n_groups: int = 6, n_test: int = 2) -> dict:
    """Run CPCV validation for a single signal hypothesis."""
    df = data.df
    n = len(df)
    
    # Get trade-level returns from a full backtest
    result = run_backtest(data, hyp)
    
    if result.n_trades < 10:
        return {
            "name": hyp.name,
            "n_trades": result.n_trades,
            "pbo": 1.0,  # insufficient data = certain overfit
            "oos_win_rate": 0.0,
            "oos_avg_pnl": 0.0,
            "is_sharpe": result.sharpe,
            "cpcv_pass": False,
        }
    
    # Convert trades to bar-level equity curve for CPCV
    # Each bar gets 0 (no trade) or return (trade active)
    bar_returns = np.zeros(n)
    for trade in result.trades:
        # Spread the trade's return over its hold period
        # This gives a smooth equity curve instead of point returns
        hold = trade.exit_idx - trade.entry_idx
        if hold > 0 and trade.exit_idx < n:
            # Simple: apply full return at exit bar
            bar_returns[trade.exit_idx] = trade.pnl_pct / 100.0
    
    # Build equity curve from bar returns
    equity = np.cumprod(1 + bar_returns) * 100
    
    # Minimum length check for CPCV
    if len(equity) < 200:
        return {
            "name": hyp.name,
            "n_trades": result.n_trades,
            "pbo": 1.0,
            "n_paths": 0,
            "oos_win_rate": 0.0,
            "oos_avg_return": 0.0,
            "is_sharpe": result.sharpe,
            "is_return_pct": round(result.total_return_pct, 2),
            "is_max_dd_pct": round(result.max_dd_pct, 2),
            "cpcv_pass": False,
            "error": "insufficient data",
        }
    
    # Run CPCV
    config = CPCVConfig(
        n_groups=n_groups,
        n_test_groups=n_test,
        embargo_bars=2,  # 2 bars = 8h embargo
    )
    
    try:
        cpcv_result = evaluate_cpcv_equity(equity, config)
        
        # Extract OOS performance from path returns
        oos_returns = [r for r in cpcv_result.path_returns if r is not None]
        oos_win_rate = sum(1 for r in oos_returns if r > 0) / len(oos_returns) if oos_returns else 0.0
        oos_avg = np.mean(oos_returns) * 100 if oos_returns else 0.0  # Convert to %
        
        return {
            "name": hyp.name,
            "n_trades": result.n_trades,
            "pbo": round(cpcv_result.pbo, 4),
            "n_paths": cpcv_result.n_paths,
            "oos_win_rate": round(oos_win_rate, 4),
            "oos_avg_return": round(oos_avg, 2),
            "is_sharpe": result.sharpe,
            "is_return_pct": round(result.total_return_pct, 2),
            "is_max_dd_pct": round(result.max_dd_pct, 2),
            "cpcv_pass": cpcv_result.pbo < 0.5,  # PBO < 0.5 = not overfit
        }
    except Exception as e:
        log.warning(f"CPCV failed for {hyp.name}: {e}")
        return {
            "name": hyp.name,
            "n_trades": result.n_trades,
            "pbo": 1.0,
            "n_paths": 0,
            "oos_win_rate": 0.0,
            "oos_avg_return": 0.0,
            "is_sharpe": result.sharpe,
            "is_return_pct": round(result.total_return_pct, 2),
            "is_max_dd_pct": round(result.max_dd_pct, 2),
            "cpcv_pass": False,
            "error": str(e),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
    
    # Load DSR-passed results
    result_files = sorted(RESULTS_DIR.glob("dsr_validated_*.json"))
    if not result_files:
        log.error("No DSR results found. Run sweep_4h_dsr.py first.")
        sys.exit(1)
    
    with open(result_files[-1]) as f:
        dsr_results = json.load(f)
    
    # Filter to DSR-passed only
    dsr_passed = [r for r in dsr_results if r.get("dsr_pass", False)]
    log.info(f"Running CPCV on {len(dsr_passed)} DSR-passed signals...")
    
    # Load data
    data = load_all_4h()
    
    # Run CPCV for each DSR-passed signal
    cpcv_results = []
    for i, r in enumerate(dsr_passed):
        hyp = SignalHypothesis(
            name=r["name"],
            asset=r["asset"],
            direction=r["direction"],
            entry_z_low=r["z_low"],
            entry_z_high=r["z_high"],
            bull_filter=r["bull_filter"],
            hold_hours=r["hold_hours"],
            sl_pct=r["sl_pct"],
            trail_pct=0.0,
        )
        
        asset_data = data.get(hyp.asset)
        if asset_data is None:
            continue
        
        log.info(f"  [{i+1}/{len(dsr_passed)}] CPCV for {hyp.name}...")
        result = run_cpcv_for_signal(asset_data, hyp)
        cpcv_results.append(result)
        
        status = "✅ PASS" if result["cpcv_pass"] else "❌ FAIL"
        log.info(f"    {status}: PBO={result['pbo']:.2f}, OOS WR={result['oos_win_rate']:.1%}, "
                 f"OOS ret={result['oos_avg_return']:.1f}%")
    
    # Summary
    passed = [r for r in cpcv_results if r["cpcv_pass"]]
    log.info(f"\n{'='*60}")
    log.info(f"CPCV VALIDATION RESULTS")
    log.info(f"{'='*60}")
    log.info(f"DSR-passed signals: {len(dsr_passed)}")
    log.info(f"CPCV-passed (PBO < 0.5): {len(passed)}")
    
    if passed:
        log.info(f"\n✅ CPCV-PASSED signals:")
        for r in sorted(passed, key=lambda x: x["is_sharpe"], reverse=True):
            log.info(f"  {r['name']}: PBO={r['pbo']:.2f}, IS Sharpe={r['is_sharpe']:.2f}, "
                     f"OOS WR={r['oos_win_rate']:.1%}, OOS ret={r['oos_avg_return']:.1f}%")
    else:
        log.info(f"\n❌ No signals passed CPCV")
        # Show all by PBO
        for r in sorted(cpcv_results, key=lambda x: x["pbo"]):
            log.info(f"  {r['name']}: PBO={r['pbo']:.2f}")
    
    # Save results
    timestamp = Path(result_files[-1]).stem.replace("dsr_validated_", "")
    out_file = RESULTS_DIR / f"cpcv_validated_{timestamp}.json"
    with open(out_file, "w") as f:
        json.dump(cpcv_results, f, indent=2)
    log.info(f"\nCPCV results saved to {out_file}")