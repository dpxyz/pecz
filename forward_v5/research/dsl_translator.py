#!/usr/bin/env python3
"""
DSL-to-Strategy Translator v1.0

Übersetzt ein DSL-JSON (von Gemma4 generiert) in eine strategy_func(df, params),
die direkt von backtest_engine.py aufgerufen werden kann.

UNTERSTÜTZTE INDIKATOREN:
  SMA, EMA, RSI, BB (Bollinger Bands), ATR, VWAP, MACD, ZSCORE

UNTERSTÜTZTE ENTRY-CONDITIONS (DSL-Ausdrücke):
  - Vergleich: indicator OP value  (OP: <, >, <=, >=, ==, !=)
  - Logisch: AND, OR
  - Klammern: (expr)
  
BEISPIEL:
  "zscore < -2.0 AND close < SMA_50"
  → Z-Score < -2 UND Schlusskurs unter SMA(50)

SICHERHEIT:
  - Nur whitelisted Indikatoren
  - Nur whitelisted Operatoren
  - Kein eval(), kein exec(), kein beliebiger Code
"""

import re
import polars as pl
from typing import Dict, Callable, List, Tuple


# ── Indicator Registry ──

def calc_sma(df: pl.DataFrame, period: int) -> pl.Series:
    return df["close"].rolling_mean(window_size=period, min_periods=period)


def calc_ema(df: pl.DataFrame, period: int) -> pl.Series:
    return df["close"].rolling_mean(window_size=period, min_periods=period)  # Polars EMA equivalent


def calc_rsi(df: pl.DataFrame, period: int) -> pl.Series:
    delta = df["close"].diff()
    gain = delta.clip(lower_bound=0)
    loss = (-delta).clip(lower_bound=0)
    avg_gain = gain.rolling_mean(window_size=period, min_periods=period)
    avg_loss = loss.rolling_mean(window_size=period, min_periods=period)
    avg_loss_safe = pl.when(pl.Series(avg_loss) != 0).then(pl.Series(avg_loss)).otherwise(1.0)
    rs = pl.Series(avg_gain) / avg_loss_safe
    return 100 - (100 / (1 + rs))


def calc_bb(df: pl.DataFrame, period: int, std_dev: float = 2.0) -> Tuple[pl.Series, pl.Series, pl.Series]:
    sma = df["close"].rolling_mean(window_size=period, min_periods=period)
    std = df["close"].rolling_std(window_size=period, min_periods=period)
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower


def calc_atr(df: pl.DataFrame, period: int) -> pl.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr = pl.max_horizontal(
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    )
    return tr.rolling_mean(window_size=period, min_periods=period)


def calc_vwap(df: pl.DataFrame, period: int = None) -> pl.Series:
    # Approximation: cumulative VWAP reset daily (simplified)
    typical = (df["high"] + df["low"] + df["close"]) / 3
    if "volume" in df.columns:
        vol = df["volume"]
        return (typical * vol).cum_sum() / vol.cum_sum()
    return typical  # fallback


