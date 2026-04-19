#!/usr/bin/env python3
"""
Foundry V1 — Breite Validierung (Priorität 1)

Validiert die RSI_EMA_100_MeanRev Strategie über:
1. Mehrere Zeiträume (2023, 2024, 2025)
2. Mehrere Assets (BTC, ETH, SOL)
3. Saurer Hold-out (letzte 3 Monate = Jan-Mar 2025)
4. Walk-Forward mit längeren Fenstern

Output: Strukturierter Report mit PASS/FAIL pro Asset x Periode
"""

import sys
import json
import yaml
from pathlib import Path
from datetime import datetime

import polars as pl

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))
from dsl_translator import translate_candidate_with_name
from backtest.backtest_engine import BacktestEngine
from backtest.walk_forward import WalkForwardAnalyzer


# ── Konfiguration ──
CANDIDATE = {
    'strategy': {
        'name': 'RSI_EMA_100_MeanRev',
        'type': 'mean_reversion',
        'indicators': [
            {'name': 'RSI', 'params': {'period': 14}},
            {'name': 'EMA', 'params': {'period': 100}}
        ],
        'entry': {'condition': 'rsi_14 < 30 AND close > ema_100'},
        'exit': {'take_profit_pct': 1.5, 'stop_loss_pct': 2.5, 'max_hold_bars': 72}
    }
}

EXIT_CONFIG = CANDIDATE['strategy']['exit']

# Perioden für Multi-Period Validation
PERIODS = {
    '2023_full': ('2023-01-01', '2023-12-31'),
    '2024_h1': ('2024-01-01', '2024-06-30'),
    '2024_h2': ('2024-07-01', '2024-12-31'),
    '2024_full': ('2024-01-01', '2024-12-31'),
    '2025_q1': ('2025-01-01', '2025-03-31'),  # HOLD-OUT (ungeesehen!)
}

ASSETS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

# Hyperliquid Maker Fees
FEE_RATE = 0.0001  # 0.01%
SLIPPAGE_BPS = 1.0  # 1 bp
INITIAL_CAPITAL = 100.0  # 100€

# Gate Thresholds (from spec.yaml v0.3)
GATES = {
    'min_return_pct': 1.0,
    'min_profit_factor': 1.05,
    'max_drawdown_pct': 20.0,
    'min_trades': 20,
    'max_consecutive_losses': 8,
    'min_sharpe': 0.1,
}


def load_full_data(symbol: str) -> pl.DataFrame:
    """Lade das full Dataset (2023-2025)"""
    data_path = Path(__file__).parent / 'data'
    file_path = data_path / f'{symbol}_1h_full.parquet'
    
    if not file_path.exists():
        print(f'  ❌ {file_path} nicht gefunden!')
        return None
    
    df = pl.read_parquet(file_path)
    print(f'  Loaded {symbol}: {len(df)} rows, {df["timestamp"].min()} to {df["timestamp"].max()}')
    return df


