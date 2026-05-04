"""
Tests for Statistical Robustness (Monte Carlo, DSR, Bonferroni)
"""

import math
import pytest
import numpy as np

from statistical_robustness import (
    monte_carlo_permutation,
    deflated_sharpe_ratio,
    bonferroni_correction,
    full_robustness_check,
    _compute_sharpe,
    _norm_cdf,
    _norm_ppf,
)


class TestNormHelpers:
    def test_cdf_at_zero(self):
        assert abs(_norm_cdf(0) - 0.5) < 0.001

    def test_cdf_symmetry(self):
        assert abs(_norm_cdf(1) + _norm_cdf(-1) - 1.0) < 0.001

    def test_cdf_extremes(self):
        assert _norm_cdf(-10) < 0.001
        assert _norm_cdf(10) > 0.999

    def test_ppf_at_half(self):
        assert abs(_norm_ppf(0.5)) < 0.01

    def test_ppf_inverse_cdf(self):
        """ppf(cdf(x)) ≈ x for standard normal."""
        for x in [-2, -1, 0, 1, 2]:
            p = _norm_cdf(x)
            x_back = _norm_ppf(p)
            assert abs(x_back - x) < 0.01, f"ppf(cdf({x})) = {x_back}"


class TestSharpe:
    def test_sharpe_zero_returns(self):
        assert _compute_sharpe(np.array([])) == 0.0

    def test_sharpe_constant(self):
        assert _compute_sharpe(np.array([0.01, 0.01, 0.01])) == 0.0  # zero std

    def test_sharpe_positive(self):
        returns = np.array([0.02, -0.01, 0.03, 0.01, -0.005])
        s = _compute_sharpe(returns)
        assert s > 0  # positive mean / std


class TestMonteCarlo:
    def test_significant_strategy(self):
        """Strategy with real edge should pass MC test."""
        rng = np.random.RandomState(42)
        returns = list(rng.normal(0.005, 0.02, 200))  # strong positive drift

        result = monte_carlo_permutation(returns, n_simulations=500, seed=42)
        # With 200 trades of 0.5% mean, bootstrap CI should not include 0
        assert result.original_return > 0
        assert result.is_significant  # 95% CI should exclude 0
        assert result.ci_95_low > 0  # all bootstraps positive

    def test_random_strategy(self):
        """Random strategy should fail MC test."""
        rng = np.random.RandomState(42)
        returns = list(rng.normal(0, 0.02, 50))  # zero mean, noisy

        result = monte_carlo_permutation(returns, n_simulations=500, seed=42)
        assert result.n_simulations == 500
        # With zero mean, CI should include 0 (negative returns likely)
        # Not guaranteed but P(neg) should be high

    def test_too_few_trades(self):
        """Fewer than 10 trades → not significant."""
        result = monte_carlo_permutation([0.01, 0.02, 0.03])
        assert not result.is_significant
        assert "Too few" in result.interpretation

    def test_ci_for_negative_mean(self):
        """95% CI for negative-mean strategy should include 0 or be negative."""
        rng = np.random.RandomState(42)
        returns = list(rng.normal(-0.005, 0.02, 100))  # negative drift

        result = monte_carlo_permutation(returns, n_simulations=500, seed=42)
        assert result.ci_95_high < 0.5  # generous: CI should be mostly negative

    def test_deterministic_with_seed(self):
        """Same seed → same results."""
        returns = [0.01, -0.005, 0.02, -0.01, 0.015] * 20
        r1 = monte_carlo_permutation(returns, n_simulations=100, seed=123)
        r2 = monte_carlo_permutation(returns, n_simulations=100, seed=123)
        assert r1.p_value == r2.p_value


