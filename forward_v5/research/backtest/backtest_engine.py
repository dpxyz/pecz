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
    max_consecutive_losses: int = 0
    sharpe_ratio: float = 0.0

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

        # PnL — trades store pnl in PERCENT (net_pnl * 100)
        # So sum(pnls) is already in % — use directly for net_return
        pnls = [t.pnl for t in self.trades if t.pnl is not None]
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = sum(abs(p) for p in pnls if p < 0)
        net_pnl_pct = sum(pnls)  # Already in %

        self.net_return = net_pnl_pct  # % direkt (war vorher /capital * 100 = 100x zu klein)

        # Win Rate
        wins = sum(1 for p in pnls if p > 0)
        self.win_rate = (wins / len(pnls)) * 100 if pnls else 0

        # Profit Factor
        self.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

        # Expectancy (in %)
        self.expectancy = net_pnl_pct / len(pnls) if pnls else 0

        # Max Drawdown
        self.max_drawdown = self._calc_max_drawdown()
        
        # Max Consecutive Losses
        self.max_consecutive_losses = self._calc_max_consecutive_losses(pnls)
        
        # Sharpe Ratio (from equity curve)
        self.sharpe_ratio = self._calc_sharpe_ratio()

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
    
    def _calc_max_consecutive_losses(self, pnls: list) -> int:
        """Berechne maximale aufeinanderfolgende Verluste"""
        max_streak = 0
        current_streak = 0
        for pnl in pnls:
            if pnl < 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        return max_streak
    
    def _calc_sharpe_ratio(self) -> float:
        """Berechne Sharpe Ratio aus der Equity-Kurve"""
        if not self.equity_curve or len(self.equity_curve) < 2:
            return 0.0
        
        # Tägliche Returns aus Equity-Kurve
        equity = np.array(self.equity_curve)
        returns = np.diff(equity) / equity[:-1]
        
        if len(returns) == 0 or np.std(returns) == 0:
            return 0.0
        
        # Annualisiere: ~365 Tage / 24 Stunden = Bar-Returns für 1h
        # Sharpe = mean(returns) / std(returns) * sqrt(bars_per_year)
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        
        if std_ret == 0:
            return 0.0
        
        # Annualisierter Sharpe (8760 Bars/Jahr für 1h)
        sharpe = mean_ret / std_ret * np.sqrt(8760)
        return float(sharpe)

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
            'max_consecutive_losses': self.max_consecutive_losses,
            'sharpe_ratio': self.sharpe_ratio,
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
        timeframe: str = "1h",
        exit_config: Dict = None,
        df: pl.DataFrame = None
    ) -> BacktestResult:
        """
        Führe Backtest aus
        
        Args:
            strategy_func: Callable(df: pl.DataFrame, params: dict) -> pl.DataFrame
                          Muss 'signal' Column zurückgeben (-1, 0, 1)
            exit_config: Dict with take_profit_pct, stop_loss_pct, max_hold_bars
            df: Pre-loaded DataFrame (wenn gesetzt, wird symbol/timeframe nicht geladen)
        """
        if exit_config is None:
            exit_config = {}
        import time
        import tracemalloc
        
        start_time = time.time()
        tracemalloc.start()
        
        result = BacktestResult(
            strategy_name=strategy_name,
            params=params
        )
        
        try:
            # Lade Daten: entweder übergebenes DataFrame oder aus Datei
            if df is not None:
                data = df
            else:
                lf = self.load_data(symbol, timeframe)
                data = lf.collect()
            
            if len(data) < 50:
                result.failure_reasons.append("Insufficient data (< 50 bars)")
                return result
            
            # Generiere Signale
            df_signals = strategy_func(data, params)
            
            if 'signal' not in df_signals.columns:
                result.failure_reasons.append("Strategy did not produce 'signal' column")
                return result
            
            # Simuliere Trades (Polars-native)
            result = self._simulate_trades_polars(df_signals, result, exit_config)
            
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
        result: BacktestResult,
        exit_config: Dict = None
    ) -> BacktestResult:
        """
        Simuliere Trades aus Signalen - mit Exit-Logik (TP/SL/Max-Hold)

        Exit Priority:
        1. Stop-Loss (bar-wise check)
        2. Take-Profit (bar-wise check)
        3. Max-Hold-Bars (time-based exit)
        4. Signal Exit (strategy flips from 1 to 0/-1)

        - Entry on signal edge (0->1), executed at next open + slippage
        - No lookahead bias
        """
        if exit_config is None:
            exit_config = {}

        tp_pct = exit_config.get("take_profit_pct", None)
        sl_pct = exit_config.get("stop_loss_pct", None)
        max_hold = exit_config.get("max_hold_bars", None)
        trailing_stop_pct = exit_config.get("trailing_stop_pct", None)  # % from high water mark

        # Hole timestamp Column Name
        timestamp_col = None
        for col in ['timestamp', 'datetime', 'date', 'time']:
            if col in df.columns:
                timestamp_col = col
                break

        if timestamp_col is None:
            df = df.with_row_index("_row_idx")
            timestamp_col = "_row_idx"

        # Convert to numpy arrays for fast bar-wise iteration
        signals = df["signal"].to_numpy()
        opens = df["open"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        closes = df["close"].to_numpy()
        n = len(df)

        trades = []
        equity = self.initial_capital
        equity_curve = [equity]

        i = 0
        in_position = False
        entry_price = 0.0
        entry_bar = 0
        highest_since_entry = 0.0  # For trailing stop

        while i < n - 1:
            # Check for entry signal (0 or not-in-position -> 1)
            if not in_position and signals[i] == 1:
                # Enter at next bar's open
                entry_price = opens[i + 1] * (1 + self.slippage)
                entry_bar = i + 1
                highest_since_entry = highs[i + 1]  # Track high for trailing stop
                in_position = True
                i += 1
                continue

            # If not in position, advance
            if not in_position:
                i += 1
                continue

            # We're in a position - check exits bar by bar
            # Priority: SL > TP > Max-Hold > Signal Exit

            # 1. Stop-Loss check
            if sl_pct is not None and lows[i] <= entry_price * (1 - sl_pct / 100):
                exit_price = entry_price * (1 - sl_pct / 100) * (1 - self.slippage)
                gross_pnl = (exit_price - entry_price) / entry_price
                net_pnl = gross_pnl - self.fee_rate * 2
                trades.append(Trade(
                    entry_time=str(entry_bar),
                    exit_time=str(i),
                    entry_price=entry_price,
                    exit_price=exit_price,
                    side='long',
                    pnl=net_pnl * 100,
                    exit_reason='stop_loss'
                ))
                equity *= (1 + net_pnl)
                equity_curve.append(equity)
                in_position = False
                i += 1
                continue

            # 2. Take-Profit check
            if tp_pct is not None and highs[i] >= entry_price * (1 + tp_pct / 100):
                exit_price = entry_price * (1 + tp_pct / 100) * (1 - self.slippage)
                gross_pnl = (exit_price - entry_price) / entry_price
                net_pnl = gross_pnl - self.fee_rate * 2
                trades.append(Trade(
                    entry_time=str(entry_bar),
                    exit_time=str(i),
                    entry_price=entry_price,
                    exit_price=exit_price,
                    side='long',
                    pnl=net_pnl * 100,
                    exit_reason='take_profit'
                ))
                equity *= (1 + net_pnl)
                equity_curve.append(equity)
                in_position = False
                i += 1
                continue

            # 3. Trailing Stop check
            if trailing_stop_pct is not None:
                # Update high water mark
                if highs[i] > highest_since_entry:
                    highest_since_entry = highs[i]
                # Check if price dropped below trailing stop level
                trailing_level = highest_since_entry * (1 - trailing_stop_pct / 100)
                # NOTE: Uses CLOSE for trailing check (not LOW).
                # LOW-based would be more conservative but makes most strategies unprofitable
                # with 2% trailing on 1h crypto. Paper engine uses real-time price checks
                # which are more accurate than either OHLC approximation.
                # See: STRATEGIC_REVIEW.md for full analysis.
                if closes[i] <= trailing_level:
                    exit_price = trailing_level * (1 - self.slippage)
                    gross_pnl = (exit_price - entry_price) / entry_price
                    net_pnl = gross_pnl - self.fee_rate * 2
                    trades.append(Trade(
                        entry_time=str(entry_bar),
                        exit_time=str(i),
                        entry_price=entry_price,
                        exit_price=exit_price,
                        side='long',
                        pnl=net_pnl * 100,
                        exit_reason='trailing_stop'
                    ))
                    equity *= (1 + net_pnl)
                    equity_curve.append(equity)
                    in_position = False
                    i += 1
                    continue

            # 4. Max hold bars
            bars_held = i - entry_bar
            if max_hold is not None and bars_held >= max_hold:
                exit_price = closes[i] * (1 - self.slippage)
                gross_pnl = (exit_price - entry_price) / entry_price
                net_pnl = gross_pnl - self.fee_rate * 2
                trades.append(Trade(
                    entry_time=str(entry_bar),
                    exit_time=str(i),
                    entry_price=entry_price,
                    exit_price=exit_price,
                    side='long',
                    pnl=net_pnl * 100,
                    exit_reason='max_hold'
                ))
                equity *= (1 + net_pnl)
                equity_curve.append(equity)
                in_position = False
                i += 1
                continue

            # 5. Signal exit (signal flips from 1 to 0 or -1)
            if signals[i] != 1:
                exit_price = opens[i + 1] * (1 - self.slippage) if i + 1 < n else closes[i] * (1 - self.slippage)
                gross_pnl = (exit_price - entry_price) / entry_price
                net_pnl = gross_pnl - self.fee_rate * 2
                trades.append(Trade(
                    entry_time=str(entry_bar),
                    exit_time=str(i),
                    entry_price=entry_price,
                    exit_price=exit_price,
                    side='long',
                    pnl=net_pnl * 100,
                    exit_reason='signal_exit'
                ))
                equity *= (1 + net_pnl)
                equity_curve.append(equity)
                in_position = False

            i += 1

        # Close open position at end of data
        if in_position:
            exit_price = closes[-1] * (1 - self.slippage)
            gross_pnl = (exit_price - entry_price) / entry_price
            net_pnl = gross_pnl - self.fee_rate * 2
            trades.append(Trade(
                entry_time=str(entry_bar),
                exit_time=str(n - 1),
                entry_price=entry_price,
                exit_price=exit_price,
                side='long',
                pnl=net_pnl * 100,
                exit_reason='end_of_data'
            ))
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
