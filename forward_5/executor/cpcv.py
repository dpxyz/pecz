"""
Combinatorial Purged Cross-Validation (CPCV)

Implements CPCV as described by López de Prado (2018).
Superior to Walk-Forward because:
1. Multiple backtest paths (not just one chronological split)
2. Purging removes label overlap between train/test
3. Embargo adds temporal buffer for serial correlation decay
4. Probability of Backtest Overfitting (PBO) computation

Reference: deep_research_foundry_v13_part2.txt (Section 3)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

log = logging.getLogger("cpcv")


@dataclass
class CPCVPath:
    """One train/test split in CPCV."""
    path_id: int
    train_indices: np.ndarray  # indices into the data
    test_indices: np.ndarray   # indices into the data
    purge_removed: int = 0     # how many samples were purged
    embargo_removed: int = 0   # how many samples embargoed


@dataclass
class CPCVResult:
    """Result of CPCV evaluation across all paths."""
    n_groups: int
    n_test_groups: int
    n_paths: int  # C(n_groups, n_test_groups)
    embargo_bars: int
    path_sharpes: list[float]  # Sharpe for each test path
    path_returns: list[float]  # cumulative return for each test path
    pbo: float  # Probability of Backtest Overfitting
    mean_sharpe: float
    std_sharpe: float
    all_paths_profitable: bool  # all test paths have positive return
    n_profitable: int  # number of profitable paths
    interpretation: str = ""


@dataclass
class CPCVConfig:
    """Configuration for CPCV."""
    n_groups: int = 6          # number of groups to split data into
    n_test_groups: int = 2     # groups held out for testing
    embargo_bars: int = 48     # 4h bars: 48 = 8 days embargo
    min_trades_per_path: int = 10  # minimum trades needed per test path


def split_into_groups(n_samples: int, n_groups: int) -> list[list[int]]:
    """Split data indices into n_groups contiguous groups.
    
    Each group contains approximately n_samples/n_groups indices.
    Groups are contiguous in time (preserving temporal order).
    """
    if n_groups > n_samples:
        n_groups = n_samples
    
    group_size = n_samples // n_groups
    remainder = n_samples % n_groups
    
    groups = []
    idx = 0
    for g in range(n_groups):
        size = group_size + (1 if g < remainder else 0)
        groups.append(list(range(idx, idx + size)))
        idx += size
    
    return groups


def generate_cpcv_paths(
    n_samples: int,
    config: CPCVConfig,
) -> list[CPCVPath]:
    """Generate all CPCV train/test splits.
    
    Splits data into n_groups contiguous groups, then generates
    C(n_groups, n_test_groups) paths by holding out each combination
    of n_test_groups groups.
    
    Purging: Remove train samples whose labels overlap with test labels.
    Embargo: Remove train samples within embargo_bars of test boundary.
    """
    from itertools import combinations
    
    groups = split_into_groups(n_samples, config.n_groups)
    
    # Generate all combinations of test groups
    test_combos = list(combinations(range(config.n_groups), config.n_test_groups))
    
    paths = []
    for path_id, test_group_ids in enumerate(test_combos):
        # Test indices = union of all test groups
        test_indices = []
        for g in test_group_ids:
            test_indices.extend(groups[g])
        
        # Train indices = everything NOT in test groups
        train_indices = []
        for g in range(config.n_groups):
            if g not in test_group_ids:
                train_indices.extend(groups[g])
        
        test_set = set(test_indices)
        train_set = set(train_indices)
        
        # Purging: Remove train samples whose index is adjacent to test boundaries
        # In time series, if test labels span [t1, t2], any train sample
        # whose label formation window overlaps [t1, t2] must be removed.
        # Simplified: remove train samples within 1 bar of test boundaries.
        purge_removed = 0
        purged_train = []
        for idx in train_indices:
            # Check if this index is adjacent to any test index
            is_adjacent = any(
                abs(idx - t_idx) <= 1 for t_idx in test_indices
            )
            if is_adjacent:
                purge_removed += 1
            else:
                purged_train.append(idx)
        
        # Embargo: Remove train samples within embargo_bars AFTER test set
        # This prevents serial correlation from leaking test info into train
        min_test_idx = min(test_indices)
        max_test_idx = max(test_indices)
        
        embargo_removed = 0
        final_train = []
        for idx in purged_train:
            # Remove if within embargo window after test set end
            if max_test_idx < idx <= max_test_idx + config.embargo_bars:
                embargo_removed += 1
            # Remove if within embargo window before test set start
            elif min_test_idx - config.embargo_bars <= idx < min_test_idx:
                embargo_removed += 1
            else:
                final_train.append(idx)
        
        paths.append(CPCVPath(
            path_id=path_id,
            train_indices=np.array(final_train, dtype=int),
            test_indices=np.array(test_indices, dtype=int),
            purge_removed=purge_removed,
            embargo_removed=embargo_removed,
        ))
    
    log.info(f"CPCV: {len(paths)} paths from {config.n_groups} groups, "
             f"{config.n_test_groups} test groups, {config.embargo_bars} bars embargo")
    return paths


def evaluate_cpcv(
    trade_returns: list[float],
    trade_timestamps: list,  # timestamps aligned with trade_returns
    config: CPCVConfig,
    annualization_factor: float = 2190,  # 4h bars: 6*365 = 2190
) -> CPCVResult:
    """Evaluate a strategy using CPCV.
    
    Takes a list of trade returns and their timestamps,
    splits into paths, and evaluates each path's OOS performance.
    
    Args:
        trade_returns: list of per-trade returns
        trade_timestamps: timestamps for each trade (for temporal ordering)
        config: CPCV configuration
        annualization_factor: for Sharpe annualization (2190 for 4h bars)
    
    Returns:
        CPCVResult with path-level statistics and PBO
    """
    from math import comb
    
    n_samples = len(trade_returns)
    n_paths = comb(config.n_groups, config.n_test_groups)
    
    if n_samples < 20:
        return CPCVResult(
            n_groups=config.n_groups, n_test_groups=config.n_test_groups,
            n_paths=n_paths, embargo_bars=config.embargo_bars,
            path_sharpes=[], path_returns=[], pbo=1.0,
            mean_sharpe=0, std_sharpe=0,
            all_paths_profitable=False, n_profitable=0,
            interpretation=f"Too few trades ({n_samples}) for CPCV"
        )
    
    paths = generate_cpcv_paths(n_samples, config)
    
    path_sharpes = []
    path_returns = []
    
    for path in paths:
        test_rets = [trade_returns[i] for i in path.test_indices if i < n_samples]
        
        if len(test_rets) < config.min_trades_per_path:
            continue
        
        test_arr = np.array(test_rets)
        cum_ret = float(np.prod(1 + test_arr) - 1)
        
        # Sharpe for this path
        if np.std(test_arr) > 0:
            sharpe = float(np.mean(test_arr) / np.std(test_arr)) * np.sqrt(annualization_factor)
        else:
            sharpe = 0.0
        
        path_sharpes.append(sharpe)
        path_returns.append(cum_ret)
    
    if not path_sharpes:
        return CPCVResult(
            n_groups=config.n_groups, n_test_groups=config.n_test_groups,
            n_paths=n_paths, embargo_bars=config.embargo_bars,
            path_sharpes=[], path_returns=[], pbo=1.0,
            mean_sharpe=0, std_sharpe=0,
            all_paths_profitable=False, n_profitable=0,
            interpretation="No valid paths (too few trades per path)"
        )
    
    # Probability of Backtest Overfitting (PBO)
    # PBO = fraction of paths where strategy loses money
    n_losing = sum(1 for r in path_returns if r <= 0)
    pbo = n_losing / len(path_returns)
    
    mean_sharpe = float(np.mean(path_sharpes))
    std_sharpe = float(np.std(path_sharpes))
    n_profitable = sum(1 for r in path_returns if r > 0)
    all_profitable = n_profitable == len(path_returns)
    
    if all_profitable:
        interp = f"✅ CPCV PASS: {n_profitable}/{len(path_returns)} paths profitable, PBO={pbo:.2%}, SR={mean_sharpe:.2f}±{std_sharpe:.2f}"
    else:
        interp = f"❌ CPCV FAIL: {n_profitable}/{len(path_returns)} paths profitable, PBO={pbo:.2%}, SR={mean_sharpe:.2f}±{std_sharpe:.2f}"
    
    return CPCVResult(
        n_groups=config.n_groups,
        n_test_groups=config.n_test_groups,
        n_paths=n_paths,
        embargo_bars=config.embargo_bars,
        path_sharpes=path_sharpes,
        path_returns=path_returns,
        pbo=pbo,
        mean_sharpe=mean_sharpe,
        std_sharpe=std_sharpe,
        all_paths_profitable=all_profitable,
        n_profitable=n_profitable,
        interpretation=interp,
    )


def evaluate_cpcv_equity(
    equity_curve: list[float],
    config: CPCVConfig,
) -> CPCVResult:
    """Evaluate using equity curve (period returns derived from equity).
    
    Args:
        equity_curve: equity at each period (e.g. 4h bar)
        config: CPCV configuration
    
    Returns:
        CPCVResult with path-level statistics
    """
    if len(equity_curve) < 20:
        return CPCVResult(
            n_groups=config.n_groups, n_test_groups=config.n_test_groups,
            n_paths=0, embargo_bars=config.embargo_bars,
            path_sharpes=[], path_returns=[], pbo=1.0,
            mean_sharpe=0, std_sharpe=0,
            all_paths_profitable=False, n_profitable=0,
            interpretation="Too few data points for CPCV"
        )
    
    # Convert equity curve to period returns
    eq = np.array(equity_curve)
    period_returns = eq[1:] / eq[:-1] - 1
    # Filter out NaN/Inf
    period_returns = np.nan_to_num(period_returns, nan=0.0, posinf=0.0, neginf=0.0)
    
    timestamps = list(range(len(period_returns)))
    
    paths = generate_cpcv_paths(len(period_returns), config)
    
    path_sharpes = []
    path_returns = []
    
    for path in paths:
        test_rets = period_returns[path.test_indices[path.test_indices < len(period_returns)]]
        
        if len(test_rets) < 5:
            continue
        
        cum_ret = float(np.prod(1 + test_rets) - 1)
        
        if np.std(test_rets) > 0:
            sharpe = float(np.mean(test_rets) / np.std(test_rets)) * np.sqrt(2190)
        else:
            sharpe = 0.0
        
        path_sharpes.append(sharpe)
        path_returns.append(cum_ret)
    
    if not path_sharpes:
        return CPCVResult(
            n_groups=config.n_groups, n_test_groups=config.n_test_groups,
            n_paths=len(paths), embargo_bars=config.embargo_bars,
            path_sharpes=[], path_returns=[], pbo=1.0,
            mean_sharpe=0, std_sharpe=0,
            all_paths_profitable=False, n_profitable=0,
            interpretation="No valid paths"
        )
    
    n_losing = sum(1 for r in path_returns if r <= 0)
    pbo = n_losing / len(path_returns)
    mean_sharpe = float(np.mean(path_sharpes))
    std_sharpe = float(np.std(path_sharpes))
    n_profitable = sum(1 for r in path_returns if r > 0)
    
    return CPCVResult(
        n_groups=config.n_groups,
        n_test_groups=config.n_test_groups,
        n_paths=len(paths),
        embargo_bars=config.embargo_bars,
        path_sharpes=path_sharpes,
        path_returns=path_returns,
        pbo=pbo,
        mean_sharpe=mean_sharpe,
        std_sharpe=std_sharpe,
        all_paths_profitable=n_profitable == len(path_returns),
        n_profitable=n_profitable,
    )