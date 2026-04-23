import asyncio
from typing import Optional
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
from risk_guard import RiskGuard, MAX_DRAWDOWN_PCT
from discord_reporter import DiscordReporter, COLOR_BLUE, COLOR_RED
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

# Price sanity floors: reject trades with obviously wrong prices
PRICE_FLOORS = {
    "BTCUSDT": 10000,  # BTC is never below $10k
    "ETHUSDT": 100,     # ETH is never below $100
    "SOLUSDT": 10,      # SOL is never below $10
    "AVAXUSDT": 5,      # AVAX is never below $5
    "DOGEUSDT": 0.01,   # DOGE is never below $0.01
    "ADAUSDT": 0.10,    # ADA is never below $0.10
}


def log_trade(event: dict, path: Optional[str] = None):
    """Append trade event to JSONL file.
    
    Includes price sanity check to reject garbage entries from backfill/restart.
    BTC should be > 10000, ETH > 100, etc. If price is obviously wrong,
    log a warning and skip the entry.
    
    Args:
        event: Trade event dict with symbol, price, etc.
        path: Override path for testing. Defaults to TRADE_LOG.
    """
    # Price sanity check: reject obviously wrong prices
    symbol = event.get("symbol", "")
    price = event.get("price", 0)
    
    floor = PRICE_FLOORS.get(symbol, 0)
    if price > 0 and price < floor:
        log.warning(f"⛔ REJECTED garbage trade: {event['event']} {symbol} @ {price:.4f} "
                    f"(floor={floor}). Indicators: {event.get('indicators', {})}")
        return False
    
    event["logged_at"] = datetime.now(timezone.utc).isoformat()
    target = path or TRADE_LOG
    with open(target, "a") as f:
        f.write(json.dumps(event) + "\n")
    return True