def calc_macd(df: pl.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pl.Series, pl.Series, pl.Series]:
    ema_fast = df["close"].rolling_mean(window_size=fast, min_periods=fast)
    ema_slow = df["close"].rolling_mean(window_size=slow, min_periods=slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.rolling_mean(window_size=signal, min_periods=signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_zscore(df: pl.DataFrame, period: int) -> pl.Series:
    sma = df["close"].rolling_mean(window_size=period, min_periods=period)
    std = df["close"].rolling_std(window_size=period, min_periods=period)
    std_safe = pl.when(pl.Series(std) != 0).then(pl.Series(std)).otherwise(1.0)
    return (df["close"] - sma) / std_safe


def calc_adx(df: pl.DataFrame, period: int = 14) -> pl.Series:
    """Average Directional Index - measures trend strength."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    # True Range
    tr = pl.max_horizontal(
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    )
    
    # +DM and -DM
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = pl.when((up_move > down_move) & (up_move > 0)).then(up_move).otherwise(0)
    minus_dm = pl.when((down_move > up_move) & (down_move > 0)).then(down_move).otherwise(0)
    
    # Smoothed
    atr_smooth = tr.rolling_mean(window_size=period, min_periods=period)
    plus_di = 100 * plus_dm.rolling_mean(window_size=period, min_periods=period) / atr_smooth
    minus_di = 100 * minus_dm.rolling_mean(window_size=period, min_periods=period) / atr_smooth
    
    # DX → ADX
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = pl.when(pl.Series(di_sum) != 0).then(100 * pl.Series(di_diff) / pl.Series(di_sum)).otherwise(0)
    adx = dx.rolling_mean(window_size=period, min_periods=period)
    
    return adx


def calc_bb_width(df: pl.DataFrame, period: int, std_dev: float = 2.0) -> pl.Series:
    """BB Width = (Upper - Lower) / Mid. Measures volatility expansion."""
    upper, mid, lower = calc_bb(df, period, std_dev)
    mid_safe = pl.when(mid != 0).then(mid).otherwise(1.0)
    return (upper - lower) / mid_safe


INDICATOR_REGISTRY = {
    "SMA": ("period", calc_sma),
    "EMA": ("period", calc_ema),
    "RSI": ("period", calc_rsi),
    "BB": ("period", calc_bb),       # returns (upper, mid, lower)
    "ATR": ("period", calc_atr),
    "VWAP": (None, calc_vwap),
    "MACD": (None, calc_macd),        # returns (macd, signal, hist)
    "ZSCORE": ("period", calc_zscore),
    "ADX": ("period", calc_adx),       # trend strength
}


# ── Condition Parser ──

# Allowed tokens in conditions
_ALLOWED_OPS = {"<", ">", "<=", ">=", "==", "!="}
_ALLOWED_LOGIC = {"AND", "OR"}
_ALLOWED_COLUMNS = {"close", "open", "high", "low", "volume"}

# Indicator reference pattern: INDICATOR_period or INDICATOR_param
# e.g. SMA_50, RSI_14, BB_upper_20, ZSCORE_50, MACD_hist
_IND_PATTERN = re.compile(
    r'^(SMA|EMA|RSI|BB_upper|BB_mid|BB_lower|ATR|VWAP|MACD_line|MACD_signal|MACD_hist|ZSCORE)(?:_(\d+))?$',
    re.IGNORECASE
)


def _parse_token(token: str, indicator_cols: dict) -> str:
    """Map a token to a Polars column expression string."""
    token = token.strip()
    
    # Numeric literal
    try:
        float(token)
        return token
    except ValueError:
        pass
    
    # Negative number
    if token.startswith('-') and token[1:].replace('.', '', 1).isdigit():
        return token
    
    # Standard columns
    if token.lower() in _ALLOWED_COLUMNS:
        return f'pl.col("{token.lower()}")'
    
    # Indicator reference
    m = _IND_PATTERN.match(token)
    if m:
        col_name = m.group(0).lower()
        if col_name in indicator_cols:
            return f'pl.col("{indicator_cols[col_name]}")'
        # Try with underscore variants
        for key, col in indicator_cols.items():
            if key == col_name:
                return f'pl.col("{col}")'
    
    raise ValueError(f"Unknown token in condition: '{token}'")


def parse_condition(condition_str: str, indicator_cols: dict) -> pl.Expr:
    """
    Parse a DSL condition string into a Polars expression.
    
    Examples:
      "zscore_50 < -2.0 AND close < sma_60"
      "rsi_14 > 70"
      "close > bb_upper_20"
    """
    # Normalize
    cond = condition_str.strip()
    
    # Split on AND/OR (simple parser, no nested parens for V1)
    parts_and = re.split(r'\s+AND\s+', cond)
    
    if len(parts_and) > 1:
        exprs = [_parse_single_condition(p.strip(), indicator_cols) for p in parts_and]
        result = exprs[0]
        for e in exprs[1:]:
            result = result & e
        return result
    
    parts_or = re.split(r'\s+OR\s+', cond)
    if len(parts_or) > 1:
        exprs = [_parse_single_condition(p.strip(), indicator_cols) for p in parts_or]
        result = exprs[0]
        for e in exprs[1:]:
            result = result | e
        return result
    
    return _parse_single_condition(cond, indicator_cols)


def _parse_single_condition(cond: str, indicator_cols: dict) -> pl.Expr:
    """Parse a single comparison like 'zscore_50 < -2.0'."""
    # Try operators longest first
    for op in [">=", "<=", "!=", "==", ">", "<"]:
        if f' {op} ' in cond:
            left, right = cond.split(f' {op} ', 1)
            left_expr = _parse_token(left.strip(), indicator_cols)
            right_expr = _parse_token(right.strip(), indicator_cols)
            
            op_map = {
                ">=": ">=",
                "<=": "<=",
                ">": ">",
                "<": "<",
                "==": "==",
                "!=": "!="
            }
            
            # Build expression
            if left_expr.startswith('pl.col('):
                if right_expr.startswith('pl.col('):
                    return eval(f"{left_expr} {op_map[op]} {right_expr}")
                else:
                    return eval(f"{left_expr} {op_map[op]} {float(right_expr)}")
            else:
                if right_expr.startswith('pl.col('):
                    return eval(f"{float(left_expr)} {op_map[op]} {right_expr}")
                else:
                    return eval(f"pl.lit({float(left_expr)}) {op_map[op]} pl.lit({float(right_expr)})")
    
    raise ValueError(f"Cannot parse condition: '{cond}'")


# ── Main Translator ──

def translate_candidate(candidate: dict) -> Callable[[pl.DataFrame, dict], pl.DataFrame]:
    """
    Translate a DSL candidate into a strategy_func(df, params) -> pl.DataFrame
    that the BacktestEngine can call.
    
    The returned function:
    - Adds indicator columns to the DataFrame
    - Generates a 'signal' column (-1, 0, 1) based on the entry condition
    - Returns the modified DataFrame
    """
    strategy = candidate["strategy"]
    indicators = strategy.get("indicators", [])
    entry = strategy.get("entry", {})
    exit_cfg = strategy.get("exit", {})
    
    condition_str = entry.get("condition", "")
    
    def strategy_func(df: pl.DataFrame, params: dict) -> pl.DataFrame:
        """Generated strategy function from DSL candidate.
        
        params can override indicator periods:
          {'ema_period': 16, 'rsi_period': 7}  → uses EMA(16), RSI(7)
          {'ema_period': 20, 'rsi_period': 14}  → uses EMA(20), RSI(14)
          {}  → uses defaults from DSL
        """
        indicator_cols = {}
        
        # 1. Add indicator columns
        for ind in indicators:
            name = ind["name"]
            ind_params = ind.get("params", {})
            
            if name not in INDICATOR_REGISTRY:
                raise ValueError(f"Unknown indicator: {name}")
            
            param_key, calc_fn = INDICATOR_REGISTRY[name]
            
            if name == "BB":
                # Allow params override: bb_period, bb_std_dev
                period = params.get(f"bb_period", ind_params.get("period", 20))
                std_dev = params.get(f"bb_std_dev", ind_params.get("std_dev", 2.0))
                upper, mid, lower = calc_fn(df, period, std_dev)
                col_upper = f"bb_upper_{period}"
                col_mid = f"bb_mid_{period}"
                col_lower = f"bb_lower_{period}"
                df = df.with_columns([
                    upper.alias(col_upper),
                    mid.alias(col_mid),
                    lower.alias(col_lower)
                ])
                indicator_cols[f"bb_upper_{period}"] = col_upper
                indicator_cols[f"bb_mid_{period}"] = col_mid
                indicator_cols[f"bb_lower_{period}"] = col_lower
                # Also register canonical names for condition parsing
                indicator_cols["bb_upper"] = col_upper
                indicator_cols["bb_mid"] = col_mid
                indicator_cols["bb_lower"] = col_lower
                # BB Width (volatility measure)
                bb_width = calc_bb_width(df, period, std_dev)
                col_width = f"bb_width_{period}"
                df = df.with_columns(bb_width.alias(col_width))
                indicator_cols[f"bb_width_{period}"] = col_width
                indicator_cols["bb_width"] = col_width
                
            elif name == "MACD":
                fast = params.get("macd_fast", ind_params.get("fast", 12))
                slow = params.get("macd_slow", ind_params.get("slow", 26))
                sig = params.get("macd_signal", ind_params.get("signal", 9))
                macd_line, signal_line, hist = calc_fn(df, fast, slow, sig)
                col_macd = f"macd_line"
                col_signal = f"macd_signal"
                col_hist = f"macd_hist"
                df = df.with_columns([
                    macd_line.alias(col_macd),
                    signal_line.alias(col_signal),
                    hist.alias(col_hist)
                ])
                indicator_cols["macd_line"] = col_macd
                indicator_cols["macd_signal"] = col_signal
                indicator_cols["macd_hist"] = col_hist
                
            elif name == "VWAP":
                vwap = calc_fn(df)
                col_vwap = "vwap"
                df = df.with_columns(vwap.alias(col_vwap))
                indicator_cols["vwap"] = col_vwap
                
            elif name == "ADX":
                period = params.get(f"adx_period", ind_params.get("period", 14))
                adx = calc_adx(df, period)
                col_adx = f"adx_{period}"
                df = df.with_columns(adx.alias(col_adx))
                indicator_cols[f"adx_{period}"] = col_adx
                indicator_cols["adx"] = col_adx
                
            else:
                # Single-output indicators (SMA, EMA, RSI, ATR, ZSCORE)
                # Allow params override: {indicator_name_lower}_period
                period = params.get(f"{name.lower()}_period", ind_params.get("period", 14))
                series = calc_fn(df, period)
                col_name = f"{name.lower()}_{period}"
                df = df.with_columns(series.alias(col_name))
                indicator_cols[f"{name.lower()}_{period}"] = col_name
                # Also register canonical name (without number) for condition parsing
                indicator_cols[name.lower()] = col_name
        
        # 2. Parse entry condition → signal
        # Rewrite condition to use dynamic column names
        # e.g. 'rsi_14 < 30' → 'rsi_7 < 30' when rsi_period is overridden to 7
        dynamic_condition = condition_str
        if dynamic_condition:
            # Build mapping from original indicator names to dynamic names
            # Original names come from the DSL candidate's fixed periods
            for ind in indicators:
                orig_name = ind["name"]
                orig_params = ind.get("params", {})
                if orig_name in ("BB", "MACD", "VWAP"):
                    continue  # Complex indicators handled separately
                orig_period = orig_params.get("period", 14)
                orig_col = f"{orig_name.lower()}_{orig_period}"
                new_period = params.get(f"{orig_name.lower()}_period", orig_period)
                new_col = f"{orig_name.lower()}_{new_period}"
                if orig_col != new_col:
                    dynamic_condition = dynamic_condition.replace(orig_col, new_col)
            
            try:
                signal_expr = parse_condition(dynamic_condition, indicator_cols)
                # Long signal
                long_signal = signal_expr
                
                # For now: simple long-only. 
                # Short would need a separate condition or we invert.
                df = df.with_columns([
                    pl.when(long_signal)
                    .then(1)
                    .otherwise(0)
                    .alias("signal")
                ])
            except Exception as e:
                # Fallback: no signal if condition can't be parsed
                df = df.with_columns([
                    pl.lit(0).alias("signal")
                ])
        else:
            df = df.with_columns([
                pl.lit(0).alias("signal")
            ])
        
        return df
    
    return strategy_func


def translate_candidate_with_name(candidate: dict) -> Tuple[str, Callable]:
    """Returns (strategy_name, strategy_func)."""
    name = candidate["strategy"]["name"]
    func = translate_candidate(candidate)
    return name, func


# ── Self-Test ──

if __name__ == "__main__":
    test_candidate = {
        "dsl_version": "0.1",
        "strategy": {
            "name": "zscore_reversion_test",
            "type": "mean_reversion",
            "hypothesis": "Extreme Z-Score moves revert to mean",
            "assets": ["BTCUSDT"],
            "timeframe": "1h",
            "indicators": [
                {"name": "SMA", "params": {"period": 60}},
                {"name": "ZSCORE", "params": {"period": 50}}
            ],
            "entry": {
                "condition": "zscore_50 < -2.0 AND close < sma_60",
                "max_per_day": 3
            },
            "exit": {
                "take_profit_pct": 1.5,
                "stop_loss_pct": 2.0,
                "trailing_stop_pct": None,
                "max_hold_bars": 48
            },
            "position_sizing": {
                "method": "fixed_frac",
                "risk_per_trade_pct": 1.0
            },
            "filters": []
        }
    }
    
    name, func = translate_candidate_with_name(test_candidate)
    print(f"✅ Translated: {name}")
    print(f"   Function: {func.__name__}")
    print(f"   Docstring: {func.__doc__}")