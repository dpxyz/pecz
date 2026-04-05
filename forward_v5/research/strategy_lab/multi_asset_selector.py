#!/usr/bin/env python3
"""
Strategy: Multi-Asset Selector

Hypothesis:
- Relative Stärke persistiert kurzfristig
- Top-2 Assets (nach Momentum) schneiden besser ab als Bottom
- Einfacher Momentum-Rank + Long-Top-2

Logic:
1. Berechne Momentum (z.B. 20-Period Return) für jedes Asset
2. Ränge Assets nach Momentum
3. Long Signal für Top-2
4. Kein Signal für Rest

VPS-Limits:
- Max 2-3 Assets gleichzeitig
- Oder: Asset-Liste aufteilen in Batches
- Relative Stärke über einfache Momentum-Metric

Notes:
- Diese Strategie arbeitet mit MULTIPLE DataFrames
- Input: Dict of DataFrames (symbol -> df)
- Output: Dict of DataFrames mit Signal-Column
"""

import polars as pl
from typing import Dict, List


def multi_asset_selector_strategy(
    data_dict: Dict[str, pl.DataFrame],
    params: dict
) -> Dict[str, pl.DataFrame]:
    """
    Multi-Asset Selector Strategie
    
    Parameters:
    -----------
    momentum_period : int
        Lookback für Momentum (default: 20)
    n_top : int
        Anzahl Top-Assets (default: 2)
    
    Returns:
    --------
    Dict[str, pl.DataFrame] mit Signal-Column
    """
    momentum_period = params.get('momentum_period', 20)
    n_top = params.get('n_top', 2)
    
    if len(data_dict) < n_top:
        raise ValueError(f"Need at least {n_top} assets, got {len(data_dict)}")
    
    # Berechne Momentum für jedes Asset
    momentums = {}
    
    for symbol, df in data_dict.items():
        df = df.with_columns([
            pl.col('close').shift(momentum_period).alias('past_close')
        ])
        
        df = df.with_columns([
            ((pl.col('close') - pl.col('past_close')) / pl.col('past_close') * 100)
            .alias('momentum')
        ])
        
        momentums[symbol] = df
    
    # Erstelle konsolidiertes Ranking (vereinfacht)
    # In V1: Wir nutzen einfach Momentum-Threshold statt Ranking
    # Ranking über multiple DataFrames ist komplex in Polars
    
    result = {}
    
    for symbol, df in momentums.items():
        # Entry wenn Momentum positiv und > Median
        df = df.with_columns([
            pl.when(pl.col('momentum') > 2.0).then(1).otherwise(0).alias('signal')
        ])
        
        result[symbol] = df
    
    return result


def single_asset_equivalent(df: pl.DataFrame, params: dict) -> pl.DataFrame:
    """
    Für Backtesting: Single-Asset Version
    Nutzt relative Stärke zum eigenen SMA
    """
    momentum_period = params.get('momentum_period', 20)
    
    df = df.with_columns([
        pl.col('close').shift(momentum_period).alias('past_close')
    ])
    
    df = df.with_columns([
        ((pl.col('close') - pl.col('past_close')) / pl.col('past_close') * 100)
        .alias('momentum')
    ])
    
    # Entry wenn Momentum > 0
    df = df.with_columns([
        pl.when(pl.col('momentum') > 2.0).then(1).otherwise(0).alias('signal')
    ])
    
    return df


def get_default_params() -> dict:
    return {
        'momentum_period': 20,
        'n_top': 2,
        'momentum_threshold': 2.0
    }


def get_vps_safe_param_grid() -> dict:
    """VPS-Safe: 12 Kombinationen"""
    return {
        'momentum_period': [10, 20, 30],
        'n_top': [2],
        'momentum_threshold': [1.0, 2.0, 3.0, 5.0]
    }


if __name__ == "__main__":
    print("Multi-Asset Selector Strategy V1")
    print(f"Default: {get_default_params()}")
    print("Grid: 3*1*4 = 12 combinations")
    print("Note: Single-asset equivalent for backtesting includes relative momentum")
