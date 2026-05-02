"""
Foundry V12 — Context-Aware LLM Strategy Discovery

LLM gets full hypothesis context + building blocks.
3 iterations × 10 strategies each, with feedback loop.
"""

import json, os, sys, time, requests, numpy as np, pandas as pd
from pathlib import Path
from copy import deepcopy

sys.path.insert(0, str(Path(__file__).parent))
from run_foundry_v11 import load_fgi, load_dxy, enrich_asset

DATA_DIR = Path(__file__).parent / "data_v10"
OUTPUT = Path(__file__).parent / "foundry_v12_results.json"

# ── LLM Config ──
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://172.17.0.1:32771/v1/chat/completions")
OLLAMA_KEY = os.environ.get("OLLAMA_KEY", "ollama-cloud")
MODEL = os.environ.get("FOUNDRY_MODEL", "gemma4:31b-cloud")

# ── Building Blocks ──
CONTEXT = """You are a crypto strategy researcher. Create 10 NOVEL strategies using ONLY these building blocks:

ASSETS: ONLY BTCUSDT, ETHUSDT, SOLUSDT. No other assets.

SIGNALS: funding_z (float), bull200 (0/1), bull50 (0/1), fgi (int or None), vol_ratio (float).

PROVEN: bear z<-1=Long, bull pullback z -1.0 to -0.3=Long, SOL z<-1.5=Long, BTC FGI<40 filter, ETH vol_ratio>1.5 confirm, BTC 4h=5x PnL.
FAILED: DXY, momentum/breakout, shorts, threshold sweeping. Do NOT use these.

Output ONLY a JSON array. Each object: name, desc, assets (from BTCUSDT/ETHUSDT/SOLUSDT), entry_bull (python bool expr with d['key']), entry_bear (same), timeframe (1h or 4h), notes.
None-safe: (d.get('fgi') or 999). Strict < for thresholds. No trailing commas.
"""

FEEDBACK_TEMPLATE = """
## RESULTS FROM ITERATION {iter}

{results}

Create 10 NEW strategies based on these results. Avoid what failed. Vary what worked.
Output ONLY a JSON array.
"""
FEEDBACK_TEMPLATE = """
## RESULTS FROM ITERATION {iter}

{results}

## INSTRUCTION
Based on these results, create 10 NEW strategies. Avoid what failed. Double down on what worked.
Try variations of the top performers. Explore adjacent parameter space.
Remember: ONLY proven building blocks. NO DXY, NO momentum, NO shorts.
"""

# ── Backtest Engine ──

def walk_forward_gate(df, entry_fn, n_windows=6, exit_hours=24, fee_pct=0.04, slippage_bps=3.0):
    total_len = len(df)
    window_size = total_len // n_windows
    results = []
    for w in range(n_windows):
        oos_start = w * window_size
        oos_end = (w + 1) * window_size if w < n_windows - 1 else total_len
        oos_df = df.iloc[oos_start:oos_end]
        trades = []
        i = 0
        while i < len(oos_df) - exit_hours:
            row = oos_df.iloc[i]
            try:
                if entry_fn(row):
                    entry_price = row['close'] * (1 + slippage_bps / 10000)
                    exit_idx = min(i + exit_hours, len(oos_df) - 1)
                    exit_price = oos_df.iloc[exit_idx]['close'] * (1 - slippage_bps / 10000)
                    pnl = (exit_price - entry_price) / entry_price * 100 - fee_pct
                    trades.append(pnl)
                    i += exit_hours
                else:
                    i += 1
            except:
                i += 1
        cum_pnl = sum(trades) if trades else 0
        win_rate = sum(1 for t in trades if t > 0) / len(trades) * 100 if trades else 0
        results.append({
            'window': w + 1, 'n_trades': len(trades), 'cum_pnl': round(cum_pnl, 2),
            'win_rate': round(win_rate, 1), 'oos_profitable': cum_pnl > 0,
        })
    n_profitable = sum(1 for r in results if r['oos_profitable'])
    total_pnl = sum(r['cum_pnl'] for r in results)
    total_trades = sum(r['n_trades'] for r in results)
    avg_wr = np.mean([r['win_rate'] for r in results if r['n_trades'] > 0]) if any(r['n_trades'] > 0 for r in results) else 0
    passed = n_profitable >= 4 and total_pnl > 0 and total_trades >= 30
    return {
        'passed': passed, 'n_profitable': n_profitable, 'n_windows': n_windows,
        'robustness': round(n_profitable / n_windows * 100),
        'total_oos_pnl': round(total_pnl, 2), 'total_trades': total_trades,
        'avg_win_rate': round(avg_wr, 1), 'windows': results,
    }

