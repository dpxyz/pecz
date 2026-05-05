#!/usr/bin/env python3
"""
Validate V14 top candidates with CPCV and save results.
Reproduces the CPCV validation from sweep_v14_extended.py and saves to JSON.
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "executor"))

from sweep_4h_data import load_all_4h, ASSETS
from sweep_4h_engine import run_backtest
from sweep_4h_cpcv import CPCVConfig, evaluate_cpcv_equity
from statistical_robustness import deflated_sharpe_ratio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("v14_cpcv_validate")

RESULTS_DIR = Path(__file__).parent / "results"

# Top V14 candidates (from IS results >20 trades)
TOP_SIGNALS = [
    {"name": "oi_surge_SOL_h48_sl5_t3.0", "asset": "SOL", "feature": "oi_pct_change", "threshold": 3.0, "direction": "long", "bull_filter": True, "hold_hours": 48, "sl_pct": 5.0},
    {"name": "oi_surge_SOL_h24_sl5_t3.0", "asset": "SOL", "feature": "oi_pct_change", "threshold": 3.0, "direction": "long", "bull_filter": True, "hold_hours": 24, "sl_pct": 5.0},
    {"name": "toptrader_ls_extreme_SOL_t5.0_h24_sl5", "asset": "SOL", "feature": "toptrader_ls_ratio", "threshold": 5.0, "direction": "short", "bull_filter": False, "hold_hours": 24, "sl_pct": 5.0},
    {"name": "oi_surge_BTC_h48_sl5_t3.0", "asset": "BTC", "feature": "oi_pct_change", "threshold": 3.0, "direction": "long", "bull_filter": True, "hold_hours": 48, "sl_pct": 5.0},
    {"name": "oi_surge_BTC_h24_sl0_t3.0", "asset": "BTC", "feature": "oi_pct_change", "threshold": 3.0, "direction": "long", "bull_filter": True, "hold_hours": 24, "sl_pct": 0.0},
    {"name": "taker_buy_pressure_BTC_t2.0_h24_sl5", "asset": "BTC", "feature": "taker_vol_ratio", "threshold": 2.0, "direction": "long", "bull_filter": True, "hold_hours": 24, "sl_pct": 5.0},
]


def run_cpcv_validation(data_4h, entries, hold_hours=24, direction="long", sl_pct=5.0, n_groups=6):
    """Run CPCV validation on entry signals."""
    asset = data_4h.asset
    df = data_4h.df
    close = df["close"].to_numpy().astype(float)
    n = len(close)
    
    equity = np.ones(n)
    position = 0
    entry_price = 0.0
    entry_idx = 0
    
    for i in range(n):
        if position > 0:
            bars_held = i - entry_idx
            pnl = (close[i] - entry_price) / entry_price
            if direction == "short":
                pnl = -pnl
            if bars_held >= hold_hours // 4:
                equity[i] = equity[i-1] * (1 + pnl)
                position = 0
            elif sl_pct > 0 and pnl < -sl_pct / 100:
                equity[i] = equity[i-1] * (1 + pnl)
                position = 0
            else:
                equity[i] = equity[i-1]
        elif position == 0 and entries[i]:
            position = 1
            entry_price = close[i]
            entry_idx = i
            equity[i] = equity[i-1]
        else:
            equity[i] = equity[i-1]
    
    config = CPCVConfig(n_groups=n_groups, n_test_groups=1)
    result = evaluate_cpcv_equity(equity, config)
    
    return {
        "pbo": result.pbo,
        "oos_mean_pct": result.oos_mean_return * 100 if hasattr(result, 'oos_mean_return') else 0,
        "n_paths": result.n_paths if hasattr(result, 'n_paths') else 0,
    }


def main():
    log.info("Loading 4h data...")
    data = load_all_4h()
    
    results = []
    n_total = len(TOP_SIGNALS)
    N_total = 168  # total hypotheses tested in V14
    
    for idx, sig in enumerate(TOP_SIGNALS):
        log.info(f"Validating {idx+1}/{n_total}: {sig['name']}")
        asset = sig["asset"]
        asset_data = data[asset]
        df = asset_data.df
        
        feature = sig["feature"]
        threshold = sig["threshold"]
        direction = sig["direction"]
        bull_filter = sig["bull_filter"]
        
        close = df["close"].to_numpy().astype(float)
        n = len(close)
        entries = np.zeros(n, dtype=bool)
        
        for i in range(n):
            val = df[feature][i] if feature in df.columns else None
            if val is None or not np.isfinite(float(val)):
                continue
            val = float(val)
            
            condition_met = False
            if direction == "long" and threshold > 0:
                condition_met = val > threshold
            elif direction == "short" and threshold > 0:
                condition_met = val > threshold
            elif direction == "long" and threshold < 0:
                condition_met = val < threshold
            
            if not condition_met:
                continue
            if bull_filter and df["bull200"][i] != 1:
                continue
            
            entries[i] = True
        
        n_trades = int(entries.sum())
        if n_trades < 10:
            log.info(f"  SKIP: only {n_trades} trades")
            continue
        
        # Manual backtest (V14 features don't fit SignalHypothesis)
        close = df["close"].to_numpy().astype(float)
        hold_bars = sig["hold_hours"] // 4
        sl_pct = sig["sl_pct"]
        equity = np.ones(n)
        position = 0
        entry_price = 0.0
        entry_idx = 0
        n_wins = 0
        total_pnl = 0.0
        max_dd = 0.0
        peak_eq = 1.0
        trades_list = []
        
        for i in range(n):
            if position > 0:
                if direction == "long":
                    pnl = (close[i] - entry_price) / entry_price
                else:
                    pnl = (entry_price - close[i]) / entry_price
                bars_held = i - entry_idx
                if bars_held >= hold_bars or (sl_pct > 0 and pnl < -sl_pct / 100):
                    trades_list.append(pnl)
                    total_pnl += pnl
                    if pnl > 0:
                        n_wins += 1
                    equity[i] = equity[entry_idx] * (1 + pnl)
                    position = 0
                else:
                    equity[i] = equity[i-1]
            elif entries[i]:
                position = 1
                entry_price = close[i]
                entry_idx = i
                equity[i] = equity[i-1]
            else:
                equity[i] = equity[i-1]
            
            if equity[i] > peak_eq:
                peak_eq = equity[i]
            dd = (equity[i] - peak_eq) / peak_eq
            if dd < max_dd:
                max_dd = dd
        
        n_actual_trades = len(trades_list)
        win_rate = n_wins / n_actual_trades if n_actual_trades > 0 else 0
        total_ret = total_pnl * 100 if n_actual_trades > 0 else 0
        avg_pnl = total_pnl / n_actual_trades if n_actual_trades > 0 else 0
        std_pnl = np.std(trades_list) if n_actual_trades > 1 else 1
        sharpe = (avg_pnl / std_pnl) * np.sqrt(6 * 365) if std_pnl > 0 else 0  # annualized for 4h bars
        
        # CPCV
        cpcv_result = run_cpcv_validation(
            asset_data, entries,
            hold_hours=sig["hold_hours"],
            direction=direction,
            sl_pct=sig["sl_pct"],
        )
        
        # DSR
        dsr_result = deflated_sharpe_ratio(
            observed_sharpe=sharpe,
            n_backtests=N_total,
            n_observations=n_actual_trades,
            skewness=0.0, kurtosis=3.0,
            annualization_factor=1, is_annualized=True,
        )
        
        result = {
            "name": sig["name"],
            "asset": asset,
            "feature": feature,
            "threshold": threshold,
            "direction": direction,
            "bull_filter": bull_filter,
            "hold_hours": sig["hold_hours"],
            "sl_pct": sig["sl_pct"],
            "n_trades": n_actual_trades,
            "win_rate": round(win_rate, 4),
            "total_return_pct": round(total_ret, 2),
            "max_dd_pct": round(max_dd * 100, 2),
            "sharpe": round(sharpe, 2),
            "cpcv_pbo": round(cpcv_result["pbo"], 4),
            "cpcv_oos_mean_pct": round(cpcv_result["oos_mean_pct"], 2),
            "cpcv_n_paths": cpcv_result.get("n_paths", 0),
            "dsr_threshold": round(dsr_result.dsr, 4),
            "dsr_pass": bool(dsr_result.is_significant),
        }
        results.append(result)
        log.info(f"  PBO={result['cpcv_pbo']:.2f}, OOS={result['cpcv_oos_mean_pct']:+.1f}%, "
                 f"Sharpe={result['sharpe']:.2f}, Trades={result['n_trades']}")
    
    # Save
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_file = RESULTS_DIR / f"v14_cpcv_validated_{ts}.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"\nSaved {len(results)} validated results to {out_file}")
    
    # Summary
    log.info("\n=== V14 CPCV VALIDATION SUMMARY ===")
    for r in results:
        status = "✅" if r["cpcv_pbo"] < 0.5 else "⚠️" if r["cpcv_pbo"] < 0.7 else "❌"
        log.info(f"  {status} {r['name']:45} PBO={r['cpcv_pbo']:.2f}  OOS={r['cpcv_oos_mean_pct']:+.1f}%  "
                 f"Sharpe={r['sharpe']:.2f}  Trades={r['n_trades']}")


if __name__ == "__main__":
    main()