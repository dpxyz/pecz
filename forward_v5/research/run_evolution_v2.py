#!/usr/bin/env python3
"""
Foundry Evolution V2 — Verbesserter KI-Lauf

Verbesserungen gegenüber V1:
- Validation-Ergebnisse als Kontext (KI lernt aus Daten)
- Strukturiertes Feedback pro Kandidat (nicht nur "FAIL")
- 10 Iterationen, 2 Kandidaten (fokussierter)
- Temperature 0.3 (konservativer, näher an Baseline)
- Two-Stage: KI generiert → Backtest → Analyzer-Feedback → KI verfeinert
"""

import json
import os
import sys
import time
import re
import urllib.request
from datetime import datetime as dt
from pathlib import Path

import polars as pl

RESEARCH_DIR = Path(__file__).parent
DATA_PATH = RESEARCH_DIR / "data"
RESULTS_DIR = RESEARCH_DIR / "runs" / "evolution_v2"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(RESEARCH_DIR))
sys.path.insert(0, str(RESEARCH_DIR / "backtest"))

from dsl_translator import translate_candidate_with_name
from backtest.backtest_engine import BacktestEngine, BacktestResult

API_URL = os.environ.get("OLLAMA_API_URL", "http://172.17.0.1:32771/v1/chat/completions")
API_KEY = os.environ.get("OLLAMA_API_KEY", "ollama-cloud")
MODEL = os.environ.get("GENERATOR_MODEL", "gemma4:31b-cloud")

ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]
DATA_FILE_MAP = {a: f"{a}_1h_full.parquet" for a in ASSETS}

PERIODS = {
    "2024": ("2024-01-01", "2024-12-31"),
    "2yr": ("2023-01-01", "2025-12-31"),
}

GATE = {
    "min_return": 1.0,
    "min_pf": 1.05,
    "max_dd": 20.0,
    "max_cl": 12,
    "min_trades": 20,
    "min_sharpe": 0.1,
}


def gate_pass(result: BacktestResult) -> dict:
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


def diagnose_result(result: BacktestResult, gate_result: dict) -> str:
    """Structured diagnosis of why a strategy failed."""
    issues = []
    if not gate_result["checks"]["return"]:
        issues.append(f"Return {result.net_return:+.1f}% < 1%")
    if not gate_result["checks"]["pf"]:
        issues.append(f"PF {result.profit_factor:.2f} < 1.05")
    if not gate_result["checks"]["dd"]:
        issues.append(f"DD {result.max_drawdown:.1f}% > 20%")
    if not gate_result["checks"]["cl"]:
        issues.append(f"CL {result.max_consecutive_losses} > 12")
    if not gate_result["checks"]["trades"]:
        issues.append(f"Trades {result.trade_count} < 20")
    if not gate_result["checks"]["sharpe"]:
        issues.append(f"Sharpe {result.sharpe_ratio:.2f} < 0.1")
    
    if result.trade_count > 300:
        issues.append("OVERTRADING: >300 trades → Entry zu schwach, zu viele Fehlsignale")
    if result.trade_count < 50:
        issues.append("UNDERTRADING: <50 trades → Entry zu restriktiv")
    if result.win_rate < 0.3 and result.trade_count > 50:
        issues.append(f"Win-Rate {result.win_rate:.0%} sehr niedrig → Entry-Qualität schlecht")
    if result.max_drawdown > 40:
        issues.append("Extreme DD > 40% → Positionsgröße oder SL prüfen")
    
    return " | ".join(issues) if issues else "PASS"


def call_gemma4(prompt: str, max_tokens: int = 2000, temperature: float = 0.3) -> dict:
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
    
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())


def parse_ki_candidates(response_text: str) -> list:
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
    
    bracket_match = re.search(r'\[.*\]', text, re.DOTALL)
    if bracket_match:
        try:
            return json.loads(bracket_match.group())
        except json.JSONDecodeError:
            pass
    
    return []


def candidate_to_strategy_spec(candidate: dict) -> dict:
    return {
        'strategy': {
            'name': candidate.get('name', 'KI_Unknown'),
            'type': candidate.get('type', 'momentum').lower().replace('-', '_').replace(' ', '_'),
            'indicators': candidate.get('indicators', []),
            'entry': {'condition': candidate.get('entry_condition', '')},
            'exit': candidate.get('exit_config', {}),
        }
    }


def load_df(asset: str, start: str, end: str) -> pl.DataFrame:
    data_file = DATA_PATH / DATA_FILE_MAP[asset]
    df = pl.scan_parquet(str(data_file)).collect()
    start_dt = dt.fromisoformat(start + "T00:00:00+00:00")
    end_dt = dt.fromisoformat(end + "T23:59:59+00:00")
    return df.filter(
        (pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt)
    )


