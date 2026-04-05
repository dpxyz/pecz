#!/usr/bin/env python3
"""
Volatility Filter

Usage:
- Filtert Trades basierend auf Volatilitätsregime
- Vermeidet Hochvolatilität (wenn gewünscht) oder nutzt sie

Regimes:
- ATR < Q1: Low Vol (konsolidierung)
- ATR Q1-Q3: Normal Vol (Tradable)
- ATR > Q3: High Vol (avoid or mean reversion)
"""

import polars as pl


def add_volatility_filter(
    df: pl.DataFrame,
    atr_period: int = 14,
    use_percentile: bool = True,
    low_vol_threshold: float = 0.5,  # ATR/close < 0.5%
    high_vol_threshold: float = 2.0  # ATR/close > 2%
) -> pl.DataFrame:
    """
    Füge Volatilitäts-Filter hinzu
    
    Returns DataFrame mit:
    - atr: Absolute True Range
    - atr_pct: ATR als % von Close
    - vol_regime: 'low', 'normal', 'high'
    - vol_filter_pass: bool
    """
    # True Range berechnen
    df = df.with_columns([
        (pl.col('high') - pl.col('low')).alias('range1'),
        (pl.col('high') - pl.col('close').shift(1)).abs().alias('range2'),
        (pl.col('low') - pl.col('close').shift(1)).abs().alias('range3')
    ])
    
    df = df.with_columns([
        pl.max_horizontal(['range1', 'range2', 'range3']).alias('true_range')
    ])
    
    # ATR
    df = df.with_columns([
        pl.col('true_range').rolling_mean(window_size=atr_period, min_periods=atr_period).alias('atr'),
        (pl.col('true_range').rolling_mean(window_size=atr_period, min_periods=atr_period) / 
         pl.col('close') * 100).alias('atr_pct')
    ])
    
    # Volatilitäts-Regime (fixed thresholds für VPS-Simplicity)
    df = df.with_columns([
        pl.when(pl.col('atr_pct') < low_vol_threshold).then(pl.lit('low'))
          .when(pl.col('atr_pct') > high_vol_threshold).then(pl.lit('high'))
          .otherwise(pl.lit('normal'))
          .alias('vol_regime')
    ])
    
    # Filter-Pass (nur normal volatility)
    df = df.with_columns([
        (pl.col('vol_regime') == 'normal').alias('vol_filter_pass')
    ])
    
    return df


def filter_by_volatility(
    df: pl.DataFrame,
    signal_col: str = 'signal',
    filtered_col: str = 'signal_filtered',
    allow_low_vol: bool = False,
    allow_high_vol: bool = False
) -> pl.DataFrame:
    """
    Wende Volatilitätsfilter auf Signal an
    """
    allowed_regimes = ['normal']
    if allow_low_vol:
        allowed_regimes.append('low')
    if allow_high_vol:
        allowed_regimes.append('high')
    
    return df.with_columns([
        pl.when(
            (pl.col(signal_col) == 1) & 
            (pl.col('vol_regime').is_in(allowed_regimes))
        ).then(1)
        .when(
            (pl.col(signal_col) == -1) & 
            (pl.col('vol_regime').is_in(allowed_regimes))
        ).then(-1)
        .otherwise(0)
        .alias(filtered_col)
    ])


if __name__ == "__main__":
    print("Volatility Filter V1")
    print("Usage: Add to filter noise during high/low volatility")
