"""
Benjamini-Hochberg False Discovery Rate (BH-FDR)

Implements BH-FDR as a less conservative alternative to Bonferroni.
- Bonferroni controls FWER (probability of ANY false positive) → too strict at large N
- BH-FDR controls FDR (expected fraction of false discoveries) → more power

At N=1000, α=0.05:
  Bonferroni threshold: p ≤ 0.00005 (kills true signals)
  BH-FDR threshold: adaptive by rank, typically p ≤ 0.001-0.05 (finds more real signals)

For Foundry V13: Use BH-FDR for Discovery phase, Bonferroni for Production gate.

Reference: deep_research_foundry_v13_part2.txt (Section 3)
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

log = logging.getLogger("bh_fdr")


@dataclass
class BHFDRResult:
    """Result of Benjamini-Hochberg FDR procedure."""
    n_tests: int
    alpha: float  # target FDR level
    n_discoveries: int  # number of significant results after BH
    discoveries: list[dict]  # [{index, p_value, adjusted_threshold, rank}]
    fdr_estimate: float  # estimated false discovery rate
    bonferroni_would_find: int  # how many Bonferroni would find (comparison)
    interpretation: str = ""


def benjamini_hochberg(
    p_values: list[float],
    alpha: float = 0.05,
) -> BHFDRResult:
    """Benjamini-Hochberg FDR procedure.
    
    Algorithm:
    1. Sort p-values in ascending order: p_(1) ≤ p_(2) ≤ ... ≤ p_(m)
    2. Find largest k where p_(k) ≤ (k/m) * α
    3. Reject H0 for all hypotheses 1..k
    
    This controls FDR at level α when tests are independent or
    positively dependent (PRDS condition).
    
    Args:
        p_values: list of p-values from all tests
        alpha: target FDR level (default 0.05)
    
    Returns:
        BHFDRResult with discoveries and comparison to Bonferroni
    """
    m = len(p_values)
    
    if m == 0:
        return BHFDRResult(
            n_tests=0, alpha=alpha, n_discoveries=0,
            discoveries=[], fdr_estimate=0, bonferroni_would_find=0,
            interpretation="No tests performed"
        )
    
    # Sort p-values with original indices
    indexed = [(i, p) for i, p in enumerate(p_values)]
    indexed.sort(key=lambda x: x[1])
    
    # Find largest k where p_(k) ≤ (k/m) * alpha
    k_max = 0
    for rank_minus_1, (orig_idx, p) in enumerate(indexed):
        rank = rank_minus_1 + 1
        threshold = (rank / m) * alpha
        if p <= threshold:
            k_max = rank
    
    # Build discoveries list
    discoveries = []
    for rank_minus_1, (orig_idx, p) in enumerate(indexed):
        rank = rank_minus_1 + 1
        threshold = (rank / m) * alpha
        is_discovery = rank <= k_max
        discoveries.append({
            "index": orig_idx,
            "p_value": p,
            "adjusted_threshold": threshold,
            "rank": rank,
            "is_discovery": is_discovery,
        })
    
    n_discoveries = k_max
    
    # FDR estimate = (m * alpha) / max(k, 1) for the accepted set
    fdr_estimate = (m * alpha) / max(n_discoveries, 1)
    
    # Bonferroni comparison
    bonf_threshold = alpha / m
    bonf_count = sum(1 for p in p_values if p < bonf_threshold)
    
    if n_discoveries > 0:
        interp = f"BH-FDR: {n_discoveries}/{m} discoveries at FDR={alpha:.0%}, est. {fdr_estimate:.2%} false, Bonferroni would find {bonf_count}"
    else:
        interp = f"BH-FDR: 0/{m} discoveries at FDR={alpha:.0%}, Bonferroni would find {bonf_count}"
    
    log.info(interp)
    
    return BHFDRResult(
        n_tests=m,
        alpha=alpha,
        n_discoveries=n_discoveries,
        discoveries=discoveries,
        fdr_estimate=min(fdr_estimate, alpha),  # cap at alpha
        bonferroni_would_find=bonf_count,
        interpretation=interp,
    )


def holm_correction(
    p_values: list[float],
    alpha: float = 0.05,
) -> dict:
    """Holm-Bonferroni step-down procedure.
    
    Less conservative than Bonferroni, still controls FWER.
    Step-down: compare each sorted p-value against α/(m-k+1).
    
    Args:
        p_values: list of p-values
        alpha: FWER level
    
    Returns:
        dict with n_significant, is_significant list, interpretation
    """
    m = len(p_values)
    if m == 0:
        return {"n_significant": 0, "is_significant": [], "interpretation": "No tests"}
    
    indexed = [(i, p) for i, p in enumerate(p_values)]
    indexed.sort(key=lambda x: x[1])
    
    is_significant = [False] * m
    n_sig = 0
    
    for rank_minus_1, (orig_idx, p) in enumerate(indexed):
        rank = rank_minus_1 + 1
        threshold = alpha / (m - rank + 1)
        if p <= threshold:
            is_significant[orig_idx] = True
            n_sig += 1
        else:
            # Holm stops at first non-rejection
            break
    
    return {
        "n_significant": n_sig,
        "is_significant": is_significant,
        "interpretation": f"Holm-Bonferroni: {n_sig}/{m} significant at FWER={alpha:.0%}"
    }


def cluster_effective_n(
    returns_matrix: list[list[float]],
    threshold: float = 0.7,
) -> int:
    """Estimate effective N via hierarchical clustering of return series.
    
    When 200 backtest variants are run, many are highly correlated.
    The effective N (number of independent tests) is much lower.
    This uses Spearman correlation + single-linkage clustering.
    
    Critical for DSR: using N=200 would make DSR thresholds unreachable,
    but if those 200 variants cluster into 15 independent groups,
    N_eff=15 is the right input for DSR.
    
    Args:
        returns_matrix: list of return series (one per backtest variant)
        threshold: correlation threshold for clustering (ρ ≥ threshold = same cluster)
    
    Returns:
        effective N (number of independent clusters)
    """
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform
    from scipy.stats import spearmanr
    
    if len(returns_matrix) <= 1:
        return len(returns_matrix)
    
    data = np.array(returns_matrix)
    
    # Handle very short series
    if data.shape[1] < 5:
        return len(returns_matrix)
    
    # Spearman correlation
    try:
        corr_matrix, _ = spearmanr(data, axis=1)
        if corr_matrix.ndim == 0:  # scalar for 2 series
            corr_matrix = np.array([[1.0, float(corr_matrix)], [float(corr_matrix), 1.0]])
    except Exception:
        return len(returns_matrix)
    
    # Distance = 1 - |correlation|
    dist_matrix = 1 - np.abs(corr_matrix)
    np.fill_diagonal(dist_matrix, 0)
    
    # Ensure symmetric and valid
    dist_matrix = np.maximum(dist_matrix, 0)
    dist_matrix = (dist_matrix + dist_matrix.T) / 2
    
    # Convert to condensed form for scipy
    try:
        condensed = squareform(dist_matrix)
    except Exception:
        return len(returns_matrix)
    
    # Hierarchical clustering (single linkage)
    Z = linkage(condensed, method='single')
    
    # Cut at distance = 1 - threshold (clusters where |ρ| >= threshold merge)
    cut_distance = 1 - threshold
    clusters = fcluster(Z, t=cut_distance, criterion='distance')
    
    n_effective = len(set(clusters))
    
    log.info(f"Cluster effective N: {len(returns_matrix)} variants → {n_effective} independent clusters (threshold ρ≥{threshold})")
    
    return n_effective