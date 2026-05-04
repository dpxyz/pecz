"""
Phase 1.1: 4h Sweep Signal Definitions

Defines all signal hypotheses to test on 4h data.
Each hypothesis is a simple config — the sweep engine does the rest.

Based on deep research findings:
- Mild negative funding (z ∈ [-0.5, 0)) is the proven edge (SOL champion)
- 4h is mathematically aligned with 8h funding epochs
- Bull trend filter (EMA200) improves robustness
- Trailing stops destroy performance
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SignalHypothesis:
    """One signal hypothesis to test."""
    name: str           # Human-readable name
    asset: str          # BTC, ETH, SOL, AVAX, DOGE, ADA
    direction: str      # "long" or "short"
    entry_z_low: float  # Lower bound of funding z-score range
    entry_z_high: float # Upper bound of funding z-score range
    bull_filter: str    # "none", "bull50", "bull200"
    hold_hours: int     # Hold duration in hours (must be multiple of 4)
    sl_pct: float       # Stop-loss percentage (0 = no SL)
    trail_pct: float    # Trailing stop percentage (0 = no trail)


def generate_hypotheses() -> list[SignalHypothesis]:
    """Generate all signal hypotheses for the 4h sweep.
    
    Strategy: systematic grid across the parameter space we know matters.
    """
    hypotheses = []
    assets = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
    
    # ── HYPOTHESIS GROUP 1: Mild Negative Funding Long ──
    # The proven edge: z ∈ [-0.5, 0) on SOL, now test on all assets + 4h
    for asset in assets:
        hypotheses.append(SignalHypothesis(
            name=f"{asset}_mild_neg_long_4h",
            asset=asset, direction="long",
            entry_z_low=-0.5, entry_z_high=0.0,
            bull_filter="none", hold_hours=24, sl_pct=5.0, trail_pct=0.0,
        ))
        # With bull200 filter
        hypotheses.append(SignalHypothesis(
            name=f"{asset}_mild_neg_bull200_4h",
            asset=asset, direction="long",
            entry_z_low=-0.5, entry_z_high=0.0,
            bull_filter="bull200", hold_hours=24, sl_pct=5.0, trail_pct=0.0,
        ))
    
    # ── HYPOTHESIS GROUP 2: Narrower z-ranges ──
    for asset in assets:
        # z ∈ [-0.3, 0) — very mild negative
        hypotheses.append(SignalHypothesis(
            name=f"{asset}_slight_neg_4h",
            asset=asset, direction="long",
            entry_z_low=-0.3, entry_z_high=0.0,
            bull_filter="none", hold_hours=24, sl_pct=5.0, trail_pct=0.0,
        ))
        # z ∈ [-1.0, -0.3) — moderate negative
        hypotheses.append(SignalHypothesis(
            name=f"{asset}_mod_neg_4h",
            asset=asset, direction="long",
            entry_z_low=-1.0, entry_z_high=-0.3,
            bull_filter="none", hold_hours=24, sl_pct=5.0, trail_pct=0.0,
        ))
    
    # ── HYPOTHESIS GROUP 3: Hold Duration ──
    # Test different hold periods on the champion range
    for asset in ["BTC", "ETH", "SOL"]:  # Top 3 only for speed
        for hold in [8, 12, 16, 20, 28, 32]:
            hypotheses.append(SignalHypothesis(
                name=f"{asset}_mild_neg_h{hold}_4h",
                asset=asset, direction="long",
                entry_z_low=-0.5, entry_z_high=0.0,
                bull_filter="none", hold_hours=hold, sl_pct=5.0, trail_pct=0.0,
            ))
    
    # ── HYPOTHESIS GROUP 4: Stop-Loss Variants ──
    for asset in ["BTC", "ETH", "SOL"]:
        for sl in [0.0, 3.0, 4.0, 7.0, 10.0]:
            hypotheses.append(SignalHypothesis(
                name=f"{asset}_mild_neg_sl{sl:.0f}_4h",
                asset=asset, direction="long",
                entry_z_low=-0.5, entry_z_high=0.0,
                bull_filter="none", hold_hours=24, sl_pct=sl, trail_pct=0.0,
            ))
    
    # ── HYPOTHESIS GROUP 5: Positive Funding Short (Extreme Only) ──
    # Deep research: z > 0.5 is DEAD, only z > 2.0 worth testing
    for asset in ["BTC", "ETH", "SOL"]:
        hypotheses.append(SignalHypothesis(
            name=f"{asset}_extreme_pos_short_4h",
            asset=asset, direction="short",
            entry_z_low=2.0, entry_z_high=10.0,
            bull_filter="none", hold_hours=24, sl_pct=5.0, trail_pct=0.0,
        ))
    
    # ── HYPOTHESIS GROUP 6: Cross-Sectional Funding ──
    # SOL funding below BTC average → long SOL
    # (Will be implemented as a special case in the engine)
    
    return hypotheses


if __name__ == "__main__":
    hyps = generate_hypotheses()
    print(f"Total hypotheses: {len(hyps)}")
    for h in hyps[:5]:
        print(f"  {h.name}: {h}")
    print(f"  ...")
    print(f"  {hyps[-1].name}: {hyps[-1]}")
    
    # Count by direction
    longs = sum(1 for h in hyps if h.direction == "long")
    shorts = sum(1 for h in hyps if h.direction == "short")
    print(f"\nLong hypotheses: {longs}, Short hypotheses: {shorts}")