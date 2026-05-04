"""Tests for BH-FDR and cluster_effective_n"""

import pytest
import numpy as np
from bh_fdr import benjamini_hochberg, holm_correction, cluster_effective_n, BHFDRResult


class TestBenjaminiHochberg:
    def test_no_discoveries(self):
        """All large p-values → no discoveries."""
        p_values = [0.5, 0.6, 0.7, 0.8, 0.9]
        result = benjamini_hochberg(p_values, alpha=0.05)
        assert result.n_discoveries == 0
        assert result.n_tests == 5

    def test_all_discoveries(self):
        """All very small p-values → all discoveries."""
        p_values = [1e-10, 1e-8, 1e-6, 1e-4, 1e-3]
        result = benjamini_hochberg(p_values, alpha=0.05)
        assert result.n_discoveries == 5

    def test_partial_discoveries(self):
        """Some significant, some not."""
        p_values = [0.001, 0.005, 0.03, 0.15, 0.4]
        result = benjamini_hochberg(p_values, alpha=0.05)
        # First few should be discovered
        assert result.n_discoveries >= 2
        assert result.n_discoveries < 5

    def test_bonferroni_comparison(self):
        """BH should find at least as many as Bonferroni."""
        np.random.seed(42)
        # 100 tests, 10 with true signal
        p_values = [1e-6] * 10 + list(np.random.uniform(0.1, 0.9, 90))
        result = benjamini_hochberg(p_values, alpha=0.05)
        assert result.n_discoveries >= result.bonferroni_would_find
        assert result.bonferroni_would_find <= 10  # Bonferroni finds at most the 10 true

    def test_empty_input(self):
        result = benjamini_hochberg([], alpha=0.05)
        assert result.n_discoveries == 0

    def test_single_test(self):
        result = benjamini_hochberg([0.01], alpha=0.05)
        assert result.n_discoveries == 1

    def test_ranking(self):
        """Discoveries should be sorted by p-value rank."""
        p_values = [0.3, 0.001, 0.5, 0.01]
        result = benjamini_hochberg(p_values, alpha=0.05)
        # Discoveries should reference original indices
        for d in result.discoveries:
            assert d["index"] in range(4)

    def test_large_N(self):
        """At N=1000, BH should still find true signals."""
        np.random.seed(42)
        p_values = [1e-8] * 5 + list(np.random.uniform(0.3, 1.0, 995))
        result = benjamini_hochberg(p_values, alpha=0.05)
        assert result.n_discoveries >= 5
        # Bonferroni at N=1000 would need p < 0.00005
        assert result.bonferroni_would_find <= 5


class TestHolmCorrection:
    def test_all_significant(self):
        p_values = [1e-10, 1e-8, 1e-6]
        result = holm_correction(p_values, alpha=0.05)
        assert result["n_significant"] == 3

    def test_none_significant(self):
        p_values = [0.5, 0.6, 0.7]
        result = holm_correction(p_values, alpha=0.05)
        assert result["n_significant"] == 0

    def test_step_down_stops(self):
        """Holm stops at first non-rejection."""
        p_values = [0.001, 0.01, 0.08, 0.001]  # sorted: 0.001, 0.001, 0.01, 0.08
        result = holm_correction(p_values, alpha=0.05)
        # First two should pass (threshold = 0.05/4, 0.05/3)
        # Third: threshold = 0.05/2 = 0.025, p=0.01 passes
        # Fourth: threshold = 0.05/1 = 0.05, p=0.08 fails → stops
        assert result["n_significant"] >= 2

    def test_empty(self):
        result = holm_correction([], alpha=0.05)
        assert result["n_significant"] == 0


class TestClusterEffectiveN:
    def test_independent_series(self):
        """Independent series should give N_eff ≈ N."""
        np.random.seed(42)
        series = [np.random.normal(0, 1, 100).tolist() for _ in range(10)]
        n_eff = cluster_effective_n(series, threshold=0.7)
        # Should be close to 10 for independent series
        assert n_eff >= 7  # some randomness but should be high

    def test_identical_series(self):
        """Identical series should cluster to N_eff=1."""
        base = np.random.normal(0, 1, 100).tolist()
        series = [base for _ in range(10)]
        n_eff = cluster_effective_n(series, threshold=0.7)
        assert n_eff == 1  # all identical → 1 cluster

    def test_two_groups(self):
        """Two groups of correlated series → N_eff=2."""
        np.random.seed(42)
        base_a = np.random.normal(0, 1, 100)
        base_b = np.random.normal(0, 1, 100)
        # Group A: base_a + noise
        series_a = [base_a + np.random.normal(0, 0.01, 100) for _ in range(5)]
        # Group B: base_b + noise
        series_b = [base_b + np.random.normal(0, 0.01, 100) for _ in range(5)]
        series = [s.tolist() for s in series_a + series_b]
        n_eff = cluster_effective_n(series, threshold=0.7)
        assert n_eff <= 4  # should cluster into ~2 groups

    def test_single_series(self):
        n_eff = cluster_effective_n([[0.1, 0.2, 0.3]], threshold=0.7)
        assert n_eff == 1

    def test_empty(self):
        n_eff = cluster_effective_n([], threshold=0.7)
        assert n_eff == 0