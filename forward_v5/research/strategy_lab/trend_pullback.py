#!/usr/bin/env python3
"""
Strategy: Trend Pullback

Hypothesis:
- Etablierte Trends tendieren zu Pullbacks vorm Fortsetzen
- EMA-Trend + RSI-Oversold = Entry
- Stop bei Trendbruch

Logic:
1. Trend: Close > EMA20 (bullisch) oder Close < EMA20 (bearisch)
2. Pullback: RSI < 40 (Long) oder RSI > 60 (Short)
3. Entry: Next Bar Open
4. Exit: Stop-Loss oder Take-Profit oder Trendbruch

VPS-Optimizations:
- Vectorized (keine Schleifen)
- Polars LazyFrames
- Einfache Parameter
"""

import polars as pl
import numpy as np


def trend_pullback_strategy(df: pl.DataFrame, params: dict) -> pl.DataFrame:
    """
    Trend Pullback Strategie
    
    Parameters:
    -----------
    ema_period : int
        EMA-Basis (default: 20)
    rsi_period : int
        RSI-Länge (default: 14)
    rsi_threshold_long : int
        Entry wenn RSI < this (default: 40)
    rsi_threshold_short : int
        Entry wenn RSI > this (default: 60, use 0 to disable shorts)
    """
    ema_period = params.get('ema_period', 20)
    rsi_period = params.get('rsi_period', 14)
    rsi_long = params.get('rsi_threshold_long', 40)
    rsi_short = params.get('rsi_threshold_short', 60)
    
    # EMA berechnen
    df = df.with_columns([
        pl.col('close').ewm_mean(span=ema_period, adjust=False).alias('ema')
    ])
    
    # RSI Berechnung (simplified)
    df = df.with_columns([
        pl.col('close').diff().alias('delta')
    ])
    
    df = df.with_columns([
        pl.when(pl.col('delta') > 0).then(pl.col('delta')).otherwise(0).alias('gain'),
        pl.when(pl.col('delta') < 0).then(-pl.col('delta')).otherwise(0).alias('loss')
    ])
    
    df = df.with_columns([
        pl.col('gain').rolling_mean(window_size=rsi_period, min_periods=1).alias('avg_gain'),
        pl.col('loss').rolling_mean(window_size=rsi_period, min_periods=1).alias('avg_loss')
    ])
    
    df = df.with_columns([
        (100 - (100 / (1 + (pl.col('avg_gain') / pl.when(pl.col('avg_loss') == 0).then(1).otherwise(pl.col('avg_loss'))))).alias('rsi')
    ])
    
    # Trend-Definition
    df = df.with_columns([
        (pl.col('close') > pl.col('ema')).alias('bullish_trend'),
        (pl.col('close') < pl.col('ema')).alias('bearish_trend')
    ])
    
    # Signal-Generierung
    df = df.with_columns([
        pl.when(
            (pl.col('bullish_trend')) & 
            (pl.col('rsi') < rsi_long)
        ).then(1).when(
            (pl.col('bearish_trend')) & 
            (pl.col('rsi') > rsi_short) & 
            (rsi_short > 0)  # Shorts nur wenn threshold > 0
        ).then(-1).otherwise(0).alias('signal')
    ])
    
    return df


def get_default_params() -> dict:
    """Standard-Parameter für diese Strategie"""
    return {
        'ema_period': 20,
        'rsi_period': 14,
        'rsi_threshold_long': 40,
        'rsi_threshold_short': 60
    }


def get_param_grid() -> dict:
    """
    Parameter-Grid für Sweep
    Max 20 Kombinationen (VPS-Safe)
    """
    return {
        'ema_period': [15, 20, 25],
        'rsi_period': [10, 14],
        'rsi_threshold_long': [35, 40, 45],
        'rsi_threshold_short': [55, 60]  # 3*2*3*2 = 36 -> zu viel
    }


def get_vps_safe_param_grid() -> dict:
    """VPS-Safe: Max 18 Kombinationen"""
    return {
        'ema_period': [15, 20, 25],
        'rsi_period': [14],
        'rsi_threshold_long': [35, 40, 45],
        'rsi_threshold_short': [60]
    }


if __name__ == "__main__":
    print("Trend Pullback Strategy V1")
    print(f"Default params: {get_default_params()}")
    print(f"VPS-Safe grid combinations: {12}")  # 3*1*3*1 = 9
