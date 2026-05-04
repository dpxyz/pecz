"""
Phase 1.1: Correlation check for CPCV-passed signals.

Check if the top signals are truly uncorrelated (ρ < 0.4).
If BTC and ETH mild_neg are ρ > 0.7, they're the same edge.
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import polars as pl

from sweep_4h_data import load_all_4h
from sweep_4h_signals import SignalHypothesis
from sweep_4h_engine import run_backtest

log = logging.getLogger("sweep_4h_corr")

RESULTS_DIR = Path(__file__).parent / "results"


def compute_trade_correlation(trades_a, trades_b, n_bars):
    """Compute Spearman correlation of bar-level PnL between two signals."""
    returns_a = np.zeros(n_bars)
    returns_b = np.zeros(n_bars)
    
    for t in trades_a:
        if t.exit_idx < n_bars:
            returns_a[t.exit_idx] = t.pnl_pct / 100.0
    
    for t in trades_b:
        if t.exit_idx < n_bars:
            returns_b[t.exit_idx] = t.pnl_pct / 100.0
    
    # Only compare bars where at least one has a trade
    mask = (returns_a != 0) | (returns_b != 0)
    if mask.sum() < 20:
        return 0.0, mask.sum()
    
    a = returns_a[mask]
    b = returns_b[mask]
    
    # Spearman correlation
    from scipy.stats import spearmanr
    corr, pvalue = spearmanr(a, b)
    return corr if not np.isnan(corr) else 0.0, mask.sum()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
    
    # Load CPCV results
    cpcv_files = sorted(RESULTS_DIR.glob("cpcv_validated_*.json"))
    if not cpcv_files:
        log.error("No CPCV results found")
        sys.exit(1)
    
    with open(cpcv_files[-1]) as f:
        cpcv_results = json.load(f)
    
    # Take top 5 by PBO (most robust)
    cpcv_passed = [r for r in cpcv_results if r["cpcv_pass"]]
    top5 = sorted(cpcv_passed, key=lambda x: x["pbo"])[:5]
    
    log.info(f"Correlation check for top {len(top5)} CPCV-passed signals:")
    for r in top5:
        log.info(f"  {r['name']}: PBO={r['pbo']:.2f}, IS Sharpe={r['is_sharpe']:.2f}")
    
    # Load data and run backtests
    data = load_all_4h()
    
    # Get trade lists for each signal
    signal_trades = {}
    for r in top5:
        hyp = SignalHypothesis(
            name=r["name"], asset=r["name"].split("_")[0],
            direction="long", entry_z_low=-0.5, entry_z_high=0.0,
            bull_filter="bull200" if "bull200" in r["name"] else "none",
            hold_hours=r["name"].split("_")[-2] if "h" in r["name"] else 24,
            sl_pct=r["name"].split("_")[-1].replace("sl", "") if "sl" in r["name"] else 5.0,
            trail_pct=0.0,
        )
        # Parse the signal name properly
        parts = r["name"].split("_")
        asset = parts[0]
        
        # Reconstruct hypothesis from stored params
        # We need the backtest result for trade lists
        asset_data = data.get(asset)
        if not asset_data:
            continue
        
        # Find the matching hypothesis from the original sweep
        from sweep_4h_signals import generate_hypotheses
        all_hyps = generate_hypotheses()
        matching = [h for h in all_hyps if h.name == r["name"]]
        if not matching:
            log.warning(f"No matching hypothesis for {r['name']}")
            continue
        
        result = run_backtest(asset_data, matching[0])
        signal_trades[r["name"]] = (asset, result.trades)
    
    # Compute correlations between all pairs
    n_bars = 5001  # approximate
    log.info(f"\nCorrelation matrix (Spearman ρ):")
    
    names = list(signal_trades.keys())
    n = len(names)
    corr_matrix = np.zeros((n, n))
    
    for i in range(n):
        for j in range(n):
            if i == j:
                corr_matrix[i][j] = 1.0
            elif i < j:
                corr, n_overlap = compute_trade_correlation(
                    signal_trades[names[i]][1],
                    signal_trades[names[j]][1],
                    n_bars,
                )
                corr_matrix[i][j] = corr
                corr_matrix[j][i] = corr
    
    # Print matrix
    header = "         " + "  ".join(f"{n[:10]:>10}" for n in names)
    log.info(header)
    for i in range(n):
        row = f"{names[i][:10]:>10}"
        for j in range(n):
            val = corr_matrix[i][j]
            flag = " ⚠️" if abs(val) > 0.4 and i != j else "  "
            row += f"  {val:>8.2f}{flag}"
        log.info(row)
    
    # Identify uncorrelated pairs
    log.info(f"\nUncorrelated pairs (|ρ| < 0.4):")
    for i in range(n):
        for j in range(i + 1, n):
            if abs(corr_matrix[i][j]) < 0.4:
                log.info(f"  ✅ {names[i]} ↔ {names[j]}: ρ={corr_matrix[i][j]:.2f}")
            else:
                log.info(f"  ⚠️  {names[i]} ↔ {names[j]}: ρ={corr_matrix[i][j]:.2f} (correlated!)")