#!/usr/bin/env python3
"""
Walk-Forward Gate for Evolution Candidates (V8 — Extended DSL)

Runs Walk-Forward validation on a candidate strategy.
Used as a quality gate: only candidates that pass WF enter the Hall of Fame.

Supported indicators (V8):
  close, open, high, low, volume
  bb_lower_N, bb_upper_N, bb_mid_N, bb_width_N
  rsi_N, ema_N, sma_N, zscore_N
  stoch_k_N, stoch_d_N           (NEW)
  williams_r_N                   (NEW)
  atr_N                          (NEW)
  roc_N                          (NEW)
  macd_N_M, macd_signal_N_M      (NEW, simplified)
  macd_hist_N_M                  (NEW)
  adx_N                          (NEW, simplified)
  volume_sma_N                   (NEW)
  ema_slope_N, sma_slope_N       (NEW)

Usage:
    python3 walk_forward_gate.py --candidate <json_file_or_string>
    python3 walk_forward_gate.py --hof <json_file>
"""

import sys
import json
import time
import re
from pathlib import Path
from datetime import datetime

import polars as pl
import numpy as np

RESEARCH_DIR = Path(__file__).parent
sys.path.insert(0, str(RESEARCH_DIR))
sys.path.insert(0, str(RESEARCH_DIR / "backtest"))

from backtest.backtest_engine import BacktestEngine


def aggregate_to_4h(df_1h: pl.DataFrame) -> pl.DataFrame:
    """Aggregate 1h candles to 4h candles."""
    return df_1h.sort("timestamp").group_by_dynamic(
        "timestamp", every="4h", label="left"
    ).agg([
        pl.col("open").first(),
        pl.col("high").max(),
        pl.col("low").min(),
        pl.col("close").last(),
        pl.col("volume").sum(),
    ])

ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
SYMBOLS = [f"{a}USDT" for a in ASSETS]
DATA_DIR = RESEARCH_DIR / "data"
OUTPUT_DIR = RESEARCH_DIR / "runs" / "walk_forward"


def load_asset_data(symbol: str, timeframe: str = "1h") -> pl.DataFrame:
    """Load data, preferring _full version."""
    for suffix in [f"_{timeframe}_full.parquet", f"_{timeframe}.parquet"]:
        path = DATA_DIR / f"{symbol}{suffix}"
        if path.exists():
            return pl.read_parquet(path)
    raise FileNotFoundError(f"No data for {symbol}")


# ─── Strategy Function Builder (V8 Extended) ─────────────────────────

NATIVE_STRATEGIES = {
    "close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200": "mean_reversion_bb",
}

SIMPLE_INDICATORS = {'close', 'open', 'high', 'low', 'volume'}
PARSABLE_PREFIXES = [
    'bb_lower_', 'bb_upper_', 'bb_width_', 'bb_mid_',
    'rsi_', 'ema_', 'sma_', 'zscore_',
    'stoch_k_', 'stoch_d_',
    'williams_r_',
    'atr_',
    'roc_',
    'macd_', 'macd_signal_', 'macd_hist_',
    'adx_',
    'volume_sma_',
    'ema_slope_', 'sma_slope_',
    # New V8 indicators
    'mfi_', 'cmf_', 'obv_',
    'cci_',
    'volume_ratio_',
    'keltner_lower_', 'keltner_mid_', 'keltner_upper_',
    'bull_power_', 'bear_power_',
]


