"""
Executor V1 — Discord Reporter
Sends trade events, status updates, and alerts to Discord.
Uses the OpenClaw message tool (no separate webhook needed).
"""

from typing import Optional
import json
import logging

log = logging.getLogger("discord_reporter")

# ── Message Templates ──

def _build_container(text_header: str, body: str, color: str) -> dict:
    """Build a Discord Components v2 container with accent color."""
    return {
        "text": text_header,
        "container": {"accentColor": color},
        "blocks": [{"type": "text", "text": body}]
    }


# Color scheme for event types
COLOR_BLUE = "#3b82f6"    # Info / Entry
COLOR_GREEN = "#22c55e"   # Win / Resume
COLOR_RED = "#ef4444"     # Kill / Loss / Blocked
COLOR_AMBER = "#f59e0b"  # Warning / Pause
COLOR_GRAY = "#6b7280"   # Status / Neutral


def format_entry(event: dict) -> tuple:
    """Format a trade entry event. Returns (header, body, color)."""
    symbol = event.get("symbol", "?")
    price = event.get("price", 0)
    indicators = event.get("indicators", {})
    reason = event.get("reason", "")
    adx = indicators.get("adx_14", "?")
    ema50 = indicators.get("ema_50", "?")
    equity = event.get("equity", 0)
    
    header = "🟢 **ENTRY LONG**"
    body = (
        f"**{symbol}**\n"
        f"Price: ${price:,.2f}\n"
        f"ADX: {adx} | EMA50: {ema50}\n"
        f"Equity: {equity:.2f}€\n"
        f"_{reason}_"
    )
    return header, body, COLOR_BLUE


def format_exit(event: dict) -> tuple:
    """Format a trade exit event. Returns (header, body, color)."""
    symbol = event.get("symbol", "?")
    price = event.get("price", 0)
    pnl = event.get("pnl", 0)
    reason = event.get("reason", "")
    equity = event.get("equity", 0)
    
    if pnl >= 0:
        header = "✅ **WIN**"
        color = COLOR_GREEN
        pnl_str = f"+{pnl:.2f}"
    else:
        header = "❌ **LOSS**"
        color = COLOR_RED
        pnl_str = f"{pnl:.2f}"
    
    body = (
        f"**EXIT {symbol}**\n"
        f"Price: ${price:,.2f}\n"
        f"PnL: {pnl_str}€\n"
        f"Equity: {equity:.2f}€\n"
        f"_{reason}_"
    )
    return header, body, color


def format_guard_change(event: dict) -> tuple:
    """Format a guard state change. Returns (header, body, color)."""
    reason = event.get("reason", "")
    
    if "KILL_SWITCH" in reason:
        return (
            "🚨 **CRITICAL**",
            f"**KILL SWITCH ACTIVATED**\n{reason}\nAll trading halted. Use `!resume` to restart.",
            COLOR_RED
        )
    elif "SOFT_PAUSE" in reason:
        return (
            "⚠️ **WARNING**",
            f"**SOFT PAUSE**\n{reason}\nNo new entries for 24h.",
            COLOR_AMBER
        )
    elif "STOP_NEW" in reason:
        return (
            "🛑 **STOP NEW**",
            f"**NO NEW ENTRIES**\n{reason}\nDaily loss limit reached.",
            COLOR_AMBER
        )
    elif "Cooldown" in reason or "COOLDOWN" in reason:
        return (
            "⏳ **COOLDOWN**",
            f"**COOLDOWN**\n{reason}\n24h waiting period.",
            COLOR_GRAY
        )
    elif "RUNNING" in reason:
        return (
            "✅ **RESUMED**",
            f"{reason}",
            COLOR_GREEN
        )
    else:
        return (
            "🔄 **GUARD**",
            f"{reason}",
            COLOR_GRAY
        )


def format_entry_blocked(event: dict) -> tuple:
    """Format a blocked entry. Returns (header, body, color)."""
    reason = event.get("reason", "")
    symbol = event.get("symbol", "?")
    return (
        "🛑 **BLOCKED**",
        f"**ENTRY BLOCKED** {symbol}\n{reason}",
        COLOR_AMBER  # Warning, not critical
    )


