"""Executor V1 — Paper Trading Engine for MACD+ADX+EMA Baseline Strategy."""

from .signal_generator import SignalGenerator, Signal, SignalType
from .state_manager import StateManager, GuardState
from .risk_guard import RiskGuard
from .data_feed import DataFeed

__version__ = "0.1.0"