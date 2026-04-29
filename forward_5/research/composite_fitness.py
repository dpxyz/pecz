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

# ─── Weight Configuration (V9) ───
# V9 weights: target-asset aware, no IS score, added drawdown
# All components normalized to [0, 1] before weighting
WEIGHTS = {
    "oos_return": 0.30,          # Out-of-sample return (30% — the reality check)
    "target_asset_profitable": 0.25,  # Per target-asset-group ratio (25%)
    "trade_quality": 0.20,       # Min trades per asset/window (20%)
    "wf_robustness": 0.15,       # Walk-forward robustness (15%)
    "drawdown": 0.10,            # Drawdown penalty (10%)
}

# Normalization ranges (V9)
NORM = {
    "oos_return": (0, 2.0),              # 0..+2% mapped to 0..1, hard floor at 0
    "target_asset_profitable": (0, 1.0),  # already 0..1 ratio
    "trade_quality": (3, 50),             # 3..50 trades per asset/window, floor at 3
    "wf_robustness": (0, 100),            # 0..100 mapped to 0..1
    "drawdown": (0, 20),                   # 0..20% DD mapped to 0..1 (inverted), >20% = 0
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


def compute_fitness(h, target_assets=None):
    """Compute composite fitness score for a HOF entry.
    
    target_assets: list of primary assets (e.g., ['DOGE', 'ADA', 'AVAX'] for MR).
        If None, all assets are targets (legacy behavior).
    """
    # 1. OOS Return (hard floor at 0 — negative returns = 0)
    oos = max(0, h.get("avg_oos_return", 0))
    oos_norm = normalize(oos, *NORM["oos_return"])

    # 2. Target-Asset Profitable Ratio
    #    If target_assets specified, check profitable ratio among those assets
    if target_assets:
        wf_assets = h.get("assets", {})
        target_profitable = sum(1 for a in target_assets if a in wf_assets and wf_assets[a].get("avg_oos_return", 0) > 0)
        target_count = max(1, sum(1 for a in target_assets if a in wf_assets))
        tap_ratio = target_profitable / target_count
    else:
        tap_ratio = parse_profitable_ratio(h.get("wf_profitable_10w", h.get("wf_profitable_assets", "0/6")))
    tap_norm = normalize(tap_ratio, *NORM["target_asset_profitable"])

    # 3. Trade Quality (min_trades, floor at 3)
    trades = max(3, h.get("min_trades", 0))
    trades_norm = normalize(trades, *NORM["trade_quality"])

    # 4. WF Robustness
    wf = h.get("wf_robustness_10w", h.get("wf_robustness", 0))
    wf_norm = normalize(wf, *NORM["wf_robustness"])

    # 5. Drawdown (inverted: lower = better, >20% = 0)
    dd = h.get("avg_dd", 50)
    if dd > 20:
        dd_norm = 0.0
    else:
        dd_norm = 1.0 - normalize(dd, *NORM["drawdown"])

    # Weighted sum
    fitness = (
        WEIGHTS["oos_return"] * oos_norm +
        WEIGHTS["target_asset_profitable"] * tap_norm +
        WEIGHTS["trade_quality"] * trades_norm +
        WEIGHTS["wf_robustness"] * wf_norm +
        WEIGHTS["drawdown"] * dd_norm
    )

    components = {
        "oos_return": round(oos_norm, 3),
        "target_asset_profitable": round(tap_norm, 3),
        "trade_quality": round(trades_norm, 3),
        "wf_robustness": round(wf_norm, 3),
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
    print(f"   Weights: OOS_R={WEIGHTS['oos_return']:.0%} TAP={WEIGHTS['target_asset_profitable']:.0%} "
          f"TQ={WEIGHTS['trade_quality']:.0%} WF={WEIGHTS['wf_robustness']:.0%} "
          f"DD={WEIGHTS['drawdown']:.0%}")
    print("=" * 80)

    # Top 10
    print(f"\n{'#':<3} {'Fitness':>7} {'Name':<45} {'WF':>5} {'OOS':>7} {'TAP':>5} {'TQ':>4} {'DD':>5} {'10w':>4}")
    print("-" * 95)
    for i, (h, fitness, comp) in enumerate(scored[:15], 1):
        wf = h.get("wf_robustness_10w", h.get("wf_robustness", 0))
        oos = h.get("avg_oos_return", 0)
        tap = comp.get("target_asset_profitable", 0)
        tq = comp.get("trade_quality", 0)
        dd = h.get("avg_dd", 0)
        passed_10w = "✅" if h.get("wf_passed_10w") else "❌"
        print(f"{i:<3} {fitness:>7.3f} {h['name'][:45]:<45} {wf:>5.1f} {oos:>+6.2f}% {tap:>5.2f} {tq:>4.2f} {dd:>4.1f}% {passed_10w:>4}")

    # Component breakdown for top 5
    print(f"\n📋 COMPONENT BREAKDOWN (top 5):")
    for i, (h, fitness, comp) in enumerate(scored[:5], 1):
        wf = h.get("wf_robustness_10w", h.get("wf_robustness", 0))
        oos = h.get("avg_oos_return", 0)
        print(f"\n  {i}. {h['name'][:50]} (fitness={fitness:.3f})")
        print(f"     OOS_ret={comp['oos_return']:.2f} TAP={comp['target_asset_profitable']:.2f} "
              f"TQ={comp['trade_quality']:.2f} WF={comp['wf_robustness']:.2f} "
              f"DD={comp['drawdown']:.2f}")
        print(f"     Raw: OOS={oos:+.2f}% WF={wf:.1f} "
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