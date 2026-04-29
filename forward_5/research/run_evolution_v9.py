#!/usr/bin/env python3
"""
Foundry Evolution V9 — Oktopus Evolution: Asset-Specific Arms + Signal-Exit

Changes from V8:
- 6 redesigned arms: MR-ALT, MR-RELAXED, TREND-REGIME, SIGNAL-EXIT, VOL-BOOSTED, CROSS-ASSET
- MR arms target DOGE/ADA/AVAX only (lessons learned: MR never works on BTC/ETH)
- Signal-reversal exits replace trailing stops (trail never fires on 1h)
- Entry+Exit paired generation (Arm 4: SIGNAL-EXIT)
- Mutation guards: only HOF members, entry-only mutations, min trades threshold
- IS pre-filter: skip WF if <3 trades/asset/window average
- Per-asset OOS breakdown in HOF
- Target-asset grouping in WF gate
- V9 fitness weights: OOS 30%, Target-Asset Profitable 25%, Trade Quality 20%, WF Robustness 15%, Drawdown 10%
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
WF_PASS_PROFITABLE = 3

# IS pre-filter: minimum trades per asset per window before sending to WF
IS_MIN_TRADES_THRESHOLD = 3

API_URL = os.environ.get("OLLAMA_API_URL", "http://172.17.0.1:32771/v1/chat/completions")
API_KEY = os.environ.get("OLLAMA_API_KEY", "ollama-cloud")
MODEL = os.environ.get("GENERATOR_MODEL", "deepseek-v4-pro:cloud")

ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
MR_TARGET_ASSETS = ["DOGE", "ADA", "AVAX"]  # MR only works on volatile alts
NON_MR_TARGET_ASSETS = ASSETS  # All 6 for non-MR arms
DATA_PATH = RESEARCH_DIR / "data"
DATA_FILE_MAP = {a: f"{a}USDT_1h_full.parquet" for a in ASSETS}
PERIODS = {
    "2024": ("2024-01-01", "2024-12-31"),
    "2yr": ("2023-01-01", "2024-12-31"),
}

HOF_DIR = RESEARCH_DIR / "runs" / "evolution_v9"
HOF_FILE = HOF_DIR / "evolution_v9_hof.json"
HOF_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# ARM DEFINITIONS (V9 — Asset-Specific)
# ============================================================================

ARMS = [
    {
        "name": "MR-ALT",
        "prompt_key": "MR_ALT",
        "target_assets": MR_TARGET_ASSETS,
        "temperature": 0.3,
        "is_mr": True,
        "exit_style": "signal_reversal",
        "default_exit_condition": "rsi_14 > 50",
    },
    {
        "name": "MR-RELAXED",
        "prompt_key": "MR_RELAXED",
        "target_assets": MR_TARGET_ASSETS,
        "temperature": 0.4,
        "is_mr": True,
        "exit_style": "signal_reversal",
        "default_exit_condition": "close > bb_mid_20",
    },
    {
        "name": "TREND-REGIME",
        "prompt_key": "TREND_REGIME",
        "target_assets": NON_MR_TARGET_ASSETS,
        "temperature": 0.5,
        "is_mr": False,
        "exit_style": "signal_reversal",
        "default_exit_condition": "close < ema_20",
    },
    {
        "name": "SIGNAL-EXIT",
        "prompt_key": "SIGNAL_EXIT",
        "target_assets": NON_MR_TARGET_ASSETS,
        "temperature": 0.4,
        "is_mr": False,
        "exit_style": "paired",
        # LLM generates both entry AND exit
    },
    {
        "name": "VOL-BOOSTED",
        "prompt_key": "VOL_BOOSTED",
        "target_assets": NON_MR_TARGET_ASSETS,
        "temperature": 0.5,
        "is_mr": False,
        "exit_style": "signal_reversal",
        "default_exit_condition": "rsi_14 > 60",
    },
    {
        "name": "VOLATILITY-BREAK",
        "prompt_key": "VOLATILITY_BREAK",
        "target_assets": NON_MR_TARGET_ASSETS,
        "temperature": 0.6,
        "is_mr": False,
        "exit_style": "signal_reversal",
        "default_exit_condition": "close > ema_50",
    },
]

# MR max 40% of HOF
MR_HOF_MAX_PCT = 0.40

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


# ============================================================================
# LLM PROMPTS (V9 — Asset-Specific + Lessons Learned)
# ============================================================================

# Common indicator list for all prompts
INDICATOR_LIST = """Verfügbare Indikatoren (NUTZE DIESE EXAKTEN NAMEN):
- close, open, high, low, volume
- bb_lower_N, bb_upper_N, bb_mid_N, bb_width_N (Bollinger, N=10-30)
- keltner_lower_N, keltner_upper_N, keltner_mid_N (Keltner Channel, N=10-30)
- rsi_N (RSI, N=5-21)
- zscore_N (Z-Score, N=10-30)
- cci_N (Commodity Channel Index, N=10-30)
- stoch_k_N, stoch_d_N (Stochastic, N=5-21)
- williams_r_N (Williams %R, N=5-21)
- atr_N (ATR, N=10-20)
- ema_N, sma_N (Moving Average, N=10-200)
- ema_slope_N (EMA Steigung %, positiv = steigend, N=10-50)
- volume_sma_N, volume_ratio_N (Volume SMA / Ratio, N=10-50)
- mfi_N (Money Flow Index, N=5-21)
- cmf_N (Chaikin Money Flow, N=10-30)
- obv_N (OBV Rate of Change %, N=10-30)
- bull_power_N, bear_power_N (Elder Ray, N=10-21)
- adx_N (ADX Trend-Stärke, N=10-20)
- macd_12_26, macd_signal_12_26, macd_hist_12_26 (MACD)
- roc_N (Rate of Change %, N=5-21)"""

LESSONS_LEARNED = """LESSONS LEARNED (150+ Strategien getestet, 0 echter Edge):
- Trailing Stop feuert NIE auf 1h (80-91% signal_exit, trailing 2-3% zu eng)
- Entries zu restriktiv = 0.4 Trades/Window = Rauschen
- Mean Reversion funktioniert NUR auf DOGE/ADA/AVAX, NIEMALS auf BTC/ETH
- Alle 4 "Champions" waren Rauschen — neue WF-Gate hat sie alle demotet
- IS-Score overfitted 150x — V17 hatte IS=4.88 aber OOS=-0.15%
- NICHTS was auf BTC/ETH MR macht, funktioniert jemals OOS"""

PROMPTS = {
    "MR_ALT": f"""Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE Mean-Reversion-Strategie für Long-Entry.

