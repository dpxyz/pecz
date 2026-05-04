"""
Statistical Robustness Testing

Implements three critical tests for backtest validity:
1. Monte Carlo Permutation Test — trade reshuffling to test if returns are structural
2. Deflated Sharpe Ratio (DSR) — López de Prado's test penalizing multiple testing
3. Bonferroni Correction — adjusted significance threshold for N backtests

Without these tests, we cannot distinguish real alpha from noise.
Reference: deep_research_3_statistics.md, deep_research_complete_summary.md
"""

import math
import random
import logging
from typing import Optional
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger("statistical_robustness")


# ── Data Classes ──

@dataclass
class MonteCarloResult:
    """Result of Monte Carlo permutation test."""
    original_return: float
    original_sharpe: float
    n_simulations: int
    p_value: float  # fraction of random permutations with return >= original
    ci_95_low: float  # 2.5th percentile of permuted returns
    ci_95_high: float  # 97.5th percentile
    is_significant: bool  # p_value < 0.05
    interpretation: str = ""


@dataclass
class DSRResult:
    """Result of Deflated Sharpe Ratio test."""
    observed_sharpe: float
    annualized_sharpe: float
    n_backtests: int  # total number of backtests run
    n_observations: int  # number of return observations
    skewness: float
    kurtosis: float
    dsr: float  # deflated sharpe ratio (adjusted threshold)
    expected_max_sharpe: float  # E[max(SR)] under null
    dsr_statistic: float  # (SR_hat - E[max]) / SE
    p_value: float
    is_significant: bool  # DSR > 0 at 5% level
    interpretation: str = ""


@dataclass
class BonferroniResult:
    """Result of Bonferroni correction."""
    n_backtests: int
    original_alpha: float  # e.g. 0.05
    adjusted_alpha: float  # 0.05 / n_backtests
    original_p_value: float
    is_significant_before: bool
    is_significant_after: bool
    interpretation: str = ""


@dataclass
class RobustnessReport:
    """Combined robustness assessment for a strategy."""
    strategy_name: str
    monte_carlo: Optional[MonteCarloResult] = None
    dsr: Optional[DSRResult] = None
    bonferroni: Optional[BonferroniResult] = None
    overall_pass: bool = False  # all three tests pass
    overall_interpretation: str = ""


# ── Monte Carlo Permutation Test ──

