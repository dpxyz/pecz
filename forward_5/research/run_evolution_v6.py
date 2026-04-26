#!/usr/bin/env python3
"""
Foundry Evolution V6 — True Evolutionary Algorithm

Fitness = WF Robustness (not IS score)
Elitism: Top-K survive unchanged
Mutation: Small changes to existing champions
Crossover: Combine entry/exit from different strategies
Selection: Only WF-passed strategies advance to next generation

Uses V5's proven BacktestEngine + DSL translator for IS evaluation,
and walk_forward_gate for OOS validation.
"""

import json
import os
import sys
import time
import random
import re
import urllib.request
from datetime import datetime as dt
from datetime import datetime
from pathlib import Path

import polars as pl

# Add research paths
RESEARCH_DIR = Path(__file__).parent
sys.path.insert(0, str(RESEARCH_DIR))
sys.path.insert(0, str(RESEARCH_DIR / "backtest"))
sys.path.insert(0, str(RESEARCH_DIR / "strategy_lab"))

from dsl_translator import translate_candidate_with_name
from backtest.backtest_engine import BacktestEngine, BacktestResult
from walk_forward_gate import build_strategy_func, run_wf_on_candidate

# ============================================================================
# CONFIG
# ============================================================================

GENERATIONS = 8
POPULATION_PER_GEN = 6  # 4 mutations + 1 crossover + 1 fresh
ELITISM = 2  # Top-K always survive
WF_WINDOWS = 5

API_URL = os.environ.get("OLLAMA_API_URL", "http://172.17.0.1:32771/v1/chat/completions")
API_KEY = os.environ.get("OLLAMA_API_KEY", "ollama-cloud")
MODEL = os.environ.get("GENERATOR_MODEL", "gemma4:31b-cloud")

ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]
DATA_PATH = RESEARCH_DIR / "data"
DATA_FILE_MAP = {a: f"{a}_1h_full.parquet" for a in ASSETS}
PERIODS = {
    "2024": ("2024-01-01", "2024-12-31"),
    "2yr": ("2023-01-01", "2024-12-31"),
}

HOF_FILE = RESEARCH_DIR / "runs" / "evolution_v6" / "evolution_v6_hof.json"
HOF_FILE.parent.mkdir(parents=True, exist_ok=True)

# Seeds: V32 (WF champion) + V17 (IS champion)
SEED_STRATEGIES = [
    {
        "name": "V32_MR_BB_FAST_RSI_EMA50",
        "entry_condition": "close < bb_lower_14 AND rsi_7 < 25 AND close > ema_50",
        "exit_config": {"trailing_stop_pct": 2.2, "stop_loss_pct": 3.0, "max_hold_bars": 18},
        "is_score": 1.28,
        "wf_robustness": 88.3,
        "wf_passed": True,
        "generation": 0,
    },
    {
        "name": "V17_Mid_Target_Exit",
        "entry_condition": "close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200",
        "exit_config": {"trailing_stop_pct": 1.5, "stop_loss_pct": 3.0, "max_hold_bars": 36},
        "is_score": 4.88,
        "wf_robustness": 30.0,
        "wf_passed": False,
        "generation": 0,
    },
]


# ============================================================================
# DATA LOADING
# ============================================================================

def load_df(asset: str, start: str, end: str) -> pl.DataFrame:
    data_file = DATA_PATH / DATA_FILE_MAP[asset]
    df = pl.scan_parquet(str(data_file)).collect()
    start_dt = dt.fromisoformat(start + "T00:00:00+00:00")
    end_dt = dt.fromisoformat(end + "T23:59:59+00:00")
    return df.filter(
        (pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt)
    )


def candidate_to_strategy_spec(candidate: dict) -> dict:
    return {
        'strategy': {
            'name': candidate.get('name', 'KI_Unknown'),
            'type': candidate.get('type', 'mean_reversion').lower().replace('-', '_').replace(' ', '_'),
            'indicators': candidate.get('indicators', []),
            'entry': {'condition': candidate.get('entry_condition', '')},
            'exit': candidate.get('exit_config', {}),
        }
    }