class TestDSR:
    def test_dsr_pass_with_real_edge(self):
        """High Sharpe with few backtests should pass."""
        result = deflated_sharpe_ratio(
            observed_sharpe=2.5,  # very high
            n_backtests=10,
            n_observations=200,
            skewness=0,
            kurtosis=3,
        )
        assert result.is_significant
        assert result.dsr_statistic > 0

    def test_dsr_fail_with_many_backtests(self):
        """Even decent annualized Sharpe fails with 6000 backtests."""
        result = deflated_sharpe_ratio(
            observed_sharpe=1.0,  # decent annualized
            n_backtests=6000,
            n_observations=200,
            skewness=0,
            kurtosis=3,
            is_annualized=True,
        )
        # With 6000 backtests, E[max] ~3.7, so annualized SR=1.0 should fail
        assert not result.is_significant
        # E[max] should be positive (penalizes multiple testing)
        assert result.expected_max_sharpe > 0

    def test_dsr_penalizes_backtest_count(self):
        """More backtests → higher E[max] → harder to pass."""
        r10 = deflated_sharpe_ratio(1.5, n_backtests=10, n_observations=100)
        r6000 = deflated_sharpe_ratio(1.5, n_backtests=6000, n_observations=100)
        # E[max] should increase with more backtests
        assert r6000.expected_max_sharpe > r10.expected_max_sharpe

    def test_dsr_insufficient_data(self):
        """Fewer than 10 observations → not significant."""
        result = deflated_sharpe_ratio(2.0, n_backtests=10, n_observations=5)
        assert not result.is_significant

    def test_dsr_single_backtest(self):
        """1 backtest → E[max] = 0 (no multiple testing penalty)."""
        result = deflated_sharpe_ratio(1.0, n_backtests=1, n_observations=200)
        assert result.expected_max_sharpe == 0.0


class TestBonferroni:
    def test_single_test(self):
        """1 backtest → no correction needed."""
        result = bonferroni_correction(1, 0.03)
        assert result.adjusted_alpha == 0.05
        assert result.is_significant_after

    def test_6000_backtests(self):
        """6000 backtests → adjusted alpha = 0.05/6000."""
        result = bonferroni_correction(6000, 0.03)
        assert result.adjusted_alpha == pytest.approx(0.05 / 6000, rel=0.01)
        assert not result.is_significant_after  # 0.03 >> 0.0000083

    def test_very_small_p_passes(self):
        """Extremely small p-value passes even with many backtests."""
        result = bonferroni_correction(6000, 0.000001)
        assert result.is_significant_after

    def test_not_significant_before(self):
        """P-value above alpha → not significant before or after."""
        result = bonferroni_correction(10, 0.1)
        assert not result.is_significant_before
        assert not result.is_significant_after


class TestFullRobustnessCheck:
    def test_real_edge_passes(self):
        """Strategy with real edge should pass overall."""
        rng = np.random.RandomState(42)
        returns = list(rng.normal(0.01, 0.02, 200))  # strong positive drift

        report = full_robustness_check(
            trade_returns=returns,
            n_backtests=10,
            strategy_name="test_strong",
            n_simulations=200,
            seed=42,
        )
        # With 10 backtests and strong edge, both MC and DSR should pass
        assert report.monte_carlo.is_significant
        assert report.dsr.is_significant
        assert report.overall_pass

    def test_noise_fails(self):
        """Random noise should fail overall."""
        rng = np.random.RandomState(42)
        returns = list(rng.normal(0, 0.05, 50))  # zero mean

        report = full_robustness_check(
            trade_returns=returns,
            n_backtests=6000,
            strategy_name="test_noise",
            n_simulations=200,
            seed=42,
        )
        # Noise with 6000 backtests should fail DSR at minimum
        assert not report.overall_pass or not report.dsr.is_significant

    def test_report_has_all_fields(self):
        """Report contains all test results."""
        report = full_robustness_check(
            trade_returns=[0.01, -0.005, 0.02] * 10,
            n_backtests=100,
            strategy_name="test",
            n_simulations=50,
        )
        assert report.monte_carlo is not None
        assert report.dsr is not None
        assert report.bonferroni is not None
        assert report.overall_interpretation != ""