def filter_period(df: pl.DataFrame, start: str, end: str) -> pl.DataFrame:
    """Filtere DataFrame auf Zeitraum"""
    from datetime import datetime, timezone
    start_dt = datetime.strptime(start, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    
    # Convert to same dtype as the timestamp column
    ts_dtype = df['timestamp'].dtype
    if ts_dtype == pl.Datetime('ms', 'UTC'):
        start_val = int(start_dt.timestamp() * 1000)
        end_val = int(end_dt.timestamp() * 1000) + 86400000  # +1 Tag
    elif ts_dtype == pl.Datetime('us', 'UTC') or ts_dtype == pl.Datetime('us', None):
        start_val = int(start_dt.timestamp() * 1_000_000)
        end_val = int(end_dt.timestamp() * 1_000_000) + 86_400_000_000
    else:
        start_val = start_dt
        end_val = end_dt
    
    # Use Polars native filtering with epoch ms values
    # Cast timestamp to epoch ms for comparison
    return df.filter(
        (pl.col('timestamp').cast(pl.Int64) >= start_val) &
        (pl.col('timestamp').cast(pl.Int64) <= end_val)
    )


def run_backtest_period(engine: BacktestEngine, name: str, func, df: pl.DataFrame, 
                         period_name: str, symbol: str) -> dict:
    """Führe Backtest für eine Periode durch"""
    result = engine.run(name, func, {}, symbol, '1h', exit_config=EXIT_CONFIG, df=df)
    
    return {
        'period': period_name,
        'symbol': symbol,
        'trades': result.trade_count,
        'net_return_pct': round(result.net_return, 2),
        'profit_factor': round(result.profit_factor, 3),
        'max_drawdown_pct': round(result.max_drawdown, 1),
        'win_rate_pct': round(result.win_rate, 1),
        'max_consecutive_losses': result.max_consecutive_losses,
        'sharpe_ratio': round(result.sharpe_ratio, 3),
        'expectancy': round(result.expectancy, 4),
        'bars': len(df),
    }


def check_gates(stats: dict) -> dict:
    """Prüfe Gate-Conditions"""
    checks = {
        'return': stats['net_return_pct'] >= GATES['min_return_pct'],
        'pf': stats['profit_factor'] >= GATES['min_profit_factor'],
        'dd': stats['max_drawdown_pct'] <= GATES['max_drawdown_pct'],
        'trades': stats['trades'] >= GATES['min_trades'],
        'consec_loss': stats['max_consecutive_losses'] <= GATES['max_consecutive_losses'],
        'sharpe': stats['sharpe_ratio'] >= GATES['min_sharpe'],
    }
    passed = all(checks.values())
    return {'passed': passed, 'checks': checks}


def main():
    print('╔══════════════════════════════════════════════╗')
    print('║  Foundry V1 — Breite Validierung            ║')
    print('║  Strategie: RSI_EMA_100_MeanRev              ║')
    print('║  Platform: Hyperliquid (0.01% Maker)        ║')
    print('║  Kapital: 100€                              ║')
    print('╚══════════════════════════════════════════════╝')
    print()
    
    # Übersetze Strategie
    name, func = translate_candidate_with_name(CANDIDATE)
    engine = BacktestEngine(
        data_path=str(Path(__file__).parent / 'data'),
        fee_rate=FEE_RATE,
        slippage_bps=SLIPPAGE_BPS,
        initial_capital=INITIAL_CAPITAL
    )
    
    all_results = []
    
    # ── Multi-Asset x Multi-Period Matrix ──
    print('═' * 70)
    print('PHASE 1: Multi-Asset × Multi-Period Backtest')
    print('═' * 70)
    print()
    
    data_cache = {}
    for symbol in ASSETS:
        df = load_full_data(symbol)
        if df is None:
            continue
        data_cache[symbol] = df
    
    # Header
    print(f'\n{"Asset":8s} {"Periode":12s} {"Bars":>6s} {"Trades":>7s} {"Return":>8s} {"PF":>6s} {"DD%":>6s} {"Win%":>6s} {"CL":>3s} {"Sharpe":>7s} {"Gate":>5s}')
    print('─' * 85)
    
    for symbol in ASSETS:
        df_full = data_cache.get(symbol)
        if df_full is None:
            continue
        
        for period_name, (start, end) in PERIODS.items():
            df_period = filter_period(df_full, start, end)
            if len(df_period) < 100:
                print(f'{symbol:8s} {period_name:12s} {"< 100 bars, skip"}')
                continue
            
            # Check if 'signal' column exists in df — we need raw data for engine.run()
            # engine.run() will call strategy_func internally
            stats = run_backtest_period(engine, name, func, df_period, period_name, symbol)
            gate = check_gates(stats)
            
            gate_str = '✅' if gate['passed'] else '❌'
            # Mark which checks failed
            fail_details = [k for k, v in gate['checks'].items() if not v]
            if fail_details:
                gate_str += f' ({", ".join(fail_details)})'
            
            print(f'{symbol:8s} {period_name:12s} {stats["bars"]:>6d} {stats["trades"]:>7d} {stats["net_return_pct"]:>7.2f}% {stats["profit_factor"]:>6.3f} {stats["max_drawdown_pct"]:>5.1f}% {stats["win_rate_pct"]:>5.1f}% {stats["max_consecutive_losses"]:>3d} {stats["sharpe_ratio"]:>7.3f} {gate_str:>5s}')
            
            stats['gate'] = gate
            all_results.append(stats)
    
    # ── Walk-Forward über volle Zeitreihe ──
    print(f'\n{"="*70}')
    print('PHASE 2: Walk-Forward Validation (Full Dataset)')
    print('═' * 70)
    print()
    
    for symbol in ASSETS:
        df_full = data_cache.get(symbol)
        if df_full is None:
            continue
        
        print(f'\n--- {symbol} Walk-Forward (2023-2025) ---')
        
        # Simple walk-forward: 5 windows, 70/30 split
        n_windows = 5
        total_bars = len(df_full)
        window_size = total_bars // n_windows
        
        profitable_windows = 0
        for i in range(n_windows):
            # Train: first 70% of window, Test: last 30%
            start = i * window_size
            end = start + window_size
            split = start + int(window_size * 0.7)
            
            df_train = df_full.slice(start, split - start)
            df_test = df_full.slice(split, end - split)
            
            if len(df_train) < 100 or len(df_test) < 50:
                continue
            
            # Run backtest on test period
            r = engine.run(name, func, {}, symbol, '1h', exit_config=EXIT_CONFIG, df=df_test)
            oos_ret = r.net_return
            trades = r.trade_count
            
            if oos_ret > 0:
                profitable_windows += 1
            
            print(f'  Window {i+1}/5: OOS {oos_ret:+.2f}% ({trades} trades)')
        
        print(f'  → {profitable_windows}/{n_windows} windows profitable', end='')
        if profitable_windows >= 2:
            print(' ✅')
        else:
            print(' ❌')
    
    # ── Hold-out Test (2025 Q1 = ungeesehen) ──
    print(f'\n{"="*70}')
    print('PHASE 3: Hold-out Test (2025 Q1 — UNGESEHEN)')
    print('═' * 70)
    print()
    
    print(f'\n{"Asset":8s} {"Trades":>7s} {"Return":>8s} {"PF":>6s} {"DD%":>6s} {"Win%":>6s} {"CL":>3s} {"Gate":>5s}')
    print('─' * 55)
    
    holdout_results = []
    for symbol in ASSETS:
        df_full = data_cache.get(symbol)
        if df_full is None:
            continue
        
        df_holdout = filter_period(df_full, '2025-01-01', '2025-03-31')
        if len(df_holdout) < 50:
            print(f'{symbol:8s} insufficient holdout data ({len(df_holdout)} bars)')
            continue
        
        stats = run_backtest_period(engine, name, func, df_holdout, '2025_q1', symbol)
        gate = check_gates(stats)
        
        gate_str = '✅' if gate['passed'] else '❌'
        fail_details = [k for k, v in gate['checks'].items() if not v]
        if fail_details:
            gate_str += f' ({", ".join(fail_details)})'
        
        print(f'{symbol:8s} {stats["trades"]:>7d} {stats["net_return_pct"]:>7.2f}% {stats["profit_factor"]:>6.3f} {stats["max_drawdown_pct"]:>5.1f}% {stats["win_rate_pct"]:>5.1f}% {stats["max_consecutive_losses"]:>3d} {gate_str:>5s}')
        
        stats['gate'] = gate
        holdout_results.append(stats)
    
    # ── Zusammenfassung ──
    print(f'\n{"="*70}')
    print('ZUSAMMENFASSUNG')
    print('═' * 70)
    print()
    
    # Wieviele Asset x Period Kombinationen PASS?
    total = len(all_results)
    passing = sum(1 for r in all_results if r['gate']['passed'])
    
    print(f'Multi-Period x Multi-Asset:')
    print(f'  Total: {total} Kombinationen')
    print(f'  PASS: {passing} ({passing/total*100:.0f}% bei Total={total})')
    print(f'  FAIL: {total - passing}')
    print()
    
    # Hold-out
    ho_total = len(holdout_results)
    ho_passing = sum(1 for r in holdout_results if r['gate']['passed'])
    print(f'Hold-out (2025 Q1, ungeesehen):')
    print(f'  Total: {ho_total} Assets')
    print(f'  PASS: {ho_passing}')
    print(f'  FAIL: {ho_total - ho_passing}')
    print()
    
    # Robustheit pro Asset
    for symbol in ASSETS:
        asset_results = [r for r in all_results if r['symbol'] == symbol]
        asset_pass = sum(1 for r in asset_results if r['gate']['passed'])
        if asset_results:
            avg_return = sum(r['net_return_pct'] for r in asset_results) / len(asset_results)
            print(f'  {symbol}: {asset_pass}/{len(asset_results)} Periods PASS, Avg Return: {avg_return:.2f}%')
    
    # Save results
    output_path = Path(__file__).parent / 'runs' / 'validation_v2_results.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert for JSON serialization
    json_results = []
    for r in all_results + holdout_results:
        jr = dict(r)
        jr['gate'] = {
            'passed': r['gate']['passed'],
            'checks': {k: str(v) for k, v in r['gate']['checks'].items()}
        }
        json_results.append(jr)
    
    with open(output_path, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'strategy': CANDIDATE['strategy']['name'],
            'platform': 'hyperliquid',
            'fee_rate': FEE_RATE,
            'initial_capital': INITIAL_CAPITAL,
            'results': json_results,
            'summary': {
                'total_combinations': total,
                'passing': passing,
                'pass_rate': f'{passing/total*100:.0f}%' if total > 0 else '0%',
                'holdout_passing': ho_passing,
                'holdout_total': ho_total,
            }
        }, f, indent=2, default=str)
    
    print(f'\nResults saved to: {output_path}')


if __name__ == '__main__':
    main()