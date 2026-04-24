#!/usr/bin/env python3
"""
Foundry Parallel Run — Trail Validation vs KI Evolution

Zwei Modi gegeneinander:
1. VALIDATION: Parameter-Sweep (Trail 2.0-3.5%, Max Hold 48/72h) — reine Mathematik
2. EVOLUTION: Gemma4 generiert Strategie-Kandidaten → Backtest → Gate — KI

Läuft isoliert, berührt V1 Paper Engine nicht.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from datetime import datetime as dt
from pathlib import Path
from dataclasses import dataclass, field

import polars as pl

# ── Paths ──
RESEARCH_DIR = Path(__file__).parent
DATA_PATH = RESEARCH_DIR / "data"
RESULTS_DIR = RESEARCH_DIR / "runs" / "trail_validation"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(RESEARCH_DIR))
sys.path.insert(0, str(RESEARCH_DIR / "backtest"))

from dsl_translator import translate_candidate_with_name
from backtest.backtest_engine import BacktestEngine, BacktestResult

# ── Ollama Cloud Config ──
API_URL = os.environ.get("OLLAMA_API_URL", "http://172.17.0.1:32771/v1/chat/completions")
API_KEY = os.environ.get("OLLAMA_API_KEY", "ollama-cloud")
MODEL = os.environ.get("GENERATOR_MODEL", "gemma4:31b-cloud")

# ── Assets (testnet-relevant only) ──
ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]

# Data file naming: *_1h_full.parquet (not *_1h.parquet)
DATA_FILE_MAP = {a: f"{a}_1h_full.parquet" for a in ASSETS}

# ── Periods ──
PERIODS = {
    "2024": ("2024-01-01", "2024-12-31"),
    "2yr": ("2023-01-01", "2025-04-20"),
}

# ── Gate Thresholds (v0.3, CL≤12) ──
GATE = {
    "min_return": 1.0,
    "min_pf": 1.05,
    "max_dd": 20.0,
    "max_cl": 12,
    "min_trades": 20,
    "min_sharpe": 0.1,
}


def gate_pass(result: BacktestResult) -> dict:
    """Evaluate backtest result against gate thresholds."""
    checks = {
        "return": result.net_return >= GATE["min_return"],
        "pf": result.profit_factor >= GATE["min_pf"],
        "dd": result.max_drawdown <= GATE["max_dd"],
        "cl": result.max_consecutive_losses <= GATE["max_cl"],
        "trades": result.trade_count >= GATE["min_trades"],
        "sharpe": result.sharpe_ratio >= GATE["min_sharpe"],
    }
    passed = all(checks.values())
    return {"passed": passed, "checks": checks, "cl": result.max_consecutive_losses}


# ═══════════════════════════════════════════════════════════════
# MODE 1: VALIDATION — Parameter Sweep (No KI)
# ═══════════════════════════════════════════════════════════════

def run_validation():
    """Parameter-Sweep: gleiche Strategie, verschiedene Trail-Weiten."""
    print("=" * 60)
    print("MODE 1: VALIDATION — Trail Parameter Sweep")
    print("=" * 60)
    
    variants = [
        {"name": "TS2.0_MH48", "trailing_stop_pct": 2.0, "stop_loss_pct": 2.5, "max_hold_bars": 48},
        {"name": "TS2.5_MH48", "trailing_stop_pct": 2.5, "stop_loss_pct": 3.0, "max_hold_bars": 48},
        {"name": "TS3.0_MH48", "trailing_stop_pct": 3.0, "stop_loss_pct": 3.5, "max_hold_bars": 48},
        {"name": "TS3.5_MH48", "trailing_stop_pct": 3.5, "stop_loss_pct": 4.0, "max_hold_bars": 48},
        {"name": "TS2.5_MH72", "trailing_stop_pct": 2.5, "stop_loss_pct": 3.0, "max_hold_bars": 72},
        {"name": "TS3.0_MH72", "trailing_stop_pct": 3.0, "stop_loss_pct": 3.5, "max_hold_bars": 72},
    ]
    
    # Strategy spec for DSL translator
    base_strategy = {
        'strategy': {
            'name': 'Momentum_MACD',
            'type': 'momentum',
            'indicators': [
                {'name': 'MACD', 'params': {'fast': 12, 'slow': 26, 'signal': 9}},
                {'name': 'EMA', 'params': {'period': 50}},
                {'name': 'EMA', 'params': {'period': 200}},
                {'name': 'ADX', 'params': {'period': 14}},
            ],
            'entry': {'condition': 'macd_hist > 0 AND close > ema_50 AND ema_50 > ema_200 AND adx_14 > 20'},
        }
    }
    
    engine = BacktestEngine(str(DATA_PATH), fee_rate=0.0005, slippage_bps=5.0, initial_capital=10000.0)
    
    all_results = []
    
    for variant in variants:
        vname = variant["name"]
        exit_config = {k: v for k, v in variant.items() if k != "name"}
        
        # Inject exit config into strategy spec
        strategy = {**base_strategy}
        strategy['strategy'] = {**base_strategy['strategy'], 'exit': exit_config}
        
        for asset in ASSETS:
            for period_name, (start, end) in PERIODS.items():
                label = f"{vname} | {asset} | {period_name}"
                
                try:
                    # Load data directly from full parquet
                    data_file = DATA_PATH / DATA_FILE_MAP[asset]
                    if not data_file.exists():
                        print(f"  SKIP {label}: data file not found ({data_file.name})")
                        continue
                    df = pl.scan_parquet(str(data_file)).collect()
                    
                    # Filter to period (datetime comparison)
                    from datetime import datetime as dt
                    start_dt = dt.fromisoformat(start + "T00:00:00+00:00")
                    end_dt = dt.fromisoformat(end.replace("2025-04-20", "2025-12-31") + "T23:59:59+00:00")
                    df = df.filter(
                        (pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt)
                    )
                    
                    if len(df) < 50:
                        print(f"  SKIP {label}: insufficient data ({len(df)} bars)")
                        continue
                    
                    # Translate strategy → signal function
                    strategy_name_xl, strategy_func = translate_candidate_with_name(strategy)
                    
                    # Run backtest
                    result = engine.run(
                        strategy_name=vname,
                        strategy_func=strategy_func,
                        params={},
                        symbol=asset,
                        timeframe="1h",
                        exit_config=exit_config,
                        df=df,
                    )
                    
                    # Evaluate gate
                    gate_result = gate_pass(result)
                    
                    entry = {
                        "variant": vname,
                        "asset": asset,
                        "period": period_name,
                        "trailing_stop_pct": variant["trailing_stop_pct"],
                        "max_hold_bars": variant["max_hold_bars"],
                        "trades": result.trade_count,
                        "return_pct": round(result.net_return, 2),
                        "pf": round(result.profit_factor, 2),
                        "dd_pct": round(result.max_drawdown, 2),
                        "win_rate": round(result.win_rate, 2),
                        "cl": result.max_consecutive_losses,
                        "sharpe": round(result.sharpe_ratio, 2),
                        "gate_pass": gate_result["passed"],
                        "gate_checks": {k: str(v) for k, v in gate_result["checks"].items()},
                    }
                    all_results.append(entry)
                    
                    status = "✅ PASS" if gate_result["passed"] else "❌ FAIL"
                    print(f"  {status} {label}: R={result.net_return:+.1f}% DD={result.max_drawdown:.1f}% CL={result.max_consecutive_losses} PF={result.profit_factor:.2f} T={result.trade_count}")
                    
                except Exception as e:
                    print(f"  ERROR {label}: {e}")
    
    # Summary per variant
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    summary = {}
    for r in all_results:
        v = r["variant"]
        if v not in summary:
            summary[v] = {"pass": 0, "total": 0, "returns": [], "dds": [], "cls": []}
        summary[v]["total"] += 1
        if r["gate_pass"]:
            summary[v]["pass"] += 1
        summary[v]["returns"].append(r["return_pct"])
        summary[v]["dds"].append(r["dd_pct"])
        summary[v]["cls"].append(r["cl"])
    
    print(f"\n{'Variant':<16} {'Pass':>6} {'Rate':>7} {'Avg R%':>8} {'Avg DD%':>8} {'Avg CL':>7}")
    print("-" * 55)
    for vname, s in summary.items():
        avg_r = sum(s["returns"]) / len(s["returns"]) if s["returns"] else 0
        avg_dd = sum(s["dds"]) / len(s["dds"]) if s["dds"] else 0
        avg_cl = sum(s["cls"]) / len(s["cls"]) if s["cls"] else 0
        rate = f"{s['pass']}/{s['total']} ({s['pass']/s['total']*100:.0f}%)" if s["total"] else "N/A"
        print(f"{vname:<16} {s['pass']:>6} {rate:>7} {avg_r:>+8.1f} {avg_dd:>8.1f} {avg_cl:>7.1f}")
    
    # Save results
    out_path = RESULTS_DIR / "validation_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {out_path}")
    
    return all_results, summary


# ═══════════════════════════════════════════════════════════════
# MODE 2: EVOLUTION — KI-generated Strategies (Gemma4)
# ═══════════════════════════════════════════════════════════════

def call_gemma4(prompt: str, max_tokens: int = 2000, temperature: float = 0.7) -> dict:
    """Call Gemma4:31b Cloud via Ollama API."""
    import urllib.request
    import urllib.error
    
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def parse_ki_candidates(response_text: str) -> list:
    """Parse KI-generated strategy candidates from JSON response."""
    # Try to extract JSON from markdown code blocks
    import re
    json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    else:
        text = response_text
    
    try:
        candidates = json.loads(text)
        if isinstance(candidates, list):
            return candidates
        elif isinstance(candidates, dict):
            return [candidates]
    except json.JSONDecodeError:
        pass
    
    # Fallback: try to find any JSON array
    bracket_match = re.search(r'\[.*\]', text, re.DOTALL)
    if bracket_match:
        try:
            return json.loads(bracket_match.group())
        except json.JSONDecodeError:
            pass
    
    return []


def candidate_to_strategy_spec(candidate: dict) -> dict:
    """Convert KI candidate to Foundry strategy spec format."""
    return {
        'strategy': {
            'name': candidate.get('name', 'KI_Unknown'),
            'type': candidate.get('type', 'momentum').lower().replace('-', '_').replace(' ', '_'),
            'indicators': candidate.get('indicators', []),
            'entry': {'condition': candidate.get('entry_condition', '')},
            'exit': candidate.get('exit_config', {}),
        }
    }


def run_evolution(n_iterations: int = 3, candidates_per_iter: int = 3):
    """KI-generierte Strategien backtesten."""
    print("\n" + "=" * 60)
    print("MODE 2: EVOLUTION — KI-generated Strategies (Gemma4)")
    print("=" * 60)
    
    engine = BacktestEngine(str(DATA_PATH), fee_rate=0.0005, slippage_bps=5.0, initial_capital=10000.0)
    all_results = []
    total_tokens = 0
    
    # Context from V1 paper trading for better KI suggestions
    v1_context = """
