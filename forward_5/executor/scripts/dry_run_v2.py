#!/usr/bin/env python3
"""
V2 Dry-Run: Replay historical V10 data through the V2 signal generator.
Simulates what the V2 engine would have done on real data.
"""

import sys
from pathlib import Path
import polars as pl
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from signal_generator_v2 import SignalGeneratorV2, SignalType

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "research" / "data_v10"

COST_RT = 0.001  # 0.1% round-trip

def run_dry_run():
    gen = SignalGeneratorV2()
    
    # V2 active assets
    assets = {
        "AVAXUSDT": {"direction": "LONG", "signal": "z<-1"},
        "BTCUSDT": {"direction": "LONG", "signal": "z<-1 bear-only"},
    }
    
    all_trades = {}
    
    for symbol, info in assets.items():
        print(f"\n{'='*60}")
        print(f"  {symbol} — {info['signal']}")
        print(f"{'='*60}")
        
        df = pl.read_parquet(DATA_DIR / f"{symbol}_1h_full.parquet").sort("timestamp")
        df = df.with_columns(
            pl.when(pl.col("funding_z").is_finite())
            .then(pl.col("funding_z"))
            .otherwise(None)
            .alias("funding_z")
        )
        df = df.with_columns(
            (pl.col("close").shift(-24) / pl.col("close") - 1).alias("ret_24h")
        )
        
        # Build candles list
        rows = df.iter_rows(named=True)
        all_candles = list(rows)
        
        # Track regime
        closes = df["close"]
        ema200 = closes.ewm_mean(alpha=2/201, min_samples=200)
        bull200_series = closes > ema200
        
        trades = []
        in_position = False
        entry_price = 0
        entry_ts = 0
        entry_side = "LONG"
        peak_price = 0
        trough_price = 0
        bars_held = 0
        cooldown_until_ts = 0
        
        # Start from candle 210 (EMA200 warmup)
        for i in range(210, len(all_candles) - 24):
            candle = all_candles[i]
            ts = candle["timestamp"]
            close = candle["close"]
            high = candle.get("high", close)
            low = candle.get("low", close)
            fz = candle.get("funding_z")
            bull = bool(bull200_series[i]) if bull200_series[i] is not None else True
            
            if fz is None or not np.isfinite(fz):
                bars_held += 1 if in_position else 0
                continue
            
            # Cooldown check
            if ts < cooldown_until_ts:
                continue
            
            # Check exit if in position
            if in_position:
                bars_held += 1
                
                # Update peak/trough
                if entry_side == "LONG" and high > peak_price:
                    peak_price = high
                elif entry_side == "SHORT" and low < trough_price:
                    trough_price = low
                
                pos = {
                    "entry_price": entry_price, 
                    "peak_price": peak_price,
                    "trough_price": trough_price,
                    "symbol": symbol, "side": entry_side,
                }
                current_candle = {"low": low, "high": high, "close": close, "timestamp": ts}
                exit_sig = gen.check_exit(pos, current_candle, bars_held, bull200=bull)
                
                if exit_sig:
                    # Calculate PnL
                    if entry_side == "LONG":
                        pnl_pct = (close - entry_price) / entry_price
                    else:
                        pnl_pct = (entry_price - close) / entry_price
                    
                    net_ret = pnl_pct - COST_RT
                    trades.append({
                        "entry_ts": entry_ts, "exit_ts": ts,
                        "entry_price": entry_price, "exit_price": close,
                        "side": entry_side, "pnl_pct": net_ret * 100,
                        "reason": exit_sig.reason[:40],
                        "bull200": bull,
                        "bars_held": bars_held,
                    })
                    
                    in_position = False
                    cooldown_until_ts = ts + 24 * 3600 * 1000  # 24h cooldown (funding is 8h-cyclical)
                    bars_held = 0
                    continue
            
            # Check entry
            if not in_position:
                # Build candle window for evaluate()
                window = all_candles[i-249:i+1] if i >= 249 else all_candles[:i+1]
                candle_list = [
                    {"timestamp": r["timestamp"], "open": r["open"], "high": r["high"],
                     "low": r["low"], "close": r["close"], "volume": r.get("volume", 0),
                     "symbol": symbol}
                    for r in window
                ]
                
                sig = gen.evaluate(candle_list, funding_z=fz, bull200=bull)
                
                if sig and sig.type in (SignalType.SIGNAL_LONG, SignalType.SIGNAL_SHORT):
                    in_position = True
                    entry_price = close
                    entry_ts = ts
                    entry_side = "LONG" if sig.type == SignalType.SIGNAL_LONG else "SHORT"
                    peak_price = close
                    trough_price = close
                    bars_held = 0
        
        # Calculate stats
        if trades:
            pnls = [t["pnl_pct"] for t in trades]
            wins = sum(1 for p in pnls if p > 0)
            
            # Time-based split for OOS (last 30%)
            all_ts = [t["entry_ts"] for t in trades]
            t_max = max(all_ts)
            t_split = t_max * 0.7 + min(all_ts) * 0.3
            is_trades = [t for t in trades if t["entry_ts"] <= t_split]
            oos_trades = [t for t in trades if t["entry_ts"] > t_split]
            
            print(f"\n  Total trades: {len(trades)}")
            print(f"  Win rate: {wins}/{len(trades)} = {wins/len(trades)*100:.1f}%")
            print(f"  Avg PnL: {np.mean(pnls):+.4f}%")
            print(f"  Cumulative: {sum(pnls):+.2f}%")
            
            if is_trades:
                is_pnls = [t["pnl_pct"] for t in is_trades]
                print(f"\n  IS ({len(is_trades)} trades): avg={np.mean(is_pnls):+.4f}%, cum={sum(is_pnls):+.2f}%")
            if oos_trades:
                oos_pnls = [t["pnl_pct"] for t in oos_trades]
                print(f"  OOS ({len(oos_trades)} trades): avg={np.mean(oos_pnls):+.4f}%, cum={sum(oos_pnls):+.2f}%")
                oos_wins = sum(1 for p in oos_pnls if p > 0)
                print(f"  OOS WR: {oos_wins}/{len(oos_trades)} = {oos_wins/len(oos_trades)*100:.1f}%")
            
            # Regime breakdown
            bull_trades = [t for t in trades if t["bull200"]]
            bear_trades = [t for t in trades if not t["bull200"]]
            if bull_trades:
                bp = [t["pnl_pct"] for t in bull_trades]
                print(f"\n  Bull regime: {len(bull_trades)} trades, avg={np.mean(bp):+.4f}%")
            if bear_trades:
                bp = [t["pnl_pct"] for t in bear_trades]
                print(f"  Bear regime: {len(bear_trades)} trades, avg={np.mean(bp):+.4f}%")
            
            all_trades[symbol] = trades
        else:
            print(f"\n  No trades generated")
            all_trades[symbol] = []
    
    # Portfolio summary
    print(f"\n{'='*60}")
    print(f"  PORTFOLIO SUMMARY")
    print(f"{'='*60}")
    
    all_pnls = []
    for sym, trades in all_trades.items():
        sym_pnls = [t["pnl_pct"] for t in trades]
        all_pnls.extend(sym_pnls)
        print(f"  {sym}: {len(trades)} trades, cum={sum(sym_pnls):+.2f}%")
    
    if all_pnls:
        print(f"\n  Total: {len(all_pnls)} trades")
        print(f"  Avg PnL: {np.mean(all_pnls):+.4f}%")
        print(f"  Cumulative: {sum(all_pnls):+.2f}%")
        wins = sum(1 for p in all_pnls if p > 0)
        print(f"  Win rate: {wins}/{len(all_pnls)} = {wins/len(all_pnls)*100:.1f}%")


if __name__ == "__main__":
    run_dry_run()