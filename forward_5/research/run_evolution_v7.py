#!/usr/bin/env python3
"""
Foundry Evolution V7 — Three-Phase Evolutionary Search

Phase 1: EXPLORATION (40%) — Free search, temp 0.3 + 0.7
Phase 2: EVOLUTION (40%) — Mutate + crossover HOF champions
Phase 3: HARD CHECK (20%) — 10-window WF on top-3

Fitness = WF Robustness. HOF is persistent across runs.
"""

import json
import os
import sys
import time
import random
import re
import urllib.request
from datetime import datetime
from pathlib import Path

import polars as pl

RESEARCH_DIR = Path(__file__).parent
sys.path.insert(0, str(RESEARCH_DIR))
sys.path.insert(0, str(RESEARCH_DIR / "backtest"))
sys.path.insert(0, str(RESEARCH_DIR / "strategy_lab"))

from dsl_translator import translate_candidate_with_name
from backtest.backtest_engine import BacktestEngine
from walk_forward_gate import build_strategy_func, run_wf_on_candidate

# ============================================================================
# CONFIG
# ============================================================================

N_EXPLORATION_CONSERVATIVE = 5  # temp 0.3
N_EXPLORATION_CREATIVE = 5      # temp 0.7
N_MUTATIONS = 3                 # per top-3 parent
N_CROSSEOVERS = 3               # random pairs from HOF
N_HARD_CHECK_TOP = 3           # top-3 get 10-window WF
WF_WINDOWS_NORMAL = 5
WF_WINDOWS_HARD = 10

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

HOF_DIR = RESEARCH_DIR / "runs" / "evolution_v7"
HOF_FILE = HOF_DIR / "evolution_v7_hof.json"
HOF_DIR.mkdir(parents=True, exist_ok=True)

# WF thresholds
WF_PASS_ROBUSTNESS = 50.0
WF_PASS_PROFITABLE = 3

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

def candidate_to_strategy_spec(candidate: dict) -> dict:
    return {
        'strategy': {
            'name': candidate.get('name', 'V7_Unknown'),
            'type': candidate.get('type', 'mean_reversion'),
            'indicators': candidate.get('indicators', []),
            'entry': {'condition': candidate.get('entry_condition', '')},
            'exit': candidate.get('exit_config', {}),
        }
    }

# ============================================================================
# LLM CALLS
# ============================================================================

EXPLORATION_PROMPT_CONSERVATIVE = """Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE Mean-Reversion-Strategie. Konservativ, nah an bewährtem.

Bekannte funktionierende Patterns (als Inspiration, nicht zum Kopieren):
- BB+RSI: close < bb_lower_14 AND rsi_7 < 25 AND close > ema_50 (WF=88.3, IS=1.28) ← aktuell bester
- BB+RSI+EMA200: close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200 (WF=30, IS=4.88) ← overfitted

Variiere Parameter leicht: BB period 10-30, RSI period 5-21, RSI threshold 20-40, EMA 50-200.
Exit: Trail 1.5-3.0%, SL 2.0-4.0%, Max Hold 12-48h.

Antworte NUR mit JSON:
{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}"""

EXPLORATION_PROMPT_CREATIVE = """Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE kreative Strategie. Denk über BB+RSI hinaus!

⚠️ Was funktioniert auf 1h Crypto: Mean Reversion nach sharp drops, wenn der Macro-Trend intakt.
⚠️ Was NICHT funktioniert: Trend-following (MACD, Momentum) — 1h ist zu noisy dafür.

Probiere:
- Stochastic %K/%D überkauft/überverkauft
- Williams %R Extremwerte
- Preis-Drop + Volume-Spike
- ZScore-Extreme + EMA-Filter
- BB-Width Squeeze (enger Bollinger Band vor Ausbruch)
- Kombinationen davon

Oder etwas ganz anderes. Sei kreativ, aber begründet.

Antworte NUR mit JSON:
{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}"""

MUTATION_PROMPT = """MUTIERE diese Strategie leicht. Ändere MAXIMAL 1-2 Parameter.

⚠️ WF Robustness > IS Score. Niedriger IS + robuster OOS = besser.

ELTER: {parent_name}
Entry: {parent_entry}
Exit: {parent_exit}
WF Robustness: {parent_wf}

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {{"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}}}"""

CROSSOVER_PROMPT = """CROSSOVER zwei Strategien. Nimm Entry von der besseren + Exit von der anderen, oder mische Parameter.

ELTER A (WF={parent_a_wf}):
Entry: {parent_a_entry}
Exit: {parent_a_exit}

ELTER B (WF={parent_b_wf}):
Entry: {parent_b_entry}
Exit: {parent_b_exit}

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {{"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}}}"""


