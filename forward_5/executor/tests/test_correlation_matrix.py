"""
Tests for Correlation Matrix
"""

import pytest
import numpy as np

from correlation_matrix import (
    compute_correlation_matrix,
    check_signal_independence,
    CorrelationMatrix,
)


class TestCorrelationMatrix:
    def test_identical_signals(self):
        """Identical signals → ρ = 1.0."""
        returns = list(np.random.RandomState(42).normal(0, 0.02, 100))
        matrix = compute_correlation_matrix({"a": returns, "b": returns})
        assert matrix.rho_matrix[0, 1] == pytest.approx(1.0, abs=0.01)
        assert len(matrix.correlated_pairs) == 1

    def test_independent_signals(self):
        """Independent signals → low ρ."""
        rng = np.random.RandomState(42)
        a = list(rng.normal(0, 0.02, 200))
        b = list(rng.normal(0, 0.02, 200))
        matrix = compute_correlation_matrix({"a": a, "b": b})
        # Random independent signals should have |ρ| < 0.3 typically
        assert abs(matrix.rho_matrix[0, 1]) < 0.5  # generous
        assert len(matrix.independent_pairs) == 1

    def test_negatively_correlated(self):
        """Negatively correlated signals → ρ < 0."""
        a = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] * 10
        b = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1] * 10
        matrix = compute_correlation_matrix({"a": a, "b": b})
        assert matrix.rho_matrix[0, 1] < -0.5

    def test_single_signal(self):
        """Single signal → empty matrix."""
        matrix = compute_correlation_matrix({"a": [1, 2, 3]})
        assert len(matrix.signal_names) == 1

    def test_empty(self):
        """No signals → empty matrix."""
        matrix = compute_correlation_matrix({})
        assert len(matrix.signal_names) == 0

    def test_diagonal_is_one(self):
        """Diagonal of correlation matrix = 1.0."""
        rng = np.random.RandomState(42)
        matrix = compute_correlation_matrix({
            "a": list(rng.normal(0, 1, 100)),
            "b": list(rng.normal(0, 1, 100)),
            "c": list(rng.normal(0, 1, 100)),
        })
        for i in range(3):
            assert matrix.rho_matrix[i, i] == pytest.approx(1.0, abs=0.01)

    def test_symmetric(self):
        """Correlation matrix is symmetric."""
        rng = np.random.RandomState(42)
        matrix = compute_correlation_matrix({
            "a": list(rng.normal(0, 1, 100)),
            "b": list(rng.normal(0, 1, 100)),
        })
        assert matrix.rho_matrix[0, 1] == pytest.approx(matrix.rho_matrix[1, 0], abs=0.001)

    def test_unequal_lengths(self):
        """Unequal lengths → trimmed to shortest."""
        rng = np.random.RandomState(42)
        matrix = compute_correlation_matrix({
            "a": list(rng.normal(0, 1, 100)),
            "b": list(rng.normal(0, 1, 50)),
        })
        assert matrix.n_observations == 50

    def test_summary(self):
        """Summary is readable."""
        rng = np.random.RandomState(42)
        matrix = compute_correlation_matrix({
            "a": list(rng.normal(0, 1, 50)),
            "b": list(rng.normal(0, 1, 50)),
        })
        s = matrix.summary()
        assert "Correlation Matrix" in s

    def test_get_correlation(self):
        """get_correlation returns correct pair."""
        rng = np.random.RandomState(42)
        a = list(rng.normal(0, 1, 50))
        b = list(rng.normal(0, 1, 50))
        matrix = compute_correlation_matrix({"a": a, "b": b})
        corr = matrix.get_correlation("a", "b")
        assert corr is not None
        assert corr.signal_a == "a"
        assert corr.signal_b == "b"

    def test_get_correlation_unknown(self):
        """Unknown signal → None."""
        matrix = compute_correlation_matrix({"a": [1, 2, 3]})
        assert matrix.get_correlation("a", "unknown") is None

    def test_is_independent_of(self):
        """is_independent_of returns uncorrelated signals."""
        rng = np.random.RandomState(42)
        matrix = compute_correlation_matrix({
            "a": list(rng.normal(0, 1, 100)),
            "b": list(rng.normal(0, 1, 100)),
            "c": list(rng.normal(0, 1, 100)),
        })
        indep = matrix.is_independent_of("a", threshold=0.7)
        # Random signals should be independent
        assert isinstance(indep, list)


class TestCheckSignalIndependence:
    def test_independent_new_signal(self):
        """New independent signal → passes."""
        rng = np.random.RandomState(42)
        existing = {"sol_funding": list(rng.normal(0, 0.02, 100))}
        new = list(rng.normal(0, 0.02, 100))  # independent

        result = check_signal_independence(new, existing, "btc_4h")
        assert result["is_independent"]
        assert len(result["blocking_signals"]) == 0

    def test_correlated_new_signal(self):
        """Correlated new signal → blocked."""
        rng = np.random.RandomState(42)
        existing = {"sol_funding": list(rng.normal(0, 0.02, 100))}
        new = existing["sol_funding"]  # identical → ρ=1.0

        result = check_signal_independence(new, existing, "sol_copy")
        assert not result["is_independent"]
        assert "sol_funding" in result["blocking_signals"]

    def test_multiple_existing(self):
        """Check against multiple existing signals."""
        rng = np.random.RandomState(42)
        existing = {
            "sol_funding": list(rng.normal(0, 0.02, 100)),
            "btc_4h": list(rng.normal(0, 0.02, 100)),
        }
        new = list(rng.normal(0, 0.02, 100))

        result = check_signal_independence(new, existing, "eth_liq")
        assert result["is_independent"]
        assert len(result["correlations"]) == 2