ERGEBNISSE V1 PAPER TRADING (5 Tage, Echtzeit):
- Win-Rate: 25% (3/12 Trades profitabel)
- Total PnL: -0.95€ (-0.95%)
- HAUPTPROBLEM: Trailing Stop 2% zu eng — 11/12 Exits = Trailing Stop
- Entry-Logik funktioniert (MACD+ADX+EMA findet Trends)
- Exit-Logik zu starr (wirft Positionen raus bevor Trend läuft)
- Alts (SOL, DOGE, ADA, AVAX) brauchen mehr Trail-Raum als BTC
- DD kontrolliert: 1.62% nach 5 Tagen
"""
    
    generation_prompt_template = """Du bist ein Quant-Stratege für Crypto-Perps auf Hyperliquid (1h Timeframe, 0.01% Maker-Fees, 100€ Startkapital).

{v1_context}

AUFGABE: Generiere {n} Strategie-Kandidaten die das V1 EXIT-PROBLEM lösen.
Fokus auf BESSERE EXIT-STRATEGIEN, nicht neue Entry-Logik.

WICHTIG: Du MUSST die folgende exakte JSON-Struktur verwenden. Abweichungen führen zu Fehlern.

Verfügbare Indikatoren und ihre exakten JSON-Keys:
- MACD: {{"name": "MACD", "params": {{"fast": 12, "slow": 26, "signal": 9}}}}
- EMA: {{"name": "EMA", "params": {{"period": 50}}}}  ← period kann 20, 50, 100, 200 sein
- ADX: {{"name": "ADX", "params": {{"period": 14}}}}
- RSI: {{"name": "RSI", "params": {{"period": 14}}}}
- BB: {{"name": "BB", "params": {{"period": 20, "std_dev": 2.0}}}}
- ATR: {{"name": "ATR", "params": {{"period": 14}}}}