# ============================================================================
# LLM CALLS
# ============================================================================

MUTATION_PROMPT = """Du bist ein evolutionärer Quant-Stratege. MUTIERE die gegebene Strategie leicht.

⚠️ FITNESS = Walk-Forward Robustness, NICHT IS-Score!
- V32 (IS 1.28, WF 88.3) ist CHAMPION weil OOS robust
- V17 (IS 4.88, WF 30.0) ist FAILED weil overfitted
- Hoher IS = overfitted. Niedriger IS + hoher WF = champion.

MUTATIONS-REGELN:
- Ändere MAXIMAL 1-2 Parameter pro Mutation
- BB: period 10-30, RSI: period 5-21, threshold 20-40, EMA: period 50-200
- Trail: 1.5-3.0%, SL: 2.0-4.0%, Max Hold: 12-48h
- KEINE komplett neuen Indikatoren — nur Parameter-Mutationen

ELTERN-STRATEGIE:
Name: {parent_name}
Entry: {parent_entry}
Exit: {parent_exit}
WF Robustness: {parent_wf}
IS Score: {parent_is}

Generiere GENAU EINE Mutation als JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {{"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}}}"""

CROSSOVER_PROMPT = """Du bist ein evolutionärer Quant-Stratege. CROSSOVER zwei Strategien zu einer neuen.

⚠️ FITNESS = Walk-Forward Robustness, NICHT IS-Score!

ELTER A:
Name: {parent_a_name}
Entry: {parent_a_entry}
Exit: {parent_a_exit}
WF: {parent_a_wf}

ELTER B:
Name: {parent_b_name}
Entry: {parent_b_entry}
Exit: {parent_b_exit}
WF: {parent_b_wf}

CROSSOVER: Nimm Entry von einem + Exit vom anderen, oder mische Parameter.
Generiere GENAU EINE Crossover-Strategie als JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {{"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}}}"""

FRESH_PROMPT = """Generiere eine MEAN-REVERSION-Strategie für 1h Crypto.

⚠️ Lektion: IS-Score lügt! Niedriger IS + hoher WF = besser.
Beste bekannte Strategie: close < bb_lower_14 AND rsi_7 < 25 AND close > ema_50 (WF 88.3)

Probiere etwas ANDERES als BB+RSI:
- Stochastic %K < 20 AND %D < 30
- Williams %R < -80
- Price drops: close < close[-3] * 0.97
- Volume spike: volume > sma_20 * 1.5

Generiere GENAU EINE Strategie als JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {{"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}}}"""


