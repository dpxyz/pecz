"""
Executor V2 — Paper Trading Engine (Funding-First)

V2 changes from V1:
- Signal: funding_z based (not MACD) — 3 validated signals
- Exit: regime-dependent SL (2.5% bull / 1.5% bear), TS 3%, MaxHold 24h
- SHORT positions supported (SOL bear-only)
- Assets: AVAX, BTC, SOL only (V10 validated)
- DataFeed V2: funding rate polling + z-score + regime
"""

import asyncio
from typing import Optional
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data_feed import DataFeed, SYMBOL_MAP
from data_feed_v2 import DataFeedV2, V2_ACTIVE_ASSETS
from signal_generator_v2 import SignalGeneratorV2, SignalType
from state_manager import StateManager, GuardState
from risk_guard import RiskGuard, MAX_DRAWDOWN_PCT
from discord_reporter import DiscordReporter, COLOR_BLUE, COLOR_RED, COLOR_GREEN, COLOR_AMBER
from command_listener import CommandListener

log = logging.getLogger("paper_engine_v2")

# ── Configuration ──

INITIAL_CAPITAL = 100.0
SLIPPAGE_BPS = 3.0  # 3 bps (more realistic for funding entries)
FEE_RATE = 0.0002   # 0.02% taker fee (worst case Hyperliquid)

PAPER_MODE = True  # ⛔ NEVER set to False without Dave's explicit OK

ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]  # V11 WF Gate passed. AVAX/DOGE archived (bear-only, 0 trades in bull)

# ── Leverage Tiers (ADR-007, V2 adjusted) ──
# AVAX: 1.0x (high vol, primary signal)
# BTC: 1.5x (bear-only, reduced from 1.8x)
# SOL: 1.0x (short = more risk, conservative)
LEVERAGE_TIERS = {
    "BTCUSDT": 1.5,   # Bear+FGI<40, deep liquidity
    "ETHUSDT": 1.5,   # Bear-only, deep liquidity
    "SOLUSDT": 1.0,   # z<-1.5, higher vol → conservative
}

DEFAULT_LEVERAGE = 1.0

# ── Trade Log ──
TRADE_LOG = Path(__file__).parent / "trades_v2.jsonl"
SIGNAL_AUDIT_LOG = Path(__file__).parent / "signal_audit_v2.jsonl"

PRICE_FLOORS = {
    "BTCUSDT": 10000,
    "AVAXUSDT": 5,
}


def log_trade(event: dict, path: Optional[str] = None):
    symbol = event.get("symbol", "")
    price = event.get("price", 0)
    floor = PRICE_FLOORS.get(symbol, 0)
    if price > 0 and price < floor:
        log.warning(f"⛔ REJECTED garbage trade: {event['event']} {symbol} @ {price:.4f} (floor={floor})")
        return False
    event["logged_at"] = datetime.now(timezone.utc).isoformat()
    event["engine_version"] = "V2"
    target = path or TRADE_LOG
    with open(target, "a") as f:
        f.write(json.dumps(event) + "\n")
    return True