def call_llm(prompt: str, temperature: float = 0.3) -> str:
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 1024,
    })
    req = urllib.request.Request(
        API_URL, data=payload.encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  ⚠️ LLM error: {e}")
        return ""


def parse_strategy(text: str) -> dict | None:
    m = re.search(r'\{[^{}]*\{[^{}]*\}[^{}]*\}', text, re.DOTALL)
    if not m:
        m = re.search(r'\{[^{}]+\}', text)
    if not m:
        return None
    for attempt in [m.group(), re.sub(r',\s*}', '}', m.group()), re.sub(r',\s*]', ']', m.group())]:
        try:
            d = json.loads(attempt)
            if "entry_condition" in d and "exit_config" in d:
                return d
        except:
            pass
    return None

# ============================================================================
# EVALUATION
# ============================================================================

def run_is_backtest(entry_condition: str, exit_config: dict) -> dict | None:
    try:
        candidate = {"name": "eval", "entry_condition": entry_condition, "exit_config": exit_config, "indicators": [], "type": "mean_reversion"}
        strategy_spec = candidate_to_strategy_spec(candidate)
        _, strategy_func = translate_candidate_with_name(strategy_spec)
        engine = BacktestEngine(data_path=str(DATA_PATH))

        all_returns, all_dds, all_cls, all_trades = [], [], [], []
        profitable = 0

        for asset in ASSETS:
            for period_name, (start, end) in PERIODS.items():
                try:
                    df = load_df(asset, start, end)
                    if len(df) < 50:
                        continue
                    result = engine.run(strategy_name="eval", strategy_func=strategy_func, params={}, symbol=asset, timeframe="1h", exit_config=exit_config, df=df)
                    if result.trade_count > 0:
                        all_returns.append(result.net_return)
                        all_dds.append(result.max_drawdown)
                        all_cls.append(result.max_consecutive_losses)
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
        max_cl = max(all_cls)
        min_trades = min(all_trades)
        score = (total_return / avg_dd) * (profitable / 12) * min(1, min_trades / 5) if total_return > 0 and avg_dd > 0 else 0

        return {"avg_return": round(total_return, 2), "avg_dd": round(avg_dd, 1), "max_cl": max_cl,
                "min_trades": min_trades, "profitable_assets": f"{profitable}/12", "is_score": round(score, 2)}
    except Exception as e:
        print(f"  ⚠️ IS error: {e}")
        return None


def run_wf(entry_condition: str, exit_config: dict, n_windows: int = WF_WINDOWS_NORMAL) -> dict | None:
    try:
        strategy_func, parseable = build_strategy_func(entry_condition)
        if not parseable or strategy_func is None:
            return {"wf_robustness": 0.0, "wf_passed": False, "wf_profitable_assets": "0/6",
                    "avg_oos_return": 0.0, "tier": "NEEDS_REVIEW" if not parseable else "PARSE_ERROR"}
        result = run_wf_on_candidate(name="eval", entry=entry_condition, exit_config=exit_config, n_windows=n_windows)
        return {"wf_robustness": result.get("robustness_score", 0), "wf_passed": result.get("passed", False),
                "wf_profitable_assets": result.get("profitable_assets", "0/6"),
                "avg_oos_return": result.get("avg_oos_return", 0), "tier": result.get("tier", "?")}
    except Exception as e:
        print(f"  ⚠️ WF error: {e}")
        return None


def evaluate(candidate: dict) -> dict:
    name = candidate.get("name", "?")
    print(f"\n  🧬 {name}")
    print(f"     Entry: {candidate['entry_condition']}")
    print(f"     Exit: {json.dumps(candidate['exit_config'])}")

    is_result = run_is_backtest(candidate["entry_condition"], candidate["exit_config"])
    if is_result:
        candidate.update(is_result)
        print(f"     IS: {is_result['is_score']:.2f} | R={is_result['avg_return']:+.2f}% | DD={is_result['avg_dd']:.1f}% | {is_result['profitable_assets']}")
    else:
        candidate.update({"avg_return": 0, "avg_dd": 0, "max_cl": 0, "min_trades": 0, "profitable_assets": "0/12", "is_score": 0})
        print(f"     IS: FAILED")

    wf_result = run_wf(candidate["entry_condition"], candidate["exit_config"])
    if wf_result:
        candidate.update(wf_result)
        status = "✅ PASS" if wf_result["wf_passed"] else "❌ FAIL"
        print(f"     WF: {status} | R={wf_result['wf_robustness']:.1f} | OOS={wf_result.get('avg_oos_return', 0):+.2f}% | {wf_result['wf_profitable_assets']}")
    else:
        candidate.update({"wf_robustness": 0, "wf_passed": False, "wf_profitable_assets": "0/6", "avg_oos_return": 0, "tier": "?"})
        print(f"     WF: ERROR")

    return candidate

# ============================================================================
# HOF
# ============================================================================

def load_hof() -> list[dict]:
    if HOF_FILE.exists():
        try:
            return json.loads(HOF_FILE.read_text()).get("hof", [])
        except:
            pass
    return []


def save_hof(hof: list[dict]):
    hof.sort(key=lambda x: (x.get("wf_robustness", 0), x.get("is_score", 0)), reverse=True)
    champion = hof[0] if hof else None
    HOF_FILE.write_text(json.dumps({"updated": datetime.now().isoformat(), "champion": champion, "hof": hof[:30]}, indent=2))

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("FOUNDRY V7 — Three-Phase Evolutionary Search")
    print(f"Phase 1: {N_EXPLORATION_CONSERVATIVE} conservative + {N_EXPLORATION_CREATIVE} creative")
    print(f"Phase 2: {N_MUTATIONS}×3 mutations + {N_CROSSEOVERS} crossovers from HOF")
    print(f"Phase 3: Top-{N_HARD_CHECK_TOP} hard-check (10-window WF)")
    print("=" * 70)

    hof = load_hof()
    print(f"\n🏆 HOF: {len(hof)} strategies")
    for s in hof[:5]:
        wf = "✅" if s.get("wf_passed") else "❌"
        print(f"   {s['name']}: WF={s.get('wf_robustness', 0):.1f} {wf} | IS={s.get('is_score', 0):.2f}")

    all_candidates = []

    # =========================================================================
    # PHASE 1: EXPLORATION
    # =========================================================================
    print(f"\n{'='*70}")
    print("PHASE 1: EXPLORATION")
    print(f"{'='*70}")

    # Conservative (temp 0.3)
    print(f"\n📝 Generating {N_EXPLORATION_CONSERVATIVE} conservative candidates (temp=0.3)...")
    for i in range(N_EXPLORATION_CONSERVATIVE):
        response = call_llm(EXPLORATION_PROMPT_CONSERVATIVE, temperature=0.3)
        candidate = parse_strategy(response)
        if candidate:
            candidate["phase"] = "exploration_conservative"
            all_candidates.append(candidate)
            print(f"  ✅ Parsed: {candidate.get('name', '?')}")
        else:
            print(f"  ⚠️ Parse error on conservative #{i+1}")

    # Creative (temp 0.7)
    print(f"\n🎨 Generating {N_EXPLORATION_CREATIVE} creative candidates (temp=0.7)...")
    for i in range(N_EXPLORATION_CREATIVE):
        response = call_llm(EXPLORATION_PROMPT_CREATIVE, temperature=0.7)
        candidate = parse_strategy(response)
        if candidate:
            candidate["phase"] = "exploration_creative"
            all_candidates.append(candidate)
            print(f"  ✅ Parsed: {candidate.get('name', '?')}")
        else:
            print(f"  ⚠️ Parse error on creative #{i+1}")

    # Evaluate Phase 1
    print(f"\n📊 Evaluating {len(all_candidates)} Phase 1 candidates...")
    phase1_evaluated = []
    for c in all_candidates:
        result = evaluate(c)
        phase1_evaluated.append(result)
        # Immediately add WF-passed to HOF
        if result.get("wf_passed") and result.get("wf_robustness", 0) > 0:
            hof.append(result)
    
    save_hof(hof)

    # =========================================================================
    # PHASE 2: EVOLUTION (only if HOF has entries)
    # =========================================================================
    print(f"\n{'='*70}")
    print("PHASE 2: EVOLUTION")
    print(f"{'='*70}")

    phase2_candidates = []

    if hof:
        # Mutate top-3
        top3 = sorted(hof, key=lambda x: x.get("wf_robustness", 0), reverse=True)[:3]
        print(f"\n🧬 Mutating top-3 HOF entries...")
        for parent in top3:
            for j in range(N_MUTATIONS):
                prompt = MUTATION_PROMPT.format(
                    parent_name=parent["name"], parent_entry=parent["entry_condition"],
                    parent_exit=json.dumps(parent["exit_config"]), parent_wf=parent.get("wf_robustness", "?"))
                response = call_llm(prompt, temperature=0.3)
                child = parse_strategy(response)
                if child:
                    child["phase"] = f"mutation_from_{parent['name'][:15]}"
                    phase2_candidates.append(child)

        # Crossover random pairs
        print(f"\n🔀 Crossover from HOF pairs...")
        for _ in range(N_CROSSEOVERS):
            if len(hof) >= 2:
                a, b = random.sample(hof, min(2, len(hof)))
                # Put higher-WF parent first
                if a.get("wf_robustness", 0) < b.get("wf_robustness", 0):
                    a, b = b, a
                prompt = CROSSOVER_PROMPT.format(
                    parent_a_name=a["name"], parent_a_entry=a["entry_condition"],
                    parent_a_exit=json.dumps(a["exit_config"]), parent_a_wf=a.get("wf_robustness", "?"),
                    parent_b_name=b["name"], parent_b_entry=b["entry_condition"],
                    parent_b_exit=json.dumps(b["exit_config"]), parent_b_wf=b.get("wf_robustness", "?"))
                response = call_llm(prompt, temperature=0.3)
                child = parse_strategy(response)
                if child:
                    child["phase"] = f"crossover_{a['name'][:10]}_x_{b['name'][:10]}"
                    phase2_candidates.append(child)
    else:
        print("  ⚠️ No HOF entries — skipping evolution phase")

    # Evaluate Phase 2
    print(f"\n📊 Evaluating {len(phase2_candidates)} Phase 2 candidates...")
    phase2_evaluated = []
    for c in phase2_candidates:
        result = evaluate(c)
        phase2_evaluated.append(result)
        if result.get("wf_passed") and result.get("wf_robustness", 0) > 0:
            hof.append(result)

    save_hof(hof)

    # =========================================================================
    # PHASE 3: HARD CHECK
    # =========================================================================
    print(f"\n{'='*70}")
    print("PHASE 3: HARD CHECK (10-window WF)")
    print(f"{'='*70}")

    hof_sorted = sorted(hof, key=lambda x: x.get("wf_robustness", 0), reverse=True)
    hard_check_candidates = [s for s in hof_sorted if s.get("wf_passed")][:N_HARD_CHECK_TOP]

    if hard_check_candidates:
        print(f"\n🔍 Re-validating top-{len(hard_check_candidates)} with {WF_WINDOWS_HARD} windows...")
        for s in hard_check_candidates:
            print(f"  🧐 {s['name']} (current WF={s.get('wf_robustness', 0):.1f})...")
            wf_hard = run_wf(s["entry_condition"], s["exit_config"], n_windows=WF_WINDOWS_HARD)
            if wf_hard:
                s["wf_robustness_10w"] = wf_hard["wf_robustness"]
                s["wf_passed_10w"] = wf_hard["wf_passed"]
                s["wf_profitable_10w"] = wf_hard["wf_profitable_assets"]
                status = "✅" if wf_hard["wf_passed"] else "❌"
                print(f"     {status} 10-window: Robustness={wf_hard['wf_robustness']:.1f} | {wf_hard['wf_profitable_assets']} | OOS={wf_hard.get('avg_oos_return', 0):+.2f}%")

        save_hof(hof)
    else:
        print("\n  ⚠️ No WF-passed candidates for hard check")

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    print(f"\n{'='*70}")
    print("FINAL SUMMARY")
    print(f"{'='*70}")
    print(f"Phase 1 evaluated: {len(phase1_evaluated)}")
    phase1_passed = [c for c in phase1_evaluated if c.get("wf_passed")]
    print(f"Phase 1 WF-passed: {len(phase1_passed)}")
    print(f"Phase 2 evaluated: {len(phase2_evaluated)}")
    phase2_passed = [c for c in phase2_evaluated if c.get("wf_passed")]
    print(f"Phase 2 WF-passed: {len(phase2_passed)}")

    print(f"\n🏆 HALL OF FAME (top 10 by WF Robustness):")
    for i, s in enumerate(hof_sorted[:10]):
        wf = "✅" if s.get("wf_passed") else "❌"
        hc = f" | 10w={s.get('wf_robustness_10w', '?')}" if "wf_robustness_10w" in s else ""
        print(f"  {i+1}. {s['name']:45s} WF={s.get('wf_robustness', 0):5.1f} {wf} | IS={s.get('is_score', 0):5.2f}{hc}")

    # Champion declaration
    champions_10w = [s for s in hof_sorted if s.get("wf_passed_10w")]
    if champions_10w:
        champ = champions_10w[0]
        print(f"\n🎉 CHAMPION (10-window validated): {champ['name']}")
        print(f"   WF={champ.get('wf_robustness_10w', '?')} | IS={champ.get('is_score', '?')} | OOS={champ.get('avg_oos_return', '?')}%")
    elif hard_check_candidates:
        print(f"\n⚠️  No candidate passed 10-window hard check")
    else:
        print(f"\n⚠️  No WF-passed candidates this run")

    # Save full results
    results_file = HOF_DIR / f"evolution_v7_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results_file.write_text(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "phase1_evaluated": len(phase1_evaluated),
        "phase1_passed": len(phase1_passed),
        "phase2_evaluated": len(phase2_evaluated),
        "phase2_passed": len(phase2_passed),
        "phase1_results": phase1_evaluated,
        "phase2_results": phase2_evaluated,
        "hof": hof_sorted,
        "champion": champions_10w[0] if champions_10w else None,
    }, indent=2, default=str))
    print(f"\n💾 Results saved to {results_file}")


if __name__ == "__main__":
    main()