def build_strategy_func(entry_condition: str, exit_condition: str = None):
    """
    Build a strategy function from a DSL entry condition string.
    Optionally builds an exit signal column from exit_condition (V9 signal-reversal exits).
    Returns (strategy_func, parseable_bool) tuple.
    
    When exit_condition is provided, the strategy_func adds an 'exit_signal' column
    and the exit_config should include {"exit_signal_col": "exit_signal"} for the
    backtest engine to use explicit exit conditions.
    """
    # 1) Native strategies: exact match
    native_name = NATIVE_STRATEGIES.get(entry_condition.strip())
    if native_name == "mean_reversion_bb":
        from strategy_lab.mean_reversion_bb import mean_reversion_bb_strategy
        return mean_reversion_bb_strategy, True

    # 2) Check if entry uses only parseable indicators
    cond_lower = entry_condition.lower()
    tokens = re.findall(r'[a-z_]+\d*', cond_lower)
    for t in tokens:
        if t in ('and', 'or', 'not', '') or t in SIMPLE_INDICATORS:
            continue
        if any(t.startswith(p) for p in PARSABLE_PREFIXES):
            continue
        if t.startswith('volume'):
            continue
        # Bare number fragments from compound names like macd_12_26 → _26
        if re.match(r'^_?\d+$', t):
            continue
        # Multiplication like '* 1.5' may leave stray tokens
        if t in ('*', '/', '+', '-'):
            continue
        # Unknown indicator → cannot parse
        return None, False

    # Also validate exit_condition indicators if provided
    if exit_condition:
        exit_lower = exit_condition.lower()
        exit_tokens = re.findall(r'[a-z_]+\d*', exit_lower)
        for t in exit_tokens:
            if t in ('and', 'or', 'not', '') or t in SIMPLE_INDICATORS:
                continue
            if any(t.startswith(p) for p in PARSABLE_PREFIXES):
                continue
            if t.startswith('volume'):
                continue
            if re.match(r'^_?\d+$', t):
                continue
            if t in ('*', '/', '+', '-'):
                continue
            return None, False

    # 3) Extended DSL parser
    def strategy_func(df: pl.DataFrame, params: dict) -> pl.DataFrame:
        # Compute indicators needed for both entry and exit
        combined = entry_condition
        if exit_condition:
            combined = f"{entry_condition} AND {exit_condition}"
        indicators = _compute_indicators(combined, df)
        df = df.with_columns([v.alias(k) for k, v in indicators.items()])
        
        # Entry signal
        conditions = [c.strip() for c in entry_condition.split(' AND ')]
        signal = pl.lit(True)
        for cond in conditions:
            signal = signal & _parse_simple_condition(cond)
        df = df.with_columns((pl.when(signal).then(1).otherwise(0)).alias('signal'))
        
        # Exit signal (V9: explicit exit condition different from entry)
        if exit_condition:
            exit_conds = [c.strip() for c in exit_condition.split(' AND ')]
            exit_signal = pl.lit(True)
            for cond in exit_conds:
                exit_signal = exit_signal & _parse_simple_condition(cond)
            df = df.with_columns((pl.when(exit_signal).then(1).otherwise(0)).alias('exit_signal'))
        
        return df

    return strategy_func, True