ZIEL-ASSETS: NUR DOGE, ADA, AVAX (volatile Alts — MR funktioniert HIER, nie auf BTC/ETH).

{LESSONS_LEARNED}

{INDICATOR_LIST}

ENTRY-REGELN:
- Mindestens 5 Signale pro Window (locker, nicht restriktiv!)
- RSI < 35 ODER close < bb_lower (ohne extra EMA-200 Filter!)
- Kombiniere 2-3 Indikatoren mit AND
- KEIN OR! Nur AND als logischer Operator
- KEINE Array-Vergleiche wie indicator[1]

GUTE ANSÄTZE:
- RSI + BB: close < bb_lower_20 AND rsi_14 < 35
- RSI + CCI: rsi_14 < 30 AND cci_20 < -100
- Stochastic + BB: stoch_k_14 < 20 AND close < bb_lower_20

EXIT: KEIN trailing_stop! Nutze stattdessen exit_condition.
Stop Loss: 3-4%, Max Hold: 18-24 Bars.

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_condition": "rsi_14 > 50", "exit_config": {{"stop_loss_pct": 3.5, "max_hold_bars": 20}}}}""",

    "MR_RELAXED": f"""Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE RELAXED Mean-Reversion-Strategie für Long-Entry.

ZIEL-ASSETS: NUR DOGE, ADA, AVAX (volatile Alts).

{LESSONS_LEARNED}

{INDICATOR_LIST}

ENTRY-REGELN (NOCH LOCKERER ALS MR-ALT):
- Ziel: ≥5 Trades pro Window, eher zu viele als zu wenige
- RSI < 40 (nicht < 30!)
- BB_lower OHNE zusätzlichen EMA-Filter
- Nur 2 Indikatoren kombinieren (weniger Filter = mehr Trades)
- KEIN OR! Nur AND als logischer Operator
- KEINE Array-Vergleiche

GUTE ANSÄTZE:
- RSI-only relaxed: rsi_14 < 40 AND close < bb_lower_20
- Stochastic relaxed: stoch_k_14 < 30 AND rsi_14 < 40
- Z-Score: zscore_20 < -1.5 AND rsi_14 < 40

EXIT: KEIN trailing_stop! Nutze exit_condition.
Exit wenn Preis sich erholt: close > bb_mid_20 ODER rsi_14 > 50.
Stop Loss: 3.5%, Max Hold: 24 Bars.

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_condition": "close > bb_mid_20", "exit_config": {{"stop_loss_pct": 3.5, "max_hold_bars": 24}}}}""",

    "TREND_REGIME": f"""Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE Trend-Regime-Strategie für Long-Entry.

ZIEL-ASSETS: ALLE 6 (BTC, ETH, SOL, AVAX, DOGE, ADA)

{LESSONS_LEARNED}

{INDICATOR_LIST}

ENTRY-REGELN:
- TRADE NUR wenn Markt im Trend (ADX > 20 + EMA Steigung positiv)
- Entry: Trend-Bestätigung + Momentum + Volume
- Mindestens 3 Indikatoren mit AND
- KEIN OR! Nur AND als logischer Operator
- KEINE Array-Vergleiche

GUTE ANSÄTZE:
- ADX + EMA + CMF: adx_14 > 20 AND close > ema_50 AND ema_slope_50 > 0 AND cmf_20 > 0
- MACD + OBV + ADX: macd_hist_12_26 > 0 AND adx_14 > 25 AND obv_20 > 0
- EMA-Cross + Volume: close > ema_50 AND ema_slope_50 > 0 AND volume_ratio_20 > 1.2

EXIT: KEIN trailing_stop! Nutze exit_condition.
Exit wenn Trend endet: close < ema_20 ODER adx_14 < 20.
Stop Loss: 4%, Max Hold: 24 Bars.

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_condition": "close < ema_20", "exit_config": {{"stop_loss_pct": 4.0, "max_hold_bars": 24}}}}""",

    "SIGNAL_EXIT": f"""Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE Strategie mit PAARIERTEN Entry+Exit Signalen für Long-Entry.

ZIEL-ASSETS: ALLE 6 (BTC, ETH, SOL, AVAX, DOGE, ADA)

{LESSONS_LEARNED}

{INDICATOR_LIST}

BESONDERHEIT: Du generierst Entry UND Exit als PAAR!
- Entry = WANN kaufen (z.B. RSI < 30)
- Exit = WANN verkaufen (z.B. RSI > 50) — ANDERS als Entry-Umkehr!
- Der Exit MUSS eine ANDERE Schwelle haben als der Entry
- Entry "RSI < 30" → Exit "RSI > 50" (nicht "RSI > 30" = sofort raus)

ENTRY-REGELN:
- Entry soll ≥5 Signale pro Window geben
- Exit soll genug Raum geben für Gewinn (nicht sofort aussteigen)
- KEIN OR! Nur AND als logischer Operator
- KEINE Array-Vergleiche

BEISPIELE für Entry/Exit-Paare:
- Entry: rsi_14 < 30 AND close < bb_lower_20 | Exit: rsi_14 > 55
- Entry: stoch_k_14 < 20 AND mfi_14 < 20 | Exit: stoch_k_14 > 60
- Entry: cci_20 < -100 AND close < keltner_lower_20 | Exit: cci_20 > 0

EXIT: KEIN trailing_stop! Der exit_condition ist dein Exit-Signal.
Stop Loss: 3.5%, Max Hold: 20 Bars.

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_condition": "...", "exit_config": {{"stop_loss_pct": 3.5, "max_hold_bars": 20}}}}""",

    "VOL_BOOSTED": f"""Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE Volume/Money-Flow-Boosted Strategie für Long-Entry.

ZIEL-ASSETS: ALLE 6 (BTC, ETH, SOL, AVAX, DOGE, ADA)

{LESSONS_LEARNED}

{INDICATOR_LIST}

ENTRY-REGELN:
- FOKUS auf Volume + Money Flow Indikatoren (MFI, CMF, OBV, Volume Ratio)
- Volume MUSS der Primäre Indikator sein (nicht nur Filter)
- Mindestens 2 Volume/Money-Flow Indikatoren + 1 Preis-Indikator
- KEIN OR! Nur AND als logischer Operator
- KEINE Array-Vergleiche

GUTE ANSÄTZE:
- MFI Oversold + Volume: mfi_14 < 20 AND volume_ratio_20 > 1.5 AND close < bb_lower_20
- CMF Reversal: cmf_20 < -0.1 AND obv_20 < -5 AND rsi_14 < 35
- Volume Spike + BB: volume_ratio_20 > 2.0 AND close < bb_lower_14 AND mfi_14 < 25

EXIT: KEIN trailing_stop! Nutze exit_condition.
Exit wenn Money Flow sich dreht: rsi_14 > 60 ODER cmf_20 > 0.1.
Stop Loss: 3.5%, Max Hold: 20 Bars.

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_condition": "rsi_14 > 60", "exit_config": {{"stop_loss_pct": 3.5, "max_hold_bars": 20}}}}""",

    "VOLATILITY_BREAK": f"""Du bist ein Quant-Stratege für 1h Crypto Perps.
Generiere EINE Volatility-Breakout / ATR-Expansion Strategie für Long-Entry.

ZIEL-ASSETS: ALLE 6 (BTC, ETH, SOL, AVAX, DOGE, ADA)

{LESSONS_LEARNED}

{INDICATOR_LIST}

KONZEPT: Volatility-Breakout nutzt Phasen niedriger Volatilität (Squeeze),
gefolgt von Expansion. Wenn BB_Width oder ATR schrumpft und dann expandiert,
steht ein großer Move bevor. Keltner-Channel Breakouts sind ein klassisches Signal.

ENTRY-REGELN:
- Kombiniere Volatility-Indikatoren (BB_Width, ATR, Keltner) mit Trend-Bestätigung
- Fokus auf Squeeze-Breakout: niedrige Volatilität + plötzliche Expansion
- Mindestens 2-3 Indikatoren mit AND
- KEIN OR! Nur AND als logischer Operator
- KEINE Array-Vergleiche

GUTE ANSÄTZE:
- Squeeze + Trend: bb_width_20 < 0.02 AND close > bb_mid_20 AND adx_14 > 25
- Keltner Breakout: close > keltner_upper_20 AND volume_ratio_20 > 1.5 AND roc_14 > 0
- ATR Expansion + Momentum: atr_14 > 0.5 AND roc_14 > 1 AND close > ema_50

EXIT: KEIN trailing_stop! Nutze exit_condition.
Exit wenn Volatility nachlässt: close < bb_mid_20 ODER bb_width_20 < 0.01.
Stop Loss: 4%, Max Hold: 24 Bars.

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_condition": "close < bb_mid_20", "exit_config": {{"stop_loss_pct": 4.0, "max_hold_bars": 24}}}}""",
}

