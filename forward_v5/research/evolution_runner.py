#!/usr/bin/env python3
"""
Evolution Runner v2.0 – Foundry: Generate → Translate → Backtest → Gate → Report

Foundry-Prinzipien:
1. Spec ist Wahrheit
2. KI generiert, aber bewertet nie
3. Binäre Verdicts: PASS oder FAIL
4. PASS = BACKTEST_PASS (gefunden + validiert, NICHT deployed)
5. FAIL = verworfen, keine manuelle Rettung
6. Output = 1 Discord-Nachricht

Pipeline:
  spec.yaml → Gemma4 Generator → DSL-JSON → dsl_translator → strategy_func
  → backtest_engine.run() → walk_forward → gate_evaluator → PASS/FAIL
  → Discord Report

Usage:
  python3 evolution_runner.py              # Echter Foundry-Run
  python3 evolution_runner.py --mock        # Test-Run mit Mock-Daten
  python3 evolution_runner.py --dry-run     # Generiere nur, kein Backtest
"""

import json
import os
import sys
import yaml
from datetime import datetime
from pathlib import Path

from strategy_dsl import validate_candidate
from gate_evaluator import evaluate_all
from generator import generate_candidates
from dsl_translator import translate_candidate_with_name


# ── Config ──
MAX_ITERATIONS = int(os.environ.get("EVOLUTION_MAX_ITER", "5"))
RUNS_DIR = Path(__file__).parent / "runs"
DATA_PATH = os.environ.get("FOUNDRY_DATA_PATH", "/data/.openclaw/workspace/forward_v5/forward_v5/research/data")

# Import backtest engine
sys.path.insert(0, str(Path(__file__).parent / "backtest"))
try:
    from backtest_engine import BacktestEngine, BacktestResult
    from walk_forward import WalkForwardAnalyzer, WalkForwardResult
    HAS_BACKTEST = True
except ImportError:
    HAS_BACKTEST = False
    print("[WARN] Backtest engine not importable, falling back to mock")


def load_spec() -> dict:
    spec_path = Path(__file__).parent / "spec.yaml"
    with open(spec_path) as f:
        return yaml.safe_load(f)


def mock_backtest(candidate: dict, spec: dict) -> dict:
    """Mock backtest for testing without real data."""
    strategy = candidate.get("strategy", {})
    stype = strategy.get("type", "mean_reversion")
    
    results = {
        "mean_reversion": {
            "backtest_results": {
                "net_return": 0.035, "max_drawdown": 18.0,
                "profit_factor": 1.42, "win_rate": 56.0,
                "expectancy": 0.012, "trade_count": 72,
                "sharpe_ratio": 0.45, "max_consecutive_losses": 5,
                "resource_usage": {"execution_time_ms": 2100, "memory_peak_mb": 134.0, "cpu_avg_pct": 15}
            },
            "walk_forward": {"windows_profitable": 2, "degradation_pct": 35}
        },
        "trend_following": {
            "backtest_results": {
                "net_return": 0.062, "max_drawdown": 22.0,
                "profit_factor": 1.55, "win_rate": 42.0,
                "expectancy": 0.018, "trade_count": 45,
                "sharpe_ratio": 0.68, "max_consecutive_losses": 6,
                "resource_usage": {"execution_time_ms": 1800, "memory_peak_mb": 98.0, "cpu_avg_pct": 11}
            },
            "walk_forward": {"windows_profitable": 2, "degradation_pct": 30}
        },
        "breakout": {
            "backtest_results": {
                "net_return": 0.048, "max_drawdown": 14.0,
                "profit_factor": 1.61, "win_rate": 38.0,
                "expectancy": 0.015, "trade_count": 58,
                "sharpe_ratio": 0.55, "max_consecutive_losses": 7,
                "resource_usage": {"execution_time_ms": 2400, "memory_peak_mb": 156.0, "cpu_avg_pct": 18}
            },
            "walk_forward": {"windows_profitable": 3, "degradation_pct": 20}
        },
    }
    return results.get(stype, results["mean_reversion"])


