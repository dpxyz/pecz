"""
Phase 1.1: Run the full 4h sweep across all hypotheses and assets.

Orchestrates: data loading → backtesting → statistical validation → edge registration.
Outputs results to sweep_4h_results.json for analysis.
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone

from sweep_4h_data import load_all_4h
from sweep_4h_signals import generate_hypotheses
from sweep_4h_engine import run_backtest

log = logging.getLogger("sweep_4h_run")

RESULTS_DIR = Path(__file__).parent / "results"


def run_sweep() -> list[dict]:
    """Run all hypotheses and return results."""
    log.info("Loading 4h data for all assets...")
    data = load_all_4h()
    
    hyps = generate_hypotheses()
    log.info(f"Running {len(hyps)} hypotheses across {len(data)} assets...")
    
    results = []
    for i, hyp in enumerate(hyps):
        asset_data = data.get(hyp.asset)
        if asset_data is None:
            log.warning(f"  [{i+1}/{len(hyps)}] SKIP {hyp.name}: no data for {hyp.asset}")
            continue
        
        result = run_backtest(asset_data, hyp)
        
        results.append({
            "name": hyp.name,
            "asset": hyp.asset,
            "direction": hyp.direction,
            "z_low": hyp.entry_z_low,
            "z_high": hyp.entry_z_high,
            "bull_filter": hyp.bull_filter,
            "hold_hours": hyp.hold_hours,
            "sl_pct": hyp.sl_pct,
            "n_trades": result.n_trades,
            "win_rate": round(result.win_rate, 4),
            "avg_pnl_pct": round(result.avg_pnl_pct, 4),
            "total_return_pct": round(result.total_return_pct, 2),
            "max_dd_pct": round(result.max_dd_pct, 2),
            "sharpe": round(result.sharpe, 2),
        })
        
        if (i + 1) % 10 == 0 or result.n_trades > 0:
            log.info(f"  [{i+1}/{len(hyps)}] {hyp.name}: {result.n_trades} trades, "
                     f"WR={result.win_rate:.1%}, ret={result.total_return_pct:.1f}%, "
                     f"DD={result.max_dd_pct:.1f}%, Sharpe={result.sharpe:.2f}")
    
    return results


def analyze_results(results: list[dict]) -> dict:
    """Quick analysis of sweep results."""
    profitable = [r for r in results if r["total_return_pct"] > 0]
    high_wr = [r for r in results if r["win_rate"] > 0.5]
    high_sharpe = sorted(results, key=lambda r: r["sharpe"], reverse=True)[:10]
    
    # Group by asset
    by_asset = {}
    for r in results:
        asset = r["asset"]
        if asset not in by_asset:
            by_asset[asset] = []
        by_asset[asset].append(r)
    
    analysis = {
        "total_hypotheses": len(results),
        "profitable": len(profitable),
        "high_winrate": len(high_wr),
        "best_by_sharpe": high_sharpe,
        "by_asset": {
            asset: {
                "count": len(rs),
                "profitable": sum(1 for r in rs if r["total_return_pct"] > 0),
                "best_sharpe": max(rs, key=lambda r: r["sharpe"]),
            }
            for asset, rs in by_asset.items()
        }
    }
    return analysis


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
    
    RESULTS_DIR.mkdir(exist_ok=True)
    
    log.info("=" * 60)
    log.info("PHASE 1.1: 4h Funding Sweep")
    log.info("=" * 60)
    
    results = run_sweep()
    
    # Save raw results
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_file = RESULTS_DIR / f"sweep_4h_{timestamp}.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"Results saved to {results_file}")
    
    # Analyze
    analysis = analyze_results(results)
    log.info(f"\n{'='*60}")
    log.info(f"SWEEP RESULTS SUMMARY")
    log.info(f"{'='*60}")
    log.info(f"Total hypotheses: {analysis['total_hypotheses']}")
    log.info(f"Profitable: {analysis['profitable']}")
    
    log.info(f"\nTop 10 by Sharpe:")
    for r in analysis["best_by_sharpe"]:
        log.info(f"  {r['name']}: Sharpe={r['sharpe']:.2f}, "
                 f"WR={r['win_rate']:.1%}, ret={r['total_return_pct']:.1f}%, "
                 f"DD={r['max_dd_pct']:.1f}%, trades={r['n_trades']}")
    
    log.info(f"\nBest per asset:")
    for asset, info in analysis["by_asset"].items():
        best = info["best_sharpe"]
        log.info(f"  {asset}: {best['name']} Sharpe={best['sharpe']:.2f}, "
                 f"ret={best['total_return_pct']:.1f}%, "
                 f"profitable={info['profitable']}/{info['count']}")