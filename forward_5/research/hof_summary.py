#!/usr/bin/env python3
"""HOF Summary — always run before claiming any 'new champion'.

Shows the full 10w-ranked HOF so you never miss existing champions.
Usage: python3 hof_summary.py
"""
import json
from pathlib import Path

HOF_PATH = Path(__file__).parent / "runs/evolution_v7/evolution_v7_hof.json"

def main():
    if not HOF_PATH.exists():
        print("No HOF file found.")
        return

    data = json.loads(HOF_PATH.read_text())
    hof = data["hof"]

    # Separate: 10w-passed vs 5w-only vs failed
    champions_10w = [h for h in hof if h.get("wf_passed_10w")]
    champions_5w = [h for h in hof if h.get("wf_passed") and not h.get("wf_passed_10w")]
    failed = [h for h in hof if not h.get("wf_passed")]

    # Sort by OOS return (best measure of real performance)
    champions_10w.sort(key=lambda h: h.get("avg_oos_return", -999), reverse=True)
    champions_5w.sort(key=lambda h: h.get("wf_robustness", 0), reverse=True)

    print("=" * 70)
    print("📊 HOF SUMMARY — FULL RANKING")
    print("=" * 70)

    print(f"\n🏆 10W CHAMPIONS ({len(champions_10w)}):")
    print(f"{'#':<3} {'Name':<50} {'WF':>5} {'10w':>5} {'OOS':>8} {'OOS%':>6} {'IS':>7} {'Type':>7}")
    print("-" * 100)
    for i, h in enumerate(champions_10w, 1):
        oos = h.get("avg_oos_return", 0)
        oos_pct = h.get("wf_profitable_10w", "?")
        print(f"{i:<3} {h['name'][:50]:<50} {h.get('wf_robustness',0):5.1f} {'✅':>5} {oos:+7.2f}% {oos_pct:>6} {h.get('is_score',0):7.2f} {h.get('strategy_type','?'):>7}")

    print(f"\n🥈 5W ONLY (not 10w-validated) ({len(champions_5w)}):")
    for i, h in enumerate(champions_5w, 1):
        print(f"{i:<3} {h['name'][:50]:<50} {h.get('wf_robustness',0):5.1f} {'❌':>5} {h.get('avg_oos_return',0):+7.2f}% {h.get('wf_profitable_assets','?'):>6} {h.get('is_score',0):7.2f} {h.get('strategy_type','?'):>7}")

    print(f"\n❌ FAILED ({len(failed)})")

    # Type breakdown
    types = {}
    for h in hof:
        t = h.get("strategy_type", "?")
        passed_10w = h.get("wf_passed_10w", False)
        passed_5w = h.get("wf_passed", False)
        if t not in types:
            types[t] = {"total": 0, "passed_5w": 0, "passed_10w": 0}
        types[t]["total"] += 1
        if passed_5w:
            types[t]["passed_5w"] += 1
        if passed_10w:
            types[t]["passed_10w"] += 1

    print(f"\n📋 TYPE BREAKDOWN:")
    print(f"{'Type':<10} {'Total':>6} {'5w✅':>6} {'10w✅':>6}")
    print("-" * 30)
    for t, d in sorted(types.items(), key=lambda x: x[1]["passed_10w"], reverse=True):
        print(f"{t:<10} {d['total']:>6} {d['passed_5w']:>6} {d['passed_10w']:>6}")

    # Best OOS champion
    if champions_10w:
        best = champions_10w[0]
        print(f"\n🌟 BEST OOS CHAMPION: {best['name']}")
        print(f"   OOS={best.get('avg_oos_return',0):+.2f}% | {best.get('wf_profitable_10w','?')} profitable periods")
        print(f"   Entry: {best['entry_condition']}")

    # Key warning
    mr_10w = sum(1 for h in champions_10w if h.get("strategy_type") == "MR")
    if mr_10w == len(champions_10w) and len(champions_10w) > 0:
        print(f"\n⚠️  ALL {len(champions_10w)} 10w-champions are MR — diversity problem!")

if __name__ == "__main__":
    main()