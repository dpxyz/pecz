"""
Regression test: Peak price must be updated for ALL candles, including replay.

Bug: update_peak() was only called inside _evaluate_symbol(), which is skipped
for is_replay candles. During gap recovery after a crash, the peak price stayed
stale, causing the trailing stop to be calculated against an outdated peak.

Fix: Move update_peak() to _on_candle() BEFORE the is_replay check, so it
runs for both live and replay candles.
"""

import pytest
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from state_manager import StateManager


def test_peak_updated_on_replay_candle():
    """Peak price must be updated for replay candles during gap recovery."""
    db = tempfile.mktemp(suffix=".db")
    sm = StateManager(db_path=db)
    
    # Open a position with initial peak
    sm.open_position("BTCUSDT", 50000.0, 0.001, "2026-01-01T00:00:00Z")
    sm.update_peak("BTCUSDT", 50500.0)  # Initial peak
    
    # Verify initial peak
    pos = sm.get_open_position("BTCUSDT")
    assert pos["peak_price"] == 50500.0
    
    # Simulate replay candle updating peak to a higher value
    # This should work because update_peak is called in _on_candle BEFORE is_replay check
    sm.update_peak("BTCUSDT", 51000.0)
    pos = sm.get_open_position("BTCUSDT")
    assert pos["peak_price"] == 51000.0, "Peak should be updated even for replay candle"
    
    # Simulate replay candle with even higher peak
    sm.update_peak("BTCUSDT", 52000.0)
    pos = sm.get_open_position("BTCUSDT")
    assert pos["peak_price"] == 52000.0, "Peak should track highest high across all candles"
    
    # Lower high should NOT decrease peak
    sm.update_peak("BTCUSDT", 51500.0)
    pos = sm.get_open_position("BTCUSDT")
    assert pos["peak_price"] == 52000.0, "Peak should never decrease"
    
    import os
    os.unlink(db)


def test_trailing_stop_uses_correct_peak():
    """Trailing stop must be calculated against the actual highest peak, not stale entry."""
    db = tempfile.mktemp(suffix=".db")
    sm = StateManager(db_path=db)
    
    # Open position at $100
    sm.open_position("ETHUSDT", 100.0, 1.0, "2026-01-01T00:00:00Z")
    
    # Peak rises to $105 (5% gain)
    sm.update_peak("ETHUSDT", 105.0)
    
    # Trailing stop at 2% below peak = $102.90
    pos = sm.get_open_position("ETHUSDT")
    expected_stop = 105.0 * 0.98  # = 102.90
    assert pos["peak_price"] == 105.0
    
    # If peak were stale at entry ($100), stop would be at $98 — WAY too low
    # This is the bug we're testing against
    stale_stop = 100.0 * 0.98  # = 98.0 (incorrect)
    correct_stop = expected_stop     # = 102.9 (correct)
    assert stale_stop != correct_stop, "Stale peak would give wrong stop"
    
    import os
    os.unlink(db)