#!/usr/bin/env python3
"""
Foundry Evolution V4 — Creative Explosion

Temp 0.7, offene Strategie-Suche (kein BB+RSI-Fokus).
V17 als Benchmark ("schlag das"), aber Freiheit für komplett neue Typen.
10 Iterationen, 3 Kandidaten pro Iteration.
Multi-Asset Backtest (6 Assets × 2 Perioden).
"""

import json
import os
import sys
import re
import time
import urllib.request
from datetime import datetime as dt
from pathlib import Path

import polars as pl

RESEARCH_DIR = Path(__file__).parent
DATA_PATH = RESEARCH_DIR / "data"
RESULTS_DIR = RESEARCH_DIR / "runs" / "evolution_v4"
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
    "2yr": ("2023-01-01", "2024-12-31"),
}

PREVIOUS_RUNS_DIR = RESULTS_DIR  # loads hall_of_fame from previous runs

# V17 Benchmark (Mean_Reversion_BB from V3)
V17_BENCHMARK = {
    "name": "V17_Mid_Target_Exit",
    "entry": "close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200",
    "exit": {"trailing_stop_pct": 1.5, "stop_loss_pct": 3.0, "max_hold_bars": 36},
    "score_v3": 4.88,
    "profitable_assets": "5/6",
    "avg_return": "+3.88%",
}


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
            'type': candidate.get('type', 'momentum').lower().replace('-', '_').replace(' ', '_'),
            'indicators': candidate.get('indicators', []),
            'entry': {'condition': candidate.get('entry_condition', '')},
            'exit': candidate.get('exit_config', {}),
        }
    }


def backtest_multi_asset(candidate: dict, engine: BacktestEngine) -> dict:
    """Backtest a candidate across all 6 assets × 2 periods."""
    results = {}
    all_returns = []
    all_dds = []
    all_cls = []
    all_trades = []
    
    for asset in ASSETS:
        for period_name, (start, end) in PERIODS.items():
            try:
                df = load_df(asset, start, end)
                if len(df) < 50:
                    results[f"{asset}_{period_name}"] = {"error": "insufficient data"}
                    continue
                
                strategy_spec = candidate_to_strategy_spec(candidate)
                _, strategy_func = translate_candidate_with_name(strategy_spec)
                
                exit_config = candidate.get("exit_config", {})
                result = engine.run(
                    strategy_name=candidate.get("name", "?"),
                    strategy_func=strategy_func,
                    params={},
                    symbol=asset,
                    timeframe="1h",
                    exit_config=exit_config,
                    df=df,
                )
                
                r = {
                    "R": round(result.net_return, 2),
                    "DD": round(result.max_drawdown, 2),
                    "CL": result.max_consecutive_losses,
                    "PF": round(result.profit_factor, 2),
                    "WR": round(result.win_rate, 1),
                    "T": result.trade_count,
                }
                
                if result.trade_count > 0:
                    all_returns.append(result.net_return)
                    all_dds.append(result.max_drawdown)
                    all_cls.append(result.max_consecutive_losses)
                    all_trades.append(result.trade_count)
                
                results[f"{asset}_{period_name}"] = r
                
            except Exception as e:
                results[f"{asset}_{period_name}"] = {"error": str(e)[:80]}
    
    # Aggregate scoring
    if not all_returns:
        return {
            "name": candidate.get("name", "?"),
            "avg_return": 0,
            "avg_dd": 0,
            "max_cl": 99,
            "min_trades": 0,
            "profitable_assets": "0/6",
            "score": 0,
            "assets": results,
        }
    
    # Use 2024 period for scoring (matches V3 methodology)
    returns_2024 = [results.get(f"{a}_2024", {}).get("R", -999) for a in ASSETS if isinstance(results.get(f"{a}_2024"), dict) and "error" not in results.get(f"{a}_2024", {})]
    dds_2024 = [results.get(f"{a}_2024", {}).get("DD", 100) for a in ASSETS if isinstance(results.get(f"{a}_2024"), dict) and "error" not in results.get(f"{a}_2024", {})]
    cls_2024 = [results.get(f"{a}_2024", {}).get("CL", 99) for a in ASSETS if isinstance(results.get(f"{a}_2024"), dict) and "error" not in results.get(f"{a}_2024", {})]
    trades_2024 = [results.get(f"{a}_2024", {}).get("T", 0) for a in ASSETS if isinstance(results.get(f"{a}_2024"), dict) and "error" not in results.get(f"{a}_2024", {})]
    
    profitable = sum(1 for r in returns_2024 if r > 0) if returns_2024 else 0
    total_assets = len(returns_2024) if returns_2024 else 1
    
    avg_return = sum(returns_2024) / len(returns_2024) if returns_2024 else 0
    avg_dd = sum(dds_2024) / len(dds_2024) if dds_2024 else 100
    max_cl = max(cls_2024) if cls_2024 else 99
    min_trades = min(trades_2024) if trades_2024 else 0
    
    # Score: same as V3 (higher = better)
    # +2 for profitable, -0.5 for each % DD, +avg_return * 0.3
    score = (profitable * 2) - (avg_dd * 0.5) + (avg_return * 0.3)
    if min_trades < 10:
        score *= 0.3  # Penalize low trade count
    if max_cl > 12:
        score *= 0.5  # Penalize high consecutive losses
    
    return {
        "name": candidate.get("name", "?"),
        "type": candidate.get("type", "?"),
        "entry_condition": candidate.get("entry_condition", "?"),
        "exit_config": candidate.get("exit_config", {}),
        "avg_return": round(avg_return, 2),
        "avg_dd": round(avg_dd, 2),
        "max_cl": max_cl,
        "min_trades": min_trades,
        "profitable_assets": f"{profitable}/{total_assets}",
        "score": round(score, 2),
        "assets": results,
        "iteration": candidate.get("_iteration", 0),
    }


