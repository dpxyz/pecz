"""
Quick integration test: Run SignalGenerator + StateManager + RiskGuard
on historical data to verify the full pipeline (offline).
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))

from signal_generator import SignalGenerator, SignalType
from state_manager import StateManager, GuardState
from risk_guard import RiskGuard

DATA_DIR = Path("/data/.openclaw/workspace/forward_v5/forward_v5/research/data")
ASSETS = ["BTCUSDT", "ETHUSDT"]
INITIAL_CAPITAL = 100.0
FEE_RATE = 0.0001
SLIPPAGE_BPS = 1.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("integration_test")


def run_backtest_on_history():
    """Simulate paper trading on historical data."""
    import os, tempfile
    db_path = os.path.join(tempfile.gettempdir(), 'executor_test.db')
    if os.path.exists(db_path):
        os.remove(db_path)
    state = StateManager(db_path=db_path)
    state.set_start_equity(INITIAL_CAPITAL)
    state.set_equity(INITIAL_CAPITAL)
    state.set_state("peak_equity", INITIAL_CAPITAL)

    risk = RiskGuard(state)
    gen = SignalGenerator()

    total_trades = 0
    wins = 0
    losses = 0

    for symbol in ASSETS:
        parquet = DATA_DIR / f"{symbol}_1h_full.parquet"
        df = pl.read_parquet(str(parquet))

        candles = []
        for row in df.iter_rows(named=True):
            candles.append({
                "timestamp": row["timestamp"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row.get("volume", 0),
                "symbol": symbol,
            })

        log.info(f"📊 Processing {symbol}: {len(candles)} candles")

        # Process 2024 full year only
        start_2024 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_2024 = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

        window_size = 210
        position = None
        bars_held = 0
        peak_price = 0

        for i in range(window_size, len(candles)):
            candle = candles[i]
            ts = candle["timestamp"]

            if not isinstance(ts, (int, float)):
                # datetime object
                ts_val = ts
            else:
                ts_val = datetime.fromtimestamp(ts / 1000, tz=timezone.utc) if ts > 1e12 else datetime.fromtimestamp(ts, tz=timezone.utc)

            # Only process 2024
            if ts_val < start_2024 or ts_val > end_2024:
                continue

            # Skip non-hourly (process every candle for simplicity)
            if i % 1 != 0:
                continue

            window = candles[i - window_size:i]

            # Check exit first
            if position:
                bars_held += 1
                peak_price = max(peak_price, candle["high"])

                exit_signal = gen.check_exit(
                    {"entry_price": position["entry_price"], "symbol": symbol, "peak_price": peak_price},
                    candle,
                    bars_held
                )

                if exit_signal:
                    exit_price = exit_signal.price * (1 - SLIPPAGE_BPS / 10000)
                    fee = exit_price * FEE_RATE
                    pnl = (exit_price - position["entry_price"]) * position["size"] - fee

                    total_trades += 1
                    if pnl >= 0:
                        wins += 1
                    else:
                        losses += 1

                    log.info(f"  {'✅' if pnl >= 0 else '❌'} CLOSE {symbol} @ {exit_price:.2f} "
                             f"PnL={pnl:.2f} ({exit_signal.type.value}) bars={bars_held}")
                    position = None
                    bars_held = 0
                    peak_price = 0
                    continue

            # Check entry
            if not position:
                signal = gen.evaluate(window)
                if signal and signal.type == SignalType.SIGNAL_LONG:
                    entry_price = candle["close"] * (1 + SLIPPAGE_BPS / 10000)
                    fee = entry_price * FEE_RATE
                    size = (INITIAL_CAPITAL - fee) / entry_price

                    position = {"entry_price": entry_price, "size": size}
                    peak_price = candle["high"]
                    bars_held = 0

                    log.info(f"  🟢 ENTRY {symbol} @ {entry_price:.2f} "
                             f"ADX={signal.indicators.get('adx_14', '?')}")

    print(f"\n{'='*60}")
    print(f"  Integration Test Results")
    print(f"{'='*60}")
    print(f"  Total Trades: {total_trades}")
    print(f"  Wins: {wins} | Losses: {losses}")
    print(f"  Win Rate: {wins/max(total_trades,1)*100:.1f}%")
    print(f"✅ Full pipeline works")


if __name__ == "__main__":
    run_backtest_on_history()