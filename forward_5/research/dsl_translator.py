#!/usr/bin/env python3
"""
DSL-to-Strategy Translator v1.0

Übersetzt ein DSL-JSON (von Gemma4 generiert) in eine strategy_func(df, params),
die direkt von backtest_engine.py aufgerufen werden kann.

UNTERSTÜTZTE INDIKATOREN:
  SMA, EMA, RSI, BB (Bollinger Bands), ATR, VWAP, MACD, ZSCORE, ADX

UNTERSTÜTZTE ENTRY-CONDITIONS (DSL-Ausdrücke):
  - Vergleich: indicator OP value  (OP: <, >, <=, >=, ==, !=)
  - Logisch: AND, OR
  - Klammern: (expr)
"""

import re
import polars as pl
from typing import Dict, Callable, List, Tuple


# ── Indicator Registry ──

def calc_sma(df: pl.DataFrame, period: int) -> pl.Series:
    return df["close"].rolling_mean(window_size=period, min_periods=period)


def calc_ema(df: pl.DataFrame, period: int) -> pl.Series:
    return df["close"].ewm_mean(alpha=2/(period+1), min_samples=period)


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
    typical = (df["high"] + df["low"] + df["close"]) / 3
    if "volume" in df.columns:
        vol = df["volume"]
        return (typical * vol).cum_sum() / vol.cum_sum()
    return typical


