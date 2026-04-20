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
from discord_reporter import DiscordReporter, COLOR_BLUE
from command_listener import CommandListener

log = logging.getLogger("paper_engine")

# ── Configuration ──

INITIAL_CAPITAL = 100.0  # Total portfolio capital (NOT per asset)
SLIPPAGE_BPS = 1.0  # 1 basis point simulated slippage
FEE_RATE = 0.0001   # 0.01% maker fee (Hyperliquid)

# ╔══════════════════════════════════════════════════════════════╗
# ║  ⛔ PAPER MODE — HARD SWITCH                               ║
# ║  When PAPER_MODE=True, the engine NEVER sends real orders. ║
# ║  All trades are simulated locally. No real money at risk.  ║
# ║  Set to False ONLY after explicit human approval.          ║
# ╚══════════════════════════════════════════════════════════════╝
PAPER_MODE = True  # ⛔ NEVER set to False without Dave's explicit OK

ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]
# LINK replaced by DOGE — LINK not available on Hyperliquid Testnet

DISCORD_CHANNEL_ID = None  # Loaded from .env at runtime
DISCORD_WEBHOOK_URL = None  # Not used — OpenClaw message tool instead of webhook

# ── Leverage Tiers (ADR-007) ──
# Static, asset-specific. Based on backtest DD analysis.
# Tier 1 (1.8x): BTC, ETH — low volatility, deepest liquidity
# Tier 2 (1.5x): SOL, LINK, ADA — medium volatility
# Tier 3 (1.0x): AVAX — high volatility, conservative
LEVERAGE_TIERS = {
    "BTCUSDT":  1.8,
    "ETHUSDT":  1.8,
    "SOLUSDT":  1.5,
    "AVAXUSDT": 1.0,
    "DOGEUSDT": 1.5,  # Replaces LINK (not on Testnet)
    "ADAUSDT":  1.5,
}

DEFAULT_LEVERAGE = 1.0

# ── Trade Log (JSONL) ──

TRADE_LOG = Path(__file__).parent / "trades.jsonl"

