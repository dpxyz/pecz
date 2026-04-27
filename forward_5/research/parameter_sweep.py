#!/usr/bin/env python3
"""
Parameter-Sweep-Modul — Systematische Parametersuche für Foundry-Kandidaten.

Grid Search + Regime-Overlay + Quick-WF Prefilter.
Nimmt einen Kandidaten + Parameterraum und findet das optimale Parameter-Set.

Eingabe: HOF-Kandidat + Parameterraum-Definition
Ausgabe: Top-N optimierte Kandidaten (sortiert nach IS-Score)
"""

import json
import sys
import itertools
from pathlib import Path
from typing import Optional
from datetime import datetime

import polars as pl
import numpy as np

RESEARCH_DIR = Path(__file__).parent
sys.path.insert(0, str(RESEARCH_DIR))
sys.path.insert(0, str(RESEARCH_DIR / "backtest"))

from backtest.backtest_engine import BacktestEngine
from walk_forward_gate import build_strategy_func, run_wf_on_candidate

ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
DATA_PATH = RESEARCH_DIR / "data"
DATA_FILE_MAP = {a: f"{a}USDT_1h_full.parquet" for a in ASSETS}

PERIODS = {
    "2024": ("2024-01-01", "2024-12-31"),
    "2yr": ("2023-01-01", "2024-12-31"),
}


# ============================================================================
# REGIME OVERLAYS
# ============================================================================

REGIME_OVERLAYS = [
    {"name": "none",        "condition": None},
    {"name": "adx_trend",   "condition": "adx_14 > 20"},
    {"name": "adx_strong",  "condition": "adx_14 > 25"},
    {"name": "bb_squeeze",  "condition": "bb_width_20 < 0.03"},
    {"name": "low_vol",     "condition": "atr_14 < atr_14_sma"},
]


# ============================================================================
# PARAMETER-RAUM DEFINITIONEN
# ============================================================================

# Standard-Parameterräume je nach Strategie-Typ
PARAM_SPACES = {
    "MR": {
        "bb_period": [12, 14, 16, 18, 20, 24],
        "rsi_period": [5, 7, 10, 14, 21],
        "rsi_threshold": [25, 28, 30, 32, 35],
        "ema_period": [50, 100, 150, 200],
        "trailing_stop_pct": [1.5, 1.8, 2.0, 2.2, 2.5, 3.0],
        "stop_loss_pct": [2.5, 3.0, 3.5, 4.0],
        "max_hold_bars": [12, 18, 24, 30, 36],
    },
    "TREND": {
        "ema_fast": [20, 50],
        "ema_slow": [100, 150, 200],
        "adx_threshold": [18, 20, 25, 30],
        "adx_period": [10, 14, 20],
        "trailing_stop_pct": [2.5, 3.0, 3.5, 4.0],
        "stop_loss_pct": [3.0, 4.0, 5.0],
        "max_hold_bars": [24, 36, 48, 72],
    },
    "MOM": {
        "roc_period": [3, 5, 7, 10, 14],
        "roc_threshold": [1, 2, 3, 5],
        "macd_fast": [8, 12],
        "macd_slow": [21, 26],
        "trailing_stop_pct": [2.0, 2.5, 3.0, 3.5],
        "stop_loss_pct": [2.5, 3.0, 3.5, 4.0],
        "max_hold_bars": [12, 18, 24, 36],
    },
}


# ============================================================================
# DATA LOADING
# ============================================================================

def load_df(asset: str, start: str, end: str) -> pl.DataFrame:
    from datetime import datetime as dt
    data_file = DATA_PATH / DATA_FILE_MAP[asset]
    df = pl.scan_parquet(str(data_file)).collect()
    start_dt = dt.fromisoformat(start + "T00:00:00+00:00")
    end_dt = dt.fromisoformat(end + "T23:59:59+00:00")
    return df.filter(
        (pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt)
    )


# ============================================================================
# IS-BACKTEST (Gradient-Score)
# ============================================================================