MUTATION_PROMPT = """MUTIERE diese Strategie. Ändere 1-3 Entry-Parameter oder füge einen Entry-Filter hinzu.
Exit bleibt GLEICH (entry-only Mutation).

ELTER: {parent_name}
Entry: {parent_entry}
Exit: {parent_exit}
WF Robustness: {parent_wf} | IS-Score: {parent_is}

Verfügbare Indikatoren: close, open, high, low, volume, bb_lower_N, bb_upper_N, bb_mid_N, bb_width_N,
rsi_N, zscore_N, stoch_k_N, stoch_d_N, williams_r_N, atr_N, roc_N, macd_12_26,
macd_signal_12_26, macd_hist_12_26, adx_N, ema_N, sma_N, volume_sma_N, ema_slope_N,
mfi_N, cmf_N, obv_N, bull_power_N, bear_power_N, keltner_lower_N, keltner_upper_N,
keltner_mid_N, cci_N, volume_ratio_N.

WICHTIG: Nur Entry verändern! Exit unverändert lassen!
KEIN trailing_stop! Kein OR! Keine Array-Vergleiche!

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_condition": "{exit_condition}", "exit_config": {{"stop_loss_pct": X, "max_hold_bars": Z}}}}"""

CROSSOVER_PROMPT = """CROSSOVER zwei Strategien. Kombiniere die besten Entry-Indikatoren aus beiden.
Exit bleibt vom besseren Elter.

ELTER A (WF={parent_a_wf}, IS={parent_a_is}):
Entry: {parent_a_entry}
Exit: {parent_a_exit}

ELTER B (WF={parent_b_wf}, IS={parent_b_is}):
Entry: {parent_b_entry}
Exit: {parent_b_exit}

KEIN trailing_stop! Kein OR! Keine Array-Vergleiche!

Antworte NUR mit JSON:
{{"name": "DESCRIPTIVE_NAME", "entry_condition": "...", "exit_condition": "...", "exit_config": {{"stop_loss_pct": X, "max_hold_bars": Z}}}}"""


# ============================================================================
# LLM CALLS
# ============================================================================

def call_llm(prompt: str, temperature: float = 0.3) -> str:
    extra_params = {}
    if "deepseek" in MODEL.lower():
        extra_params["reasoning_effort"] = "high"

    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 2048,
        **extra_params,
    })
    req = urllib.request.Request(
        API_URL, data=payload.encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            msg = data["choices"][0]["message"]
            content = msg.get("content", "")
            if not content.strip() and msg.get("reasoning", "").strip():
                print(f"  ⚠️ Thinking model returned empty content, using reasoning field")
                content = msg["reasoning"]
            return content
    except urllib.error.HTTPError as e:
        if e.code == 503:
            # Server overloaded — retry once after 10s, then fallback to gemma4
            print(f"  ⚠️ LLM 503 (overloaded), retrying in 10s...")
            time.sleep(10)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read())
                    msg = data["choices"][0]["message"]
                    content = msg.get("content", "")
                    if not content.strip() and msg.get("reasoning", "").strip():
                        print(f"  ⚠️ Thinking model returned empty content, using reasoning field")
                        content = msg["reasoning"]
                    return content
            except Exception as e2:
                print(f"  ⚠️ LLM retry failed: {e2}, trying fallback model")
                fallback_payload = json.dumps({
                    "model": "gemma4:31b-cloud",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": 2048,
                })
                fallback_req = urllib.request.Request(
                    API_URL, data=fallback_payload.encode(),
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
                )
                try:
                    with urllib.request.urlopen(fallback_req, timeout=120) as resp:
                        data = json.loads(resp.read())
                        return data["choices"][0]["message"].get("content", "")
                except Exception as e3:
                    print(f"  ⚠️ Fallback model also failed: {e3}")
                    return ""
        print(f"  ⚠️ LLM error: {e}")
        return ""
    except Exception as e:
        print(f"  ⚠️ LLM error: {e}")
        return ""