def make_entry_fn(entry_bull_expr, entry_bear_expr):
    def entry_fn(row):
        try:
            d = dict(row)
            for k, v in d.items():
                if isinstance(v, float) and (v != v):
                    d[k] = None
            # Convert float bools to ints
            if 'bull200' in d and d['bull200'] is not None:
                d['bull200'] = int(d['bull200'])
            if 'bull50' in d and d['bull50'] is not None:
                d['bull50'] = int(d['bull50'])
            if (d.get('bull200') or 0) == 1:
                result = eval(entry_bull_expr, {"__builtins__": {}, "d": d}, {})
            else:
                result = eval(entry_bear_expr, {"__builtins__": {}, "d": d}, {})
            return bool(result)
        except:
            return False
    return entry_fn

# ── LLM Call ──

def call_llm(prompt: str, retries=3) -> str:
    for attempt in range(retries):
        try:
            resp = requests.post(
                OLLAMA_URL,
                headers={"Authorization": f"Bearer {OLLAMA_KEY}", "Content-Type": "application/json"},
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                    "max_tokens": 6000,
                },
                timeout=120,
            )
            data = resp.json()
            msg = data.get("choices", [{}])[0].get("message", {})
            content = msg.get("content", "")
            if not content:
                # Thinking model: content may be in reasoning field
                content = msg.get("reasoning", "") or msg.get("reasoning_content", "")
            if not content:
                # Try full response as string
                content = str(data)
            if content:
                return content
            print(f"  LLM empty response (attempt {attempt+1})")
        except Exception as e:
            print(f"  LLM error: {e} (attempt {attempt+1})")
            time.sleep(5)
    return ""

def parse_strategies(llm_output: str) -> list:
    """Extract JSON array from LLM output."""
    # Try all possible content fields
    text = llm_output
    
    # Find JSON array
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        chunk = text[start:end]
        try:
            result = json.loads(chunk)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
        # Try fixing common issues
        fixed = chunk.replace("'", '"').replace("True", "true").replace("False", "false").replace("None", "null")
        try:
            result = json.loads(fixed)
            if isinstance(result, list):
                return result
        except:
            pass
    
    # Try to find individual JSON objects
    import re
    objects = re.findall(r'\{[^{}]*\}', text)
    if objects:
        strategies = []
        for obj_str in objects:
            try:
                obj = json.loads(obj_str.replace("'", '"').replace("True", "true").replace("False", "false"))
                if 'name' in obj or 'entry_bull' in obj:
                    strategies.append(obj)
            except:
                pass
        if strategies:
            return strategies
    
    print(f"  WARNING: Could not parse LLM output as JSON")
    print(f"  Raw output (first 1000): {llm_output[:1000]}")
    return []

# ── Load Data ──

def load_data():
    fgi = load_fgi()
    dxy = load_dxy()
    datasets = {}
    for asset in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        df = pd.read_parquet(DATA_DIR / f"{asset}_1h_full.parquet")
        df = enrich_asset(df.copy(), fgi, dxy)
        df['funding_z'] = df['funding_z'].replace([np.inf, -np.inf], np.nan)
        df['bull200'] = df['bull200'].fillna(0).astype(int)
        datasets[(asset, "1h")] = df
    # BTC 4h
    df4h = pd.read_parquet(DATA_DIR / "BTCUSDT_4h_full.parquet")
    # Enrich 4h with FGI
    df4h['timestamp_dt'] = pd.to_datetime(df4h['timestamp'], unit='ms')
    fgi_df = fgi if isinstance(fgi, pd.DataFrame) else pd.DataFrame()
    if not fgi_df.empty and 'fgi' in fgi_df.columns:
        fgi_df = fgi_df.set_index('timestamp') if 'timestamp' in fgi_df.columns else fgi_df
        # Merge FGI by nearest timestamp
        df4h = df4h.sort_values('timestamp_dt')
        fgi_sorted = fgi_df.sort_values('timestamp') if 'timestamp' in fgi_df.columns else fgi_df
        # Simple: use last known FGI
        df4h['fgi'] = fgi_df['fgi'].iloc[-1] if len(fgi_df) > 0 else None
    df4h['fund_cross_up'] = 0
    df4h['fund_cross_down'] = 0
    df4h['squeeze'] = 0
    df4h['dxy'] = None
    df4h['dxy_5d_chg'] = None
    datasets[("BTCUSDT", "4h")] = df4h
    return datasets