def call_llm(prompt: str, temperature: float = 0.7) -> dict:
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 3000,
        "temperature": temperature,
    }).encode()
    
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def parse_candidates(response_text: str) -> list:
    """Parse LLM response into list of candidates."""
    # Try code block first
    json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response_text, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    else:
        # Try raw JSON
        text = response_text.strip()
        if text.startswith('['):
            pass
        else:
            bracket_match = re.search(r'\[.*\]', text, re.DOTALL)
            if bracket_match:
                text = bracket_match.group(0)
            else:
                return []
    
    try:
        candidates = json.loads(text)
        if isinstance(candidates, list):
            return candidates
        elif isinstance(candidates, dict):
            return [candidates]
    except json.JSONDecodeError as e:
        print(f"  ⚠️ JSON parse error: {e}")
        print(f"  Text preview: {text[:200]}")
    return []


PROMPT_TEMPLATE = """Du bist ein Quant-Stratege für Crypto-Perps (Hyperliquid, 1h, 0.01% Maker-Fees, 100€ Startkapital).

AUFGABE: Generiere {n_candidates} STRATEGISCH VERSCHIEDENE Kandidaten. NICHT nur Mean-Reversion!

BENCHMARK (zum Schlagen):
V17 Mean_Reversion_BB: Score 4.88, 5/6 profitabel, Avg R +3.88%, DD 5.66%, CL max 8
Entry: close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200
Exit: Trail 1.5%, SL 3.0%, Max Hold 36h

DU SOLLT ETWAS ANDERES PROBIEREN — nicht nur BB+RSI-Varianten!

STRATEGIE-TYPEN (wähle VERSCHIEDENE):

1. **Momentum-Rotation**: RSI-Momentum + EMA-Stack (rsi_14 > 55 AND ema_20 > ema_50 AND ema_50 > ema_200)
2. **Trend-Exhaustion**: ADX-Abfall + RSI-Divergenz (adx_14 < 25 AND rsi_14 > rsi_14_prev BUT close < ema_50) — Trend verliert Steam
3. **Volatility-Breakout**: BB-Squeeze → Expansion (bb_width_20 < threshold AND atr_14 > atr_sma)
4. **EMA-Cross + Filter**: EMA_12 > EMA_50 (Golden Cross) NUR WENN adx_14 > 20 (Trend bestätigt)
5. **RSI-Divergenz**: RSI steigt während Preis fällt (bottom divergence)
6. **Multi-Timeframe-Proxy**: close > ema_200 (Macro-Trend) + close < ema_20 (Short-Term Pullback) + rsi_14 < 40
7. **ADX-Momentum**: adx_14 > 25 AND macd_hist > 0 AND close > ema_50
8. **Mean-Reversion VARIANTE**: Aber NICHT einfach bb_lower + rsi < 30! Was gibt es noch? ZScore, Stochastic, RSI-Bounce von 40 (nicht 30)

WICHTIGE REGELN:
- NIEMALS period=0 oder period=1! Minimum period=2
- entry_condition MUSS konkreter DSL-Ausdruck sein
- Indikator-Namen MÜSSEN mit period-Nummer matchen (rsi_14, ema_50, bb_upper_20 etc.)
- IMMER exit_config mit trailing_stop_pct + stop_loss_pct + max_hold_bars
- Max 4 Indikatoren pro Strategie
- Nur LONG

GÜLTIGE INDIKATOREN:
SMA(N), EMA(N), RSI(N), BB(N, std_dev=2.0), ATR(N), MACD(12,26,9), ZSCORE(N), ADX(N)
Sonder-Variablen: bb_upper_N, bb_lower_N, bb_mid_N, bb_width_N, macd_line, macd_signal, macd_hist, close, open, high, low, volume

DSL-FORMAT (genau dieses JSON, kein Markdown):
[
  {{
    "name": "deskriptiver_name",
    "type": "trend_following|momentum|mean_reversion|breakout|hybrid",
    "indicators": [
      {{"name": "EMA", "params": {{"period": 50}}}},
      {{"name": "RSI", "params": {{"period": 14}}}}
    ],
    "entry_condition": "close > ema_50 AND rsi_14 > 55 AND adx_14 > 20",
    "exit_config": {{
      "trailing_stop_pct": 3.0,
      "stop_loss_pct": 3.5,
      "max_hold_bars": 72
    }}
  }}
]

{feedback_section}

Gib NUR ein JSON-Array zurück. Kein Text davor oder danach."""


