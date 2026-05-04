"""
Phase 1.1: 4h Sweep Backtest Engine

Simple event-driven backtest for 4h bars.
- Entry: funding z-score in range + optional bull filter
- Exit: time-based (hold_hours) or stop-loss
- No trailing (proven to destroy performance)
- Returns: trade log + performance metrics
"""

import numpy as np
import polars as pl
from dataclasses import dataclass, field
from typing import Optional

from sweep_4h_signals import SignalHypothesis
from sweep_4h_data import AssetData4h


@dataclass
class Trade:
    entry_idx: int
    exit_idx: int
    entry_price: float
    exit_price: float
    direction: str  # "long" or "short"
    entry_z: float
    hold_bars: int
    pnl_pct: float
    hit_sl: bool


@dataclass
class BacktestResult:
    hypothesis: SignalHypothesis
    n_trades: int
    win_rate: float
    avg_pnl_pct: float
    total_return_pct: float
    max_dd_pct: float
    sharpe: float
    trades: list[Trade] = field(default_factory=list)


def run_backtest(data: AssetData4h, hyp: SignalHypothesis) -> BacktestResult:
    """Run a single backtest for one hypothesis on one asset."""
    df = data.df
    n = len(df)
    
    # Extract arrays for speed
    close = df["close"].to_numpy().astype(float)
    high = df["high"].to_numpy().astype(float)
    low = df["low"].to_numpy().astype(float)
    funding_z = df["funding_z"].to_numpy() if "funding_z" in df.columns else np.full(n, np.nan)
    bull200 = df["bull200"].to_numpy() if "bull200" in df.columns else np.ones(n, dtype=np.int8)
    bull50 = df["bull50"].to_numpy() if "bull50" in df.columns else np.ones(n, dtype=np.int8)
    
    hold_bars = hyp.hold_hours // 4  # Convert hours to 4h bars
    
    # Skip NaN-heavy regions
    valid_start = 50  # EMA200 warmup
    
    trades: list[Trade] = []
    in_trade = False
    entry_idx = 0
    entry_price = 0.0
    
    for i in range(valid_start, n):
        # If in a trade, check exit conditions
        if in_trade:
            bars_held = i - entry_idx
            hit_sl = False
            exit_price = None
            
            # Stop-loss check
            if hyp.sl_pct > 0:
                if hyp.direction == "long":
                    sl_price = entry_price * (1 - hyp.sl_pct / 100)
                    if low[i] <= sl_price:
                        exit_price = sl_price
                        hit_sl = True
                else:  # short
                    sl_price = entry_price * (1 + hyp.sl_pct / 100)
                    if high[i] >= sl_price:
                        exit_price = sl_price
                        hit_sl = True
            
            # Time-based exit
            if bars_held >= hold_bars:
                if exit_price is None:
                    exit_price = close[i]
            
            # Exit if triggered
            if exit_price is not None:
                if hyp.direction == "long":
                    pnl = (exit_price - entry_price) / entry_price * 100
                else:
                    pnl = (entry_price - exit_price) / entry_price * 100
                
                trades.append(Trade(
                    entry_idx=entry_idx,
                    exit_idx=i,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    direction=hyp.direction,
                    entry_z=funding_z[entry_idx] if not np.isnan(funding_z[entry_idx]) else 0.0,
                    hold_bars=bars_held,
                    pnl_pct=pnl,
                    hit_sl=hit_sl,
                ))
                in_trade = False
        
        # Check entry conditions (only if not in trade)
        if not in_trade and not np.isnan(funding_z[i]):
            # Z-score range check
            z_in_range = hyp.entry_z_low <= funding_z[i] < hyp.entry_z_high
            
            # Bull filter check
            bull_ok = True
            if hyp.bull_filter == "bull200":
                bull_ok = bull200[i] == 1
            elif hyp.bull_filter == "bull50":
                bull_ok = bull50[i] == 1
            
            if z_in_range and bull_ok:
                in_trade = True
                entry_idx = i
                entry_price = close[i]
    
    # Compute metrics
    if len(trades) == 0:
        return BacktestResult(
            hypothesis=hyp, n_trades=0, win_rate=0.0,
            avg_pnl_pct=0.0, total_return_pct=0.0,
            max_dd_pct=0.0, sharpe=0.0, trades=[],
        )
    
    pnls = np.array([t.pnl_pct for t in trades])
    wins = pnls > 0
    win_rate = wins.sum() / len(pnls)
    avg_pnl = pnls.mean()
    
    # Cumulative return (compounding)
    cum_returns = np.cumprod(1 + pnls / 100) * 100
    total_return = cum_returns[-1] - 100
    
    # Max drawdown
    peak = np.maximum.accumulate(cum_returns)
    dd = (cum_returns - peak) / peak * 100
    max_dd = dd.min()
    
    # Sharpe (annualized, 4h bars ~6 per day)
    if pnls.std() > 0:
        sharpe = (pnls.mean() / pnls.std()) * np.sqrt(6 * 365)
    else:
        sharpe = 0.0
    
    return BacktestResult(
        hypothesis=hyp, n_trades=len(trades), win_rate=win_rate,
        avg_pnl_pct=avg_pnl, total_return_pct=total_return,
        max_dd_pct=max_dd, sharpe=sharpe, trades=trades,
    )


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
    
    from sweep_4h_data import load_all_4h
    from sweep_4h_signals import generate_hypotheses
    
    data = load_all_4h()
    hyps = generate_hypotheses()
    
    # Quick test: run the SOL champion hypothesis
    sol_data = data.get("SOL")
    if sol_data:
        champion = SignalHypothesis(
            name="SOL_mild_neg_champion_4h",
            asset="SOL", direction="long",
            entry_z_low=-0.5, entry_z_high=0.0,
            bull_filter="none", hold_hours=24, sl_pct=5.0, trail_pct=0.0,
        )
        result = run_backtest(sol_data, champion)
        print(f"\n{champion.name}:")
        print(f"  Trades: {result.n_trades}")
        print(f"  Win Rate: {result.win_rate:.1%}")
        print(f"  Avg PnL: {result.avg_pnl_pct:.2f}%")
        print(f"  Total Return: {result.total_return_pct:.1f}%")
        print(f"  Max DD: {result.max_dd_pct:.1f}%")
        print(f"  Sharpe: {result.sharpe:.2f}")