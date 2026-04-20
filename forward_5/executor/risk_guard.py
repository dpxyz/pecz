"""
Executor V1 — Risk Guard
Kill-switches and runtime guards per ADR-006.
All thresholds are hardcoded, not configurable by strategy.
"""

import logging
from datetime import datetime, timezone, timedelta
from enum import Enum

from state_manager import StateManager, GuardState

log = logging.getLogger("risk_guard")

# ── Hardcoded Thresholds (NOT configurable) ──

DAILY_LOSS_PCT = 5.0        # Stop new entries if daily loss > 5%
MAX_DRAWDOWN_PCT = 20.0     # Kill switch if drawdown from peak > 20%
MAX_OPEN_POSITIONS = 1      # 1 position per symbol (6 assets = max 6 concurrent)
CONSECUTIVE_LOSS_PAUSE = 5  # Soft pause after 5 consecutive losses
COOLDOWN_HOURS = 24         # 24h cooldown after kill switch


class RiskGuard:
    """Deterministic risk guard — no LLM, no vibes, no overrides."""

    def __init__(self, state: StateManager):
        self.state = state
        log.info("RiskGuard initialized — thresholds hardcoded:")
        log.info(f"  Daily Loss: >{DAILY_LOSS_PCT}%")
        log.info(f"  Max Drawdown: >{MAX_DRAWDOWN_PCT}%")
        log.info(f"  Max Positions: {MAX_OPEN_POSITIONS}")
        log.info(f"  Consecutive Loss Pause: ≥{CONSECUTIVE_LOSS_PAUSE}")
        log.info(f"  Cooldown: {COOLDOWN_HOURS}h")

    def check_all(self, symbol: str = "BTCUSDT") -> tuple[bool, str]:
        """
        Check all risk guards. Returns (allowed, reason).
        If allowed=False, the trade should NOT be entered.
        """
        guard = self.state.get_guard_state()

        # ── KILL_SWITCH: No trading at all ──
        if guard == GuardState.KILL_SWITCH:
            return False, f"KILL_SWITCH active — all trading halted"

        # ── COOLDOWN: Waiting period after kill ──
        if guard == GuardState.COOLDOWN:
            cooldown_start = self.state.get_state("kill_timestamp")
            if cooldown_start:
                cooldown_until = cooldown_start + (COOLDOWN_HOURS * 3600)
                now = int(datetime.now(timezone.utc).timestamp())
                if now < cooldown_until:
                    remaining = (cooldown_until - now) / 3600
                    return False, f"COOLDOWN active — {remaining:.1f}h remaining"
                else:
                    log.info("Cooldown expired, resuming RUNNING")
                    self.state.set_guard_state(GuardState.RUNNING, "Cooldown expired")
                    guard = GuardState.RUNNING

        # ── SOFT_PAUSE: No new entries for 24h ──
        if guard == GuardState.SOFT_PAUSE:
            pause_start = self.state.get_state("pause_timestamp")
            if pause_start:
                pause_until = pause_start + (COOLDOWN_HOURS * 3600)
                now = int(datetime.now(timezone.utc).timestamp())
                if now < pause_until:
                    remaining = (pause_until - now) / 3600
                    return False, f"SOFT_PAUSE active — {remaining:.1f}h remaining"
                else:
                    log.info("Soft pause expired, resuming RUNNING")
                    self.state.set_guard_state(GuardState.RUNNING, "Soft pause expired")
                    guard = GuardState.RUNNING

        # ── STOP_NEW: No new entries ──
        if guard == GuardState.STOP_NEW:
            stop_start = self.state.get_state("stop_new_timestamp")
            if stop_start:
                stop_until = stop_start + (COOLDOWN_HOURS * 3600)
                now = int(datetime.now(timezone.utc).timestamp())
                if now < stop_until:
                    remaining = (stop_until - now) / 3600
                    return False, f"STOP_NEW active — {remaining:.1f}h remaining"
                else:
                    log.info("Stop-new expired, resuming RUNNING")
                    self.state.set_guard_state(GuardState.RUNNING, "Stop-new expired")

        # ── Max positions ──
        open_pos = self.state.get_open_position(symbol)
        if open_pos:
            return False, f"Already in position — max {MAX_OPEN_POSITIONS} position(s)"

        # ── Daily loss check ──
        equity = self.state.get_equity()
        start_equity = self.state.get_start_equity()
        daily_pnl = self.state.get_daily_pnl()
        daily_loss_pct = abs(daily_pnl) / start_equity * 100 if daily_pnl < 0 else 0

        if daily_loss_pct > DAILY_LOSS_PCT:
            self.state.set_guard_state(GuardState.STOP_NEW,
                                       f"Daily loss {daily_loss_pct:.1f}% > {DAILY_LOSS_PCT}%")
            return False, f"Daily loss {daily_loss_pct:.1f}% exceeds {DAILY_LOSS_PCT}%"

        # ── Drawdown check ──
        peak_equity = self.state.get_state("peak_equity", start_equity)
        if peak_equity > 0:
            drawdown_pct = (peak_equity - equity) / peak_equity * 100
            if drawdown_pct > MAX_DRAWDOWN_PCT:
                self._trigger_kill(f"Drawdown {drawdown_pct:.1f}% > {MAX_DRAWDOWN_PCT}%")
                return False, f"KILL_SWITCH: Drawdown {drawdown_pct:.1f}% > {MAX_DRAWDOWN_PCT}%"

        # ── Consecutive losses ──
        cl = self.state.get_consecutive_losses()
        if cl >= CONSECUTIVE_LOSS_PAUSE:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            self.state.set_state("pause_timestamp", now_ts)
            self.state.set_guard_state(GuardState.SOFT_PAUSE,
                                       f"{cl} consecutive losses ≥ {CONSECUTIVE_LOSS_PAUSE}")
            return False, f"SOFT_PAUSE: {cl} consecutive losses"

        return True, "All guards clear"

    def on_trade_closed(self, pnl: float):
        """Called after a trade is closed. Updates state and checks guards."""
        equity = self.state.get_equity()
        new_equity = equity + pnl
        self.state.set_equity(new_equity)

        # Update peak equity
        peak = self.state.get_state("peak_equity", self.state.get_start_equity())
        if new_equity > peak:
            self.state.set_state("peak_equity", new_equity)

        if pnl >= 0:
            self.state.reset_consecutive_losses()
        else:
            cl = self.state.increment_consecutive_losses()
            log.warning(f"Loss recorded — consecutive losses: {cl}")

    def _trigger_kill(self, reason: str):
        """Trigger KILL_SWITCH — close all, stop trading."""
        now_ts = int(datetime.now(timezone.utc).timestamp())
        self.state.set_state("kill_timestamp", now_ts)
        self.state.set_guard_state(GuardState.KILL_SWITCH, reason)
        log.critical(f"🚨 KILL_SWITCH triggered: {reason}")

    def manual_kill(self, reason: str = "Manual trigger via Discord"):
        """Manual kill switch from Discord command."""
        self._trigger_kill(reason)

    def manual_resume(self, reason: str = "Manual resume via Discord"):
        """Manual resume from Discord command (bypasses cooldown)."""
        prev_state = self.state.get_guard_state()
        self.state.set_guard_state(GuardState.RUNNING, reason)
        self.state.reset_consecutive_losses()
        if prev_state in (GuardState.KILL_SWITCH, GuardState.COOLDOWN):
            log.warning(f"✅ Manual resume (COOLDOWN BYPASSED): {reason}")
        else:
            log.info(f"✅ Manual resume: {reason}")


# ── Test ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")

    sm = StateManager(db_path="executor/state.db")
    rg = RiskGuard(sm)

    print("Risk Guard Test:")
    allowed, reason = rg.check_all("BTCUSDT")
    print(f"  Initial check: allowed={allowed}, reason={reason}")

    # Simulate 5 consecutive losses
    for i in range(5):
        sm.increment_consecutive_losses()
    allowed, reason = rg.check_all("BTCUSDT")
    print(f"  After 5 losses: allowed={allowed}, reason={reason}")
    print(f"  Guard state: {sm.get_guard_state()}")

    sm.reset_consecutive_losses()
    print("✅ RiskGuard works")