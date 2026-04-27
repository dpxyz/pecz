#!/usr/bin/env python3
"""
Foundry Evolution V8 — Multi-Strategy Space + Gradient IS-Score

Changes from V7:
- DSL parser extended: Stochastic, Williams %R, ATR, ROC, MACD, ADX, Volume
- IS-Score: Sortino-like gradient (negative scores for losing strategies)
- Prompts: Trend + Momentum + Mean Reversion (not just MR)
- Strategy types: MR, Trend, Momentum, Volume-Boosted, Regime-Filtered
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
from walk_forward_gate import build_strategy_func, run_wf_on_candidate

# ============================================================================
# CONFIG
# ============================================================================

N_EXPLORATION_PER_TYPE = 5  # candidates per strategy type (was 2, raised for more diversity)
N_MUTATIONS_PER_PARENT = 3
N_CROSSOVERS = 3
N_HARD_CHECK_TOP = 3

WF_WINDOWS_NORMAL = 10
WF_WINDOWS_HARD = 10
WF_PASS_ROBUSTNESS = 50.0
WF_PASS_PROFITABLE = 3

API_URL = os.environ.get("OLLAMA_API_URL", "http://172.17.0.1:32771/v1/chat/completions")
API_KEY = os.environ.get("OLLAMA_API_KEY", "ollama-cloud")
MODEL = os.environ.get("GENERATOR_MODEL", "gemma4:31b-cloud")

# Use same asset names as walk_forward_gate.py (without USDT suffix)
# wfg constructs symbol = f"{asset}USDT" internally
ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
DATA_PATH = RESEARCH_DIR / "data"
DATA_FILE_MAP = {a: f"{a}USDT_1h_full.parquet" for a in ASSETS}
PERIODS = {
    "2024": ("2024-01-01", "2024-12-31"),
    "2yr": ("2023-01-01", "2024-12-31"),
}

HOF_DIR = RESEARCH_DIR / "runs" / "evolution_v7"  # same dir for continuity
HOF_FILE = HOF_DIR / "evolution_v7_hof.json"
HOF_DIR.mkdir(parents=True, exist_ok=True)

# Strategy types for exploration
STRATEGY_TYPES = [
    {
        "name": "Mean Reversion",
        "prompt_key": "MR",
    },
    {
        "name": "Trend Following",
        "prompt_key": "TREND",
    },
    {
        "name": "Momentum",
        "prompt_key": "MOM",
    },
    {
        "name": "Volume-Boosted",
        "prompt_key": "VOL",
    },
    {
        "name": "Volatility/Regime",
        "prompt_key": "REGIME",
    },
    {
        "name": "4h Timeframe",
        "prompt_key": "4H",
    },
]

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


def aggregate_to_4h(df_1h: pl.DataFrame) -> pl.DataFrame:
    """Aggregate 1h candles to 4h candles for Arm 6 (4h timeframe)."""
    return df_1h.sort("timestamp").group_by_dynamic(
        "timestamp", every="4h", label="left"
    ).agg([
        pl.col("open").first(),
        pl.col("high").max(),
        pl.col("low").min(),
        pl.col("close").last(),
        pl.col("volume").sum(),
    ])

# ============================================================================
# LLM PROMPTS (V8 — Multi-Strategy)
# ============================================================================

PROMPTS = {
    "MR": """Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE Mean-Reversion-Strategie für Long-Entry.

Verfügbare Indikatoren (NUTZE DIESE EXAKTEN NAMEN):
- close, open, high, low, volume
- bb_lower_N, bb_upper_N, bb_width_N (Bollinger, N=10-30)
- rsi_N (RSI, N=5-21)
- zscore_N (Z-Score, N=10-30)
- stoch_k_N, stoch_d_N (Stochastic, N=5-21)
- williams_r_N (Williams %R, N=5-21)
- atr_N (ATR, N=10-20)
- ema_N, sma_N (Moving Average, N=10-200)
- volume_sma_N (Volume SMA, N=10-50)

Entry: Kombiniere 2-4 Indikatoren mit AND. Jeder Vergleich: indicator operator value.
Exit: trailing_stop_pct, stop_loss_pct, max_hold_bars.

WICHTIGE REGELN:
- Verwende NUR AND als logischen Operator. KEIN OR!
- Verwende NUR einfache Vergleiche (indicator > wert). KEINE Array-Vergleiche wie indicator[1]!

Beispiel: close < bb_lower_20 AND rsi_14 < 30 AND close > ema_100

Antworte NUR mit JSON:
{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}""",

    "TREND": """Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE Trend-Following-Strategie für Long-Entry.

KONTEXT: Auf 1h Crypto funktioniert Trend-following, WENN man im richtigen Regime tradet.
Nutze ADX als Trend-Filter und gleitende Durchschnitte für Richtung.

Verfügbare Indikatoren (NUTZE DIESE EXAKTEN NAMEN):
- close, open, high, low, volume
- ema_N, sma_N (Moving Average, N=10-200)
- adx_N (ADX Trend-Stärke, N=10-20)
- macd_12_26, macd_signal_12_26, macd_hist_12_26 (MACD)
- roc_N (Rate of Change %, N=5-21)
- atr_N (ATR, N=10-20)
- ema_slope_N (EMA Steigung, positiv = steigend)
- volume_sma_N (Volume SMA)

WICHTIGE REGELN:
- Verwende NUR AND als logischen Operator. KEIN OR!
- Verwende NUR einfache Vergleiche (indicator > wert). KEINE Array-Vergleiche wie indicator[1]!

Gute Ansätze:
- EMA-Crossover + ADX-Filter: close > ema_50 AND close > ema_200 AND adx_14 > 25
- MACD-Momentum: macd_hist_12_26 > 0 AND close > ema_100 AND adx_14 > 20
- ROC-Boost: roc_14 > 2 AND close > ema_50 AND volume > volume_sma_20

Exit: trailing_stop_pct 2.5-4.0% (Trend braucht Raum!), stop_loss_pct 3-5%, max_hold_bars 24-72.

Antworte NUR mit JSON:
{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}""",

    "MOM": """Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE Momentum-Strategie für Long-Entry.

Momentum auf 1h Crypto: Starke Moves (Breakouts, Momentum-Spikes) traden,
nicht warten auf Umkehr. Entry wenn Preis-Bewegung + Volumen bestätigen.

