#!/usr/bin/env python3
"""
Strategy: Mean Reversion Panic

Hypothesis:
- Kurze, heftige Bewegungen (Panic) kehren zum Mittelwert zurück
- Z-Score > Threshold = Panic-Entry
- Mean-Reversion-Signal

Logic:
1. Berechne Z-Score über SMA und StdDev
2. Entry Long wenn Z-Score < -2.0 (Panic-Abverkauf)
3. Entry Short wenn Z-Score > +2.0 (Panic-Rally)
4. Exit bei Mean-Cross (Z-Score zurück zu 0)

VPS-Optimizations:
- Vectorisiert
- Polars-native
- Keine komplexen Iterationen
"""

import polars as pl


def mean_reversion_panic_strategy(df: pl.DataFrame, params: dict) -> pl.DataFrame:
    """
    Mean Reversion Panic Strategie
    
    Parameters:
    -----------
    sma_period : int
        Basis für Mean-Berechnung (default: 50)
    std_period : int
        Volatilitäts-Fenster (default: 50)
    z_entry_long : float
        Threshold für Long Entry (default: -2.0)
    z_entry_short : float
        Threshold für Short Entry (default: 2.0)
    z_exit : float
        Exit wenn Z-Score zurück (default: 0.0)
    """
    sma_period = params.get('sma_period', 50)
    std_period = params.get('std_period', 50)
    z_entry_long = params.get('z_entry_long', -2.0)
    z_entry_short = params.get('z_entry_short', 2.0)
    
    # SMA und StdDev
    df = df.with_columns([
        pl.col('close').rolling_mean(window_size=sma_period, min_periods=sma_period).alias('sma'),
        pl.col('close').rolling_std(window_size=std_period, min_periods=std_period).alias('std')
    ])
    
    # Z-Score berechnen
    df = df.with_columns([
        ((pl.col('close') - pl.col('sma')) / pl.when(pl.col('std') == 0)
         .then(0.001).otherwise(pl.col('std'))).alias('z_score')
    ])
    
    # Signal-Generierung
    df = df.with_columns([
        pl.when(pl.col('z_score') < z_entry_long)
        .then(1)
        .when(pl.col('z_score') > z_entry_short)
        .then(-1)
        .otherwise(0)
        .alias('signal')
    ])
    
    return df


# Konsistentes Interface für Backtest-Engine
strategy_func = mean_reversion_panic_strategy


def get_default_params() -> dict:
    """Standard-Parameter"""
    return {
        'sma_period': 50,
        'std_period': 50,
        'z_entry_long': -2.0,
        'z_entry_short': 2.0
    }


def get_vps_safe_param_grid() -> dict:
    """VPS-Safe: Max 16 Kombinationen"""
    return {
        'sma_period': [40, 50, 60],
        'std_period': [50],  # Gleich wie SMA für Einfachheit
        'z_entry_long': [-2.5, -2.0, -1.5],
        'z_entry_short': [2.0, 2.5]
    }


if __name__ == "__main__":
    print("Mean Reversion Panic Strategy V1")
    print(f"Default params: {get_default_params()}")
    print("Grid: 3*1*3*2 = 18 combinations")