def run_is_backtest(entry: str, exit_config: dict, strategy_type: str = "") -> dict | None:
    """Quick IS-Backtest mit Gradient-Score.
    If strategy_type is '4H', data is aggregated to 4h candles.
    """
    try:
        strategy_func, parseable = build_strategy_func(entry)
        if not parseable or strategy_func is None:
            return None
        
        engine = BacktestEngine(data_path=str(DATA_PATH))
        all_returns, all_dds, all_trades = [], [], []
        profitable = 0
        
        is_4h = strategy_type == "4H"
        
        for asset in ASSETS:
            for period_name, (start, end) in PERIODS.items():
                try:
                    df = load_df(asset, start, end)
                    if len(df) < 50:
                        continue
                    if is_4h:
                        from run_evolution_v8 import aggregate_to_4h as agg_4h
                        df = agg_4h(df)
                        if len(df) < 20:
                            continue
                    timeframe = "4h" if is_4h else "1h"
                    result = engine.run(
                        strategy_name="sweep", strategy_func=strategy_func, params={},
                        symbol=f"{asset}USDT", timeframe=timeframe,
                        exit_config=exit_config, df=df,
                    )
                    if result.trade_count > 0:
                        all_returns.append(result.net_return)
                        all_dds.append(result.max_drawdown)
                        all_trades.append(result.trade_count)
                        if result.net_return > 0:
                            profitable += 1
                except:
                    continue
        
        if not all_returns:
            return None
        
        n = len(all_returns)
        total_return = sum(all_returns) / n
        avg_dd = sum(all_dds) / n
        min_trades = min(all_trades)
        profitable_ratio = profitable / n
        trade_quality = min(1.0, min_trades / 5)
        
        if total_return > 0 and avg_dd > 0:
            score = (total_return / avg_dd) * profitable_ratio * trade_quality
        elif total_return <= 0:
            score = total_return * profitable_ratio * trade_quality * 0.1
        else:
            score = 0
        
        return {
            "avg_return": round(total_return, 2),
            "avg_dd": round(avg_dd, 1),
            "min_trades": min_trades,
            "profitable_assets": f"{profitable}/{n}",
            "is_score": round(score, 2),
        }
    except Exception as e:
        return None


# ============================================================================
# PARAMETER-EXTRAKTION UND RECONSTRUCTION
# ============================================================================

def extract_entry_params(entry: str) -> dict:
    """Extrahiere Parameter aus Entry-Condition String."""
    import re
    params = {}
    
    # BB period
    m = re.search(r'bb_lower_(\d+)', entry)
    if m:
        params["bb_period"] = int(m.group(1))
    
    # RSI period and threshold
    m = re.search(r'rsi_(\d+)\s*[<>]\s*(\d+)', entry)
    if m:
        params["rsi_period"] = int(m.group(1))
        params["rsi_threshold"] = int(m.group(2))
    
    # EMA period
    m = re.search(r'ema_(\d+)', entry)
    if m:
        params["ema_period"] = int(m.group(1))
    
    # ADX threshold
    m = re.search(r'adx_(\d+)\s*[<>]\s*(\d+)', entry)
    if m:
        params["adx_period"] = int(m.group(1))
        params["adx_threshold"] = int(m.group(2))
    
    # ROC period and threshold
    m = re.search(r'roc_(\d+)\s*[<>]\s*(\d+)', entry)
    if m:
        params["roc_period"] = int(m.group(1))
        params["roc_threshold"] = float(m.group(2))
    
    # Stochastic period
    m = re.search(r'stoch_k_(\d+)', entry)
    if m:
        params["stoch_period"] = int(m.group(1))
    
    # Williams %R period
    m = re.search(r'williams_r_(\d+)', entry)
    if m:
        params["williams_period"] = int(m.group(1))
    
    # Volume SMA period
    m = re.search(r'volume_sma_(\d+)', entry)
    if m:
        params["volume_sma_period"] = int(m.group(1))
    
    return params


