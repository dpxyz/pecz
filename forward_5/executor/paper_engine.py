"""
Executor V1 — Paper Trading Engine
Orchestrates Data Feed, Signal Generator, Position Manager, Risk Guard.
Runs on 1h candle close, deterministic execution, JSONL trade log.
"""

import asyncio
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent dir for imports when running standalone
sys.path.insert(0, str(Path(__file__).parent))

from data_feed import DataFeed, SYMBOL_MAP
from signal_generator import SignalGenerator, SignalType
from state_manager import StateManager, GuardState
from risk_guard import RiskGuard

log = logging.getLogger("paper_engine")

# ── Configuration ──

INITIAL_CAPITAL = 100.0
SLIPPAGE_BPS = 1.0  # 1 basis point simulated slippage
FEE_RATE = 0.0001   # 0.01% maker fee (Hyperliquid)
ASSETS = ["BTCUSDT", "ETHUSDT"]

# ── Trade Log (JSONL) ──

TRADE_LOG = Path(__file__).parent / "trades.jsonl"

def log_trade(event: dict):
    """Append trade event to JSONL file."""
    event["logged_at"] = datetime.now(timezone.utc).isoformat()
    with open(TRADE_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


class PaperTradingEngine:
    def __init__(self, assets: list[str] = None, db_path: str = "executor/state.db"):
        self.assets = assets or ASSETS
        self.state = StateManager(db_path=db_path)
        self.risk = RiskGuard(self.state)
        self.signal = SignalGenerator()
        self.feed = DataFeed(db_path=db_path, assets=self.assets, on_candle=self._on_candle)
        self._running = False
        self._last_candle_hour = {}  # track which hours we've processed

        # Initialize equity
        if not self.state.get_state("start_equity"):
            self.state.set_start_equity(INITIAL_CAPITAL)
            self.state.set_equity(INITIAL_CAPITAL)
            self.state.set_state("peak_equity", INITIAL_CAPITAL)

        log.info(f"PaperTradingEngine initialized: {self.assets}")
        log.info(f"  Capital: {INITIAL_CAPITAL}€ | Fee: {FEE_RATE*100}% | Slippage: {SLIPPAGE_BPS}bps")

    async def start(self):
        """Start the engine — connects to Hyperliquid WebSocket."""
        self._running = True
        log.info("🚀 Paper Trading Engine starting...")
        log.info(f"   Assets: {self.assets}")
        log.info(f"   Strategy: MACD Momentum + ADX+EMA regime filter")
        log.info(f"   Kill-switches: Daily>{self.risk.__class__.__name__}")
        log.info(f"   DB: {self.state.db_path}")
        log.info(f"   Trade log: {TRADE_LOG}")

        await self.feed.start()

    async def stop(self):
        self._running = False
        await self.feed.stop()
        log.info("Paper Trading Engine stopped")

    async def _on_candle(self, symbol: str, candle: dict):
        """Called by DataFeed when a new 1h candle arrives."""
        ts = candle.get("timestamp", 0)
        hour_key = f"{symbol}_{ts}"

        # Deduplicate: only process each candle once
        if hour_key in self._last_candle_hour:
            return
        self._last_candle_hour[hour_key] = True

        log.info(f"📊 {symbol} candle: close={candle['close']:.2f} @ {datetime.fromtimestamp(ts/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')}")

        # Store candle in state DB (data_feed already does this)
        # Evaluate signal
        await self._evaluate_symbol(symbol, candle)

    async def _evaluate_symbol(self, symbol: str, current_candle: dict):
        """Evaluate signal for a symbol using buffered candles."""
        # Get historical candles from DB
        candles_raw = self.state.get_state(f"last_candles_{symbol}")

        # Fetch from data_feed's SQLite
        candles = self.feed.get_candles(symbol, limit=210)

        if len(candles) < 210:
            log.info(f"  {symbol}: Only {len(candles)} candles, need 210 for warmup")
            return

        # Evaluate signal
        signal = self.signal.evaluate(candles)
        if not signal:
            return

        current_price = current_candle["close"]
        equity = self.state.get_equity()
        guard_state = self.state.get_guard_state()

        # ── Check exit for open position ──
        open_pos = self.state.get_open_position(symbol)
        if open_pos:
            # Update peak for trailing stop
            if current_candle["high"] > open_pos.get("peak_price", 0):
                self.state.update_peak(symbol, current_candle["high"])

            # Check exit conditions
            bars_held = self.state.get_state(f"bars_held_{symbol}", 0) + 1
            self.state.set_state(f"bars_held_{symbol}", bars_held)

            exit_signal = self.signal.check_exit(open_pos, current_candle, bars_held)
            if exit_signal:
                exit_price = exit_signal.price
                # Apply slippage
                exit_price *= (1 - SLIPPAGE_BPS / 10000)
                # Apply fee
                fee = exit_price * FEE_RATE

                pnl = (exit_price - open_pos["entry_price"]) * open_pos["size"] - fee
                self.state.close_position(symbol, exit_price, current_candle["timestamp"],
                                           exit_signal.reason, guard_state.value)
                self.risk.on_trade_closed(pnl)

                log_trade({
                    "event": "EXIT",
                    "symbol": symbol,
                    "side": "LONG",
                    "price": exit_price,
                    "size": open_pos["size"],
                    "pnl": pnl,
                    "equity": self.state.get_equity(),
                    "reason": exit_signal.reason,
                    "guard_state": guard_state.value,
                    "timestamp": current_candle["timestamp"],
                })
                # Reset bars held
                self.state.set_state(f"bars_held_{symbol}", 0)
                return

        # ── Check for new entry ──
        if signal.type == SignalType.SIGNAL_LONG:
            if open_pos:
                return  # Already in position

            # Risk guard check
            allowed, reason = self.risk.check_all(symbol)
            if not allowed:
                log.info(f"  🛑 {symbol} entry blocked: {reason}")
                log_trade({
                    "event": "ENTRY_BLOCKED",
                    "symbol": symbol,
                    "price": current_price,
                    "reason": reason,
                    "guard_state": guard_state.value,
                    "timestamp": current_candle["timestamp"],
                })
                return

            # Calculate position size (100% of equity, 1x leverage)
            entry_price = current_price * (1 + SLIPPAGE_BPS / 10000)  # Slippage on entry
            fee = entry_price * FEE_RATE
            size = (equity - fee) / entry_price  # Full capital, 1x leverage

            self.state.open_position(symbol, entry_price, current_candle["timestamp"],
                                     size, guard_state.value)

            log_trade({
                "event": "ENTRY",
                "symbol": symbol,
                "side": "LONG",
                "price": entry_price,
                "size": size,
                "equity": equity,
                "reason": signal.reason,
                "guard_state": guard_state.value,
                "indicators": signal.indicators,
                "timestamp": current_candle["timestamp"],
            })
            log.info(f"  🟢 ENTRY {symbol} @ {entry_price:.2f}, size={size:.6f}")

        elif signal.type == SignalType.SIGNAL_FLAT:
            log.debug(f"  {symbol}: No entry — {signal.reason}")


# ── Backfill: Load historical data from parquet ──

async def backfill_from_parquet(engine: PaperTradingEngine):
    """Load historical candles from parquet files to warm up indicators."""
    research_dir = Path(__file__).parent.parent / "research"
    for symbol in engine.assets:
        parquet_path = research_dir / "data" / f"{symbol}_1h_full.parquet"
        if not parquet_path.exists():
            log.warning(f"No parquet for {symbol} at {parquet_path}")
            continue

        import polars as pl
        df = pl.read_parquet(str(parquet_path))
        log.info(f"Backfilling {symbol}: {len(df)} candles from parquet")

        # Insert into data_feed's candle table
        with sqlite3.connect(engine.feed.db_path) as conn:
            for row in df.iter_rows(named=True):
                conn.execute("""
                    INSERT OR REPLACE INTO candles (symbol, ts, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (symbol, row["timestamp"], row["open"], row["high"],
                      row["low"], row["close"], row.get("volume", 0)))
        log.info(f"  ✅ {symbol}: {len(df)} candles backfilled")


# ── Main ──

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    engine = PaperTradingEngine(assets=ASSETS)

    # Backfill historical data first
    await backfill_from_parquet(engine)

    log.info("=" * 60)
    log.info("  PAPER TRADING ENGINE V1 — MACD+ADX+EMA Baseline")
    log.info("  Entry: macd_hist > 0 AND close > ema_50 AND ema_50 > ema_200 AND adx_14 > 20")
    log.info("  Exit:  trailing_stop 2%, stop_loss 2.5%, max_hold 48h")
    log.info("  Kill-switches: DailyLoss>5%, MaxDD>20%, MaxPositions=1, CL≥5")
    log.info("  Capital: 100€ | Leverage: 1x | Slippage: 1bp | Fee: 0.01%")
    log.info("=" * 60)

    try:
        await engine.start()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        await engine.stop()

    # Print final stats
    stats = engine.state.get_trade_stats()
    log.info(f"\n📊 Final Stats: {stats}")
    equity = engine.state.get_equity()
    start = engine.state.get_start_equity()
    log.info(f"💰 Final Equity: {equity:.2f}€ (started: {start:.2f}€, PnL: {equity-start:.2f}€)")


if __name__ == "__main__":
    asyncio.run(main())