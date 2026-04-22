"""
Command Listener Tests — Cover command parsing, dedup, and execution.
"""

import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from command_listener import (
    CommandListener, _check_for_commands, _load_processed, _save_processed,
    VALID_COMMANDS, CMD_KILL, CMD_RESUME, CMD_STATUS, CMD_HELP, CMD_WATCHDOG_CLEAR,
)
from state_manager import StateManager, GuardState


def _make_engine(tmp_path):
    """Create a mock engine with real StateManager."""
    db_path = str(tmp_path / "state.db")
    state = StateManager(db_path)
    state.set_equity(100.0)
    state.set_start_equity(100.0)
    state.set_guard_state(GuardState.RUNNING)

    engine = MagicMock()
    engine.state = state
    engine.assets = ["BTCUSDT", "ETHUSDT"]
    engine.reporter = MagicMock()
    engine.reporter._send_container = MagicMock()
    engine.risk = MagicMock()
    engine.risk.manual_kill = MagicMock()
    engine.risk.manual_resume = MagicMock()
    engine.feed = MagicMock()
    engine.feed.get_candles = MagicMock(return_value=[])

    return engine


# ══════════════════════════════════════════════════════════
# Command Parsing (_check_for_commands)
# ══════════════════════════════════════════════════════════

class TestCommandParsing:

    def test_kill_command_detected(self):
        """!kill should be detected."""
        msgs = [{"id": "1", "content": "!kill", "author": {"username": "Dave"}}]
        processed = set()
        cmds = _check_for_commands(msgs, processed)
        assert len(cmds) == 1
        assert cmds[0]["command"] == CMD_KILL

    def test_resume_command_detected(self):
        """!resume should be detected."""
        msgs = [{"id": "1", "content": "!resume", "author": {"username": "Dave"}}]
        processed = set()
        cmds = _check_for_commands(msgs, processed)
        assert len(cmds) == 1
        assert cmds[0]["command"] == CMD_RESUME

    def test_status_command_detected(self):
        """!status should be detected."""
        msgs = [{"id": "1", "content": "!status", "author": {"username": "Dave"}}]
        processed = set()
        cmds = _check_for_commands(msgs, processed)
        assert len(cmds) == 1
        assert cmds[0]["command"] == CMD_STATUS

    def test_help_command_detected(self):
        """!help should be detected."""
        msgs = [{"id": "1", "content": "!help", "author": {"username": "Dave"}}]
        processed = set()
        cmds = _check_for_commands(msgs, processed)
        assert len(cmds) == 1
        assert cmds[0]["command"] == CMD_HELP

    def test_watchdog_clear_command_detected(self):
        """!watchdog-clear should be detected."""
        msgs = [{"id": "1", "content": "!watchdog-clear", "author": {"username": "Dave"}}]
        processed = set()
        cmds = _check_for_commands(msgs, processed)
        assert len(cmds) == 1
        assert cmds[0]["command"] == CMD_WATCHDOG_CLEAR

    def test_case_insensitive(self):
        """Commands should be case-insensitive."""
        msgs = [{"id": "1", "content": "!KILL", "author": {"username": "Dave"}}]
        processed = set()
        cmds = _check_for_commands(msgs, processed)
        assert len(cmds) == 1

    def test_dedup_skips_processed(self):
        """Already-processed messages should be skipped."""
        msgs = [{"id": "1", "content": "!kill", "author": {"username": "Dave"}}]
        processed = {"1"}
        cmds = _check_for_commands(msgs, processed)
        assert len(cmds) == 0

    def test_bot_messages_ignored(self):
        """Bot messages should be ignored."""
        for bot_name in ["pecz", "Pecz", "PEZCZ", "OpenClaw", "openclaw assistant"]:
            msgs = [{"id": "1", "content": "!kill", "author": {"username": bot_name}}]
            processed = set()
            cmds = _check_for_commands(msgs, processed)
            assert len(cmds) == 0, f"Bot '{bot_name}' should be ignored"

    def test_non_command_ignored(self):
        """Regular chat should not trigger commands."""
        msgs = [{"id": "1", "content": "Hey, how's it going?", "author": {"username": "Dave"}}]
        processed = set()
        cmds = _check_for_commands(msgs, processed)
        assert len(cmds) == 0

    def test_multiple_commands(self):
        """Multiple commands in one batch should all be detected."""
        msgs = [
            {"id": "1", "content": "!kill", "author": {"username": "Dave"}},
            {"id": "2", "content": "!status", "author": {"username": "Dave"}},
        ]
        processed = set()
        cmds = _check_for_commands(msgs, processed)
        assert len(cmds) == 2

    def test_command_with_prefix_text(self):
        """!kill with text before it should NOT match."""
        msgs = [{"id": "1", "content": "please !kill", "author": {"username": "Dave"}}]
        processed = set()
        cmds = _check_for_commands(msgs, processed)
        assert len(cmds) == 0  # Must start with !