def reconstruct_entry(entry_template: str, params: dict) -> str:
    """Rekonstruiere Entry-Condition mit neuen Parametern."""
    import re
    entry = entry_template
    
    # BB period
    if "bb_period" in params:
        entry = re.sub(r'bb_lower_\d+', f'bb_lower_{params["bb_period"]}', entry)
        entry = re.sub(r'bb_upper_\d+', f'bb_upper_{params["bb_period"]}', entry)
        entry = re.sub(r'bb_width_\d+', f'bb_width_{params["bb_period"]}', entry)
    
    # RSI period and threshold
    if "rsi_period" in params:
        entry = re.sub(r'rsi_\d+', f'rsi_{params["rsi_period"]}', entry)
    if "rsi_threshold" in params:
        entry = re.sub(r'(rsi_\d+\s*[<>]\s*)\d+', lambda m: f'{m.group(1)}{params["rsi_threshold"]}', entry)
    
    # EMA period
    if "ema_period" in params:
        # Replace the last ema in the entry (usually the trend filter)
        ema_matches = list(re.finditer(r'ema_\d+', entry))
        if ema_matches:
            last_match = ema_matches[-1]
            entry = entry[:last_match.start()] + f'ema_{params["ema_period"]}' + entry[last_match.end():]
    
    # ADX period and threshold
    if "adx_period" in params:
        entry = re.sub(r'adx_\d+', f'adx_{params["adx_period"]}', entry)
    if "adx_threshold" in params:
        entry = re.sub(r'(adx_\d+\s*[<>]\s*)\d+', lambda m: f'{m.group(1)}{params["adx_threshold"]}', entry)
    
    # ROC period and threshold
    if "roc_period" in params:
        entry = re.sub(r'roc_\d+', f'roc_{params["roc_period"]}', entry)
    if "roc_threshold" in params:
        entry = re.sub(r'(roc_\d+\s*[<>]\s*)[\d.]+', lambda m: f'{m.group(1)}{params["roc_threshold"]}', entry)
    
    return entry


# ============================================================================
# GRID SEARCH
# ============================================================================

def grid_search(
    entry_template: str,
    exit_config: dict,
    param_space: dict,
    exit_params: bool = True,
    max_combinations: int = 500,
    top_n: int = 10,
    regime_overlays: bool = True,
) -> list[dict]:
    """
    Systematischer Grid-Search über Parameter-Raum.
    
    Args:
        entry_template: Entry-Condition mit Platzhalter-Parametern
        exit_config: Basis-Exit-Konfiguration
        param_space: Dict von {param_name: [values]}
        exit_params: Auch Exit-Parameter variieren?
        max_combinations: Max Anzahl Kombinationen (Abbruch-Limit)
        top_n: Nur Top-N zurückgeben
        regime_overlays: Auch Regime-Overlays testen?
    
    Returns:
        Liste von Top-N Kandidaten sortiert nach IS-Score
    """
    # Entry-Parameter-Kombinationen generieren
    entry_params = {k: v for k, v in param_space.items() if k not in 
                    ["trailing_stop_pct", "stop_loss_pct", "max_hold_bars"]}
    exit_param_keys = ["trailing_stop_pct", "stop_loss_pct", "max_hold_bars"]
    exit_param_space = {k: v for k, v in param_space.items() if k in exit_param_keys}
    
    # Entry-Kombinationen
    if entry_params:
        entry_keys = list(entry_params.keys())
        entry_values = list(entry_params.values())
        entry_combos = list(itertools.product(*entry_values))
        entry_combos = [dict(zip(entry_keys, vals)) for vals in entry_combos]
    else:
        entry_combos = [{}]
    
    # Exit-Kombinationen
    if exit_params and exit_param_space:
        exit_keys = list(exit_param_space.keys())
        exit_values = list(exit_param_space.values())
        exit_combos = list(itertools.product(*exit_values))
        exit_combos = [dict(zip(exit_keys, vals)) for vals in exit_combos]
    else:
        exit_combos = [{}]
    
    total_combos = len(entry_combos) * len(exit_combos)
    if regime_overlays:
        total_combos *= len(REGIME_OVERLAYS)
    
    print(f"  🔍 Grid: {len(entry_combos)} entries × {len(exit_combos)} exits × {len(REGIME_OVERLAYS) if regime_overlays else 1} regimes = {total_combos} combos")
    
    if total_combos > max_combinations:
        # Random sample
        import random
        print(f"  ⚠️ Too many combos ({total_combos}), sampling {max_combinations}")
        all_combos = [(e, x, r) for e in entry_combos for x in exit_combos 
                      for r in (REGIME_OVERLAYS if regime_overlays else [{"name": "none", "condition": None}])]
        sampled = random.sample(all_combos, min(max_combinations, len(all_combos)))
    else:
        sampled = [(e, x, r) for e in entry_combos for x in exit_combos
                   for r in (REGIME_OVERLAYS if regime_overlays else [{"name": "none", "condition": None}])]
    
    results = []
    for i, (entry_params_dict, exit_params_dict, regime) in enumerate(sampled):
        # Reconstruct entry
        entry = reconstruct_entry(entry_template, entry_params_dict)
        
        # Add regime filter
        if regime.get("condition"):
            entry = f"{entry} AND {regime['condition']}"
        
        # Merge exit config
        exit_cfg = {**exit_config, **exit_params_dict}
        
        # Quick IS-Backtest
        is_result = run_is_backtest(entry, exit_cfg)
        
        if is_result:
            result = {
                "entry": entry,
                "exit_config": exit_cfg,
                "regime": regime["name"],
                **is_result,
                **entry_params_dict,
            }
            results.append(result)
        
        # Progress
        if (i + 1) % 50 == 0:
            print(f"    ... {i+1}/{len(sampled)} tested, {len(results)} valid")
    
    # Sort by IS-Score (descending)
    results.sort(key=lambda x: x.get("is_score", -999), reverse=True)
    
    print(f"  ✅ Grid complete: {len(results)} valid, top IS={results[0]['is_score'] if results else 'N/A'}")
    
    return results[:top_n]