Verfügbare Indikatoren (NUTZE DIESE EXAKTEN NAMEN):
- close, open, high, low, volume
- roc_N (Rate of Change %, N=3-21)
- macd_hist_12_26 (MACD Histogram)
- volume_sma_N (Volume SMA)
- ema_N, sma_N (N=10-200)
- adx_N (ADX, N=10-20)
- atr_N (ATR, N=10-20)
- bb_width_N (Bollinger Band Breite)

WICHTIGE REGELN:
- Verwende NUR AND als logischen Operator. KEIN OR!
- Verwende NUR einfache Vergleiche (indicator > wert). KEINE Array-Vergleiche wie indicator[1]!
- KEINE _sma Endungen bei nicht-unterstützten Indikatoren (z.B. bb_width_20_sma ist ungültig)

Gute Ansätze:
- Breakout: close > bb_upper_20 AND roc_5 > 3 AND volume > volume_sma_20 * 1.5
- Momentum-Spike: roc_10 > 5 AND macd_hist_12_26 > 0 AND adx_14 > 30
- Vol-Explosion: bb_width_20 > 0.05 AND close > ema_50 AND volume > volume_sma_20 * 2

Exit: trailing_stop_pct 2.0-3.5%, stop_loss_pct 2.5-4.0%, max_hold_bars 12-48.

Antworte NUR mit JSON:
{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}""",

    "VOL": """Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE Volume-Boosted Strategie für Long-Entry.

KONTEXT: Volume ist der beste Konfirmator. Egal ob MR oder Trend —
Volumen-Spike + Preis-Signal = stärkster Entry.

Verfügbare Indikatoren (NUTZE DIESE EXAKTEN NAMEN):
- close, open, high, low, volume
- volume_sma_N (Volume SMA, N=10-50)
- bb_lower_N, bb_upper_N (Bollinger)
- rsi_N (RSI, N=5-21)
- ema_N, sma_N (N=10-200)
- stoch_k_N, stoch_d_N (Stochastic)
- zscore_N (Z-Score)

WICHTIGE REGELN:
- Verwende NUR AND als logischen Operator. KEIN OR!
- Verwende NUR einfache Vergleiche (indicator > wert). KEINE Array-Vergleiche wie indicator[1]!

Gute Ansätze:
- Vol-Confirm MR: close < bb_lower_20 AND volume > volume_sma_20 * 1.5 AND rsi_14 < 30
- Vol-Spike Reversal: volume > volume_sma_20 * 2 AND stoch_k_14 < 20 AND close > ema_100
- Climax-Volume: zscore_20 < -2 AND volume > volume_sma_20 * 2.5

Exit: trailing_stop_pct 1.5-3.0%, stop_loss_pct 2.5-4.0%, max_hold_bars 12-36.

Antworte NUR mit JSON:
{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}""",

    "REGIME": """Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE Regime-basierte Strategie für Long-Entry.

KONTEXT: Verschiedene Markt-Regimes erfordern verschiedene Strategien.
Nutze BB-Width, ADX, ATR um das Regime zu erkennen, dann den passenden Entry.

Verfügbare Indikatoren (NUTZE DIESE EXAKTEN NAMEN):
- close, open, high, low, volume
- bb_width_N (Bollinger Band Breite — niedrig = Squeeze, hoch = Expansion)
- adx_N (ADX — niedrig = Range, hoch = Trend)
- atr_N (ATR — niedrig = ruhig, hoch = volatil)
- ema_N, sma_N (N=10-200)
- rsi_N (RSI)
- volume_sma_N
- ema_slope_N (EMA Steigung)
- macd_hist_12_26

WICHTIGE REGELN:
- Verwende NUR AND als logischen Operator. KEIN OR!
- Verwende NUR einfache Vergleiche (indicator > wert). KEINE Array-Vergleiche wie indicator[1]!
- Verwende KEINE _sma Endungen bei ATR (atr_14_sma ist ungültig, nutze atr_N direkt).

Gute Ansätze:
- Squeeze-Breakout: bb_width_20 < 0.02 AND adx_14 > 25 AND close > ema_50
- Low-Vol MR: atr_14 < 1.5 AND rsi_14 < 30 AND close > ema_100
- Trend-Regime Entry: adx_14 > 25 AND ema_slope_50 > 0 AND close > ema_200

Exit: trailing_stop_pct 2.0-4.0%, stop_loss_pct 2.5-5.0%, max_hold_bars 18-72.

Antworte NUR mit JSON:
{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}""",

    "4H": """Du bist ein Quant-Stratege für 4h Crypto Perps.
Generiere EINE Strategie für Long-Entry auf 4-Stunden-Kerzen.

KONTEXT: 4h-Kerzen haben weniger Rauschen als 1h. Trendsignale sind verlässlicher,
aber es gibt weniger Trades. Passe die Parameter an:
- BB-Periode: 10-40 (statt 10-20 auf 1h)
- EMA-Periode: 20-200 (wie bei 1h, aber Trends halten länger)
- RSI-Periode: 10-21 (wie 1h)
- Max Hold: 6-24 bars (= 24h-96h, statt 12-48 auf 1h)

Verfugbare Indikatoren (NUTZE DIESE EXAKTEN NAMEN):
- close, open, high, low, volume
- bb_lower_N, bb_upper_N, bb_width_N (N=10-40)
- rsi_N (N=10-21)
- ema_N, sma_N (N=10-200)
- adx_N (N=10-21)
- macd_hist_12_26
- atr_N (N=10-20)
- volume_sma_N (N=10-50)

WICHTIGE REGELN:
- Verwende NUR AND als logischen Operator. KEIN OR!
- Verwende NUR einfache Vergleiche (indicator > wert). KEINE Array-Vergleiche wie indicator[1]!

Gute 4h-Ansätze:
- 4h Trend: close > ema_50 AND adx_14 > 20 AND macd_hist_12_26 > 0
- 4h MR: close < bb_lower_20 AND rsi_14 < 35 AND close > ema_100
- 4h Breakout: bb_width_20 < 0.03 AND close > ema_50 AND adx_14 > 25

Exit: trailing_stop_pct 2.0-4.0%, stop_loss_pct 3.0-5.0%, max_hold_bars 6-24.