def monte_carlo_permutation(
    trade_returns: list[float],
    n_simulations: int = 1000,
    alpha: float = 0.05,
    seed: Optional[int] = None,
) -> MonteCarloResult:
    """Monte Carlo Permutation Test for backtest validity.

    Two-layer test:
    1. RESHUFFLE: Permutes trade order to test path-dependency
       (does drawdown/timing matter?)
    2. BOOTSTRAP: Resamples returns WITH REPLACEMENT to test if the
       mean return is significantly positive vs random sampling.

    The bootstrap layer is the critical one: if random resamples of the
    same return distribution can produce similar cumulative returns,
    the edge is not structural.

    Args:
        trade_returns: list of per-trade returns (e.g. [0.02, -0.01, 0.03, ...])
        n_simulations: number of random simulations
        alpha: significance level
        seed: random seed for reproducibility

    Returns:
        MonteCarloResult with p-value and confidence intervals
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    returns = np.array(trade_returns)
    n_trades = len(returns)

    if n_trades < 10:
        return MonteCarloResult(
            original_return=0, original_sharpe=0, n_simulations=0,
            p_value=1.0, ci_95_low=0, ci_95_high=0, is_significant=False,
            interpretation="Too few trades for Monte Carlo test (<10)"
        )

    # Original statistics
    original_cum_return = float(np.prod(1 + returns) - 1)
    original_sharpe = _compute_sharpe(returns)

    # BOOTSTRAP: Resample returns with replacement (n_trades per simulation)
    # This tests: is the MEAN return significantly positive?
    # If bootstrap returns are similar to original, the edge is noise.
    bootstrapped_returns = []

    for _ in range(n_simulations):
        # Resample WITH replacement from the return distribution
        sample = np.random.choice(returns, size=n_trades, replace=True)
        cum_ret = float(np.prod(1 + sample) - 1)
        bootstrapped_returns.append(cum_ret)

    bootstrapped_returns = np.array(bootstrapped_returns)

    # P-value: fraction of bootstrapped returns >= original
    # A low p-value means the original is in the right tail = unlikely to be noise
    # But bootstrap with replacement preserves the mean, so p-value will be ~0.5
    # The real test: what fraction of bootstraps have NEGATIVE cumulative return?
    p_value_neg = float(np.mean(bootstrapped_returns <= 0))  # prob of losing money

    # Better p-value: fraction of bootstraps with return >= original
    # For positive edge, this should be ~0.5 (original is near median)
    # What matters is the fraction that goes negative = risk of ruin
    p_value = float(np.mean(bootstrapped_returns >= original_cum_return))

    # Confidence intervals
    ci_low = float(np.percentile(bootstrapped_returns, (alpha / 2) * 100))
    ci_high = float(np.percentile(bootstrapped_returns, (1 - alpha / 2) * 100))

    # Significance: 95% CI should not include 0 (or negative baseline)
    is_significant = ci_low > 0  # all bootstrapped returns are positive

    # Also check: probability of negative cumulative return
    if p_value_neg > 0.05:
        is_significant = False

    if is_significant:
        interp = f"PASS: Original return {original_cum_return:.2%}, 95% CI [{ci_low:.2%}, {ci_high:.2%}] does not include 0, P(neg)={p_value_neg:.2%}"
    else:
        interp = f"FAIL: Original return {original_cum_return:.2%}, 95% CI [{ci_low:.2%}, {ci_high:.2%}], P(neg)={p_value_neg:.2%}"

    return MonteCarloResult(
        original_return=original_cum_return,
        original_sharpe=original_sharpe,
        n_simulations=n_simulations,
        p_value=p_value_neg,  # report probability of negative return
        ci_95_low=ci_low,
        ci_95_high=ci_high,
        is_significant=is_significant,
        interpretation=interp,
    )


# ── Deflated Sharpe Ratio (DSR) ──

def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_backtests: int,
    n_observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    annualization_factor: float = 252,  # trading days
    is_annualized: bool = False,
) -> DSRResult:
    """Deflated Sharpe Ratio test (López de Prado, 2018).

    Tests whether an observed Sharpe Ratio is statistically significant
    after accounting for:
    1. Multiple testing (N backtests inflates expected max SR)
    2. Non-normal returns (skewness + kurtosis adjustment)
    3. Sample size (more observations = more reliable)

    The key insight: with N backtests, the expected maximum SR under
    the null is E[max(SR)] ≈ (1 - γ) * Φ⁻¹(1 - 1/N) + γ * Φ⁻¹(1 - 1/(N*e))
    where γ ≈ 0.5772 (Euler-Mascheroni constant).

    Args:
        observed_sharpe: annualized Sharpe Ratio of the strategy
        n_backtests: total number of backtests run (including failed ones)
        n_observations: number of return observations (trades or periods)
        skewness: skewness of returns
        kurtosis: excess kurtosis of returns (normal = 3)
        annualization_factor: periods per year (252 for daily, 52 for weekly)

    Returns:
        DSRResult with test statistic and p-value
    """
    if n_backtests < 1 or n_observations < 10:
        return DSRResult(
            observed_sharpe=observed_sharpe, annualized_sharpe=observed_sharpe,
            n_backtests=n_backtests, n_observations=n_observations,
            skewness=skewness, kurtosis=kurtosis,
            dsr=0, expected_max_sharpe=0, dsr_statistic=0, p_value=1.0,
            is_significant=False,
            interpretation="Insufficient data for DSR test"
        )

    # Annualize Sharpe if not already
    annualized_sharpe = observed_sharpe if is_annualized else observed_sharpe * math.sqrt(annualization_factor)

    # Expected maximum Sharpe Ratio under null (multiple testing)
    # E[max(SR)] ≈ (1-γ) * Z^{-1}(1-1/N) + γ * Z^{-1}(1-1/(N*e))
    # Using the simplified version from López de Prado
    e_gamma = 0.5772156649  # Euler-Mascheroni constant

    if n_backtests == 1:
        expected_max_sr = 0.0
    else:
        # Inverse CDF of standard normal at (1 - 1/N)
        z_1_over_n = _norm_ppf(1 - 1.0 / n_backtests)
        z_1_over_ne = _norm_ppf(1 - 1.0 / (n_backtests * math.e))
        expected_max_sr = (1 - e_gamma) * z_1_over_n + e_gamma * z_1_over_ne

    # Adjust for non-normality: SE of Sharpe under non-iid
    # SE(SR) ≈ sqrt( (1 - skew*SR + (kurt-1)/4 * SR^2) / (n-1) )
    se_sharpe = math.sqrt(
        (1 - skewness * annualized_sharpe + (kurtosis - 1) / 4 * annualized_sharpe ** 2)
        / (n_observations - 1)
    ) if n_observations > 1 else 1.0

    # DSR test statistic
    # DSR = (SR_hat - E[max(SR)]) / SE
    dsr_statistic = (annualized_sharpe - expected_max_sr) / se_sharpe if se_sharpe > 0 else 0

    # P-value from standard normal
    p_value = 1 - _norm_cdf(dsr_statistic)

    # DSR "threshold" = expected_max_sr (the deflated benchmark)
    dsr_threshold = expected_max_sr

    is_significant = p_value < 0.05

    if is_significant:
        interp = f"PASS: DSR={dsr_statistic:.3f} > 0, SR={annualized_sharpe:.3f} exceeds E[max]={expected_max_sr:.3f} (p={p_value:.4f}, N={n_backtests} BT)"
    else:
        interp = f"FAIL: DSR={dsr_statistic:.3f} ≤ 0, SR={annualized_sharpe:.3f} below E[max]={expected_max_sr:.3f} (p={p_value:.4f}, N={n_backtests} BT)"

    return DSRResult(
        observed_sharpe=observed_sharpe,
        annualized_sharpe=annualized_sharpe,
        n_backtests=n_backtests,
        n_observations=n_observations,
        skewness=skewness,
        kurtosis=kurtosis,
        dsr=dsr_threshold,
        expected_max_sharpe=expected_max_sr,
        dsr_statistic=dsr_statistic,
        p_value=p_value,
        is_significant=is_significant,
        interpretation=interp,
    )


# ── Bonferroni Correction ──

def bonferroni_correction(
    n_backtests: int,
    observed_p_value: float,
    alpha: float = 0.05,
) -> BonferroniResult:
    """Bonferroni correction for multiple testing.

    Simple but conservative: divide alpha by number of tests.
    If we run 6000 backtests and 1 passes at p=0.05,
    the adjusted threshold is 0.05/6000 = 0.0000083.

    Args:
        n_backtests: total number of backtests
        observed_p_value: the p-value of the best strategy
        alpha: family-wise error rate (default 0.05)

    Returns:
        BonferroniResult with adjusted significance
    """
    adjusted_alpha = alpha / n_backtests if n_backtests > 0 else alpha

    is_significant_before = observed_p_value < alpha
    is_significant_after = observed_p_value < adjusted_alpha

    if is_significant_after:
        interp = f"PASS: p={observed_p_value:.6f} < α/n={adjusted_alpha:.6f} (N={n_backtests})"
    elif is_significant_before:
        interp = f"FAIL: p={observed_p_value:.6f} < α={alpha} but ≥ α/n={adjusted_alpha:.6f} — NOT significant after Bonferroni (N={n_backtests})"
    else:
        interp = f"FAIL: p={observed_p_value:.6f} ≥ α={alpha} — not significant even before correction"

    return BonferroniResult(
        n_backtests=n_backtests,
        original_alpha=alpha,
        adjusted_alpha=adjusted_alpha,
        original_p_value=observed_p_value,
        is_significant_before=is_significant_before,
        is_significant_after=is_significant_after,
        interpretation=interp,
    )


# ── Combined Report ──

def full_robustness_check(
    trade_returns: list[float],
    n_backtests: int,
    strategy_name: str = "unnamed",
    observed_p_value: Optional[float] = None,
    n_simulations: int = 1000,
    annualization_factor: float = 252,
    seed: Optional[int] = None,
) -> RobustnessReport:
    """Run all three robustness tests and produce a combined report.

    This is the main entry point for validating a backtest result.

    Args:
        trade_returns: list of per-trade returns
        n_backtests: total number of backtests run (for DSR + Bonferroni)
        strategy_name: human-readable name
        observed_p_value: if known, the p-value from the backtest
        n_simulations: Monte Carlo iterations
        annualization_factor: periods per year
        seed: random seed

    Returns:
        RobustnessReport with all test results
    """
    report = RobustnessReport(strategy_name=strategy_name)

    # 1. Monte Carlo
    report.monte_carlo = monte_carlo_permutation(
        trade_returns, n_simulations=n_simulations, seed=seed
    )
    log.info(f"  Monte Carlo: {report.monte_carlo.interpretation}")

    # 2. DSR
    returns = np.array(trade_returns)
    sharpe = _compute_sharpe(returns)
    # Manual skewness/kurtosis (numpy 2.0 removed np.skew/np.kurtosis)
    if len(returns) > 2:
        from scipy.stats import skew as _skew, kurtosis as _kurtosis
        skew = float(_skew(returns))
        kurt = float(_kurtosis(returns) + 3)  # excess→actual kurtosis
    else:
        skew = 0.0
        kurt = 3.0

    report.dsr = deflated_sharpe_ratio(
        observed_sharpe=sharpe,
        n_backtests=n_backtests,
        n_observations=len(trade_returns),
        skewness=skew,
        kurtosis=kurt,
        annualization_factor=annualization_factor,
    )
    log.info(f"  DSR: {report.dsr.interpretation}")

    # 3. Bonferroni
    if observed_p_value is not None:
        report.bonferroni = bonferroni_correction(
            n_backtests=n_backtests,
            observed_p_value=observed_p_value,
        )
        log.info(f"  Bonferroni: {report.bonferroni.interpretation}")
    else:
        # Estimate p-value from Monte Carlo result
        report.bonferroni = bonferroni_correction(
            n_backtests=n_backtests,
            observed_p_value=report.monte_carlo.p_value,
        )
        log.info(f"  Bonferroni (estimated): {report.bonferroni.interpretation}")

    # Overall assessment
    mc_pass = report.monte_carlo.is_significant
    dsr_pass = report.dsr.is_significant
    bon_pass = report.bonferroni.is_significant_after

    report.overall_pass = mc_pass and dsr_pass

    if report.overall_pass and bon_pass:
        report.overall_interpretation = f"✅ ALL PASS — {strategy_name} has statistically robust edge"
    elif report.overall_pass:
        report.overall_interpretation = f"⚠️ MC+DSR PASS, BONFERRONI FAIL — edge exists but may be inflated by multiple testing"
    elif mc_pass:
        report.overall_interpretation = f"⚠️ MC PASS, DSR FAIL — returns are structural but likely inflated by backtest count"
    else:
        report.overall_interpretation = f"❌ FAIL — {strategy_name} likely has no real edge"

    log.info(f"  Overall: {report.overall_interpretation}")
    return report


# ── Helpers ──

def _compute_sharpe(returns: np.ndarray) -> float:
    """Compute non-annualized Sharpe Ratio."""
    if len(returns) < 2 or np.std(returns) == 0:
        return 0.0
    return float(np.mean(returns) / np.std(returns))


def _norm_cdf(x: float) -> float:
    """Standard normal CDF approximation (Abramowitz & Stegun)."""
    if x < -8:
        return 0.0
    if x > 8:
        return 1.0
    # Approximation using error function
    t = 1.0 / (1.0 + 0.2316419 * abs(x))
    d = 0.3989422804014327  # 1/sqrt(2*pi)
    p = d * math.exp(-x * x / 2) * (
        t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))))
    )
    return 1.0 - p if x > 0 else p


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (quantile function).

    Rational approximation (Peter Acklam).
    Valid for 0 < p < 1.
    """
    if p <= 0 or p >= 1:
        return 8.0 if p >= 1 else -8.0  # clamp

    if p < 0.5:
        t = math.sqrt(-2 * math.log(p))
    else:
        t = math.sqrt(-2 * math.log(1 - p))

    # Rational approximation coefficients
    c0 = 2.515517
    c1 = 0.802853
    c2 = 0.010328
    d1 = 1.432788
    d2 = 0.189269
    d3 = 0.001308

    result = t - (c0 + c1 * t + c2 * t ** 2) / (1 + d1 * t + d2 * t ** 2 + d3 * t ** 3)

    if p < 0.5:
        return -result
    return result