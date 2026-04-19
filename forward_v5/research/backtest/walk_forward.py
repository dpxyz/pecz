#!/usr/bin/env python3
"""
Walk-Forward Analysis V2 - Full Exit Logic Support

- Nutzt BacktestEngine.run() statt _quick_simulate
- TP/SL/max-hold Exit-Logik wird im Walk-Forward berücksichtigt
- Kleine Fenster (VPS-RAM)
- Wenige Kombinationen
- Strikte Train/Validate/OOS Trennung
- Keine Data-Leakage
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Callable, Any
from dataclasses import dataclass

import polars as pl

from backtest.backtest_engine import BacktestEngine, BacktestResult
from backtest.parameter_sweep import ParameterSweep, SweepResult


@dataclass
class WalkForwardResult:
    """Ergebnis einer Walk-Forward Analyse"""
    strategy_name: str
    symbol: str
    timeframe: str
    n_windows: int
    
    # In-Sample (Train) Performance
    is_results: List[Dict]
    
    # Out-of-Sample Performance
    oos_results: List[Dict]
    
    # Robustness Score
    robustness_score: float = 0.0  # 0-100
    passed: bool = False
    
    execution_time_ms: int = 0
    
    def to_dict(self) -> Dict:
        return {
            'strategy_name': self.strategy_name,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'n_windows': self.n_windows,
            'is_results': self.is_results,
            'oos_results': self.oos_results,
            'robustness_score': self.robustness_score,
            'passed': self.passed,
            'execution_time_ms': self.execution_time_ms
        }


class WalkForwardAnalyzer:
    """
    Walk-Forward Analyse V2 - Full Engine
    
    Konzept:
    1. Teile Daten in Windows (z.B. 70% Train, 30% OOS)
    2. Optimiere auf Train (mit BacktestEngine inkl. Exit-Logik)
    3. Teste besten Parameter auf OOS (mit BacktestEngine inkl. Exit-Logik)
    4. Wiederhole für mehrere Window
    5. Berechne Robustness Score
    
    VPS-Limits:
    - Max 5 Windows (RAM)
    - Max 20 Parameter-Kombinationen pro Window
    """
    
    MAX_WINDOWS = 5
    MAX_PARAMS_PER_WINDOW = 20
    
    def __init__(
        self,
        engine: BacktestEngine,
        data_path: str,
        train_pct: float = 0.7,
        n_windows: int = 3  # Weniger = VPS-sicherer
    ):
        self.engine = engine
        self.data_path = Path(data_path)
        self.train_pct = train_pct
        self.n_windows = min(n_windows, self.MAX_WINDOWS)
    
    def _split_data(self, symbol: str, timeframe: str) -> List[tuple]:
        """
        Teile Daten in Windows
        Returns: List of (train_df, test_lf) LazyFrames
        """
        file_path = self.data_path / f"{symbol}_{timeframe}.parquet"
        
        if not file_path.exists():
            raise FileNotFoundError(f"Data not found: {file_path}")
        
        df = pl.read_parquet(file_path)
        n_rows = len(df)
        
        # Berechne Window-Größe
        window_size = n_rows // self.n_windows
        train_size = int(window_size * self.train_pct)
        
        windows = []
        for i in range(self.n_windows):
            start_idx = i * window_size
            end_idx = min(start_idx + window_size, n_rows)
            
            # Train / Test Split
            train_df = df[start_idx:start_idx + train_size]
            test_df = df[start_idx + train_size:end_idx]
            
            if len(train_df) < 50 or len(test_df) < 20:
                continue  # Skip zu kleine Windows
            
            windows.append((train_df, test_df))
        
        return windows
    
    def analyze(
        self,
        strategy_name: str,
        strategy_func: Callable,
        param_grid: Dict[str, List[Any]],
        symbol: str = "BTCUSDT",
        timeframe: str = "1h",
        robustness_threshold: float = 0.6,  # 60% = passed
        exit_config: Dict = None
    ) -> WalkForwardResult:
        """
        Führe Walk-Forward Analyse durch (V2: Full Engine)
        """
        start_time = time.time()
        
        if exit_config is None:
            exit_config = {}
        
        # Reduziere Grid für VPS-Safety
        param_grid = self._reduce_grid(param_grid)
        
        # Splitte Daten
        windows = self._split_data(symbol, timeframe)
        
        is_results = []
        oos_results = []
        
        print(f"Walk-Forward Analysis V2 (Full Engine): {len(windows)} windows")
        print(f"Train: {self.train_pct*100:.0f}%, Test: {(1-self.train_pct)*100:.0f}%")
        print(f"Exit config: {exit_config}")
        print("=" * 60)
        
        for i, (train_df, test_df) in enumerate(windows, 1):
            print(f"\n--- Window {i}/{len(windows)} ---")
            print(f"Train size: {len(train_df)}, Test size: {len(test_df)}")
            
            # 1. Train: Finde beste Parameter mit VOLLER BacktestEngine
            best_return = -float('inf')
            best_params = None
            
            keys = list(param_grid.keys())
            values = [param_grid[k] for k in keys]
            
            import itertools
            for combo in itertools.product(*values):
                params = dict(zip(keys, combo))
                
                result = self.engine.run(
                    strategy_name, strategy_func, params, symbol, timeframe,
                    exit_config=exit_config, df=train_df
                )
                
                if result.trade_count > 0 and result.net_return > best_return:
                    best_return = result.net_return
                    best_params = params
            
            if best_params is None:
                # No params produced trades - use first combo
                best_params = dict(zip(keys, values[0] if values else []))
                best_return = 0.0
            
            print(f"Best train params: {best_params}, Return: {best_return:.2f}%")
            
            is_results.append({
                'window': i,
                'return': best_return,
                'params': best_params
            })
            
            # 2. Test: Validiere auf OOS mit VOLLER BacktestEngine
            oos_result = self.engine.run(
                strategy_name, strategy_func, best_params, symbol, timeframe,
                exit_config=exit_config, df=test_df
            )
            
            oos_return = oos_result.net_return if oos_result.trade_count > 0 else 0.0
            
            degradation = (best_return - oos_return) / max(abs(best_return), 0.01) if best_return != 0 else 0
            
            print(f"OOS return: {oos_return:.2f}% (trades: {oos_result.trade_count})")
            
            oos_results.append({
                'window': i,
                'return': oos_return,
                'params': best_params,
                'degradation': degradation,
                'trades': oos_result.trade_count,
                'profit_factor': oos_result.profit_factor,
                'max_drawdown': oos_result.max_drawdown
            })
        
        # Berechne Robustness Score
        robustness = self._calc_robustness(is_results, oos_results)
        
        wfr = WalkForwardResult(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            n_windows=len(windows),
            is_results=is_results,
            oos_results=oos_results,
            robustness_score=robustness,
            passed=robustness >= robustness_threshold * 100
        )
        
        wfr.execution_time_ms = int((time.time() - start_time) * 1000)
        
        return wfr
    
    def _reduce_grid(self, grid: Dict) -> Dict:
        """Reduziere Grid auf MAX_PARAMS_PER_WINDOW"""
        import itertools
        
        total = 1
        for v in grid.values():
            total *= len(v)
        
        if total <= self.MAX_PARAMS_PER_WINDOW:
            return grid
        
        # Reduziere: Nimm nur erste n Werte pro Parameter
        reduced = {}
        n_params = len(grid)
        max_per_param = max(1, int(self.MAX_PARAMS_PER_WINDOW ** (1/n_params)))
        
        for key, values in grid.items():
            reduced[key] = values[:max_per_param]
        
        print(f"Grid reduced: {total} -> {self._count_combinations(reduced)} combinations")
        
        return reduced
    
    def _count_combinations(self, grid: Dict) -> int:
        import itertools
        total = 1
        for v in grid.values():
            total *= len(v)
        return total
    
    def _calc_robustness(self, is_results: List, oos_results: List) -> float:
        """
        Berechne Robustness Score (0-100)
        
        Formel:
        - OOS positiv: +30 Punkte pro Window
        - Degradation < 50%: +20 Punkte pro Window
        - Konsistenz (alle OOS same direction): +10 Punkte
        """
        if not oos_results:
            return 0.0
        
        score = 0.0
        n = len(oos_results)
        
        for oos in oos_results:
            # OOS positiv
            if oos['return'] > 0:
                score += 30 / n
            
            # Geringe Degradation
            if oos['degradation'] < 0.5:
                score += 20 / n
        
        # Konsistenz
        directions = [1 if r['return'] > 0 else -1 for r in oos_results]
        if len(set(directions)) == 1:
            score += 10
        
        return min(100.0, score)
    
    def save(self, result: WalkForwardResult, output_path: str):
        """Speichere Ergebnis"""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        
        print(f"\n✓ Walk-forward results saved to: {output_path}")


if __name__ == "__main__":
    print("Walk-Forward Analyzer V2")
    print(f"Max windows: {WalkForwardAnalyzer.MAX_WINDOWS}")
    print(f"Max params/window: {WalkForwardAnalyzer.MAX_PARAMS_PER_WINDOW}")