#!/usr/bin/env python3
"""
Foundry Evolution V10 — Funding-First

Changes from V9:
- 3 Arms: FUNDING-LONG, FUNDING-SHORT, FUNDING-SHIFT (no more MR/Trend/Vol)
- Data: data_v10/ with pre-computed funding features
- 6 Features: funding_z, regime (bull200), squeeze, fund_cross_up, vol_ratio, ret_4h
- Asset-specific: Long on BTC/SOL/AVAX/DOGE, Short on ADA, Shift on ETH
- ~100 Seeds per run (not 1000)
- 5 Runs max (then stop if 0 WF-passed)
- Kill criterion: 0/5 OOS positive in Phase 1 = project ends
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
import numpy as np

RESEARCH_DIR = Path(__file__).parent
sys.path.insert(0, str(RESEARCH_DIR))
sys.path.insert(0, str(RESEARCH_DIR / "backtest"))
sys.path.insert(0, str(RESEARCH_DIR / "strategy_lab"))

from backtest.backtest_engine import BacktestEngine
from composite_fitness import compute_fitness, parse_profitable_ratio
from walk_forward_gate import build_strategy_func, run_wf_on_candidate

# ============================================================================
# CONFIG
# ============================================================================

N_EXPLORATION_PER_TYPE = 10
N_MUTATIONS_PER_PARENT = 5
N_CROSSOVERS = 5
N_HARD_CHECK_TOP = 3

WF_WINDOWS_NORMAL = 10
WF_WINDOWS_HARD = 10
WF_PASS_ROBUSTNESS = 50.0
WF_PASS_PROFITABLE = 2  # ≥2 profitable target-assets

# IS pre-filter: minimum trades per asset per window
IS_MIN_TRADES_THRESHOLD = 2

API_URL = os.environ.get("OLLAMA_API_URL", "http://172.17.0.1:32771/v1/chat/completions")
API_KEY = os.environ.get("OLLAMA_API_KEY", "ollama-cloud")
MODEL = os.environ.get("GENERATOR_MODEL", "gemma4:31b-cloud")
FALLBACK_MODEL = "deepseek-v4-pro:cloud"

ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
LONG_ASSETS = ["BTC", "SOL", "AVAX", "DOGE"]  # Long at low funding
SHORT_ASSETS = ["ADA"]  # Short at high funding (ADA confirmed)
SHIFT_ASSETS = ["ETH", "BTC", "SOL"]  # Fund regime shift works here

DATA_DIR = RESEARCH_DIR / "data_v10"
DATA_FILE_MAP = {a: f"{a}USDT_1h_full.parquet" for a in ASSETS}
PERIODS = {
    "2024": ("2024-01-01", "2024-12-31"),
    "2yr": ("2023-01-01", "2024-12-31"),
}

HOF_DIR = RESEARCH_DIR / "runs" / "evolution_v10"
HOF_FILE = HOF_DIR / "evolution_v10_hof.json"
HOF_DIR.mkdir(parents=True, exist_ok=True)

MAX_RUNS = 5  # Stop after 5 runs if 0 WF-passed

# ============================================================================
# ARM DEFINITIONS (V10 — Funding-First)
# ============================================================================

ARMS = [
    {
        "name": "FUNDING-LONG",
        "prompt_key": "FUNDING_LONG",
        "target_assets": LONG_ASSETS,
        "temperature": 0.3,
        "is_mr": False,
        "exit_style": "signal_reversal",
        "default_exit_condition": "funding_z > 0.5",
        "direction": "LONG",
    },
    {
        "name": "FUNDING-SHORT",
        "prompt_key": "FUNDING_SHORT",
        "target_assets": SHORT_ASSETS,
        "temperature": 0.3,
        "is_mr": False,
        "exit_style": "signal_reversal",
        "default_exit_condition": "funding_z < -0.5",
        "direction": "SHORT",
    },
    {
        "name": "FUNDING-SHIFT",
        "prompt_key": "FUNDING_SHIFT",
        "target_assets": SHIFT_ASSETS,
        "temperature": 0.4,
        "is_mr": False,
        "exit_style": "signal_reversal",
        "default_exit_condition": "fund_cross_down == 1",
        "direction": "LONG",
    },
]

# ============================================================================
# LLM PROMPTS (V10 — Funding-First)
# ============================================================================

OOS_RESULTS = """
OOS-VALIDIERTE ERGEBNISSE (Feb-Apr 2026, TRUE UNSEEN):
- BTC Long P10 (funding_z < -0.93): +0.33%/trade, 52% Win, 412 trades
- SOL Long z<-2: +0.61%/trade, 63% Win, 97 trades
- AVAX Long z<-1: +0.63%/trade, 52% Win, 228 trades
- ETH 7d Fund→Pos Shift: +1.12%/trade, 58% Win, 101 trades
- ADA Short P90 (funding_z > 1.12): +0.81%/trade, 64% Win, 118 trades
- DOGE Long P10: +1.02%/trade, 55% Win
"""

INDICATOR_LIST_V10 = """Verfügbare Features (NUTZE DIESE EXAKTEN NAMEN):
PRECOMPUTED (direkt als Spalte im Datensatz, KEINE Berechnung nötig):
- funding_z: Funding Rate 30d Z-Score (negativ = Shorts zahlen, positiv = Longs zahlen)
- funding_rate: Raw Funding Rate
- bull200: 1 wenn close > EMA200 (Bull-Regime), 0 wenn Bear
- bull50: 1 wenn close > EMA50
- fund_cross_up: 1 wenn 7d-Funding-Mean von negativ nach positiv wechselt (Regime-Shift)
- fund_cross_down: 1 wenn 7d-Funding-Mean von positiv nach negativ wechselt
- squeeze: 1 wenn 4h-Return < -2% UND funding_z > 1.5 (Short Squeeze Setup)
- vol_ratio: Volume / 24h-MA (Hoch = ungewöhnliches Volume)
- ret_4h: 4h Return (für Momentum/Squeeze-Erkennung)
- ema50, ema200: Moving Averages (als Preis-Level, nicht Entry)
- close, open, high, low, volume