# ============================================================================
# QUICK-WF PREFILTER (3-Window)
# ============================================================================

def quick_wf_filter(candidates: list[dict], top_n: int = 3) -> list[dict]:
    """
    Schneller 3-Window WF als Prefilter.
    Nur Kandidaten die hier bestehen kommen zum teuren 10w-WF.
    """
    print(f"  ⚡ Quick-WF (3-window) on {len(candidates)} candidates...")
    
    passed = []
    for c in candidates:
        wf = run_wf_on_candidate(
            name=f"sweep_{c.get('regime', 'none')}",
            entry=c["entry"],
            exit_config=c["exit_config"],
            n_windows=3,
        )
        
        c["quick_wf_robustness"] = wf.get("robustness_score", 0)
        c["quick_wf_passed"] = wf.get("passed", False)
        c["quick_wf_profitable"] = wf.get("profitable_assets", "0/6")
        
        # Prefilter: IS > 0 UND Quick-WF robustness > 30
        if c.get("is_score", -999) > 0 and c.get("quick_wf_robustness", 0) >= 30:
            passed.append(c)
        # Oder: Quick-WF passed
        elif c.get("quick_wf_passed", False):
            passed.append(c)
    
    print(f"  ⚡ Quick-WF: {len(passed)}/{len(candidates)} survived")
    
    # Sort by IS-Score
    passed.sort(key=lambda x: x.get("is_score", -999), reverse=True)
    return passed[:top_n]


# ============================================================================
# FULL SWEEP PIPELINE
# ============================================================================