def parse_strategy(text: str) -> dict | None:
    """Parse LLM response into strategy dict. Handles exit_condition field."""
    m = re.search(r'\{[^{}]*\{[^{}]*\}[^{}]*\}', text, re.DOTALL)
    if not m:
        m = re.search(r'\{[^{}]+\}', text)
    if not m:
        return None
    for attempt in [m.group(), re.sub(r',\s*}', '}', m.group()), re.sub(r',\s*]', ']', m.group())]:
        try:
            d = json.loads(attempt)
            if "entry_condition" in d:
                entry = d["entry_condition"]
                if " OR " in entry.upper():
                    print(f"    ⚠️ Rejected OR in entry: {entry[:60]}")
                    return None
                if re.search(r'\w+\[', entry):
                    print(f"    ⚠️ Rejected array comparison in entry: {entry[:60]}")
                    return None
                # Validate exit_condition if present (OR allowed in exit, no arrays)
                if "exit_condition" in d:
                    ec = d["exit_condition"]
                    if re.search(r'\w+\[', ec):
                        print(f"    ⚠️ Rejected array comparison in exit_condition: {ec[:60]}")
                        return None
                # Remove trailing_stop_pct if LLM sneakily includes it
                if "exit_config" in d and isinstance(d["exit_config"], dict):
                    d["exit_config"].pop("trailing_stop_pct", None)
                if "exit_config" not in d:
                    d["exit_config"] = {}
                return d
        except:
            pass
    return None

# ============================================================================
# EVALUATION
# ============================================================================

def get_target_assets(strategy_type: str) -> list:
    """Get target assets for a strategy type."""
    for arm in ARMS:
        if arm["prompt_key"] == strategy_type or arm["name"] == strategy_type:
            return arm["target_assets"]
    # Legacy type mapping
    if strategy_type in ("MR", "MR_ALT", "MR_RELAXED"):
        return MR_TARGET_ASSETS
    return NON_MR_TARGET_ASSETS


def is_mr_type(strategy_type: str) -> bool:
    for arm in ARMS:
        if arm["prompt_key"] == strategy_type or arm["name"] == strategy_type:
            return arm["is_mr"]
    return strategy_type in ("MR",)


def run_is_backtest(entry_condition: str, exit_config: dict, strategy_type: str = "",
                    target_assets: list = None) -> dict | None:
    try:
        exit_condition = exit_config.get("exit_condition", None)
        strategy_func, parseable = build_strategy_func(entry_condition, exit_condition=exit_condition)
        if not parseable or strategy_func is None:
            return None

        # If exit_condition is set, add exit_signal_col to exit_config for backtest engine
        bt_exit_config = dict(exit_config)
        if exit_condition:
            bt_exit_config["exit_signal_col"] = "exit_signal"

        engine = BacktestEngine(data_path=str(DATA_PATH))

        # Only test target assets (saves compute for MR arms)
        test_assets = target_assets or ASSETS

        all_returns, all_dds, all_cls, all_trades = [], [], [], []
        profitable = 0
        exit_reasons = {}
        per_asset_returns = {}

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
                        for t in result.trades:
                            r = t.exit_reason
                            if r not in exit_reasons:
                                exit_reasons[r] = {"count": 0, "total_pnl": 0.0, "wins": 0}
                            exit_reasons[r]["count"] += 1
                            exit_reasons[r]["total_pnl"] += t.pnl
                            if t.pnl > 0:
                                exit_reasons[r]["wins"] += 1
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
        avg_trades = sum(all_trades) / n

        profitable_ratio = profitable / n
        pr = max(profitable_ratio, 0.05)

        if total_return > 0 and avg_dd > 0:
            score = (total_return / avg_dd) * pr * min(1.0, min_trades / 5)
        elif total_return <= 0:
            score = total_return * pr * min(1.0, min_trades / 5) * 0.1
        else:
            score = 0

        exit_summary = {}
        for r, d in exit_reasons.items():
            avg_pnl = d["total_pnl"] / d["count"] if d["count"] > 0 else 0
            wr = d["wins"] / d["count"] if d["count"] > 0 else 0
            exit_summary[r] = {"count": d["count"], "avg_pnl": round(avg_pnl, 2), "win_rate": round(wr, 2)}

        # Compute exit_reason ratios for HOF
        total_exits = sum(d["count"] for d in exit_reasons.values())
        exit_condition_count = exit_reasons.get("exit_condition", {}).get("count", 0)
        stop_loss_count = exit_reasons.get("stop_loss", {}).get("count", 0)

        return {
            "avg_return": round(total_return, 2),
            "avg_dd": round(avg_dd, 1),
            "max_cl": max_cl,
            "min_trades": min_trades,
            "avg_trades": round(avg_trades, 1),
            "profitable_assets": f"{profitable}/{n}",
            "is_score": round(score, 2),
            "exit_reasons": exit_summary,
            "per_asset_returns": per_asset_returns,
            "exit_condition_ratio": round(exit_condition_count / total_exits, 2) if total_exits > 0 else 0,
            "stop_loss_ratio": round(stop_loss_count / total_exits, 2) if total_exits > 0 else 0,
        }
    except Exception as e:
        print(f"  ⚠️ IS error: {e}")
        return None


def run_wf(entry_condition: str, exit_config: dict, n_windows: int = WF_WINDOWS_NORMAL,
           strategy_type: str = "", target_assets: list = None) -> dict | None:
    try:
        exit_condition = exit_config.get("exit_condition", None)
        strategy_func, parseable = build_strategy_func(entry_condition, exit_condition=exit_condition)
        if not parseable or strategy_func is None:
            return {"wf_robustness": 0.0, "wf_passed": False, "wf_profitable_assets": "0/6",
                    "avg_oos_return": 0.0, "tier": "NEEDS_REVIEW" if not parseable else "PARSE_ERROR"}

        bt_exit_config = dict(exit_config)
        if exit_condition:
            bt_exit_config["exit_signal_col"] = "exit_signal"

        result = run_wf_on_candidate(
            name="eval", entry=entry_condition, exit_config=bt_exit_config,
            n_windows=n_windows, target_assets=target_assets,
        )
        return {
            "wf_robustness": result.get("robustness_score", 0),
            "wf_passed": result.get("passed", False),
            "wf_profitable_assets": result.get("profitable_assets", "0/6"),
            "avg_oos_return": result.get("avg_oos_return", 0),
            "tier": result.get("tier", "?"),
        }
    except Exception as e:
        print(f"  ⚠️ WF error: {e}")
        return None