def backtest_candidate(candidate: dict, engine: BacktestEngine, 
                        asset: str = "BTCUSDT", period: str = "2024") -> dict:
    """Run backtest for a single candidate, return result + diagnosis."""
    start, end = PERIODS[period]
    cname = candidate.get("name", "Unknown")
    exit_config = candidate.get("exit_config", {})
    
    try:
        strategy_spec = candidate_to_strategy_spec(candidate)
        _, strategy_func = translate_candidate_with_name(strategy_spec)
        
        df = load_df(asset, start, end)
        if len(df) < 50:
            return {"error": f"insufficient data ({len(df)} bars)"}
        
        result = engine.run(
            strategy_name=cname,
            strategy_func=strategy_func,
            params={},
            symbol=asset,
            timeframe="1h",
            exit_config=exit_config,
            df=df,
        )
        
        gate_result = gate_pass(result)
        diagnosis = diagnose_result(result, gate_result)
        
        return {
            "name": cname,
            "trades": result.trade_count,
            "return_pct": round(result.net_return, 2),
            "pf": round(result.profit_factor, 2),
            "dd_pct": round(result.max_drawdown, 2),
            "win_rate": round(result.win_rate, 2),
            "cl": result.max_consecutive_losses,
            "sharpe": round(result.sharpe_ratio, 2),
            "gate_pass": gate_result["passed"],
            "diagnosis": diagnosis,
            "exit_config": exit_config,
        }
    except Exception as e:
        return {"name": cname, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# MAIN: Enhanced Evolution Loop
# ═══════════════════════════════════════════════════════════════

def run_evolution_v2(n_iterations: int = 10, candidates_per_iter: int = 2):
    print("=" * 70)
    print("EVOLUTION V2 — Enhanced KI Loop with Structured Feedback")
    print("=" * 70)
    
    engine = BacktestEngine(str(DATA_PATH), fee_rate=0.0005, slippage_bps=5.0, initial_capital=10000.0)
    all_results = []
    total_tokens = 0
    hall_of_fame = []  # best strategies survive
    
    # ── Baseline context from Validation Sweep ──
    validation_context = """
BEKANNTE ERGEBNISSE (Validation Parameter Sweep, 72 Backtests):
Beste Trail-Weite: 3.0% (V1 nutzt 2.0%, das ist ZU ENG)
BTC 2024: -14% bis -17% (schlecht, Bärenmarkt-Phase)
ETH 2024: -10% bis -19% (schlecht)
SOL 2024: -2% bis +5% (neutral)
DOGE 2024: +84% bis +152% (stark, hohe Volatilität)
ADA 2024: +41% bis +51% (gut)
AVAX 2024: -24% bis +20% (gemischt)

WICHTIGSTE ERKENNTNIS: Trail 2.0% (V1) erzeugt zu viele Whipsaw-Ausstiege.
Trail 3.0-3.5% lässt Trends länger laufen → bessere Ergebnisse.

V1 PAPER TRADING LIVE-DATEN (5 Tage):
- Win-Rate: 25% (3/12 Trades profitabel)
- 11/12 Exits = Trailing Stop (zu eng!)
- Entry funktioniert, Exit ist das Problem
"""
    
    # ── DSL Reference ──
    dsl_reference = """
STRIKTE DSL-SYNTAX (Pflicht, Abweichungen = Fehler):

Indikatoren (exakte JSON-Keys):
- {"name": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}}
- {"name": "EMA", "params": {"period": 50}}  (period: 20, 50, 100, 200)
- {"name": "ADX", "params": {"period": 14}}
- {"name": "RSI", "params": {"period": 14}}
- {"name": "BB", "params": {"period": 20, "std_dev": 2.0}}
- {"name": "ATR", "params": {"period": 14}}

Entry-Condition Variablen (NUR diese!):
macd_hist, macd_line, macd_signal, ema_20, ema_50, ema_100, ema_200, adx_14, rsi_14, close, bb_upper_20, bb_lower_20, bb_mid_20, atr_14

Entry-Condition Syntax:
- Vergleich: variable OP zahl  (OP: >, <, >=, <=)
- Logisch: AND, OR
- BEISPIEL: "macd_hist > 0 AND close > ema_50 AND adx_14 > 20"
- FALSCH: "MACD Line > Signal Line", "Price > EMA", "ADX > 25"

Exit-Config:
{"trailing_stop_pct": 3.0, "stop_loss_pct": 3.5, "max_hold_bars": 72}
"""
    
    # ── Iteration Loop ──
    feedback = "Erste Iteration — noch keine Ergebnisse."
    
    for iteration in range(1, n_iterations + 1):
        print(f"\n{'─' * 70}")
        print(f"ITERATION {iteration}/{n_iterations}")
        print(f"{'─' * 70}")
        
        # ── Build prompt ──
        # If we have a hall of fame, include best strategies as examples
        hof_context = ""
        if hall_of_fame:
            best = hall_of_fame[0]
            hof_context = f"""
BESTE BISHERIGE STRATEGIE (zum Verbessern):
Name: {best['name']}
Return: {best['return_pct']:+.1f}%, DD: {best['dd_pct']:.1f}%, CL: {best['cl']}, PF: {best['pf']:.2f}, Trades: {best['trades']}
Diagnose: {best.get('diagnosis', 'N/A')}
Exit-Config: {best.get('exit_config', {})}
"""
        
        prompt = f"""Du bist ein Quant-Stratege. Deine Aufgabe: Generiere {candidates_per_iter} Strategie-Kandidaten für Crypto-Perps (1h, Hyperliquid).

{validation_context}

{dsl_reference}

{hof_context}

REGELN:
- Max 4 Indikatoren
- Trailing Stop 2.5-4.0% (NICHT 2.0%!)
- Max Hold 48-96
- Stop Loss ≤ 5%
- Nur LONG
- WENIGER TRADES sind BESSER → strengere Entry-Conditions reduzieren Fehlsignale
- Fokus auf EXIT-OPTIMIERUNG, nicht neue Entry-Logik

FEEDBACK AUS LETZTER ITERATION:
{feedback}

Gib ein JSON-Array zurück mit keys: name, type, indicators, entry_condition, exit_config"""
        
        # ── Call Gemma4 ──
        try:
            print(f"  🤖 Calling Gemma4 (temp=0.3)...")
            resp = call_gemma4(prompt, max_tokens=2000, temperature=0.3)
            tokens_used = resp.get("usage", {}).get("total_tokens", 0)
            total_tokens += tokens_used
            content = resp["choices"][0]["message"]["content"]
            
            candidates = parse_ki_candidates(content)
            if not candidates:
                print(f"  ⚠️ No valid JSON → skipping")
                feedback = "Letzte Iteration lieferte kein gültiges JSON. Bitte nur JSON zurückgeben."
                continue
            
            print(f"  📦 Parsed {len(candidates)} candidates ({tokens_used} tokens)")
            
        except Exception as e:
            print(f"  ❌ Gemma4 error: {e}")
            feedback = f"Gemma4 call failed: {e}"
            continue
        
        # ── Backtest each candidate ──
        iter_results = []
        for candidate in candidates:
            cname = candidate.get("name", "Unknown")
            print(f"\n  🧪 Testing: {cname}")
            
            # Quick test on BTC 2024 first
            r = backtest_candidate(candidate, engine, "BTCUSDT", "2024")
            
            if "error" in r:
                print(f"    ❌ ERROR: {r['error']}")
                iter_results.append(r)
                continue
            
            status = "✅" if r["gate_pass"] else "❌"
            print(f"    {status} BTC 2024: R={r['return_pct']:+.1f}% DD={r['dd_pct']:.1f}% CL={r['cl']} PF={r['pf']:.2f} T={r['trades']}")
            print(f"       Diagnose: {r.get('diagnosis', 'N/A')}")
            
            r["iteration"] = iteration
            r["raw_candidate"] = candidate
            all_results.append(r)
            iter_results.append(r)
            
            # If BTC 2024 passes gate → test all assets
            if r["gate_pass"]:
                print(f"    🎯 BTC 2024 GATE PASS! Testing all assets...")
                for asset in ASSETS[1:]:
                    for period_name in PERIODS:
                        r_a = backtest_candidate(candidate, engine, asset, period_name)
                        if "error" not in r_a:
                            r_a["iteration"] = iteration
                            r_a["asset"] = asset
                            r_a["period"] = period_name
                            r_a["raw_candidate"] = candidate
                            all_results.append(r_a)
                            s = "✅" if r_a["gate_pass"] else "❌"
                            print(f"    {s} {asset} {period_name}: R={r_a['return_pct']:+.1f}% DD={r_a['dd_pct']:.1f}%")
        
        # ── Update Hall of Fame ──
        valid_results = [r for r in iter_results if "error" not in r]
        if valid_results:
            best_iter = max(valid_results, key=lambda r: r.get("return_pct", -999))
            
            # Add to hall of fame if better than worst entry (or hall of fame empty)
            if len(hall_of_fame) < 5:
                hall_of_fame.append(best_iter)
            elif best_iter.get("return_pct", -999) > hall_of_fame[-1].get("return_pct", -999):
                hall_of_fame[-1] = best_iter
            
            hall_of_fame.sort(key=lambda r: r.get("return_pct", -999), reverse=True)
        
        # ── Build structured feedback for next iteration ──
        feedback_parts = []
        for r in iter_results:
            if "error" in r:
                feedback_parts.append(f"{r.get('name', '?')}: FEHLER - {r['error']}")
            else:
                feedback_parts.append(
                    f"{r['name']}: R={r['return_pct']:+.1f}% DD={r['dd_pct']:.1f}% CL={r['cl']} "
                    f"T={r['trades']} PF={r['pf']:.2f} | {r.get('diagnosis', '?')}"
                )
        feedback = "\n".join(feedback_parts)
        
        # Show hall of fame
        if hall_of_fame:
            best = hall_of_fame[0]
            print(f"\n  🏆 Hall of Fame Leader: {best['name']} = {best['return_pct']:+.1f}% (Iter {best.get('iteration', '?')})")
    
    # ═══════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("EVOLUTION V2 — FINAL RESULTS")
    print(f"{'=' * 70}")
    
    valid = [r for r in all_results if "error" not in r]
    if not valid:
        print("  No valid results produced.")
    else:
        # Per-candidate summary
        by_name = {}
        for r in valid:
            n = r["name"]
            if n not in by_name:
                by_name[n] = []
            by_name[n].append(r)
        
        print(f"\n{'Candidate':<35} {'R%':>8} {'DD%':>8} {'CL':>4} {'PF':>6} {'T':>4} {'Status':>8}")
        print("-" * 75)
        for name, results in sorted(by_name.items(), key=lambda x: max(r.get("return_pct", -999) for r in x[1]), reverse=True):
            best_r = max(results, key=lambda r: r.get("return_pct", -999))
            status = "✅ PASS" if best_r.get("gate_pass") else "❌ FAIL"
            print(f"{name:<35} {best_r['return_pct']:>+8.1f} {best_r['dd_pct']:>8.1f} {best_r['cl']:>4} {best_r['pf']:>6.2f} {best_r['trades']:>4} {status:>8}")
        
        # Hall of Fame
        print(f"\n{'─' * 70}")
        print("🏆 HALL OF FAME")
        print(f"{'─' * 70}")
        for i, h in enumerate(hall_of_fame, 1):
            print(f"  {i}. {h['name']} (Iter {h.get('iteration', '?')}): R={h['return_pct']:+.1f}% DD={h['dd_pct']:.1f}% CL={h['cl']} T={h['trades']}")
            print(f"     Diagnosis: {h.get('diagnosis', 'N/A')}")
            print(f"     Exit: {h.get('exit_config', {})}")
        
        # Compare with Validation baseline
        print(f"\n{'─' * 70}")
        print("📊 COMPARISON: Evolution V2 vs Validation Baseline")
        print(f"{'─' * 70}")
        print(f"  Best Evolution V2:  {hall_of_fame[0]['return_pct']:+.1f}% (BTC 2024)" if hall_of_fame else "  No valid evolution results")
        print(f"  Best Validation:    -14.3% (TS2.0, BTC 2024)")
        print(f"  Validation avg 2024: +32.2% (TS2.0 across all assets)")
        
        # Token usage
        print(f"\n  KI Tokens used: {total_tokens:,}")
        print(f"  Iterations: {n_iterations}")
        print(f"  Valid strategies: {len(valid)}")
    
    # Save results
    out_path = RESULTS_DIR / "evolution_v2_results.json"
    with open(out_path, "w") as f:
        json.dump({
            "total_tokens": total_tokens,
            "iterations": n_iterations,
            "hall_of_fame": [{k: v for k, v in h.items() if k != "raw_candidate"} for h in hall_of_fame],
            "results": [{k: v for k, v in r.items() if k != "raw_candidate"} for r in all_results],
        }, f, indent=2)
    print(f"\n  Results saved to {out_path}")
    
    return all_results, hall_of_fame, total_tokens


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--candidates", type=int, default=2)
    args = parser.parse_args()
    
    start = time.time()
    run_evolution_v2(n_iterations=args.iterations, candidates_per_iter=args.candidates)
    elapsed = time.time() - start
    print(f"\nTotal runtime: {elapsed:.1f}s")