def sweep_candidate(
    candidate: dict,
    param_space: Optional[dict] = None,
    max_combinations: int = 500,
    quick_wf_top_n: int = 3,
) -> dict:
    """
    Vollständige Sweep-Pipeline für einen Kandidaten.
    
    1. Parameter aus Entry extrahieren
    2. Grid-Search + Regime-Overlay
    3. Quick-WF Prefilter
    4. Return Top-N
    """
    name = candidate.get("name", "?")
    entry = candidate.get("entry_condition", candidate.get("entry", ""))
    exit_config = candidate.get("exit_config", {})
    
    print(f"\n🎯 Sweep: {name}")
    print(f"   Entry: {entry}")
    
    # Auto-detect strategy type and param space
    if param_space is None:
        from autopsy import classify_strategy_type
        stype = classify_strategy_type(entry)
        if stype in PARAM_SPACES:
            # Use only entry-relevant params from the space
            current_params = extract_entry_params(entry)
            param_space = {}
            for k, v in PARAM_SPACES[stype].items():
                # Include if it's an exit param or matches current entry params
                if k in ["trailing_stop_pct", "stop_loss_pct", "max_hold_bars"]:
                    param_space[k] = v
                elif k in current_params:
                    # Include values around current value
                    current_val = current_params[k]
                    relevant = [val for val in v if abs(val - current_val) <= max(v) * 0.5]
                    if len(relevant) < 3:
                        relevant = v[:5]
                    param_space[k] = relevant
        else:
            # Fallback: just exit params
            param_space = {
                "trailing_stop_pct": [1.5, 2.0, 2.5, 3.0, 3.5],
                "stop_loss_pct": [2.5, 3.0, 3.5, 4.0],
                "max_hold_bars": [12, 18, 24, 36, 48],
            }
    
    print(f"   Param space: {list(param_space.keys())} ({sum(len(v) for v in param_space.values())} total values)")
    
    # Step 1: Grid Search
    grid_results = grid_search(
        entry_template=entry,
        exit_config=exit_config,
        param_space=param_space,
        max_combinations=max_combinations,
        top_n=20,
        regime_overlays=True,
    )
    
    if not grid_results:
        print("  ❌ No valid combinations found")
        return {"name": name, "grid_results": [], "wf_candidates": []}
    
    # Step 2: Quick-WF Prefilter
    wf_candidates = quick_wf_filter(grid_results, top_n=quick_wf_top_n)
    
    return {
        "name": name,
        "original_entry": entry,
        "original_exit": exit_config,
        "grid_results": grid_results[:10],
        "wf_candidates": wf_candidates,
        "best_is_score": grid_results[0].get("is_score", 0) if grid_results else None,
        "best_entry": grid_results[0].get("entry", "") if grid_results else None,
        "best_regime": grid_results[0].get("regime", "none") if grid_results else None,
    }


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Parameter Sweep for Foundry Candidates")
    parser.add_argument("--candidate", help="JSON string or file with candidate")
    parser.add_argument("--hof", help="HOF JSON file to sweep top entries")
    parser.add_argument("--top-n", type=int, default=3, help="Top-N HOF entries to sweep")
    parser.add_argument("--max-combos", type=int, default=500, help="Max grid combinations")
    args = parser.parse_args()
    
    if args.candidate:
        if Path(args.candidate).exists():
            with open(args.candidate) as f:
                c = json.load(f)
        else:
            c = json.loads(args.candidate)
        
        result = sweep_candidate(c, max_combinations=args.max_combos)
        print(json.dumps(result, indent=2, default=str))
    
    elif args.hof:
        with open(args.hof) as f:
            data = json.load(f)
        
        hof = data.get("hof", data.get("hall_of_fame", []))
        # Only sweep WF-passed candidates
        wf_passed = [s for s in hof if s.get("wf_passed") or s.get("wf_robustness", 0) > 40]
        to_sweep = sorted(wf_passed, key=lambda x: x.get("wf_robustness", 0), reverse=True)[:args.top_n]
        
        print(f"Sweeping top {len(to_sweep)} HOF entries...")
        
        all_results = []
        for candidate in to_sweep:
            result = sweep_candidate(candidate, max_combinations=args.max_combos)
            all_results.append(result)
            
            if result.get("wf_candidates"):
                print(f"\n  🏆 {candidate.get('name', '?')}: {len(result['wf_candidates'])} WF candidates")
                for wc in result["wf_candidates"]:
                    print(f"     IS={wc.get('is_score', 0):.2f} regime={wc.get('regime', 'none')} R={wc.get('avg_return', 0):+.2f}%")
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = RESEARCH_DIR / "runs" / "evolution_v7" / f"sweep_results_{timestamp}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"\n💾 Results saved to {output_file}")
    
    else:
        print("Usage: python parameter_sweep.py --candidate <json_or_file> OR --hof <hof_file>")