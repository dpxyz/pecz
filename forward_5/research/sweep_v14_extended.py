#!/usr/bin/env python3
"""
Sweep V14: Extended Features with 2yr OI/LS/Taker + DXY data

Tests hypotheses using the newly backfilled data:
- OI surge (ΔOI > threshold)
- LS Ratio extremes (toptrader_ls > threshold)
- Taker Vol Ratio (buy pressure)
- DXY regime filter
- Combinations with existing funding signals
"""

import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "executor"))
sys.path.insert(0, str(Path(__file__).parent))

from sweep_4h_data import load_all_4h, ASSETS
from sweep_4h_engine import run_backtest
from sweep_4h_cpcv import CPCVConfig, evaluate_cpcv_equity
from statistical_robustness import deflated_sharpe_ratio

log = logging.getLogger("sweep_v14")

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


@dataclass
class FeatureHypothesis:
    """A feature-based hypothesis to test."""
    name: str
    asset: str
    feature: str           # column name in 4h data
    condition: str         # "above", "below", "surge", "crosssec"
    thresholds: list[float]  # values to sweep
    direction: str         # "long" or "short"
    bull_filter: bool
    hold_hours: list[int]
    sl_pct: list[float]


def generate_feature_hypotheses() -> list[FeatureHypothesis]:
    """Generate hypotheses for extended features."""
    hyps = []
    
    for asset in ["BTC", "ETH", "SOL"]:
        # 1. OI Surge — sudden OI increase → trend continuation
        for hold in [24, 48]:
            for sl in [0, 5]:
                hyps.append(FeatureHypothesis(
                    name=f"oi_surge_{asset}_h{hold}_sl{sl}",
                    asset=asset, feature="oi_pct_change", condition="surge",
                    thresholds=[3.0, 5.0, 8.0, 12.0],
                    direction="long", bull_filter=True,
                    hold_hours=[hold], sl_pct=[sl],
                ))
        
        # 2. TopTrader LS Ratio — extreme long positioning → contrarian short
        hyps.append(FeatureHypothesis(
            name=f"toptrader_ls_extreme_{asset}",
            asset=asset, feature="toptrader_ls_ratio", condition="above",
            thresholds=[2.5, 3.0, 4.0, 5.0],
            direction="short", bull_filter=False,
            hold_hours=[24, 48], sl_pct=[5],
        ))
        
        # 3. Taker Vol Ratio — buy pressure → momentum
        hyps.append(FeatureHypothesis(
            name=f"taker_buy_pressure_{asset}",
            asset=asset, feature="taker_vol_ratio", condition="above",
            thresholds=[1.2, 1.5, 2.0, 3.0],
            direction="long", bull_filter=True,
            hold_hours=[24, 48], sl_pct=[0, 5],
        ))
        
        # 4. Taker Vol Ratio — sell pressure → short
        hyps.append(FeatureHypothesis(
            name=f"taker_sell_pressure_{asset}",
            asset=asset, feature="taker_vol_ratio", condition="below",
            thresholds=[0.5, 0.6, 0.7, 0.8],
            direction="short", bull_filter=False,
            hold_hours=[24, 48], sl_pct=[5],
        ))
        
        # 5. DXY Regime — weak dollar → crypto long
        hyps.append(FeatureHypothesis(
            name=f"dxy_weak_{asset}",
            asset=asset, feature="dxy_10d_roc", condition="below",
            thresholds=[-1.0, -2.0, -3.0],
            direction="long", bull_filter=True,
            hold_hours=[48, 96], sl_pct=[5],
        ))
        
        # 6. DXY + Funding combo
        hyps.append(FeatureHypothesis(
            name=f"dxy_weak_funding_neg_{asset}",
            asset=asset, feature="dxy_10d_roc", condition="below",
            thresholds=[-1.0, -2.0],
            direction="long", bull_filter=True,
            hold_hours=[48], sl_pct=[5],
        ))
    
    return hyps


def _check_feature_condition(df_row: dict, hyp: FeatureHypothesis, threshold: float) -> bool:
    """Check if a feature meets the entry condition."""
    val = df_row.get(hyp.feature, None)
    if val is None or not np.isfinite(val):
        return False
    
    if hyp.condition == "above":
        return val > threshold
    elif hyp.condition == "below":
        return val < threshold
    elif hyp.condition == "surge":
        return val > threshold  # positive % change
    return False