def call_llm(prompt: str) -> str:
    """Call LLM via OpenAI-compatible API (gemma4)."""
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1024,
    })
    
    req = urllib.request.Request(
        API_URL,
        data=payload.encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  ⚠️ LLM API error: {e}")
        return ""


def parse_strategy_response(text: str) -> dict | None:
    """Parse JSON strategy from LLM response."""
    json_match = re.search(r'\{[^{}]*\{[^{}]*\}[^{}]*\}', text, re.DOTALL)
    if not json_match:
        json_match = re.search(r'\{[^{}]+\}', text)
    if not json_match:
        return None
    
    try:
        data = json.loads(json_match.group())
        if "entry_condition" in data and "exit_config" in data:
            return data
    except json.JSONDecodeError:
        pass
    
    try:
        fixed = re.sub(r',\s*}', '}', json_match.group())
        fixed = re.sub(r',\s*]', ']', fixed)
        data = json.loads(fixed)
        if "entry_condition" in data and "exit_config" in data:
            return data
    except:
        pass
    
    return None


# ============================================================================
# EVALUATION
# ============================================================================

def run_is_backtest(entry_condition: str, exit_config: dict) -> dict | None:
    """Run in-sample backtest using V5's proven pipeline."""
    try:
        candidate = {
            "name": "eval_candidate",
            "entry_condition": entry_condition,
            "exit_config": exit_config,
            "indicators": [],
            "type": "mean_reversion",
        }
        strategy_spec = candidate_to_strategy_spec(candidate)
        _, strategy_func = translate_candidate_with_name(strategy_spec)
        
        engine = BacktestEngine(data_path=str(DATA_PATH))
        
        all_returns = []
        all_dds = []
        all_cls = []
        all_trades = []
        profitable = 0
        
        for asset in ASSETS:
            for period_name, (start, end) in PERIODS.items():
                try:
                    df = load_df(asset, start, end)
                    if len(df) < 50:
                        continue
                    
                    result = engine.run(
                        strategy_name="eval_candidate",
                        strategy_func=strategy_func,
                        params={},
                        symbol=asset,
                        timeframe="1h",
                        exit_config=exit_config,
                        df=df,
                    )
                    
                    if result.trade_count > 0:
                        all_returns.append(result.net_return)
                        all_dds.append(result.max_drawdown)
                        all_cls.append(result.max_consecutive_losses)
                        all_trades.append(result.trade_count)
                        if result.net_return > 0:
                            profitable += 1
                except Exception:
                    continue
        
        if not all_returns:
            return None
        
        n = len(all_returns)
        total_return = sum(all_returns) / n
        avg_dd = sum(all_dds) / n
        max_cl = max(all_cls)
        min_trades = min(all_trades)
        
        if total_return > 0 and avg_dd > 0:
            score = (total_return / avg_dd) * (profitable / 12) * min(1, min_trades / 5)
        else:
            score = 0
            
        return {
            "avg_return": round(total_return, 2),
            "avg_dd": round(avg_dd, 1),
            "max_cl": max_cl,
            "min_trades": min_trades,
            "profitable_assets": f"{profitable}/12",
            "is_score": round(score, 2),
        }
    except Exception as e:
        print(f"  ⚠️ IS backtest error: {e}")
        return None


def run_wf_validation(entry_condition: str, exit_config: dict) -> dict | None:
    """Run walk-forward validation using the WF gate."""
    try:
        strategy_func, parseable = build_strategy_func(entry_condition)
        if not parseable or strategy_func is None:
            return {
                "wf_robustness": 0.0,
                "wf_passed": False,
                "wf_profitable_assets": "0/6",
                "avg_oos_return": 0.0,
                "tier": "NEEDS_REVIEW" if not parseable else "PARSE_ERROR",
            }
        
        result = run_wf_on_candidate(
            name="eval_candidate",
            entry=entry_condition,
            exit_config=exit_config,
            n_windows=WF_WINDOWS,
        )
        
        return {
            "wf_robustness": result.get("robustness_score", 0),
            "wf_passed": result.get("passed", False),
            "wf_profitable_assets": result.get("profitable_assets", "0/6"),
            "avg_oos_return": result.get("avg_oos_return", 0),
            "tier": result.get("tier", "?"),
        }
    except Exception as e:
        print(f"  ⚠️ WF validation error: {e}")
        return None


# ============================================================================
# HOF MANAGEMENT
# ============================================================================

def load_hof() -> list[dict]:
    if HOF_FILE.exists():
        try:
            data = json.loads(HOF_FILE.read_text())
            return data.get("hof", [])
        except:
            pass
    return []


def save_hof(hof: list[dict]):
    hof.sort(key=lambda x: (x.get("wf_robustness", 0), x.get("is_score", 0)), reverse=True)
    data = {
        "updated": datetime.now().isoformat(),
        "champion": hof[0] if hof else None,
        "hof": hof[:20],
    }
    HOF_FILE.write_text(json.dumps(data, indent=2))


# ============================================================================
# EVOLUTION OPERATORS
# ============================================================================

def select_parent(hof: list[dict]) -> dict:
    """Select parent using fitness-proportionate selection (WF robustness)."""
    weights = [max(s.get("wf_robustness", 1), 1) for s in hof]
    total = sum(weights)
    r = random.random() * total
    cumulative = 0
    for i, w in enumerate(weights):
        cumulative += w
        if r <= cumulative:
            return hof[i]
    return hof[0]


def mutate(parent: dict) -> dict | None:
    prompt = MUTATION_PROMPT.format(
        parent_name=parent["name"],
        parent_entry=parent["entry_condition"],
        parent_exit=json.dumps(parent["exit_config"]),
        parent_wf=parent.get("wf_robustness", "?"),
        parent_is=parent.get("is_score", "?"),
    )
    
    response = call_llm(prompt)
    child = parse_strategy_response(response)
    
    if child:
        child["generation"] = parent.get("generation", 0) + 1
        child["parent"] = parent["name"]
        child["mutation_type"] = "mutate"
    
    return child


def crossover(parent_a: dict, parent_b: dict) -> dict | None:
    prompt = CROSSOVER_PROMPT.format(
        parent_a_name=parent_a["name"],
        parent_a_entry=parent_a["entry_condition"],
        parent_a_exit=json.dumps(parent_a["exit_config"]),
        parent_a_wf=parent_a.get("wf_robustness", "?"),
        parent_b_name=parent_b["name"],
        parent_b_entry=parent_b["entry_condition"],
        parent_b_exit=json.dumps(parent_b["exit_config"]),
        parent_b_wf=parent_b.get("wf_robustness", "?"),
    )
    
    response = call_llm(prompt)
    child = parse_strategy_response(response)
    
    if child:
        child["generation"] = max(parent_a.get("generation", 0), parent_b.get("generation", 0)) + 1
        child["parent"] = f"{parent_a['name']} x {parent_b['name']}"
        child["mutation_type"] = "crossover"
    
    return child


def evaluate_candidate(candidate: dict) -> dict:
    """Full evaluation: IS backtest + WF validation."""
    print(f"  🧬 Evaluating: {candidate.get('name', '?')}")
    print(f"     Entry: {candidate['entry_condition']}")
    print(f"     Exit: {json.dumps(candidate['exit_config'])}")
    
    # Step 1: IS backtest
    is_result = run_is_backtest(candidate["entry_condition"], candidate["exit_config"])
    if is_result:
        candidate.update(is_result)
        print(f"     IS: {is_result['is_score']:.2f} | R={is_result['avg_return']:+.2f}% | DD={is_result['avg_dd']:.1f}% | {is_result['profitable_assets']}")
    else:
        candidate["is_score"] = 0
        print("     IS: FAILED — strategy not parseable or no trades")
    
    # Step 2: WF validation
    wf_result = run_wf_validation(candidate["entry_condition"], candidate["exit_config"])
    if wf_result:
        candidate.update(wf_result)
        status = "✅ PASS" if wf_result["wf_passed"] else "❌ FAIL"
        print(f"     WF: {status} | Robustness={wf_result['wf_robustness']:.1f} | OOS={wf_result.get('avg_oos_return', 0):+.2f}% | {wf_result['wf_profitable_assets']}")
    else:
        candidate["wf_robustness"] = 0
        candidate["wf_passed"] = False
        print("     WF: ERROR")
    
    return candidate


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("FOUNDRY EVOLUTION V6 — True Evolutionary Algorithm")
    print(f"Generations: {GENERATIONS} | Population: {POPULATION_PER_GEN} | Elitism: {ELITISM}")
    print("Fitness = WF Robustness (not IS score!)")
    print("=" * 70)
    
    hof = load_hof()
    if not hof:
        print("\n🌱 Seeding HOF with V32 + V17...")
        hof = list(SEED_STRATEGIES)
        save_hof(hof)
    
    print(f"\n🏆 Starting HOF: {len(hof)} strategies")
    for s in hof:
        print(f"   {s['name']}: WF={s.get('wf_robustness', '?')}, IS={s.get('is_score', '?')}")
    
    all_results = []
    
    for gen in range(1, GENERATIONS + 1):
        print(f"\n{'='*70}")
        print(f"GENERATION {gen}/{GENERATIONS}")
        print(f"{'='*70}")
        
        children = []
        
        # 1. Mutations from top parents (weighted by fitness)
        n_mutations = POPULATION_PER_GEN - 2
        for i in range(n_mutations):
            parent = select_parent(hof)
            print(f"\n🧬 Mutation {i+1}/{n_mutations} from {parent['name']} (WF={parent.get('wf_robustness', '?')})")
            child = mutate(parent)
            if child:
                children.append(child)
            else:
                print("  ⚠️ LLM parse error, skipping")
        
        # 2. Crossover of top 2
        if len(hof) >= 2:
            print(f"\n🔀 Crossover: {hof[0]['name']} x {hof[1]['name']}")
            child = crossover(hof[0], hof[1])
            if child:
                children.append(child)
        
        # 3. Fresh exploration
        print(f"\n🎲 Fresh exploration candidate")
        response = call_llm(FRESH_PROMPT)
        child = parse_strategy_response(response)
        if child:
            child["generation"] = gen
            child["parent"] = "fresh"
            child["mutation_type"] = "fresh"
            children.append(child)
        
        # 4. Evaluate all children
        print(f"\n{'='*70}")
        print(f"EVALUATING {len(children)} CANDIDATES")
        print(f"{'='*70}")
        
        evaluated = []
        for child in children:
            result = evaluate_candidate(child)
            evaluated.append(result)
            all_results.append(result)
        
        # 5. Update HOF (keep elite + any child that improves HOF)
        hof_sorted = sorted(hof, key=lambda x: (x.get("wf_robustness", 0), x.get("is_score", 0)), reverse=True)
        new_hof = hof_sorted[:ELITISM]  # Keep top elite
        
        for child in evaluated:
            if child.get("wf_robustness", 0) > 0:
                if len(new_hof) < 20 or child["wf_robustness"] > new_hof[-1].get("wf_robustness", 0):
                    new_hof.append(child)
        
        new_hof.sort(key=lambda x: (x.get("wf_robustness", 0), x.get("is_score", 0)), reverse=True)
        hof = new_hof[:20]
        save_hof(hof)
        
        # Generation summary
        print(f"\n📊 Generation {gen} Summary:")
        print(f"   Evaluated: {len(evaluated)} candidates")
        wf_passed = [c for c in evaluated if c.get("wf_passed")]
        print(f"   WF-Passed: {len(wf_passed)}/{len(evaluated)}")
        if wf_passed:
            best = max(wf_passed, key=lambda x: x.get("wf_robustness", 0))
            print(f"   🎉 Best this gen: {best['name']} (WF={best['wf_robustness']:.1f})")
        print(f"\n🏆 Current HOF Top 5:")
        for i, s in enumerate(hof[:5]):
            wf_mark = "✅" if s.get("wf_passed") else "❌"
            print(f"   {i+1}. {s['name']}: WF={s.get('wf_robustness', 0):.1f} {wf_mark} | IS={s.get('is_score', 0):.2f}")
    
    # Final summary
    print(f"\n{'='*70}")
    print("FINAL HALL OF FAME (sorted by WF Robustness)")
    print(f"{'='*70}")
    for i, s in enumerate(hof):
        wf_mark = "✅ PASSED" if s.get("wf_passed") else "❌ FAILED"
        print(f"{i+1:2d}. {s['name']:45s} WF={s.get('wf_robustness', 0):5.1f} | IS={s.get('is_score', 0):5.2f} | {wf_mark}")
    
    v32_wf = 88.3
    champions = [s for s in hof if s.get("wf_robustness", 0) > v32_wf]
    if champions:
        print(f"\n🎉 NEW CHAMPION(S) beating V32 (WF={v32_wf}):")
        for c in champions:
            print(f"   {c['name']}: WF={c['wf_robustness']:.1f}, IS={c.get('is_score', 0):.2f}")
    else:
        print(f"\n⚠️  No new champion. V32 (WF={v32_wf}) remains best.")
    
    # Save full results
    results_file = HOF_FILE.parent / f"evolution_v6_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results_file.write_text(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "generations": GENERATIONS,
        "population_per_gen": POPULATION_PER_GEN,
        "all_results": all_results,
        "hof": hof,
        "champion": hof[0] if hof else None,
    }, indent=2))
    print(f"\n💾 Results saved to {results_file}")


if __name__ == "__main__":
    main()