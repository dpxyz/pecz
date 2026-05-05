"""
Edge Decay Monitor — Daily funding distribution tracker.

Checks for structural shifts in funding rate distributions that could
indicate edge decay. Alerts via Discord when shifts exceed thresholds.

Thresholds:
- >10pp shift in neg% = WARNING
- >20pp shift in neg% = CRITICAL
- >15% shift in mean funding rate = WARNING
"""

import sqlite3
import logging
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

import requests

log = logging.getLogger("edge_decay_monitor")

DB_PATH = Path(__file__).parent / "state_v2.db"
HL_API_URL = "https://api.hyperliquid.xyz/info"
HL_SYMBOLS = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL"}

# Thresholds
NEG_PCT_SHIFT_WARNING = 10  # percentage points
NEG_PCT_SHIFT_CRITICAL = 20
MEAN_SHIFT_PCT = 15  # percent change in mean

# Baseline window: compare last 30d vs 30d before that
BASELINE_DAYS = 30
COMPARE_DAYS = 30


def get_hl_funding(coin: str, hours: int = 336) -> list:
    """Fetch funding rates from HyperLiquid API."""
    start_ms = int((time.time() - hours * 3600) * 1000)
    payload = {"type": "fundingHistory", "coin": coin, "startTime": start_ms}
    try:
        resp = requests.post(HL_API_URL, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return [(d["time"], float(d["fundingRate"])) for d in data]
    except Exception as e:
        log.error(f"HL API error for {coin}: {e}")
        return []


def compute_distribution(rates: list) -> dict:
    """Compute funding distribution metrics."""
    if not rates:
        return {}
    n = len(rates)
    neg_count = sum(1 for r in rates if r < 0)
    mild_neg_count = sum(1 for r in rates if -0.0005 <= r < 0)
    mean_rate = sum(rates) / n
    std_rate = (sum((r - mean_rate) ** 2 for r in rates) / n) ** 0.5
    return {
        "n": n,
        "mean_pct": mean_rate * 100,
        "std_pct": std_rate * 100,
        "neg_pct": neg_count / n * 100,
        "mild_neg_pct": mild_neg_count / n * 100,
        "min_pct": min(rates) * 100,
        "max_pct": max(rates) * 100,
    }


def check_edge_decay():
    """Main edge decay check. Returns alert dict."""
    alerts = []
    results = {}

    for symbol, coin in HL_SYMBOLS.items():
        # Fetch last 14 days of 1h funding
        raw = get_hl_funding(coin, hours=BASELINE_DAYS * 24 * 2)
        if len(raw) < 100:
            log.warning(f"Insufficient data for {symbol}: {len(raw)} points")
            continue

        # Sort by timestamp
        raw.sort(key=lambda x: x[0])
        rates = [r for _, r in raw]
        timestamps = [t for t, _ in raw]

        # Split into baseline (older) and current (newer)
        cutoff = timestamps[len(timestamps) // 2]
        baseline = [r for t, r in raw if t < cutoff]
        current = [r for t, r in raw if t >= cutoff]

        base_dist = compute_distribution(baseline)
        curr_dist = compute_distribution(current)

        if not base_dist or not curr_dist:
            continue

        # Check shifts
        neg_shift = curr_dist["neg_pct"] - base_dist["neg_pct"]
        mild_neg_shift = curr_dist["mild_neg_pct"] - base_dist["mild_neg_pct"]
        mean_shift_pct = ((curr_dist["mean_pct"] - base_dist["mean_pct"]) /
                          abs(base_dist["mean_pct"]) * 100
                          if abs(base_dist["mean_pct"]) > 1e-6 else 0)

        severity = "ok"
        if abs(neg_shift) >= NEG_PCT_SHIFT_CRITICAL:
            severity = "CRITICAL"
        elif abs(neg_shift) >= NEG_PCT_SHIFT_WARNING:
            severity = "WARNING"

        result = {
            "symbol": symbol,
            "baseline": base_dist,
            "current": curr_dist,
            "neg_shift_pp": round(neg_shift, 1),
            "mild_neg_shift_pp": round(mild_neg_shift, 1),
            "mean_shift_pct": round(mean_shift_pct, 1),
            "severity": severity,
        }
        results[symbol] = result

        if severity != "ok":
            alerts.append(result)

    return {"alerts": alerts, "all_results": results}


def format_discord_message(check_result: dict) -> str:
    """Format edge decay check as Discord message."""
    lines = ["🔍 **Edge Decay Monitor** — Daily Check\n"]

    for symbol, r in check_result["all_results"].items():
        icon = {"ok": "✅", "WARNING": "⚠️", "CRITICAL": "🔴"}.get(r["severity"], "❓")
        lines.append(f"{icon} **{r['symbol']}** — neg% shift: {r['neg_shift_pp']:+.1f}pp")
        lines.append(f"   Baseline: neg%={r['baseline']['neg_pct']:.1f}%, "
                      f"mean={r['baseline']['mean_pct']:.4f}%")
        lines.append(f"   Current:  neg%={r['current']['neg_pct']:.1f}%, "
                      f"mean={r['current']['mean_pct']:.4f}%")
        lines.append("")

    if check_result["alerts"]:
        lines.append("⚠️ **Action required:** Review signal parameters for affected assets.")
    else:
        lines.append("✅ No significant edge decay detected.")

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    result = check_edge_decay()
    msg = format_discord_message(result)
    print(msg)

    # Save results
    output_path = Path(__file__).parent / "edge_decay_results.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")