def run_feature_backtest(data_4h, hyp: FeatureHypothesis) -> list[dict]:
    """Run backtests for all threshold/hold/sl combinations of a hypothesis."""
    from sweep_4h_signals import SignalHypothesis
    
    df = data_4h.df
    results = []
    
    for threshold in hyp.thresholds:
        for hold in hyp.hold_hours:
            for sl in hyp.sl_pct:
                # Create entry signals
                close = df["close"].to_numpy().astype(float)
                n = len(close)
                entries = np.zeros(n, dtype=bool)
                
                for i in range(n):
                    row = {col: df[col][i] for col in df.columns}
                    
                    # Check feature condition
                    if not _check_feature_condition(row, hyp, threshold):
                        continue
                    
                    # Check bull filter
                    if hyp.bull_filter and row.get("bull200", 0) != 1:
                        continue
                    
                    # For combo signals, also check funding
                    if "funding" in hyp.name:
                        fz = row.get("funding_z", None)
                        if fz is None or not np.isfinite(fz):
                            continue
                        if fz >= 0:  # need negative funding for long
                            continue
                    
                    entries[i] = True
                
                result = _run_with_entries(data_4h, entries, hold, sl, hyp.direction)
                
                results.append({
                    "name": f"{hyp.name}_t{threshold}_h{hold}_sl{sl}",
                    "feature": hyp.feature,
                    "threshold": threshold,
                    "hold_hours": hold,
                    "sl_pct": sl,
                    "direction": hyp.direction,
                    "bull_filter": hyp.bull_filter,
                    "asset": hyp.asset,
                    "n_trades": result["n_trades"],
                    "win_rate": round(result["win_rate"], 4),
                    "total_return_pct": round(result["total_return_pct"], 2),
                    "sharpe": round(result["sharpe"], 2),
                    "max_dd_pct": round(result["max_dd_pct"], 2),
                })
    
    return results