def _compute_indicators(entry_condition: str, df: pl.DataFrame) -> dict:
    """Compute all indicators referenced in the entry condition."""
    indicators = {}

    # BB bands: bb_lower_N, bb_upper_N, bb_width_N, bb_mid_N
    for m in re.finditer(r'bb_(lower|upper|mid|width)_(\d+)', entry_condition):
        period = int(m.group(2))
        if f'bb_upper_{period}' not in indicators:
            sma = pl.col('close').rolling_mean(window_size=period, min_periods=period)
            std = pl.col('close').rolling_std(window_size=period, min_periods=period)
            indicators[f'bb_upper_{period}'] = sma + 2.0 * std
            indicators[f'bb_lower_{period}'] = sma - 2.0 * std
            indicators[f'bb_mid_{period}'] = sma
            indicators[f'bb_width_{period}'] = (4.0 * std) / pl.when(sma == 0).then(0.001).otherwise(sma)

    # RSI: rsi_N
    for m in re.finditer(r'rsi_(\d+)', entry_condition):
        period = int(m.group(1))
        key = f'rsi_{period}'
        if key not in indicators:
            delta = pl.col('close').diff()
            gain = pl.when(delta > 0).then(delta).otherwise(0.0)
            loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
            avg_gain = gain.rolling_mean(window_size=period, min_periods=period)
            avg_loss = loss.rolling_mean(window_size=period, min_periods=period)
            rs = avg_gain / pl.when(avg_loss == 0).then(0.0001).otherwise(avg_loss)
            indicators[key] = 100 - (100 / (1 + rs))

    # ZScore: zscore_N
    for m in re.finditer(r'zscore_(\d+)', entry_condition):
        period = int(m.group(1))
        key = f'zscore_{period}'
        if key not in indicators:
            sma = pl.col('close').rolling_mean(window_size=period, min_periods=period)
            std = pl.col('close').rolling_std(window_size=period, min_periods=period)
            indicators[key] = (pl.col('close') - sma) / pl.when(std == 0).then(0.001).otherwise(std)

    # EMA/SMA: ema_N, sma_N (on close)
    for m in re.finditer(r'(ema|sma)_(\d+)', entry_condition):
        kind = m.group(1)
        period = int(m.group(2))
        key = f'{kind}_{period}'
        # Skip if it's part of slope or macd
        if 'slope' in entry_condition and key in indicators:
            continue
        if key not in indicators:
            indicators[key] = pl.col('close').rolling_mean(window_size=period, min_periods=period)

    # EMA/SMA Slope: ema_slope_N, sma_slope_N
    for m in re.finditer(r'(ema|sma)_slope_(\d+)', entry_condition):
        kind = m.group(1)
        period = int(m.group(2))
        base_key = f'{kind}_{period}'
        slope_key = f'{kind}_slope_{period}'
        if base_key not in indicators:
            indicators[base_key] = pl.col('close').rolling_mean(window_size=period, min_periods=period)
        if slope_key not in indicators:
            indicators[slope_key] = indicators[base_key] - indicators[base_key].shift(1)

    # Stochastic %K/%D: stoch_k_N, stoch_d_N
    for m in re.finditer(r'stoch_(k|d)_(\d+)', entry_condition):
        period = int(m.group(2))
        k_key = f'stoch_k_{period}'
        d_key = f'stoch_d_{period}'
        if k_key not in indicators:
            lowest = pl.col('low').rolling_min(window_size=period, min_periods=period)
            highest = pl.col('high').rolling_max(window_size=period, min_periods=period)
            k_val = (pl.col('close') - lowest) / pl.when(highest - lowest == 0).then(0.001).otherwise(highest - lowest) * 100
            indicators[k_key] = k_val
        if d_key not in indicators:
            indicators[d_key] = indicators[k_key].rolling_mean(window_size=3, min_periods=3)

    # Williams %R: williams_r_N
    for m in re.finditer(r'williams_r_(\d+)', entry_condition):
        period = int(m.group(1))
        key = f'williams_r_{period}'
        if key not in indicators:
            highest = pl.col('high').rolling_max(window_size=period, min_periods=period)
            lowest = pl.col('low').rolling_min(window_size=period, min_periods=period)
            # Williams %R: -100 to 0 (oversold < -80)
            indicators[key] = (highest - pl.col('close')) / pl.when(highest - lowest == 0).then(0.001).otherwise(highest - lowest) * -100

    # ATR: atr_N
    for m in re.finditer(r'atr_(\d+)', entry_condition):
        period = int(m.group(1))
        key = f'atr_{period}'
        if key not in indicators:
            tr = pl.max_horizontal([
                (pl.col('high') - pl.col('low')).abs(),
                (pl.col('high') - pl.col('close').shift(1)).abs(),
                (pl.col('low') - pl.col('close').shift(1)).abs(),
            ])
            indicators[key] = tr.rolling_mean(window_size=period, min_periods=period)

    # ROC: roc_N (Rate of Change in %)
    for m in re.finditer(r'roc_(\d+)', entry_condition):
        period = int(m.group(1))
        key = f'roc_{period}'
        if key not in indicators:
            indicators[key] = (pl.col('close') / pl.col('close').shift(period) - 1) * 100

    # MACD: macd_N_M, macd_signal_N_M, macd_hist_N_M
    macd_matches = re.finditer(r'macd_(?:hist_)?(?:(\d+)_(\d+))', entry_condition)
    macd_periods = set()
    for m in macd_matches:
        fast, slow = int(m.group(1)), int(m.group(2))
        macd_periods.add((fast, slow))
    # Also match simple macd_N references
    for m in re.finditer(r'macd_(\d+)(?!_)', entry_condition):
        fast = int(m.group(1))
        macd_periods.add((fast, fast * 2 + 2))
    if not macd_periods and ('macd_' in entry_condition.lower()):
        macd_periods.add((12, 26))

    for fast, slow in macd_periods:
        macd_key = f'macd_{fast}_{slow}'
        signal_key = f'macd_signal_{fast}_{slow}'
        hist_key = f'macd_hist_{fast}_{slow}'
        if macd_key not in indicators:
            ema_fast = pl.col('close').rolling_mean(window_size=fast, min_periods=fast)
            ema_slow = pl.col('close').rolling_mean(window_size=slow, min_periods=slow)
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.rolling_mean(window_size=9, min_periods=9)
            indicators[macd_key] = macd_line
            indicators[signal_key] = signal_line
            indicators[hist_key] = macd_line - signal_line

    # ADX: adx_N (simplified)
    for m in re.finditer(r'adx_(\d+)', entry_condition):
        period = int(m.group(1))
        key = f'adx_{period}'
        if key not in indicators:
            plus_dm = pl.when(pl.col('high') - pl.col('high').shift(1) > pl.col('low').shift(1) - pl.col('low')).then(
                pl.max_horizontal([pl.col('high') - pl.col('high').shift(1), pl.lit(0.0)])
            ).otherwise(pl.lit(0.0))
            minus_dm = pl.when(pl.col('low').shift(1) - pl.col('low') > pl.col('high') - pl.col('high').shift(1)).then(
                pl.max_horizontal([pl.col('low').shift(1) - pl.col('low'), pl.lit(0.0)])
            ).otherwise(pl.lit(0.0))
            tr = pl.max_horizontal([
                (pl.col('high') - pl.col('low')).abs(),
                (pl.col('high') - pl.col('close').shift(1)).abs(),
                (pl.col('low') - pl.col('close').shift(1)).abs(),
            ])
            atr_val = tr.rolling_mean(window_size=period, min_periods=period)
            plus_di = 100 * plus_dm.rolling_mean(window_size=period, min_periods=period) / pl.when(atr_val == 0).then(0.001).otherwise(atr_val)
            minus_di = 100 * minus_dm.rolling_mean(window_size=period, min_periods=period) / pl.when(atr_val == 0).then(0.001).otherwise(atr_val)
            di_sum = plus_di + minus_di
            dx = 100 * (plus_di - minus_di).abs() / pl.when(di_sum == 0).then(0.001).otherwise(di_sum)
            indicators[key] = dx.rolling_mean(window_size=period, min_periods=period)

    # Volume SMA: volume_sma_N
    for m in re.finditer(r'volume_sma_(\d+)', entry_condition):
        period = int(m.group(1))
        key = f'volume_sma_{period}'
        if key not in indicators:
            indicators[key] = pl.col('volume').rolling_mean(window_size=period, min_periods=period)

    # ---- New V8 Indicators ----

    # MFI: mfi_N (Money Flow Index)
    for m in re.finditer(r'mfi_(\d+)', entry_condition):
        period = int(m.group(1))
        key = f'mfi_{period}'
        if key not in indicators:
            typical = (pl.col('high') + pl.col('low') + pl.col('close')) / 3
            raw_mf = typical * pl.col('volume')
            delta = typical.diff()
            pos_mf = pl.when(delta > 0).then(raw_mf).otherwise(0)
            neg_mf = pl.when(delta < 0).then(raw_mf).otherwise(0)
            pos_flow = pos_mf.rolling_mean(window_size=period, min_periods=period)
            neg_flow = neg_mf.rolling_mean(window_size=period, min_periods=period)
            neg_safe = pl.when(neg_flow == 0).then(1.0).otherwise(neg_flow)
            indicators[key] = 100 - (100 / (1 + pos_flow / neg_safe))

    # CMF: cmf_N (Chaikin Money Flow)
    for m in re.finditer(r'cmf_(\d+)', entry_condition):
        period = int(m.group(1))
        key = f'cmf_{period}'
        if key not in indicators:
            denom = pl.col('high') - pl.col('low')
            denom_safe = pl.when(denom == 0).then(1.0).otherwise(denom)
            clv = ((pl.col('close') - pl.col('low')) - (pl.col('high') - pl.col('close'))) / denom_safe
            mf_vol = clv * pl.col('volume')
            indicators[key] = mf_vol.rolling_sum(window_size=period, min_periods=period) / \
                pl.col('volume').rolling_sum(window_size=period, min_periods=period)

    # OBV: obv_N (On-Balance Volume ROC)
    for m in re.finditer(r'obv_(\d+)', entry_condition):
        period = int(m.group(1))
        key = f'obv_{period}'
        if key not in indicators:
            direction = pl.when(pl.col('close') > pl.col('close').shift(1)).then(1) \
                .when(pl.col('close') < pl.col('close').shift(1)).then(-1).otherwise(0)
            signed_vol = direction * pl.col('volume')
            obv = signed_vol.cum_sum()
            obv_shifted = obv.shift(period)
            obv_safe = pl.when(obv_shifted == 0).then(1.0).otherwise(obv_shifted)
            indicators[key] = (obv - obv_shifted) / obv_safe.abs() * 100

    # CCI: cci_N (Commodity Channel Index)
    for m in re.finditer(r'cci_(\d+)', entry_condition):
        period = int(m.group(1))
        key = f'cci_{period}'
        if key not in indicators:
            typical = (pl.col('high') + pl.col('low') + pl.col('close')) / 3
            sma_t = typical.rolling_mean(window_size=period, min_periods=period)
            mad = (typical - sma_t).abs().rolling_mean(window_size=period, min_periods=period)
            mad_safe = pl.when(mad == 0).then(1.0).otherwise(mad)
            indicators[key] = (typical - sma_t) / (0.015 * mad_safe)

    # Volume Ratio: volume_ratio_N
    for m in re.finditer(r'volume_ratio_(\d+)', entry_condition):
        period = int(m.group(1))
        key = f'volume_ratio_{period}'
        if key not in indicators:
            vol_sma = pl.col('volume').rolling_mean(window_size=period, min_periods=period)
            vol_safe = pl.when(vol_sma == 0).then(1.0).otherwise(vol_sma)
            indicators[key] = pl.col('volume') / vol_safe

    # Keltner Channel: keltner_lower_N, keltner_mid_N, keltner_upper_N
    for m in re.finditer(r'keltner_(lower|mid|upper)_(\d+)', entry_condition):
        period = int(m.group(2))
        if f'keltner_upper_{period}' not in indicators:
            ema = pl.col('close').ewm_mean(alpha=2/(period+1), min_samples=period)
            tr = pl.max_horizontal([
                (pl.col('high') - pl.col('low')).abs(),
                (pl.col('high') - pl.col('close').shift(1)).abs(),
                (pl.col('low') - pl.col('close').shift(1)).abs(),
            ])
            atr = tr.rolling_mean(window_size=period, min_periods=period)
            indicators[f'keltner_upper_{period}'] = ema + 1.5 * atr
            indicators[f'keltner_mid_{period}'] = ema
            indicators[f'keltner_lower_{period}'] = ema - 1.5 * atr

    # Elder Ray: bull_power_N, bear_power_N
    for m in re.finditer(r'(bull|bear)_power_(\d+)', entry_condition):
        period = int(m.group(2))
        if f'bull_power_{period}' not in indicators:
            ema = pl.col('close').ewm_mean(alpha=2/(period+1), min_samples=period)
            indicators[f'bull_power_{period}'] = pl.col('high') - ema
            indicators[f'bear_power_{period}'] = pl.col('low') - ema

    return indicators


