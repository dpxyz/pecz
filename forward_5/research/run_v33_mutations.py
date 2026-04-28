#!/usr/bin/env python3
"""V33 Profit Mutation Run — Targeted mutations of V33 for profitability.
V33 is our first 10w-WF champion (58.3 robustness, +0.008% OOS).
Goal: Mutate exit + volume filter for higher OOS return while keeping WF robustness.
"""
import json, sys, time, urllib.request, os
from pathlib import Path
from datetime import datetime

RESEARCH_DIR = Path(__file__).parent
sys.path.insert(0, str(RESEARCH_DIR.parent / "executor"))
sys.path.insert(0, str(RESEARCH_DIR))

from walk_forward_gate import run_wf_on_candidate

API_URL = os.environ.get("OLLAMA_API_URL", "http://172.17.0.1:32771/v1/chat/completions")
API_KEY = os.environ.get("OLLAMA_API_KEY", "ollama-cloud")
MODEL = os.environ.get("GENERATOR_MODEL", "deepseek-v4-pro:cloud")

V33_ENTRY = "close < bb_lower_14 AND rsi_14 < 30 AND close > ema_50 AND volume > volume_sma_20"
V33_EXIT = {"trailing_stop_pct": 2.2, "stop_loss_pct": 3.0, "max_hold_bars": 18}

ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
DATA_PATH = RESEARCH_DIR / "data"
DATA_FILE_MAP = {a: f"{a}USDT_1h_full.parquet" for a in ASSETS}
PERIODS = {"2024": ("2024-01-01", "2024-12-31"), "2yr": ("2023-01-01", "2024-12-31")}
HOF_DIR = RESEARCH_DIR / "runs" / "evolution_v7"

def call_llm(prompt, temperature=0.4):
    extra = {}
    if "deepseek" in MODEL.lower():
        extra["reasoning_effort"] = "high"
    payload = json.dumps({
        "model": MODEL, "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature, "max_tokens": 2048, **extra
    }).encode()
    req = urllib.request.Request(API_URL, data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
            msg = data["choices"][0]["message"]
            content = msg.get("content", "")
            if not content.strip() and msg.get("reasoning", "").strip():
                content = msg["reasoning"]
            return content
    except Exception as e:
        print(f"  ⚠️ LLM error: {e}")
        return ""

def backtest_strategy(name, entry, exit_config):
    """Run walk-forward on a strategy, return result dict."""
    try:
        r = run_wf_on_candidate(name=name, entry=entry, exit_config=exit_config, n_windows=10)
        return r
    except Exception as e:
        return {"error": str(e), "name": name}


def evaluate_wf(result):
    """Extract WF metrics from run_wf_on_candidate result."""
    robustness = result.get("robustness_score", 0)
    avg_oos = result.get("avg_oos_return", 0)
    profitable = result.get("profitable_assets", "0/0")
    is_score = result.get("is_score", 0)
    return {
        "wf_robustness_10w": round(robustness, 1),
        "wf_passed_10w": robustness >= 50,
        "avg_oos_return": round(avg_oos, 4),
        "profitable_10w": profitable,
        "is_score": round(is_score, 4) if isinstance(is_score, (int, float)) else 0,
    }

print("=" * 70)
print("V33 PROFIT MUTATION RUN")
print(f"Parent: V33_MR_BB_RSI14_30_VOL (WF10w=58.3, OOS=+0.008%)")
print(f"Model: {MODEL}")
print(f"Goal: Maximize OOS return while keeping WF10w >= 50")
print("=" * 70)

# Phase 1: LLM-generated profit mutations
print("\n📝 Phase 1: LLM Profit Mutations (15 candidates)")
MUTATION_PROMPT = f"""You are a crypto trading strategy optimizer. We have a Mean Reversion strategy that passes 10-window walk-forward but has very low profitability (+0.008% OOS).

BASE STRATEGY:
- Entry: {V33_ENTRY}
- Exit: trailing_stop_pct=2.2, stop_loss_pct=3.0, max_hold_bars=18

PROBLEMS:
- Trailing stop too tight (2.2%) — exits before move completes
- Max hold too short (18 bars) — cuts winners early  
- Volume filter threshold too low (1.0x SMA) — doesn't filter enough noise
- OOS return is +0.008% — basically zero

YOUR TASK: Generate 3 MUTATED variants that MAXIMIZE OOS PROFITABILITY while keeping the core Mean Reversion logic.

RULES:
- Keep the base entry structure (bb_lower + rsi + ema + volume)
- You may adjust: bb period, rsi period/threshold, ema period, volume multiplier
- You may add ONE additional filter (e.g. adx, atr, regime)
- Focus on EXIT optimization: wider trailing stops, longer holds, regime-aware exits
- Each variant MUST have different exit parameters

OUTPUT FORMAT (one per line, no other text):
NAME|entry_condition|trailing_stop_pct,stop_loss_pct,max_hold_bars

Example:
V33_WiderTrail|close < bb_lower_14 AND rsi_14 < 30 AND close > ema_50 AND volume > volume_sma_20 * 1.2|3.5,4.0,36"""

all_candidates = []

for batch in range(5):  # 5 batches × 3 = 15 candidates
    print(f"\n  Batch {batch+1}/5...")
    response = call_llm(MUTATION_PROMPT, temperature=0.5 + batch * 0.1)
    
    for line in response.strip().split("\n"):
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) < 3:
            continue
        name = parts[0].strip()
        entry = parts[1].strip()
        exit_parts = parts[2].strip().split(",")
        
        if len(exit_parts) >= 3:
            try:
                exit_config = {
                    "trailing_stop_pct": float(exit_parts[0]),
                    "stop_loss_pct": float(exit_parts[1]),
                    "max_hold_bars": int(exit_parts[2])
                }
                all_candidates.append({"name": name, "entry_condition": entry, "exit_config": exit_config})
                print(f"  ✅ Parsed: {name}")
            except:
                print(f"  ⚠️ Parse error: {line[:60]}")

