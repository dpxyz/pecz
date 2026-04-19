#!/usr/bin/env python3
"""
Foundry V1 – Multi-Strategy Validation (v0.3)

Validiert 6 Strategie-Typen über:
1. Volles 2023-2025 Dataset (20,160 bars/asset)
2. 3 Assets (BTC, ETH, SOL)
3. Walk-Forward (5 windows)
4. Hold-out (2025 Q1)

Vergleicht: Mean-Reversion vs Trend-Following vs Momentum vs Breakout vs Hybrid
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from dsl_translator import translate_candidate_with_name
from backtest.backtest_engine import BacktestEngine

# ── Strategies ──
STRATEGIES = [
    # Mean-Rev (baseline)
    ('MeanRev_RSI_EMA100', {
        'strategy': {
            'name': 'MeanRev_RSI_EMA100', 'type': 'mean_reversion',
            'indicators': [{'name': 'RSI', 'params': {'period': 14}}, {'name': 'EMA', 'params': {'period': 100}}],
            'entry': {'condition': 'rsi_14 < 30 AND close > ema_100'},
            'exit': {'take_profit_pct': 1.5, 'stop_loss_pct': 2.5, 'max_hold_bars': 72}
        }
    }),
    # BB Breakout (trend-following)
    ('Breakout_BB_RSI', {
        'strategy': {
            'name': 'Breakout_BB_RSI', 'type': 'breakout',
            'indicators': [{'name': 'BB', 'params': {'period': 20, 'std_dev': 2.0}}, {'name': 'RSI', 'params': {'period': 14}}],
            'entry': {'condition': 'close > bb_upper_20 AND rsi_14 > 55'},
            'exit': {'trailing_stop_pct': 1.5, 'stop_loss_pct': 2.0, 'max_hold_bars': 48}
        }
    }),
    # EMA Crossover (trend-following)
    ('Trend_EMA_Cross', {
        'strategy': {
            'name': 'Trend_EMA_Cross', 'type': 'trend_following',
            'indicators': [{'name': 'EMA', 'params': {'period': 9}}, {'name': 'EMA', 'params': {'period': 21}}],
            'entry': {'condition': 'ema_9 > ema_21'},
            'exit': {'trailing_stop_pct': 2.0, 'stop_loss_pct': 3.0, 'max_hold_bars': 72}
        }
    }),
    # RSI Momentum (trend filter)
    ('Momentum_RSI_EMA50', {
        'strategy': {
            'name': 'Momentum_RSI_EMA50', 'type': 'momentum',
            'indicators': [{'name': 'RSI', 'params': {'period': 14}}, {'name': 'EMA', 'params': {'period': 50}}],
            'entry': {'condition': 'rsi_14 > 55 AND rsi_14 < 75 AND close > ema_50'},
            'exit': {'trailing_stop_pct': 2.0, 'stop_loss_pct': 2.5, 'max_hold_bars': 48}
        }
    }),
    # Mean-Rev with BB + EMA filter
    ('MeanRev_BB_EMA100', {
        'strategy': {
            'name': 'MeanRev_BB_EMA100', 'type': 'mean_reversion',
            'indicators': [{'name': 'BB', 'params': {'period': 20, 'std_dev': 2.0}}, {'name': 'RSI', 'params': {'period': 14}}, {'name': 'EMA', 'params': {'period': 100}}],
            'entry': {'condition': 'close < bb_lower_20 AND rsi_14 < 35 AND close > ema_100'},
            'exit': {'take_profit_pct': 1.5, 'stop_loss_pct': 2.5, 'max_hold_bars': 72}
        }
    }),
    # MACD Momentum
    ('Momentum_MACD', {
        'strategy': {
            'name': 'Momentum_MACD', 'type': 'momentum',
            'indicators': [{'name': 'MACD', 'params': {'fast': 12, 'slow': 26, 'signal': 9}}, {'name': 'EMA', 'params': {'period': 50}}],
            'entry': {'condition': 'macd_hist > 0 AND close > ema_50'},
            'exit': {'trailing_stop_pct': 2.0, 'stop_loss_pct': 2.5, 'max_hold_bars': 48}
        }
    }),
]

ASSETS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
PERIODS = {
    '2023_full': ('2023-01-01', '2023-12-31'),
    '2024_h1': ('2024-01-01', '2024-06-30'),
    '2024_h2': ('2024-07-01', '2024-12-31'),
    '2024_full': ('2024-01-01', '2024-12-31'),
    '2025_q1': ('2025-01-01', '2025-03-31'),
}

FEE_RATE = 0.0001
SLIPPAGE_BPS = 1.0
INITIAL_CAPITAL = 100.0

GATES = {
    'min_return_pct': 1.0,
    'min_profit_factor': 1.05,
    'max_drawdown_pct': 20.0,
    'min_trades': 20,
    'max_consecutive_losses': 8,
    'min_sharpe': 0.1,
}

def filter_period(df, start, end):
    start_ms = int(datetime.strptime(start, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.strptime(end, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp() * 1000) + 86400000
    return df.filter(
        (pl.col('timestamp').cast(pl.Int64) >= start_ms) &
        (pl.col('timestamp').cast(pl.Int64) <= end_ms)
    )

def check_gates(r):
    if r.trade_count < GATES['min_trades']:
        return False, f'trades({r.trade_count}<{GATES["min_trades"]})'
    checks = [
        ('return', r.net_return >= GATES['min_return_pct']),
        ('pf', r.profit_factor >= GATES['min_profit_factor']),
        ('dd', r.max_drawdown <= GATES['max_drawdown_pct']),
        ('trades', r.trade_count >= GATES['min_trades']),
        ('cl', r.max_consecutive_losses <= GATES['max_consecutive_losses']),
        ('sharpe', r.sharpe_ratio >= GATES['min_sharpe']),
    ]
    fails = [name for name, ok in checks if not ok]
    return len(fails) == 0, ', '.join(fails) if fails else 'ALL_PASS'


def main():
    print('╔════════════════════════════════════════════════════╗')
    print('║  Foundry V1 — Multi-Strategy Validation v0.3       ║')
    print('║  6 Strategien × 3 Assets × 5 Perioden              ║')
    print('║  Platform: Hyperliquid (0.01% Maker)                ║')
    print('╚════════════════════════════════════════════════════╝')
    print()
    
    engine = BacktestEngine(data_path=str(Path(__file__).parent / 'data'),
                            fee_rate=FEE_RATE, slippage_bps=SLIPPAGE_BPS,
                            initial_capital=INITIAL_CAPITAL)
    
    # Load full datasets
    data_cache = {}
    for symbol in ASSETS:
        df = pl.read_parquet(f'data/{symbol}_1h_full.parquet')
        data_cache[symbol] = df
        print(f'  Loaded {symbol}: {len(df)} rows')
    
    # ── Strategy × Asset × Period Matrix ──
    print(f'\n{"Strategy":30s} {"Asset":8s} {"Period":12s} {"Trades":>6s} {"Return":>8s} {"PF":>6s} {"DD%":>6s} {"Win%":>6s} {"CL":>3s} {"Sharpe":>7s} {"Gate":>8s}')
    print('─' * 105)
    
    results = []
    
    for strat_name, candidate in STRATEGIES:
        name, func = translate_candidate_with_name(candidate)
        exit_cfg = candidate['strategy'].get('exit', {})
        
        for symbol in ASSETS:
            df_full = data_cache[symbol]
            
            for period_name, (start, end) in PERIODS.items():
                df_period = filter_period(df_full, start, end)
                if len(df_period) < 100:
                    continue
                
                r = engine.run(name, func, {}, symbol, '1h', exit_config=exit_cfg, df=df_period)
                passed, gate_info = check_gates(r)
                
                gate_str = '✅' if passed else f'❌ ({gate_info})' if r.trade_count > 0 else '❌ (0trades)'
                
                print(f'{name:30s} {symbol:8s} {period_name:12s} {r.trade_count:>6d} {r.net_return:>7.2f}% {r.profit_factor:>6.3f} {r.max_drawdown:>5.1f}% {r.win_rate:>5.1f}% {r.max_consecutive_losses:>3d} {r.sharpe_ratio:>7.3f} {gate_str:>8s}')
                
                results.append({
                    'strategy': name, 'type': candidate['strategy']['type'],
                    'symbol': symbol, 'period': period_name,
                    'trades': r.trade_count, 'net_return_pct': round(r.net_return, 2),
                    'profit_factor': round(r.profit_factor, 3), 'max_drawdown_pct': round(r.max_drawdown, 1),
                    'win_rate_pct': round(r.win_rate, 1), 'max_consecutive_losses': r.max_consecutive_losses,
                    'sharpe_ratio': round(r.sharpe_ratio, 3), 'gate_passed': passed, 'gate_info': gate_info
                })
    
    # ── Summary ──
    print(f'\n{"="*105}')
    print('ZUSAMMENFASSUNG: PASS-Rate pro Strategie')
    print('═' * 105)
    
    for strat_name, candidate in STRATEGIES:
        strat_results = [r for r in results if r['strategy'] == strat_name]
        total = len(strat_results)
        passed = sum(1 for r in strat_results if r['gate_passed'])
        avg_return = sum(r['net_return_pct'] for r in strat_results) / max(total, 1)
        best_asset = max(strat_results, key=lambda x: x['net_return_pct']) if strat_results else None
        
        print(f'\n  {strat_name} ({candidate["strategy"]["type"]}):')
        print(f'    PASS: {passed}/{total} ({passed/max(total,1)*100:.0f}%)')
        print(f'    Avg Return: {avg_return:.2f}%')
        if best_asset:
            print(f'    Best: {best_asset["symbol"]} {best_asset["period"]} → {best_asset["net_return_pct"]:+.2f}%')
    
    # Save results
    output_path = Path(__file__).parent / 'runs' / 'multi_strategy_validation.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump({'timestamp': datetime.now().isoformat(), 'results': results}, f, indent=2, default=str)
    print(f'\nResults saved to: {output_path}')


if __name__ == '__main__':
    main()