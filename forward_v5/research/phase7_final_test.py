#!/usr/bin/env python3
"""
Phase 7 Final Test Suite
Umfassende Tests für Strategy Lab + Kimi Integration
"""

import subprocess
import sys
import time
import json
import os
from pathlib import Path

# Test-Konfiguration
STRATEGIES = ['trend_pullback', 'mean_reversion_panic', 'multi_asset_selector']
REPEAT_COUNT = 3
STRESS_COUNT = 10

def run_strategy(strategy_name, iteration=1):
    """Führe eine Strategie aus und sammle Metriken"""
    print(f"\n{'='*60}")
    print(f"Testing: {strategy_name} (Run {iteration})")
    print('='*60)
    
    start_time = time.time()
    
    result = subprocess.run(
        [sys.executable, 'run_demo_strategy.py', '--strategy', strategy_name],
        capture_output=True,
        text=True,
        timeout=300
    )
    
    elapsed = time.time() - start_time
    
    # Parse Output
    output = result.stdout
    stderr = result.stderr
    
    print(f"Exit Code: {result.returncode}")
    print(f"Laufzeit: {elapsed:.3f}s")
    
    # Extrahiere Metriken aus Output
    metrics = {
        'strategy': strategy_name,
        'iteration': iteration,
        'exit_code': result.returncode,
        'runtime_seconds': elapsed,
        'total_combinations': None,
        'completed': None,
        'failed': None,
        'verdict': None,
        'net_return': None,
        'max_drawdown': None,
        'trade_count': None,
        'execution_time_ms': None,
        'memory_peak_mb': None
    }
    
    # Parse aus Output
    for line in output.split('\n'):
        if 'Total:' in line and 'combinations' in line:
            try:
                metrics['total_combinations'] = int(line.split('Total:')[1].split()[0])
            except:
                pass
        if 'Completed:' in line:
            try:
                metrics['completed'] = int(line.split('Completed:')[1].split()[0])
            except:
                pass
        if 'Failed:' in line:
            try:
                metrics['failed'] = int(line.split('Failed:')[1].split()[0])
            except:
                pass
        if 'Verdict:' in line and 'FAIL' in line:
            metrics['verdict'] = 'FAIL'
        if 'Verdict:' in line and 'PASS' in line:
            metrics['verdict'] = 'PASS'
        if 'Return:' in line and '%' in line:
            try:
                metrics['net_return'] = float(line.split('Return:')[1].split('%')[0])
            except:
                pass
        if 'Drawdown:' in line and '%' in line:
            try:
                metrics['max_drawdown'] = float(line.split('Drawdown:')[1].split('%')[0])
            except:
                pass
        if 'Trades:' in line and 'Next Actions' not in line:
            try:
                metrics['trade_count'] = int(line.split('Trades:')[1].split()[0])
            except:
                pass
    
    # Lese Scorecard für detaillierte Metriken
    scorecard_path = Path(f'research/scorecards/scorecard_{strategy_name}.json')
    if scorecard_path.exists():
        try:
            with open(scorecard_path) as f:
                sc = json.load(f)
                if 'backtest_results' in sc and 'resource_usage' in sc['backtest_results']:
                    ru = sc['backtest_results']['resource_usage']
                    metrics['execution_time_ms'] = ru.get('execution_time_ms')
                    metrics['memory_peak_mb'] = ru.get('memory_peak_mb')
        except Exception as e:
            print(f"  ⚠️  Scorecard-Lesefehler: {e}")
    
    # Zeige Ergebnis
    print(f"Kombinationen: {metrics['total_combinations']} (Completed: {metrics['completed']}, Failed: {metrics['failed']})")
    print(f"Verdict: {metrics['verdict']}")
    if metrics['net_return'] is not None:
        print(f"Return: {metrics['net_return']:.2f}%")
    if metrics['max_drawdown'] is not None:
        print(f"Drawdown: {metrics['max_drawdown']:.2f}%")
    if metrics['trade_count'] is not None:
        print(f"Trades: {metrics['trade_count']}")
    if metrics['execution_time_ms'] is not None:
        print(f"execution_time_ms: {metrics['execution_time_ms']}")
    if metrics['memory_peak_mb'] is not None:
        print(f"memory_peak_mb: {metrics['memory_peak_mb']}")
    
    return metrics, output, stderr