def _parse_simple_condition(cond: str):
    """Parse a single comparison like 'close < bb_lower_20' into a Polars boolean expression.
    Supports multiplication: volume > volume_sma_20 * 1.5"""
    for op in ['<=', '>=', '!=', '==', '<', '>']:
        if op in cond:
            parts = cond.split(op, 1)
            left = _parse_value(parts[0].strip())
            right = _parse_expr(parts[1].strip())
            if op == '<=': return left <= right
            if op == '>=': return left >= right
            if op == '!=': return left != right
            if op == '==': return left == right
            if op == '<': return left < right
            if op == '>': return left > right
    return pl.lit(False)


def _parse_expr(val: str):
    """Parse a value or simple expression (with * or /) into a Polars expression."""
    val = val.strip()
    # Handle multiplication: col_name * number
    if '*' in val:
        parts = val.split('*', 1)
        left = _parse_value(parts[0].strip())
        right = _parse_value(parts[1].strip())
        return left * right
    # Handle division: col_name / number
    if '/' in val:
        parts = val.split('/', 1)
        left = _parse_value(parts[0].strip())
        right = _parse_value(parts[1].strip())
        return left / right
    return _parse_value(val)


def _parse_value(val: str):
    """Parse a value reference into a Polars expression."""
    val = val.strip()
    try:
        return pl.lit(float(val))
    except ValueError:
        return pl.col(val)


