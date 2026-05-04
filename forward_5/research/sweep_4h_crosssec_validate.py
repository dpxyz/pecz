"""
DSR + CPCV validation for cross-sectional funding signals.
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "executor"))

from statistical_robustness import deflated_sharpe_ratio
from cpcv import CPCVConfig, evaluate_cpcv_equity
from sweep_4h_data import load_all_4h
from sweep_4h_crosssec import compute_cross_sectional_funding, run_crosssec_backtest
from sweep_4h_signals import SignalHypothesis

log = logging.getLogger("sweep_4h_crosssec_validate")
RESULTS_DIR = Path(__file__).parent / "results"


def validate_crosssec():
    log.info("Loading data...")
    data_4h = load_all_4h()
    crosssec = compute_cross_sectional_funding(data_4h)
    
    # Cross-sectional hypotheses that were profitable IS
    hypotheses = [
        SignalHypothesis("BTC_crosssec_z-1.0_bull200", "BTC", "long", -2.0, -1.0, "bull200", 24, 5.0, 0.0),
        SignalHypothesis("ETH_crosssec_z-1.0_bull200", "ETH", "long", -2.0, -1.0, "bull200", 24, 5.0, 0.0),
        SignalHypothesis("BTC_crosssec_z-1.5_none", "BTC", "long", -2.5, -1.5, "none", 24, 5.0, 0.0),
        SignalHypothesis("BTC_crosssec_z-1.0_none", "BTC", "long", -2.0, -1.0, "none", 24, 5.0, 0.0),
        SignalHypothesis("BTC_crosssec_z-1.5_bull200", "BTC", "long", -2.5, -1.5, "bull200", 24, 5.0, 0.0),
        SignalHypothesis("BTC_crosssec_z-0.5_bull200", "BTC", "long", -1.5, -0.5, "bull200", 24, 5.0, 0.0),
        SignalHypothesis("ETH_crosssec_z-0.5_bull200", "ETH", "long", -1.5, -0.5, "bull200", 24, 5.0, 0.0),
    ]
    
    N_total = 18  # Total cross-sectional hypotheses tested
    
    # Run backtests
    results = []
    for hyp in hypotheses:
        result = run_crosssec_backtest(data_4h, crosssec, hyp)
        results.append({
            "name": hyp.name, "asset": hyp.asset, "direction": hyp.direction,
            "z_low": hyp.entry_z_low, "z_high": hyp.entry_z_high,
            "bull_filter": hyp.bull_filter,
            "n_trades": result.n_trades, "win_rate": round(result.win_rate, 4),
            "avg_pnl_pct": round(result.avg_pnl_pct, 4),
            "total_return_pct": round(result.total_return_pct, 2),
            "max_dd_pct": round(result.max_dd_pct, 2),
            "sharpe": round(result.sharpe, 2),
        })
        log.info(f"  {hyp.name}: {result.n_trades} trades, Sharpe={result.sharpe:.2f}, "
                 f"ret={result.total_return_pct:.1f}%")
    
    # DSR validation
    log.info("\n--- DSR Validation ---")
    dsr_threshold = None
    for r in results:
        if r["n_trades"] < 10:
            r["dsr_pass"] = False
            r["dsr_threshold"] = 0.0
            continue
        
        dsr_result = deflated_sharpe_ratio(
            observed_sharpe=r["sharpe"],
            n_backtests=N_total,
            n_observations=r["n_trades"],
            skewness=0.0, kurtosis=3.0,
            annualization_factor=1, is_annualized=False,
        )
        r["dsr_threshold"] = round(dsr_result.dsr, 4)
        r["dsr_pass"] = dsr_result.is_significant
        
        if dsr_threshold is None:
            dsr_threshold = dsr_result.dsr
    
    dsr_passed = [r for r in results if r["dsr_pass"]]
    log.info(f"DSR threshold (N={N_total}): {dsr_threshold:.4f}")
    log.info(f"DSR passed: {len(dsr_passed)}/{len(results)}")
    
    # CPCV validation for DSR-passed
    log.info("\n--- CPCV Validation ---")
    for r in dsr_passed:
        hyp = [h for h in hypotheses if h.name == r["name"]][0]
        asset_data = data_4h.get(hyp.asset)
        if not asset_data:
            continue
        
        # Build equity curve from backtest
        bt_result = run_crosssec_backtest(data_4h, crosssec, hyp)
        n = len(asset_data.df)
        bar_returns = np.zeros(n)
        for t in bt_result.trades:
            if t.exit_idx < n:
                bar_returns[t.exit_idx] = t.pnl_pct / 100.0
        equity = np.cumprod(1 + bar_returns) * 100
        
        config = CPCVConfig(n_groups=6, n_test_groups=2, embargo_bars=2)
        try:
            cpcv_result = evaluate_cpcv_equity(equity, config)
            r["cpcv_pbo"] = round(cpcv_result.pbo, 4)
            oos_returns = [ret for ret in cpcv_result.path_returns if ret is not None]
            r["cpcv_oos_wr"] = round(sum(1 for ret in oos_returns if ret > 0) / len(oos_returns), 4) if oos_returns else 0
            r["cpcv_oos_ret"] = round(np.mean(oos_returns) * 100, 2) if oos_returns else 0
            r["cpcv_pass"] = cpcv_result.pbo < 0.5
        except Exception as e:
            log.warning(f"CPCV failed for {r['name']}: {e}")
            r["cpcv_pbo"] = 1.0
            r["cpcv_pass"] = False
        
        status = "✅" if r.get("cpcv_pass") else "❌"
        log.info(f"  {status} {r['name']}: PBO={r.get('cpcv_pbo', 'N/A')}, "
                 f"OOS WR={r.get('cpcv_oos_wr', 'N/A'):.1%}, "
                 f"OOS ret={r.get('cpcv_oos_ret', 'N/A'):.1f}%")
    
    # Summary
    validated = [r for r in results if r.get("dsr_pass") and r.get("cpcv_pass")]
    log.info(f"\n{'='*60}")
    log.info(f"CROSS-SECTIONAL VALIDATION SUMMARY")
    log.info(f"{'='*60}")
    log.info(f"Tested: {len(results)}, DSR passed: {len(dsr_passed)}, CPCV passed: {len(validated)}")
    
    for r in validated:
        log.info(f"  ✅ {r['name']}: IS Sharpe={r['sharpe']:.2f}, PBO={r['cpcv_pbo']:.2f}, "
                 f"OOS ret={r['cpcv_oos_ret']:.1f}%")
    
    # Save
    timestamp = "20260504_crosssec"
    out_file = RESULTS_DIR / f"crosssec_validated_{timestamp}.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"Results saved to {out_file}")
    
    return validated


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
    validate_crosssec()