def load_previous_hall_of_fame() -> list:
    """Load best strategies from previous runs to seed the prompt."""
    best = []
    # Check all evolution_v4 result files
    if RESULTS_DIR.exists():
        for f in sorted(RESULTS_DIR.glob("evolution_v4_results*.json")):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                hof = data.get("hall_of_fame", [])
                for r in hof:
                    best.append(r)
            except Exception:
                continue
    # Deduplicate by name, keep best score
    by_name = {}
    for r in best:
        name = r.get("name", "?")
        if name not in by_name or r.get("score", 0) > by_name[name].get("score", 0):
            by_name[name] = r
    result = sorted(by_name.values(), key=lambda x: x.get("score", 0), reverse=True)[:10]
    return result


def run_evolution_v4(n_iterations: int = 10, candidates_per_iter: int = 3):
    print("=" * 70)
    print("EVOLUTION V4 — Creative Explosion")
    print(f"Temp: 0.7 | Iterations: {n_iterations} | Candidates/Iter: {candidates_per_iter}")
    print(f"Assets: {', '.join(ASSETS)} | Periods: {list(PERIODS.keys())}")
    print(f"Benchmark: V17 (Score {V17_BENCHMARK['score_v3']})")
    print("=" * 70)
    
    engine = BacktestEngine(str(DATA_PATH), fee_rate=0.0005, slippage_bps=5.0, initial_capital=10000.0)
    all_results = []
    hall_of_fame = []
    total_tokens = 0
    
    previous_hof = load_previous_hall_of_fame()
    if previous_hof:
        print(f"  📚 Loaded {len(previous_hof)} strategies from previous runs")
    
    feedback = "Erste Iteration — noch keine Ergebnisse. Sei kreativ!"
    
    for iteration in range(1, n_iterations + 1):
        print(f"\n{'─' * 70}")
        print(f"ITERATION {iteration}/{n_iterations}")
        print(f"{'─' * 70}")
        
        # Build feedback section
        if iteration == 1:
            feedback_section = ""
        else:
            feedback_section = f"\nERGEBNISSE VON ITERATION {iteration-1}:\n{feedback}\n\nVerbessere basierend auf diesem Feedback. Probiere ANDERE Ansätze!"
        
        # Hall of fame context (includes previous runs)
        combined_hof = previous_hof + hall_of_fame
        # Deduplicate
        seen = set()
        unique_hof = []
        for r in combined_hof:
            name = r.get("name", "?")
            if name not in seen:
                seen.add(name)
                unique_hof.append(r)
        combined_hof = sorted(unique_hof, key=lambda x: x.get("score", 0), reverse=True)[:10]
        
        hof_section = ""
        if combined_hof:
            hof_lines = []
            for i, h in enumerate(combined_hof[:5]):
                hof_lines.append(
                    f"  {i+1}. {h['name']}: Score={h.get('score',0):.2f}, R={h.get('avg_return',0):+.1f}%, "
                    f"DD={h.get('avg_dd',0):.1f}%, CL={h.get('max_cl','?')}, Profit={h.get('profitable_assets','?')}\n"
                    f"     Entry: {h.get('entry_condition','?')}\n"
                    f"     Exit: {h.get('exit_config',{})}"
                )
            hof_section = f"\nBESTE STRATEGIEN (bisherige + diese Run):\n" + "\n".join(hof_lines) + "\n\nVerbessere diese oder finde etwas BESSERES!"
        
        prompt = PROMPT_TEMPLATE.format(
            n_candidates=candidates_per_iter,
            feedback_section=feedback_section + hof_section,
        )
        
        # Call LLM
        try:
            print(f"  🤖 Calling {MODEL} (temp=0.7)...")
            resp = call_llm(prompt, temperature=0.7)
            tokens_used = resp.get("usage", {}).get("total_tokens", 0)
            total_tokens += tokens_used
            content = resp["choices"][0]["message"]["content"]
            
            candidates = parse_candidates(content)
            if not candidates:
                print(f"  ⚠️ No valid JSON → retry with simpler prompt")
                feedback = "Letzte Iteration lieferte kein gültiges JSON. Bitte nur JSON-Array zurückgeben."
                continue
            
            print(f"  📦 Parsed {len(candidates)} candidates ({tokens_used} tokens)")
            
        except Exception as e:
            print(f"  ❌ LLM error: {e}")
            feedback = f"LLM call failed: {e}"
            continue
        
        # Backtest each candidate
        iter_feedback = []
        for i, cand in enumerate(candidates):
            cand["_iteration"] = iteration
            cname = cand.get("name", f"Unknown_{i}")
            print(f"\n  🧪 [{iteration}.{i+1}] Testing: {cname}")
            print(f"     Entry: {cand.get('entry_condition', '?')[:80]}")
            print(f"     Exit:  {cand.get('exit_config', {})}")
            
            result = backtest_multi_asset(cand, engine)
            result["iteration"] = iteration
            all_results.append(result)
            
            # Status
            status = "✅" if result["score"] > 0 else "❌"
            print(f"  {status} {cname}: Score={result['score']:.2f} R={result['avg_return']:+.1f}% DD={result['avg_dd']:.1f}% CL={result['max_cl']} T≥{result['min_trades']} Profitable={result['profitable_assets']}")
            
            # Per-asset detail
            for asset in ASSETS:
                key = f"{asset}_2024"
                r = result["assets"].get(key, {})
                if isinstance(r, dict) and "error" not in r:
                    marker = "+" if r.get("R", 0) > 0 else ""
                    print(f"     {asset}: R={marker}{r.get('R', '?')}% DD={r.get('DD', '?')}% T={r.get('T', '?')}")
                elif isinstance(r, dict) and "error" in r:
                    print(f"     {asset}: ERROR - {r['error'][:50]}")
            
            # Feedback for next iteration
            iter_feedback.append(
                f"{cname} (type={result.get('type', '?')}): Score={result['score']:.2f}, "
                f"R={result['avg_return']:+.1f}%, DD={result['avg_dd']:.1f}%, "
                f"CL={result['max_cl']}, T≥{result['min_trades']}, "
                f"Profitable={result['profitable_assets']}"
            )
            
            # Update hall of fame
            if result["score"] > 0:
                if len(hall_of_fame) < 10:
                    hall_of_fame.append(result)
                elif result["score"] > hall_of_fame[-1]["score"]:
                    hall_of_fame[-1] = result
                hall_of_fame.sort(key=lambda x: x["score"], reverse=True)
        
        feedback = "\n".join(iter_feedback)
        
        # Show current best
        if hall_of_fame:
            best = hall_of_fame[0]
            vs_v17 = "🏆 BEATS V17!" if best["score"] > V17_BENCHMARK["score_v3"] else f"({V17_BENCHMARK['score_v3']:.2f} - {best['score']:.2f} = {V17_BENCHMARK['score_v3'] - best['score']:.2f} behind V17)"
            print(f"\n  🏆 Best: {best['name']} = Score {best['score']:.2f} {vs_v17}")
    
    # ═══════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("EVOLUTION V4 — FINAL RESULTS")
    print(f"{'=' * 70}")
    print(f"Total candidates: {len(all_results)} | Tokens: {total_tokens}")
    
    if hall_of_fame:
        print(f"\n🏆 HALL OF FAME (Top 10):")
        print(f"{'#':<4} {'Name':<40} {'Score':>8} {'R%':>8} {'DD%':>8} {'CL':>4} {'T≥':>4} {'Profit':>8}")
        print("-" * 90)
        for i, r in enumerate(hall_of_fame[:10]):
            vs = "🏆" if r["score"] > V17_BENCHMARK["score_v3"] else "  "
            print(f"{i+1:<4} {r['name'][:40]:<40} {r['score']:>8.2f} {r['avg_return']:>+8.1f} {r['avg_dd']:>8.1f} {r['max_cl']:>4} {r['min_trades']:>4} {r['profitable_assets']:>8} {vs}")
    else:
        print("\n❌ No candidates scored > 0")
    
    # Compare with V17
    print(f"\n📊 V17 BENCHMARK: Score {V17_BENCHMARK['score_v3']:.2f} | R={V17_BENCHMARK['avg_return']} | Profitable={V17_BENCHMARK['profitable_assets']}")
    if hall_of_fame and hall_of_fame[0]["score"] > V17_BENCHMARK["score_v3"]:
        print(f"🎉 NEW CHAMPION: {hall_of_fame[0]['name']} beats V17!")
    elif hall_of_fame:
        print(f"📉 No strategy beats V17 yet. Best: {hall_of_fame[0]['name']} (Score {hall_of_fame[0]['score']:.2f})")
    
    # Save results
    results_file = RESULTS_DIR / "evolution_v4_results.json"
    with open(results_file, "w") as f:
        json.dump({
            "total_tokens": total_tokens,
            "results": all_results,
            "hall_of_fame": hall_of_fame[:10],
            "v17_benchmark": V17_BENCHMARK,
            "config": {
                "temperature": 0.7,
                "iterations": n_iterations,
                "candidates_per_iter": candidates_per_iter,
                "assets": ASSETS,
                "periods": list(PERIODS.keys()),
            }
        }, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to {results_file}")
    return all_results, hall_of_fame


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--candidates", type=int, default=3)
    args = parser.parse_args()
    
    run_evolution_v4(n_iterations=args.iterations, candidates_per_iter=args.candidates)