class PaperTradingEngineV2:
    """V2 Paper Trading Engine — Funding-First Strategy."""

    def __init__(self, assets: Optional[list[str]] = None, db_path: str = "state_v2.db"):
        self.assets = assets or ASSETS
        self.state = StateManager(db_path=db_path)
        self.risk = RiskGuard(self.state)
        self.signal = SignalGeneratorV2()

        from dotenv import load_dotenv
        import os
        load_dotenv(Path(__file__).parent / ".env")
        channel_id = os.environ.get("DISCORD_CHANNEL_ID")
        self.reporter = DiscordReporter(channel_id=channel_id)
        self.main_address = os.environ.get("HL_MAIN_ADDRESS", "")

        # V2 DataFeed with funding
        self.feed = DataFeedV2(
            db_path=db_path, assets=self.assets,
            on_candle=self._on_candle, engine_last_processed_ts=None
        )
        self.commands = CommandListener(self, channel_id=channel_id)
        self._running = False
        self._last_candle_hour: dict[str, bool] = {}
        self._engine_start_time = None
        self._last_summary_hour = -1
        self._last_regime: dict[str, bool] = {}  # Track regime changes

        # Initialize equity
        if not self.state.get_state("start_equity"):
            self.state.set_start_equity(INITIAL_CAPITAL)
            self.state.set_equity(INITIAL_CAPITAL)
            self.state.set_state("peak_equity", INITIAL_CAPITAL)

        log.info(f"PaperTradingEngineV2 initialized: {self.assets}")
        log.info(f"  Capital: {INITIAL_CAPITAL}€ | Fee: {FEE_RATE*100}% | Slippage: {SLIPPAGE_BPS}bps")

    async def start(self):
        if not PAPER_MODE:
            log.critical("⛔⛔⛔ PAPER_MODE is OFF — REAL MONEY AT RISK ⛔⛔⛔")
            raise RuntimeError("PAPER_MODE=False requires explicit human approval.")

        self._running = True
        self._engine_start_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        self.state.set_state("engine_start_time", int(datetime.now(timezone.utc).timestamp()))
        self.state.set_state("_engine_start_time_ms", str(self._engine_start_time))

        # Gap recovery
        engine_last_ts = None
        try:
            ts_str = self.state.get_state("last_processed_ts")
            if ts_str:
                engine_last_ts = int(float(ts_str))
                log.info(f"Gap recovery: last ts={engine_last_ts}")
        except Exception:
            pass
        self.feed._engine_last_processed_ts = engine_last_ts

        # Startup message
        tier_str = ', '.join(f"{s}@{LEVERAGE_TIERS.get(s, 1.0)}x" for s in self.assets)
        header = "🚀 **Paper Trading Engine V2 Started**"
        body = (
            f"⛔ **PAPER MODE — NO REAL ORDERS**\n"
            f"Assets: {tier_str}\n"
            f"Strategy: Funding-First (V10 validated)\n"
            f"  • BTC Long z<-1 (bear + FGI<40)\n"
            f"  • ETH Long z<-1 (bear-only)\n"
            f"  • SOL Long z<-1.5 (all regimes) — V2+V12 WidePullback\n"
            f"Exit: 24h time-based (primary), Emergency SL 4%, Trailing DISABLED\n"
            f"Capital: {INITIAL_CAPITAL}€ total ({INITIAL_CAPITAL/len(self.assets):.1f}€/asset)\n"
            f"Kill-switches: DailyLoss>5%, MaxDD>20%, MaxPos=1, CL≥5\n"
            f"Commands: !kill, !resume, !status, !help"
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
        log.info("Paper Trading Engine V2 stopped")

    async def _on_candle(self, symbol: str, candle: dict):
        """Called by DataFeedV2 when a CLOSED 1h candle arrives."""
        ts = candle.get("timestamp", 0)
        hour_key = f"{symbol}_{ts}"
        is_replay = candle.get("is_replay", False)

        if hour_key in self._last_candle_hour:
            return
        self._last_candle_hour[hour_key] = True

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        max_age_ms = 2 * 3600 * 1000
        if self._engine_start_time and ts < self._engine_start_time:
            self.state.set_state("last_processed_ts", str(ts))
            return
        if (now_ms - ts) > max_age_ms:
            self.state.set_state("last_processed_ts", str(ts))
            return

        # Update peak for open positions
        open_pos = self.state.get_open_position(symbol)
        if open_pos:
            side = open_pos.get("side", "LONG")
            if side == "LONG" and candle.get("high", 0) > open_pos.get("peak_price", 0):
                self.state.update_peak(symbol, candle["high"])
            elif side == "SHORT":
                # For shorts, track trough (lowest price)
                trough = open_pos.get("trough_price", open_pos["entry_price"])
                if candle.get("low", 0) < trough:
                    self._update_trough(symbol, candle["low"])

        if is_replay:
            self.state.set_state("last_processed_ts", str(ts))
            return

        # Cleanup dedup
        if len(self._last_candle_hour) > 2000:
            keys_to_remove = list(self._last_candle_hour.keys())[:1000]
            for k in keys_to_remove:
                del self._last_candle_hour[k]

        log.info(f"📊 {symbol} CLOSED: close={candle['close']:.2f} @ {datetime.fromtimestamp(ts/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")

        # ── Log regime change ──
        bull200 = self.feed.get_regime(symbol)
        if bull200 is not None:
            prev_regime = self._last_regime.get(symbol)
            if prev_regime is not None and prev_regime != bull200:
                regime_str = "bull→bear 🐻" if not bull200 else "bear→bull 🐂"
                log.info(f"  🔄 {symbol}: Regime change {regime_str}")
                log_trade({"event": "REGIME_CHANGE", "symbol": symbol,
                           "bull200": bull200, "prev_bull200": prev_regime,
                           "close": candle["close"], "timestamp": ts},
                          path=str(SIGNAL_AUDIT_LOG))
            self._last_regime[symbol] = bull200

        self.state.set_state("last_processed_ts", str(ts))

        # ── Hourly Z-Score + OI + Spread + FGI + DXY Snapshot ──
        funding_z = self.feed.get_funding_z(symbol)
        bull200 = self.feed.get_regime(symbol)
        oi = self.feed.get_oi(symbol)
        oi_drop = self.feed.get_oi_drop(symbol)
        fgi = self.feed.get_fgi()
        fgi_class = self.feed.get_fgi_class()
        dxy = self.feed.get_dxy()
        dxy_5d = self.feed.get_dxy_5d_chg()
        # Measure live spread once per hour
        live_spread_bps = self._measure_spread(symbol)
        if funding_z is not None:
            log_trade({
                "event": "Z_SCORE_SNAP", "symbol": symbol,
                "funding_z": round(funding_z, 4),
                "bull200": bull200,
                "oi_contracts": oi,
                "oi_drop_pct": oi_drop,
                "dxy": dxy, "dxy_5d_chg": dxy_5d,
                "spread_bps": live_spread_bps,
                "close": candle["close"],
                "timestamp": ts,
            }, path=str(SIGNAL_AUDIT_LOG))

        # ── Unrealized Drawdown Check ──
        equity = self.state.get_equity()
        peak = float(self.state.get_state("peak_equity", equity))
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
                if pos.get("side", "LONG") == "LONG":
                    pos_pnl = (mark - pos["entry_price"]) * pos["size"] - exit_fee
                else:
                    pos_pnl = (pos["entry_price"] - mark) * pos["size"] - exit_fee
                unrealized_pnl += pos_pnl

        mark_to_market = equity + unrealized_pnl
        mtm_dd = (peak - mark_to_market) / peak * 100 if peak > 0 else 0
        if mtm_dd > MAX_DRAWDOWN_PCT:
            log.warning(f"⚠️ Unrealized DD: {mtm_dd:.1f}% > {MAX_DRAWDOWN_PCT}% — KILL")
            self.risk._trigger_kill(f"Unrealized DD {mtm_dd:.1f}% > {MAX_DRAWDOWN_PCT}%")
            await self._force_close_all(symbol, candle, "Unrealized DD KILL")
            self.reporter._send_container("🚨 **KILL: Unrealized DD**",
                f"Mark-to-market DD: {mtm_dd:.1f}% > {MAX_DRAWDOWN_PCT}%\nAll positions force-closed.", COLOR_RED)
            return

        # Evaluate signal
        await self._evaluate_symbol(symbol, candle)

        # ── Equity snapshot ──
        equity = self.state.get_equity()
        peak = float(self.state.get_state("peak_equity", equity))
        n_open = sum(1 for sym in self.assets if self.state.get_open_position(sym))
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
                if pos.get("side", "LONG") == "LONG":
                    unrealized_pnl += (mark - pos["entry_price"]) * pos["size"] - exit_fee
                else:
                    unrealized_pnl += (pos["entry_price"] - mark) * pos["size"] - exit_fee
        mtm_equity = equity + unrealized_pnl
        dd = (peak - mtm_equity) / peak * 100 if peak > 0 else 0
        self.state.log_equity_snapshot(
            ts=ts, equity=equity, unrealized_pnl=unrealized_pnl,
            drawdown_pct=dd, guard_state=self.state.get_guard_state().value,
            n_positions=n_open
        )

        # ── 4h Summary ──
        candle_hour_utc = (ts // 3600000) % 24
        if candle_hour_utc % 4 == 0 and candle_hour_utc != self._last_summary_hour:
            self._last_summary_hour = candle_hour_utc
            self.reporter.report_hourly(self.state, assets=self.assets)

    async def _evaluate_symbol(self, symbol: str, current_candle: dict):
        """Evaluate funding-first signal for a symbol."""
        candles = self.feed.get_candles(symbol, limit=210)
        if len(candles) < 210:
            log.info(f"  {symbol}: Only {len(candles)} candles, need 210 for warmup")
            return

        # Get funding z-score and regime from V2 data feed
        funding_z = self.feed.get_funding_z(symbol)
        bull200 = self.feed.get_regime(symbol)

        # V14: Extended metrics
        oi_pct_change = self.feed.get_oi_pct_change(symbol)
        ls_ratio = self.feed.get_ls_ratio(symbol)
        taker_vol_ratio = self.feed.get_taker_vol_ratio(symbol)

        # Evaluate signal with all data
        signal = self.signal.evaluate(
            candles, funding_z=funding_z, bull200=bull200, fgi=self.feed.get_fgi(),
            oi_pct_change=oi_pct_change, ls_ratio=ls_ratio,
            taker_vol_ratio=taker_vol_ratio,
            dxy_10d_roc=self.feed.get_dxy_5d_chg(),  # 5d ROC as proxy for 10d (data limitation)
        )

        # ── Signal Audit: Log EVERY evaluation ──
        audit_event = {
            "event": "SIGNAL_EVAL",
            "symbol": symbol,
            "funding_z": funding_z,
            "bull200": bull200,
            "oi_pct_change": oi_pct_change,
            "ls_ratio": ls_ratio,
            "taker_vol_ratio": taker_vol_ratio,
            "signal_type": signal.type.value if signal else "NONE",
            "signal_reason": signal.reason if signal else "no signal",
            "timestamp": current_candle.get("timestamp", 0),
        }
        log_trade(audit_event, path=str(SIGNAL_AUDIT_LOG))

        if not signal:
            return

        current_price = current_candle["close"]
        ts = current_candle["timestamp"]
        equity = self.state.get_equity()
        guard_state = self.state.get_guard_state()

        # ── KILL_SWITCH: Force-close ALL ──
        if guard_state == GuardState.KILL_SWITCH:
            await self._force_close_all(symbol, current_candle, "KILL_SWITCH force-close")
            return

        # ── Check exit for open position ──
        open_pos = self.state.get_open_position(symbol)
        if open_pos:
            side = open_pos.get("side", "LONG")

            # Update peak/trough for trailing stop
            if side == "LONG" and current_candle["high"] > open_pos.get("peak_price", 0):
                self.state.update_peak(symbol, current_candle["high"])
            elif side == "SHORT":
                trough = open_pos.get("trough_price", open_pos["entry_price"])
                if current_candle["low"] < trough:
                    self._update_trough(symbol, current_candle["low"])

            bars_held = self.state.get_state(f"bars_held_{symbol}", 0) + 1
            self.state.set_state(f"bars_held_{symbol}", bars_held)

            exit_signal = self.signal.check_exit(
                open_pos, current_candle, bars_held,
                bull200=bull200 if bull200 is not None else True
            )
            if exit_signal:
                await self._execute_exit(symbol, open_pos, current_candle, exit_signal, guard_state)
                return

        # ── Check for new entry ──
        if signal.type in (SignalType.SIGNAL_LONG, SignalType.SIGNAL_SHORT):
            if open_pos:
                return  # Already in position

            # Risk guard check
            allowed, reason = self.risk.check_all(symbol)
            if not allowed:
                log.info(f"  ⛔ {symbol}: Risk guard blocked — {reason}")
                log_trade({"event": "SIGNAL_BLOCKED", "symbol": symbol, "reason": reason,
                           "funding_z": funding_z, "bull200": bull200,
                           "timestamp": current_candle.get("timestamp", 0)},
                          path=str(SIGNAL_AUDIT_LOG))
                return

            # Cooldown check (prevent re-entry within 24h)
            last_exit_ts = self.state.get_state(f"last_exit_ts_{symbol}", 0)
            cooldown_ms = self.signal.p["cooldown_bars"] * 3600 * 1000
            if ts - last_exit_ts < cooldown_ms:
                remaining_h = (cooldown_ms - (ts - last_exit_ts)) / 3600000
                log.info(f"  ⏳ {symbol}: Cooldown — {remaining_h:.1f}h remaining")
                log_trade({"event": "SIGNAL_BLOCKED", "symbol": symbol,
                           "reason": f"cooldown {remaining_h:.1f}h remaining",
                           "funding_z": funding_z, "bull200": bull200,
                           "timestamp": current_candle.get("timestamp", 0)},
                          path=str(SIGNAL_AUDIT_LOG))
                return

            side = "LONG" if signal.type == SignalType.SIGNAL_LONG else "SHORT"
            await self._execute_entry(symbol, signal, current_candle, side, bull200, guard_state)

    async def _execute_entry(self, symbol: str, signal, candle: dict,
                             side: str, bull200: Optional[bool], guard_state: GuardState):
        """Execute a paper trade entry."""
        ts = candle["timestamp"]
        entry_price = candle["close"]
        # Apply slippage (worst case: we get a slightly worse price)
        if side == "LONG":
            entry_price *= (1 + SLIPPAGE_BPS / 10000)
        else:
            entry_price *= (1 - SLIPPAGE_BPS / 10000)

        equity = self.state.get_equity()
        leverage = LEVERAGE_TIERS.get(symbol, DEFAULT_LEVERAGE)
        # Position size: equal weight, leveraged
        pos_notional = (equity / len(self.assets)) * leverage
        size = pos_notional / entry_price

        # Entry fee
        fee = size * entry_price * FEE_RATE * leverage

        # Open position with side info
        pos_id = self.state.open_position(
            symbol, entry_price, ts, size, guard_state.value
        )
        # Store side and regime in position metadata
        self.state.set_state(f"pos_side_{symbol}", side)
        self.state.set_state(f"pos_regime_{symbol}", "bull" if bull200 else "bear")
        self.state.set_state(f"bars_held_{symbol}", 0)

        if side == "SHORT":
            # For shorts, track trough (lowest price = best for short)
            self._update_trough(symbol, entry_price)

        entry_event = {
            "event": "ENTRY",
            "symbol": symbol,
            "side": side,
            "price": entry_price,
            "size": size,
            "leverage": leverage,
            "notional": pos_notional,
            "equity": equity,
            "fee": fee,
            "reason": signal.reason,
            "guard_state": guard_state.value,
            "indicators": signal.indicators,
            "timestamp": ts,
        }
        log_trade(entry_event)

        emoji = "📈" if side == "LONG" else "📉"
        color = COLOR_GREEN if side == "LONG" else COLOR_RED
        self.reporter._send_container(
            f"{emoji} **ENTRY {side} {symbol}**",
            f"Price: {entry_price:.2f} | Size: {size:.4f} | Lev: {leverage}x\n"
            f"Reason: {signal.reason}\n"
            f"Z-Score: {signal.indicators.get('funding_z', 'N/A')} | "
            f"Regime: {'Bull' if bull200 else 'Bear'}\n"
            f"Equity: {equity:.2f}€",
            color
        )
        log.info(f"📊 ENTRY {side} {symbol} @ {entry_price:.2f}, size={size:.4f}, lev={leverage}x")

    async def _execute_exit(self, symbol: str, pos: dict, candle: dict,
                            exit_signal, guard_state):
        """Execute a paper trade exit."""
        ts = candle["timestamp"]
        side = self.state.get_state(f"pos_side_{symbol}", "LONG")
        entry_price = pos["entry_price"]

        exit_price = exit_signal.price
        # Apply slippage
        if side == "LONG":
            exit_price *= (1 - SLIPPAGE_BPS / 10000)
        else:
            exit_price *= (1 + SLIPPAGE_BPS / 10000)

        # Fee
        leverage = LEVERAGE_TIERS.get(symbol, DEFAULT_LEVERAGE)
        fee = pos["size"] * exit_price * FEE_RATE * leverage

        # PnL calculation (direction-aware)
        if side == "LONG":
            pnl = (exit_price - entry_price) * pos["size"] - fee
        else:
            pnl = (entry_price - exit_price) * pos["size"] - fee

        self.state.close_position(symbol, exit_price, ts,
                                   exit_signal.reason, guard_state.value,
                                   net_pnl=pnl)
        self.risk.on_trade_closed(pnl)

        # Update last exit timestamp for cooldown
        self.state.set_state(f"last_exit_ts_{symbol}", ts)
        self.state.set_state(f"bars_held_{symbol}", 0)
        # Clean up side metadata
        self.state.set_state(f"pos_side_{symbol}", None)
        self.state.set_state(f"pos_regime_{symbol}", None)

        exit_event = {
            "event": "EXIT",
            "symbol": symbol,
            "side": side,
            "price": exit_price,
            "size": pos["size"],
            "pnl": pnl,
            "fee": fee,
            "equity": self.state.get_equity(),
            "reason": exit_signal.reason,
            "guard_state": guard_state.value,
            "timestamp": ts,
        }
        log_trade(exit_event)

        emoji = "✅" if pnl >= 0 else "❌"
        color = COLOR_GREEN if pnl >= 0 else COLOR_RED
        self.reporter._send_container(
            f"{emoji} **EXIT {side} {symbol}**",
            f"Price: {exit_price:.2f} | PnL: {pnl:+.2f}€\n"
            f"Reason: {exit_signal.reason}\n"
            f"Equity: {self.state.get_equity():.2f}€",
            color
        )

    def _measure_spread(self, symbol: str) -> Optional[float]:
        """Measure live bid-ask spread from Binance."""
        try:
            import requests
            resp = requests.get(
                "https://fapi.binance.com/fapi/v1/depth",
                params={"symbol": symbol, "limit": 5},
                timeout=5, headers={"User-Agent": "Mozilla/5.0"}
            )
            data = resp.json()
            best_bid = float(data["bids"][0][0])
            best_ask = float(data["asks"][0][0])
            mid = (best_bid + best_ask) / 2
            spread_bps = (best_ask - best_bid) / mid * 10000
            return round(spread_bps, 2)
        except Exception as e:
            log.debug(f"Spread measurement failed for {symbol}: {e}")
            return None

    async def _force_close_all(self, trigger_symbol: str, trigger_candle: dict, reason: str):
        """Force-close all open positions."""
        ts = trigger_candle["timestamp"]
        for sym in self.assets:
            pos = self.state.get_open_position(sym)
            if not pos:
                continue
            side = self.state.get_state(f"pos_side_{sym}", "LONG")
            if sym == trigger_symbol:
                mark = trigger_candle["close"]
            else:
                latest = self.feed.get_candles(sym, limit=1)
                mark = latest[0]["close"] if latest else pos["entry_price"]

            if side == "LONG":
                exit_price = mark * (1 - SLIPPAGE_BPS / 10000)
                pnl = (exit_price - pos["entry_price"]) * pos["size"]
            else:
                exit_price = mark * (1 + SLIPPAGE_BPS / 10000)
                pnl = (pos["entry_price"] - exit_price) * pos["size"]

            leverage = LEVERAGE_TIERS.get(sym, DEFAULT_LEVERAGE)
            fee = pos["size"] * exit_price * FEE_RATE * leverage
            pnl -= fee

            self.state.close_position(sym, exit_price, ts, reason,
                                       GuardState.KILL_SWITCH.value, net_pnl=pnl)
            self.risk.on_trade_closed(pnl)
            log_trade({
                "event": "EXIT", "symbol": sym, "side": side,
                "price": exit_price, "size": pos["size"],
                "pnl": pnl, "equity": self.state.get_equity(),
                "reason": reason, "guard_state": GuardState.KILL_SWITCH.value,
                "timestamp": ts,
            })
            self.state.set_state(f"pos_side_{sym}", None)
            self.state.set_state(f"pos_regime_{sym}", None)
            log.warning(f"🚨 Force-close: {sym} {side} @ {exit_price:.2f}, PnL={pnl:.2f}")

    def _update_trough(self, symbol: str, low_price: float):
        """Update trough price for short position trailing stop."""
        pos = self.state.get_open_position(symbol)
        if pos:
            current_trough = pos.get("trough_price", pos["entry_price"])
            if low_price < current_trough:
                with sqlite3.connect(self.state.db_path) as conn:
                    # Store trough as metadata (reuse peak_price column for simplicity)
                    # Actually, let's add a proper trough tracking
                    conn.execute("""
                        UPDATE positions SET peak_price = ?
                        WHERE id = ? AND state = 'IN_LONG'
                    """, (low_price, pos["id"]))


# ── Main ──

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    engine = PaperTradingEngineV2()

    log.info("=" * 60)
    log.info("  PAPER TRADING ENGINE V2 — Funding-First")
    log.info("  BTC z<-1 (bear+FGI<40) | BTC/ETH Bull Pullback [-1,-0.2] | SOL z<-1.5")
    log.info("  Exit: 24h time-based, Emergency SL 4%, Trailing DISABLED")
    log.info(f"  Leverage: {LEVERAGE_TIERS}")
    log.info(f"  Capital: {INITIAL_CAPITAL}€ | Slippage: {SLIPPAGE_BPS}bps | Fee: {FEE_RATE*100}%")
    log.info("=" * 60)

    try:
        await engine.start()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        await engine.stop()

    stats = engine.state.get_trade_stats()
    log.info(f"\n📊 Final Stats: {stats}")
    equity = engine.state.get_equity()
    start = engine.state.get_start_equity()
    log.info(f"💰 Final Equity: {equity:.2f}€ (started: {start:.2f}€, PnL: {equity-start:.2f}€)")


if __name__ == "__main__":
    asyncio.run(main())