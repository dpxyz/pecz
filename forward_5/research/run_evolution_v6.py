#!/usr/bin/env python3
"""
Foundry Evolution V6 — True Evolutionary Algorithm

Fitness = WF Robustness (not IS score)
Elitism: Top-K survive unchanged
Mutation: Small changes to existing champions
Crossover: Combine entry/exit from different strategies
Selection: Only WF-passed strategies advance to next generation

Pipeline per generation:
1. Load HOF (seed with V32 if empty)
2. Select parents (weighted by fitness)
3. Mutate each parent → child
4. Crossover top-2 parents → child
5. WF-Gate all children
6. Replace HOF: keep elite + any child that beats worst HOF member
7. Repeat
"""

import json
import os
import sys
import time
import random
import re
from datetime import datetime
from pathlib import Path

# Add research paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "forward_v5" / "research"))
sys.path.insert(0, str(Path(__file__).parent / "strategy_lab"))

from backtest.backtest_engine import BacktestEngine

# ============================================================================
# CONFIG
# ============================================================================

GENERATIONS = 8
POPULATION_PER_GEN = 6  # 4 mutations + 1 crossover + 1 fresh
ELITISM = 2  # Top-K always survive
WF_WINDOWS = 5
WF_THRESHOLD = 50.0  # Robustness needed to "pass"
PROFITABLE_THRESHOLD = 3  # OOS assets profitable needed

ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
HOF_FILE = Path(__file__).parent / "runs" / "evolution_v6" / "evolution_v6_hof.json"
HOF_FILE.parent.mkdir(parents=True, exist_ok=True)

# V32 — our WF champion (88.3 robustness, 5/6 OOS profitable)
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
]

# V17 as reference (IS-champion but WF-failed)
V17_REFERENCE = {
    "name": "V17_Mid_Target_Exit",
    "entry_condition": "close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200",
    "exit_config": {"trailing_stop_pct": 1.5, "stop_loss_pct": 3.0, "max_hold_bars": 36},
    "is_score": 4.88,
    "wf_robustness": 30.0,
    "wf_passed": False,
}

# ============================================================================
# MUTATION OPERATORS
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
- Exit-Varianten: engere/weitere Trails, kürzere/längere Haltezeiten
- Entry-Varianten: andere RSI-Schwelle, anderer BB-Zeitraum, anderer EMA-Filter
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

ELTER A (Entry-Fokus):
Name: {parent_a_name}
Entry: {parent_a_entry}
Exit: {parent_a_exit}
WF: {parent_a_wf}

ELTER B (Exit-Fokus):
Name: {parent_b_name}
Entry: {parent_b_entry}
Exit: {parent_b_exit}
WF: {parent_b_wf}

CROSSOVER: Nimm das BESSERE Entry- oder Exit-Teil und kombiniere mit einem parameter-angepassten Gegenpart.
Oder nimm Entry von A + Exit von B. Oder mische die Parameter.

