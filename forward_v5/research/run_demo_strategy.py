#!/usr/bin/env python3
"""
Demo: Strategy Research Workflow
Zeigt wie Backtest Engine, Parameter Sweep und Scorecards zusammenarbeiten
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backtest'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'strategy_lab'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scorecards'))

from backtest_engine import BacktestEngine, BacktestResult
from parameter_sweep import quick_sweep
from scorecard_generator import ScorecardGenerator
import trend_pullback
import mean_reversion_panic


def demo_single_backtest():
    """Demo: Einzelner Backtest"""
    print("=" * 60)
    print("Demo: Single Backtest")
    print("=" * 60)
    
    # Engine initialisieren
    data_path = os.path.join(os.path.dirname(__file__), 'data')
    
    if not os.path.exists(data_path):
        print(f"⚠️  Data directory not found: {data_path}")
        print("    Create research/data/ with OHLCV Parquet files")
        return
    
    engine = BacktestEngine(data_path)
    
    # Strategie-Parameter
    params = trend_pullback.get_default_params()
    
    print(f"Strategy: trend_pullback")
    print(f"Params: {params}")
    print(f"Data: {data_path}")
    print("-" * 60)
    
    try:
        result = engine.run("trend_pullback", trend_pullback.trend_pullback_strategy, params, "BTCUSDT")
        
        print(f"Result:")
        print(f"  Trades: {result.trade_count}")
        print(f"  Net Return: {result.net_return:.2f}%")
        print(f"  Max Drawdown: {result.max_drawdown:.2f}%")
        print(f"  Win Rate: {result.win_rate:.1f}%")
        print(f"  Execution Time: {result.execution_time_ms}ms")
        print(f"  Memory Peak: {result.memory_peak_mb:.2f}MB")
        
        if result.failure_reasons:
            print(f"  ⚠️  Failures: {result.failure_reasons}")
        
    except FileNotFoundError as e:
        print(f"⚠️  {e}")
        print("    Place BTCUSDT_1h.parquet in research/data/")


def demo_parameter_sweep():
    """Demo: Parameter Sweep"""
    print("\n" + "=" * 60)
    print("Demo: Parameter Sweep (max 50 combinations)")
    print("=" * 60)
    
    data_path = os.path.join(os.path.dirname(__file__), 'data')
    
    if not os.path.exists(data_path):
        print(f"⚠️  Data directory not found: {data_path}")
        return
    
    engine = BacktestEngine(data_path)
    
    # VPS-Safe Grid
    grid = trend_pullback.get_vps_safe_param_grid()
    
    print(f"Strategy: trend_pullback")
    print(f"Grid: {grid}")
    print(f"Max combinations: 9 (VPS-Safe)")
    print("-" * 60)
    
    try:
        result = quick_sweep(
            engine,
            "trend_pullback",
            trend_pullback.trend_pullback_strategy,
            grid,
            symbol="BTCUSDT"
        )
        
        print(f"\nSweep Complete:")
        print(f"  Total: {result.total_combinations}")
        print(f"  Completed: {result.completed}")
        print(f"  Failed: {result.failed}")
        print(f"  Time: {result.execution_time_ms}ms")
        
        print(f"\nBest Result:")
        best = result.best_result
        print(f"  Params: {best.get('params', {})}")
        print(f"  Return: {best.get('net_return', 0):.2f}%")
        print(f"  Drawdown: {best.get('max_drawdown', 0):.2f}%")
        print(f"  Trades: {best.get('trade_count', 0)}")
        
        return result
        
    except FileNotFoundError as e:
        print(f"⚠️  {e}")
        return None


def demo_scorecard(result=None):
    """Demo: Scorecard Generation"""
    print("\n" + "=" * 60)
    print("Demo: Scorecard Generation")
    print("=" * 60)
    
    gen = ScorecardGenerator()
    
    # Dummy-Daten wenn kein Result übergeben
    if result is None:
        backtest_data = {
            'net_return': 12.5,
            'max_drawdown': -6.2,
            'profit_factor': 1.3,
            'win_rate': 51.2,
            'expectancy': 0.45,
            'trade_count': 38,
            'resource_usage': {
                'execution_time_ms': 4500,
                'memory_peak_mb': 128.5
            }
        }
        params = {'ema_period': 20, 'rsi_period': 14}
        wf_data = {
            'n_windows': 3,
            'robustness_score': 75,
            'passed': True
        }
    else:
        backtest_data = {
            'net_return': result.best_result.get('net_return', 0),
            'max_drawdown': result.best_result.get('max_drawdown', 0),
            'profit_factor': result.best_result.get('profit_factor', 0),
            'win_rate': result.best_result.get('win_rate', 0),
            'expectancy': result.best_result.get('expectancy', 0),
            'trade_count': result.best_result.get('trade_count', 0),
            'resource_usage': {
                'execution_time_ms': result.execution_time_ms,
                'memory_peak_mb': 128.0  # Dummy
            }
        }
        params = result.best_result.get('params', {})
        wf_data = {
            'n_windows': 3,
            'robustness_score': 75,
            'passed': True
        }
    
    scorecard = gen.create(
        strategy_name="trend_pullback",
        hypothesis="Trend + Pullback = Continuation. EMA above + RSI oversold = entry",
        dataset={
            'symbol': 'BTCUSDT',
            'timeframe': '1h',
            'date_range': '2024-01-01 to 2024-12-31',
            'n_bars': 8760
        },
        parameters=params,
        backtest_results=backtest_data,
        walk_forward=wf_data
    )
    
    print(gen.summary(scorecard))
    print(f"\nVerdict: {scorecard['verdict']}")
    print(f"Next Actions: {scorecard['next_actions']}")
    
    # Speichern
    filepath = gen.save(scorecard, "demo_scorecard_trend_pullback.json")
    print(f"\nSaved: {filepath}")


def demo_strategies_list():
    """Auflistung aller verfügbaren Strategien"""
    print("\n" + "=" * 60)
    print("Available Strategies (Phase 7)")
    print("=" * 60)
    
    strategies = [
        ('trend_pullback', 'EMA-Trend + RSI Pullback', trend_pullback.get_vps_safe_param_grid()),
        ('mean_reversion_panic', 'Z-Score Panic Recovery', mean_reversion_panic.get_vps_safe_param_grid()),
        ('multi_asset_selector', 'Momentum Ranking', {'momentum_period': [10, 20, 30], 'n_top': [2]}),
    ]
    
    for name, desc, grid in strategies:
        import itertools
        n_combos = 1
        for v in grid.values():
            n_combos *= len(v)
        
        print(f"\n📊 {name}")
        print(f"   {desc}")
        print(f"   Grid: {n_combos} combinations (VPS-Safe)")
    
    print("\n🔧 Filter Modules (for composition):")
    print("   - rsi_regime_filter.py")
    print("   - volatility_filter.py")


if __name__ == "__main__":
    print("\n" + "╔" + "=" * 58 + "╗")
    print("║" + "  Phase 7: Strategy Lab — Research Workflow Demo".center(58) + "║")
    print("╚" + "=" * 58 + "╝")
    
    # Liste
    demo_strategies_list()
    
    # Demo 1: Single Backtest
    demo_single_backtest()
    
    # Demo 2: Parameter Sweep
    sweep_result = demo_parameter_sweep()
    
    # Demo 3: Scorecard
    demo_scorecard(sweep_result)
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Add OHLCV data to research/data/")
    print("  2. Run: python run_demo_strategy.py")
    print("  3. Check scorecards/ for results")
    print("  4. Integrate best strategy into forward_v5")