def format_hourly_status(state_manager, assets: Optional[list] = None) -> tuple:
    """Format hourly status report. Returns (header, body, color)."""
    from state_manager import GuardState
    
    # Use provided assets or default list
    if assets is None:
        assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT"]
    
    equity = state_manager.get_equity()
    start_equity = state_manager.get_start_equity()
    guard = state_manager.get_guard_state()
    cl = state_manager.get_consecutive_losses()
    stats = state_manager.get_trade_stats()
    daily_pnl = state_manager.get_daily_pnl()
    
    pnl_total = equity - start_equity
    pnl_pct = (pnl_total / start_equity) * 100 if start_equity > 0 else 0
    
    # Iterate tracked assets for open positions
    positions = []
    for sym in assets:
        pos = state_manager.get_open_position(sym)
        if pos:
            positions.append(f"{sym.split('USDT')[0]}: ${pos['entry_price']:,.0f}")
    pos_str = ", ".join(positions) if positions else "None"
    
    guard_emoji = {
        GuardState.RUNNING: "🟢",
        GuardState.SOFT_PAUSE: "🟡",
        GuardState.STOP_NEW: "🟠",
        GuardState.KILL_SWITCH: "🔴",
        GuardState.COOLDOWN: "⏳",
    }
    
    header = "📊 **Hourly Status**"
    body = (
        f"Equity: {equity:.2f}€ ({pnl_pct:+.1f}%)\n"
        f"Daily PnL: {daily_pnl:+.2f}€\n"
        f"Positions: {pos_str}\n"
        f"Guard: {guard_emoji.get(guard, '❓')} {guard.value}\n"
        f"Consecutive Losses: {cl}\n"
        f"Trades: {stats['total_trades']} ({stats['win_rate']:.0f}% win)"
    )
    return header, body, COLOR_BLUE


def format_daily_summary(state_manager) -> tuple:
    """Format daily summary report. Returns (header, body, color)."""
    equity = state_manager.get_equity()
    start_equity = state_manager.get_start_equity()
    stats = state_manager.get_trade_stats()
    daily_pnl = state_manager.get_daily_pnl()
    
    total_pnl = equity - start_equity
    total_pct = (total_pnl / start_equity) * 100 if start_equity > 0 else 0
    peak = state_manager.get_state("peak_equity", start_equity)
    dd = (peak - equity) / peak * 100 if peak > 0 else 0
    
    color = COLOR_GREEN if total_pnl >= 0 else COLOR_RED
    
    header = "📋 **Daily Summary**"
    body = (
        f"Equity: {equity:.2f}€ ({total_pct:+.1f}%)\n"
        f"Daily PnL: {daily_pnl:+.2f}€\n"
        f"Peak: {peak:.2f}€ | DD: {dd:.1f}%\n"
        f"Trades: {stats['total_trades']} | W: {stats['wins']} | L: {stats['losses']}\n"
        f"Win Rate: {stats['win_rate']:.0f}%"
    )
    return header, body, color


# ── Discord Sender ──

def send_to_discord(message: str, channel_id: Optional[str] = None):
    """
    Send a plain text message to Discord via OpenClaw message tool.
    Used for custom/freeform messages.
    """
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
    ch_id = os.environ.get("DISCORD_CHANNEL_ID", channel_id)
    
    if bot_token and ch_id:
        try:
            import urllib.request
            url = f"https://discord.com/api/v10/channels/{ch_id}/messages"
            payload = json.dumps({"content": message}).encode()
            req = urllib.request.Request(url, data=payload, method="POST")
            req.add_header("Authorization", f"Bot {bot_token}")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201):
                    log.debug("Discord message sent via Bot API")
                    return True
        except Exception as e:
            log.warning(f"Discord Bot API send failed: {e}")

    log.info(f"DISCORD (not sent): {message[:100]}...")
    return False


def send_container_to_discord(header: str, body: str, color: str,
                               channel_id: Optional[str] = None):
    """
    Send a colored container (Components v2) to Discord via OpenClaw.
    Falls back to plain text if components fail.
    """
    components = _build_container(header, body, color)
    
    # Try Components v2 via OpenClaw subprocess
    try:
        import subprocess
        cmd = [
            "openclaw", "message", "send",
            "--channel", "discord",
            "--components", json.dumps(components),
        ]
        if channel_id:
            cmd.extend(["--target", channel_id])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log.debug("Discord container sent via OpenClaw")
            return True
        log.debug(f"Components send failed: {result.stderr[:200]}")
    except Exception as e:
        log.debug(f"Components send error: {e}")

    # Fallback: plain text
    plain_msg = f"{header}\n{body}"
    return send_to_discord(plain_msg, channel_id=channel_id)


class DiscordReporter:
    """Send formatted trade events to Discord with colored containers."""
    
    def __init__(self, channel_id: Optional[str] = None):
        self.channel_id = channel_id
    
    def _send_text(self, msg: str):
        send_to_discord(msg, channel_id=self.channel_id)
    
    def _send_container(self, header: str, body: str, color: str):
        send_container_to_discord(header, body, color, channel_id=self.channel_id)
    
    def report_entry(self, event: dict):
        header, body, color = format_entry(event)
        self._send_container(header, body, color)
    
    def report_exit(self, event: dict):
        header, body, color = format_exit(event)
        self._send_container(header, body, color)
    
    def report_guard_change(self, event: dict):
        header, body, color = format_guard_change(event)
        self._send_container(header, body, color)
    
    def report_entry_blocked(self, event: dict):
        header, body, color = format_entry_blocked(event)
        self._send_container(header, body, color)
    
    def report_hourly(self, state_manager, assets: Optional[list] = None):
        header, body, color = format_hourly_status(state_manager, assets=assets)
        self._send_container(header, body, color)
    
    def report_daily(self, state_manager):
        header, body, color = format_daily_summary(state_manager)
        self._send_container(header, body, color)
    
    def report_custom(self, message: str):
        self._send_text(message)


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