def evaluate(candidate: dict) -> dict:
    name = candidate.get("name", "?")
    stype = candidate.get("strategy_type", "MR_ALT")
    target_assets = candidate.get("target_assets", get_target_assets(stype))
    candidate["target_assets"] = target_assets

    exit_config = candidate.get("exit_config", {})
    exit_condition = candidate.get("exit_condition", None)
    if exit_condition:
        exit_config["exit_condition"] = exit_condition
    candidate["exit_config"] = exit_config

    print(f"\n  🧬 {name} [{stype}]")
    print(f"     Entry: {candidate['entry_condition']}")
    print(f"     Exit: {exit_condition or 'signal_flip'} | {json.dumps({k:v for k,v in exit_config.items() if k != 'exit_condition'})}")
    print(f"     Target: {target_assets}")

    is_result = run_is_backtest(candidate["entry_condition"], exit_config, strategy_type=stype, target_assets=target_assets)
    if is_result:
        candidate.update(is_result)
        print(f"     IS: {is_result['is_score']:.2f} | R={is_result['avg_return']:+.2f}% | DD={is_result['avg_dd']:.1f}% | {is_result['profitable_assets']} | avg_trades={is_result.get('avg_trades', 0):.1f}")
    else:
        candidate.update({"avg_return": 0, "avg_dd": 0, "max_cl": 0, "min_trades": 0, "profitable_assets": "0/12", "is_score": -10})
        print(f"     IS: FAILED (parse error)")
        return candidate

    # IS pre-filter: skip WF if not enough trades
    avg_trades = is_result.get("avg_trades", 0)
    if avg_trades < IS_MIN_TRADES_THRESHOLD:
        candidate["wf_robustness"] = 0
        candidate["wf_passed"] = False
        candidate["wf_profitable_assets"] = "0/6"
        candidate["avg_oos_return"] = 0
        candidate["tier"] = "low_trades"
        candidate["wf_skipped"] = True
        print(f"     WF: SKIPPED (avg {avg_trades:.1f} trades < {IS_MIN_TRADES_THRESHOLD} threshold)")
        return candidate

    wf_result = run_wf(candidate["entry_condition"], exit_config, strategy_type=stype, target_assets=target_assets)
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
            return hof
        except:
            pass
    return []


def save_hof(hof: list[dict]):
    hof.sort(key=lambda x: (1 if x.get("wf_passed") else 0, x.get("wf_robustness", 0), x.get("is_score", 0)), reverse=True)
    champion = hof[0] if hof else None
    HOF_FILE.write_text(json.dumps({"updated": datetime.now().isoformat(), "champion": champion, "hof": hof[:50]}, indent=2))


def hof_mr_count(hof: list[dict]) -> int:
    """Count MR entries in HOF that passed WF."""
    return sum(1 for s in hof if s.get("wf_passed") and is_mr_type(s.get("strategy_type", classify_strategy_type(s.get("entry_condition", "")))))

# ============================================================================
# DIVERSITY & CLASSIFICATION
# ============================================================================

def entry_pattern(entry: str) -> str:
    indicators = sorted(set(re.findall(
        r'(bb_lower|bb_upper|bb_width|bb_mid|rsi|ema|sma|macd|adx|zscore|atr|volume|stoch|williams|roc|mfi|cmf|obv|bull_power|bear_power|keltner|cci|volume_ratio|ema_slope)',
        entry.lower())))
    return '+'.join(indicators) if indicators else 'unknown'


def classify_strategy_type(entry: str) -> str:
    """Classify strategy type from entry condition. Returns V9 arm key."""
    e = entry.lower()
    if 'bb_lower' in e or 'zscore' in e or 'keltner_lower' in e:
        if 'volume' in e or 'mfi' in e or 'cmf' in e or 'obv' in e or 'volume_ratio' in e:
            return 'VOL_BOOSTED'
        return 'MR_ALT'
    if 'rsi' in e and '<' in e:
        if 'volume' in e or 'mfi' in e or 'cmf' in e or 'obv' in e or 'volume_ratio' in e:
            return 'VOL_BOOSTED'
        return 'MR_ALT'
    if 'cci_' in e and '<' in e:
        return 'MR_ALT'
    if 'bb_width' in e:
        return 'TREND_REGIME'
    if 'adx' in e or 'ema_slope' in e:
        return 'TREND_REGIME'
    if 'roc_' in e or 'macd_hist' in e or 'bull_power' in e:
        return 'VOLATILITY_BREAK'
    if 'cmf' in e or 'mfi' in e or 'obv' in e:
        return 'VOL_BOOSTED'
    if 'stoch' in e or 'williams' in e:
        return 'MR_ALT'
    if 'bear_power' in e:
        return 'MR_ALT'
    return 'MR_ALT'

# ============================================================================
# MAIN — V9 Oktopus Evolution
# ============================================================================

