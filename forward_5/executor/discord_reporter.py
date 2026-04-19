"""
Executor V1 — Discord Reporter
Sends trade events, status updates, and alerts to Discord.
Uses the OpenClaw message tool (no separate webhook needed).
"""

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("discord_reporter")

# ── Message Templates ──

def format_entry(event: dict) -> str:
    """Format a trade entry event."""
    symbol = event.get("symbol", "?")
    price = event.get("price", 0)
    indicators = event.get("indicators", {})
    reason = event.get("reason", "")
    adx = indicators.get("adx_14", "?")
    ema50 = indicators.get("ema_50", "?")
    equity = event.get("equity", 0)
    
    return (
        f"🟢 **ENTRY LONG** {symbol}\n"
        f"Price: ${price:,.2f}\n"
        f"ADX: {adx} | EMA50: {ema50}\n"
        f"Equity: {equity:.2f}€\n"
        f"_{reason}_"
    )


def format_exit(event: dict) -> str:
    """Format a trade exit event."""
    symbol = event.get("symbol", "?")
    price = event.get("price", 0)
    pnl = event.get("pnl", 0)
    reason = event.get("reason", "")
    equity = event.get("equity", 0)
    
    emoji = "✅" if pnl >= 0 else "❌"
    pnl_str = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
    
    return (
        f"{emoji} **EXIT** {symbol}\n"
        f"Price: ${price:,.2f}\n"
        f"PnL: {pnl_str}€\n"
        f"Equity: {equity:.2f}€\n"
        f"_{reason}_"
    )


def format_guard_change(event: dict) -> str:
    """Format a guard state change."""
    reason = event.get("reason", "")
    
    if "KILL_SWITCH" in reason:
        return (
            f"🚨 **KILL SWITCH ACTIVATED**\n"
            f"{reason}\n"
            f"All trading halted. Use `!resume` to restart after cooldown."
        )
    elif "SOFT_PAUSE" in reason:
        return (
            f"⚠️ **SOFT PAUSE**\n"
            f"{reason}\n"
            f"No new entries for 24h. Existing positions managed normally."
        )
    elif "STOP_NEW" in reason:
        return (
            f"🛑 **STOP NEW ENTRIES**\n"
            f"{reason}\n"
            f"No new entries for 24h due to daily loss limit."
        )
    elif "Cooldown" in reason or "COOLDOWN" in reason:
        return (
            f"⏳ **COOLDOWN**\n"
            f"{reason}\n"
            f"24h waiting period after kill switch."
        )
    elif "RUNNING" in reason:
        return f"✅ **RESUMED**\n{reason}"
    else:
        return f"🔄 **Guard: {reason}**"


def format_entry_blocked(event: dict) -> str:
    """Format a blocked entry."""
    reason = event.get("reason", "")
    symbol = event.get("symbol", "?")
    return f"🛑 **ENTRY BLOCKED** {symbol}: {reason}"


def format_hourly_status(state_manager) -> str:
    """Format hourly status report."""
    from state_manager import GuardState
    
    equity = state_manager.get_equity()
    start_equity = state_manager.get_start_equity()
    guard = state_manager.get_guard_state()
    cl = state_manager.get_consecutive_losses()
    stats = state_manager.get_trade_stats()
    daily_pnl = state_manager.get_daily_pnl()
    
    pnl_total = equity - start_equity
    pnl_pct = (pnl_total / start_equity) * 100 if start_equity > 0 else 0
    
    # Position info
    pos_btc = state_manager.get_open_position("BTCUSDT")
    pos_eth = state_manager.get_open_position("ETHUSDT")
    positions = []
    if pos_btc:
        positions.append(f"BTC: ${pos_btc['entry_price']:,.0f}")
    if pos_eth:
        positions.append(f"ETH: ${pos_eth['entry_price']:,.0f}")
    pos_str = ", ".join(positions) if positions else "None"
    
    guard_emoji = {
        GuardState.RUNNING: "🟢",
        GuardState.SOFT_PAUSE: "🟡",
        GuardState.STOP_NEW: "🟠",
        GuardState.KILL_SWITCH: "🔴",
        GuardState.COOLDOWN: "⏳",
    }
    
    return (
        f"📊 **Hourly Status**\n"
        f"Equity: {equity:.2f}€ ({pnl_pct:+.1f}%)\n"
        f"Daily PnL: {daily_pnl:+.2f}€\n"
        f"Positions: {pos_str}\n"
        f"Guard: {guard_emoji.get(guard, '❓')} {guard.value}\n"
        f"Consecutive Losses: {cl}\n"
        f"Trades: {stats['total_trades']} ({stats['win_rate']:.0f}% win)"
    )


