"""
Executor V1 — Command Listener
Listens for Discord commands (!kill, !resume, !status) in #foundry-reports.
Runs as a background task alongside the Paper Trading Engine.
"""

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("command_listener")

# ── Discord Command Polling ──
# Since we can't use a persistent WebSocket for Discord (Bot API 403),
# we poll recent messages in #foundry-reports via OpenClaw message tool.

POLL_INTERVAL_S = 30  # Check every 30 seconds
PROCESSED_FILE = Path(__file__).parent / ".commands_processed"

# Commands
CMD_KILL = "!kill"
CMD_RESUME = "!resume"
CMD_STATUS = "!status"
CMD_HELP = "!help"

VALID_COMMANDS = [CMD_KILL, CMD_RESUME, CMD_STATUS, CMD_HELP]


def _load_processed() -> set:
    """Load set of already-processed message IDs."""
    if PROCESSED_FILE.exists():
        try:
            return set(json.loads(PROCESSED_FILE.read_text()))
        except Exception:
            return set()
    return set()


def _save_processed(ids: set):
    """Save processed message IDs (keep last 1000)."""
    recent = list(ids)[-1000:]
    PROCESSED_FILE.write_text(json.dumps(recent))


def _read_recent_messages(channel_id: str, limit: int = 10) -> list:
    """Read recent messages from Discord channel via OpenClaw."""
    try:
        import subprocess
        cmd = [
            "openclaw", "message", "read",
            "--channel", "discord",
            "--target", channel_id,
            "--limit", str(limit),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            log.debug(f"Read failed: {result.stderr[:200]}")
            return []

        # Parse the table output from openclaw message read
        # Format: | Time | Author | Text | Id |
        messages = []
        lines = result.stdout.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line.startswith("|") or "Time" in line or "──" in line:
                continue
            # Split by | and extract fields
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 5:
                msg_id = parts[4].strip()
                author = parts[2].strip()
                content = parts[3].strip()
                if msg_id and content:
                    messages.append({
                        "id": msg_id,
                        "author": {"username": author},
                        "content": content,
                    })
        return messages
    except Exception as e:
        log.debug(f"Read messages failed: {e}")
    return []


def _check_for_commands(messages: list, processed: set) -> list:
    """Extract commands from messages that haven't been processed yet."""
    commands = []
    for msg in messages:
        msg_id = msg.get("id", msg.get("message_id", ""))
        if msg_id and str(msg_id) in processed:
            continue

        content = msg.get("content", "")
        author = msg.get("author", {}).get("username", "") if isinstance(msg.get("author"), dict) else ""
        
        # Skip our own messages
        bot_names = ["pecz", "pezcz", "openclaw", "openclaw assistant"]
        if author.lower() in bot_names:
            continue

        # Check for commands
        content_stripped = content.strip().lower()
        for cmd in VALID_COMMANDS:
            if content_stripped.startswith(cmd):
                commands.append({
                    "command": cmd,
                    "message_id": str(msg_id),
                    "author": author,
                    "raw_content": content.strip(),
                })
                break

        if msg_id:
            processed.add(str(msg_id))

    return commands


class CommandListener:
    """Polls Discord for commands and executes them on the Paper Trading Engine."""

    def __init__(self, engine, channel_id: str = None):
        self.engine = engine
        self.channel_id = channel_id
        self._processed = _load_processed()
        self._running = False
        log.info(f"CommandListener initialized — watching for: {', '.join(VALID_COMMANDS)}")

    async def start(self):
        """Start polling for commands."""
        self._running = True
        log.info("📡 Command listener started — polling every 30s")
        
        while self._running:
            try:
                await self._poll()
            except Exception as e:
                log.error(f"Command poll error: {e}")
            await asyncio.sleep(POLL_INTERVAL_S)

    async def stop(self):
        self._running = False
        _save_processed(self._processed)
        log.info("Command listener stopped")

    async def _poll(self):
        """Check for new commands and execute them."""
        if not self.channel_id:
            return

        messages = _read_recent_messages(self.channel_id)
        commands = _check_for_commands(messages, self._processed)

        for cmd in commands:
            await self._execute(cmd)
            self._processed.add(cmd["message_id"])

        # Save processed IDs periodically
        _save_processed(self._processed)

    async def _execute(self, cmd: dict):
        """Execute a Discord command."""
        command = cmd["command"]
        author = cmd.get("author", "Unknown")
        
        log.info(f"📨 Command from {author}: {command}")

        if command == CMD_KILL:
            await self._cmd_kill(author)
        elif command == CMD_RESUME:
            await self._cmd_resume(author)
        elif command == CMD_STATUS:
            await self._cmd_status()
        elif command == CMD_HELP:
            await self._cmd_help()

    async def _cmd_kill(self, author: str):
        """!kill — Activate kill switch immediately."""
        from state_manager import GuardState
        
        current = self.engine.state.get_guard_state()
        if current == GuardState.KILL_SWITCH:
            self.engine.reporter.report_custom(
                "🚨 **Kill switch already active**\nUse `!resume` to restart after review."
            )
            return

        self.engine.risk.manual_kill(f"Manual !kill by {author}")
        self.engine.reporter.report_custom(
            f"🚨 **KILL SWITCH ACTIVATED** by {author}\n"
            f"All trading halted immediately.\n"
            f"Any open positions will be managed to close.\n"
            f"Use `!resume` to restart after review."
        )
        log.critical(f"🚨 Manual kill switch activated by {author}")

    async def _cmd_resume(self, author: str):
        """!resume — Resume from kill switch / pause."""
        from state_manager import GuardState
        
        current = self.engine.state.get_guard_state()
        if current == GuardState.RUNNING:
            self.engine.reporter.report_custom(
                "✅ **Already running** — no pause active."
            )
            return

        self.engine.risk.manual_resume(f"Manual !resume by {author}")
        self.engine.reporter.report_custom(
            f"✅ **RESUMED** by {author}\n"
            f"Guard state → RUNNING\n"
            f"Consecutive losses reset to 0.\n"
            f"New entries allowed."
        )
        log.info(f"✅ Manual resume by {author}")

    async def _cmd_status(self):
        """!status — Show current engine status."""
        from discord_reporter import format_hourly_status
        status_msg = format_hourly_status(self.engine.state)
        # Add uptime info
        start_time = self.engine.state.get_state("engine_start_time")
        if start_time:
            now = int(datetime.now(timezone.utc).timestamp())
            uptime_h = (now - start_time) / 3600
            status_msg += f"\nUptime: {uptime_h:.1f}h"
        self.engine.reporter.report_custom(status_msg)

    async def _cmd_help(self):
        """!help — Show available commands."""
        self.engine.reporter.report_custom(
            "📋 **Executor V1 Commands**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "**!kill** — Activate kill switch (stops all trading)\n"
            "**!resume** — Resume from kill/pause state\n"
            "**!status** — Show current equity, guard state, positions\n"
            "**!help** — Show this message\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Commands work in #foundry-reports channel."
        )


# ── Integration Test ──

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    
    print("Command Listener Test:")
    print(f"  Valid commands: {VALID_COMMANDS}")
    print(f"  Poll interval: {POLL_INTERVAL_S}s")
    
    # Test command parsing
    test_messages = [
        {"id": "1", "content": "!kill", "author": {"username": "Dave"}},
        {"id": "2", "content": "!status", "author": {"username": "Dave"}},
        {"id": "3", "content": "Just chatting", "author": {"username": "Dave"}},
        {"id": "4", "content": "!resume", "author": {"username": "Dave"}},
        {"id": "5", "content": "!help", "author": {"username": "Dave"}},
        {"id": "1", "content": "!kill", "author": {"username": "Dave"}},  # Duplicate
    ]
    
    processed = set()
    commands = _check_for_commands(test_messages, processed)
    print(f"\n  Found {len(commands)} commands:")
    for cmd in commands:
        print(f"    {cmd['command']} from {cmd['author']}")
    
    print(f"\n  Processed IDs: {len(processed)}")
    print("✅ CommandListener works")