def calc_macd(df: pl.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pl.Series, pl.Series, pl.Series]:
    ema_fast = df["close"].ewm_mean(alpha=2/(fast+1), min_samples=fast)
    ema_slow = df["close"].ewm_mean(alpha=2/(slow+1), min_samples=slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm_mean(alpha=2/(signal+1), min_samples=signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_zscore(df: pl.DataFrame, period: int) -> pl.Series:
    sma = df["close"].rolling_mean(window_size=period, min_periods=period)
    std = df["close"].rolling_std(window_size=period, min_periods=period)
    std_safe = pl.when(pl.Series(std) != 0).then(pl.Series(std)).otherwise(1.0)
    return (df["close"] - sma) / std_safe


def calc_adx(df: pl.DataFrame, period: int = 14) -> pl.Series:
    high = pl.col("high")
    low = pl.col("low")
    close = pl.col("close")
    
    tr = pl.max_horizontal(
        (high - low),
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    )
    
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = pl.when((up_move > down_move) & (up_move > 0)).then(up_move).otherwise(0)
    minus_dm = pl.when((down_move > up_move) & (down_move > 0)).then(down_move).otherwise(0)
    
    atr_smooth = tr.rolling_mean(window_size=period, min_periods=period)
    plus_dm_smooth = plus_dm.rolling_mean(window_size=period, min_periods=period)
    minus_dm_smooth = minus_dm.rolling_mean(window_size=period, min_periods=period)
    
    plus_di = pl.when(atr_smooth != 0).then(100 * plus_dm_smooth / atr_smooth).otherwise(0)
    minus_di = pl.when(atr_smooth != 0).then(100 * minus_dm_smooth / atr_smooth).otherwise(0)
    
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = pl.when(di_sum != 0).then(100 * di_diff / di_sum).otherwise(0)
    adx = dx.rolling_mean(window_size=period, min_periods=period)
    
    result = df.select(adx.alias("adx"))
    return result["adx"]


def calc_bb_width(df: pl.DataFrame, period: int, std_dev: float = 2.0) -> pl.Series:
    upper, mid, lower = calc_bb(df, period, std_dev)
    mid_safe = pl.when(mid != 0).then(mid).otherwise(1.0)
    return (upper - lower) / mid_safe


def calc_stoch(df: pl.DataFrame, period: int = 14) -> Tuple[pl.Series, pl.Series]:
    """Stochastic Oscillator %K and %D."""
    low_min = pl.col("low").rolling_min(window_size=period, min_periods=period)
    high_max = pl.col("high").rolling_max(window_size=period, min_periods=period)
    denom = high_max - low_min
    denom_safe = pl.when(denom != 0).then(denom).otherwise(1.0)
    k = 100 * (pl.col("close") - low_min) / denom_safe
    d = k.rolling_mean(window_size=3, min_periods=3)
    result = df.select([k.alias("stoch_k"), d.alias("stoch_d")])
    return result["stoch_k"], result["stoch_d"]


def calc_williams_r(df: pl.DataFrame, period: int = 14) -> pl.Series:
    """Williams %R."""
    high_max = pl.col("high").rolling_max(window_size=period, min_periods=period)
    low_min = pl.col("low").rolling_min(window_size=period, min_periods=period)
    denom = high_max - low_min
    denom_safe = pl.when(denom != 0).then(denom).otherwise(1.0)
    wr = -100 * (high_max - pl.col("close")) / denom_safe
    result = df.select(wr.alias("williams_r"))
    return result["williams_r"]


def calc_ema_slope(df: pl.DataFrame, period: int = 50) -> pl.Series:
    """EMA slope: (EMA[t] - EMA[t-1]) / EMA[t-1] * 100 (percent change)."""
    ema = pl.col("close").ewm_mean(alpha=2/(period+1), min_samples=period)
    ema_shifted = ema.shift(1)
    ema_safe = pl.when(ema_shifted != 0).then(ema_shifted).otherwise(1.0)
    slope = (ema - ema_shifted) / ema_safe * 100
    result = df.select(slope.alias("ema_slope"))
    return result["ema_slope"].fill_null(0)


def calc_mfi(df: pl.DataFrame, period: int = 14) -> pl.Series:
    """Money Flow Index — volume-weighted RSI."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    raw_mf = typical * df["volume"]
    delta_typ = typical.diff()
    pos_mf = pl.when(delta_typ > 0).then(raw_mf).otherwise(0)
    neg_mf = pl.when(delta_typ < 0).then(raw_mf).otherwise(0)
    pos_flow = pos_mf.rolling_mean(window_size=period, min_periods=period)
    neg_flow = neg_mf.rolling_mean(window_size=period, min_periods=period)
    neg_safe = pl.when(neg_flow != 0).then(neg_flow).otherwise(1.0)
    mfi = 100 - (100 / (1 + pos_flow / neg_safe))
    result = df.select(mfi.alias("mfi"))
    return result["mfi"].fill_null(50)


def calc_cmf(df: pl.DataFrame, period: int = 20) -> pl.Series:
    """Chaikin Money Flow — buying/selling pressure."""
    high = pl.col("high")
    low = pl.col("low")
    close = pl.col("close")
    vol = pl.col("volume")
    denom = high - low
    denom_safe = pl.when(denom != 0).then(denom).otherwise(1.0)
    clv = ((close - low) - (high - close)) / denom_safe
    mf_vol = clv * vol
    cmf = mf_vol.rolling_sum(window_size=period, min_periods=period) / \
          vol.rolling_sum(window_size=period, min_periods=period)
    result = df.select(cmf.alias("cmf"))
    return result["cmf"].fill_null(0)


def calc_obv(df: pl.DataFrame, period: int = None) -> pl.Series:
    """On Balance Volume rate of change over N periods."""
    close = pl.col("close")
    vol = pl.col("volume")
    direction = pl.when(close > close.shift(1)).then(1).when(close < close.shift(1)).then(-1).otherwise(0)
    signed_vol = direction * vol
    obv = signed_vol.cum_sum()
    if period is not None and period > 0:
        obv_shifted = obv.shift(period)
        obv_safe = pl.when(obv_shifted != 0).then(obv_shifted).otherwise(1.0)
        obv_roc = (obv - obv_shifted) / obv_safe.abs() * 100
        result = df.select(obv_roc.alias("obv"))
        return result["obv"].fill_null(0)
    result = df.select(obv.alias("obv"))
    return result["obv"]


def calc_elder_ray(df: pl.DataFrame, period: int = 13) -> Tuple[pl.Series, pl.Series]:
    """Elder Ray: Bull Power = High - EMA, Bear Power = Low - EMA."""
    ema = pl.col("close").ewm_mean(alpha=2/(period+1), min_samples=period)
    bull_power = pl.col("high") - ema
    bear_power = pl.col("low") - ema
    result = df.select([bull_power.alias("bull_power"), bear_power.alias("bear_power")])
    return result["bull_power"].fill_null(0), result["bear_power"].fill_null(0)


def calc_keltner(df: pl.DataFrame, period: int = 20, atr_mult: float = 1.5) -> Tuple[pl.Series, pl.Series, pl.Series]:
    """Keltner Channel: EMA ± ATR*multiplier."""
    ema = pl.col("close").ewm_mean(alpha=2/(period+1), min_samples=period)
    # ATR via expressions
    high = pl.col("high")
    low = pl.col("low")
    close = pl.col("close")
    tr = pl.max_horizontal(high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs())
    atr = tr.rolling_mean(window_size=period, min_periods=period)
    upper = ema + atr_mult * atr
    lower = ema - atr_mult * atr
    result = df.select([upper.alias("k_up"), ema.alias("k_mid"), lower.alias("k_low")])
    return result["k_up"], result["k_mid"], result["k_low"]


def calc_cci(df: pl.DataFrame, period: int = 20) -> pl.Series:
    """Commodity Channel Index."""
    typical = (pl.col("high") + pl.col("low") + pl.col("close")) / 3
    sma_t = typical.rolling_mean(window_size=period, min_periods=period)
    mad = (typical - sma_t).abs().rolling_mean(window_size=period, min_periods=period)
    mad_safe = pl.when(mad != 0).then(mad).otherwise(1.0)
    cci = (typical - sma_t) / (0.015 * mad_safe)
    result = df.select(cci.alias("cci"))
    return result["cci"].fill_null(0)


def calc_volume_ratio(df: pl.DataFrame, period: int = 20) -> pl.Series:
    """Current volume / rolling average volume."""
    vol_sma = pl.col("volume").rolling_mean(window_size=period, min_periods=period)
    vol_safe = pl.when(vol_sma != 0).then(vol_sma).otherwise(1.0)
    vr = pl.col("volume") / vol_safe
    result = df.select(vr.alias("volume_ratio"))
    return result["volume_ratio"]


INDICATOR_REGISTRY = {
    "SMA": ("period", calc_sma),
    "EMA": ("period", calc_ema),
    "RSI": ("period", calc_rsi),
    "BB": ("period", calc_bb),
    "ATR": ("period", calc_atr),
    "VWAP": (None, calc_vwap),
    "MACD": (None, calc_macd),
    "ZSCORE": ("period", calc_zscore),
    "ADX": ("period", calc_adx),
    "STOCH": ("period", calc_stoch),
    "WILLIAMS_R": ("period", calc_williams_r),
    "EMA_SLOPE": ("period", calc_ema_slope),
    "MFI": ("period", calc_mfi),
    "CMF": ("period", calc_cmf),
    "OBV": ("period", calc_obv),
    "ELDER_RAY": ("period", calc_elder_ray),
    "KELTNER": ("period", calc_keltner),
    "CCI": ("period", calc_cci),
    "VOLUME_RATIO": ("period", calc_volume_ratio),
}


# ── Condition Parser ──

_ALLOWED_OPS = {"<", ">", "<=", ">=", "==", "!="}
_ALLOWED_LOGIC = {"AND", "OR"}
_ALLOWED_COLUMNS = {"close", "open", "high", "low", "volume"}

_IND_PATTERN = re.compile(
    r'^(SMA|EMA|RSI|BB_upper|BB_mid|BB_lower|ATR|ATR_sma|VWAP|MACD_line|MACD_signal|MACD_hist|ZSCORE|ADX|bb_width|bb_upper|bb_mid|bb_lower|bb_width_\d+|atr_sma|ema|sma|rsi|macd_line|macd_signal|macd_hist|adx|atr|zscore|stoch_k|stoch_d|williams_r|ema_slope|mfi|cmf|obv|bull_power|bear_power|keltner_upper|keltner_mid|keltner_lower|cci|volume_ratio|volume_ratio_\d+)(?:_(\d+))?$',
    re.IGNORECASE
)


def _parse_token(token: str, indicator_cols: dict) -> str:
    token = token.strip()
    
    try:
        float(token)
        return token
    except ValueError:
        pass
    
    if token.startswith('-') and token[1:].replace('.', '', 1).isdigit():
        return token
    
    if token.lower() in _ALLOWED_COLUMNS:
        return f'pl.col("{token.lower()}")'
    
    m = _IND_PATTERN.match(token)
    if m:
        col_name = token.lower()
        if col_name in indicator_cols:
            return f'pl.col("{indicator_cols[col_name]}")'
        for key, col in indicator_cols.items():
            if key == col_name:
                return f'pl.col("{col}")'
    
    raise ValueError(f"Unknown token in condition: '{token}'")


def parse_condition(condition_str: str, indicator_cols: dict) -> pl.Expr:
    cond = condition_str.strip()
    
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
    for op in [">=", "<=", "!=", "==", ">", "<"]:
        if f' {op} ' in cond:
            left, right = cond.split(f' {op} ', 1)
            left_expr = _parse_token(left.strip(), indicator_cols)
            right_expr = _parse_token(right.strip(), indicator_cols)
            
            op_map = {">=": ">=", "<=": "<=", ">": ">", "<": "<", "==": "==", "!=": "!="}
            
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
    strategy = candidate["strategy"]
    indicators = strategy.get("indicators", [])
    entry = strategy.get("entry", {})
    condition_str = entry.get("condition", "")
    
    def strategy_func(df: pl.DataFrame, params: dict) -> pl.DataFrame:
        indicator_cols = {}
        
        for ind in indicators:
            name = ind["name"]
            ind_params = ind.get("params", {})
            
            if name not in INDICATOR_REGISTRY:
                raise ValueError(f"Unknown indicator: {name}")
            
            param_key, calc_fn = INDICATOR_REGISTRY[name]
            
            if name == "BB":
                period = params.get("bb_period", ind_params.get("period", 20))
                std_dev = params.get("bb_std_dev", ind_params.get("std_dev", 2.0))
                upper, mid, lower = calc_fn(df, period, std_dev)
                col_upper = f"bb_upper_{period}"
                col_mid = f"bb_mid_{period}"
                col_lower = f"bb_lower_{period}"
                col_width = f"bb_width_{period}"
                df = df.with_columns([
                    upper.alias(col_upper),
                    mid.alias(col_mid),
                    lower.alias(col_lower),
                    ((upper - lower) / mid).alias(col_width),
                ])
                indicator_cols["bb_upper"] = col_upper
                indicator_cols["bb_mid"] = col_mid
                indicator_cols["bb_lower"] = col_lower
                indicator_cols["bb_width"] = col_width
                indicator_cols[col_upper] = col_upper
                indicator_cols[col_mid] = col_mid
                indicator_cols[col_lower] = col_lower
                indicator_cols[col_width] = col_width
                
            elif name == "MACD":
                fast = ind_params.get("fast", 12)
                slow = ind_params.get("slow", 26)
                signal = ind_params.get("signal", 9)
                macd_line, signal_line, histogram = calc_fn(df, fast, slow, signal)
                df = df.with_columns([
                    macd_line.alias("macd_line"),
                    signal_line.alias("macd_signal"),
                    histogram.alias("macd_hist"),
                ])
                indicator_cols["macd_line"] = "macd_line"
                indicator_cols["macd_signal"] = "macd_signal"
                indicator_cols["macd_hist"] = "macd_hist"
                
            elif name == "VWAP":
                series = calc_fn(df)
                df = df.with_columns(series.alias("vwap"))
                indicator_cols["vwap"] = "vwap"
                
            elif name == "ADX":
                period = params.get("adx_period", ind_params.get("period", 14))
                series = calc_fn(df, period)
                col_name = f"adx_{period}"
                df = df.with_columns(series.alias(col_name))
                indicator_cols["adx"] = col_name
                indicator_cols[col_name] = col_name
                
            elif name == "STOCH":
                period = params.get("stoch_period", ind_params.get("period", 14))
                k, d = calc_fn(df, period)
                col_k = f"stoch_k_{period}"
                col_d = f"stoch_d_{period}"
                df = df.with_columns([k.alias(col_k), d.alias(col_d)])
                indicator_cols["stoch_k"] = col_k
                indicator_cols["stoch_d"] = col_d
                indicator_cols[col_k] = col_k
                indicator_cols[col_d] = col_d
                
            elif name == "ELDER_RAY":
                period = params.get("elder_ray_period", ind_params.get("period", 13))
                bull, bear = calc_fn(df, period)
                col_bull = f"bull_power_{period}"
                col_bear = f"bear_power_{period}"
                df = df.with_columns([bull.alias(col_bull), bear.alias(col_bear)])
                indicator_cols["bull_power"] = col_bull
                indicator_cols["bear_power"] = col_bear
                indicator_cols[col_bull] = col_bull
                indicator_cols[col_bear] = col_bear
                
            elif name == "KELTNER":
                period = params.get("keltner_period", ind_params.get("period", 20))
                atr_mult = params.get("keltner_atr_mult", ind_params.get("atr_mult", 1.5))
                upper, mid, lower = calc_fn(df, period, atr_mult)
                col_upper = f"keltner_upper_{period}"
                col_mid = f"keltner_mid_{period}"
                col_lower = f"keltner_lower_{period}"
                df = df.with_columns([upper.alias(col_upper), mid.alias(col_mid), lower.alias(col_lower)])
                indicator_cols["keltner_upper"] = col_upper
                indicator_cols["keltner_mid"] = col_mid
                indicator_cols["keltner_lower"] = col_lower
                indicator_cols[col_upper] = col_upper
                indicator_cols[col_mid] = col_mid
                indicator_cols[col_lower] = col_lower
                
            elif name == "OBV":
                period = params.get("obv_period", ind_params.get("period", 20))
                series = calc_fn(df, period)
                col_name = f"obv_{period}"
                df = df.with_columns(series.alias(col_name))
                indicator_cols["obv"] = col_name
                indicator_cols[col_name] = col_name
                
            else:
                period = params.get(f"{name.lower()}_period", ind_params.get("period", 14))
                series = calc_fn(df, period)
                col_name = f"{name.lower()}_{period}"
                df = df.with_columns(series.alias(col_name))
                indicator_cols[f"{name.lower()}"] = col_name
                indicator_cols[col_name] = col_name
        
        # Parse entry condition → signal
        dynamic_condition = condition_str
        if dynamic_condition:
            for ind in indicators:
                orig_name = ind["name"]
                orig_params = ind.get("params", {})
                if orig_name in ("BB", "MACD", "VWAP"):
                    continue
                orig_period = orig_params.get("period", 14)
                orig_col = f"{orig_name.lower()}_{orig_period}"
                new_period = params.get(f"{orig_name.lower()}_period", orig_period)
                new_col = f"{orig_name.lower()}_{new_period}"
                if orig_col != new_col:
                    dynamic_condition = dynamic_condition.replace(orig_col, new_col)
            
            try:
                signal_expr = parse_condition(dynamic_condition, indicator_cols)
                df = df.with_columns([
                    pl.when(signal_expr).then(1).otherwise(0).alias("signal")
                ])
            except Exception:
                df = df.with_columns([pl.lit(0).alias("signal")])
        else:
            df = df.with_columns([pl.lit(0).alias("signal")])
        
        return df
    
    return strategy_func


def translate_candidate_with_name(candidate: dict) -> Tuple[str, Callable]:
    name = candidate["strategy"]["name"]
    func = translate_candidate(candidate)
    return name, func


if __name__ == "__main__":
    test_candidate = {
        "dsl_version": "0.1",
        "strategy": {
            "name": "test_strategy",
            "type": "mean_reversion",
            "indicators": [
                {"name": "EMA", "params": {"period": 200}},
                {"name": "RSI", "params": {"period": 14}},
                {"name": "BB", "params": {"period": 20, "std_dev": 2.0}},
            ],
            "entry": {"condition": "close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200"},
            "exit": {"trailing_stop_pct": 1.5, "stop_loss_pct": 3.0, "max_hold_bars": 36},
        }
    }
    
    name, func = translate_candidate_with_name(test_candidate)
    print(f"✅ Translated: {name}")