def format_daily_summary(state_manager) -> str:
    """Format daily summary report."""
    equity = state_manager.get_equity()
    start_equity = state_manager.get_start_equity()
    stats = state_manager.get_trade_stats()
    daily_pnl = state_manager.get_daily_pnl()
    
    total_pnl = equity - start_equity
    total_pct = (total_pnl / start_equity) * 100 if start_equity > 0 else 0
    peak = state_manager.get_state("peak_equity", start_equity)
    dd = (peak - equity) / peak * 100 if peak > 0 else 0
    
    return (
        f"📋 **Daily Summary**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Equity: {equity:.2f}€ ({total_pct:+.1f}%)\n"
        f"Daily PnL: {daily_pnl:+.2f}€\n"
        f"Peak: {peak:.2f}€ | DD: {dd:.1f}%\n"
        f"Trades: {stats['total_trades']} | W: {stats['wins']} | L: {stats['losses']}\n"
        f"Win Rate: {stats['win_rate']:.0f}%\n"
        f"━━━━━━━━━━━━━━━━━━"
    )


# ── Discord Sender ──

def send_to_discord(message: str, channel_id: str = None):
    """
    Send a message to Discord via OpenClaw message tool.
    Primary path: OpenClaw message API → Discord channel.
    Fallback: Direct Discord Bot API.
    """
    # Primary: OpenClaw subprocess (uses configured bot)
    try:
        import subprocess
        cmd = ["openclaw", "message", "send", "--channel", "discord",
               "--message", message]
        if channel_id:
            cmd.extend(["--target", channel_id])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log.debug("Discord message sent via OpenClaw")
            return True
    except Exception as e:
        log.debug(f"OpenClaw send failed: {e}")

    # Fallback: Direct Discord API via bot token
    import os
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    
    if bot_token and channel_id:
        try:
            import urllib.request
            url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
            payload = json.dumps({"content": message}).encode()
            req = urllib.request.Request(url, data=payload, method="POST")
            req.add_header("Authorization", f"Bot {bot_token}")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200 or resp.status == 201:
                    log.debug("Discord message sent via Bot API")
                    return True
        except Exception as e:
            log.warning(f"Discord Bot API send failed: {e}")

    # Last resort: log it
    log.info(f"DISCORD (not sent): {message[:100]}...")
    return False


class DiscordReporter:
    """Send formatted trade events to Discord via OpenClaw message tool."""
    
    def __init__(self, channel_id: str = None):
        self.channel_id = channel_id
    
    def _send(self, msg: str):
        send_to_discord(msg, channel_id=self.channel_id)
    
    def report_entry(self, event: dict):
        self._send(format_entry(event))
    
    def report_exit(self, event: dict):
        self._send(format_exit(event))
    
    def report_guard_change(self, event: dict):
        self._send(format_guard_change(event))
    
    def report_entry_blocked(self, event: dict):
        self._send(format_entry_blocked(event))
    
    def report_hourly(self, state_manager):
        self._send(format_hourly_status(state_manager))
    
    def report_daily(self, state_manager):
        self._send(format_daily_summary(state_manager))
    
    def report_custom(self, message: str):
        self._send(message)


# ── Test ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
    
    reporter = DiscordReporter()
    
    # Test all message types
    print("Testing message formats:")
    print(format_entry({
        "symbol": "BTCUSDT", "price": 85432.50, "equity": 100.0,
        "indicators": {"adx_14": 28.5, "ema_50": 84200.0},
        "reason": "macd_hist=0.0012 > 0, close=85432.50 > ema50=84200.00"
    }))
    print()
    print(format_exit({
        "symbol": "BTCUSDT", "price": 87140.00, "pnl": 1.96,
        "equity": 101.96, "reason": "Trailing stop hit: peak=87600"
    }))
    print()
    print(format_guard_change({"reason": "KILL_SWITCH: Drawdown 21.3% > 20%"}))
    print()
    print(format_guard_change({"reason": "SOFT_PAUSE: 5 consecutive losses ≥ 5"}))
    print()
    print(format_guard_change({"reason": "RUNNING: Manual resume via Discord"}))
    print()
    print(format_entry_blocked({"symbol": "BTCUSDT", "reason": "SOFT_PAUSE active — 12.5h remaining"}))
    print()
    print("✅ DiscordReporter formats work")