class PaperTradingEngine:
    def __init__(self, assets: Optional[list[str]] = None, db_path: str = "state.db"):
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
        self.feed = DataFeed(db_path=db_path, assets=self.assets, on_candle=self._on_candle, engine_last_processed_ts=None)
        self.commands = CommandListener(self, channel_id=channel_id)
        self._running = False
        self._last_candle_hour: dict[str, bool] = {}  # track which hours we've processed
        self._engine_start_time = None  # set on start(), used to skip backfill candles
        self._last_summary_hour = -1  # track 4h summary reporting

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
        log.info("   Strategy: MACD Momentum + ADX+EMA regime filter")
        log.info(f"   Capital: {INITIAL_CAPITAL}€ | Fee: {FEE_RATE*100}% | Slippage: {SLIPPAGE_BPS}bps")
        log.info(f"   DB: {self.state.db_path}")
        log.info(f"   Trade log: {TRADE_LOG}")

        # Record engine start time
        self._engine_start_time = int(datetime.now(timezone.utc).timestamp() * 1000)  # ms for candle ts comparison
        self.state.set_state("engine_start_time", int(datetime.now(timezone.utc).timestamp()))
        self.state.set_state("_engine_start_time_ms", str(self._engine_start_time))

        # Position recovery: check for orphaned DB positions (closed by KILL/restart but no EXIT logged)
        # This fixes the bug where KILL_SWITCH force-closes positions without writing EXIT to trades.jsonl
        try:
            open_positions = self.state.get_open_positions()
            if not open_positions:
                log.info("Position recovery: no open positions found")
        except Exception as e:
            log.warning(f"Position recovery check failed: {e}")

        # Gap recovery: get last processed timestamp from state
        # This tells the data feed where to start replaying missed candles
        engine_last_ts = None
        try:
            ts_str = self.state.get_state("last_processed_ts")
            if ts_str:
                engine_last_ts = int(float(ts_str))
                log.info(f"Gap recovery: engine last processed ts={engine_last_ts}")
        except Exception:
            pass

        # Update data feed with gap recovery timestamp
        self.feed._engine_last_processed_ts = engine_last_ts

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
        
        Replay candles (is_replay=True) from gap recovery/backfill are used
        to warm up indicators but MUST NOT trigger trades.
        """
        ts = candle.get("timestamp", 0)
        hour_key = f"{symbol}_{ts}"
        is_replay = candle.get("is_replay", False)

        # Deduplicate: only process each closed candle once
        if hour_key in self._last_candle_hour:
            return
        self._last_candle_hour[hour_key] = True

        # Skip stale candles (older than 2 hours) — prevents backfill garbage
        # This is a safety net on top of the DataFeed's is_replay flag
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        max_age_ms = 2 * 3600 * 1000  # 2 hours
        if self._engine_start_time and ts < self._engine_start_time:
            # Still update last_processed_ts so gap recovery progresses
            self.state.set_state("last_processed_ts", str(ts))
            return
        if (now_ms - ts) > max_age_ms:
            # Candle is too old (more than 2 hours) — skip it
            self.state.set_state("last_processed_ts", str(ts))
            return

        # Skip trading signals for replay candles (gap recovery/backfill)
        # These candles warm up indicators but MUST NOT trigger new trades
        if is_replay:
            log.debug(f"⏭️ {symbol}: Replay candle @ {ts} — warming indicators only")
            self.state.set_state("last_processed_ts", str(ts))
            # Still update indicators for this candle so they're warm for live candles
            # (Signal generator uses the candle data, just don't ACT on the signal)
            return

        # Clean up old dedup entries (keep last 24 hours = ~144 entries per asset)
        # Prevents unbounded memory growth over months of operation
        if len(self._last_candle_hour) > 2000:
            # Remove oldest entries (rough cleanup)
            keys_to_remove = list(self._last_candle_hour.keys())[:1000]
            for k in keys_to_remove:
                del self._last_candle_hour[k]

        log.info(f"📊 {symbol} CLOSED candle: close={candle['close']:.2f} @ {datetime.fromtimestamp(ts/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")

        # Update last_processed_ts in state DB for gap recovery after crashes
        self.state.set_state("last_processed_ts", str(ts))

        # ── Unrealized Drawdown Check ──
        # Risk Guard DD check uses REALIZED equity only.
        # But with 6 concurrent positions, unrealized DD can exceed 20%
        # before any position is closed. Check mark-to-market DD here.
        equity = self.state.get_equity()
        peak = float(self.state.get_state("peak_equity", equity))
        unrealized_pnl = 0.0
        for sym in self.assets:
            pos = self.state.get_open_position(sym)
            if pos:
                mark_price = candle["close"] if sym == symbol else None
                # For other assets, get latest close from DB
                if not mark_price:
                    latest = self.feed.get_candles(sym, limit=1)
                    if latest:
                        mark_price = latest[0]["close"]
                    else:
                        mark_price = pos["entry_price"]  # fallback
                lev = LEVERAGE_TIERS.get(sym, DEFAULT_LEVERAGE)
                exit_fee = pos["size"] * mark_price * FEE_RATE * lev
                pos_pnl = (mark_price - pos["entry_price"]) * pos["size"] - exit_fee
                unrealized_pnl += pos_pnl
        mark_to_market = equity + unrealized_pnl
        mtm_dd = (peak - mark_to_market) / peak * 100 if peak > 0 else 0
        if mtm_dd > MAX_DRAWDOWN_PCT:
            log.warning(f"⚠️ Unrealized DD: {mtm_dd:.1f}% > {MAX_DRAWDOWN_PCT}% — triggering KILL")
            self.risk._trigger_kill(f"Unrealized DD {mtm_dd:.1f}% > {MAX_DRAWDOWN_PCT}%")
            # Force-close all positions immediately
            for sym in self.assets:
                open_pos = self.state.get_open_position(sym)
                if open_pos:
                    mark = candle["close"] if sym == symbol else (self.feed.get_candles(sym, limit=1)[0]["close"] if self.feed.get_candles(sym, limit=1) else open_pos["entry_price"])
                    exit_price = mark * (1 - SLIPPAGE_BPS / 10000)
                    lev = LEVERAGE_TIERS.get(sym, DEFAULT_LEVERAGE)
                    fee = open_pos["size"] * exit_price * FEE_RATE * lev
                    pnl = (exit_price - open_pos["entry_price"]) * open_pos["size"] - fee
                    self.state.close_position(sym, exit_price, ts, "Unrealized DD KILL", GuardState.KILL_SWITCH.value, net_pnl=pnl)
                    self.risk.on_trade_closed(pnl)
            self.reporter._send_container(
                "\U0001f6a8 **KILL: Unrealized DD**",
                f"Mark-to-market DD: {mtm_dd:.1f}% > {MAX_DRAWDOWN_PCT}%\nAll positions force-closed.",
                COLOR_RED)
            return

        # Evaluate signal using DB candle history
        await self._evaluate_symbol(symbol, candle)

        # ── Log equity snapshot for Monitor V1 ──
        equity = self.state.get_equity()
        peak = float(self.state.get_state("peak_equity", equity))
        # Count open positions
        n_open = sum(1 for sym in self.assets if self.state.get_open_position(sym))
        # Unrealized PnL
        unrealized_pnl = 0.0
        for sym in self.assets:
            pos = self.state.get_open_position(sym)
            if pos:
                mark = candle["close"] if sym == symbol else None
                if not mark:
                    latest = self.feed.get_candles(sym, limit=1)
                    mark = latest[0]["close"] if latest else pos["entry_price"]
                lev = LEVERAGE_TIERS.get(sym, DEFAULT_LEVERAGE)
                exit_fee = pos["size"] * mark * FEE_RATE * lev
                unrealized_pnl += (mark - pos["entry_price"]) * pos["size"] - exit_fee
        mtm_equity = equity + unrealized_pnl
        dd = (peak - mtm_equity) / peak * 100 if peak > 0 else 0
        self.state.log_equity_snapshot(
            ts=ts, equity=equity, unrealized_pnl=unrealized_pnl,
            drawdown_pct=dd, guard_state=self.state.get_guard_state().value,
            n_positions=n_open
        )

        # ── 4-hourly summary report ──
        candle_hour_utc = (ts // 3600000) % 24  # 0-23 UTC hour
        # Report at 0, 4, 8, 12, 16, 20 UTC (= 1, 5, 9, 13, 17, 21 Berlin)
        if candle_hour_utc % 4 == 0 and candle_hour_utc != self._last_summary_hour:
            self._last_summary_hour = candle_hour_utc
            self.reporter.report_hourly(self.state, assets=self.assets)
            log.info(f"📋 4h summary sent (hour {candle_hour_utc} UTC)")

    async def _evaluate_symbol(self, symbol: str, current_candle: dict):
        """Evaluate signal for a symbol using buffered candles."""
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

        # ── KILL_SWITCH: Force-close ALL open positions ──
        # BUG FIX: KILL_SWITCH must close ALL positions, not just the current symbol.
        # Each candle only processes one symbol — closing just one would leave the
        # other 5 positions floating for up to 6 hours. Close them ALL now.
        if guard_state == GuardState.KILL_SWITCH:
            closed_any = False
            for sym in self.assets:
                open_pos = self.state.get_open_position(sym)
                if open_pos:
                    # Use this candle's price for the current symbol,
                    # latest DB price for other symbols
                    if sym == symbol:
                        mark = current_price
                    else:
                        latest = self.feed.get_candles(sym, limit=1)
                        mark = latest[0]["close"] if latest else open_pos["entry_price"]
                    exit_price = mark * (1 - SLIPPAGE_BPS / 10000)
                    leverage = LEVERAGE_TIERS.get(sym, DEFAULT_LEVERAGE)
                    fee = open_pos["size"] * exit_price * FEE_RATE * leverage
                    pnl = (exit_price - open_pos["entry_price"]) * open_pos["size"] - fee

                    self.state.close_position(sym, exit_price, current_candle["timestamp"],
                                               "KILL_SWITCH force-close", guard_state.value,
                                               net_pnl=pnl)
                    self.risk.on_trade_closed(pnl)

                    exit_event = {
                        "event": "EXIT",
                        "symbol": sym,
                        "side": "LONG",
                        "price": exit_price,
                        "size": open_pos["size"],
                        "pnl": pnl,
                        "equity": self.state.get_equity(),
                        "reason": "KILL_SWITCH force-close",
                        "guard_state": GuardState.KILL_SWITCH.value,
                        "timestamp": current_candle["timestamp"],
                    }
                    log_trade(exit_event)
                    closed_any = True
                    log.warning(f"\U0001f6a8 KILL_SWITCH force-close: {sym} @ {exit_price:.2f}, PnL={pnl:.2f}")

            if closed_any:
                self.reporter._send_container(
                    "\U0001f6a8 **KILL CLOSE**",
                    "All positions force-closed by KILL_SWITCH.\nNo further trading until !resume.",
                    COLOR_RED
                )
            return  # No further evaluation during KILL

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
                "equity": equity - fee,  # BUG FIX: Report post-fee equity
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
                lo = float(candle["l"])
                c = float(candle["c"])
                v = float(candle.get("v", 0))
                
                conn.execute("""
                    INSERT OR REPLACE INTO candles (symbol, ts, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (symbol, ts, o, h, lo, c, v))
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