#!/usr/bin/env python3
"""Composite Fitness Score for Foundry HOF Champions.

Combines multiple dimensions into a single ranking metric:
1. OOS Return (out-of-sample performance) — the reality check
2. WF Robustness 10w (stability across windows) — consistency
3. OOS Profitable Ratio (how many periods profitable) — reliability
4. IS Score (in-sample quality) — signal quality floor
5. Trade Count (min_trades) — statistical significance
6. Drawdown penalty (avg_dd) — risk-adjusted

Weights are tuned for our use case: we care MOST about OOS performance
and consistency, but need enough trades for statistical validity.

Usage: python3 composite_fitness.py
"""
import json
import re
from pathlib import Path

HOF_PATH = Path(__file__).parent / "runs/evolution_v7/evolution_v7_hof.json"

# ─── Weight Configuration ───
# All components normalized to [0, 1] before weighting
WEIGHTS = {
    "oos_return": 0.25,      # Out-of-sample return (most important reality check)
    "oos_profitable": 0.25,  # Fraction of OOS periods profitable (consistency)
    "wf_robustness": 0.20,   # Walk-forward robustness (stability across windows)
    "is_score": 0.10,        # In-sample quality (floor, not driver)
    "trade_count": 0.15,     # Minimum trade count (statistical significance — higher weight!)
    "drawdown": 0.05,        # Drawdown penalty (risk-adjusted — lower weight)
}

# Normalization ranges (based on observed HOF data)
NORM = {
    "oos_return": (-2.0, 1.0),      # -2% to +1% mapped to 0..1
    "oos_profitable": (0, 1.0),     # already 0..1 ratio
    "wf_robustness": (0, 100),      # 0..100 mapped to 0..1
    "is_score": (-1.0, 1.0),        # -1 to +1 mapped to 0..1
    "trade_count": (0, 100),        # 0..100 trades mapped to 0..1
    "drawdown": (0, 50),            # 0..50% DD mapped to 0..1 (inverted: less = better)
}


def normalize(value, low, high):
    """Map value to [0, 1] range, clamped."""
    if high == low:
        return 0.5
    return max(0.0, min(1.0, (value - low) / (high - low)))


def parse_profitable_ratio(s):
    """Parse '3/6' or '5/6' into a 0..1 ratio."""
    if isinstance(s, (int, float)):
        return float(s)
    m = re.match(r"(\d+)/(\d+)", str(s))
    if m:
        return int(m.group(1)) / int(m.group(2))
    return 0.0


def compute_fitness(h):
    """Compute composite fitness score for a HOF entry."""
    # 1. OOS Return
    oos = h.get("avg_oos_return", 0)
    oos_norm = normalize(oos, *NORM["oos_return"])

    # 2. OOS Profitable Ratio
    oos_pr = parse_profitable_ratio(h.get("wf_profitable_10w", h.get("wf_profitable_assets", "0/6")))
    oos_pr_norm = normalize(oos_pr, *NORM["oos_profitable"])

    # 3. WF Robustness
    wf = h.get("wf_robustness_10w", h.get("wf_robustness", 0))
    wf_norm = normalize(wf, *NORM["wf_robustness"])

    # 4. IS Score
    is_score = h.get("is_score", 0)
    is_norm = normalize(is_score, *NORM["is_score"])

    # 5. Trade Count (min_trades across all IS windows)
    trades = h.get("min_trades", 0)
    trades_norm = normalize(trades, *NORM["trade_count"])

    # 6. Drawdown (inverted: lower = better)
    dd = h.get("avg_dd", 50)
    dd_norm = 1.0 - normalize(dd, *NORM["drawdown"])  # invert

    # Weighted sum
    fitness = (
        WEIGHTS["oos_return"] * oos_norm +
        WEIGHTS["oos_profitable"] * oos_pr_norm +
        WEIGHTS["wf_robustness"] * wf_norm +
        WEIGHTS["is_score"] * is_norm +
        WEIGHTS["trade_count"] * trades_norm +
        WEIGHTS["drawdown"] * dd_norm
    )

    components = {
        "oos_return": round(oos_norm, 3),
        "oos_profitable": round(oos_pr_norm, 3),
        "wf_robustness": round(wf_norm, 3),
        "is_score": round(is_norm, 3),
        "trade_count": round(trades_norm, 3),
        "drawdown": round(dd_norm, 3),
    }

    return round(fitness, 4), components


