"""
Executor V1 — State Manager
Persistent state via SQLite: position, equity, guard states, trade history.
Recoverable after crash/restart.
"""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum

log = logging.getLogger("state_manager")

# ── Guard States (ADR-006) ──

class GuardState(Enum):
    RUNNING = "RUNNING"
    SOFT_PAUSE = "SOFT_PAUSE"
    STOP_NEW = "STOP_NEW"
    KILL_SWITCH = "KILL_SWITCH"
    COOLDOWN = "COOLDOWN"


# ── Position States ──

class PositionState(Enum):
    NO_POSITION = "NO_POSITION"
    IN_LONG = "IN_LONG"
    COOLDOWN = "COOLDOWN"


class StateManager:
    def __init__(self, db_path: str = "executor/state.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    state TEXT NOT NULL,
                    entry_price REAL,
                    entry_time INTEGER,
                    peak_price REAL,
                    size REAL,
                    unrealized_pnl REAL DEFAULT 0,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    close_reason TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    event TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT,
                    price REAL,
                    size REAL,
                    equity REAL,
                    pnl REAL DEFAULT 0,
                    guard_state TEXT,
                    reason TEXT,
                    indicators_json TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_ts
                ON trades(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_symbol
                ON trades(symbol)
            """)

    # ── Key-Value State ──

    def get_state(self, key: str, default=None):
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM state WHERE key = ?", (key,)
            ).fetchone()
            return json.loads(row[0]) if row else default

    def set_state(self, key: str, value):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO state (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, json.dumps(value), now))

    # ── Guard State ──

    def get_guard_state(self) -> GuardState:
        state = self.get_state("guard_state", GuardState.RUNNING.value)
        return GuardState(state)

    def set_guard_state(self, state: GuardState, reason: str = ""):
        self.set_state("guard_state", state.value)
        self.log_event("GUARD_STATE_CHANGE", symbol="SYSTEM",
                       reason=f"{state.value}: {reason}",
                       guard_state=state.value)
        log.info(f"Guard state → {state.value}: {reason}")

    # ── Position Management ──

    def get_open_position(self, symbol: str) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT id, symbol, state, entry_price, entry_time,
                       peak_price, size, unrealized_pnl
                FROM positions
                WHERE symbol = ? AND state = 'IN_LONG'
                ORDER BY id DESC LIMIT 1
            """, (symbol,)).fetchone()
            if row:
                return {
                    "id": row[0], "symbol": row[1], "state": row[2],
                    "entry_price": row[3], "entry_time": row[4],
                    "peak_price": row[5], "size": row[6],
                    "unrealized_pnl": row[7],
                }
            return None

    def open_position(self, symbol: str, entry_price: float, entry_time: int,
                      size: float, guard_state: str = "RUNNING"):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO positions (symbol, state, entry_price, entry_time,
                                       peak_price, size, opened_at)
                VALUES (?, 'IN_LONG', ?, ?, ?, ?, ?)
            """, (symbol, entry_price, entry_time, entry_price, size, now))
            pos_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        self.log_event("ENTRY", symbol=symbol, side="LONG",
                       price=entry_price, size=size, guard_state=guard_state,
                       reason=f"Entry at {entry_price:.2f}")
        log.info(f"📊 OPENED LONG {symbol} @ {entry_price:.2f}, size={size}")
        return pos_id

    def close_position(self, symbol: str, exit_price: float, exit_time: int,
                       reason: str, guard_state: str = "RUNNING", net_pnl: float = None):
        pos = self.get_open_position(symbol)
        if not pos:
            log.warning(f"No open position for {symbol}")
            return None

        # Use pre-calculated NET PnL if provided (includes exit fee)
        # Otherwise fall back to gross PnL calculation
        if net_pnl is not None:
            pnl = net_pnl
        else:
            pnl = (exit_price - pos["entry_price"]) * pos["size"]
        now = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE positions SET state = 'CLOSED', closed_at = ?,
                                     close_reason = ?
                WHERE id = ?
            """, (now, reason, pos["id"]))

        self.log_event("EXIT", symbol=symbol, side="LONG",
                       price=exit_price, size=pos["size"],
                       pnl=pnl, guard_state=guard_state, reason=reason)
        log.info(f"📊 CLOSED {symbol} @ {exit_price:.2f}, PnL={pnl:.2f} ({reason})")
        return pnl

    def update_peak(self, symbol: str, high_price: float):
        """Update peak price for trailing stop calculation."""
        pos = self.get_open_position(symbol)
        if pos and high_price > pos.get("peak_price", 0):
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE positions SET peak_price = ? WHERE id = ?
                """, (high_price, pos["id"]))

    # ── Equity ──

    def get_equity(self) -> float:
        return self.get_state("equity", 100.0)

    def set_equity(self, equity: float):
        self.set_state("equity", equity)

    def get_start_equity(self) -> float:
        return self.get_state("start_equity", 100.0)

    def set_start_equity(self, equity: float):
        self.set_state("start_equity", equity)

    # ── Consecutive Losses ──

    def get_consecutive_losses(self) -> int:
        return self.get_state("consecutive_losses", 0)

    def increment_consecutive_losses(self):
        cl = self.get_consecutive_losses() + 1
        self.set_state("consecutive_losses", cl)
        return cl

    def reset_consecutive_losses(self):
        self.set_state("consecutive_losses", 0)

    # ── Trade Logging ──

    def log_event(self, event: str, symbol: str = "", side: str = "",
                  price: float = 0, size: float = 0, equity: float = 0,
                  pnl: float = 0, guard_state: str = "", reason: str = "",
                  indicators: dict = None):
        now_ts = int(datetime.now(timezone.utc).timestamp())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO trades (timestamp, event, symbol, side, price, size,
                                    equity, pnl, guard_state, reason, indicators_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (now_ts, event, symbol, side, price, size, equity, pnl,
                  guard_state, reason, json.dumps(indicators or {})))

    # ── Daily PnL ──

    def get_daily_pnl(self) -> float:
        """Get today's realized PnL."""
        now = datetime.now(timezone.utc)
        start_of_day = int(datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp())
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT COALESCE(SUM(pnl), 0) FROM trades
                WHERE event = 'EXIT' AND timestamp >= ?
            """, (start_of_day,)).fetchone()
            return row[0] if row else 0.0

    # ── Stats ──

    def get_trade_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            exits = conn.execute("""
                SELECT COUNT(*), COALESCE(SUM(pnl), 0),
                       COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0)
                FROM trades WHERE event = 'EXIT'
            """).fetchone()
            total_trades = exits[0]
            total_pnl = exits[1]
            wins = exits[2]
            return {
                "total_trades": total_trades,
                "total_pnl": total_pnl,
                "win_rate": wins / max(total_trades, 1) * 100,
                "wins": wins,
                "losses": total_trades - wins,
            }


# ── Test ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")

    sm = StateManager(db_path="executor/state.db")
    sm.set_start_equity(100.0)
    sm.set_equity(100.0)

    print("State Manager Test:")
    print(f"  Guard State: {sm.get_guard_state()}")
    print(f"  Equity: {sm.get_equity()}")
    print(f"  Start Equity: {sm.get_start_equity()}")
    print(f"  Consecutive Losses: {sm.get_consecutive_losses()}")

    # Simulate open/close
    sm.open_position("BTCUSDT", 85000.0, 1713500000, 0.00117)
    pos = sm.get_open_position("BTCUSDT")
    print(f"  Open Position: {pos}")

    sm.update_peak("BTCUSDT", 87000.0)
    pnl = sm.close_position("BTCUSDT", 86000.0, 1713540000, "Trailing stop")
    print(f"  Closed Position PnL: {pnl:.4f}")

    sm.increment_consecutive_losses()
    sm.increment_consecutive_losses()
    print(f"  Consecutive Losses: {sm.get_consecutive_losses()}")
    sm.reset_consecutive_losses()
    print(f"  After Reset: {sm.get_consecutive_losses()}")

    stats = sm.get_trade_stats()
    print(f"  Trade Stats: {stats}")
    print("✅ StateManager works")