Antworte NUR mit JSON:
{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}""",
}

MUTATION_PROMPT = """MUTIERE diese Strategie. Ändere 1-3 Parameter oder füge einen Filter hinzu.

ELTER: {parent_name}
Entry: {parent_entry}
Exit: {parent_exit}
WF Robustness: {parent_wf} | IS-Score: {parent_is}

Verfügbare Indikatoren: close, open, high, low, volume, bb_lower_N, bb_upper_N, bb_width_N,
rsi_N, zscore_N, stoch_k_N, stoch_d_N, williams_r_N, atr_N, roc_N, macd_12_26,
macd_signal_12_26, macd_hist_12_26, adx_N, ema_N, sma_N, volume_sma_N, ema_slope_N.

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {{"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}}}"""

CROSSOVER_PROMPT = """CROSSOVER zwei Strategien. Kombiniere den besten Entry mit dem besten Exit,
oder mische Indikatoren aus beiden.

ELTER A (WF={parent_a_wf}, IS={parent_a_is}):
Entry: {parent_a_entry}
Exit: {parent_a_exit}

ELTER B (WF={parent_b_wf}, IS={parent_b_is}):
Entry: {parent_b_entry}
Exit: {parent_b_exit}

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_config": {{"trailing_stop_pct": X, "stop_loss_pct": Y, "max_hold_bars": Z}}}}"""


# ============================================================================
# LLM CALLS
# ============================================================================

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
                entry = d["entry_condition"]
                # Reject OR in entry conditions (parser splits on AND only)
                if " OR " in entry.upper():
                    print(f"    ⚠️ Rejected OR in entry: {entry[:60]}")
                    return None
                # Reject unsupported array comparisons like indicator[1]
                if re.search(r'\w+\[', entry):
                    print(f"    ⚠️ Rejected array comparison in entry: {entry[:60]}")
                    return None
                return d
        except:
            pass
    return None

# ============================================================================
# EVALUATION
# ============================================================================

def run_is_backtest(entry_condition: str, exit_config: dict, strategy_type: str = "") -> dict | None:
    try:
        strategy_func, parseable = build_strategy_func(entry_condition)
        if not parseable or strategy_func is None:
            return None

        is_4h = strategy_type == "4H"
        engine = BacktestEngine(data_path=str(DATA_PATH))

        all_returns, all_dds, all_cls, all_trades = [], [], [], []
        profitable = 0
        exit_reasons = {}  # {reason: {count, total_pnl, wins}}
        per_asset_returns = {}  # {asset: {period_name: net_return}}

        for asset in ASSETS:
            for period_name, (start, end) in PERIODS.items():
                try:
                    df = load_df(asset, start, end)
                    if len(df) < 50:
                        continue
                    # Aggregate to 4h if this is a 4h strategy
                    if is_4h:
                        df = aggregate_to_4h(df)
                        if len(df) < 20:
                            continue
                    timeframe = "4h" if is_4h else "1h"
                    result = engine.run(strategy_name="eval", strategy_func=strategy_func, params={}, symbol=f"{asset}USDT", timeframe=timeframe, exit_config=exit_config, df=df)
                    if result.trade_count > 0:
                        all_returns.append(result.net_return)
                        all_dds.append(result.max_drawdown)
                        all_cls.append(result.max_consecutive_losses)
                        all_trades.append(result.trade_count)
                        if result.net_return > 0:
                            profitable += 1
                        # Collect exit reason stats
                        for t in result.trades:
                            r = t.exit_reason
                            if r not in exit_reasons:
                                exit_reasons[r] = {"count": 0, "total_pnl": 0.0, "wins": 0}
                            exit_reasons[r]["count"] += 1
                            exit_reasons[r]["total_pnl"] += t.pnl
                            if t.pnl > 0:
                                exit_reasons[r]["wins"] += 1
                        # Track per-asset returns
                        per_asset_returns.setdefault(asset, {})[period_name] = result.net_return
                except:
                    continue

        if not all_returns:
            return None

        n = len(all_returns)
        total_return = sum(all_returns) / n
        avg_dd = sum(all_dds) / n
        max_cl = max(all_cls)
        min_trades = min(all_trades)

        # V8 IS-Score: Sortino-like gradient (negative scores allowed)
        profitable_ratio = profitable / n
        trade_quality = min(1.0, min_trades / 5)

        # Floor profitable_ratio at 0.05 so terrible strategies (0/12) don't score IS=0
        # (same as "untested"). Without floor: -79% return * 0/12 * 0.1 = 0.00 — misleading.
        pr = max(profitable_ratio, 0.05)

        # 4H penalty: aggregating 1h→4h then testing on same data is in-sample.
        # Discount IS by 50% to reflect overfitting risk.
        is_4h = strategy_type == "4H"
        four_h_discount = 0.5 if is_4h else 1.0

        if total_return > 0 and avg_dd > 0:
            score = (total_return / avg_dd) * pr * trade_quality * four_h_discount
        elif total_return <= 0:
            score = total_return * pr * trade_quality * 0.1 * four_h_discount
        else:
            score = 0

        # Build exit_reasons summary
        exit_summary = {}
        for r, d in exit_reasons.items():
            avg_pnl = d["total_pnl"] / d["count"] if d["count"] > 0 else 0
            wr = d["wins"] / d["count"] if d["count"] > 0 else 0
            exit_summary[r] = {"count": d["count"], "avg_pnl": round(avg_pnl, 2), "win_rate": round(wr, 2)}

        return {"avg_return": round(total_return, 2), "avg_dd": round(avg_dd, 1), "max_cl": max_cl,
                "min_trades": min_trades, "profitable_assets": f"{profitable}/{n}", "is_score": round(score, 2),
                "exit_reasons": exit_summary, "per_asset_returns": per_asset_returns}
    except Exception as e:
        print(f"  ⚠️ IS error: {e}")
        return None


def run_wf(entry_condition: str, exit_config: dict, n_windows: int = WF_WINDOWS_NORMAL, strategy_type: str = "") -> dict | None:
    try:
        # Note: run_wf_on_candidate uses its own IS-backtest internally,
        # so 4h strategies need special handling there too.
        # For now, 4h IS-backtest is handled in run_is_backtest(),
        # and WF gate runs on 1h data (acceptable for initial screening).
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
    stype = candidate.get("strategy_type", classify_strategy_type(candidate.get("entry_condition", "")))
    print(f"\n  🧬 {name} [{stype}]")
    print(f"     Entry: {candidate['entry_condition']}")
    print(f"     Exit: {json.dumps(candidate['exit_config'])}")

    is_result = run_is_backtest(candidate["entry_condition"], candidate["exit_config"], strategy_type=stype)
    if is_result:
        candidate.update(is_result)
        print(f"     IS: {is_result['is_score']:.2f} | R={is_result['avg_return']:+.2f}% | DD={is_result['avg_dd']:.1f}% | {is_result['profitable_assets']}")
    else:
        candidate.update({"avg_return": 0, "avg_dd": 0, "max_cl": 0, "min_trades": 0, "profitable_assets": "0/12", "is_score": -10})
        print(f"     IS: FAILED (parse error)")

    wf_result = run_wf(candidate["entry_condition"], candidate["exit_config"], strategy_type=stype)
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
            hof = json.loads(HOF_FILE.read_text()).get("hof", [])
            # Backfill IS scores for entries missing them
            needs_save = False
            for entry in hof:
                if entry.get("wf_passed") and entry.get("is_score", 0) == 0 and entry.get("avg_return", 0) == 0:
                    is_result = run_is_backtest(entry["entry_condition"], entry.get("exit_config", {}))
                    if is_result:
                        entry.update(is_result)
                        needs_save = True
                        print(f"  🔄 Backfilled IS for {entry.get('name', '?')}: IS={is_result['is_score']:.2f}")
            if needs_save:
                save_hof(hof)
            return hof
        except:
            pass
    return []


def save_hof(hof: list[dict]):
    # Sort: WF-passed first (by robustness), then by IS-score
    hof.sort(key=lambda x: (1 if x.get("wf_passed") else 0, x.get("wf_robustness", 0), x.get("is_score", 0)), reverse=True)
    champion = hof[0] if hof else None
    HOF_FILE.write_text(json.dumps({"updated": datetime.now().isoformat(), "champion": champion, "hof": hof[:50]}, indent=2))

# ============================================================================
# DIVERSITY TRACKING
# ============================================================================

def entry_pattern(entry: str) -> str:
    """Extract indicator pattern for diversity tracking."""
    indicators = sorted(set(re.findall(
        r'(bb_lower|bb_upper|bb_width|rsi|ema|sma|macd|adx|zscore|atr|volume|stoch|williams|roc)',
        entry.lower())))
    return '+'.join(indicators) if indicators else 'unknown'


def classify_strategy_type(entry: str) -> str:
    """Classify strategy type from entry condition.
    Primary type = dominant signal (bb_lower+rsi = MR, roc/macd = MOM, etc.)
    Overlay indicators (adx, volume) don't change the primary type.
    """
    e = entry.lower()
    # Primary type detection (order matters: most specific first)
    # MR: bb_lower/zscore = oversold signal
    if 'bb_lower' in e or 'zscore' in e:
        if 'volume' in e:
            return 'VOL'
        return 'MR'
    # rsi < threshold (oversold) is MR signal
    if 'rsi' in e and '<' in e:
        if 'volume' in e:
            return 'VOL'
        return 'MR'
    # Regime: bb_width or standalone ATR
    if 'bb_width' in e:
        return 'REGIME'
    if 'atr_' in e and 'bb' not in e and 'rsi' not in e:
        return 'REGIME'
    # TREND: ema crossover + adx/macd
    if 'adx' in e or 'ema_slope' in e:
        return 'TREND'
    if 'close > ema_' in e and 'close > ema_200' in e:
        return 'TREND'
    # MOM: roc, macd, bb_upper breakout
    if 'roc_' in e or 'macd_hist' in e or ('bb_upper' in e and 'close >' in e):
        return 'MOM'
    # Stochastic / Williams
    if 'stoch' in e or 'williams' in e:
        return 'MR'
    # Fallback
    return 'MR'

# ============================================================================
# MAIN — Multi-Strategy Evolutionary Search
# ============================================================================

def main():
    hof = load_hof()
    hof_passed = [s for s in hof if s.get("wf_passed")]
    hof_10w_passed = [s for s in hof if s.get("wf_passed_10w")]

    # Count strategy types in HOF
    hof_types = {}
    for s in hof_passed:
        t = classify_strategy_type(s.get("entry_condition", ""))
        hof_types[t] = hof_types.get(t, 0) + 1

    # Load arm performance history for budget steering
    arm_perf_file = HOF_DIR / 'arm_performance.json'
    if arm_perf_file.exists():
        try:
            arm_performance = json.load(open(arm_perf_file))
        except:
            arm_performance = {}
    else:
        arm_performance = {}

    print("=" * 70)
    print("FOUNDRY V8 — Oktopus Evolutionary Search")
    print(f"Arms: {', '.join(t['name'] for t in STRATEGY_TYPES)}")
    print(f"IS-Score: Gradient (negative = losing but comparable)")
    print(f"DSL: Extended (Stochastic, Williams, ATR, ROC, MACD, ADX, Volume)")
    print(f"WF windows: {WF_WINDOWS_NORMAL} | HOF: {len(hof)} ({len(hof_passed)} passed)")
    print(f"Budget steering: {'active' if arm_performance else 'default'}")
    print("=" * 70)

    if hof_types:
        print(f"  HOF types: {hof_types}")
    for s in hof[:5]:
        wf = "✅" if s.get("wf_passed") else "❌"
        stype = s.get("strategy_type", classify_strategy_type(s.get("entry_condition", "")))
        print(f"  {s.get('name','?'):40s} WF={s.get('wf_robustness',0):5.1f} {wf} IS={s.get('is_score',0):6.2f} [{stype}]")

    seen_patterns = set(entry_pattern(s.get("entry_condition", "")) for s in hof)
    seen_exact_entries = set(s.get("entry_condition", "").strip().lower() for s in hof)
    print(f"  Known patterns: {len(seen_patterns)}, exact entries: {len(seen_exact_entries)}")

    all_candidates = []
    all_results_for_save = []

    # =========================================================================
    # PHASE 1: EXPLORATION — One LLM call per strategy type
    # =========================================================================
    print(f"\n{'='*70}")
    print("PHASE 1: EXPLORATION")
    print("=" * 70)

    phase1_evaluated = []
    phase1_passed = []

    for stype in STRATEGY_TYPES:
        prompt = PROMPTS[stype["prompt_key"]]
        n_cands = N_EXPLORATION_PER_TYPE

        # If this type is underrepresented in HOF, generate more
        hof_count = hof_types.get(stype["prompt_key"], 0)
        if hof_count < 1:
            n_cands = max(n_cands, 3)
            print(f"\n  📝 {stype['name']} ({n_cands} candidates, UNDERREPRESENTED in HOF)")
        else:
            print(f"\n  📝 {stype['name']} ({n_cands} candidates)")

        # Budget steering: adapt based on arm performance
        arm_key = stype["prompt_key"]
        arm_perf = arm_performance.get(arm_key, {})
        arm_trend = arm_perf.get("trend", "new")
        if arm_trend == "dead":
            n_cands = 1  # Probe mode only
            print(f"     💀 DEAD arm — probe mode ({n_cands} candidate)")
        elif arm_trend == "producing":
            n_cands = max(n_cands, 3)  # More tentacles
            print(f"     🌟 PRODUCING arm — extra budget ({n_cands} candidates)")
        elif arm_trend == "promising":
            n_cands = max(n_cands, 3)
            print(f"     📈 PROMISING arm — extra budget ({n_cands} candidates)")

        for i in range(n_cands):
            temp = 0.3 if i == 0 else 0.6
            response = call_llm(prompt, temperature=temp)
            parsed = parse_strategy(response)
            if parsed:
                parsed["strategy_type"] = stype["prompt_key"]
                pat = entry_pattern(parsed["entry_condition"])
                parsed["entry_pattern"] = pat
                is_new = pat not in seen_patterns
                parsed["is_new_pattern"] = is_new
                if is_new:
                    seen_patterns.add(pat)
                # Deduplicate exact entry conditions (LLM often generates same entry with different names)
                exact_entry = parsed["entry_condition"].strip().lower()
                if exact_entry in seen_exact_entries:
                    print(f"  ⏭️ Duplicate entry (skip): {parsed.get('name', '?')}")
                    continue
                seen_exact_entries.add(exact_entry)
                diversity_tag = " 🌱 NEW PATTERN" if is_new else ""
                print(f"  ✅ Parsed: {parsed.get('name', '?')} [{pat}]{diversity_tag}")
                all_candidates.append(parsed)
            else:
                print(f"  ⚠️ Parse error on {stype['name']} #{i+1}")

    # Evaluate Phase 1
    print(f"\n📊 Evaluating {len(all_candidates)} Phase 1 candidates...")
    for c in all_candidates:
        result = evaluate(c)
        phase1_evaluated.append(result)
        if result.get("wf_passed") and result.get("wf_robustness", 0) > 0:
            hof.append(result)
            phase1_passed.append(result)

    save_hof(hof)
    all_results_for_save.extend(phase1_evaluated)

    print(f"\n📊 Phase 1 Results: {len(phase1_passed)}/{len(phase1_evaluated)} WF-passed")
    new_patterns_found = sum(1 for c in phase1_evaluated if c.get("is_new_pattern"))
    print(f"   New entry patterns: {new_patterns_found}")
    print(f"   Total known patterns: {len(seen_patterns)}")

    # =========================================================================
    # PHASE 2: EVOLUTION — Mutate + Crossover from HOF
    # =========================================================================
    print(f"\n{'='*70}")
    print("PHASE 2: EVOLUTION")
    print("=" * 70)

    phase2_evaluated = []
    phase2_passed = []

    # Build mutation pool: HOF-passed + best Phase 1 PER ARM TYPE + autopsie feed
    mutation_pool = list(hof_passed) if hof_passed else []
    
    # Add top Phase 1 candidates PER ARM TYPE (ensures diversity, not just MR)
    phase1_sorted = sorted(phase1_evaluated, key=lambda x: x.get('is_score', -10), reverse=True)
    seen_entries = {s.get('entry_condition', '') for s in mutation_pool}
    type_added = {}  # track how many per type
    for cand in phase1_sorted:
        entry = cand.get('entry_condition', '')
        stype = cand.get('strategy_type', classify_strategy_type(entry))
        if entry not in seen_entries and type_added.get(stype, 0) < 2:
            mutation_pool.append(cand)
            seen_entries.add(entry)
            type_added[stype] = type_added.get(stype, 0) + 1
    
    # Add autopsie mutation feed if exists
    autopsie_feed_file = HOF_DIR / 'mutation_feed.json'
    if autopsie_feed_file.exists():
        try:
            feed_entries = json.loads(autopsie_feed_file.read_text())
            for feed_entry in feed_entries[:5]:
                if isinstance(feed_entry, dict):
                    # Extract mutated entries from autopsie mutations
                    for m in feed_entry.get('mutations', []):
                        modified_entry = m.get('entry_modifier')
                        if modified_entry and modified_entry not in seen_entries:
                            # Merge exit_modifier with defaults (partial dicts are ok)
                            exit_mod = m.get('exit_modifier')
                            base_exit = {'trailing_stop_pct': 2.0, 'stop_loss_pct': 3.0, 'max_hold_bars': 24}
                            if exit_mod and isinstance(exit_mod, dict):
                                exit_config = {**base_exit, **exit_mod}
                            else:
                                exit_config = base_exit.copy()
                            mutation_pool.append({
                                'name': f"Autopsie_{feed_entry.get('candidate_name', '?')}_{m['type']}",
                                'entry_condition': modified_entry,
                                'exit_config': exit_config,
                                'strategy_type': classify_strategy_type(modified_entry),
                                'is_score': 0,
                                'wf_robustness': 0,
                            })
                            seen_entries.add(modified_entry)
                    # Also check for direct entry_condition (legacy format)
                    ec = feed_entry.get('entry_condition')
                    if ec and ec not in seen_entries:
                        mutation_pool.append(feed_entry)
                        seen_entries.add(ec)
        except:
            pass
    
    print(f"  Mutation pool: {len(mutation_pool)} candidates ({len(hof_passed)} HOF + {len(mutation_pool)-len(hof_passed)} other)")
    
    # Mutate entries from the pool
    if mutation_pool:
        # Pick top entries by different criteria for diversity
        top_n = min(3, len(mutation_pool))
        parents = sorted(mutation_pool, key=lambda x: x.get("wf_robustness", x.get("is_score", -10)), reverse=True)[:top_n]
        
        for parent in parents:
            for i in range(N_MUTATIONS_PER_PARENT):
                prompt = MUTATION_PROMPT.format(
                    parent_name=parent.get("name", "?"),
                    parent_entry=parent.get("entry_condition", ""),
                    parent_exit=json.dumps(parent.get("exit_config", {})),
                    parent_wf=parent.get("wf_robustness", 0),
                    parent_is=parent.get("is_score", 0),
                )
                response = call_llm(prompt, temperature=0.4)
                parsed = parse_strategy(response)
                if parsed:
                    parsed["strategy_type"] = classify_strategy_type(parsed.get("entry_condition", ""))
                    parsed["parent"] = parent.get("name", "?")
                    parsed["phase"] = "mutation"
                    print(f"  🔀 Mutation of {parent.get('name','?')}: {parsed.get('name','?')}")
                    evaluate(parsed)
                    phase2_evaluated.append(parsed)
                    if parsed.get("wf_passed"):
                        hof.append(parsed)
                        phase2_passed.append(parsed)

        # Crossover: mix entries from different strategy types
        if len(mutation_pool) >= 2:
            # Group by type for diverse crossover
            type_groups = {}
            for m in mutation_pool:
                t = m.get('strategy_type', classify_strategy_type(m.get('entry_condition', '')))
                type_groups.setdefault(t, []).append(m)
            
            for i in range(N_CROSSOVERS):
                # Prefer cross-type crossover for diversity
                types = list(type_groups.keys())
                if len(types) >= 2:
                    t1, t2 = random.sample(types, 2)
                    a = random.choice(type_groups[t1])
                    b = random.choice(type_groups[t2])
                else:
                    a, b = random.sample(mutation_pool[:5], 2)
                prompt = CROSSOVER_PROMPT.format(
                    parent_a_wf=a.get("wf_robustness", 0),
                    parent_a_is=a.get("is_score", 0),
                    parent_a_entry=a.get("entry_condition", ""),
                    parent_a_exit=json.dumps(a.get("exit_config", {})),
                    parent_b_wf=b.get("wf_robustness", 0),
                    parent_b_is=b.get("is_score", 0),
                    parent_b_entry=b.get("entry_condition", ""),
                    parent_b_exit=json.dumps(b.get("exit_config", {})),
                )
                response = call_llm(prompt, temperature=0.4)
                parsed = parse_strategy(response)
                if parsed:
                    parsed["strategy_type"] = classify_strategy_type(parsed.get("entry_condition", ""))
                    parsed["phase"] = "crossover"
                    print(f"  🔀 Crossover: {parsed.get('name','?')}")
                    evaluate(parsed)
                    phase2_evaluated.append(parsed)
                    if parsed.get("wf_passed"):
                        hof.append(parsed)
                        phase2_passed.append(parsed)

    save_hof(hof)
    all_results_for_save.extend(phase2_evaluated)

    print(f"\n📊 Phase 2 Results: {len(phase2_passed)}/{len(phase2_evaluated)} WF-passed")

    # =========================================================================
    # PHASE 2.5: SWEEP — Parameter optimization on HOF entries
    # =========================================================================
    print(f"\n{'='*70}")
    print("PHASE 2.5: PARAMETER SWEEP (Grid + Regime Overlay)")
    print("=" * 70)

    from parameter_sweep import sweep_candidate

    phase25_results = []
    sweep_wf_candidates = []

    # Sweep top HOF entry PER ARM TYPE (not just top-3 overall which are all MR)
    sweepable = sorted(hof, key=lambda x: (1 if x.get('wf_passed') else 0, x.get('wf_robustness', 0), x.get('is_score', 0)), reverse=True)
    # Pick top-1 per strategy type for diversity
    seen_types = set()
    top_sweep = []
    for s in sweepable:
        stype = s.get('strategy_type', classify_strategy_type(s.get('entry_condition', '')))
        if stype not in seen_types:
            top_sweep.append(s)
            seen_types.add(stype)
        if len(top_sweep) >= 3:  # max 3 sweep targets per run
            break

    if top_sweep:
        for candidate in top_sweep:
            try:
                sweep_result = sweep_candidate(
                    candidate,
                    max_combinations=200,
                    quick_wf_top_n=2,
                )
                phase25_results.append(sweep_result)

                # Add sweep WF candidates to HOF
                for wc in sweep_result.get('wf_candidates', []):
                    sweep_entry = wc.get('entry', '')
                    sweep_exit = wc.get('exit_config', {})
                    sweep_name = f"Sweep_{candidate.get('name', '?')}_{wc.get('regime', 'none')}"

                    # Full WF on sweep candidates
                    sweep_stype = candidate.get('strategy_type', classify_strategy_type(sweep_entry))
                    wf_result = run_wf(sweep_entry, sweep_exit, strategy_type=sweep_stype)
                    if wf_result:
                        hof_entry = {
                            'name': sweep_name,
                            'entry_condition': sweep_entry,
                            'exit_config': sweep_exit,
                            'is_score': wc.get('is_score', 0),
                            'avg_return': wc.get('avg_return', 0),
                            'avg_dd': wc.get('avg_dd', 0),
                            'strategy_type': classify_strategy_type(sweep_entry),
                            'phase': 'sweep',
                            'parent': candidate.get('name', '?'),
                            'regime': wc.get('regime', 'none'),
                            **wf_result,
                        }
                        hof.append(hof_entry)
                        sweep_wf_candidates.append(hof_entry)
                        status = '✅ PASS' if wf_result.get('wf_passed') else '❌ FAIL'
                        print(f"     {status} {sweep_name}: IS={wc.get('is_score', 0):.2f} WF={wf_result.get('wf_robustness', 0):.1f} regime={wc.get('regime', 'none')}")
            except Exception as e:
                print(f"  ⚠️ Sweep error on {candidate.get('name', '?')}: {e}")

        save_hof(hof)
    else:
        print("  ⚠️ No HOF entries to sweep")

    print(f"\n📊 Phase 2.5 Results: {len(sweep_wf_candidates)} WF-candidates from sweep")

    # =========================================================================
    # PHASE 3: HARD CHECK — 10-window WF on top candidates
    # =========================================================================
    print(f"\n{'='*70}")
    print("PHASE 3: HARD CHECK (10-window WF)")
    print("=" * 70)

    # Find new WF-passed candidates that haven't been 10w-checked
    newly_passed = [s for s in hof if s.get("wf_passed") and not s.get("wf_passed_10w") and "wf_robustness_10w" not in s]
    top_for_hard = sorted(newly_passed, key=lambda x: x.get("wf_robustness", 0), reverse=True)[:N_HARD_CHECK_TOP]

    if top_for_hard:
        for candidate in top_for_hard:
            print(f"\n  🔍 Hard-checking: {candidate.get('name', '?')} (WF={candidate.get('wf_robustness', 0):.1f})")
            cand_type = candidate.get('strategy_type', classify_strategy_type(candidate.get("entry_condition", "")))
            wf_10w = run_wf(candidate["entry_condition"], candidate.get("exit_config", {}), n_windows=WF_WINDOWS_HARD, strategy_type=cand_type)
            if wf_10w:
                candidate["wf_robustness_10w"] = wf_10w.get("wf_robustness", 0)
                candidate["wf_passed_10w"] = wf_10w.get("wf_passed", False)
                candidate["wf_profitable_10w"] = wf_10w.get("wf_profitable_assets", "0/6")
                status = "✅ 10w PASS" if wf_10w.get("wf_passed") else "❌ 10w FAIL"
                print(f"     {status} | R10w={wf_10w.get('wf_robustness', 0):.1f} | {wf_10w.get('wf_profitable_assets', '0/6')}")
        save_hof(hof)
    else:
        print("  ⚠️ No new WF-passed candidates for hard check")

    # =========================================================================
    # PHASE 3.5: AUTOPSIE — Learn from failures
    # =========================================================================
    print(f"\n{'='*70}")
    print("PHASE 3.5: AUTOPSIE (Learn from WF failures)")
    print("=" * 70)

    from autopsy import autopsie as run_autopsie

    # Autopsie on all evaluated candidates that failed WF
    all_evaluated = phase1_evaluated + phase2_evaluated
    wf_failed = [c for c in all_evaluated if not c.get('wf_passed') and c.get('wf_robustness', 0) > 0]

    # Also include sweep candidates that didn't pass
    for sr in phase25_results:
        for wc in sr.get('grid_results', []):
            if not wc.get('quick_wf_passed'):
                wf_failed.append({
                    'name': f"Sweep_{wc.get('regime', 'none')}",
                    'entry_condition': wc.get('entry', ''),
                    'exit_config': wc.get('exit_config', {}),
                    'wf_passed': False,
                    'wf_robustness': wc.get('quick_wf_robustness', 0),
                })

    autopsy_results = []
    mutation_feed = []  # For next run's discovery

    for candidate in wf_failed[:10]:  # Top 10 most promising failures
        try:
            # Re-run WF to get detailed results for autopsie
            wf_detail = run_wf_on_candidate(
                name=candidate.get('name', '?'),
                entry=candidate.get('entry_condition', candidate.get('entry', '')),
                exit_config=candidate.get('exit_config', {}),
                strategy_type=candidate.get('strategy_type', classify_strategy_type(candidate.get('entry_condition', ''))),
            )
            result = run_autopsie(candidate, wf_detail)
            autopsy_results.append(result)

            # Collect high-priority mutations for next run
            if result.get('priority') in ('high', 'medium') and result.get('mutations'):
                mutation_feed.append(result)
                exit_info = result.get('exit_reasons_summary', '')
                print(f"  🔬 {candidate.get('name', '?')}: {result['priority']} priority")
                if exit_info:
                    print(f"     Exit: {exit_info}")
                for l in result.get('learnings', []):
                    print(f"     📝 {l}")
                for m in result.get('mutations', []):
                    print(f"     🔀 {m['type']}: {m['msg']}")
            else:
                print(f"  🔬 {candidate.get('name', '?')}: {result['priority']} priority (skip)")
        except Exception as e:
            print(f"  ⚠️ Autopsie error on {candidate.get('name', '?')}: {e}")

    # Save mutation feed for next run
    if mutation_feed:
        feed_file = HOF_DIR / 'mutation_feed.json'
        with open(feed_file, 'w') as f:
            json.dump(mutation_feed, f, indent=2, default=str)
        print(f"\n  💾 Mutation feed saved ({len(mutation_feed)} entries)")

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    print(f"\n{'='*70}")
    print("FINAL SUMMARY")
    print("=" * 70)

    total_evaluated = len(phase1_evaluated) + len(phase2_evaluated)
    total_passed = len(phase1_passed) + len(phase2_passed)
    print(f"Phase 1:   {len(phase1_evaluated)} evaluated, {len(phase1_passed)} WF-passed")
    print(f"Phase 2:   {len(phase2_evaluated)} evaluated, {len(phase2_passed)} WF-passed")
    print(f"Phase 2.5: {len(sweep_wf_candidates)} sweep candidates")
    print(f"Phase 3.5: {len(mutation_feed)} high-priority autopsie learnings")
    print(f"Total:     {total_evaluated} evaluated, {total_passed} WF-passed")

    # Strategy type breakdown
    type_stats = {}
    for c in phase1_evaluated + phase2_evaluated:
        t = c.get("strategy_type", classify_strategy_type(c.get("entry_condition", "")))
        if t not in type_stats:
            type_stats[t] = {"evaluated": 0, "wf_passed": 0, "parse_fail": 0}
        type_stats[t]["evaluated"] += 1
        if c.get("wf_passed"):
            type_stats[t]["wf_passed"] += 1
        if c.get("is_score", 0) == -10:  # parse failure marker
            type_stats[t]["parse_fail"] += 1

    print(f"\n  Strategy type breakdown:")
    for t, stats in sorted(type_stats.items()):
        print(f"    {t:8s}: {stats['evaluated']} eval, {stats['wf_passed']} WF-passed, {stats['parse_fail']} parse-fail")

    print(f"\n  Entry patterns explored: {len(seen_patterns)}")
    print(f"  HOF total: {len(hof)} | WF-passed: {len([s for s in hof if s.get('wf_passed')])} | 10w-champions: {len([s for s in hof if s.get('wf_passed_10w')])}")

    # Top 10 HOF
    print(f"\n🏆 HALL OF FAME (top 10 by WF Robustness):")
    sorted_hof = sorted(hof, key=lambda x: (x.get("wf_robustness", 0), x.get("is_score", 0)), reverse=True)
    for i, s in enumerate(sorted_hof[:10]):
        wf = "✅" if s.get("wf_passed") else "❌"
        hc = f" 10w={'✅' if s.get('wf_passed_10w') else '❌'}" if "wf_robustness_10w" in s else ""
        stype = s.get("strategy_type", classify_strategy_type(s.get("entry_condition", "")))
        pat = entry_pattern(s.get("entry_condition", ""))
        print(f"  {i+1}. {s.get('name', '?'):40s} WF={s.get('wf_robustness', 0):5.1f} {wf}{hc} | IS={s.get('is_score', 0):6.2f} [{stype}] {pat}")

    hof_10w = [s for s in hof if s.get("wf_passed_10w")]
    if hof_10w:
        champ = hof_10w[0]
        print(f"\n🎉 TRUE CHAMPION (10w-passed):")
        print(f"   {champ.get('name','?')} | WF10w={champ.get('wf_robustness_10w','?')} | IS={champ.get('is_score','?')} | OOS={champ.get('avg_oos_return','?')}%")
    else:
        print(f"\n⚠️  {len([s for s in hof if s.get('wf_passed')])} candidates passed WF but NOT 10w — no true champion")

    # Next run hint
    if total_passed == 0:
        print(f"\n💡 NEXT RUN: No new WF-passed — increase exploration budget or try new timeframe")
    elif total_passed > 2:
        print(f"\n💡 NEXT RUN: Good diversity — shift budget to evolution (mutation/crossover)")

    # =========================================================================
    # ARM PERFORMANCE UPDATE — Budget Steering
    # =========================================================================
    all_arm_results = phase1_evaluated + phase2_evaluated + sweep_wf_candidates
    for arm_key in ["MR", "TREND", "MOM", "VOL", "REGIME", "4H"]:
        arm_cands = [c for c in all_arm_results if c.get("strategy_type", classify_strategy_type(c.get("entry_condition", c.get("entry", "")))) == arm_key]
        if arm_key not in arm_performance:
            arm_performance[arm_key] = {"candidates_total": 0, "wf_passed": 0, "avg_is": 0, "trend": "new", "history": []}
        perf = arm_performance[arm_key]
        perf["candidates_total"] = perf.get("candidates_total", 0) + len(arm_cands)
        new_passed = sum(1 for c in arm_cands if c.get("wf_passed"))
        perf["wf_passed"] = perf.get("wf_passed", 0) + new_passed
        avg_is = sum(c.get("is_score", 0) for c in arm_cands) / max(len(arm_cands), 1)
        perf["avg_is"] = round(avg_is, 3)
        # Update trend
        history = perf.get("history", [])
        history.append({"date": datetime.now().strftime("%Y-%m-%d"), "candidates": len(arm_cands), "wf_passed": new_passed, "avg_is": round(avg_is, 3)})
        perf["history"] = history[-10:]  # Keep last 10 entries
        recent_is = [h["avg_is"] for h in perf["history"][-5:]]
        if any(is_val > 0 for is_val in recent_is):
            perf["trend"] = "producing"
        elif len(recent_is) >= 3 and recent_is[-1] > recent_is[0]:
            perf["trend"] = "promising"
        elif all(is_val < -0.3 for is_val in recent_is):
            perf["trend"] = "dead"
        elif len(recent_is) >= 2 and recent_is[-1] < recent_is[0]:
            perf["trend"] = "declining"
        else:
            perf["trend"] = "stable"
    # Save arm performance
    with open(arm_perf_file, 'w') as f:
        json.dump(arm_performance, f, indent=2)
    print(f"\n📊 Arm Performance Update:")
    for arm_key, perf in arm_performance.items():
        print(f"  {arm_key:8s}: {perf.get('trend', '?'):10s} | IS_avg={perf.get('avg_is', 0):+.3f} | WF_passed={perf.get('wf_passed', 0)} | candidates={perf.get('candidates_total', 0)}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = HOF_DIR / f"evolution_v7_results_{timestamp}.json"
    report = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "version": "V8_multi_strategy",
        "phase1_evaluated": len(phase1_evaluated),
        "phase1_passed": len(phase1_passed),
        "phase2_evaluated": len(phase2_evaluated),
        "phase2_passed": len(phase2_passed),
        "hof_size": len(hof),
        "champion": hof_10w[0] if hof_10w else None,
        "type_stats": type_stats,
        "hof_top5": [
            {"name": s.get("name", "?"), "wf_robustness": s.get("wf_robustness", 0),
             "wf_passed": s.get("wf_passed", False), "is_score": s.get("is_score", 0),
             "strategy_type": classify_strategy_type(s.get("entry_condition", "")),
             "wf_robustness_10w": s.get("wf_robustness_10w", 0)}
            for s in sorted_hof[:5]
        ],
        "phase1_results": phase1_evaluated,
        "phase2_results": phase2_evaluated,
    }
    with open(results_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n💾 Results saved to {results_file}")

    # Save daily report
    report_file = HOF_DIR / f"daily_{datetime.now().strftime('%Y-%m-%d')}_report.json"
    with open(report_file, 'w') as f:
        json.dump({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "version": "V8_multi_strategy",
            "phase1_evaluated": len(phase1_evaluated),
            "phase1_passed": len(phase1_passed),
            "phase2_evaluated": len(phase2_evaluated),
            "phase2_passed": len(phase2_passed),
            "hof_size": len(hof),
            "champion": hof_10w[0] if hof_10w else None,
            "type_stats": type_stats,
            "hof_top5": report["hof_top5"],
        }, f, indent=2, default=str)

    print(f"Report saved to {report_file}")
    print(f"\nDaily run complete. Exit code: 0")


if __name__ == "__main__":
    main()