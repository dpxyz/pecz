#!/usr/bin/env python3
"""
Backtest Engine V2 - VPS-First Design, Polars-Native
"""

import polars as pl
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple
from pathlib import Path
from datetime import datetime


@dataclass
class Trade:
    entry_time: str
    exit_time: Optional[str] = None
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    side: str = ""
    size: float = 1.0
    pnl: Optional[float] = None
    exit_reason: str = ""


@dataclass
class BacktestResult:
    strategy_name: str
    params: Dict
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)

    net_return: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    expectancy: float = 0.0
    trade_count: int = 0
    max_consecutive_losses: int = 0
    sharpe_ratio: float = 0.0

    execution_time_ms: int = 0
    memory_peak_mb: float = 0.0
    failure_reasons: List[str] = field(default_factory=list)

    def calculate_metrics(self, initial_capital: float = 10000.0):
        self.trade_count = len(self.trades)
        if self.trade_count == 0:
            self.failure_reasons.append("No trades generated")
            return self

        pnls = [t.pnl for t in self.trades if t.pnl is not None]
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = sum(abs(p) for p in pnls if p < 0)
        net_pnl_pct = sum(pnls)

        self.net_return = net_pnl_pct
        wins = sum(1 for p in pnls if p > 0)
        self.win_rate = (wins / len(pnls)) * 100 if pnls else 0
        self.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
        self.expectancy = net_pnl_pct / len(pnls) if pnls else 0
        self.max_drawdown = self._calc_max_drawdown()
        self.max_consecutive_losses = self._calc_max_consecutive_losses(pnls)
        self.sharpe_ratio = self._calc_sharpe_ratio()
        return self

    def _calc_max_drawdown(self) -> float:
        if not self.equity_curve or len(self.equity_curve) < 2:
            return 0.0
        equity = np.array(self.equity_curve)
        running_peak = np.maximum.accumulate(equity)
        drawdowns = (running_peak - equity) / running_peak
        return float(np.max(drawdowns)) * 100

    def _calc_max_consecutive_losses(self, pnls: list) -> int:
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
        if not self.equity_curve or len(self.equity_curve) < 2:
            return 0.0
        equity = np.array(self.equity_curve)
        returns = np.diff(equity) / equity[:-1]
        if len(returns) == 0 or np.std(returns) == 0:
            return 0.0
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        if std_ret == 0:
            return 0.0
        return float(mean_ret / std_ret * np.sqrt(8760))

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
    def __init__(self, data_path: str, fee_rate: float = 0.0005, slippage_bps: float = 5.0, initial_capital: float = 10000.0):
        self.data_path = Path(data_path)
        self.fee_rate = fee_rate
        self.slippage = slippage_bps / 10000
        self.initial_capital = initial_capital

    def load_data(self, symbol: str, timeframe: str = "1h") -> pl.LazyFrame:
        file_path = self.data_path / f"{symbol}_{timeframe}.parquet"
        if not file_path.exists():
            # Try _full variant
            file_path = self.data_path / f"{symbol}_{timeframe}_full.parquet"
            if not file_path.exists():
                raise FileNotFoundError(f"Data not found: {file_path}")
        return pl.scan_parquet(str(file_path))

    def run(self, strategy_name: str, strategy_func: Callable, params: Dict,
            symbol: str = "BTCUSDT", timeframe: str = "1h",
            exit_config: Dict = None, df: pl.DataFrame = None) -> BacktestResult:
        
        if exit_config is None:
            exit_config = {}

        import time
        import tracemalloc
        
        start_time = time.time()
        tracemalloc.start()
        
        result = BacktestResult(strategy_name=strategy_name, params=params)
        
        try:
            if df is not None:
                data = df
            else:
                lf = self.load_data(symbol, timeframe)
                data = lf.collect()
            
            if len(data) < 50:
                result.failure_reasons.append("Insufficient data (< 50 bars)")
                return result
            
            df_signals = strategy_func(data, params)
            
            if 'signal' not in df_signals.columns:
                result.failure_reasons.append("Strategy did not produce 'signal' column")
                return result
            
            result = self._simulate_trades(df_signals, result, exit_config)
            result.calculate_metrics(self.initial_capital)
            
        except Exception as e:
            result.failure_reasons.append(f"Execution error: {str(e)}")
        finally:
            result.execution_time_ms = int((time.time() - start_time) * 1000)
            _, peak = tracemalloc.get_traced_memory()
            result.memory_peak_mb = peak / 1024 / 1024
            tracemalloc.stop()
        
        return result

    def _simulate_trades(self, df: pl.DataFrame, result: BacktestResult, exit_config: Dict = None) -> BacktestResult:
        if exit_config is None:
            exit_config = {}

        tp_pct = exit_config.get("take_profit_pct", None)
        sl_pct = exit_config.get("stop_loss_pct", None)
        max_hold = exit_config.get("max_hold_bars", None)
        trailing_stop_pct = exit_config.get("trailing_stop_pct", None)
        exit_signal_col = exit_config.get("exit_signal_col", None)

        # If exit_condition is provided, compute exit signal column
        if exit_signal_col and exit_signal_col in df.columns:
            exit_signals = df[exit_signal_col].to_numpy()
        else:
            exit_signals = None

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
        highest_since_entry = 0.0

        while i < n - 1:
            if not in_position and signals[i] == 1:
                entry_price = opens[i + 1] * (1 + self.slippage)
                entry_bar = i + 1
                highest_since_entry = highs[i + 1]
                in_position = True
                i += 1
                continue

            if not in_position:
                i += 1
                continue

            # Stop-Loss
            if sl_pct is not None and lows[i] <= entry_price * (1 - sl_pct / 100):
                exit_price = entry_price * (1 - sl_pct / 100) * (1 - self.slippage)
                gross_pnl = (exit_price - entry_price) / entry_price
                net_pnl = gross_pnl - self.fee_rate * 2
                trades.append(Trade(entry_time=str(entry_bar), exit_time=str(i),
                    entry_price=entry_price, exit_price=exit_price, side='long',
                    pnl=net_pnl * 100, exit_reason='stop_loss'))
                equity *= (1 + net_pnl)
                equity_curve.append(equity)
                in_position = False
                i += 1
                continue

            # Take-Profit
            if tp_pct is not None and highs[i] >= entry_price * (1 + tp_pct / 100):
                exit_price = entry_price * (1 + tp_pct / 100) * (1 - self.slippage)
                gross_pnl = (exit_price - entry_price) / entry_price
                net_pnl = gross_pnl - self.fee_rate * 2
                trades.append(Trade(entry_time=str(entry_bar), exit_time=str(i),
                    entry_price=entry_price, exit_price=exit_price, side='long',
                    pnl=net_pnl * 100, exit_reason='take_profit'))
                equity *= (1 + net_pnl)
                equity_curve.append(equity)
                in_position = False
                i += 1
                continue

            # Trailing Stop
            if trailing_stop_pct is not None:
                if highs[i] > highest_since_entry:
                    highest_since_entry = highs[i]
                if closes[i] <= highest_since_entry * (1 - trailing_stop_pct / 100):
                    exit_price = closes[i] * (1 - self.slippage)
                    gross_pnl = (exit_price - entry_price) / entry_price
                    net_pnl = gross_pnl - self.fee_rate * 2
                    trades.append(Trade(entry_time=str(entry_bar), exit_time=str(i),
                        entry_price=entry_price, exit_price=exit_price, side='long',
                        pnl=net_pnl * 100, exit_reason='trailing_stop'))
                    equity *= (1 + net_pnl)
                    equity_curve.append(equity)
                    in_position = False
                    i += 1
                    continue

            # Max hold bars
            bars_held = i - entry_bar
            if max_hold is not None and bars_held >= max_hold:
                exit_price = closes[i] * (1 - self.slippage)
                gross_pnl = (exit_price - entry_price) / entry_price
                net_pnl = gross_pnl - self.fee_rate * 2
                trades.append(Trade(entry_time=str(entry_bar), exit_time=str(i),
                    entry_price=entry_price, exit_price=exit_price, side='long',
                    pnl=net_pnl * 100, exit_reason='max_hold'))
                equity *= (1 + net_pnl)
                equity_curve.append(equity)
                in_position = False
                i += 1
                continue

            # Explicit exit condition (V9: signal-reversal exit)
            # Takes priority over entry-signal flip when exit_signals are provided
            if exit_signals is not None and exit_signals[i] == 1:
                exit_price = opens[i + 1] * (1 - self.slippage) if i + 1 < n else closes[i] * (1 - self.slippage)
                gross_pnl = (exit_price - entry_price) / entry_price
                net_pnl = gross_pnl - self.fee_rate * 2
                trades.append(Trade(entry_time=str(entry_bar), exit_time=str(i),
                    entry_price=entry_price, exit_price=exit_price, side='long',
                    pnl=net_pnl * 100, exit_reason='exit_condition'))
                equity *= (1 + net_pnl)
                equity_curve.append(equity)
                in_position = False
                i += 1
                continue

            # Signal exit (legacy: entry condition no longer true)
            if signals[i] != 1:
                exit_price = opens[i + 1] * (1 - self.slippage) if i + 1 < n else closes[i] * (1 - self.slippage)
                gross_pnl = (exit_price - entry_price) / entry_price
                net_pnl = gross_pnl - self.fee_rate * 2
                trades.append(Trade(entry_time=str(entry_bar), exit_time=str(i),
                    entry_price=entry_price, exit_price=exit_price, side='long',
                    pnl=net_pnl * 100, exit_reason='signal_exit'))
                equity *= (1 + net_pnl)
                equity_curve.append(equity)
                in_position = False

            i += 1

        # Close open position at end
        if in_position:
            exit_price = closes[-1] * (1 - self.slippage)
            gross_pnl = (exit_price - entry_price) / entry_price
            net_pnl = gross_pnl - self.fee_rate * 2
            trades.append(Trade(entry_time=str(entry_bar), exit_time=str(n - 1),
                entry_price=entry_price, exit_price=exit_price, side='long',
                pnl=net_pnl * 100, exit_reason='end_of_data'))
            equity *= (1 + net_pnl)
            equity_curve.append(equity)

        if len(equity_curve) == 1:
            equity_curve.append(equity)

        result.trades = trades
        result.equity_curve = equity_curve
        return result