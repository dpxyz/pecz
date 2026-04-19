#!/usr/bin/env python3
"""
Parameter Sweep V1 - VPS-Safe Design
- Max 50 Kombinationen (hartes Limit)
- Sequentielle Ausführung (kein Parallel-RAM-Overhead)
- Chunked Parameter-Expansion (kein kartesisches Produkt-Explosion)
- Lazy Result-Tracking
"""

import itertools
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Callable
from dataclasses import dataclass, asdict

from backtest.backtest_engine import BacktestEngine, BacktestResult


@dataclass
class SweepResult:
    """Ergebnis eines Parameter Sweeps"""
    strategy_name: str
    symbol: str
    timeframe: str
    total_combinations: int
    completed: int
    failed: int
    best_result: Dict[str, Any]
    all_results: List[Dict]
    execution_time_ms: int = 0
    
    def to_dict(self) -> Dict:
        return {
            'strategy_name': self.strategy_name,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'total_combinations': self.total_combinations,
            'completed': self.completed,
            'failed': self.failed,
            'best_result': self.best_result,
            'execution_time_ms': self.execution_time_ms
        }


class ParameterSweep:
    """
    VPS-sicherer Parameter Sweep
    
    Regeln:
    - MAX_COMBINATIONS = 50 (hart)
    - Sequentielle Ausführung
    - Speichert nur Top-10 Details (RAM sparen)
    """
    
    MAX_COMBINATIONS = 50
    TOP_RESULTS_TO_KEEP = 10
    
    def __init__(
        self,
        engine: BacktestEngine,
        strategy_name: str,
        strategy_func: Callable,
        param_grid: Dict[str, List[Any]],
        symbol: str = "BTCUSDT",
        timeframe: str = "1h"
    ):
        self.engine = engine
        self.strategy_name = strategy_name
        self.strategy_func = strategy_func
        self.param_grid = param_grid
        self.symbol = symbol
        self.timeframe = timeframe
        
        # Validierung
        self._validate_grid()
    
    def _validate_grid(self):
        """Prüfe Limits vor Start"""
        combinations = 1
        for values in self.param_grid.values():
            combinations *= len(values)
        
        if combinations > self.MAX_COMBINATIONS:
            raise ValueError(
                f"Parameter grid too large: {combinations} combinations "
                f"(max {self.MAX_COMBINATIONS}). "
                f"Reduce parameters or ranges."
            )
    
    def run(self, metric: str = "net_return") -> SweepResult:
        """
        Führe Sweep aus
        
        Args:
            metric: Sortierungsmetrik ('net_return', 'profit_factor', 'win_rate', etc.)
        """
        start_time = time.time()
        
        # Generiere Kombinationen
        keys = list(self.param_grid.keys())
        values = [self.param_grid[k] for k in keys]
        
        param_combinations = [
            dict(zip(keys, combo))
            for combo in itertools.product(*values)
        ]
        
        total = len(param_combinations)
        results = []
        completed = 0
        failed = 0
        
        print(f"Starting parameter sweep: {total} combinations")
        print(f"Symbol: {self.symbol}, Timeframe: {self.timeframe}")
        print("-" * 60)
        
        # Sequentielle Ausführung (VPS-sicher)
        for i, params in enumerate(param_combinations, 1):
            print(f"[{i}/{total}] Testing: {params}", end=" ")
            
            try:
                result = self.engine.run(
                    self.strategy_name,
                    self.strategy_func,
                    params,
                    self.symbol,
                    self.timeframe
                )
                
                result_dict = result.to_dict()
                result_dict['params'] = params  # Explizit speichern
                
                if not result.failure_reasons:
                    results.append(result_dict)
                    print(f"✓ Return: {result.net_return:.2f}%, Trades: {result.trade_count}")
                    completed += 1
                else:
                    print(f"✗ Failed: {result.failure_reasons[0]}")
                    failed += 1
                    
            except Exception as e:
                print(f"✗ Error: {str(e)[:50]}")
                failed += 1
            
            # VPS-Safety: Kleine Pause zwischen Runs
            time.sleep(0.1)
        
        # Sortiere nach Metrik
        results_sorted = sorted(
            results,
            key=lambda x: x.get(metric, -float('inf')),
            reverse=True
        )
        
        best = results_sorted[0] if results_sorted else {
            'strategy_name': self.strategy_name,
            'net_return': 0,
            'failure_reasons': ['No successful results']
        }
        
        # Nur Top-10 behalten (RAM sparen)
        top_results = results_sorted[:self.TOP_RESULTS_TO_KEEP]
        
        sweep_result = SweepResult(
            strategy_name=self.strategy_name,
            symbol=self.symbol,
            timeframe=self.timeframe,
            total_combinations=total,
            completed=completed,
            failed=failed,
            best_result=best,
            all_results=top_results
        )
        
        sweep_result.execution_time_ms = int((time.time() - start_time) * 1000)
        
        return sweep_result
    
    def save(self, sweep_result: SweepResult, output_path: str):
        """Speichere Ergebnis als JSON"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(sweep_result.to_dict(), f, indent=2, default=str)
        
        print(f"\n✓ Sweep results saved to: {output_path}")


def quick_sweep(
    engine: BacktestEngine,
    strategy_name: str,
    strategy_func: Callable,
    param_grid: Dict[str, List[Any]],
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    metric: str = "net_return"
) -> SweepResult:
    """
    Convenience-Funktion für schnelle Sweeps
    """
    sweep = ParameterSweep(
        engine=engine,
        strategy_name=strategy_name,
        strategy_func=strategy_func,
        param_grid=param_grid,
        symbol=symbol,
        timeframe=timeframe
    )
    
    return sweep.run(metric=metric)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Parameter Sweep V1')
    parser.add_argument('--data', required=True, help='Data directory')
    parser.add_argument('--strategy', required=True, help='Strategy name')
    parser.add_argument('--symbol', default='BTCUSDT')
    parser.add_argument('--timeframe', default='1h')
    parser.add_argument('--output', help='Output JSON file')
    
    args = parser.parse_args()
    print(f"Parameter Sweep initialized")
    print(f"Max combinations: {ParameterSweep.MAX_COMBINATIONS}")