def log_trade(event: dict):
    """Append trade event to JSONL file."""
    event["logged_at"] = datetime.now(timezone.utc).isoformat()
    with open(TRADE_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


class PaperTradingEngine:
    def __init__(self, assets: list[str] = None, db_path: str = "state.db"):
        self.assets = assets or ASSETS
        self.state = StateManager(db_path=db_path)
        self.risk = RiskGuard(self.state)
        self.signal = SignalGenerator()
        # Load Discord channel from .env
        from dotenv import load_dotenv
        import os
        load_dotenv(Path(__file__).parent / ".env")
        channel_id = os.environ.get("DISCORD_CHANNEL_ID", DISCORD_CHANNEL_ID)
        self.reporter = DiscordReporter(channel_id=channel_id)
        self.main_address = os.environ.get("HL_MAIN_ADDRESS", "")
        self.feed = DataFeed(db_path=db_path, assets=self.assets, on_candle=self._on_candle)
        self.commands = CommandListener(self, channel_id=channel_id)
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
        # ⛔ PAPER MODE GATE — abort if someone accidentally disabled it
        if not PAPER_MODE:
            log.critical("⛔⛔⛔ PAPER_MODE is OFF — REAL MONEY AT RISK ⛔⛔⛔")
            log.critical("Set PAPER_MODE=True in paper_engine.py or confirm with Dave first!")
            raise RuntimeError("PAPER_MODE=False requires explicit human approval. Engine aborted.")

        self._running = True
        log.info("🚀 Paper Trading Engine starting...")
        log.info("   ⛔ PAPER_MODE=TRUE — No real orders will be placed")
        log.info(f"   Assets: {self.assets}")
        log.info(f"   Strategy: MACD Momentum + ADX+EMA regime filter")
        log.info(f"   Capital: {INITIAL_CAPITAL}€ | Fee: {FEE_RATE*100}% | Slippage: {SLIPPAGE_BPS}bps")
        log.info(f"   DB: {self.state.db_path}")
        log.info(f"   Trade log: {TRADE_LOG}")

        # Record engine start time
        self.state.set_state("engine_start_time", int(datetime.now(timezone.utc).timestamp()))

        # Check Hyperliquid testnet balance
        balance_str = ""
        if self.main_address:
            try:
                import urllib.request
                url = "https://api.hyperliquid-testnet.xyz/info"
                data = json.dumps({"type": "clearinghouseState", "user": self.main_address.lower()}).encode()
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                resp = urllib.request.urlopen(req, timeout=10)
                state = json.loads(resp.read())
                val = state.get("marginSummary", {}).get("accountValue", "0")
                balance_str = f"\n💰 Testnet Balance: ${val} (Main: {self.main_address[:10]}...)"
            except Exception as e:
                balance_str = f"\n⚠️ Balance check failed: {e}"

        # Send startup message to Discord — Components v2 container
        # ⛔ PAPER MODE SAFETY — startup message
        tier_str = ', '.join(f"{s}@{LEVERAGE_TIERS.get(s, 1.0)}x" for s in self.assets)
        header = "🚀 **Paper Trading Engine V1 Started**"
        body = (
            f"⛔ **PAPER MODE — NO REAL ORDERS**\n"
            f"Assets: {tier_str}\n"
            f"Strategy: MACD+ADX+EMA Baseline (ADR-007 tiers)\n"
            f"Capital: {INITIAL_CAPITAL}€ total ({INITIAL_CAPITAL/len(self.assets):.1f}€/asset)\n"
            f"Kill-switches: DailyLoss>5%, MaxDD>20%, MaxPos=1, CL≥5\n"
            f"Commands: !kill, !resume, !status, !help"
            f"{balance_str}"
        )
        self.reporter._send_container(header, body, COLOR_BLUE)

        # Start command listener and data feed concurrently
        await asyncio.gather(
            self.commands.start(),
            self.feed.start(),
        )

    async def stop(self):
        self._running = False
        await self.commands.stop()
        await self.feed.stop()
        log.info("Paper Trading Engine stopped")

    async def _on_candle(self, symbol: str, candle: dict):
        """Called by DataFeed when a CLOSED 1h candle arrives.
        
        Note: DataFeed now filters partial candles — only CLOSED candles
        (where close_time < now) trigger this callback. This ensures we
        only evaluate signals on complete candle data, matching backtest logic.
        """
        ts = candle.get("timestamp", 0)
        hour_key = f"{symbol}_{ts}"

        # Deduplicate: only process each closed candle once
        if hour_key in self._last_candle_hour:
            return
        self._last_candle_hour[hour_key] = True

        log.info(f"📊 {symbol} CLOSED candle: close={candle['close']:.2f} @ {datetime.fromtimestamp(ts/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")

        # Evaluate signal using DB candle history
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
                # Fee on the actual position value (leveraged)
                leverage = LEVERAGE_TIERS.get(symbol, DEFAULT_LEVERAGE)
                fee = open_pos["size"] * exit_price * FEE_RATE * leverage

                pnl = (exit_price - open_pos["entry_price"]) * open_pos["size"] - fee
                # ⚠️ BUG 2 FIX: Pass NET PnL to close_position so trades table is correct
                # (Previously close_position recalculated GROSS PnL, missing the exit fee)
                self.state.close_position(symbol, exit_price, current_candle["timestamp"],
                                           exit_signal.reason, guard_state.value,
                                           net_pnl=pnl)
                self.risk.on_trade_closed(pnl)

                exit_event = {
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
                }
                log_trade(exit_event)
                self.reporter.report_exit(exit_event)
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
                self.reporter.report_entry_blocked({
                    "event": "ENTRY_BLOCKED",
                    "symbol": symbol,
                    "price": current_price,
                    "reason": reason,
                    "guard_state": guard_state.value,
                    "timestamp": current_candle["timestamp"],
                })
                log_trade({
                    "event": "ENTRY_BLOCKED",
                    "symbol": symbol,
                    "price": current_price,
                    "reason": reason,
                    "guard_state": guard_state.value,
                    "timestamp": current_candle["timestamp"],
                })
                return

            # Calculate position size: equal-weight allocation from total equity
            # 100€ total / 6 assets = ~16.67€ per position, then apply leverage
            # Fee is proportional to position value: fee = size * price * rate * leverage
            # So: size * price * (1 + fee_rate * leverage) = allocation * leverage
            #     size = (allocation * leverage) / (price * (1 + fee_rate * leverage))
            allocation = equity / len(self.assets)  # Equal weight per asset
            leverage = LEVERAGE_TIERS.get(symbol, DEFAULT_LEVERAGE)
            entry_price = current_price * (1 + SLIPPAGE_BPS / 10000)  # Slippage on entry
            size = (allocation * leverage) / (entry_price * (1 + FEE_RATE * leverage))
            fee = size * entry_price * FEE_RATE * leverage  # Actual fee on leveraged position

            # ⚠️ BUG 1 FIX: Deduct entry fee from equity immediately
            # The fee is real money spent on the trade — must reduce equity.
            # (Previously only exit fee was deducted on close, overstating equity.)
            self.state.set_equity(equity - fee)

            self.state.open_position(symbol, entry_price, current_candle["timestamp"],
                                     size, guard_state.value)

            entry_event = {
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
            }
            log_trade(entry_event)
            self.reporter.report_entry(entry_event)
            log.info(f"  🟢 ENTRY {symbol} @ {entry_price:.2f}, size={size:.6f}")

        elif signal.type == SignalType.SIGNAL_FLAT:
            log.debug(f"  {symbol}: No entry — {signal.reason}")


# ── Backfill: Load historical data from Hyperliquid Testnet API ──

async def backfill_from_api(engine: PaperTradingEngine):
    """Load historical candles from Hyperliquid Testnet REST API.
    
    This replaces the old parquet backfill. Testnet prices differ from mainnet,
    so we MUST use testnet data for consistent indicator calculations.
    
    Returns ~5000 1h candles per asset (Sep 2025 to now), which is more than
    enough for EMA-200 warmup (210 candles needed).
    """
    import urllib.request
    
    api_url = "https://api.hyperliquid-testnet.xyz/info"
    start_time = 1758679200000  # Sep 24, 2025 (earliest available on testnet)
    
    if PAPER_MODE:
        api_url = "https://api.hyperliquid-testnet.xyz/info"
    else:
        api_url = "https://api.hyperliquid.xyz/info"
    
    total_inserted = 0
    
    for symbol in engine.assets:
        coin = SYMBOL_MAP.get(symbol, symbol.replace("USDT", ""))
        
        payload = json.dumps({
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": "1h",
                "startTime": start_time,
            }
        }).encode()
        
        req = urllib.request.Request(api_url, data=payload, headers={"Content-Type": "application/json"})
        
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
        except Exception as e:
            log.error(f"Backfill API failed for {symbol}: {e}")
            continue
        
        if not isinstance(data, list):
            log.error(f"Unexpected backfill response for {symbol}")
            continue
        
        inserted = 0
        with sqlite3.connect(engine.feed.db_path) as conn:
            for candle in data:
                ts = int(candle["t"])
                o = float(candle["o"])
                h = float(candle["h"])
                l = float(candle["l"])
                c = float(candle["c"])
                v = float(candle.get("v", 0))
                
                conn.execute("""
                    INSERT OR REPLACE INTO candles (symbol, ts, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (symbol, ts, o, h, l, c, v))
                inserted += 1
        
        total_inserted += inserted
        log.info(f"  ✅ {symbol}: {inserted} candles backfilled from API")
    
    log.info(f"Backfill complete: {total_inserted} candles total")
    
    # ⚠️ BUG 10 FIX: Verify each asset has enough candles for warmup
    min_required = 210  # EMA-200 + 10 buffer
    for symbol in engine.assets:
        count = len(engine.feed.get_candles(symbol, limit=500))
        if count < min_required:
            log.error(f"⚠️ {symbol}: Only {count} candles after backfill (need {min_required})!")
            log.error(f"  Engine will not produce signals until {min_required - count} more hours pass")
        else:
            log.info(f"  ✅ {symbol}: {count} candles — warmup OK")


# ── Main ──

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    engine = PaperTradingEngine(assets=ASSETS)

    # Backfill historical data from API first
    await backfill_from_api(engine)

    log.info("=" * 60)
    log.info("  PAPER TRADING ENGINE V1 — MACD+ADX+EMA Baseline")
    log.info("  Entry: macd_hist > 0 AND close > ema_50 AND ema_50 > ema_200 AND adx_14 > 20")
    log.info("  Exit:  trailing_stop 2%, stop_loss 2.5%, max_hold 48h")
    log.info("  Kill-switches: DailyLoss>5%, MaxDD>20%, MaxPositions=1, CL≥5")
    log.info(f"  Leverage Tiers (ADR-007): {LEVERAGE_TIERS}")
    log.info("  Capital: 100€ total (~16.67€/asset) | Slippage: 1bp | Fee: 0.01%")
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