"""
Phase 1.1: DSR validation for 4h sweep results.

Deflated Sharpe Ratio (Bailey & López de Prado):
- Penalizes for multiple testing
- DSR = probability that Sharpe is genuine given N tests
- DSR > 0.95 → likely genuine, not overfit

Uses the existing statistical_robustness module.
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np

# Add parent to path for executor imports
sys.path.insert(0, str(Path(__file__).parent.parent / "executor"))

from statistical_robustness import deflated_sharpe_ratio

from sweep_4h_data import load_all_4h
from sweep_4h_signals import generate_hypotheses, SignalHypothesis
from sweep_4h_engine import run_backtest, BacktestResult

log = logging.getLogger("sweep_4h_dsr")

RESULTS_DIR = Path(__file__).parent / "results"


def validate_with_dsr(results_file: str = None) -> list[dict]:
    """Load sweep results and apply DSR validation."""
    # Find latest results file
    if results_file is None:
        result_files = sorted(RESULTS_DIR.glob("sweep_4h_*.json"))
        if not result_files:
            log.error("No sweep results found")
            return []
        results_file = str(result_files[-1])
    
    with open(results_file) as f:
        results = json.load(f)
    
    log.info(f"Loaded {len(results)} results from {results_file}")
    
    # Total number of independent tests (for DSR)
    N_total = len(results)
    
    # Compute DSR for each result
    # We need: observed Sharpe, N tests, sample length, returns std
    # Using cluster_effective_n would be better, but for now use raw N
    
    validated = []
    for r in results:
        if r["n_trades"] < 10:
            r["dsr"] = 0.0
            r["dsr_pass"] = False
            validated.append(r)
            continue
        
        # DSR calculation
        # sharpe_annual, n_tests, n_observations, skew, kurt
        sharpe_ann = r["sharpe"]
        n_obs = r["n_trades"]  # number of trade observations
        
        try:
            dsr_result = deflated_sharpe_ratio(
                observed_sharpe=sharpe_ann,
                n_backtests=N_total,
                n_observations=n_obs,
                skewness=0.0,
                kurtosis=3.0,
                annualization_factor=1,  # Sharpe is per-trade, not annualized
                is_annualized=False,
            )
            dsr_val = dsr_result.dsr  # Expected max Sharpe under null
            dsr_statistic = dsr_result.dsr_statistic
            is_sig = dsr_result.is_significant
        except Exception as e:
            log.warning(f"DSR failed for {r['name']}: {e}")
            dsr = 0.0
        
        r["dsr_threshold"] = round(dsr_val, 4)  # Expected max Sharpe under null
        r["dsr_statistic"] = round(dsr_statistic, 4)
        r["dsr_pass"] = is_sig  # True if observed Sharpe > expected max under null
        validated.append(r)
    
    # Report
    dsr_passed = [r for r in validated if r["dsr_pass"]]
    log.info(f"\n{'='*60}")
    log.info(f"DSR VALIDATION RESULTS")
    log.info(f"{'='*60}")
    log.info(f"Total hypotheses: {len(validated)}")
    log.info(f"DSR passed (observed > expected max): {len(dsr_passed)}")
    log.info(f"Expected max Sharpe under null (N={len(validated)}): {dsr_passed[0]['dsr_threshold'] if dsr_passed else 'N/A'}")
    
    if dsr_passed:
        log.info(f"\n✅ DSR-PASSED signals (Sharpe > expected max under null):")
        for r in sorted(dsr_passed, key=lambda x: x["sharpe"], reverse=True):
            log.info(f"  {r['name']}: Sharpe={r['sharpe']:.2f} > threshold={r['dsr_threshold']:.2f}, "
                     f"ret={r['total_return_pct']:.1f}%, DD={r['max_dd_pct']:.1f}%")
    else:
        log.info(f"\n❌ No signals passed DSR (all likely overfit)")
        # Show top 10 by Sharpe
        top = sorted(validated, key=lambda x: x["sharpe"], reverse=True)[:10]
        log.info(f"\nTop 10 by Sharpe (none passed DSR):")
        for r in top:
            log.info(f"  {r['name']}: Sharpe={r['sharpe']:.2f}, threshold={r['dsr_threshold']:.2f}")
    
    # Save validated results
    out_file = RESULTS_DIR / f"dsr_validated_{Path(results_file).stem.replace('sweep_4h_', '')}.json"
    with open(out_file, "w") as f:
        json.dump(validated, f, indent=2)
    log.info(f"Validated results saved to {out_file}")
    
    return validated


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
    validate_with_dsr()