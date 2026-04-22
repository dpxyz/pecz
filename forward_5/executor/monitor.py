"""
Monitor V1 — Reads state.db, generates dashboard JSON, sends daily report.

Outputs:
  - monitor_data.json (equity curve + stats for pecz.pages.dev)
  - Daily Discord report at 21:00 Berlin (19:00 UTC)
  - Alert on DD approaching threshold
"""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("monitor")

DB_PATH = Path(__file__).parent / "state.db"
OUTPUT_PATH = Path(__file__).parent / "monitor_data.json"

# Alert thresholds
DD_WARNING_PCT = 15.0   # Warning when DD > 15%
DD_CRITICAL_PCT = 20.0  # Critical when DD > 20%


class MonitorV1:
    def __init__(self, db_path: str = None, output_path: str = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.output_path = Path(output_path) if output_path else OUTPUT_PATH

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ── Data Collection ──

    def get_equity_curve(self, hours: int = 168) -> list[dict]:
        """Get equity curve for last N hours (default 7 days)."""
        conn = self._get_conn()
        try:
            cutoff = int(datetime.now(timezone.utc).timestamp() * 1000) - (hours * 3600000)
            rows = conn.execute("""
                SELECT ts, equity, unrealized_pnl, drawdown_pct, guard_state, n_positions
                FROM equity_history
                WHERE ts >= ?
                ORDER BY ts ASC
            """, (cutoff,)).fetchall()
            return [
                {"ts": r[0], "equity": r[1], "unrealized_pnl": r[2],
                 "drawdown_pct": r[3], "guard_state": r[4], "n_positions": r[5]}
                for r in rows
            ]
        finally:
            conn.close()

    def get_open_positions(self) -> list[dict]:
        """Get all open positions with current mark prices and calculated uPnL."""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT symbol, entry_price, entry_time, peak_price, size, unrealized_pnl
                FROM positions
                WHERE state = 'IN_LONG'
                ORDER BY entry_time ASC
            """).fetchall()
            levs = {'BTCUSDT':1.8,'ETHUSDT':1.8,'SOLUSDT':1.5,'AVAXUSDT':1.0,'DOGEUSDT':1.5,'ADAUSDT':1.5}
            positions = []
            for r in rows:
                sym, entry, entry_time, peak, size, _ = r
                # Get latest mark price
                latest = conn.execute("""
                    SELECT close FROM candles
                    WHERE symbol = ? ORDER BY ts DESC LIMIT 1
                """, (sym,)).fetchone()
                mark = latest[0] if latest else entry
                # Calculate unrealized PnL with exit fee
                lev = levs.get(sym, 1.0)
                exit_fee = size * mark * 0.0001 * lev
                upnl = (mark - entry) * size - exit_fee
                positions.append({
                    "symbol": sym, "entry_price": entry, "entry_time": entry_time,
                    "peak_price": peak, "size": size, "unrealized_pnl": upnl,
                    "mark_price": mark, "entry_ts": entry_time,
                })
            return positions
        finally:
            conn.close()

    def get_recent_trades(self, limit: int = 20) -> list[dict]:
        """Get recent trades."""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT timestamp, event, symbol, price, size, equity, pnl, guard_state, reason
                FROM trades
                ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()
            return [
                {"timestamp": r[0], "event": r[1], "symbol": r[2], "price": r[3],
                 "size": r[4], "equity": r[5], "pnl": r[6], "guard_state": r[7], "reason": r[8]}
                for r in rows
            ]
        finally:
            conn.close()

    def get_summary(self) -> dict:
        """Get current portfolio summary."""
        conn = self._get_conn()
        try:
            # Equity
            equity = float(conn.execute(
                "SELECT value FROM state WHERE key='equity'"
            ).fetchone()[0])
            start_equity = float(conn.execute(
                "SELECT value FROM state WHERE key='start_equity'"
            ).fetchone()[0])
            peak_equity = float(conn.execute(
                "SELECT value FROM state WHERE key='peak_equity'"
            ).fetchone()[0]) if conn.execute(
                "SELECT value FROM state WHERE key='peak_equity'"
            ).fetchone() else equity

            # Guard state
            guard_row = conn.execute(
                "SELECT value FROM state WHERE key='guard_state'"
            ).fetchone()
            guard_state = guard_row[0] if guard_row else "RUNNING"

            # Consecutive losses
            cl_row = conn.execute(
                "SELECT value FROM state WHERE key='consecutive_losses'"
            ).fetchone()
            consecutive_losses = int(float(cl_row[0])) if cl_row else 0

            # Trade stats
            exits = conn.execute("""
                SELECT COUNT(*), COALESCE(SUM(pnl), 0),
                       COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0)
                FROM trades WHERE event = 'EXIT'
            """).fetchone()
            total_trades = exits[0]
            total_pnl = exits[1]
            wins = exits[2]

            # Open positions count
            n_open = conn.execute(
                "SELECT COUNT(*) FROM positions WHERE state='IN_LONG'"
            ).fetchone()[0]

            # Engine uptime
            engine_start_row = conn.execute(
                "SELECT value FROM state WHERE key='engine_start_time'"
            ).fetchone()
            engine_start = int(float(engine_start_row[0])) if engine_start_row else 0
            uptime_hours = (int(datetime.now(timezone.utc).timestamp()) - engine_start) / 3600

            # Last candle
            last_candle = conn.execute(
                "SELECT MAX(ts) FROM candles"
            ).fetchone()[0]
            last_candle_dt = datetime.fromtimestamp(last_candle / 1000, tz=timezone.utc).isoformat() if last_candle else None

            # DD
            dd = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0

            # Unrealized PnL from open positions
            unrealized_pnl = 0.0
            levs = {'BTCUSDT':1.8,'ETHUSDT':1.8,'SOLUSDT':1.5,'AVAXUSDT':1.0,'DOGEUSDT':1.5,'ADAUSDT':1.5}
            for sym in ['BTCUSDT','ETHUSDT','SOLUSDT','AVAXUSDT','DOGEUSDT','ADAUSDT']:
                pos = conn.execute('SELECT entry_price, size FROM positions WHERE symbol=? AND state="IN_LONG"', (sym,)).fetchone()
                if pos:
                    mark = conn.execute('SELECT close FROM candles WHERE symbol=? ORDER BY ts DESC LIMIT 1', (sym,)).fetchone()
                    mark_price = mark[0] if mark else pos[0]
                    fee = pos[1] * mark_price * 0.0001 * levs.get(sym, 1.0)
                    unrealized_pnl += (mark_price - pos[0]) * pos[1] - fee

            return {
                "equity": equity,
                "start_equity": start_equity,
                "peak_equity": peak_equity,
                "pnl": equity - start_equity,
                "pnl_pct": (equity - start_equity) / start_equity * 100,
                "unrealized_pnl": unrealized_pnl,
                "mtm_equity": equity + unrealized_pnl,
                "drawdown_pct": dd,
                "guard_state": guard_state,
                "consecutive_losses": consecutive_losses,
                "total_trades": total_trades,
                "wins": wins,
                "losses": total_trades - wins,
                "win_rate": wins / max(total_trades, 1) * 100,
                "total_pnl": total_pnl,
                "n_open_positions": n_open,
                "uptime_hours": round(uptime_hours, 1),
                "last_candle": last_candle_dt,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            conn.close()

    # ── Dashboard JSON ──

    def generate_dashboard_json(self) -> dict:
        """Generate full dashboard data for pecz.pages.dev."""
        summary = self.get_summary()
        equity_curve = self.get_equity_curve(hours=168)  # 7 days
        positions = self.get_open_positions()
        recent_trades = self.get_recent_trades(limit=20)

        data = {
            "summary": summary,
            "equity_curve": equity_curve,
            "positions": positions,
            "recent_trades": recent_trades,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Write JSON
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w") as f:
            json.dump(data, f, indent=2)

        log.info(f"Dashboard JSON written: {self.output_path} ({len(equity_curve)} equity points)")
        return data

    # ── Alert Check ──

    def check_alerts(self) -> Optional[str]:
        """Check for alert conditions. Returns alert message or None."""
        summary = self.get_summary()
        dd = summary.get("drawdown_pct", 0)

        if dd >= DD_CRITICAL_PCT:
            return f"🚨 CRITICAL: Drawdown {dd:.1f}% ≥ {DD_CRITICAL_PCT}%"
        elif dd >= DD_WARNING_PCT:
            return f"⚠️ WARNING: Drawdown {dd:.1f}% ≥ {DD_WARNING_PCT}%"
        return None

    # ── Daily Report ──

    def format_daily_report(self) -> tuple[str, str]:
        """Format daily report for Discord. Returns (header, body)."""
        summary = self.get_summary()
        trades = self.get_recent_trades(limit=10)
        positions = self.get_open_positions()

        s = summary
        header = "📊 **Daily Report**"

        # Equity line
        pnl_sign = "+" if s["pnl"] >= 0 else ""
        equity_line = f"Equity: **{s['equity']:.2f}€** ({pnl_sign}{s['pnl']:.2f}€, {pnl_sign}{s['pnl_pct']:.2f}%)"

        # DD line
        dd_line = f"DD: **{s['drawdown_pct']:.2f}%** | Peak: {s['peak_equity']:.2f}€"

        # Guard + CL
        guard_line = f"Guard: **{s['guard_state']}** | CL: {s['consecutive_losses']}"

        # Trade stats
        trade_line = f"Trades: {s['total_trades']} ({s['wins']}W/{s['losses']}L, {s['win_rate']:.0f}%) | Realized PnL: {s['total_pnl']:.2f}€"

        # Positions
        pos_lines = []
        if positions:
            for p in positions:
                sym = p["symbol"].replace("USDT", "")
                upnl = p["unrealized_pnl"]
                ep = p['entry_price']
                mp = p['mark_price']
                dec = 6 if ep < 1 else (4 if ep < 100 else 2)
                pos_lines.append(f"  {sym}: LONG @ {ep:.{dec}f} → {mp:.{dec}f} (uPnL: {upnl:+.2f}€)")
        else:
            pos_lines.append("  No open positions")

        # Recent trades
        trade_lines = []
        for t in trades[:5]:
            if t["event"] == "EXIT":
                sym = t["symbol"].replace("USDT", "")
                dec = 6 if t["price"] < 1 else (4 if t["price"] < 100 else 2)
                trade_lines.append(f"  {sym}: {t['event']} @ {t['price']:.{dec}f} PnL={t['pnl']:+.2f}€")

        body = "\n".join([
            equity_line,
            dd_line,
            guard_line,
            trade_line,
            "",
            "**Open Positions:**",
            *pos_lines,
        ])
        if trade_lines:
            body += "\n\n**Recent Exits:**\n" + "\n".join(trade_lines)

        body += f"\n\nUptime: {s['uptime_hours']:.0f}h | Paper Day {max(1, int(s['uptime_hours'] / 24))}/14"

        return header, body


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")

    monitor = MonitorV1()
    data = monitor.generate_dashboard_json()
    print(f"Summary: {json.dumps(data['summary'], indent=2)}")
    print(f"Equity points: {len(data['equity_curve'])}")
    print(f"Positions: {len(data['positions'])}")

    # Daily report
    header, body = monitor.format_daily_report()
    print(f"\n--- Daily Report ---")
    print(header)
    print(body)

    # Alerts
    alert = monitor.check_alerts()
    if alert:
        print(f"\n🚨 ALERT: {alert}")
    else:
        print("\n✅ No alerts")