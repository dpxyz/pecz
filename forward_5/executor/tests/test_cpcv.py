"""Tests for CPCV (Combinatorial Purged Cross-Validation)"""

import pytest
import numpy as np
from cpcv import (
    CPCVConfig, CPCVResult, CPCVPath,
    split_into_groups, generate_cpcv_paths,
    evaluate_cpcv, evaluate_cpcv_equity,
)


class TestSplitIntoGroups:
    def test_even_split(self):
        groups = split_into_groups(60, 6)
        assert len(groups) == 6
        assert sum(len(g) for g in groups) == 60
        for g in groups:
            assert len(g) == 10

    def test_uneven_split(self):
        groups = split_into_groups(65, 6)
        assert len(groups) == 6
        assert sum(len(g) for g in groups) == 65
        # First 5 groups should have 11, last group 10
        sizes = [len(g) for g in groups]
        assert 10 in sizes
        assert 11 in sizes

    def test_more_groups_than_samples(self):
        groups = split_into_groups(4, 10)
        assert len(groups) == 4
        assert sum(len(g) for g in groups) == 4

    def test_single_group(self):
        groups = split_into_groups(100, 1)
        assert len(groups) == 1
        assert len(groups[0]) == 100


class TestGenerateCPCVPaths:
    def test_six_groups_two_test(self):
        paths = generate_cpcv_paths(120, CPCVConfig(n_groups=6, n_test_groups=2, embargo_bars=0))
        # C(6,2) = 15 paths
        assert len(paths) == 15

    def test_no_overlap_between_train_test(self):
        paths = generate_cpcv_paths(120, CPCVConfig(n_groups=6, n_test_groups=2, embargo_bars=0))
        for path in paths:
            train_set = set(path.train_indices)
            test_set = set(path.test_indices)
            assert len(train_set & test_set) == 0, "Train and test overlap!"

    def test_all_indices_covered(self):
        paths = generate_cpcv_paths(120, CPCVConfig(n_groups=6, n_test_groups=2, embargo_bars=0))
        for path in paths:
            train_set = set(path.train_indices)
            test_set = set(path.test_indices)
            # Together they should cover all indices (minus purged/embargo)
            # With no embargo, and purging only removes adjacent, check coverage is high
            total = len(train_set) + len(test_set)
            assert total >= 100  # most indices should be present

    def test_embargo_removes_samples(self):
        paths_no_embargo = generate_cpcv_paths(120, CPCVConfig(n_groups=6, n_test_groups=2, embargo_bars=0))
        paths_with_embargo = generate_cpcv_paths(120, CPCVConfig(n_groups=6, n_test_groups=2, embargo_bars=12))
        
        # With embargo, train sets should be smaller
        avg_train_no_e = np.mean([len(p.train_indices) for p in paths_no_embargo])
        avg_train_with_e = np.mean([len(p.train_indices) for p in paths_with_embargo])
        assert avg_train_with_e < avg_train_no_e


class TestEvaluateCPCV:
    def test_perfect_strategy(self):
        """A strategy that always profits should pass all paths."""
        # 200 trades, all +1% return
        returns = [0.01] * 200
        timestamps = list(range(200))
        result = evaluate_cpcv(returns, timestamps, CPCVConfig(n_groups=6, n_test_groups=2, embargo_bars=0))
        assert result.n_profitable > 0
        assert result.all_paths_profitable is True
        assert result.pbo == 0.0

    def test_losing_strategy(self):
        """A strategy that always loses should fail."""
        returns = [-0.01] * 200
        timestamps = list(range(200))
        result = evaluate_cpcv(returns, timestamps, CPCVConfig(n_groups=6, n_test_groups=2, embargo_bars=0))
        assert result.n_profitable == 0
        assert result.pbo == 1.0

    def test_mixed_strategy(self):
        """A strategy with slight positive edge."""
        np.random.seed(42)
        # Slight edge: mean=0.5%, std=3%
        returns = np.random.normal(0.005, 0.03, 200).tolist()
        timestamps = list(range(200))
        result = evaluate_cpcv(returns, timestamps, CPCVConfig(n_groups=6, n_test_groups=2, embargo_bars=0))
        # Should have some profitable paths
        assert result.n_paths > 0

    def test_too_few_trades(self):
        """With very few trades, should return error result."""
        returns = [0.01, -0.01, 0.02]
        timestamps = [0, 1, 2]
        result = evaluate_cpcv(returns, timestamps, CPCVConfig())
        assert result.pbo == 1.0  # too few = assumed overfit


class TestEvaluateCPCVEquity:
    def test_growing_equity(self):
        """Monotonically growing equity curve should pass."""
        equity = [100 + i * 0.5 for i in range(60)]
        result = evaluate_cpcv_equity(equity, CPCVConfig(n_groups=6, n_test_groups=2, embargo_bars=0))
        assert result.n_profitable > 0

    def test_declining_equity(self):
        """Declining equity should fail."""
        equity = [100 - i * 0.3 for i in range(60)]
        result = evaluate_cpcv_equity(equity, CPCVConfig(n_groups=6, n_test_groups=2, embargo_bars=0))
        assert result.n_profitable == 0

    def test_short_equity(self):
        """Too short equity curve."""
        equity = [100, 101, 99]
        result = evaluate_cpcv_equity(equity, CPCVConfig())
        assert result.pbo == 1.0


class TestCPCVConfig:
    def test_default_config(self):
        config = CPCVConfig()
        assert config.n_groups == 6
        assert config.n_test_groups == 2
        assert config.embargo_bars == 48
        assert config.min_trades_per_path == 10

    def test_custom_config(self):
        config = CPCVConfig(n_groups=8, n_test_groups=3, embargo_bars=24)
        assert config.n_groups == 8
        assert config.n_test_groups == 3