def _run_with_entries(data_4h, entries: np.ndarray, hold_hours: int, sl_pct: float, direction: str) -> dict:
    """Run event-driven backtest with pre-computed entry signals."""
    df = data_4h.df
    close = df["close"].to_numpy().astype(float)
    n = len(close)
    
    trades = []
    i = 0
    while i < n:
        if not entries[i]:
            i += 1
            continue
        
        entry_price = close[i]
        entry_idx = i
        
        # Hold period
        exit_idx = min(i + hold_hours, n - 1)
        
        # Check stop-loss during hold
        sl_hit = False
        if sl_pct > 0:
            for j in range(i + 1, exit_idx + 1):
                pnl_pct = (close[j] - entry_price) / entry_price * 100
                if direction == "long" and pnl_pct < -sl_pct:
                    exit_idx = j
                    sl_hit = True
                    break
                elif direction == "short" and pnl_pct > sl_pct:
                    exit_idx = j
                    sl_hit = True
                    break
        
        exit_price = close[exit_idx]
        
        if direction == "long":
            pnl = (exit_price - entry_price) / entry_price * 100
        else:
            pnl = (entry_price - exit_price) / entry_price * 100
        
        trades.append({
            "entry_idx": entry_idx,
            "exit_idx": exit_idx,
            "pnl_pct": pnl,
        })
        
        i = exit_idx + 1
    
    # Compute stats
    if not trades:
        return {"n_trades": 0, "win_rate": 0, "avg_pnl_pct": 0,
                "total_return_pct": 0, "max_dd_pct": 0, "sharpe": 0}
    
    pnls = [t["pnl_pct"] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    
    equity = 100.0
    peak = 100.0
    max_dd = 0.0
    for p in pnls:
        equity *= (1 + p / 100)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    # Sharpe (annualized, 4h bars)
    if len(pnls) > 1:
        sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(6 * 365) if np.std(pnls) > 0 else 0
    else:
        sharpe = 0
    
    return {
        "n_trades": len(trades),
        "win_rate": wins / len(trades),
        "avg_pnl_pct": float(np.mean(pnls)),
        "total_return_pct": float(equity - 100),
        "max_dd_pct": float(max_dd),
        "sharpe": float(sharpe),
    }


def run_cpcv_validation(data_4h, entries: np.ndarray, hold_hours: int = 24, direction: str = "long", sl_pct: float = 5.0, n_groups: int = 6) -> dict:
    """Run CPCV validation on entry signals."""
    from sweep_4h_cpcv import CPCVConfig
    
    # Build equity curve from entries
    df = data_4h.df
    close = df["close"].to_numpy().astype(float)
    n = len(close)
    
    equity = 100.0
    equity_curve = [equity]
    i = 0
    while i < n:
        if entries[i]:
            entry_price = close[i]
            exit_idx = min(i + hold_hours, n - 1)
            # Check SL
            for j in range(i + 1, exit_idx + 1):
                pnl_pct = (close[j] - entry_price) / entry_price * 100
                if direction == "long" and pnl_pct < -sl_pct:
                    exit_idx = j
                    break
                elif direction == "short" and pnl_pct > sl_pct:
                    exit_idx = j
                    break
            exit_price = close[exit_idx]
            if direction == "long":
                pnl = (exit_price - entry_price) / entry_price
            else:
                pnl = (entry_price - exit_price) / entry_price
            equity *= (1 + pnl)
            # Fill bars between entry and exit
            for _ in range(exit_idx - i):
                equity_curve.append(equity)
            i = exit_idx + 1
        else:
            equity_curve.append(equity)
            i += 1
    
    config = CPCVConfig(n_groups=n_groups, n_test_groups=1)
    result = evaluate_cpcv_equity(equity_curve, config)
    return {"pbo": result.pbo, "oos_mean_pct": result.mean_sharpe * 100 if result.mean_sharpe else 0}


def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
    
    log.info("=" * 60)
    log.info("SWEEP V14: Extended Features (2yr OI/LS/Taker + DXY)")
    log.info("=" * 60)
    
    # Load data with new metrics
    log.info("Loading 4h data with 2yr metrics...")
    data = load_all_4h()
    
    # Generate hypotheses
    hyps = generate_feature_hypotheses()
    log.info(f"Testing {len(hyps)} feature hypotheses")
    
    all_results = []
    for i, hyp in enumerate(hyps):
        asset_data = data.get(hyp.asset)
        if asset_data is None:
            continue
        
        log.info(f"[{i+1}/{len(hyps)}] {hyp.name} ({hyp.feature} {hyp.condition})")
        results = run_feature_backtest(asset_data, hyp)
        
        # Only log profitable ones
        profitable = [r for r in results if r["total_return_pct"] > 0]
        if profitable:
            best = max(profitable, key=lambda r: r["sharpe"])
            log.info(f"  Best: {best['name']} ret={best['total_return_pct']:.1f}% "
                     f"Sharpe={best['sharpe']:.2f} trades={best['n_trades']} "
                     f"WR={best['win_rate']:.1%} DD={best['max_dd_pct']:.1f}%")
        
        all_results.extend(results)
    
    # Save results
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_file = RESULTS_DIR / f"sweep_v14_{timestamp}.json"
    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2)
    log.info(f"\nResults saved to {results_file}")
    
    # Summary
    profitable = [r for r in all_results if r["total_return_pct"] > 0 and r["n_trades"] >= 30]
    profitable.sort(key=lambda r: r["sharpe"], reverse=True)
    
    log.info(f"\n{'='*60}")
    log.info(f"SWEEP V14 SUMMARY")
    log.info(f"{'='*60}")
    log.info(f"Total tests: {len(all_results)}")
    log.info(f"Profitable (30+ trades): {len(profitable)}")
    
    if profitable:
        log.info(f"\nTop 20 by Sharpe:")
        for r in profitable[:20]:
            log.info(f"  {r['name']}: Sharpe={r['sharpe']:.2f}, "
                     f"ret={r['total_return_pct']:.1f}%, "
                     f"trades={r['n_trades']}, WR={r['win_rate']:.1%}, "
                     f"DD={r['max_dd_pct']:.1f}%")
    
    # Group by feature
    by_feature = {}
    for r in profitable:
        feat = r["feature"]
        if feat not in by_feature:
            by_feature[feat] = []
        by_feature[feat].append(r)
    
    log.info(f"\nBest per feature:")
    for feat, rs in by_feature.items():
        best = max(rs, key=lambda r: r["sharpe"])
        log.info(f"  {feat}: {best['name']} Sharpe={best['sharpe']:.2f} ret={best['total_return_pct']:.1f}%")
    
    # Run CPCV on top candidates
    log.info(f"\n{'='*60}")
    log.info(f"CPCV VALIDATION (top candidates)")
    log.info(f"{'='*60}")
    
    top_candidates = profitable[:5]
    for r in top_candidates:
        # Find the hypothesis
        asset = r["asset"]
        feature = r["feature"]
        threshold = r["threshold"]
        
        asset_data = data.get(asset)
        if asset_data is None:
            continue
        
        # Reconstruct entries
        df = asset_data.df
        close = df["close"].to_numpy().astype(float)
        n = len(close)
        entries = np.zeros(n, dtype=bool)
        
        for i in range(n):
            row = {col: df[col][i] for col in df.columns}
            val = row.get(feature, None)
            if val is None or not np.isfinite(val):
                continue
            
            direction = r["direction"]
            condition_met = False
            if r["threshold"] > 0 and direction == "long":
                condition_met = val > threshold
            elif r["threshold"] > 0 and direction == "short":
                condition_met = val > threshold  # LS ratio extreme
            elif direction == "short" and feature == "taker_vol_ratio":
                condition_met = val < threshold
            
            if not condition_met:
                continue
            if r["bull_filter"] and row.get("bull200", 0) != 1:
                continue
            
            entries[i] = True
        
        # CPCV
        if entries.sum() >= 30:
            cpcv_result = run_cpcv_validation(
                asset_data, entries,
                hold_hours=r["hold_hours"],
                direction=r["direction"],
                sl_pct=r["sl_pct"],
            )
            log.info(f"  {r['name']}: PBO={cpcv_result['pbo']:.3f}, "
                     f"OOS_mean={cpcv_result['oos_mean_pct']:.2f}%")
        else:
            log.info(f"  {r['name']}: SKIP (only {entries.sum()} trades)")


if __name__ == "__main__":
    main()