def main():
    if not HOF_PATH.exists():
        print("No HOF file found.")
        return

    data = json.loads(HOF_PATH.read_text())
    hof = data["hof"]

    # Score ALL entries
    scored = []
    for h in hof:
        fitness, components = compute_fitness(h)
        scored.append((h, fitness, components))

    # Sort by fitness (descending)
    scored.sort(key=lambda x: x[1], reverse=True)

    # Display
    print("=" * 80)
    print("📊 HOF COMPOSITE FITNESS RANKING")
    print(f"   Weights: OOS_R={WEIGHTS['oos_return']:.0%} OOS_P={WEIGHTS['oos_profitable']:.0%} "
          f"WF={WEIGHTS['wf_robustness']:.0%} IS={WEIGHTS['is_score']:.0%} "
          f"Trades={WEIGHTS['trade_count']:.0%} DD={WEIGHTS['drawdown']:.0%}")
    print("=" * 80)

    # Top 10
    print(f"\n{'#':<3} {'Fitness':>7} {'Name':<45} {'WF':>5} {'OOS':>7} {'OOS%':>5} {'IS':>6} {'Tr':>4} {'DD':>5} {'10w':>4}")
    print("-" * 95)
    for i, (h, fitness, comp) in enumerate(scored[:15], 1):
        wf = h.get("wf_robustness_10w", h.get("wf_robustness", 0))
        oos = h.get("avg_oos_return", 0)
        oos_pct = h.get("wf_profitable_10w", h.get("wf_profitable_assets", "?"))
        is_s = h.get("is_score", 0)
        trades = h.get("min_trades", 0)
        dd = h.get("avg_dd", 0)
        passed_10w = "✅" if h.get("wf_passed_10w") else "❌"
        print(f"{i:<3} {fitness:>7.3f} {h['name'][:45]:<45} {wf:>5.1f} {oos:>+6.2f}% {oos_pct:>5} {is_s:>6.2f} {trades:>4} {dd:>4.1f}% {passed_10w:>4}")

    # Component breakdown for top 5
    print(f"\n📋 COMPONENT BREAKDOWN (top 5):")
    for i, (h, fitness, comp) in enumerate(scored[:5], 1):
        wf = h.get("wf_robustness_10w", h.get("wf_robustness", 0))
        oos = h.get("avg_oos_return", 0)
        print(f"\n  {i}. {h['name'][:50]} (fitness={fitness:.3f})")
        print(f"     OOS_ret={comp['oos_return']:.2f} OOS_prof={comp['oos_profitable']:.2f} "
              f"WF={comp['wf_robustness']:.2f} IS={comp['is_score']:.2f} "
              f"Trades={comp['trade_count']:.2f} DD={comp['drawdown']:.2f}")
        print(f"     Raw: OOS={oos:+.2f}% WF={wf:.1f} IS={h.get('is_score',0):.2f} "
              f"trades={h.get('min_trades',0)} DD={h.get('avg_dd',0):.1f}%")
        print(f"     Entry: {h['entry_condition']}")

    # 10w champions only
    champs_10w = [(h, f, c) for h, f, c in scored if h.get("wf_passed_10w")]
    if champs_10w:
        print(f"\n🏆 10W CHAMPIONS RANKED BY FITNESS:")
        for i, (h, fitness, comp) in enumerate(champs_10w, 1):
            print(f"  {i}. {h['name'][:45]:<45} fitness={fitness:.3f} OOS={h.get('avg_oos_return',0):+.2f}%")


if __name__ == "__main__":
    main()