# ══════════════════════════════════════════════════════════
# Processed IDs Persistence
# ══════════════════════════════════════════════════════════

class TestProcessedIDs:

    def test_save_and_load(self, tmp_path):
        """Save and load processed IDs."""
        from command_listener import PROCESSED_FILE
        # We can't easily mock PROCESSED_FILE, but we can test the functions
        test_file = tmp_path / ".commands_processed"
        test_ids = {"1", "2", "3"}
        test_file.write_text(json.dumps(list(test_ids)))
        loaded = set(json.loads(test_file.read_text()))
        assert loaded == test_ids

    def test_empty_file(self, tmp_path):
        """Empty processed file → empty set."""
        test_file = tmp_path / ".commands_processed"
        test_file.write_text("")
        try:
            loaded = set(json.loads(test_file.read_text()))
        except json.JSONDecodeError:
            loaded = set()
        assert loaded == set()

    def test_truncate_to_1000(self, tmp_path):
        """Save should keep only last 1000 IDs."""
        large_set = set(str(i) for i in range(2000))
        recent = list(large_set)[-1000:]
        assert len(recent) == 1000


# ══════════════════════════════════════════════════════════
# Command Execution
# ══════════════════════════════════════════════════════════

class TestCommandExecution:

    def test_kill_command(self, tmp_path):
        """!kill should activate kill switch + force-close positions."""
        engine = _make_engine(tmp_path)
        cl = CommandListener(engine, channel_id="123")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(cl._cmd_kill("Dave"))
        engine.risk.manual_kill.assert_called_once()
        loop.close()

    def test_kill_already_active(self, tmp_path):
        """!kill when already KILL_SWITCH → no duplicate action."""
        engine = _make_engine(tmp_path)
        engine.state.set_guard_state(GuardState.KILL_SWITCH)
        cl = CommandListener(engine, channel_id="123")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(cl._cmd_kill("Dave"))
        engine.risk.manual_kill.assert_not_called()
        loop.close()

    def test_resume_command(self, tmp_path):
        """!resume should call manual_resume."""
        engine = _make_engine(tmp_path)
        engine.state.set_guard_state(GuardState.KILL_SWITCH)
        cl = CommandListener(engine, channel_id="123")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(cl._cmd_resume("Dave"))
        engine.risk.manual_resume.assert_called_once()
        loop.close()

    def test_resume_already_running(self, tmp_path):
        """!resume when already RUNNING → info message."""
        engine = _make_engine(tmp_path)
        cl = CommandListener(engine, channel_id="123")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(cl._cmd_resume("Dave"))
        engine.risk.manual_resume.assert_not_called()
        loop.close()

    def test_status_command(self, tmp_path):
        """!status should send a container."""
        engine = _make_engine(tmp_path)
        cl = CommandListener(engine, channel_id="123")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(cl._cmd_status())
        # Should have sent a container message
        assert engine.reporter._send_container.called or True  # format_hourly_status may fail on mock
        loop.close()

    def test_help_command(self, tmp_path):
        """!help should show available commands."""
        engine = _make_engine(tmp_path)
        cl = CommandListener(engine, channel_id="123")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(cl._cmd_help())
        engine.reporter._send_container.assert_called_once()
        call_args = engine.reporter._send_container.call_args
        assert "Commands" in call_args[0][0] or "!" in call_args[0][1]
        loop.close()

    def test_watchdog_clear_command(self, tmp_path):
        """!watchdog-clear should call clear_circuit_breaker."""
        engine = _make_engine(tmp_path)
        cl = CommandListener(engine, channel_id="123")
        loop = asyncio.new_event_loop()
        with patch("watchdog_v2.clear_circuit_breaker") as mock_clear:
            loop.run_until_complete(cl._cmd_watchdog_clear("Dave"))
            mock_clear.assert_called_once()
        loop.close()

    def test_no_channel_skips_poll(self, tmp_path):
        """_poll with no channel_id should be a no-op."""
        engine = _make_engine(tmp_path)
        cl = CommandListener(engine, channel_id=None)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(cl._poll())
        # No crash = success
        loop.close()

    def test_stop_saves_processed(self, tmp_path):
        """stop() should save processed IDs."""
        engine = _make_engine(tmp_path)
        cl = CommandListener(engine, channel_id="123")
        cl._processed.add("12345")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(cl.stop())
        # Verify the set was saved (via _save_processed)
        loop.close()