#!/usr/bin/env python3
"""
Foundry V1 – ATR Regime-Filter Validation (Final Robustness Check)

Vergleicht die beste Strategie (ADX+EMA MACD) mit ATR-Filter-Varianten:
1. BASELINE: ADX+EMA (50% Pass-Rate, bereits validiert)
2. ATR_EXPANSION: ADX+EMA AND ATR(14) > ATR(14)_SMA(50) (Volatilitäts-Expansion)
3. ATR_BELOW_MEDIAN: ADX+EMA AND ATR(14) < median(ATR) (niedrige Vol = weniger Whipsaw)
4. ATR+EMA_ONLY: EMA_Bull filter only (25% Pass, als Referenz)

Gleiche Gates wie vorher – keine Lockerung.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from dsl_translator import translate_candidate_with_name
from backtest.backtest_engine import BacktestEngine

# ── Strategy Variants ──
STRATEGIES = {
    'BASELINE_ADX_EMA': {
        'strategy': {
            'name': 'MACD_ADX_EMA200', 'type': 'momentum',
            'indicators': [
                {'name': 'MACD', 'params': {'fast': 12, 'slow': 26, 'signal': 9}},
                {'name': 'EMA', 'params': {'period': 50}},
                {'name': 'EMA', 'params': {'period': 200}},
                {'name': 'ADX', 'params': {'period': 14}}
            ],
            'entry': {'condition': 'macd_hist > 0 AND close > ema_50 AND ema_50 > ema_200 AND adx_14 > 20'},
            'exit': {'trailing_stop_pct': 2.0, 'stop_loss_pct': 2.5, 'max_hold_bars': 48}
        }
    },
    'ATR_EXPANSION': {
        'strategy': {
            'name': 'MACD_ADX_EMA_ATR', 'type': 'momentum',
            'indicators': [
                {'name': 'MACD', 'params': {'fast': 12, 'slow': 26, 'signal': 9}},
                {'name': 'EMA', 'params': {'period': 50}},
                {'name': 'EMA', 'params': {'period': 200}},
                {'name': 'ADX', 'params': {'period': 14}},
                {'name': 'ATR', 'params': {'period': 14}}
            ],
            'entry': {'condition': 'macd_hist > 0 AND close > ema_50 AND ema_50 > ema_200 AND adx_14 > 20 AND atr_14 > atr_sma_50'},
            'exit': {'trailing_stop_pct': 2.0, 'stop_loss_pct': 2.5, 'max_hold_bars': 48}
        }
    },
    'ATR_TIGHT': {
        'strategy': {
            'name': 'MACD_ADX_EMA_ATR_TIGHT', 'type': 'momentum',
            'indicators': [
                {'name': 'MACD', 'params': {'fast': 12, 'slow': 26, 'signal': 9}},
                {'name': 'EMA', 'params': {'period': 50}},
                {'name': 'EMA', 'params': {'period': 200}},
                {'name': 'ADX', 'params': {'period': 14}},
                {'name': 'ATR', 'params': {'period': 14}}
            ],
            'entry': {'condition': 'macd_hist > 0 AND close > ema_50 AND ema_50 > ema_200 AND adx_14 > 25 AND atr_14 > atr_sma_50'},
            'exit': {'trailing_stop_pct': 2.0, 'stop_loss_pct': 2.5, 'max_hold_bars': 48}
        }
    },
    'EMA_ONLY': {
        'strategy': {
            'name': 'MACD_EMA200', 'type': 'momentum',
            'indicators': [
                {'name': 'MACD', 'params': {'fast': 12, 'slow': 26, 'signal': 9}},
                {'name': 'EMA', 'params': {'period': 50}},
                {'name': 'EMA', 'params': {'period': 200}}
            ],
            'entry': {'condition': 'macd_hist > 0 AND close > ema_50 AND ema_50 > ema_200'},
            'exit': {'trailing_stop_pct': 2.0, 'stop_loss_pct': 2.5, 'max_hold_bars': 48}
        }
    },
}

ASSETS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT', 'XRPUSDT', 'ADAUSDT']
PERIODS = {
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
    print('╔════════════════════════════════════════════════════════╗')
    print('║  Foundry V1 – ATR Regime-Filter Validation (Final)    ║')
    print('║  4 Filter × 8 Assets × 2 Periods = 64 Tests           ║')
    print('║  Gates: UNCHANGED (no relaxation)                      ║')
    print('╚════════════════════════════════════════════════════════╝')
    print()
    
    engine = BacktestEngine(data_path=str(Path(__file__).parent / 'data'),
                            fee_rate=FEE_RATE, slippage_bps=SLIPPAGE_BPS,
                            initial_capital=INITIAL_CAPITAL)
    
    # Load datasets
    data_cache = {}
    for symbol in ASSETS:
        try:
            df = pl.read_parquet(f'data/{symbol}_1h_full.parquet')
            data_cache[symbol] = df
        except Exception as e:
            print(f'  ❌ {symbol}: {e}')
    print(f'  Loaded {len(data_cache)} assets')
    print()
    
    # ── Run all variants ──
    results = {}
    
    for variant_name, candidate in STRATEGIES.items():
        name, func = translate_candidate_with_name(candidate)
        exit_cfg = candidate['strategy'].get('exit', {})
        variant_results = []
        
        print(f'\n{"="*110}')
        print(f'VARIANT: {variant_name} ({name})')
        print(f'{"Asset":10s} {"Period":12s} {"Trades":>6s} {"Return":>8s} {"PF":>6s} {"DD%":>6s} {"Win%":>6s} {"CL":>3s} {"Sharpe":>7s} {"Gate":>20s}')
        print('─' * 110)
        
        for symbol in ASSETS:
            df_full = data_cache.get(symbol)
            if df_full is None:
                continue
            
            for period_name, (start, end) in PERIODS.items():
                df_period = filter_period(df_full, start, end)
                if len(df_period) < 100:
                    continue
                
                r = engine.run(name, func, {}, symbol, '1h', exit_config=exit_cfg, df=df_period)
                passed, gate_info = check_gates(r)
                gate_str = '✅' if passed else f'❌({gate_info[:18]})'
                
                print(f'{symbol:10s} {period_name:12s} {r.trade_count:>6d} {r.net_return:>7.2f}% {r.profit_factor:>6.3f} {r.max_drawdown:>5.1f}% {r.win_rate:>5.1f}% {r.max_consecutive_losses:>3d} {r.sharpe_ratio:>7.3f} {gate_str:>20s}')
                
                variant_results.append({
                    'strategy': name, 'variant': variant_name,
                    'symbol': symbol, 'period': period_name,
                    'trades': r.trade_count, 'net_return_pct': round(r.net_return, 2),
                    'profit_factor': round(r.profit_factor, 3),
                    'max_drawdown_pct': round(r.max_drawdown, 1),
                    'win_rate_pct': round(r.win_rate, 1),
                    'max_consecutive_losses': r.max_consecutive_losses,
                    'sharpe_ratio': round(r.sharpe_ratio, 3),
                    'gate_passed': passed, 'gate_info': gate_info
                })
        
        results[variant_name] = variant_results
    
    # ── Summary ──
    print(f'\n{"="*110}')
    print('ZUSAMMENFASSUNG: ATR-Filter Vergleich (Gates: UNVERÄNDERT)')
    print('═' * 110)
    print()
    print(f'{"Variant":20s} {"PASS":>6s} {"Total":>6s} {"Rate":>7s} {"AvgRet":>8s} {"AvgPF":>7s} {"AvgDD":>7s} {"AvgCL":>6s} {"Best":>10s} {"Worst":>10s}')
    print('─' * 110)
    
    for variant_name in STRATEGIES:
        vr = results[variant_name]
        total = len(vr)
        passed = sum(1 for r in vr if r['gate_passed'])
        avg_ret = sum(r['net_return_pct'] for r in vr) / max(total, 1)
        avg_pf = sum(r['profit_factor'] for r in vr) / max(total, 1)
        avg_dd = sum(r['max_drawdown_pct'] for r in vr) / max(total, 1)
        avg_cl = sum(r['max_consecutive_losses'] for r in vr) / max(total, 1)
        best = max(vr, key=lambda x: x['net_return_pct'])
        worst = min(vr, key=lambda x: x['net_return_pct'])
        
        print(f'{variant_name:20s} {passed:>6d} {total:>6d} {passed/max(total,1)*100:>6.0f}% {avg_ret:>7.2f}% {avg_pf:>7.3f} {avg_dd:>6.1f}% {avg_cl:>5.1f} {best["symbol"]:>10s} {worst["symbol"]:>10s}')
    
    # ── Direct Comparison: BASELINE vs ATR variants ──
    baseline = results['BASELINE_ADX_EMA']
    print(f'\n{"="*110}')
    print('DETAIL-VERGLEICH: BASELINE (ADX+EMA) → ATR-Varianten')
    print('═' * 110)
    
    for variant_name in ['ATR_EXPANSION', 'ATR_TIGHT']:
        vr = results[variant_name]
        print(f'\n  {variant_name} vs BASELINE_ADX_EMA:')
        for v in vr:
            matching = [b for b in baseline if b['symbol'] == v['symbol'] and b['period'] == v['period']]
            if matching:
                b = matching[0]
                cl_diff = v['max_consecutive_losses'] - b['max_consecutive_losses']
                dd_diff = v['max_drawdown_pct'] - b['max_drawdown_pct']
                ret_diff = v['net_return_pct'] - b['net_return_pct']
                pf_diff = v['profit_factor'] - b['profit_factor']
                symbol = f'{v["symbol"]:8s}'
                period = f'{v["period"]:10s}'
                cl_arrow = '🟢' if cl_diff < 0 else '🔴' if cl_diff > 0 else '⚪'
                dd_arrow = '🟢' if dd_diff < 0 else '🔴' if dd_diff > 0 else '⚪'
                ret_arrow = '🟢' if ret_diff > 2 else '🔴' if ret_diff < -2 else '⚪'
                print(f'    {symbol} {period} CL:{b["max_consecutive_losses"]}→{v["max_consecutive_losses"]}({cl_diff:+d}){cl_arrow}  DD:{b["max_drawdown_pct"]:.1f}%→{v["max_drawdown_pct"]:.1f}%({dd_diff:+.1f}%){dd_arrow}  Ret:{b["net_return_pct"]:+.1f}%→{v["net_return_pct"]:+.1f}%({ret_diff:+.1f}%){ret_arrow}  PF:{b["profit_factor"]:.3f}→{v["profit_factor"]:.3f}({pf_diff:+.3f})')
    
    # Save
    output_path = Path(__file__).parent / 'runs' / 'atr_filter_validation.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump({k: v for k, v in results.items()}, f, indent=2, default=str)
    print(f'\nResults saved to: {output_path}')


if __name__ == '__main__':
    main()