# Phase 2: Systematic exit grid on V33 entry
print(f"\n📝 Phase 2: Systematic Exit Grid (16 combinations)")

trail_values = [2.5, 3.0, 3.5, 4.0]
hold_values = [24, 36, 48, 72]
sl_value = 4.0  # Wider SL to let trades breathe

for trail in trail_values:
    for hold in hold_values:
        name = f"V33_Grid_T{trail}_H{hold}"
        exit_config = {"trailing_stop_pct": trail, "stop_loss_pct": sl_value, "max_hold_bars": hold}
        all_candidates.append({"name": name, "entry_condition": V33_ENTRY, "exit_config": exit_config})

print(f"  Added {len(trail_values) * len(hold_values)} grid combinations")

# Phase 3: Volume threshold variations
print(f"\n📝 Phase 3: Volume Filter Variations (6 combinations)")

vol_multipliers = [1.0, 1.2, 1.5, 1.8, 2.0, 2.5]
for vm in vol_multipliers:
    if vm == 1.0:
        entry = V33_ENTRY
    else:
        entry = f"close < bb_lower_14 AND rsi_14 < 30 AND close > ema_50 AND volume > volume_sma_20 * {vm}"
    name = f"V33_Vol{vm}x"
    all_candidates.append({"name": name, "entry_condition": entry, "exit_config": {"trailing_stop_pct": 3.0, "stop_loss_pct": 4.0, "max_hold_bars": 36}})

print(f"  Added {len(vol_multipliers)} volume variations")

# Total
print(f"\n📊 Total candidates: {len(all_candidates)}")
print(f"  LLM mutations: {sum(1 for c in all_candidates if not c['name'].startswith('V33_Grid') and not c['name'].startswith('V33_Vol'))}")
print(f"  Exit grid: {sum(1 for c in all_candidates if c['name'].startswith('V33_Grid'))}")
print(f"  Volume variations: {sum(1 for c in all_candidates if c['name'].startswith('V33_Vol'))}")

# Evaluate all
print(f"\n🔬 Evaluating {len(all_candidates)} candidates...")
results = []

for i, cand in enumerate(all_candidates):
    name = cand["name"]
    entry = cand["entry_condition"]
    exit_config = cand["exit_config"]
    
    print(f"\n  [{i+1}/{len(all_candidates)}] {name}")
    print(f"    Entry: {entry}")
    print(f"    Exit:  T={exit_config['trailing_stop_pct']}% SL={exit_config['stop_loss_pct']}% MaxH={exit_config['max_hold_bars']}b")
    
    wf_result = backtest_strategy(name, entry, exit_config)
    eval_result = evaluate_wf(wf_result)
    
    is_avg = eval_result.get("is_score", 0)
    
    result = {
        "name": name, "entry_condition": entry, "exit_config": exit_config,
        **eval_result, "parent": "V33"
    }
    results.append(result)
    
    status = "✅" if eval_result["wf_passed_10w"] else "❌"
    print(f"    WF10w={eval_result['wf_robustness_10w']} {status} | IS={is_avg:.4f} | OOS={eval_result['avg_oos_return']}% | Profit={eval_result['profitable_10w']}")

# Sort by OOS return (profit focus!)
results.sort(key=lambda x: x.get("avg_oos_return", -999), reverse=True)

# Save results
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
results_file = HOF_DIR / f"v33_mutation_results_{timestamp}.json"
with open(results_file, 'w') as f:
    json.dump({"parent": "V33_MR_BB_RSI14_30_VOL", "timestamp": timestamp, "model": MODEL,
               "total_candidates": len(results), "results": results}, f, indent=2, default=str)

# Summary
print("\n" + "=" * 70)
print("🏆 TOP 10 BY OOS RETURN")
print("=" * 70)
for i, r in enumerate(results[:10]):
    status = "✅" if r.get("wf_passed_10w") else "❌"
    print(f"  {i+1}. {r['name']:<35} WF10w={r['wf_robustness_10w']:>5} {status} | IS={r.get('is_score',0):>6.3f} | OOS={r['avg_oos_return']:>+.4f}% | Profit={r['profitable_10w']}")

wf_passed = [r for r in results if r.get("wf_passed_10w")]
print(f"\n📊 WF10w PASSED: {len(wf_passed)}/{len(results)}")
if wf_passed:
    best = max(wf_passed, key=lambda x: x["avg_oos_return"])
    print(f"🏆 Best WF-passed: {best['name']} | OOS={best['avg_oos_return']:+.4f}% | WF={best['wf_robustness_10w']}")
    print(f"   Entry: {best['entry_condition']}")
    print(f"   Exit:  {best['exit_config']}")

print(f"\n💾 Results saved to {results_file}")