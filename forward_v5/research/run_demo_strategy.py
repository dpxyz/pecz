#!/usr/bin/env python3
"""
Demo: Strategy Research Workflow
Zeigt wie Backtest Engine, Parameter Sweep, Scorecards und KI Analyst zusammenarbeiten

Usage:
    python run_demo_strategy.py                    # Standard demo
    python run_demo_strategy.py --analyze          # Mit KI-Analyst (benötigt OLLAMA_API_KEY)
    python run_demo_strategy.py --strategy mean_reversion_panic --analyze
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backtest'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'strategy_lab'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scorecards'))

from backtest_engine import BacktestEngine, BacktestResult
from parameter_sweep import quick_sweep
from scorecard_generator import ScorecardGenerator

# Strategien importieren
import trend_pullback
import mean_reversion_panic
import multi_asset_selector

# Analyst optional importieren
try:
    from analyst import KIAnalyst, check_analyst_availability
    ANALYST_AVAILABLE = True
except ImportError:
    ANALYST_AVAILABLE = False


STRATEGIES = {
    'trend_pullback': {
        'module': trend_pullback,
        'desc': 'EMA-Trend + RSI Pullback',
        'hypothesis': 'Trend + Pullback = Continuation. EMA above + RSI oversold = entry'
    },
    'mean_reversion_panic': {
        'module': mean_reversion_panic,
        'desc': 'Z-Score Panic Recovery',
        'hypothesis': 'Panic moves revert to mean. Z-score extreme = entry'
    },
    'multi_asset_selector': {
        'module': multi_asset_selector,
        'desc': 'Momentum Ranking',
        'hypothesis': 'Relative strength persists. Top momentum outperforms'
    }
}


def demo_single_backtest(strategy_name='trend_pullback'):
    """Demo: Einzelner Backtest"""
    print("=" * 60)
    print(f"Demo: Single Backtest ({strategy_name})")
    print("=" * 60)
    
    strategy = STRATEGIES[strategy_name]
    data_path = os.path.join(os.path.dirname(__file__), 'data')
    
    if not os.path.exists(data_path):
        print(f"⚠️  Data directory not found: {data_path}")
        print("    Run: python generate_dummy_data.py")
        return None
    
    engine = BacktestEngine(data_path)
    params = strategy['module'].get_default_params()
    
    print(f"Strategy: {strategy_name}")
    print(f"Desc: {strategy['desc']}")
    print(f"Params: {params}")
    print("-" * 60)
    
    try:
        result = engine.run(strategy_name, strategy['module'].strategy_func, params, "BTCUSDT")
        
        print(f"Result:")
        print(f"  Trades: {result.trade_count}")
        print(f"  Net Return: {result.net_return:.2f}%")
        print(f"  Max Drawdown: {result.max_drawdown:.2f}%")
        print(f"  Win Rate: {result.win_rate:.1f}%")
        print(f"  Execution: {result.execution_time_ms}ms")
        print(f"  Memory: {result.memory_peak_mb:.2f}MB")
        
        if result.failure_reasons:
            print(f"  ⚠️  Failures: {result.failure_reasons}")
        
        return result
        
    except FileNotFoundError as e:
        print(f"⚠️  {e}")
        print(f"    Generate dummy data via generate_dummy_data.py")
        return None


def demo_parameter_sweep(strategy_name='trend_pullback'):
    """Demo: Parameter Sweep"""
    print("\n" + "=" * 60)
    print(f"Demo: Parameter Sweep ({strategy_name})")
    print("=" * 60)
    
    strategy = STRATEGIES[strategy_name]
    data_path = os.path.join(os.path.dirname(__file__), 'data')
    
    if not os.path.exists(data_path):
        print(f"⚠️  Data directory not found: {data_path}")
        return None
    
    engine = BacktestEngine(data_path)
    grid = strategy['module'].get_vps_safe_param_grid()
    
    # Zähle Kombinationen
    import itertools
    n_combos = 1
    for v in grid.values():
        n_combos *= len(v)
    
    print(f"Strategy: {strategy_name}")
    print(f"Grid: {n_combos} combinations (VPS-Safe)")
    print("-" * 60)
    
    try:
        result = quick_sweep(
            engine,
            strategy_name,
            strategy['module'].strategy_func,
            grid,
            symbol="BTCUSDT"
        )
        
        print(f"\n✓ Sweep Complete:")
        print(f"  Total: {result.total_combinations}")
        print(f"  Completed: {result.completed}")
        print(f"  Failed: {result.failed}")
        print(f"  Time: {result.execution_time_ms}ms")
        
        print(f"\n🏆 Best Result:")
        best = result.best_result
        print(f"  Params: {best.get('params', {})}")
        print(f"  Return: {best.get('net_return', 0):.2f}%")
        print(f"  Drawdown: {best.get('max_drawdown', 0):.2f}%")
        print(f"  Trades: {best.get('trade_count', 0)}")
        
        return result
        
    except FileNotFoundError as e:
        print(f"⚠️  {e}")
        return None


def demo_scorecard(strategy_name='trend_pullback', sweep_result=None):
    """Demo: Scorecard Generation"""
    print("\n" + "=" * 60)
    print("Demo: Scorecard Generation")
    print("=" * 60)
    
    strategy = STRATEGIES[strategy_name]
    gen = ScorecardGenerator()
    
    # Daten aus Sweep oder Dummy
    if sweep_result is None:
        backtest_data = {
            'net_return': 12.5,
            'max_drawdown': -6.2,
            'profit_factor': 1.3,
            'win_rate': 51.2,
            'expectancy': 0.45,
            'trade_count': 38,
            'resource_usage': {'execution_time_ms': 4500, 'memory_peak_mb': 128.5}
        }
        params = strategy['module'].get_default_params()
        wf_data = {'n_windows': 3, 'robustness_score': 75, 'passed': True}
    else:
        best = sweep_result.best_result
        backtest_data = {
            'net_return': best.get('net_return', 0),
            'max_drawdown': best.get('max_drawdown', 0),
            'profit_factor': best.get('profit_factor', 0),
            'win_rate': best.get('win_rate', 0),
            'expectancy': best.get('expectancy', 0),
            'trade_count': best.get('trade_count', 0),
            'resource_usage': {'execution_time_ms': sweep_result.execution_time_ms, 'memory_peak_mb': 128.0}
        }
        params = best.get('params', {})
        wf_data = {'n_windows': 3, 'robustness_score': 75, 'passed': True}
    
    scorecard = gen.create(
        strategy_name=strategy_name,
        hypothesis=strategy['hypothesis'],
        dataset={'symbol': 'BTCUSDT', 'timeframe': '1h', 'date_range': '2024-01-01 to 2024-12-31', 'n_bars': 8760},
        parameters=params,
        backtest_results=backtest_data,
        walk_forward=wf_data
    )
    
    print(gen.summary(scorecard))
    print(f"\nVerdict: {scorecard['verdict']}")
    print(f"Next Actions: {scorecard['next_actions']}")
    
    filepath = gen.save(scorecard, f"scorecard_{strategy_name}.json")
    print(f"\nSaved: {filepath}")
    
    return scorecard, filepath


def demo_analyst(scorecard_path):
    """Demo: KI Analyst Analyse"""
    if not ANALYST_AVAILABLE:
        print("\n⚠️  Analyst module not available")
        return
    
    print("\n" + "=" * 60)
    print("Demo: KI Meta-Analyst")
    print("=" * 60)
    
    if not check_analyst_availability():
        print("⚠️  OLLAMA_API_KEY not set")
        print("    export OLLAMA_API_KEY='your-key'")
        return
    
    # Lade Scorecard
    import json
    with open(scorecard_path, 'r') as f:
        scorecard = json.load(f)
    
    print(f"Scorecard: {os.path.basename(scorecard_path)}")
    print(f"Strategy: {scorecard.get('strategy_name', 'unknown')}")
    print(f"Verdict: {scorecard.get('verdict', 'unknown')}")
    print("-" * 60)
    print("Analyzing with Kimi 2.5... (timeout: 30s)")
    print("-" * 60)
    
    analyst = KIAnalyst()
    report = analyst.analyze_scorecard(scorecard)
    
    print(report.summary())
    
    # Speichern
    report_path = scorecard_path.replace('.json', '_analyst_report.json')
    report.save(report_path)
    print(f"\n✓ Report saved: {report_path}")


def main():
    parser = argparse.ArgumentParser(description='Phase 7 Strategy Research')
    parser.add_argument('--strategy', choices=list(STRATEGIES.keys()), default='trend_pullback',
                        help='Strategy to test')
    parser.add_argument('--analyze', action='store_true',
                        help='Run KI analyst after scorecard generation (needs OLLAMA_API_KEY)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Use dummy data (no data files needed)')
    
    args = parser.parse_args()
    
    print("\n" + "╔" + "=" * 58 + "╗")
    print("║" + "  Phase 7: Strategy Lab — Research Workflow".center(58) + "║")
    print("╚" + "=" * 58 + "╝")
    
    print(f"\nSelected Strategy: {args.strategy}")
    print(f"Description: {STRATEGIES[args.strategy]['desc']}")
    
    if args.analyze:
        if check_analyst_availability():
            print("KI Analyst: ✓ Available (Kimi 2.5)")
        else:
            print("KI Analyst: ✗ Not configured (set OLLAMA_API_KEY)")
            print("Continuing without analysis...")
    
    # Workflow
    sweep_result = None
    
    if not args.dry_run:
        # Versuche echte Daten
        sweep_result = demo_parameter_sweep(args.strategy)
    
    # Scorecard (mit echten oder Dummy-Daten)
    scorecard, scorecard_path = demo_scorecard(args.strategy, sweep_result)
    
    # Optional: KI Analyse
    if args.analyze and check_analyst_availability():
        demo_analyst(scorecard_path)
    
    # Summary
    print("\n" + "=" * 60)
    print("Workflow Complete!")
    print("=" * 60)
    print(f"\nArtifacts:")
    print(f"  📄 Scorecard: {scorecard_path}")
    if args.analyze and check_analyst_availability():
        print(f"  🧠 Analyst Report: {scorecard_path.replace('.json', '_analyst_report.json')}")
    
    print(f"\nVerdict: {scorecard['verdict']}")
    if scorecard['verdict'] == 'PASS':
        print("\n✅ Strategy PASSED — Consider integration")
    elif scorecard['verdict'] == 'INCONCLUSIVE':
        print("\n⏳ Strategy INCONCLUSIVE — More data needed")
    else:
        print("\n❌ Strategy FAILED — Revise hypothesis")


if __name__ == "__main__":
    main()