# ─── Walk-Forward Runner ──────────────────────────────────────────────

def run_wf_on_candidate(name: str, entry: str, exit_config: dict,
                          n_windows: int = 10, oos_pct: float = 0.3,
                          strategy_type: str = "",
                          target_assets: list = None) -> dict:
    """Run Walk-Forward validation for a candidate strategy.
    
    If strategy_type is '4H', data is aggregated to 4h candles.
    target_assets: list of primary assets for V9 target-asset grouping.
        If None, all assets are targets (legacy behavior).
    """
    
    exit_condition = exit_config.get("exit_condition", None) if exit_config else None
    strategy_func, parseable = build_strategy_func(entry, exit_condition=exit_condition)
    
    if not parseable or strategy_func is None:
        return {
            "name": name,
            "entry": entry,
            "exit_config": exit_config,
            "robustness_score": 0.0,
            "passed": False,
            "profitable_assets": "0/0",
            "avg_oos_return": 0.0,
            "avg_trades": 0.0,
            "assets": {},
            "n_windows": n_windows,
            "timestamp": datetime.now().isoformat(),
            "wf_status": "NEEDS_MANUAL_REVIEW",
            "wf_reason": f"DSL parser cannot handle: {entry[:80]}",
            "is_score": 0.0,
            "tier": "needs_review",
        }
    
    results = {}
    
    for asset in ASSETS:
        symbol = f"{asset}USDT"
        try:
            df = load_asset_data(symbol)
        except FileNotFoundError:
            continue
        
        # Aggregate to 4h if this is a 4h strategy
        if strategy_type == "4H":
            df = aggregate_to_4h(df)
        
        timeframe = "4h" if strategy_type == "4H" else "1h"
        
        n_rows = len(df)
        window_size = n_rows // n_windows
        
        oos_metrics = []
        for i in range(n_windows):
            start = i * window_size
            end = min(start + window_size, n_rows)
            train_end = start + int(window_size * (1 - oos_pct))
            
            oos_df = df[train_end:end]
            if len(oos_df) < 50:
                continue
            
            engine = BacktestEngine(data_path=str(DATA_DIR))
            result = engine.run(
                strategy_name=f"WF_{name}",
                strategy_func=strategy_func,
                params={},
                symbol=symbol,
                timeframe=timeframe,
                exit_config=exit_config,
                df=oos_df,
            )
            
            oos_metrics.append({
                "window": i + 1,
                "net_return": round(result.net_return, 4),
                "trade_count": result.trade_count,
                "max_drawdown": round(result.max_drawdown, 4),
            })
        
        if oos_metrics:
            profitable_windows = sum(1 for m in oos_metrics if m["net_return"] > 0)
            avg_return = np.mean([m["net_return"] for m in oos_metrics])
            avg_trades = np.mean([m["trade_count"] for m in oos_metrics])
            avg_dd = np.mean([m["max_drawdown"] for m in oos_metrics])
            results[asset] = {
                "avg_oos_return": round(avg_return, 4),
                "avg_trades": round(avg_trades, 1),
                "avg_drawdown": round(avg_dd, 4),
                "profitable_windows": f"{profitable_windows}/{len(oos_metrics)}",
                "windows": oos_metrics,
            }
    
    # Overall scoring
    assets_with_data = len(results)
    profitable_assets = sum(1 for r in results.values() if r["avg_oos_return"] > 0)
    avg_all_return = np.mean([r["avg_oos_return"] for r in results.values()]) if results else 0
    avg_all_trades = np.mean([r["avg_trades"] for r in results.values()]) if results else 0

    # V9 Scoring: Target-asset aware
    #
    # If target_assets specified, scoring focuses on those assets.
    # MR strategies target DOGE/ADA/AVAX; non-MR target all 6.
    #
    # Components:
    #   1. OOS Return (40%) — did we actually make money?
    #   2. Profitable Ratio (30%) — how consistent across assets?
    #   3. Trade Floor (30%) — enough trades for statistical validity?

    if target_assets:
        target_results = {k: v for k, v in results.items() if k in target_assets}
        bonus_results = {k: v for k, v in results.items() if k not in target_assets}
        
        if target_results:
            target_profitable = sum(1 for r in target_results.values() if r["avg_oos_return"] > 0)
            target_assets_count = len(target_results)
            target_avg_return = np.mean([r["avg_oos_return"] for r in target_results.values()])
            target_avg_trades = np.mean([r["avg_trades"] for r in target_results.values()])
            target_profitable_ratio = target_profitable / target_assets_count
        else:
            target_profitable = 0
            target_assets_count = 0
            target_avg_return = 0
            target_avg_trades = 0
            target_profitable_ratio = 0
        
        # Use target-asset metrics for scoring
        profitable_ratio = target_profitable_ratio
        avg_all_return = target_avg_return
        avg_all_trades = target_avg_trades
        
        # For reporting, show target + bonus
        target_profitable_str = f"{target_profitable}/{target_assets_count}"
    else:
        profitable_ratio = profitable_assets / assets_with_data if assets_with_data > 0 else 0
        target_profitable_str = f"{profitable_assets}/{assets_with_data}"

    # Component 1: OOS Return score (map -2%..+1% → 0..20)
    return_score = max(0, min(20, (avg_all_return + 2) / 3 * 20))

    # Component 2: Profitable Ratio score (0..1 → 0..30)
    consistency_score = profitable_ratio * 30

    # Component 3: Trade floor (≥3 trades/window → full 30, else scaled down)
    trade_score = min(30, avg_all_trades / 3 * 30) if avg_all_trades > 0 else 0

    robustness = round(min(100, return_score + consistency_score + trade_score), 1)

    # V9 PASS criteria: target-asset aware
    if target_assets and target_results:
        n_target = len(target_assets)
        min_profitable = 2 if n_target == 3 else max(3, n_target // 2)
        passed = (robustness >= 40
                  and target_profitable >= min_profitable
                  and target_avg_trades >= 3
                  and target_avg_return > 0)
    else:
        # Legacy pass criteria
        passed = (robustness >= 40
                  and profitable_assets >= 3
                  and avg_all_trades >= 2
                  and avg_all_return > 0)
    wf_status = "PASS" if passed else "FAIL"

    return {
        "name": name,
        "entry": entry,
        "exit_config": exit_config,
        "robustness_score": robustness,
        "passed": passed,
        "profitable_assets": target_profitable_str if target_assets else f"{profitable_assets}/{assets_with_data}",
        "avg_oos_return": round(avg_all_return, 4),
        "avg_trades": round(avg_all_trades, 1),
        "assets": results,
        "target_assets": target_assets,
        "n_windows": n_windows,
        "timestamp": datetime.now().isoformat(),
        "wf_status": wf_status,
        "is_score": 0.0,
        "tier": "overfitted",
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Walk-Forward Gate for Strategy Candidates")
    parser.add_argument("--candidate", help="JSON string or file with {name, entry, exit_config}")
    parser.add_argument("--hof", help="JSON file with hall_of_fame to validate")
    parser.add_argument("--windows", type=int, default=10, help="Number of WF windows")
    args = parser.parse_args()
    
    if args.candidate:
        if Path(args.candidate).exists():
            with open(args.candidate) as f:
                c = json.load(f)
        else:
            c = json.loads(args.candidate)
        
        result = run_wf_on_candidate(
            c["name"],
            c.get("entry", c.get("entry_condition", "")),
            c.get("exit_config", c.get("exit_rule", {})),
            n_windows=args.windows,
        )
        if "is_score" not in result:
            result["is_score"] = c.get("score", 0)
        print(json.dumps(result, indent=2, default=str))
    
    elif args.hof:
        with open(args.hof) as f:
            data = json.load(f)
        
        hof = data.get("hall_of_fame", data if isinstance(data, list) else [])
        
        V17 = {
            "name": "V17_Mid_Target_Exit",
            "entry_condition": "close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200",
            "exit_config": {"trailing_stop_pct": 1.5, "stop_loss_pct": 3.0, "max_hold_bars": 36},
            "score": 4.88,
        }
        
        v17_in_hof = any(e.get("name") == "V17_Mid_Target_Exit" for e in hof)
        if not v17_in_hof:
            hof.insert(0, V17)
        
        results = []
        for entry in hof:
            is_score = entry.get("score", 0)
            print(f"\nValidating: {entry['name']} (IS-Score: {is_score})")
            result = run_wf_on_candidate(
                entry["name"],
                entry.get("entry", entry.get("entry_condition", "")),
                entry.get("exit_config", entry.get("exit_rule", {})),
                n_windows=args.windows,
            )
            result["is_score"] = is_score
            if result.get("wf_status") == "NEEDS_MANUAL_REVIEW":
                result["tier"] = "needs_review"
            elif result["passed"]:
                result["tier"] = "wf_passed"
            else:
                result["tier"] = "overfitted"
            
            tier = result["tier"]
            status = "PASS" if result["passed"] else ("REVIEW" if result.get("wf_status") == "NEEDS_MANUAL_REVIEW" else "FAIL")
            print(f"  {status} [{tier.upper()}] Robustness: {result['robustness_score']}/100 "
                  f"(OOS: {result['avg_oos_return']:+.2f}%, {result['profitable_assets']} profitable)")
            results.append(result)
        
        wf_passed = sorted(
            [r for r in results if r["passed"]],
            key=lambda r: r["robustness_score"], reverse=True
        )
        if len(wf_passed) >= 1:
            wf_passed[0]["tier"] = "champion"
            for r in wf_passed[1:]:
                r["tier"] = "robust"
        needs_review = [r for r in results if r.get("wf_status") == "NEEDS_MANUAL_REVIEW"]
        overfitted = [r for r in results if not r["passed"] and r.get("wf_status") != "NEEDS_MANUAL_REVIEW"]
        
        print(f"\n{'='*50}")
        print(f"WF GATE SUMMARY: {len(wf_passed)}/{len(results)} passed")
        if needs_review:
            print(f"NEEDS MANUAL REVIEW: {len(needs_review)}")
        if wf_passed:
            print(f"CHAMPION: {wf_passed[0]['name']} WF={wf_passed[0]['robustness_score']}/100")
        else:
            print(f"No WF-passed candidates.")
        
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = OUTPUT_DIR / f"wf_gate_{timestamp}.json"
        with open(out_file, 'w') as f:
            json.dump({"timestamp": timestamp, "results": results}, f, indent=2, default=str)
        print(f"Saved to {out_file}")
    else:
        parser.print_help()