def main():
    hof = load_hof()
    hof_passed = [s for s in hof if s.get("wf_passed")]

    # Count strategy types in HOF
    hof_types = {}
    mr_in_hof = hof_mr_count(hof)
    for s in hof_passed:
        t = s.get("strategy_type", classify_strategy_type(s.get("entry_condition", "")))
        hof_types[t] = hof_types.get(t, 0) + 1

    print("=" * 70)
    print("FOUNDRY V9 — Oktopus Evolution (Asset-Specific Arms)")
    print(f"Arms: {', '.join(a['name'] for a in ARMS)}")
    print(f"MR targets: {MR_TARGET_ASSETS} | Non-MR targets: {NON_MR_TARGET_ASSETS}")
    print(f"Exit: Signal-Reversal (no trailing stop)")
    print(f"IS pre-filter: ≥{IS_MIN_TRADES_THRESHOLD} trades/asset/window")
    print(f"WF windows: {WF_WINDOWS_NORMAL} | HOF: {len(hof)} ({len(hof_passed)} passed, {mr_in_hof} MR)")
    print(f"MR HOF cap: {MR_HOF_MAX_PCT:.0%}")
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
    # PHASE 1: EXPLORATION — Per arm with asset-specific prompts
    # =========================================================================
    print(f"\n{'='*70}")
    print("PHASE 1: EXPLORATION (V9 Asset-Specific Arms)")
    print("=" * 70)

    phase1_evaluated = []
    phase1_passed = []

    for arm in ARMS:
        prompt = PROMPTS[arm["prompt_key"]]
        n_cands = N_EXPLORATION_PER_TYPE
        arm_key = arm["prompt_key"]

        # HOF Quota: MR max 40% of HOF
        hof_total_passed = max(len(hof_passed), 1)
        mr_pct = mr_in_hof / hof_total_passed if hof_total_passed > 0 else 0

        if arm["is_mr"] and mr_pct > MR_HOF_MAX_PCT:
            n_cands = max(2, n_cands // 2)
            print(f"\n  ⚖️ MR at {mr_pct:.0%} HOF (cap {MR_HOF_MAX_PCT:.0%}) — reduced to {n_cands} candidates")
        elif not arm["is_mr"] and mr_pct > MR_HOF_MAX_PCT:
            n_cands = max(n_cands, N_EXPLORATION_PER_TYPE + 2)
            print(f"\n  🚀 Non-MR boost (MR {mr_pct:.0%}) — {n_cands} candidates")
        else:
            print(f"\n  📝 {arm['name']} ({n_cands} candidates, targets={arm['target_assets']})")

        for i in range(n_cands):
            base_temp = arm["temperature"]
            temp = base_temp if i == 0 else min(base_temp + 0.3, 0.9)
            response = call_llm(prompt, temperature=temp)
            parsed = parse_strategy(response)
            if parsed:
                parsed["strategy_type"] = arm_key
                parsed["target_assets"] = arm["target_assets"]
                pat = entry_pattern(parsed["entry_condition"])
                parsed["entry_pattern"] = pat
                is_new = pat not in seen_patterns
                parsed["is_new_pattern"] = is_new
                if is_new:
                    seen_patterns.add(pat)
                exact_entry = parsed["entry_condition"].strip().lower()
                if exact_entry in seen_exact_entries:
                    print(f"  ⏭️ Duplicate entry (skip): {parsed.get('name', '?')}")
                    continue
                seen_exact_entries.add(exact_entry)
                diversity_tag = " 🌱 NEW PATTERN" if is_new else ""
                ec_tag = f" exit_cond={parsed.get('exit_condition', 'none')}" if parsed.get('exit_condition') else ""
                print(f"  ✅ Parsed: {parsed.get('name', '?')} [{pat}]{diversity_tag}{ec_tag}")
                all_candidates.append(parsed)
            else:
                print(f"  ⚠️ Parse error on {arm['name']} #{i+1}")

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
    skipped_wf = sum(1 for c in phase1_evaluated if c.get("wf_skipped"))
    print(f"   WF skipped (low trades): {skipped_wf}")

    # =========================================================================
    # PHASE 2: EVOLUTION — Mutation + Crossover from HOF
    # =========================================================================
    print(f"\n{'='*70}")
    print("PHASE 2: EVOLUTION (Entry-Only Mutations)")
    print("=" * 70)

    phase2_evaluated = []
    phase2_passed = []

    # Mutation pool: HOF-passed + best Phase 1
    mutation_pool = list(hof_passed) if hof_passed else []

    # Add top Phase 1 candidates PER ARM TYPE
    phase1_sorted = sorted(phase1_evaluated, key=lambda x: x.get('is_score', -10), reverse=True)
    seen_entries = {s.get('entry_condition', '') for s in mutation_pool}
    type_added = {}
    for cand in phase1_sorted:
        entry = cand.get('entry_condition', '')
        stype = cand.get('strategy_type', classify_strategy_type(entry))
        if entry not in seen_entries and type_added.get(stype, 0) < 2:
            mutation_pool.append(cand)
            seen_entries.add(entry)
            type_added[stype] = type_added.get(stype, 0) + 1

    # Filter mutation pool: only entries with ≥3 trades/asset/window
    eligible_pool = [m for m in mutation_pool if m.get("avg_trades", m.get("min_trades", 0)) >= IS_MIN_TRADES_THRESHOLD]
    if not eligible_pool:
        eligible_pool = mutation_pool  # Fallback if none meet threshold

    print(f"  Mutation pool: {len(eligible_pool)} eligible ({len(mutation_pool)} total)")

    if eligible_pool:
        # Enforce MR quota in mutation
        mr_in_pool = sum(1 for m in eligible_pool if is_mr_type(m.get("strategy_type", "")))
        mr_pool_cap = int(len(eligible_pool) * MR_HOF_MAX_PCT)

        top_n = min(3, len(eligible_pool))
        parents = sorted(eligible_pool, key=lambda x: x.get("wf_robustness", x.get("is_score", -10)), reverse=True)[:top_n]

        # Ensure diversity: at most 1 MR parent if MR dominates
        mr_parents = [p for p in parents if is_mr_type(p.get("strategy_type", ""))]
        non_mr_parents = [p for p in parents if not is_mr_type(p.get("strategy_type", ""))]

        if mr_pct > MR_HOF_MAX_PCT and len(mr_parents) > 1:
            # Keep only top MR parent, add more non-MR
            parents = [mr_parents[0]] + non_mr_parents[:2]
            print(f"  ⚖️ MR mutation capped: keeping 1 MR parent, {len(non_mr_parents)} non-MR parents")

        for parent in parents:
            exit_condition = parent.get("exit_condition", parent.get("exit_config", {}).get("exit_condition", ""))
            parent_exit_display = f"exit={exit_condition}" if exit_condition else "signal_flip"

            for i in range(N_MUTATIONS_PER_PARENT):
                prompt = MUTATION_PROMPT.format(
                    parent_name=parent.get("name", "?"),
                    parent_entry=parent.get("entry_condition", ""),
                    parent_exit=parent_exit_display,
                    parent_wf=parent.get("wf_robustness", 0),
                    parent_is=parent.get("is_score", 0),
                    exit_condition=exit_condition or "signal_flip",
                )
                # Use arm-specific temperature
                parent_type = parent.get("strategy_type", "MR_ALT")
                arm_temp = 0.4
                for arm in ARMS:
                    if arm["prompt_key"] == parent_type:
                        arm_temp = arm["temperature"]
                        break

                response = call_llm(prompt, temperature=arm_temp)
                parsed = parse_strategy(response)
                if parsed:
                    parsed["strategy_type"] = parent_type
                    parsed["target_assets"] = parent.get("target_assets", get_target_assets(parent_type))
                    # Inherit exit_condition from parent (entry-only mutation)
                    if not parsed.get("exit_condition") and exit_condition:
                        parsed["exit_condition"] = exit_condition
                    parsed["parent"] = parent.get("name", "?")
                    parsed["phase"] = "mutation"
                    print(f"  🔀 Mutation of {parent.get('name','?')}: {parsed.get('name','?')}")
                    evaluate(parsed)
                    phase2_evaluated.append(parsed)
                    if parsed.get("wf_passed"):
                        hof.append(parsed)
                        phase2_passed.append(parsed)

        # Crossover
        if len(eligible_pool) >= 2:
            type_groups = {}
            for m in eligible_pool:
                t = m.get('strategy_type', classify_strategy_type(m.get('entry_condition', '')))
                type_groups.setdefault(t, []).append(m)

            for i in range(N_CROSSOVERS):
                types = list(type_groups.keys())
                if len(types) >= 2:
                    t1, t2 = random.sample(types, 2)
                    a = random.choice(type_groups[t1])
                    b = random.choice(type_groups[t2])
                else:
                    a, b = random.sample(eligible_pool[:5], 2)

                prompt = CROSSOVER_PROMPT.format(
                    parent_a_wf=a.get("wf_robustness", 0),
                    parent_a_is=a.get("is_score", 0),
                    parent_a_entry=a.get("entry_condition", ""),
                    parent_a_exit=a.get("exit_condition", a.get("exit_config", {}).get("exit_condition", "signal_flip")),
                    parent_b_wf=b.get("wf_robustness", 0),
                    parent_b_is=b.get("is_score", 0),
                    parent_b_entry=b.get("entry_condition", ""),
                    parent_b_exit=b.get("exit_condition", b.get("exit_config", {}).get("exit_condition", "signal_flip")),
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
    # PHASE 3: HARD CHECK — 10-window WF on top candidates
    # =========================================================================
    print(f"\n{'='*70}")
    print("PHASE 3: HARD CHECK (10-window WF)")
    print("=" * 70)

    newly_passed = [s for s in hof if s.get("wf_passed") and not s.get("wf_passed_10w") and "wf_robustness_10w" not in s]
    top_for_hard = sorted(newly_passed, key=lambda x: x.get("wf_robustness", 0), reverse=True)[:N_HARD_CHECK_TOP]

    if top_for_hard:
        for candidate in top_for_hard:
            print(f"\n  🔍 Hard-checking: {candidate.get('name', '?')} (WF={candidate.get('wf_robustness', 0):.1f})")
            cand_type = candidate.get('strategy_type', classify_strategy_type(candidate.get("entry_condition", "")))
            target_assets = candidate.get("target_assets", get_target_assets(cand_type))
            exit_config = candidate.get("exit_config", {})
            if candidate.get("exit_condition"):
                exit_config["exit_condition"] = candidate["exit_condition"]

            wf_10w = run_wf(candidate["entry_condition"], exit_config,
                            n_windows=WF_WINDOWS_HARD, strategy_type=cand_type,
                            target_assets=target_assets)
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
    # PHASE 4: AUTOPSIE — Learn from failures
    # =========================================================================
    print(f"\n{'='*70}")
    print("PHASE 4: AUTOPSIE (Learn from WF failures)")
    print("=" * 70)

    try:
        from autopsy import autopsie as run_autopsie
        has_autopsie = True
    except ImportError:
        has_autopsie = False
        print("  ⚠️ autopsy module not available, skipping")

    mutation_feed = []

    if has_autopsie:
        all_evaluated = phase1_evaluated + phase2_evaluated
        wf_failed = [c for c in all_evaluated if not c.get('wf_passed') and c.get('wf_robustness', 0) > 0 and not c.get('wf_skipped')]

        for candidate in wf_failed[:10]:
            try:
                exit_config = candidate.get("exit_config", {})
                if candidate.get("exit_condition"):
                    exit_config["exit_condition"] = candidate["exit_condition"]
                target_assets = candidate.get("target_assets", get_target_assets(candidate.get("strategy_type", "")))

                wf_detail = run_wf_on_candidate(
                    name=candidate.get('name', '?'),
                    entry=candidate.get('entry_condition', candidate.get('entry', '')),
                    exit_config=exit_config,
                    target_assets=target_assets,
                )
                result = run_autopsie(candidate, wf_detail)

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

        if mutation_feed:
            feed_file = HOF_DIR / 'mutation_feed.json'
            with open(feed_file, 'w') as f:
                json.dump(mutation_feed, f, indent=2, default=str)
            print(f"\n  💾 Mutation feed saved ({len(mutation_feed)} entries)")

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    print(f"\n{'='*70}")
    print("FINAL SUMMARY — FOUNDRY V9")
    print("=" * 70)

    total_evaluated = len(phase1_evaluated) + len(phase2_evaluated)
    total_passed = len(phase1_passed) + len(phase2_passed)
    skipped_wf = sum(1 for c in phase1_evaluated + phase2_evaluated if c.get("wf_skipped"))

    print(f"Phase 1:   {len(phase1_evaluated)} evaluated, {len(phase1_passed)} WF-passed, {skipped_wf} skipped (low trades)")
    print(f"Phase 2:   {len(phase2_evaluated)} evaluated, {len(phase2_passed)} WF-passed")
    print(f"Total:     {total_evaluated} evaluated, {total_passed} WF-passed")

    # Strategy type breakdown
    type_stats = {}
    for c in phase1_evaluated + phase2_evaluated:
        t = c.get("strategy_type", classify_strategy_type(c.get("entry_condition", "")))
        if t not in type_stats:
            type_stats[t] = {"evaluated": 0, "wf_passed": 0, "parse_fail": 0, "skipped": 0}
        type_stats[t]["evaluated"] += 1
        if c.get("wf_passed"):
            type_stats[t]["wf_passed"] += 1
        if c.get("is_score", 0) == -10:
            type_stats[t]["parse_fail"] += 1
        if c.get("wf_skipped"):
            type_stats[t]["skipped"] += 1

    print(f"\n  Strategy type breakdown:")
    for t, stats in sorted(type_stats.items()):
        sk = f", {stats['skipped']} skipped" if stats['skipped'] > 0 else ""
        print(f"    {t:16s}: {stats['evaluated']} eval, {stats['wf_passed']} WF-passed{sk}")

    # Exit reason analysis
    exit_type_stats = {"exit_condition": 0, "signal_exit": 0, "stop_loss": 0, "trailing_stop": 0, "max_hold": 0}
    for c in phase1_evaluated + phase2_evaluated:
        for reason, data in c.get("exit_reasons", {}).items():
            if reason in exit_type_stats:
                exit_type_stats[reason] += data.get("count", 0)
    total_exits = sum(exit_type_stats.values())
    if total_exits > 0:
        print(f"\n  Exit type distribution:")
        for r, count in exit_type_stats.items():
            if count > 0:
                pct = count / total_exits * 100
                print(f"    {r:16s}: {count:5d} ({pct:.1f}%)")

    print(f"\n  HOF total: {len(hof)} | WF-passed: {len([s for s in hof if s.get('wf_passed')])} | 10w-champions: {len([s for s in hof if s.get('wf_passed_10w')])}")

    # Top 10 HOF
    print(f"\n🏆 HALL OF FAME (top 10):")
    sorted_hof = sorted(hof, key=lambda x: (x.get("wf_robustness", 0), x.get("is_score", 0)), reverse=True)
    for i, s in enumerate(sorted_hof[:10]):
        wf = "✅" if s.get("wf_passed") else "❌"
        hc = f" 10w={'✅' if s.get('wf_passed_10w') else '❌'}" if "wf_robustness_10w" in s else ""
        stype = s.get("strategy_type", classify_strategy_type(s.get("entry_condition", "")))
        ec = s.get("exit_condition", s.get("exit_config", {}).get("exit_condition", ""))
        ec_tag = f" exit={ec}" if ec else ""
        print(f"  {i+1}. {s.get('name', '?'):40s} WF={s.get('wf_robustness', 0):5.1f} {wf}{hc} | IS={s.get('is_score', 0):6.2f} [{stype}]{ec_tag}")

    # Composite fitness ranking
    hof_scored = []
    for s in hof:
        target = s.get("target_assets", get_target_assets(s.get("strategy_type", "")))
        fitness, components = compute_fitness(s, target_assets=target)
        s["composite_fitness"] = fitness
        hof_scored.append((s, fitness))
    hof_scored.sort(key=lambda x: x[1], reverse=True)

    hof_10w = [s for s in hof if s.get("wf_passed_10w")]
    if hof_10w:
        champs_scored = [(s, f) for s, f in hof_scored if s.get("wf_passed_10w")]
        print(f"\n🏆 10W CHAMPIONS (V9 Fitness):")
        for i, (s, fitness) in enumerate(champs_scored[:5], 1):
            oos = s.get('avg_oos_return', 0)
            print(f"   {i}. fitness={fitness:.3f} {s.get('name','?')[:45]:45s} OOS={oos:+.2f}%")

    # Arm performance update
    arm_perf_file = HOF_DIR / 'arm_performance.json'
    try:
        if arm_perf_file.exists():
            arm_performance = json.load(open(arm_perf_file))
        else:
            arm_performance = {}
    except:
        arm_performance = {}

    all_arm_results = phase1_evaluated + phase2_evaluated
    for arm in ARMS:
        arm_key = arm["prompt_key"]
        arm_cands = [c for c in all_arm_results if c.get("strategy_type") == arm_key]
        if arm_key not in arm_performance:
            arm_performance[arm_key] = {"candidates_total": 0, "wf_passed": 0, "avg_is": 0, "trend": "new", "history": []}
        perf = arm_performance[arm_key]
        perf["candidates_total"] = perf.get("candidates_total", 0) + len(arm_cands)
        new_passed = sum(1 for c in arm_cands if c.get("wf_passed"))
        perf["wf_passed"] = perf.get("wf_passed", 0) + new_passed
        avg_is = sum(c.get("is_score", 0) for c in arm_cands) / max(len(arm_cands), 1)
        perf["avg_is"] = round(avg_is, 3)
        history = perf.get("history", [])
        history.append({"date": datetime.now().strftime("%Y-%m-%d"), "candidates": len(arm_cands), "wf_passed": new_passed, "avg_is": round(avg_is, 3)})
        perf["history"] = history[-10:]
        recent_is = [h["avg_is"] for h in perf["history"][-5:]]
        if any(v > 0 for v in recent_is):
            perf["trend"] = "producing"
        elif len(recent_is) >= 3 and recent_is[-1] > recent_is[0]:
            perf["trend"] = "promising"
        elif all(v < -0.3 for v in recent_is):
            perf["trend"] = "dead"
        elif len(recent_is) >= 2 and recent_is[-1] < recent_is[0]:
            perf["trend"] = "declining"
        else:
            perf["trend"] = "stable"

    with open(arm_perf_file, 'w') as f:
        json.dump(arm_performance, f, indent=2)
    print(f"\n📊 Arm Performance:")
    for arm in ARMS:
        k = arm["prompt_key"]
        perf = arm_performance.get(k, {})
        print(f"  {arm['name']:16s}: {perf.get('trend', '?'):10s} | IS_avg={perf.get('avg_is', 0):+.3f} | WF_passed={perf.get('wf_passed', 0)}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = HOF_DIR / f"evolution_v9_results_{timestamp}.json"
    report = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "version": "V9_oktopus",
        "model": MODEL,
        "phase1_evaluated": len(phase1_evaluated),
        "phase1_passed": len(phase1_passed),
        "phase2_evaluated": len(phase2_evaluated),
        "phase2_passed": len(phase2_passed),
        "hof_size": len(hof),
        "champion": hof_10w[0] if hof_10w else None,
        "type_stats": type_stats,
        "exit_type_stats": exit_type_stats,
        "hof_top5": [
            {"name": s.get("name", "?"), "wf_robustness": s.get("wf_robustness", 0),
             "wf_passed": s.get("wf_passed", False), "is_score": s.get("is_score", 0),
             "strategy_type": s.get("strategy_type", classify_strategy_type(s.get("entry_condition", ""))),
             "wf_robustness_10w": s.get("wf_robustness_10w", 0),
             "exit_condition": s.get("exit_condition", "")}
            for s in sorted_hof[:5]
        ],
    }
    with open(results_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n💾 Results saved to {results_file}")

    print(f"\nV9 Daily run complete. Exit code: 0")


if __name__ == "__main__":
    main()