#!/usr/bin/env python3
"""
Dummy Data Generator für Tests
Erzeugt synthetische OHLCV-Daten als Parquet
"""

import polars as pl
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path


def generate_ohlcv_data(
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    n_bars: int = 1000,
    start_price: float = 10000.0,
    volatility: float = 0.02,
    trend: float = 0.0001,
    output_dir: str = "data"
):
    """
    Generiere synthetische OHLCV-Daten
    
    Parameter:
    -----------
    n_bars : Anzahl Candlesticks
    start_price : Startpreis
    volatility : Intraday-Volatilität (std dev)
    trend : Trend per Bar (positiv = bullish)
    """
    
    # Zeitstempel
    start_time = datetime(2024, 1, 1, 0, 0, 0)
    
    if timeframe == "1h":
        delta = timedelta(hours=1)
    elif timeframe == "1d":
        delta = timedelta(days=1)
    else:
        delta = timedelta(hours=1)
    
    timestamps = [start_time + i * delta for i in range(n_bars)]
    
    # Preis-Generierung mit Random Walk + Trend
    np.random.seed(42)  # Reproduzierbar
    
    returns = np.random.normal(trend, volatility, n_bars)
    prices = start_price * np.exp(np.cumsum(returns))
    
    # OHLC aus Close generieren
    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []
    
    for i, close in enumerate(prices):
        # Intraday-Bewegung
        intraday_vol = abs(np.random.normal(0, volatility * close / 2))
        
        open_price = close * (1 + np.random.normal(0, volatility / 10))
        high = max(open_price, close) + intraday_vol
        low = min(open_price, close) - intraday_vol
        
        opens.append(open_price)
        highs.append(high)
        lows.append(low)
        closes.append(close)
        
        # Volume
        volumes.append(np.random.randint(100, 10000))
    
    # DataFrame erstellen
    df = pl.DataFrame({
        'timestamp': timestamps,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })
    
    # Speichern
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    filename = f"{symbol}_{timeframe}.parquet"
    filepath = output_path / filename
    
    df.write_parquet(filepath)
    
    print(f"✓ Generated: {filepath}")
    print(f"  Bars: {n_bars}")
    print(f"  Date range: {timestamps[0]} to {timestamps[-1]}")
    print(f"  Price range: ${min(lows):.2f} - ${max(highs):.2f}")
    print(f"  Final price: ${closes[-1]:.2f}")
    
    return filepath


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate dummy OHLCV data')
    parser.add_argument('--symbol', default='BTCUSDT')
    parser.add_argument('--timeframe', default='1h')
    parser.add_argument('--bars', type=int, default=1000)
    parser.add_argument('--start-price', type=float, default=10000.0)
    parser.add_argument('--output', default='data')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Dummy Data Generator")
    print("=" * 60)
    
    generate_ohlcv_data(
        symbol=args.symbol,
        timeframe=args.timeframe,
        n_bars=args.bars,
        start_price=args.start_price,
        output_dir=args.output
    )
    
    # Generate additional assets
    print("\nGenerating additional assets...")
    for symbol in ["ETHUSDT", "SOLUSDT"]:
        generate_ohlcv_data(
            symbol=symbol,
            timeframe=args.timeframe,
            n_bars=args.bars,
            start_price=np.random.uniform(5000, 50000),
            output_dir=args.output
        )
    
    print("\n✓ All files generated")
    print(f"  Directory: {args.output}/")