STANDARD-INDIKATOREN (werden berechnet — ABER: 0 Alpha bewiesen, NUR als Bestätigung):
- rsi_N, bb_lower_N, adx_N, macd_hist_12_26, etc.
⚠️ VERWENDE STANDARD-INDIKATOREN NICHT ALS ENTRY! Nur funding_z, fund_cross_up, squeeze als Entry!"""

LESSONS_LEARNED_V10 = f"""LESSONS LEARNED (V7-V9: 150+ Strategien, 0 Alpha mit Standard-Indikatoren):
- Standard-Indikatoren (RSI, BB, MACD, EMA) haben 0 Alpha auf 1h-Crypto. NIE als Entry!
- Trailing Stop feuert NIE (80-91% signal_exit, Trail zu eng)
- Mean Reversion funktioniert NUR auf DOGE/ADA/AVAX, NIEMALS auf BTC/ETH
- Funding Rate IST der bewiesene Edge — 5/6 Signale OOS-positiv!
- Asset-Richtung: BTC/SOL/AVAX/DOGE = Long bei niedriger Funding, ADA = Short bei hoher Funding
- Regime bestimmt Richtung: Bear + Low Funding = Long, Bull + High Funding = Long

{OOS_RESULTS}

KERNPRINZIP: Funding = Entry-Signal. Regime = Richtung. Volume/Uhrzeit = Bestätigung.
Standard-Indikatoren NUR als Bestätigung, NIEMALS als Entry!"""

PROMPTS = {
    "FUNDING_LONG": f"""Du bist ein Quant-Stratege für 1h Crypto Perps auf Hyperliquid.
Generiere EINE Funding-basierte LONG-Strategie.

