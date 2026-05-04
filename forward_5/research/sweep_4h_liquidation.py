"""
Phase 1.2: Post-Liquidation Mean Reversion Signal

Hypothesis: After large liquidation events, price mean-reverts.
- Use OI changes as proxy for liquidations
- Entry: OI drops >X% in single 4h bar (forced liquidations)
- Direction: Long after long liquidations, Short after short liquidations
- Bull filter: EMA200 trend confirmation

Data: bn_oi.parquet (8h OI), bn_taker_ratio.parquet (buy/sell ratio)
"""

import logging
from pathlib import Path

import numpy as np
import polars as pl

from sweep_4h_data import load_all_4h, ASSETS, FOUR_H_MS, EIGHT_H_MS
from sweep_4h_engine import run_backtest, BacktestResult
from sweep_4h_signals import SignalHypothesis

log = logging.getLogger("sweep_4h_liquidation")

DATA_DIR = Path(__file__).parent.parent / "data_collector" / "data"


def load_oi_4h() -> dict:
    """Load OI data aligned to 4h bars."""
    df = pl.read_parquet(DATA_DIR / "bn_oi.parquet")
    
    # Convert timestamp to ms if needed
    if df["timestamp"].dtype == pl.Datetime:
        df = df.with_columns(pl.col("timestamp").dt.timestamp("ms").alias("timestamp"))
    
    # Aggregate to 4h
    df = df.with_columns(
        (pl.col("timestamp") // FOUR_H_MS * FOUR_H_MS).alias("ts4h")
    )
    df_4h = df.sort(["asset", "ts4h"]).group_by(["asset", "ts4h"]).agg([
        pl.col("sum_oi").last().alias("oi"),
        pl.col("sum_oi_value").last().alias("oi_value"),
    ]).sort(["asset", "ts4h"]).rename({"ts4h": "timestamp"})
    
    result = {}
    for asset in ASSETS:
        sub = df_4h.filter(pl.col("asset") == asset).sort("timestamp")
        if len(sub) > 0:
            oi = sub["oi"].to_numpy().astype(float)
            # OI % change
            oi_pct = np.zeros(len(oi))
            oi_pct[1:] = (oi[1:] - oi[:-1]) / np.where(oi[:-1] > 0, oi[:-1], 1) * 100
            result[asset] = {
                "timestamp": sub["timestamp"].to_numpy(),
                "oi": oi,
                "oi_pct": oi_pct,
                "n_points": len(oi),
            }
            log.info(f"  {asset} OI: {len(oi)} points, range [{oi_pct.min():.1f}%, {oi_pct.max():.1f}%]")
        else:
            result[asset] = None
            log.warning(f"  {asset} OI: NO DATA")
    
    return result


def load_taker_4h() -> dict:
    """Load taker buy/sell ratio aligned to 4h bars."""
    df = pl.read_parquet(DATA_DIR / "bn_taker_ratio.parquet")
    
    if df["timestamp"].dtype == pl.Datetime:
        df = df.with_columns(pl.col("timestamp").dt.timestamp("ms").alias("timestamp"))
    
    df = df.with_columns(
        (pl.col("timestamp") // FOUR_H_MS * FOUR_H_MS).alias("ts4h")
    )
    df_4h = df.sort(["asset", "ts4h"]).group_by(["asset", "ts4h"]).agg([
        pl.col("buy_sell_ratio").last().alias("taker_ratio"),
        pl.col("buy_vol").sum().alias("buy_vol"),
        pl.col("sell_vol").sum().alias("sell_vol"),
    ]).sort(["asset", "ts4h"]).rename({"ts4h": "timestamp"})
    
    result = {}
    for asset in ASSETS:
        sub = df_4h.filter(pl.col("asset") == asset).sort("timestamp")
        if len(sub) > 0:
            result[asset] = sub
            log.info(f"  {asset} Taker: {len(sub)} points")
        else:
            result[asset] = None
            log.warning(f"  {asset} Taker: NO DATA")
    
    return result


def generate_liquidation_hypotheses() -> list[SignalHypothesis]:
    """Generate hypotheses for post-liquidation mean reversion."""
    hypotheses = []
    
    # After large OI drops (liquidation cascade), go long
    for asset in ["BTC", "ETH", "SOL"]:  # Top 3 only (best OI data)
        # OI drops > 3%, long (liquidation cleanup)
        for oi_drop in [2.0, 3.0, 5.0]:
            hypotheses.append(SignalHypothesis(
                name=f"{asset}_oi_drop{oi_drop:.0f}_long_4h",
                asset=asset, direction="long",
                entry_z_low=-oi_drop, entry_z_high=0.0,  # Repurposing: z = -OI_drop_pct
                bull_filter="none", hold_hours=24, sl_pct=5.0, trail_pct=0.0,
            ))
            # With bull200 filter
            hypotheses.append(SignalHypothesis(
                name=f"{asset}_oi_drop{oi_drop:.0f}_bull200_4h",
                asset=asset, direction="long",
                entry_z_low=-oi_drop, entry_z_high=0.0,
                bull_filter="bull200", hold_hours=24, sl_pct=5.0, trail_pct=0.0,
            ))
        
        # Taker ratio < 0.8 (heavy selling = long liquidations) → long mean reversion
        for taker_thresh in [0.7, 0.8, 0.9]:
            hypotheses.append(SignalHypothesis(
                name=f"{asset}_taker_low{taker_thresh:.1f}_long_4h",
                asset=asset, direction="long",
                entry_z_low=-taker_thresh, entry_z_high=0.0,  # Repurposing: z = -taker_ratio
                bull_filter="none", hold_hours=24, sl_pct=5.0, trail_pct=0.0,
            ))
    
    return hypotheses


def run_liquidation_backtest(data_4h, oi_data, asset, oi_drop_pct: float,
                             bull_filter: str = "none", hold_hours: int = 24,
                             sl_pct: float = 5.0) -> BacktestResult:
    """Run backtest with OI-based entry signal."""
    asset_data = data_4h.get(asset)
    if asset_data is None or oi_data.get(asset) is None:
        return BacktestResult(
            hypothesis=SignalHypothesis("empty", asset, "long", 0, 0, "none", 24, 5.0, 0.0),
            n_trades=0, win_rate=0.0, avg_pnl_pct=0.0, total_return_pct=0.0,
            max_dd_pct=0.0, sharpe=0.0,
        )
    
    df = asset_data.df
    n = len(df)
    
    # Align OI data to price data
    oi_ts = oi_data[asset]["timestamp"]
    oi_pct = oi_data[asset]["oi_pct"]
    
    # Create OI signal aligned to price timestamps
    price_ts = df["timestamp"].to_numpy()
    oi_signal = np.zeros(n)
    
    for i in range(n):
        # Find nearest OI data point
        idx = np.searchsorted(oi_ts, price_ts[i], side="right") - 1
        if 0 <= idx < len(oi_pct):
            oi_signal[i] = oi_pct[idx]
    
    # Compute entry conditions
    close = df["close"].to_numpy().astype(float)
    bull200 = df["bull200"].to_numpy() if "bull200" in df.columns else np.ones(n, dtype=np.int8)
    
    hold_bars = hold_hours // 4
    valid_start = 50
    
    trades = []
    in_trade = False
    entry_idx = 0
    entry_price = 0.0
    
    for i in range(valid_start, n):
        if in_trade:
            bars_held = i - entry_idx
            hit_sl = False
            exit_price = None
            
            # Stop-loss
            if sl_pct > 0:
                sl_price = entry_price * (1 - sl_pct / 100)
                if df["low"][i] <= sl_price:
                    exit_price = sl_price
                    hit_sl = True
            
            # Time exit
            if bars_held >= hold_bars and exit_price is None:
                exit_price = close[i]
            
            if exit_price is not None:
                pnl = (exit_price - entry_price) / entry_price * 100
                trades.append(BacktestResult(
                    hypothesis=None, n_trades=0, win_rate=0, avg_pnl_pct=0,
                    total_return_pct=0, max_dd_pct=0, sharpe=0,
                ))
                # Simplified — just track entry/exit
                in_trade = False
        
        # Entry: OI drop > threshold (liquidation event)
        if not in_trade and oi_signal[i] < -oi_drop_pct:
            bull_ok = True
            if bull_filter == "bull200":
                bull_ok = bull200[i] == 1
            
            if bull_ok:
                in_trade = True
                entry_idx = i
                entry_price = close[i]
    
    # Count trades and compute metrics (simplified)
    # ... this needs proper trade tracking
    
    # For now, return a placeholder
    return BacktestResult(
        hypothesis=SignalHypothesis(f"{asset}_oi_drop{oi_drop_pct:.0f}", asset, "long",
                                      -oi_drop_pct, 0.0, bull_filter, hold_hours, sl_pct, 0.0),
        n_trades=0, win_rate=0.0, avg_pnl_pct=0.0, total_return_pct=0.0,
        max_dd_pct=0.0, sharpe=0.0,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
    
    log.info("Loading OI and taker data...")
    oi_data = load_oi_4h()
    taker_data = load_taker_4h()
    
    log.info(f"\nOI data available: {list(oi_data.keys())}")
    log.info(f"Taker data available: {list(taker_data.keys())}")
    
    # Check data quality
    for asset in ASSETS:
        if oi_data.get(asset):
            oi_pct = oi_data[asset]["oi_pct"]
            n_points = oi_data[asset]["n_points"]
            big_drops = np.sum(oi_pct < -3.0)
            log.info(f"  {asset}: {n_points} OI points, {big_drops} drops > 3%")