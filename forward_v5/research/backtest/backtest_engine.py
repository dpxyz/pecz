#!/usr/bin/env python3
"""
Backtest Engine V2 - VPS-First Design, Polars-Native
- Polars DataFrames für den gesamten Simulationspfad
- Keine Pandas-Konvertierung
- Vektorisierte Trade-Simulation
- OHLCV Bar-Daten (keine Ticks)
"""

import polars as pl
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple
from pathlib import Path
import json
from datetime import datetime


@dataclass
class Trade:
    entry_time: str
    exit_time: Optional[str] = None
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    side: str = ""  # 'long' or 'short'
    size: float = 1.0
    pnl: Optional[float] = None
    exit_reason: str = ""


@dataclass
class BacktestResult:
    strategy_name: str
    params: Dict
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    
    # Performance Metrics
    net_return: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    expectancy: float = 0.0
    trade_count: int = 0
    
    # Metadata
    execution_time_ms: int = 0
    memory_peak_mb: float = 0.0
    failure_reasons: List[str] = field(default_factory=list)
    
    def calculate_metrics(self, initial_capital: float = 10000.0):
        """Berechne alle Performance-Metriken"""
        self.trade_count = len(self.trades)
        
        if self.trade_count == 0:
            self.failure_reasons.append("No trades generated")
            return self
        
        # PnL
        pnls = [t.pnl for t in self.trades if t.pnl is not None]
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = sum(abs(p) for p in pnls if p < 0)
        net_pnl = sum(pnls)
        
        self.net_return = (net_pnl / initial_capital) * 100
        
        # Win Rate
        wins = sum(1 for p in pnls if p > 0)
        self.win_rate = (wins / len(pnls)) * 100 if pnls else 0
        
        # Profit Factor
        self.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
        
        # Expectancy
        self.expectancy = net_pnl / len(pnls) if pnls else 0
        
        # Max Drawdown
        self.max_drawdown = self._calc_max_drawdown()
        
        return self
    
    def _calc_max_drawdown(self) -> float:
        """
        Calculate maximum drawdown from equity curve.
        Vectorized using numpy - isolated, performant, no DataFrame iteration.
        """
        if not self.equity_curve or len(self.equity_curve) < 2:
            return 0.0

        equity = np.array(self.equity_curve)
        # Cumulative maximum (running peak) - vectorized
        running_peak = np.maximum.accumulate(equity)
        # Drawdown at each point
        drawdowns = (running_peak - equity) / running_peak
        # Max drawdown
        max_dd = np.max(drawdowns)

        return float(max_dd) * 100
    
    def to_dict(self) -> Dict:
        return {
            'strategy_name': self.strategy_name,
            'params': self.params,
            'net_return': self.net_return,
            'max_drawdown': self.max_drawdown,
            'profit_factor': self.profit_factor,
            'win_rate': self.win_rate,
            'expectancy': self.expectancy,
            'trade_count': self.trade_count,
            'execution_time_ms': self.execution_time_ms,
            'memory_peak_mb': self.memory_peak_mb,
            'failure_reasons': self.failure_reasons
        }