ZIEL-ASSETS: BTC, SOL, AVAX, DOGE (Long bei niedriger Funding — bewiesen!)

{LESSONS_LEARNED_V10}

{INDICATOR_LIST_V10}

ENTRY-REGELN:
- PRIMÄRER ENTRY = funding_z (MUSS enthalten sein!)
- funding_z < -1.0 als Basis (negativ = Shorts zahlen Longs = Contrarian Long)
- Kombiniere mit 1-2 Bestätigungen: bull200 == 1, vol_ratio > 1.5, fund_cross_up == 1
- KEIN OR! Nur AND als logischer Operator
- KEINE Array-Vergleiche

BEISPIELE (bewiesen OOS-positiv):
- funding_z < -1.0 AND bull200 == 1
- funding_z < -2.0 (restriktiver = stärkerer Edge!)
- funding_z < -1.5 AND vol_ratio > 1.5
- fund_cross_up == 1 AND bull200 == 1

EXIT: Nutze exit_condition, KEIN trailing_stop!
- Exit wenn Funding neutral wird: funding_z > 0.5
- ODER Regime wechselt: bull200 == 0
- Stop Loss: 3-5% (regime-abhängig), Max Hold: 24-48 Bars

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_condition": "funding_z > 0.5", "exit_config": {{"stop_loss_pct": 4.0, "max_hold_bars": 36}}}}""",

    "FUNDING_SHORT": f"""Du bist ein Quant-Stratege für 1h Crypto Perps auf Hyperliquid.
Generiere EINE Funding-basierte SHORT-Strategie.

ZIEL-ASSETS: NUR ADA (Short bei hoher Funding — bewiesen! 64% Win OOS!)

{LESSONS_LEARNED_V10}

{INDICATOR_LIST_V10}

ENTRY-REGELN:
- PRIMÄRER ENTRY = funding_z (MUSS enthalten sein!)
- funding_z > 1.0 als Basis (positiv = Longs zahlen Shorts = Overcrowded → Short)
- Kombiniere mit Bestätigung: bull200 == 0 (Bear-Regime), vol_ratio > 1.5
- KEIN OR! Nur AND als logischer Operator
- KEINE Array-Vergleiche

BEISPIELE (bewiesen OOS-positiv):
- funding_z > 1.0 AND bull200 == 0
- funding_z > 1.5 (höherer Threshold = stärkerer Edge)
- funding_z > 2.0 AND vol_ratio > 1.5

EXIT: Nutze exit_condition, KEIN trailing_stop!
- Exit wenn Funding neutral wird: funding_z < -0.5
- ODER Regime wechselt: bull200 == 1
- Stop Loss: 3-5%, Max Hold: 24-48 Bars

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_condition": "funding_z < -0.5", "exit_config": {{"stop_loss_pct": 4.0, "max_hold_bars": 36}}}}""",

    "FUNDING_SHIFT": f"""Du bist ein Quant-Stratege für 1h Crypto Perps auf Hyperliquid.
Generiere EINE Funding-Regime-Shift-Strategie für Long-Entry.

ZIEL-ASSETS: ETH, BTC, SOL (Regime-Shift funktioniert hier — ETH +1.12%/trade OOS!)

{LESSONS_LEARNED_V10}

{INDICATOR_LIST_V10}

ENTRY-REGELN:
- PRIMÄRER ENTRY = fund_cross_up (7d Funding wechselt von negativ zu positiv)
- fund_cross_up == 1 als Trigger
- Kombiniere mit Bestätigung: bull200 == 1, vol_ratio > 1.0, squeeze == 0
- KEIN OR! Nur AND als logischer Operator
- KEINE Array-Vergleiche

BEISPIELE (bewiesen OOS-positiv):
- fund_cross_up == 1 AND bull200 == 1
- fund_cross_up == 1 AND vol_ratio > 1.0
- fund_cross_up == 1 AND funding_z < 0.5 (Shift aber noch nicht extrem)

AUCH MÖGLICH: Kombination aus funding_z + squeeze
- squeeze == 1 AND funding_z > 1.5 (Short Squeeze Setup)
- ret_4h < -0.03 AND funding_z > 2.0 (tieferer Drop + extremere Funding)

EXIT: Nutze exit_condition, KEIN trailing_stop!
- Exit wenn Funding-Regime zurückdreht: fund_cross_down == 1
- ODER nach Zeit: Max Hold 36-48 Bars
- Stop Loss: 3-5%, Max Hold: 36-48 Bars

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_condition": "fund_cross_down == 1", "exit_config": {{"stop_loss_pct": 4.0, "max_hold_bars": 48}}}}""",
}