def real_backtest(candidate: dict, spec: dict) -> dict:
    """
    Run real backtest using BacktestEngine + dsl_translator.
    
    Pipeline:
    1. Translate DSL → strategy_func
    2. Run BacktestEngine
    3. Run Walk-Forward Analysis
    4. Return results dict for gate_evaluator
    """
    if not HAS_BACKTEST:
        print("  [WARN] No backtest engine, using mock")
        return mock_backtest(candidate, spec)
    
    strategy = candidate["strategy"]
    assets = strategy.get("assets", ["BTCUSDT"])
    timeframe = strategy.get("timeframe", "1h")
    
    # 1. Translate DSL → strategy_func
    try:
        strat_name, strat_func = translate_candidate_with_name(candidate)
    except Exception as e:
        return {
            "backtest_results": {
                "net_return": 0, "max_drawdown": 100,
                "profit_factor": 0, "win_rate": 0,
                "expectancy": 0, "trade_count": 0,
                "sharpe_ratio": 0, "max_consecutive_losses": 99,
                "failure_reasons": [f"Translation error: {e}"],
                "resource_usage": {"execution_time_ms": 0, "memory_peak_mb": 0, "cpu_avg_pct": 0}
            },
            "walk_forward": {"windows_profitable": 0, "degradation_pct": 100}
        }
    
    # 2. Run backtest for first asset (V1: single-asset)
    symbol = assets[0]
    engine = BacktestEngine(
        data_path=DATA_PATH,
        fee_rate=spec.get("fees", {}).get("fee_rate", 0.0005),
        slippage_bps=spec.get("fees", {}).get("slippage_bps", 5.0),
        initial_capital=10000.0
    )
    
    bt_result = engine.run(strat_name, strat_func, strategy.get("params", {}), symbol, timeframe)
    
    # 3. Walk-Forward Analysis
    wf_result = None
    try:
        wf_analyzer = WalkForwardAnalyzer(
            engine=engine,
            data_path=DATA_PATH,
            train_pct=0.7,
            n_windows=3
        )
        # Build param_grid from strategy indicators
        param_grid = {}
        for ind in strategy.get("indicators", []):
            period = ind.get("params", {}).get("period", 14)
            # Small grid: test original and ±20%
            p1 = max(2, int(period * 0.8))
            p2 = period
            p3 = min(500, int(period * 1.2))
            param_grid[f"{ind['name'].lower()}_period"] = [p1, p2, p3]
        
        wf_result = wf_analyzer.analyze(
            strategy_name=strat_name,
            strategy_func=strat_func,
            param_grid=param_grid,
            symbol=symbol,
            timeframe=timeframe
        )
    except Exception as e:
        print(f"  [WARN] Walk-Forward failed: {e}")
        wf_result = None
    
    # 4. Build results dict for gate_evaluator
    bt_dict = bt_result.to_dict()
    
    result = {
        "backtest_results": {
            "net_return": bt_dict.get("net_return", 0) / 100,  # engine returns %, gate expects decimal (0.05 = 5%)
            "max_drawdown": bt_dict.get("max_drawdown", 100),
            "profit_factor": bt_dict.get("profit_factor", 0),
            "win_rate": bt_dict.get("win_rate", 0),
            "expectancy": bt_dict.get("expectancy", 0),
            "trade_count": bt_dict.get("trade_count", 0),
            "sharpe_ratio": bt_dict.get("sharpe_ratio", 0),
            "max_consecutive_losses": bt_dict.get("max_consecutive_losses", 99),
            "failure_reasons": bt_dict.get("failure_reasons", []),
            "resource_usage": {
                "execution_time_ms": bt_dict.get("execution_time_ms", 99999),
                "memory_peak_mb": bt_dict.get("memory_peak_mb", 999),
                "cpu_avg_pct": 0  # not tracked by engine
            }
        },
        "walk_forward": {
            "windows_profitable": sum(1 for r in (wf_result.oos_results or []) if r.get("return", 0) > 0) if wf_result else 0,
            "degradation_pct": max((r.get("degradation", 1.0) * 100 for r in (wf_result.oos_results or [])), default=100) if wf_result else 100
        }
    }
    
    return result


def build_feedback(gate_result: dict, candidate: dict) -> str:
    """Build feedback string for the KI from gate evaluation."""
    lines = [f"Strategie '{candidate['strategy']['name']}' hat FAIL."]
    lines.append(f"Gescheiterte Gates: {', '.join(gate_result['failed_gates'])}")
    lines.append("\nDetail:")
    for hint in gate_result['improvement_hints']:
        lines.append(f"  - {hint}")
    lines.append("\nVerbessere diese spezifischen Punkte. Behalte den Grundansatz bei.")
    return "\n".join(lines)


