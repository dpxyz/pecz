"""
Correlation Matrix for Signal Independence

Computes Spearman rank correlation between all signal returns.
Goal: identify uncorrelated signals (ρ < 0.7 = independent enough).

Spearman ρ preferred over Pearson because:
- Robust to outliers (rank-based)
- Captures monotonic relationships (not just linear)
- More appropriate for non-normal return distributions

Reference: deep_research_2_quantitative.md (cross-asset spillover)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

log = logging.getLogger("correlation_matrix")


@dataclass
class SignalCorrelation:
    """Correlation between two signal return streams."""
    signal_a: str
    signal_b: str
    spearman_rho: float
    p_value: float
    is_correlated: bool  # |ρ| >= 0.7
    interpretation: str = ""


@dataclass
class CorrelationMatrix:
    """Full correlation matrix across all signals."""
    signal_names: list[str]
    rho_matrix: np.ndarray  # NxN Spearman correlation
    p_value_matrix: np.ndarray  # NxN p-values
    n_observations: int
    correlated_pairs: list[SignalCorrelation] = field(default_factory=list)
    independent_pairs: list[SignalCorrelation] = field(default_factory=list)

    def get_correlation(self, signal_a: str, signal_b: str) -> Optional[SignalCorrelation]:
        """Get correlation between two specific signals."""
        if signal_a not in self.signal_names or signal_b not in self.signal_names:
            return None
        i = self.signal_names.index(signal_a)
        j = self.signal_names.index(signal_b)
        return SignalCorrelation(
            signal_a=signal_a,
            signal_b=signal_b,
            spearman_rho=float(self.rho_matrix[i, j]),
            p_value=float(self.p_value_matrix[i, j]),
            is_correlated=abs(self.rho_matrix[i, j]) >= 0.7,
        )

    def is_independent_of(self, signal: str, threshold: float = 0.7) -> list[str]:
        """List signals that are independent (|ρ| < threshold) of given signal."""
        if signal not in self.signal_names:
            return []
        i = self.signal_names.index(signal)
        independent = []
        for j, name in enumerate(self.signal_names):
            if i != j and abs(self.rho_matrix[i, j]) < threshold:
                independent.append(name)
        return independent

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [f"Correlation Matrix ({len(self.signal_names)} signals, {self.n_observations} obs)"]
        lines.append("")
        # Header
        short = [s[:8] for s in self.signal_names]
        lines.append(f"{'':>10}" + "".join(f"{s:>10}" for s in short))
        for i, name in enumerate(self.signal_names):
            row = "".join(f"{self.rho_matrix[i,j]:>10.2f}" for j in range(len(self.signal_names)))
            lines.append(f"{name[:10]:>10}{row}")
        lines.append("")
        if self.correlated_pairs:
            lines.append("⚠️ Correlated pairs (|ρ| ≥ 0.7):")
            for pair in self.correlated_pairs:
                lines.append(f"  {pair.signal_a} ↔ {pair.signal_b}: ρ={pair.spearman_rho:.3f}")
        if self.independent_pairs:
            lines.append("✅ Independent pairs (|ρ| < 0.7):")
            for pair in self.independent_pairs[:10]:
                lines.append(f"  {pair.signal_a} ↔ {pair.signal_b}: ρ={pair.spearman_rho:.3f}")
            if len(self.independent_pairs) > 10:
                lines.append(f"  ... and {len(self.independent_pairs) - 10} more")
        return "\n".join(lines)


def compute_correlation_matrix(
    signal_returns: dict[str, list[float]],
    threshold: float = 0.7,
) -> CorrelationMatrix:
    """Compute Spearman rank correlation matrix across signals.

    Args:
        signal_returns: dict mapping signal name → list of period returns
            All signals must have the same length (aligned time periods).
        threshold: correlation threshold (|ρ| >= threshold = correlated)

    Returns:
        CorrelationMatrix with full NxN correlation + classification
    """
    names = sorted(signal_returns.keys())
    n = len(names)

    if n < 2:
        return CorrelationMatrix(
            signal_names=names,
            rho_matrix=np.zeros((n, n)),
            p_value_matrix=np.zeros((n, n)),
            n_observations=0,
        )

    # Validate same length
    lengths = {k: len(v) for k, v in signal_returns.items()}
    if len(set(lengths.values())) > 1:
        # Trim to shortest common length (align by dropping tail)
        min_len = min(lengths.values())
        log.warning(f"Signal lengths differ {lengths}, trimming to {min_len}")
        for k in names:
            signal_returns[k] = signal_returns[k][:min_len]

    n_obs = len(signal_returns[names[0]])

    if n_obs < 20:
        log.warning(f"Only {n_obs} observations — correlation estimates unreliable")

    # Build matrix
    data = np.array([signal_returns[name] for name in names])  # shape (n_signals, n_obs)

    # Spearman rank correlation using scipy
    from scipy.stats import spearmanr
    rho_matrix, p_value_matrix = spearmanr(data, axis=1)

    # Ensure 2D (scipy returns scalar for 2 signals)
    if n == 2:
        rho_matrix = np.array([[1.0, rho_matrix], [rho_matrix, 1.0]])
        p_value_matrix = np.array([[0.0, p_value_matrix], [p_value_matrix, 0.0]])

    # Classify pairs
    correlated = []
    independent = []
    for i in range(n):
        for j in range(i + 1, n):
            rho = float(rho_matrix[i, j])
            p = float(p_value_matrix[i, j])
            pair = SignalCorrelation(
                signal_a=names[i],
                signal_b=names[j],
                spearman_rho=rho,
                p_value=p,
                is_correlated=abs(rho) >= threshold,
            )
            if pair.is_correlated:
                correlated.append(pair)
            else:
                independent.append(pair)

    return CorrelationMatrix(
        signal_names=names,
        rho_matrix=rho_matrix,
        p_value_matrix=p_value_matrix,
        n_observations=n_obs,
        correlated_pairs=correlated,
        independent_pairs=independent,
    )


def check_signal_independence(
    new_signal_returns: list[float],
    existing_signal_returns: dict[str, list[float]],
    new_signal_name: str = "new_signal",
    threshold: float = 0.7,
) -> dict:
    """Check if a new signal is independent of existing ones.

    Returns dict with:
    - is_independent: True if |ρ| < threshold with ALL existing signals
    - correlations: list of (name, rho) sorted by |rho| desc
    - blocking_signals: signals with |ρ| >= threshold
    """
    all_returns = {**existing_signal_returns, new_signal_name: new_signal_returns}
    matrix = compute_correlation_matrix(all_returns, threshold=threshold)

    correlations = []
    blocking = []

    for name in existing_signal_returns:
        corr = matrix.get_correlation(new_signal_name, name)
        if corr:
            correlations.append((name, corr.spearman_rho))
            if corr.is_correlated:
                blocking.append(name)

    correlations.sort(key=lambda x: abs(x[1]), reverse=True)

    return {
        "is_independent": len(blocking) == 0,
        "correlations": correlations,
        "blocking_signals": blocking,
        "interpretation": (
            f"✅ {new_signal_name} is independent of all existing signals"
            if not blocking
            else f"⚠️ {new_signal_name} is correlated with {blocking} (ρ≥{threshold})"
        ),
    }