def run_guardrail_tests():
    """Teste Guardrails und Fehlerfälle"""
    print(f"\n{'='*60}")
    print("GUARDRAIL TESTS")
    print('='*60)
    
    results = []
    
    # Test 1: Parameter-Sweep >50 Kombinationen
    print("\n[Guardrail] MAX_COMBINATIONS=50 Test...")
    try:
        sys.path.insert(0, 'backtest')
        from backtest.backtest_engine import BacktestEngine
        from parameter_sweep import ParameterSweep
        
        engine = BacktestEngine(data_path='data')
        
        # Grid mit 81 Kombinationen (>50)
        param_grid = {
            'a': [1, 2, 3],
            'b': [1, 2, 3],
            'c': [1, 2, 3],
            'd': [1, 2, 3]
        }
        
        try:
            sweep = ParameterSweep(
                engine=engine,
                strategy_name='test',
                strategy_func=lambda df, p: df,
                param_grid=param_grid
            )
            print("  ❌ FAIL: Sollte ValueError werfen")
            results.append(('MAX_COMBINATIONS', 'FAIL', 'Kein Error bei 81 Kombos'))
        except ValueError as e:
            if '50' in str(e):
                print(f"  ✅ PASS: Guardrail aktiv - {e}")
                results.append(('MAX_COMBINATIONS', 'PASS', str(e)))
            else:
                print(f"  ⚠️  UNEXPECTED: {e}")
                results.append(('MAX_COMBINATIONS', 'UNCLEAR', str(e)))
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        results.append(('MAX_COMBINATIONS', 'ERROR', str(e)))
    
    # Test 2: Multi-Asset >3 Assets
    print("\n[Guardrail] Multi-Asset >3 Assets Test...")
    try:
        sys.path.insert(0, 'strategy_lab')
        import polars as pl
        from multi_asset_selector import multi_asset_selector_strategy
        
        data_4 = {
            'BTC': pl.DataFrame({'close': [100.0, 101.0]}),
            'ETH': pl.DataFrame({'close': [100.0, 101.0]}),
            'SOL': pl.DataFrame({'close': [100.0, 101.0]}),
            'AVAX': pl.DataFrame({'close': [100.0, 101.0]}),
        }
        
        try:
            result = multi_asset_selector_strategy(data_4, {'n_top': 2})
            print("  ❌ FAIL: Sollte ValueError werfen")
            results.append(('MULTI_ASSET_LIMIT', 'FAIL', 'Kein Error bei 4 Assets'))
        except ValueError as e:
            if 'VPS Safety' in str(e) or '3' in str(e):
                print(f"  ✅ PASS: Guardrail aktiv - {e}")
                results.append(('MULTI_ASSET_LIMIT', 'PASS', str(e)))
            else:
                print(f"  ⚠️  UNEXPECTED: {e}")
                results.append(('MULTI_ASSET_LIMIT', 'UNCLEAR', str(e)))
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        results.append(('MULTI_ASSET_LIMIT', 'ERROR', str(e)))
    
    # Test 3: Ungültige Scorecard für Analyst
    print("\n[Failure Path] Ungültige Scorecard...")
    try:
        result = subprocess.run(
            [sys.executable, 'analyst.py', '--scorecard', 'nicht_existiert.json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0 and 'FileNotFound' in result.stderr:
            print("  ✅ PASS: Sauberer Fehler bei fehlender Datei")
            results.append(('INVALID_SCORECARD', 'PASS', 'Sauberer Fehler'))
        else:
            print(f"  ⚠️  UNEXPECTED: Exit={result.returncode}, stderr={result.stderr[:100]}")
            results.append(('INVALID_SCORECARD', 'UNCLEAR', result.stderr[:100]))
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        results.append(('INVALID_SCORECARD', 'ERROR', str(e)))
    
    # Test 4: Fehlender OLLAMA_API_KEY
    print("\n[Failure Path] Fehlender OLLAMA_API_KEY...")
    try:
        # Sichere env, dann lösche
        old_key = os.environ.get('OLLAMA_API_KEY')
        if 'OLLAMA_API_KEY' in os.environ:
            del os.environ['OLLAMA_API_KEY']
        
        # Erstelle eine valide Scorecard-Datei für den Test
        test_sc = {
            'strategy_name': 'test',
            'verdict': 'PASS',
            'backtest_results': {'net_return': 1.0, 'trade_count': 10}
        }
        test_path = Path('test_scorecard.json')
        with open(test_path, 'w') as f:
            json.dump(test_sc, f)
        
        result = subprocess.run(
            [sys.executable, 'analyst.py', '--scorecard', str(test_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Restore env
        if old_key:
            os.environ['OLLAMA_API_KEY'] = old_key
        test_path.unlink(missing_ok=True)
        
        if 'OLLAMA_API_KEY' in result.stdout or 'Fallback' in result.stdout:
            print("  ✅ PASS: Sauberer Fallback ohne API Key")
            results.append(('NO_API_KEY', 'PASS', 'Fallback aktiv'))
        else:
            print(f"  ⚠️  UNEXPECTED: {result.stdout[:200]}")
            results.append(('NO_API_KEY', 'UNCLEAR', result.stdout[:200]))
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        results.append(('NO_API_KEY', 'ERROR', str(e)))
    
    return results

def run_stress_test(strategy_name):
    """Belastungstest mit 10 Runs"""
    print(f"\n{'='*60}")
    print(f"STRESS TEST: {strategy_name} (10 Runs)")
    print('='*60)
    
    results = []
    start_total = time.time()
    
    for i in range(1, STRESS_COUNT + 1):
        print(f"  Run {i}/{STRESS_COUNT}...", end=' ', flush=True)
        try:
            metrics, _, _ = run_strategy(strategy_name, iteration=i)
            results.append(metrics)
            time.sleep(0.5)  # Kleine Pause
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({'error': str(e), 'iteration': i})
    
    total_time = time.time() - start_total
    
    # Statistik
    if results:
        runtimes = [r.get('runtime_seconds', 0) for r in results if 'runtime_seconds' in r]
        verdicts = [r.get('verdict') for r in results if 'verdict' in r]
        
        print(f"\n{'='*60}")
        print(f"STRESS TEST RESULTS - {strategy_name}")
        print('='*60)
        print(f"Gesamtdauer: {total_time:.2f}s")
        print(f"Durchschnitt: {sum(runtimes)/len(runtimes):.3f}s pro Run")
        print(f"Min: {min(runtimes):.3f}s, Max: {max(runtimes):.3f}s")
        print(f"Verdicts: {verdicts.count('PASS')} PASS, {verdicts.count('FAIL')} FAIL")
        print(f"Konsistent: {'JA' if len(set(verdicts)) == 1 else 'NEIN'} (alle gleich)")
    
    return results, total_time

def main():
    """Haupt-Test-Runner"""
    print("="*60)
    print("PHASE 7 FINAL TEST SUITE")
    print("="*60)
    print(f"Start: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Strategies: {STRATEGIES}")
    print(f"Repeats per strategy: {REPEAT_COUNT}")
    print(f"Stress runs: {STRESS_COUNT}")
    
    all_results = {}
    
    # TEIL A.1: Pflicht-Runs alle 3 Strategien (3x wiederholt)
    print("\n" + "="*60)
    print("TEIL A.1: Pflicht-Runs (3x pro Strategie)")
    print("="*60)
    
    for strategy in STRATEGIES:
        all_results[strategy] = []
        for i in range(1, REPEAT_COUNT + 1):
            metrics, output, stderr = run_strategy(strategy, i)
            all_results[strategy].append(metrics)
            time.sleep(1)  # Pause zwischen Runs
    
    # TEIL A.2: Guardrail Tests
    guardrail_results = run_guardrail_tests()
    all_results['guardrails'] = guardrail_results
    
    # TEIL A.3: Stress Tests (eine Strategie als Beispiel)
    stress_results, stress_time = run_stress_test('multi_asset_selector')
    all_results['stress_test'] = stress_results
    all_results['stress_total_time'] = stress_time
    
    # Speichere Ergebnisse
    report_path = Path('phase7_final_test_report.json')
    with open(report_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print(f"\n{'='*60}")
    print(f"Test Report gespeichert: {report_path}")
    print("="*60)
    
    # Finale Zusammenfassung
    print("\nFINALE ZUSAMMENFASSUNG")
    print("="*60)
    
    for strategy in STRATEGIES:
        runs = all_results[strategy]
        exit_codes = [r['exit_code'] for r in runs]
        verdicts = [r['verdict'] for r in runs if r['verdict']]
        
        print(f"\n{strategy}:")
        print(f"  Exit Codes: {exit_codes} (alle 0: {all(e == 0 for e in exit_codes)})")
        print(f"  Verdicts: {verdicts}")
        print(f"  Konsistent: {'JA' if len(set(str(v) for v in verdicts)) == 1 else 'VARIIERT'}")
    
    print(f"\nGuardrails: {sum(1 for r in guardrail_results if r[1] == 'PASS')}/{len(guardrail_results)} bestanden")
    print(f"Stress Test: {len(stress_results)} Runs in {stress_time:.2f}s")
    
    print("\n" + "="*60)
    print("TEIL A COMPLETE - Jetzt TEIL B: Kimi Parser Fix")
    print("="*60)

if __name__ == "__main__":
    main()
