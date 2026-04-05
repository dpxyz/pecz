#!/usr/bin/env python3
"""
RSI Regime Filter

Usage:
- Als Filter-Baustein für andere Strategien
- Definiert Marktregime basierend auf RSI-Level

Regime:
- RSI > 70: Overbought (Caution)
- RSI 40-70: Bull Zone (Trend)
- RSI 30-40: Neutral
- RSI < 30: Oversold (Mean Reversion)
"""

import polars as pl


def add_regime_filter(df: pl.DataFrame, rsi_period: int = 14) -> pl.DataFrame:
    """
    Füge RSI-basiertes Regime als Filter-Column hinzu
    
    Returns DataFrame mit zusätzlichen Columns:
    - rsi: RSI-Wert
    - regime: 'bull', 'neutral', 'oversold', 'overbought'
    - filter_allow_long: bool
    - filter_allow_short: bool
    """
    # RSI Berechnung
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
        (100 - (100 / (1 + (pl.col('avg_gain') / pl.when(pl.col('avg_loss') == 0)
         .then(1).otherwise(pl.col('avg_loss')))))).alias('rsi')
    ])
    
    # Regime-Definition
    df = df.with_columns([
        pl.when(pl.col('rsi') > 70).then(pl.lit('overbought'))
          .when(pl.col('rsi') > 40).then(pl.lit('bull'))
          .when(pl.col('rsi') > 30).then(pl.lit('neutral'))
          .otherwise(pl.lit('oversold'))
          .alias('regime')
    ])
    
    # Filter-Freigaben
    df = df.with_columns([
        # Long erlaubt in bull, neutral (nach oversold), oversold (Mean Rev)
        pl.when(pl.col('regime').is_in(['bull', 'neutral', 'oversold']))
          .then(True).otherwise(False).alias('filter_allow_long'),
        # Short erlaubt in overbought
        pl.when(pl.col('regime').is_in(['overbought']))
          .then(True).otherwise(False).alias('filter_allow_short')
    ])
    
    return df


def apply_filter_to_signal(
    df: pl.DataFrame,
    signal_col: str = 'signal',
    filtered_col: str = 'signal_filtered'
) -> pl.DataFrame:
    """
    Wende Filter auf existierendes Signal an
    """
    return df.with_columns([
        pl.when(
            (pl.col(signal_col) == 1) & pl.col('filter_allow_long')
        ).then(1)
        .when(
            (pl.col(signal_col) == -1) & pl.col('filter_allow_short')
        ).then(-1)
        .otherwise(0)
        .alias(filtered_col)
    ])


if __name__ == "__main__":
    print("RSI Regime Filter V1")
    print("Usage: Add as filter to existing strategies")