class BacktestEngine:
    """Minimalistische Backtest Engine - VPS First, Polars Native"""
    
    def __init__(
        self,
        data_path: str,
        fee_rate: float = 0.0005,  # 0.05% pro Trade (binance taker)
        slippage_bps: float = 5.0,   # 5 Basis-Punkte Slippage
        initial_capital: float = 10000.0
    ):
        self.data_path = Path(data_path)
        self.fee_rate = fee_rate
        self.slippage = slippage_bps / 10000  # bps -> decimal
        self.initial_capital = initial_capital
        self.data: Optional[pl.DataFrame] = None
    
    def load_data(self, symbol: str, timeframe: str = "1h") -> pl.LazyFrame:
        """Lade OHLCV Daten als LazyFrame"""
        file_path = self.data_path / f"{symbol}_{timeframe}.parquet"
        
        if not file_path.exists():
            raise FileNotFoundError(f"Data not found: {file_path}")
        
        # Polars LazyFrame - Memory-efficient
        return pl.scan_parquet(file_path)
    
    def run(
        self,
        strategy_name: str,
        strategy_func: Callable,
        params: Dict,
        symbol: str = "BTCUSDT",
        timeframe: str = "1h"
    ) -> BacktestResult:
        """
        Führe Backtest aus
        
        Args:
            strategy_func: Callable(df: pl.DataFrame, params: dict) -> pl.DataFrame
                          Muss 'signal' Column zurückgeben (-1, 0, 1)
        """
        import time
        import tracemalloc
        
        start_time = time.time()
        tracemalloc.start()
        
        result = BacktestResult(
            strategy_name=strategy_name,
            params=params
        )
        
        try:
            # Lade Daten (Lazy -> Collect bei Bedarf)
            lf = self.load_data(symbol, timeframe)
            df = lf.collect()
            
            if len(df) < 100:
                result.failure_reasons.append("Insufficient data (< 100 bars)")
                return result
            
            # Generiere Signale
            df_signals = strategy_func(df, params)
            
            if 'signal' not in df_signals.columns:
                result.failure_reasons.append("Strategy did not produce 'signal' column")
                return result
            
            # Simuliere Trades (Polars-native)
            result = self._simulate_trades_polars(df_signals, result)
            
            # Metriken berechnen
            result.calculate_metrics(self.initial_capital)
            
        except Exception as e:
            result.failure_reasons.append(f"Execution error: {str(e)}")
        
        finally:
            # Performance Tracking
            result.execution_time_ms = int((time.time() - start_time) * 1000)
            _, peak = tracemalloc.get_traced_memory()
            result.memory_peak_mb = peak / 1024 / 1024
            tracemalloc.stop()
        
        return result
    
    def _simulate_trades_polars(
        self,
        df: pl.DataFrame,
        result: BacktestResult
    ) -> BacktestResult:
        """
        Simuliere Trades aus Signalen - Polars-Native Implementation
        
        Logik:
        - Signal wird auf Bar t erzeugt (close)
        - Entry/Exit auf Bar t+1 (open + slippage)
        - Kein Lookahead-Bias
        - Vektorisiert mit Polars
        """
        # Hole timestamp Column Name (kann verschieden sein)
        timestamp_col = None
        for col in ['timestamp', 'datetime', 'date', 'time']:
            if col in df.columns:
                timestamp_col = col
                break
        
        if timestamp_col is None:
            # Erstelle Index als timestamp falls keine Zeitspalte existiert
            df = df.with_row_index("_row_idx")
            timestamp_col = "_row_idx"
        
        # ============================================
        # Schritt 1: Next-Bar Vorbereitung
        # ============================================
        # Shift(-1) holt den Wert der nächsten Zeile (next bar)
        df = df.with_columns([
            pl.col("open").shift(-1).alias("next_open"),
            pl.col(timestamp_col).shift(-1).alias("next_timestamp")
        ])
        
        # ============================================
        # Schritt 2: Signal-Edge Detection
        # ============================================
        # Finde wo Long-Entry (signal wechselt von 0 zu 1)
        # Finde wo Long-Exit (signal wechselt von 1 zu -1 oder 0)
        df = df.with_columns([
            pl.col("signal").shift(1).alias("prev_signal")
        ])
        
        df = df.with_columns([
            # Long Entry: prev war 0/Fehlt, jetzt ist 1
            pl.when(
                (pl.col("prev_signal").is_null() | (pl.col("prev_signal") == 0)) & 
                (pl.col("signal") == 1)
            ).then(1).otherwise(0).alias("long_entry_signal"),
            
            # Long Exit: prev war 1, jetzt ist -1 oder 0
            pl.when(
                (pl.col("prev_signal") == 1) & 
                (pl.col("signal").is_null() | (pl.col("signal") != 1))
            ).then(1).otherwise(0).alias("long_exit_signal")
        ])
        
        # ============================================
        # Schritt 3: Trade Points Extraktion
        # ============================================
        # Entry-Points: wo long_entry_signal == 1
        entry_points = df.filter(pl.col("long_entry_signal") == 1).select([
            pl.col(timestamp_col).alias("entry_time"),
            pl.col("next_open").alias("entry_price_raw"),
            pl.col("next_timestamp").alias("entry_exec_time")
        ])
        
        # Exit-Points: wo long_exit_signal == 1  
        exit_points = df.filter(pl.col("long_exit_signal") == 1).select([
            pl.col(timestamp_col).alias("exit_time"),
            pl.col("next_open").alias("exit_price_raw"),
            pl.col("next_timestamp").alias("exit_exec_time")
        ])
        
        # ============================================
        # Schritt 4: Trade Matching
        # ============================================
        # Konvertiere zu Python Listen für Paar-Matching
        # (Dies ist kein row-wise DataFrame iteration sondern Listen-Verarbeitung)
        entries = entry_points.to_numpy().tolist() if len(entry_points) > 0 else []
        exits = exit_points.to_numpy().tolist() if len(exit_points) > 0 else []
        
        trades = []
        equity = self.initial_capital
        equity_curve = [equity]
        
        entry_idx = 0
        exit_idx = 0
        
        # Paare Entries mit nächsten Exits
        while entry_idx < len(entries) and exit_idx < len(exits):
            entry = entries[entry_idx]
            exit = exits[exit_idx]
            
            # Prüfe ob Exit nach Entry kommt
            # Sicherstellen, dass wir skalare Werte vergleichen, nicht Series
            exit_time_val = float(exit[2]) if hasattr(exit[2], '__float__') else exit[2]
            entry_time_val = float(entry[2]) if hasattr(entry[2], '__float__') else entry[2]
            if exit_time_val > entry_time_val:  # exit_exec_time > entry_exec_time
                # Berechne Trade
                entry_price = entry[1] * (1 + self.slippage)  # + slippage
                exit_price = exit[1] * (1 - self.slippage)    # - slippage
                
                gross_pnl = (exit_price - entry_price) / entry_price
                fees = self.fee_rate * 2  # Entry + Exit
                net_pnl = gross_pnl - fees
                
                trade = Trade(
                    entry_time=str(entry[2]),
                    exit_time=str(exit[2]),
                    entry_price=entry_price,
                    exit_price=exit_price,
                    side='long',
                    pnl=net_pnl * 100  # Prozent
                )
                trades.append(trade)
                
                # Equity Update
                equity *= (1 + net_pnl)
                
                entry_idx += 1
                exit_idx += 1
            else:
                # Exit ist vor Entry (sollte nicht passieren, aber sicherheitshalber)
                exit_idx += 1
            
            equity_curve.append(equity)
        
        # ============================================
        # Schritt 5: Offene Position am Ende schließen
        # ============================================
        if entry_idx < len(entries):
            # Es gibt eine offene Position
            entry = entries[entry_idx]
            # In Polars muss man .item() verwenden um skalare Werte zu bekommen
            close_val = df.tail(1).select(pl.col("close")).to_numpy()[0][0]
            last_time_val = df.tail(1).select(pl.col(timestamp_col)).to_numpy()[0][0]
            
            entry_price = entry[1] * (1 + self.slippage)
            close_price = close_val * (1 - self.slippage)
            
            gross_pnl = (close_price - entry_price) / entry_price
            fees = self.fee_rate * 2
            net_pnl = gross_pnl - fees
            
            last_time = last_time_val
            
            trade = Trade(
                entry_time=str(entry[2]),
                exit_time=str(last_time),
                entry_price=entry_price,
                exit_price=close_price,
                side='long',
                pnl=net_pnl * 100,
                exit_reason='end_of_data'
            )
            trades.append(trade)
            
            equity *= (1 + net_pnl)
            equity_curve.append(equity)
        
        # Falls keine Trades, füge zumindest initiales Equity hinzu
        if len(equity_curve) == 1:
            equity_curve.append(equity)
        
        result.trades = trades
        result.equity_curve = equity_curve
        
        return result


# =============================================================================
# CLI Interface
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Backtest Engine V2 - Polars Native')
    parser.add_argument('--data', required=True, help='Path to data directory')
    parser.add_argument('--symbol', default='BTCUSDT', help='Trading pair')
    parser.add_argument('--timeframe', default='1h', help='Timeframe')
    parser.add_argument('--output', help='Output JSON file')
    
    args = parser.parse_args()
    
    # Beispiel-Usage
    engine = BacktestEngine(args.data)
    print(f"Backtest Engine V2 initialized (Polars Native)")
    print(f"Data path: {args.data}")
    print(f"Symbol: {args.symbol}")
    print(f"Timeframe: {args.timeframe}")