Generiere GENAU EINE Crossover-Strategie als JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {{"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}}}"""


def call_llm(prompt: str) -> str:
    """Call LLM via ollama."""
    import subprocess
    result = subprocess.run(
        ["ollama", "run", "kimi-k2.5:cloud", prompt],
        capture_output=True, text=True, timeout=120
    )
    return result.stdout.strip()


def parse_strategy_response(text: str) -> dict | None:
    """Parse JSON strategy from LLM response."""
    # Find JSON block
    json_match = re.search(r'\{[^{}]*\{[^{}]*\}[^{}]*\}', text, re.DOTALL)
    if not json_match:
        # Try simpler: single-level JSON
        json_match = re.search(r'\{[^{}]+\}', text)
    if not json_match:
        return None
    
    try:
        data = json.loads(json_match.group())
        if "entry_condition" in data and "exit_config" in data:
            return data
    except json.JSONDecodeError:
        pass
    
    # Try fixing common issues
    try:
        # Remove trailing commas
        fixed = re.sub(r',\s*}', '}', json_match.group())
        fixed = re.sub(r',\s*]', ']', fixed)
        data = json.loads(fixed)
        if "entry_condition" in data and "exit_config" in data:
            return data
    except:
        pass
    
    return None


# ============================================================================
# BACKTEST + WF GATE
# ============================================================================

def run_is_backtest(entry_condition: str, exit_config: dict) -> dict | None:
    """Run in-sample backtest for a strategy."""
    try:
        engine = BacktestEngine(
            entry_condition=entry_condition,
            exit_config=exit_config,
            assets=ASSETS,
        )
        results = engine.run()
        
        if not results:
            return None
            
        total_return = sum(r.get("return_pct", 0) for r in results.values()) / len(results)
        avg_dd = sum(r.get("max_drawdown_pct", 0) for r in results.values()) / len(results)
        max_cl = max(r.get("consecutive_losses", 0) for r in results.values())
        profitable = sum(1 for r in results.values() if r.get("return_pct", 0) > 0)
        min_trades = min(r.get("total_trades", 0) for r in results.values())
        
        # IS Score (same formula as before)
        if total_return > 0 and avg_dd > 0:
            score = (total_return / avg_dd) * (profitable / 6) * min(1, min_trades / 5)
        else:
            score = 0
            
        return {
            "avg_return": round(total_return, 2),
            "avg_dd": round(avg_dd, 1),
            "max_cl": max_cl,
            "min_trades": min_trades,
            "profitable_assets": f"{profitable}/6",
            "is_score": round(score, 2),
        }
    except Exception as e:
        print(f"  ⚠️ IS backtest error: {e}")
        return None


def run_wf_validation(entry_condition: str, exit_config: dict) -> dict | None:
    """Run walk-forward validation using the WF gate."""
    try:
        from walk_forward_gate import build_strategy_func, validate_strategy
        
        strategy_func, parseable = build_strategy_func(entry_condition)
        if not parseable or strategy_func is None:
            return {
                "wf_robustness": 0.0,
                "wf_passed": False,
                "wf_profitable_assets": "0/6",
                "avg_oos_return": 0.0,
                "tier": "NEEDS_REVIEW" if not parseable else "PARSE_ERROR",
            }
        
        # Run WF validation
        result = validate_strategy(
            strategy_func=strategy_func,
            name="candidate",
            is_score=0,  # placeholder
            entry_condition=entry_condition,
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
    """Load Hall of Fame from file."""
    if HOF_FILE.exists():
        try:
            data = json.loads(HOF_FILE.read_text())
            return data.get("hof", [])
        except:
            pass
    return []


def save_hof(hof: list[dict]):
    """Save Hall of Fame to file."""
    # Sort by WF robustness (descending), then IS score
    hof.sort(key=lambda x: (x.get("wf_robustness", 0), x.get("is_score", 0)), reverse=True)
    
    data = {
        "updated": datetime.now().isoformat(),
        "champion": hof[0] if hof else None,
        "hof": hof[:20],  # Keep top 20
    }
    HOF_FILE.write_text(json.dumps(data, indent=2))


# ============================================================================
# EVOLUTION LOOP
# ============================================================================

def select_parent(hof: list[dict]) -> dict:
    """Select parent using fitness-proportionate selection (WF robustness)."""
    # Weight by WF robustness (minimum 1 to avoid zero weights)
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
    """Mutate a parent strategy via LLM."""
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
    """Crossover two parent strategies via LLM."""
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
        print("     IS: FAILED")
    
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
    
    # Initialize HOF
    hof = load_hof()
    if not hof:
        print("\n🌱 Seeding HOF with V32 champion...")
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
        
        # 1. Mutations from top parents
        n_mutations = POPULATION_PER_GEN - 2  # reserve 2 for crossover + fresh
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
        
        # 3. One fresh candidate (exploration)
        print(f"\n🎲 Fresh exploration candidate")
        fresh_prompt = """Generiere eine MEAN-REVERSION-Strategie für 1h Crypto.
        
⚠️ Lektion: IS-Score lügt! Niedriger IS + hoher WF = besser.
Die beste bekannte Strategie: close < bb_lower_14 AND rsi_7 < 25 AND close > ema_50 (WF 88.3)

Probiere etwas ANDERES als BB+RSI:
- Stochastic %K < 20 AND %D < 30
- Williams %R < -80
- Price drops: close < close[-3] * 0.97 (3% drop in 3 bars)
- Volume spike: volume > sma_20 * 1.5

Generiere GENAU EINE Strategie als JSON:
{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}"""
        
        response = call_llm(fresh_prompt)
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
        
        # 5. Update HOF
        # Keep elite + any child that improves HOF
        hof_sorted = sorted(hof, key=lambda x: (x.get("wf_robustness", 0), x.get("is_score", 0)), reverse=True)
        new_hof = hof_sorted[:ELITISM]  # Keep top elite
        
        for child in evaluated:
            if child.get("wf_robustness", 0) > 0:  # At least has WF data
                # Add if HOF not full or better than worst
                if len(new_hof) < 20 or child["wf_robustness"] > new_hof[-1].get("wf_robustness", 0):
                    new_hof.append(child)
        
        # Re-sort and trim
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
    
    # Compare with V32
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