# ============================================================================
# LLM CALLS
# ============================================================================

def call_llm(prompt: str, temperature: float = 0.3, reasoning_effort: str = "high") -> str:
    """Call LLM with retry + fallback."""
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "reasoning_effort": reasoning_effort,
        "max_tokens": 2048,
    })
    req = urllib.request.Request(
        API_URL, data=payload.encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
            msg = data["choices"][0]["message"]
            content = msg.get("content", "")
            if not content.strip() and msg.get("reasoning", "").strip():
                content = msg["reasoning"]
            return content
    except urllib.error.HTTPError as e:
        if e.code == 503:
            print(f"  ⚠️ LLM 503, retrying in 10s...")
            time.sleep(10)
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    data = json.loads(resp.read())
                    return data["choices"][0]["message"].get("content", "")
            except Exception:
                pass
            # Fallback
            print(f"  ⚠️ Trying fallback model {FALLBACK_MODEL}")
            fb = json.dumps({
                "model": FALLBACK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": 2048,
            })
            fb_req = urllib.request.Request(API_URL, data=fb.encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
            try:
                with urllib.request.urlopen(fb_req, timeout=120) as resp:
                    return json.loads(resp.read())["choices"][0]["message"].get("content", "")
            except Exception as e3:
                print(f"  ⚠️ Fallback also failed: {e3}")
                return ""
        print(f"  ⚠️ LLM error: {e}")
        return ""
    except Exception as e:
        print(f"  ⚠️ LLM error: {e}")
        return ""


def normalize_condition(cond: str) -> str:
    """Normalize condition string."""
    cond = re.sub(r'\s+', ' ', cond.strip())
    # == 1 comparisons for binary features
    for feat in ['bull200', 'bull50', 'fund_cross_up', 'fund_cross_down', 'squeeze']:
        cond = re.sub(rf'\b{feat}\s*==\s*1\b', feat, cond)
    return cond


def parse_strategy(text: str) -> dict | None:
    """Parse LLM response into strategy dict."""
    m = re.search(r'\{[^{}]*\{[^{}]*\}[^{}]*\}', text, re.DOTALL)
    if not m:
        m = re.search(r'\{[^{}]+\}', text)
    if not m:
        return None
    for attempt in [m.group(), re.sub(r',\s*}', '}', m.group()), re.sub(r',\s*]', ']', m.group())]:
        try:
            d = json.loads(attempt)
            if "entry_condition" in d:
                d["entry_condition"] = normalize_condition(d["entry_condition"])
                if "exit_condition" in d:
                    d["exit_condition"] = normalize_condition(d["exit_condition"])
                entry = d["entry_condition"]
                if " OR " in entry.upper():
                    print(f"    ⚠️ Rejected OR in entry: {entry[:60]}")
                    return None
                # V10: Entry MUST contain funding feature
                funding_features = ['funding_z', 'funding_rate', 'fund_cross_up', 'fund_cross_down', 'squeeze']
                if not any(f in entry for f in funding_features):
                    print(f"    ⚠️ Rejected (no funding feature): {entry[:60]}")
                    return None
                if "exit_config" not in d:
                    d["exit_config"] = {}
                d["exit_config"].pop("trailing_stop_pct", None)
                return d
        except:
            pass
    return None


# ============================================================================
# EVALUATION
# ============================================================================

def get_target_assets(strategy_type: str) -> list:
    for arm in ARMS:
        if arm["prompt_key"] == strategy_type or arm["name"] == strategy_type:
            return arm["target_assets"]
    return ASSETS


def load_df(asset: str, start: str, end: str) -> pl.DataFrame:
    """Load data for an asset and period."""
    from datetime import datetime as dt, timezone
    data_file = DATA_DIR / DATA_FILE_MAP[asset]
    df = pl.scan_parquet(str(data_file)).collect()
    # Convert date strings to epoch ms for comparison with Int64 timestamps
    start_ms = int(dt.fromisoformat(start + "T00:00:00+00:00").timestamp() * 1000)
    end_ms = int(dt.fromisoformat(end + "T23:59:59+00:00").timestamp() * 1000)
    return df.filter(
        (pl.col("timestamp") >= start_ms) & (pl.col("timestamp") <= end_ms)
    )


def run_is_backtest(entry_condition: str, exit_config: dict, strategy_type: str = "",
                    target_assets: list = None) -> dict | None:
    try:
        exit_condition = exit_config.get("exit_condition", None)
        strategy_func, parseable = build_strategy_func(entry_condition, exit_condition=exit_condition)
        if not parseable or strategy_func is None:
            return None

        bt_exit_config = dict(exit_config)
        if exit_condition:
            bt_exit_config["exit_signal_col"] = "exit_signal"

        engine = BacktestEngine(data_path=str(DATA_DIR))
        test_assets = target_assets or ASSETS

        all_returns, all_dds, all_cls, all_trades = [], [], [], []
        profitable = 0

        for asset in test_assets:
            for period_name, (start, end) in PERIODS.items():
                try:
                    df = load_df(asset, start, end)
                    if len(df) < 50:
                        continue
                    result = engine.run(strategy_name="eval", strategy_func=strategy_func, params={},
                                        symbol=f"{asset}USDT", timeframe="1h",
                                        exit_config=bt_exit_config, df=df)
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

        avg_trades = sum(all_trades) / len(all_trades) if all_trades else 0
        if avg_trades < IS_MIN_TRADES_THRESHOLD:
            return None

        return {
            "avg_return": np.mean(all_returns),
            "avg_dd": np.mean(all_dds),
            "total_trades": sum(all_trades),
            "avg_trades": avg_trades,
            "profitable_assets": profitable,
            "n_assets": len(all_returns),
            "returns": all_returns,
        }
    except Exception as e:
        print(f"    ⚠️ IS backtest error: {e}")
        return None


def evaluate_candidate(candidate: dict, strategy_type: str = "", target_assets: list = None) -> dict | None:
    """Run IS backtest + WF gate on a candidate."""
    entry = candidate.get("entry_condition", "")
    exit_config = dict(candidate.get("exit_config", {}))
    if "exit_condition" in candidate:
        exit_config["exit_condition"] = candidate["exit_condition"]

    # IS Backtest
    is_result = run_is_backtest(entry, exit_config, strategy_type, target_assets)
    if is_result is None:
        return None

    # WF Gate
    exit_condition = exit_config.get("exit_condition", None)
    strategy_func, parseable = build_strategy_func(entry, exit_condition=exit_condition)
    if not parseable:
        return None

    wf_exit_config = dict(exit_config)
    if exit_condition:
        wf_exit_config["exit_signal_col"] = "exit_signal"

    try:
        wf_result = run_wf_on_candidate(
            name=candidate.get("name", "eval"),
            entry=entry,
            exit_config=wf_exit_config,
            n_windows=WF_WINDOWS_NORMAL,
            strategy_type=strategy_type,
            target_assets=target_assets or ASSETS,
        )
    except Exception as e:
        print(f"    ⚠️ WF error: {e}")
        return None

    if wf_result is None:
        return None

    # Composite fitness
    fitness_dict = {
        "avg_oos_return": wf_result.get("avg_oos_return", 0),
        "wf_profitable_10w": wf_result.get("profitable_count", 0),
        "wf_robustness_10w": wf_result.get("robustness", 0),
        "min_trades": is_result.get("avg_trades", 0),
        "avg_drawdown": is_result.get("avg_dd", 0),
        "assets": wf_result.get("assets", {}),
    }
    fitness_val, _ = compute_fitness(fitness_dict, target_assets=target_assets)

    return {
        "name": candidate.get("name", "unnamed"),
        "entry_condition": entry,
        "exit_condition": candidate.get("exit_condition", ""),
        "exit_config": exit_config,
        "type": strategy_type,
        "is_result": is_result,
        "wf_result": wf_result,
        "fitness_val": fitness_val,
        "passed": wf_result.get("passed", False),
    }


# ============================================================================
# HOF MANAGEMENT
# ============================================================================

def load_hof() -> list:
    if HOF_FILE.exists():
        try:
            with open(HOF_FILE) as f:
                return json.load(f)
        except:
            return []
    return []


def save_hof(hof: list):
    # Convert numpy types
    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return obj

    serializable = json.loads(json.dumps(hof, default=convert))
    with open(HOF_FILE, "w") as f:
        json.dump(serializable, f, indent=2)


def add_to_hof(hof: list, result: dict) -> bool:
    """Add result to HOF if it's a champion. Returns True if added."""
    if not result.get("passed"):
        return False

    entry = result["entry_condition"]
    # Check if already in HOF
    for h in hof:
        if h["entry_condition"] == entry:
            return False

    hof.append({
        "name": result["name"],
        "entry_condition": entry,
        "exit_condition": result.get("exit_condition", ""),
        "exit_config": result["exit_config"],
        "type": result["type"],
        "fitness_val": result["fitness_val"],
        "wf_robustness": result["wf_result"].get("robustness", 0),
        "wf_oos_return": result["wf_result"].get("avg_oos_return", 0),
        "wf_profitable": result["wf_result"].get("profitable_count", 0),
        "is_return": result["is_result"]["avg_return"],
        "is_trades": result["is_result"]["total_trades"],
        "added_at": datetime.now().isoformat(),
    })
    return True


# ============================================================================
# EXPLORATION
# ============================================================================

def explore_arm(arm: dict) -> list:
    """Generate N strategies for one arm using LLM."""
    prompt_template = PROMPTS[arm["prompt_key"]]
    candidates = []

    for i in range(N_EXPLORATION_PER_TYPE):
        print(f"  Generating {arm['name']} #{i+1}/{N_EXPLORATION_PER_TYPE}...")
        response = call_llm(prompt_template, temperature=arm["temperature"])
        if not response:
            continue

        parsed = parse_strategy(response)
        if parsed is None:
            print(f"    ✗ Parse failed")
            continue

        parsed["arm"] = arm["name"]
        candidates.append(parsed)
        print(f"    ✓ {parsed['name']}: {parsed['entry_condition'][:60]}")

    return candidates


# ============================================================================
# MUTATION
# ============================================================================

def mutate_strategy(parent: dict, arm: dict) -> dict | None:
    """Mutate a parent strategy via LLM."""
    prompt = f"""Mutiere diese Funding-Strategie. Ändere NUR die Schwellenwerte oder füge EINE Bestätigung hinzu.
Behalte den Kern-Entry bei (funding_z oder fund_cross)!

Original: {json.dumps(parent, ensure_ascii=False)}

{LESSONS_LEARNED_V10}

{INDICATOR_LIST_V10}

MUTATIONS-REGELN:
- Ändere Schwellenwerte: funding_z < -1.0 → <-1.5, oder <-0.5
- Füge EINE Bestätigung hinzu: bull200, vol_ratio, squeeze
- Entferne EINE Bestätigung
- Ändere Stop Loss: 3% → 4% → 5%
- Ändere Max Hold: 24 → 36 → 48 Bars
- KEIN OR! Nur AND

Antworte NUR mit JSON:
{{"name": "MUTATED_NAME", "entry_condition": "...", "exit_condition": "...", "exit_config": {{"stop_loss_pct": N, "max_hold_bars": N}}}}"""

    response = call_llm(prompt, temperature=0.5)
    if not response:
        return None

    parsed = parse_strategy(response)
    if parsed:
        parsed["arm"] = arm["name"]
    return parsed


# ============================================================================
# CROSSOVER
# ============================================================================

def crossover_strategies(parent1: dict, parent2: dict, arm: dict) -> dict | None:
    """Crossover two parent strategies via LLM."""
    prompt = f"""Kreuze zwei Funding-Strategien. Nimm den Entry von der besseren und den Exit von der anderen.
Oder kombiniere die besten Teile beider Entries.

Parent 1: {json.dumps(parent1, ensure_ascii=False)}
Parent 2: {json.dumps(parent2, ensure_ascii=False)}

{LESSONS_LEARNED_V10}

{INDICATOR_LIST_V10}

KREUZUNGS-REGELN:
- Entry MUSS funding_z oder fund_cross enthalten
- Nimm den restriktiveren Entry (mehr Filter = weniger Overfitting)
- Kombiniere Bestätigungen beider Eltern
- KEIN OR! Nur AND

Antworte NUR mit JSON:
{{"name": "CROSSOVER_NAME", "entry_condition": "...", "exit_condition": "...", "exit_config": {{"stop_loss_pct": N, "max_hold_bars": N}}}}"""

    response = call_llm(prompt, temperature=0.4)
    if not response:
        return None

    parsed = parse_strategy(response)
    if parsed:
        parsed["arm"] = arm["name"]
    return parsed


# ============================================================================
# MAIN EVOLUTION RUN
# ============================================================================

def run_evolution():
    print("=" * 70)
    print("FOUNDRY V10 — FUNDING-FIRST EVOLUTION")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Model: {MODEL}")
    print(f"Arms: {[a['name'] for a in ARMS]}")
    print(f"Max runs: {MAX_RUNS}")
    print("=" * 70)

    hof = load_hof()
    total_evaluated = 0
    total_wf_passed = 0
    run_number = len(hof)  # Approximate

    # PHASE 1: EXPLORATION
    print(f"\n{'='*70}")
    print("PHASE 1: EXPLORATION")
    print(f"{'='*70}")

    all_candidates = []
    for arm in ARMS:
        print(f"\n🦑 Arm: {arm['name']} (temp={arm['temperature']}, targets={arm['target_assets']})")
        candidates = explore_arm(arm)
        all_candidates.extend(candidates)
        print(f"  → {len(candidates)} candidates generated")

    print(f"\nTotal exploration candidates: {len(all_candidates)}")

    # PHASE 2: EVALUATION
    print(f"\n{'='*70}")
    print("PHASE 2: IS BACKTEST + WF GATE")
    print(f"{'='*70}")

    evaluated = []
    for i, cand in enumerate(all_candidates):
        arm_name = cand.get("arm", "")
        arm = next((a for a in ARMS if a["name"] == arm_name), ARMS[0])
        target = arm["target_assets"]

        print(f"\n[{i+1}/{len(all_candidates)}] {cand['name']}: {cand['entry_condition'][:60]}")
        result = evaluate_candidate(cand, arm["prompt_key"], target)
        total_evaluated += 1

        if result is None:
            print(f"  ✗ Failed IS/WF")
            continue

        status = "✅ WF-PASSED" if result["passed"] else "✗ WF-FAILED"
        rob = result["wf_result"].get("robustness", 0)
        oos = result["wf_result"].get("avg_oos_return", 0)
        print(f"  {status} | Robustness={rob:.1f} | OOS={oos:+.4f}% | Fitness={result["fitness_val"]:.2f}")

        evaluated.append(result)

        if result["passed"]:
            if add_to_hof(hof, result):
                total_wf_passed += 1
                print(f"  🏆 NEW CHAMPION: {result['name']}")

    # PHASE 3: MUTATION + CROSSOVER (if we have evaluated candidates)
    if evaluated:
        print(f"\n{'='*70}")
        print("PHASE 3: MUTATION + CROSSOVER")
        print(f"{'='*70}")

        # Sort by fitness
        evaluated.sort(key=lambda x: x.get("fitness_val", 0), reverse=True)
        top = evaluated[:5]

        # Mutate top-5
        for i, parent_result in enumerate(top):
            parent_cand = {
                "name": parent_result["name"],
                "entry_condition": parent_result["entry_condition"],
                "exit_condition": parent_result.get("exit_condition", ""),
                "exit_config": parent_result["exit_config"],
            }
            arm_name = parent_result.get("type", "")
            arm = next((a for a in ARMS if a["prompt_key"] == arm_name), ARMS[0])

            for j in range(N_MUTATIONS_PER_PARENT):
                print(f"\n  Mutating {parent_result['name']} #{j+1}...")
                mutant = mutate_strategy(parent_cand, arm)
                if mutant is None:
                    continue

                result = evaluate_candidate(mutant, arm["prompt_key"], arm["target_assets"])
                total_evaluated += 1

                if result and result["passed"]:
                    if add_to_hof(hof, result):
                        total_wf_passed += 1
                        print(f"  🏆 MUTATION CHAMPION: {result['name']}")

        # Crossover top pairs
        for i in range(min(N_CROSSOVERS, len(top) - 1)):
            p1, p2 = top[i], top[i + 1]
            p1_cand = {"name": p1["name"], "entry_condition": p1["entry_condition"],
                       "exit_condition": p1.get("exit_condition", ""), "exit_config": p1["exit_config"]}
            p2_cand = {"name": p2["name"], "entry_condition": p2["entry_condition"],
                       "exit_condition": p2.get("exit_condition", ""), "exit_config": p2["exit_config"]}

            arm_name = p1.get("type", "")
            arm = next((a for a in ARMS if a["prompt_key"] == arm_name), ARMS[0])

            print(f"\n  Crossing {p1['name']} × {p2['name']}...")
            child = crossover_strategies(p1_cand, p2_cand, arm)
            if child is None:
                continue

            result = evaluate_candidate(child, arm["prompt_key"], arm["target_assets"])
            total_evaluated += 1

            if result and result["passed"]:
                if add_to_hof(hof, result):
                    total_wf_passed += 1
                    print(f"  🏆 CROSSOVER CHAMPION: {result['name']}")

    # SAVE HOF
    save_hof(hof)

    # FINAL REPORT
    print(f"\n{'='*70}")
    print("RUN SUMMARY")
    print(f"{'='*70}")
    print(f"Evaluated: {total_evaluated}")
    print(f"WF-Passed: {total_wf_passed}")
    print(f"HOF Size: {len(hof)}")

    if hof:
        print(f"\n🏆 CHAMPIONS:")
        for h in sorted(hof, key=lambda x: x.get("wf_oos_return", 0), reverse=True):
            print(f"  {h['name']}: OOS={h.get('wf_oos_return', 0):+.4f}% | "
                  f"Rob={h.get('wf_robustness', 0):.1f} | "
                  f"Type={h['type']}")

    if total_wf_passed == 0:
        print(f"\n⚠️ 0 WF-passed. Kill criterion: if this persists across {MAX_RUNS} runs → fallback to manual signals.")
    else:
        print(f"\n✅ {total_wf_passed} champions found!")

    return hof


if __name__ == "__main__":
    run_evolution()