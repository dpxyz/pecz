#!/usr/bin/env python3
"""
Strategy: Mean_Reversion_BB V17 — Hall of Fame Champion

Entry:  close < bb_lower_20 AND rsi_14 < 30 AND close > ema_200
Exit:   trailing_stop 1.5%, stop_loss 3.0%, max_hold 36 bars

Discovered by Evolution V3 (2026-04-24)
Score: 4.88 | 5/6 assets profitable | Avg R +3.88% | DD 3.6-7.3% | CL max 7
"""

import polars as pl


def mean_reversion_bb_strategy(df: pl.DataFrame, params: dict) -> pl.DataFrame:
    """
    Mean Reversion BB V17 Strategy

    Parameters:
    -----------
    bb_period : int
        Bollinger Band period (default: 20)
    bb_std : float
        Bollinger Band std dev multiplier (default: 2.0)
    rsi_period : int
        RSI period (default: 14)
    rsi_threshold : float
        RSI oversold threshold (default: 30)
    ema_period : int
        EMA trend filter period (default: 200)
    """
    bb_period = params.get('bb_period', 20)
    bb_std = params.get('bb_std', 2.0)
    rsi_period = params.get('rsi_period', 14)
    rsi_threshold = params.get('rsi_threshold', 30)
    ema_period = params.get('ema_period', 200)

    # Bollinger Bands
    sma = pl.col('close').rolling_mean(window_size=bb_period, min_periods=bb_period)
    std = pl.col('close').rolling_std(window_size=bb_period, min_periods=bb_period)
    bb_upper = sma + bb_std * std
    bb_lower = sma - bb_std * std

    # RSI
    delta = pl.col('close').diff()
    gain = pl.when(delta > 0).then(delta).otherwise(0.0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
    avg_gain = gain.rolling_mean(window_size=rsi_period, min_periods=rsi_period)
    avg_loss = loss.rolling_mean(window_size=rsi_period, min_periods=rsi_period)
    rs = avg_gain / pl.when(avg_loss == 0).then(0.0001).otherwise(avg_loss)
    rsi = 100 - (100 / (1 + rs))

    # EMA (approximated as rolling mean for simplicity)
    ema = pl.col('close').rolling_mean(window_size=ema_period, min_periods=ema_period)

    # Signal: LONG when price below lower BB, RSI oversold, and above EMA200
    df = df.with_columns([
        bb_upper.alias('bb_upper'),
        bb_lower.alias('bb_lower'),
        rsi.alias('rsi'),
        ema.alias('ema'),
        pl.when(
            (pl.col('close') < bb_lower) &
            (rsi < rsi_threshold) &
            (pl.col('close') > ema)
        )
        .then(1)
        .otherwise(0)
        .alias('signal')
    ])

    return df


# Interface for BacktestEngine
strategy_func = mean_reversion_bb_strategy


def get_default_params() -> dict:
    """V17 Champion Parameters"""
    return {
        'bb_period': 20,
        'bb_std': 2.0,
        'rsi_period': 14,
        'rsi_threshold': 30,
        'ema_period': 200,
    }


def get_v17_exit_config() -> dict:
    """V17 Exit Configuration"""
    return {
        'trailing_stop_pct': 1.5,
        'stop_loss_pct': 3.0,
        'max_hold_bars': 36,
    }


def get_walk_forward_param_grid() -> dict:
    """
    Parameter grid for Walk-Forward Optimization.
    Small grid for VPS safety — V17 params centered around champion values.
    """
    return {
        'bb_period': [18, 20, 22],
        'rsi_threshold': [25, 30, 35],
        'ema_period': [150, 200, 250],
    }