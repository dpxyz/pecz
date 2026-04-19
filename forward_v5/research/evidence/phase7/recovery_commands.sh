#!/bin/bash
# Phase 7 Recovery Commands - Ausführung zur Wiederherstellung fehlender Rohbelege
# Datum: 2026-04-18
# Ziel: research/evidence/phase7/

set -e

EVIDENCE_DIR="/data/.openclaw/workspace/forward_v5/forward_v5/research/evidence/phase7"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Verzeichnis erstellen
mkdir -p "$EVIDENCE_DIR"

echo "=== Phase 7 Recovery Script ==="
echo "Timestamp: $TIMESTAMP"
echo "Evidence Dir: $EVIDENCE_DIR"
echo ""

# 1. Kimi-End-to-End-Test (mit API-Key)
echo "[1/11] Kimi End-to-End Test..."
python research/analyst.py research/scorecards/scorecard_mean_reversion_panic.json \
  1> "$EVIDENCE_DIR/kimi_e2e_stdout_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/kimi_e2e_stderr_${TIMESTAMP}.log" || true

# 2. trend_pullback Run 1
echo "[2/11] trend_pullback Run 1..."
python research/run_demo_strategy.py trend_pullback \
  1> "$EVIDENCE_DIR/trend_pullback_run1_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/trend_pullback_run1_stderr_${TIMESTAMP}.log" || true

# 3. trend_pullback Run 2
echo "[3/11] trend_pullback Run 2..."
python research/run_demo_strategy.py trend_pullback \
  1> "$EVIDENCE_DIR/trend_pullback_run2_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/trend_pullback_run2_stderr_${TIMESTAMP}.log" || true

# 4. trend_pullback Run 3
echo "[4/11] trend_pullback Run 3..."
python research/run_demo_strategy.py trend_pullback \
  1> "$EVIDENCE_DIR/trend_pullback_run3_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/trend_pullback_run3_stderr_${TIMESTAMP}.log" || true

# 5. mean_reversion_panic Run 1
echo "[5/11] mean_reversion_panic Run 1..."
python research/run_demo_strategy.py mean_reversion_panic \
  1> "$EVIDENCE_DIR/mean_reversion_panic_run1_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/mean_reversion_panic_run1_stderr_${TIMESTAMP}.log" || true

# 6. mean_reversion_panic Run 2
echo "[6/11] mean_reversion_panic Run 2..."
python research/run_demo_strategy.py mean_reversion_panic \
  1> "$EVIDENCE_DIR/mean_reversion_panic_run2_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/mean_reversion_panic_run2_stderr_${TIMESTAMP}.log" || true

# 7. mean_reversion_panic Run 3
echo "[7/11] mean_reversion_panic Run 3..."
python research/run_demo_strategy.py mean_reversion_panic \
  1> "$EVIDENCE_DIR/mean_reversion_panic_run3_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/mean_reversion_panic_run3_stderr_${TIMESTAMP}.log" || true

# 8. multi_asset_selector Run 1
echo "[8/11] multi_asset_selector Run 1..."
python research/run_demo_strategy.py multi_asset_selector \
  1> "$EVIDENCE_DIR/multi_asset_selector_run1_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/multi_asset_selector_run1_stderr_${TIMESTAMP}.log" || true

# 9. multi_asset_selector Run 2
echo "[9/11] multi_asset_selector Run 2..."
python research/run_demo_strategy.py multi_asset_selector \
  1> "$EVIDENCE_DIR/multi_asset_selector_run2_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/multi_asset_selector_run2_stderr_${TIMESTAMP}.log" || true

# 10. multi_asset_selector Run 3
echo "[10/11] multi_asset_selector Run 3..."
python research/run_demo_strategy.py multi_asset_selector \
  1> "$EVIDENCE_DIR/multi_asset_selector_run3_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/multi_asset_selector_run3_stderr_${TIMESTAMP}.log" || true

# 11. Guardrail-Tests
echo "[11/11] Guardrail Tests..."

# 11a. MAX_COMBINATIONS Fehler (simuliert via Parameter-Sweep)
python -c "
import sys
sys.path.insert(0, 'research')
from backtest.parameter_sweep import ParameterSweep
# 81 Kombinationen erzeugen (9x9 > 50)
param_grid = {'ema': list(range(10, 100, 10)), 'rsi': list(range(10, 100, 10))}
sweep = ParameterSweep(None)
sweep.sweep(param_grid)
" 2> "$EVIDENCE_DIR/guardrail_max_combinations_${TIMESTAMP}.log" || true

# 11b. MAX_ASSETS Fehler
python -c "
import sys
sys.path.insert(0, 'research/strategy_lab')
from multi_asset_selector import calculate_signals
import polars as pl
import numpy as np
# 4 Assets simulieren (BTC, ETH, SOL, AVAX)
df = pl.DataFrame({
    'timestamp': range(100),
    'BTC': np.random.randn(100),
    'ETH': np.random.randn(100),
    'SOL': np.random.randn(100),
    'AVAX': np.random.randn(100)
})
try:
    calculate_signals(df, ['BTC', 'ETH', 'SOL', 'AVAX'])
except ValueError as e:
    print(f'Guardrail triggered: {e}')
" 2> "$EVIDENCE_DIR/guardrail_max_assets_${TIMESTAMP}.log" || true

# 11c. Fehlender API-Key (Fallback)
OLLAMA_API_KEY="" python research/analyst.py research/scorecards/scorecard_mean_reversion_panic.json \
  1> "$EVIDENCE_DIR/fallback_missing_api_key_stdout_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/fallback_missing_api_key_stderr_${TIMESTAMP}.log" || true

# 11d. Ungültige Scorecard
python research/analyst.py does_not_exist.json \
  1> "$EVIDENCE_DIR/parser_failure_stdout_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/parser_failure_stderr_${TIMESTAMP}.log" || true

echo ""
echo "=== Recovery Complete ==="
echo "Alle Artefakte gespeichert in: $EVIDENCE_DIR"
echo "Timestamp: $TIMESTAMP"
ls -la "$EVIDENCE_DIR/"