def format_discord_report(summary: dict, run_id: str) -> str:
    """Format a clean Discord report from the run summary."""
    lines = [f"🏭 **Foundry Weekly Report** `{run_id}`"]
    lines.append("")
    
    verdict = summary.get("verdict", "FAIL")
    iterations = summary.get("iterations_run", 0)
    max_iter = summary.get("max_iterations", 5)
    
    if verdict == "PASS":
        name = summary.get("passed_candidate", "unknown")
        lines.append(f"✅ **{name}** → BACKTEST_PASS")
        lines.append(f"   Gefunden in Iteration {iterations}/{max_iter}")
        lines.append(f"   Nächster Schritt: Paper/Shadow Trading (V2)")
    else:
        lines.append("❌ **0 PASS, alle Kandidaten FAIL**")
        lines.append(f"   {iterations} Iterationen, keine Strategie besteht alle Gates")
        
        # Show last iteration's failed gates
        iters = summary.get("iterations", [])
        if iters:
            last = iters[-1]
            if last.get("failed_gates"):
                lines.append(f"   Letzte Gates: {', '.join(last['failed_gates'])}")
    
    lines.append("")
    lines.append("_Spec = Wahrheit. Gates = Wahrheit. Rest = Suche._")
    return "\n".join(lines)


def send_discord_report(report_text: str, webhook_url: str = None):
    """Send Foundry report to Discord.
    
    Priority:
    1. Use OpenClaw message tool (via subprocess) - preferred, no webhook needed
    2. Fall back to DISCORD_WEBHOOK_URL env var
    """
    import subprocess
    
    # Try OpenClaw message first (most reliable, uses existing Discord bot)
    try:
        result = subprocess.run(
            ["openclaw", "message", "send",
             "--channel", "discord",
             "--target", "1476569099386622087",
             report_text],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            print("  ✅ Discord report sent via OpenClaw")
            return True
    except Exception:
        pass
    
    # Fall back to webhook
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not url:
        print("  [INFO] No Discord webhook configured, skipping report")
        return False
    
    try:
        import urllib.request
        payload = json.dumps({"content": report_text}).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 204 or resp.status == 200:
                print("  ✅ Discord report sent via webhook")
                return True
            else:
                print(f"  ⚠️ Discord webhook returned status {resp.status}")
                return False
    except Exception as e:
        print(f"  ⚠️ Discord report failed: {e}")
        return False


def run_evolution(use_mock: bool = False, dry_run: bool = False):
    """Run the full Foundry evolution loop."""
    spec = load_spec()
    max_iter = spec.get("evolution", {}).get("max_iterations", MAX_ITERATIONS)
    
    # Create run directory
    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Save spec used
    with open(run_dir / "spec_used.yaml", "w") as f:
        yaml.dump(spec, f)
    
    mode = "MOCK" if use_mock else "DRY-RUN" if dry_run else "LIVE"
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  Pecz Foundry v2.0                           ║")
    print(f"║  Max Iterations: {max_iter}                           ║")
    print(f"║  Mode: {mode:<38} ║")
    print(f"║  Data: {DATA_PATH[:38]:<38} ║")
    print(f"╚══════════════════════════════════════════════╝\n")
    
    all_results = []
    feedback = None
    passed_candidate = None
    passed_gate_result = None
    
    for iteration in range(1, max_iter + 1):
        print(f"── Iteration {iteration}/{max_iter} ──")
        iter_dir = run_dir / f"iteration_{iteration}"
        iter_dir.mkdir(exist_ok=True)
        
        # 1. Generate candidates (Gemma4)
        try:
            candidates = generate_candidates(spec, feedback, iteration)
        except Exception as e:
            print(f"  ❌ Generator failed: {e}")
            candidates = []
        
        if not candidates:
            print(f"  ⚠️ No valid candidates generated. Skipping iteration.")
            continue
        
        if dry_run:
            print(f"  📋 Dry-run: {len(candidates)} candidates generated (no backtest)")
            for i, c in enumerate(candidates):
                with open(iter_dir / f"candidate_{i+1}.json", "w") as f:
                    json.dump(c, f, indent=2)
                print(f"    {i+1}. {c['strategy']['name']} ({c['strategy']['type']})")
            all_results.append({
                "iteration": iteration,
                "n_candidates": len(candidates),
                "best_verdict": "DRY-RUN",
                "failed_gates": []
            })
            continue
        
        # 2. Evaluate each candidate
        iter_best = None
        iter_best_result = None
        
        for i, candidate in enumerate(candidates):
            cand_name = candidate["strategy"]["name"]
            
            # Save candidate
            with open(iter_dir / f"candidate_{i+1}.json", "w") as f:
                json.dump(candidate, f, indent=2)
            
            # Backtest (real or mock)
            if use_mock:
                results = mock_backtest(candidate, spec)
            else:
                results = real_backtest(candidate, spec)
            
            # Save backtest result
            with open(iter_dir / f"backtest_{i+1}.json", "w") as f:
                json.dump(results, f, indent=2, default=str)
            
            # Check for backtest failure
            failures = results.get("backtest_results", {}).get("failure_reasons", [])
            if failures:
                print(f"  Kandidat {i+1} '{cand_name}': BACKTEST-FAIL")
                for fail in failures:
                    print(f"    {fail}")
                continue
            
            # Gate evaluation
            gate_result = evaluate_all(results, candidate, spec)
            
            # Save gate result
            with open(iter_dir / f"gate_{i+1}.json", "w") as f:
                json.dump(gate_result, f, indent=2)
            
            verdict = gate_result["verdict"]
            print(f"  Kandidat {i+1} '{cand_name}': {verdict}")
            if verdict == "FAIL":
                print(f"    Failed: {gate_result['failed_gates']}")
            
            # Track best
            if verdict == "PASS":
                passed_candidate = candidate
                passed_gate_result = gate_result
                print(f"\n  🎯 BACKTEST_PASS! '{cand_name}' besteht alle Gates!")
                break
            elif iter_best is None or len(gate_result["passed_gates"]) > len(iter_best_result["passed_gates"]):
                iter_best = candidate
                iter_best_result = gate_result
        
        all_results.append({
            "iteration": iteration,
            "n_candidates": len(candidates),
            "best_verdict": "BACKTEST_PASS" if passed_candidate else "FAIL",
            "failed_gates": iter_best_result["failed_gates"] if iter_best_result and not passed_candidate else []
        })
        
        # 3. Check if we found a PASS
        if passed_candidate:
            break
        
        # 4. Build feedback for next iteration
        if iter_best_result:
            feedback = build_feedback(iter_best_result, iter_best)
            print(f"\n  Feedback für nächste Iteration:")
            for hint in iter_best_result["improvement_hints"][:3]:
                print(f"    {hint}")
    
    # ── Summary ──
    summary = {
        "run_id": run_id,
        "completed_at": datetime.now().isoformat(),
        "mode": mode,
        "max_iterations": max_iter,
        "iterations_run": len(all_results),
        "verdict": "BACKTEST_PASS" if passed_candidate else "FAIL",
        "passed_candidate": passed_candidate["strategy"]["name"] if passed_candidate else None,
        "iterations": all_results
    }
    
    with open(run_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    # Discord report
    discord_msg = format_discord_report(summary, run_id)
    with open(run_dir / "discord_report.txt", "w") as f:
        f.write(discord_msg)
    
    print(f"\n╔══════════════════════════════════════════════╗")
    if passed_candidate:
        print(f"║  🎯 VERDICT: BACKTEST_PASS                    ║")
        print(f"║  Strategy: {passed_candidate['strategy']['name']:<32} ║")
    else:
        print(f"║  ❌ VERDICT: FAIL                              ║")
        print(f"║  Keine Strategie besteht alle 5 Gates        ║")
    print(f"║  Iterations: {len(all_results)}/{max_iter}                              ║")
    print(f"║  Mode: {mode:<38} ║")
    print(f"╚══════════════════════════════════════════════╝")
    
    print(f"\n📋 Discord Report:\n{discord_msg}")
    
    # Send to Discord
    send_discord_report(discord_msg)
    
    return summary


if __name__ == "__main__":
    use_mock = "--mock" in sys.argv
    dry_run = "--dry-run" in sys.argv
    summary = run_evolution(use_mock=use_mock, dry_run=dry_run)