Entry-Condition Syntax (STRIKT einhalten!):
- Variablen: macd_hist, macd_line, macd_signal, ema_50, ema_200, ema_20, adx_14, rsi_14, close, bb_upper_20, bb_lower_20, bb_mid_20, atr_14
- Operatoren: >, <, >=, <=, ==, !=
- Logisch: AND, OR
- BEISPIEL: "macd_hist > 0 AND close > ema_50 AND adx_14 > 20"
- KEINE anderen Variablennamen! KEIN "MACD Line > Signal Line" — nur "macd_line > macd_signal"

Exit-Config (JSON-Keys strikt):
{{"trailing_stop_pct": float, "stop_loss_pct": float, "max_hold_bars": int}}

Regeln:
- Max 4 Indikatoren
- Trailing Stop zwischen 2.5% und 4.0%
- Max Hold zwischen 48 und 96
- Stop Loss ≤ 5%
- Nur LONG

Gib JSON zurück: Array von Objekten mit keys: name, type, indicators, entry_condition, exit_config

{{"name": "...", "type": "momentum", "indicators": [...], "entry_condition": "...", "exit_config": {{...}}}}

FRÜHERE FEHLBACKS: {feedback}"""
    
    feedback = "Erste Iteration — keine vorherigen Ergebnisse."
    
    for iteration in range(1, n_iterations + 1):
        print(f"\n--- Iteration {iteration}/{n_iterations} ---")
        
        prompt = generation_prompt_template.format(
            n=candidates_per_iter,
            v1_context=v1_context,
            feedback=feedback,
        )
        
        try:
            # Call Gemma4
            print(f"  Calling Gemma4 ({MODEL})...")
            resp = call_gemma4(prompt, max_tokens=2000, temperature=0.7)
            tokens_used = resp.get("usage", {}).get("total_tokens", 0)
            total_tokens += tokens_used
            print(f"  Tokens: {tokens_used} (total: {total_tokens})")
            
            content = resp["choices"][0]["message"]["content"]
            
            # Parse candidates
            candidates = parse_ki_candidates(content)
            if not candidates:
                print(f"  ⚠️ No valid JSON candidates found, skipping iteration")
                print(f"  Raw response: {content[:200]}...")
                continue
            
            print(f"  Parsed {len(candidates)} candidates")
            
            # Backtest each candidate
            iter_feedback = []
            for ci, candidate in enumerate(candidates):
                cname = candidate.get("name", f"Candidate_{ci}")
                print(f"\n  Testing: {cname}")
                
                try:
                    strategy_spec = candidate_to_strategy_spec(candidate)
                    exit_config = candidate.get("exit_config", {})
                    
                    # Normalize exit_config keys
                    if "trailing_stop_pct" not in exit_config and "trailing_stop" in exit_config:
                        # KI might use different key names
                        pass
                    
                    strategy_name_xl, strategy_func = translate_candidate_with_name(strategy_spec)
                    
                    # Test on BTC 2024 (fast check first)
                    data_file = DATA_PATH / DATA_FILE_MAP["BTCUSDT"]
                    df = pl.scan_parquet(str(data_file)).collect()
                    start_2024 = dt.fromisoformat("2024-01-01T00:00:00+00:00")
                    end_2024 = dt.fromisoformat("2024-12-31T23:59:59+00:00")
                    df_2024 = df.filter(
                        (pl.col("timestamp") >= start_2024) & (pl.col("timestamp") <= end_2024)
                    )
                    
                    if len(df_2024) < 50:
                        print(f"    SKIP: insufficient data")
                        continue
                    
                    result = engine.run(
                        strategy_name=cname,
                        strategy_func=strategy_func,
                        params={},
                        symbol="BTCUSDT",
                        timeframe="1h",
                        exit_config=exit_config,
                        df=df_2024,
                    )
                    
                    gate_result = gate_pass(result)
                    
                    entry = {
                        "iteration": iteration,
                        "candidate": cname,
                        "asset": "BTCUSDT",
                        "period": "2024",
                        "trades": result.trade_count,
                        "return_pct": round(result.net_return, 2),
                        "pf": round(result.profit_factor, 2),
                        "dd_pct": round(result.max_drawdown, 2),
                        "win_rate": round(result.win_rate, 2),
                        "cl": result.max_consecutive_losses,
                        "sharpe": round(result.sharpe_ratio, 2),
                        "gate_pass": gate_result["passed"],
                        "exit_config": exit_config,
                        "raw_candidate": candidate,
                    }
                    all_results.append(entry)
                    
                    status = "✅ PASS" if gate_result["passed"] else "❌ FAIL"
                    print(f"    {status} BTC 2024: R={result.net_return:+.1f}% DD={result.max_drawdown:.1f}% CL={result.max_consecutive_losses} PF={result.profit_factor:.2f} T={result.trade_count}")
                    
                    # If BTC passes, test all assets
                    if gate_result["passed"]:
                        print(f"    🎯 BTC 2024 passed! Testing all assets...")
                        for asset in ASSETS[1:]:  # Skip BTC (already tested)
                            for period_name, (start, end) in PERIODS.items():
                                try:
                                    data_file_a = DATA_PATH / DATA_FILE_MAP[asset]
                                    df_a = pl.scan_parquet(str(data_file_a)).collect()
                                    start_dt_p = dt.fromisoformat(start + "T00:00:00+00:00")
                                    end_dt_p = dt.fromisoformat(end.replace("2025-04-20", "2025-12-31") + "T23:59:59+00:00")
                                    df_a = df_a.filter(
                                        (pl.col("timestamp") >= start_dt_p) & (pl.col("timestamp") <= end_dt_p)
                                    )
                                    if len(df_a) < 50:
                                        continue
                                    
                                    result_a = engine.run(
                                        strategy_name=cname,
                                        strategy_func=strategy_func,
                                        params={},
                                        symbol=asset,
                                        timeframe="1h",
                                        exit_config=exit_config,
                                        df=df_a,
                                    )
                                    gate_a = gate_pass(result_a)
                                    
                                    entry_a = {
                                        "iteration": iteration,
                                        "candidate": cname,
                                        "asset": asset,
                                        "period": period_name,
                                        "trades": result_a.trade_count,
                                        "return_pct": round(result_a.net_return, 2),
                                        "pf": round(result_a.profit_factor, 2),
                                        "dd_pct": round(result_a.max_drawdown, 2),
                                        "win_rate": round(result_a.win_rate, 2),
                                        "cl": result_a.max_consecutive_losses,
                                        "sharpe": round(result_a.sharpe_ratio, 2),
                                        "gate_pass": gate_a["passed"],
                                        "exit_config": exit_config,
                                        "raw_candidate": candidate,
                                    }
                                    all_results.append(entry_a)
                                    
                                    s = "✅" if gate_a["passed"] else "❌"
                                    print(f"    {s} {asset} {period_name}: R={result_a.net_return:+.1f}% DD={result_a.max_drawdown:.1f}% CL={result_a.max_consecutive_losses}")
                                    
                                except Exception as e:
                                    print(f"    ERROR {asset} {period_name}: {e}")
                    
                    # Build feedback for next iteration
                    iter_feedback.append(
                        f"{cname}: R={result.net_return:+.1f}% DD={result.max_drawdown:.1f}% CL={result.max_consecutive_losses} PF={result.profit_factor:.2f} {'PASS' if gate_result['passed'] else 'FAIL'}"
                    )
                    
                except Exception as e:
                    print(f"    ERROR translating/backtesting {cname}: {e}")
                    iter_feedback.append(f"{cname}: Translation/backtest error: {e}")
            
            feedback = " | ".join(iter_feedback) if iter_feedback else "No valid candidates this round"
            
        except Exception as e:
            print(f"  ERROR calling Gemma4: {e}")
            feedback = f"Gemma4 call failed: {e}"
    
    # Summary
    print("\n" + "=" * 60)
    print("EVOLUTION SUMMARY")
    print("=" * 60)
    
    candidate_summary = {}
    for r in all_results:
        c = r["candidate"]
        if c not in candidate_summary:
            candidate_summary[c] = {"pass": 0, "total": 0, "returns": [], "dds": [], "cls": []}
        candidate_summary[c]["total"] += 1
        if r["gate_pass"]:
            candidate_summary[c]["pass"] += 1
        candidate_summary[c]["returns"].append(r["return_pct"])
        candidate_summary[c]["dds"].append(r["dd_pct"])
        candidate_summary[c]["cls"].append(r["cl"])
    
    print(f"\n{'Candidate':<25} {'Pass':>6} {'Total':>6} {'Rate':>7} {'Avg R%':>8} {'Avg DD%':>8} {'Avg CL':>7}")
    print("-" * 70)
    for cname, s in candidate_summary.items():
        avg_r = sum(s["returns"]) / len(s["returns"]) if s["returns"] else 0
        avg_dd = sum(s["dds"]) / len(s["dds"]) if s["dds"] else 0
        avg_cl = sum(s["cls"]) / len(s["cls"]) if s["cls"] else 0
        rate = f"{s['pass']}/{s['total']}" if s['total'] else "N/A"
        print(f"{cname:<25} {s['pass']:>6} {s['total']:>6} {rate:>7} {avg_r:>+8.1f} {avg_dd:>8.1f} {avg_cl:>7.1f}")
    
    # Save
    out_path = RESULTS_DIR / "evolution_results.json"
    with open(out_path, "w") as f:
        json.dump({"total_tokens": total_tokens, "results": all_results}, f, indent=2)
    print(f"\nResults saved to {out_path}")
    print(f"Total KI tokens used: {total_tokens}")
    
    return all_results, candidate_summary, total_tokens


# ═══════════════════════════════════════════════════════════════
# COMPARISON
# ═══════════════════════════════════════════════════════════════

def compare(validation_results, evolution_results, total_tokens):
    """Vergleiche Validation vs Evolution Ergebnisse."""
    print("\n" + "=" * 60)
    print("🏆 HEAD-TO-HEAD COMPARISON")
    print("=" * 60)
    
    # Best validation variant
    v_passes = {}
    for r in validation_results:
        v = r["variant"]
        if v not in v_passes:
            v_passes[v] = 0
        if r["gate_pass"]:
            v_passes[v] += 1
    
    best_v = max(v_passes, key=v_passes.get) if v_passes else "N/A"
    best_v_rate = v_passes.get(best_v, 0)
    
    # Best evolution candidate
    e_passes = {}
    for r in evolution_results:
        c = r["candidate"]
        if c not in e_passes:
            e_passes[c] = 0
        if r["gate_pass"]:
            e_passes[c] += 1
    
    best_e = max(e_passes, key=e_passes.get) if e_passes else "N/A"
    best_e_rate = e_passes.get(best_e, 0)
    
    print(f"\n{'Metric':<25} {'Validation':>15} {'Evolution':>15}")
    print("-" * 55)
    print(f"{'Best variant':<25} {best_v:>15} {best_e:>15}")
    print(f"{'Best pass count':<25} {best_v_rate:>15} {best_e_rate:>15}")
    print(f"{'KI tokens used':<25} {'0':>15} {total_tokens:>15}")
    print(f"{'Runtime':<25} {'~2 min':>15} {'~15 min':>15}")
    print(f"{'Reproducibility':<25} {'100%':>15} {'Stochastic':>15}")
    
    print(f"\n🏆 WINNER: {'VALIDATION' if best_v_rate >= best_e_rate else 'EVOLUTION'}")
    print(f"   (bei gleichstand: Validation — reproduzierbar, keine KI-Kosten)")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Foundry Parallel Run")
    parser.add_argument("--mode", choices=["validation", "evolution", "both"], default="both",
                        help="Which mode to run")
    parser.add_argument("--iterations", type=int, default=3,
                        help="Number of KI evolution iterations")
    parser.add_argument("--candidates", type=int, default=3,
                        help="Candidates per KI iteration")
    args = parser.parse_args()
    
    start = time.time()
    
    val_results = val_summary = None
    evo_results = evo_summary = None
    total_tokens = 0
    
    if args.mode in ("validation", "both"):
        val_results, val_summary = run_validation()
    
    if args.mode in ("evolution", "both"):
        evo_results, evo_summary, total_tokens = run_evolution(
            n_iterations=args.iterations,
            candidates_per_iter=args.candidates,
        )
    
    if val_results and evo_results:
        compare(val_results, evo_results, total_tokens)
    
    elapsed = time.time() - start
    print(f"\nTotal runtime: {elapsed:.1f}s")
    print(f"Results directory: {RESULTS_DIR}")