# ── Main ──

def run_iteration(iter_num: int, strategies: list, datasets: dict, all_results: dict) -> str:
    """Backtest strategies and return feedback string."""
    feedback_lines = []
    for strat in strategies:
        name = strat.get("name", f"unknown_{iter_num}")
        desc = strat.get("desc", "")
        assets = strat.get("assets", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        # Ensure assets is a list, not a string
        if isinstance(assets, str):
            assets = [assets]
        # Normalize asset names
        asset_map = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
        assets = [asset_map.get(a, a) for a in assets]
        entry_bull = strat.get("entry_bull", "False")
        entry_bear = strat.get("entry_bear", "False")
        timeframe = strat.get("timeframe", "1h")
        entry_fn = make_entry_fn(entry_bull, entry_bear)

        for asset in assets:
            key = (asset, timeframe)
            if key not in datasets:
                feedback_lines.append(f"  {name}/{asset}@{timeframe}: SKIP (no data)")
                continue
            df = datasets[key]
            result = walk_forward_gate(df, entry_fn)
            rkey = f"{asset}_{name}_{timeframe}"
            all_results[rkey] = {**result, 'desc': desc, 'timeframe': timeframe, 'iter': iter_num}
            status = "✅" if result['passed'] else "❌"
            feedback_lines.append(
                f"  {status} {name}/{asset}@{timeframe}: OOS={result['n_profitable']}/6, "
                f"PnL={result['total_oos_pnl']:+.2f}%, n={result['total_trades']}, WR={result['avg_win_rate']:.1f}%"
            )
    return "\n".join(feedback_lines)

def main():
    print("=" * 80)
    print("FOUNDRY V12 — Context-Aware LLM Strategy Discovery")
    print(f"Model: {MODEL} | 3 iterations × 10 strategies")
    print("=" * 80)

    datasets = load_data()
    all_results = {}
    best_strategies = []

    for iteration in range(1, 4):
        print(f"\n{'='*60}")
        print(f"  ITERATION {iteration}/3")
        print(f"{'='*60}")

        # Build prompt
        if iteration == 1:
            prompt = CONTEXT
        else:
            prompt = CONTEXT + FEEDBACK_TEMPLATE.format(iter=iteration-1, results=prev_feedback)

        # Call LLM
        print("  Calling LLM...")
        llm_output = call_llm(prompt)
        if not llm_output:
            print("  LLM failed, using fallback strategies")
            # Fallback: deterministic strategies for this iteration
            strategies = FALLBACK_STRATEGIES.get(iteration, [])
        else:
            strategies = parse_strategies(llm_output)
            print(f"  LLM returned {len(strategies)} strategies")
        if not strategies and llm_output:
            # Debug: show what we got
            print(f"  LLM raw output (first 500 chars): {llm_output[:500]}")

        if not strategies:
            print("  No strategies parsed, skipping iteration")
            prev_feedback = "No valid strategies generated."
            continue

        # Print what we got
        for s in strategies:
            print(f"    - {s.get('name','?')}: {s.get('desc','')[:60]}")

        # Backtest
        print(f"\n  Backtesting {len(strategies)} strategies...")
        prev_feedback = run_iteration(iteration, strategies, datasets, all_results)

        # Show results
        print(f"\n  Results:")
        print(prev_feedback)

        # Track best
        for rkey, r in all_results.items():
            if r['passed'] and r.get('iter') == iteration:
                best_strategies.append(rkey)

    # ── Final Summary ──
    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}")

    passed = {k: v for k, v in all_results.items() if v['passed']}
    print(f"\n  Total tested: {len(all_results)}")
    print(f"  Total PASSED: {len(passed)}")

    # Sort by composite fitness
    for name, r in sorted(passed.items(), key=lambda x: -x[1]['total_oos_pnl']):
        print(f"  ✅ {name:45s} | OOS={r['n_profitable']}/6 | PnL={r['total_oos_pnl']:+7.2f}% | n={r['total_trades']:4d} | WR={r['avg_win_rate']:.1f}%")

    # Compare vs baseline
    print(f"\n  V2 BASELINE COMPARISON:")
    print(f"  BTC bear: 4/6, +54.3%")
    print(f"  ETH bear: 5/6, +24.7%")
    print(f"  SOL z<-1.5: 6/6, +77.0%")

    with open(OUTPUT, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Results saved to {OUTPUT}")

# ── Fallback Strategies (if LLM fails) ──
FALLBACK_STRATEGIES = {
    1: [
        {"name": "V12_TightPullback", "desc": "Bull: tighter z range -0.5 to -0.2", "assets": ["BTCUSDT","ETHUSDT"], "entry_bull": "d['funding_z'] is not None and -0.5 < d['funding_z'] < -0.2 and (d.get('bull200') or 0) == 1", "entry_bear": "d['funding_z'] is not None and d['funding_z'] < -1.0", "timeframe": "1h"},
        {"name": "V12_WidePullback", "desc": "Bull: wider z range -1.0 to -0.2", "assets": ["BTCUSDT","ETHUSDT"], "entry_bull": "d['funding_z'] is not None and -1.0 < d['funding_z'] < -0.2 and (d.get('bull200') or 0) == 1", "entry_bear": "d['funding_z'] is not None and d['funding_z'] < -1.0", "timeframe": "1h"},
        {"name": "V12_VolPullback", "desc": "Bull pullback + volume confirm", "assets": ["BTCUSDT","ETHUSDT"], "entry_bull": "d['funding_z'] is not None and -1.0 < d['funding_z'] < -0.3 and (d.get('vol_ratio') or 0) > 1.3 and (d.get('bull200') or 0) == 1", "entry_bear": "d['funding_z'] is not None and d['funding_z'] < -1.0", "timeframe": "1h"},
        {"name": "V12_FGIPullback", "desc": "Bull pullback + FGI<50", "assets": ["BTCUSDT","ETHUSDT"], "entry_bull": "d['funding_z'] is not None and -1.0 < d['funding_z'] < -0.3 and (d.get('fgi') or 999) < 50 and (d.get('bull200') or 0) == 1", "entry_bear": "d['funding_z'] is not None and d['funding_z'] < -1.0", "timeframe": "1h"},
        {"name": "V12_BTC4h_BearOnly", "desc": "BTC 4h bear z<-1", "assets": ["BTCUSDT"], "entry_bull": "False", "entry_bear": "d['funding_z'] is not None and d['funding_z'] < -1.0", "timeframe": "4h"},
        {"name": "V12_BTC4h_Pullback", "desc": "BTC 4h bull pullback", "assets": ["BTCUSDT"], "entry_bull": "d['funding_z'] is not None and -1.0 < d['funding_z'] < -0.3 and (d.get('bull200') or 0) == 1", "entry_bear": "d['funding_z'] is not None and d['funding_z'] < -1.0", "timeframe": "4h"},
        {"name": "V12_BTC4h_VolPullback", "desc": "BTC 4h vol+pullback", "assets": ["BTCUSDT"], "entry_bull": "d['funding_z'] is not None and -1.0 < d['funding_z'] < -0.3 and (d.get('vol_ratio') or 0) > 1.3 and (d.get('bull200') or 0) == 1", "entry_bear": "d['funding_z'] is not None and d['funding_z'] < -1.0", "timeframe": "4h"},
        {"name": "V12_ETH_VolBearOnly", "desc": "ETH bear z<-1 + vol>1.5", "assets": ["ETHUSDT"], "entry_bull": "d['funding_z'] is not None and -1.0 < d['funding_z'] < -0.3", "entry_bear": "d['funding_z'] is not None and d['funding_z'] < -1.0 and (d.get('vol_ratio') or 0) > 1.5", "timeframe": "1h"},
        {"name": "V12_SOL_MildPullback", "desc": "SOL z<-1.0 in bull (wider than -1.5)", "assets": ["SOLUSDT"], "entry_bull": "d['funding_z'] is not None and d['funding_z'] < -1.0 and (d.get('bull200') or 0) == 1", "entry_bear": "d['funding_z'] is not None and d['funding_z'] < -1.5", "timeframe": "1h"},
        {"name": "V12_DualRegime", "desc": "Any regime: bear z<-1 OR bull z -0.8 to -0.3", "assets": ["BTCUSDT","ETHUSDT","SOLUSDT"], "entry_bull": "d['funding_z'] is not None and -0.8 < d['funding_z'] < -0.3", "entry_bear": "d['funding_z'] is not None and d['funding_z'] < -1.0", "timeframe": "1h"},
    ],
    2: [],
    3: [],
}

if __name__ == "__main__":
    main()