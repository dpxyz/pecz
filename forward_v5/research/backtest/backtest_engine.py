#!/usr/bin/env python3
"""
Backtest Engine V1 - VPS-First Design
- Polars LazyFrames für RAM-Effizienz
- OHLCV Bar-Daten (keine Ticks)
- Reproduzierbare Ergebnisse (Seed/Determinismus)
"""

import polars as pl
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
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
        """Calculate maximum drawdown from equity curve"""
        if not self.equity_curve or len(self.equity_curve) < 2:
            return 0.0
        
        peak = self.equity_curve[0]
        max_dd = 0.0
        
        for equity in self.equity_curve[1:]:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            max_dd = max(max_dd, dd)
        
        return max_dd * 100
    
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
    """Minimalistische Backtest Engine - VPS First"""
    
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
            
            # Simuliere Trades
            result = self._simulate_trades(df_signals, result)
            
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
    
    def _simulate_trades(
        self,
        df: pl.DataFrame,
        result: BacktestResult
    ) -> BacktestResult:
        """
        Simuliere Trades aus Signalen
        Einfaches Next-Bar-Execution (kein Lookahead)
        """
        df_pd = df.to_pandas() if hasattr(df, 'to_pandas') else df
        
        position = 0  # 0 = flat, 1 = long
        entry_price = 0.0
        entry_time = None
        
        equity = self.initial_capital
        equity_curve = [equity]
        trades = []
        
        for i in range(len(df_pd) - 1):  # -1 wegen next-bar execution
            current = df_pd.iloc[i]
            next_bar = df_pd.iloc[i + 1]
            
            signal = current.get('signal', 0)
            
            # Long Entry
            if position == 0 and signal == 1:
                position = 1
                # Entry auf nächster Bar Open + Slippage
                entry_price = next_bar['open'] * (1 + self.slippage)
                entry_time = next_bar.get('timestamp', next_bar.name)
            
            # Long Exit (signal -1 oder 0 nach Long)
            elif position == 1 and (signal == -1 or signal == 0):
                # Exit auf nächster Bar Open - Slippage
                exit_price = next_bar['open'] * (1 - self.slippage)
                
                # PnL Berechnung
                gross_pnl = (exit_price - entry_price) / entry_price
                fees = self.fee_rate * 2  # Entry + Exit
                net_pnl = gross_pnl - fees
                
                trade = Trade(
                    entry_time=str(entry_time),
                    exit_time=str(next_bar.get('timestamp', next_bar.name)),
                    entry_price=entry_price,
                    exit_price=exit_price,
                    side='long',
                    pnl=net_pnl * 100  # Prozent
                )
                trades.append(trade)
                
                # Equity Update
                equity *= (1 + net_pnl)
                position = 0
                entry_price = 0
                entry_time = None
            
            equity_curve.append(equity)
        
        # Offene Position am Ende schließen (nicht ideal, aber für V1 OK)
        if position == 1:
            last = df_pd.iloc[-1]
            exit_price = last['close'] * (1 - self.slippage)
            gross_pnl = (exit_price - entry_price) / entry_price
            fees = self.fee_rate * 2
            net_pnl = gross_pnl - fees
            
            trade = Trade(
                entry_time=str(entry_time),
                exit_time=str(last.get('timestamp', last.name)),
                entry_price=entry_price,
                exit_price=exit_price,
                side='long',
                pnl=net_pnl * 100,
                exit_reason='end_of_data'
            )
            trades.append(trade)
            equity *= (1 + net_pnl)
            equity_curve.append(equity)
        
        result.trades = trades
        result.equity_curve = equity_curve
        
        return result


# =============================================================================
# CLI Interface
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Backtest Engine V1')
    parser.add_argument('--data', required=True, help='Path to data directory')
    parser.add_argument('--symbol', default='BTCUSDT', help='Trading pair')
    parser.add_argument('--timeframe', default='1h', help='Timeframe')
    parser.add_argument('--output', help='Output JSON file')
    
    args = parser.parse_args()
    
    # Beispiel-Usage
    engine = BacktestEngine(args.data)
    print(f"Backtest Engine initialized")
    print(f"Data path: {args.data}")
    print(f"Symbol: {args.symbol}")
    print(f"Timeframe: {args.timeframe}")
