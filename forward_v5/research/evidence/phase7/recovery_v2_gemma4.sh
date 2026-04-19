#!/bin/bash
# Phase 7 Recovery Script v2 - Gemma4:31b
# Datum: 2026-04-18
# Modell: gemma4:31b-cloud (Port 32770)
# Ziel: research/evidence/phase7/

set -e

EVIDENCE_DIR="/data/.openclaw/workspace/forward_v5/forward_v5/research/evidence/phase7"
WORKDIR="/data/.openclaw/workspace/forward_v5/forward_v5"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
API_URL="http://172.17.0.1:32770/v1/chat/completions"
MODEL="gemma4:31b-cloud"

# Verzeichnis erstellen
mkdir -p "$EVIDENCE_DIR"

echo "╔════════════════════════════════════════════════════════╗"
echo "║  Phase 7 Recovery Script v2 (Gemma4:31b)              ║"
echo "║  Timestamp: $TIMESTAMP                               ║"
echo "║  Evidence Dir: $EVIDENCE_DIR                          ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

cd "$WORKDIR"

# ════════════════════════════════════════════════════════
# 1. KI-End-to-End-Test mit Gemma4
# ════════════════════════════════════════════════════════
echo "[1/8] Gemma4 End-to-End Analyse (mean_reversion_panic)..."

python3 -c "
import json, sys, time, ssl
from urllib.request import Request, urlopen
from datetime import datetime

# Scorecard laden
with open('research/research/scorecards/scorecard_mean_reversion_panic.json') as f:
    scorecard = json.load(f)

# Kompakte Scorecard
bt = scorecard.get('backtest_results', {})
compact = {
    'strategy': scorecard.get('strategy_name'),
    'hypothesis': scorecard.get('hypothesis', '')[:150],
    'results': {
        'net_return': bt.get('net_return'),
        'max_drawdown': bt.get('max_drawdown'),
        'profit_factor': bt.get('profit_factor'),
        'win_rate': bt.get('win_rate'),
        'trade_count': bt.get('trade_count')
    },
    'verdict': scorecard.get('verdict')
}

prompt = f'''Du bist der Strategy Lab Analyst. Analysiere diese Scorecard:

{json.dumps(compact, indent=2, ensure_ascii=False)}

Gib JSON zurück mit: verdict, confidence, reason, weaknesses, hypotheses_next.'''

payload = {
    'model': 'gemma4:31b-cloud',
    'messages': [
        {'role': 'system', 'content': 'Du bist ein quantitativer Trading-Analyst. Antworte nur mit validem JSON.'},
        {'role': 'user', 'content': prompt}
    ],
    'temperature': 0.2,
    'max_tokens': 1000
}

headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ollama-cloud'}
start = time.time()

try:
    data = json.dumps(payload).encode('utf-8')
    req = Request('http://172.17.0.1:32770/v1/chat/completions', data=data, headers=headers, method='POST')
    ctx = ssl.create_default_context()
    with urlopen(req, timeout=60, context=ctx) as resp:
        raw = resp.read().decode('utf-8')
        result = json.loads(raw)
        elapsed = int((time.time() - start) * 1000)
        
        content = ''
        if 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0].get('message', {}).get('content', '')
        
        # JSON aus Content extrahieren
        parsed = content
        if 'json' in content:
            import re
            match = re.search(r'\`\`\`json\s*(.*?)\s*\`\`\`', content, re.DOTALL)
            if match:
                parsed = match.group(1)
        
        output = {
            'analyzed_at': datetime.now().isoformat(),
            'scorecard_file': 'scorecard_mean_reversion_panic.json',
            'strategy_name': scorecard.get('strategy_name'),
            'analyst_model': 'gemma4:31b-cloud',
            'api_url': 'http://172.17.0.1:32770/v1/chat/completions',
            'execution_time_ms': elapsed,
            'raw_response': content,
            'parsed_analysis': parsed
        }
        
        # Speichere E2E Evidence
        with open('$EVIDENCE_DIR/kimi_e2e_stdout_${TIMESTAMP}.log', 'w') as f:
            f.write(f'=== Gemma4 E2E Analysis ===\n')
            f.write(f'Model: gemma4:31b-cloud\n')
            f.write(f'Elapsed: {elapsed}ms\n')
            f.write(f'Status: SUCCESS\n\n')
            f.write(content)
        
        with open('$EVIDENCE_DIR/meta_analysis_gemma4_${TIMESTAMP}.json', 'w') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f'  SUCCESS: {elapsed}ms, content length: {len(content)} chars')
        
except Exception as e:
    elapsed = int((time.time() - start) * 1000)
    with open('$EVIDENCE_DIR/kimi_e2e_stderr_${TIMESTAMP}.log', 'w') as f:
        f.write(f'=== Gemma4 E2E Analysis FAILED ===\n')
        f.write(f'Error: {e}\n')
        f.write(f'Elapsed: {elapsed}ms\n')
    print(f'  FAILED: {e}')

echo ""

# ════════════════════════════════════════════════════════
# 2-4. Stabilitätstests: 3 Strategien × 3 Runs
# ════════════════════════════════════════════════════════

STRATEGIES=("trend_pullback" "mean_reversion_panic" "multi_asset_selector")
RUNS=3
TOTAL=$((${#STRATEGIES[@]} * $RUNS))
CURRENT=2

for STRATEGY in "${STRATEGIES[@]}"; do
    for RUN in $(seq 1 $RUNS); do
        echo "[$CURRENT/8] ${STRATEGY} Run ${RUN}..."
        
        python3 research/run_demo_strategy.py "$STRATEGY" \
            1> "$EVIDENCE_DIR/${STRATEGY}_run${RUN}_${TIMESTAMP}.log" \
            2> "$EVIDENCE_DIR/${STRATEGY}_run${RUN}_stderr_${TIMESTAMP}.log" || true
        
        CURRENT=$((CURRENT + 1))
    done
done

echo ""

# ════════════════════════════════════════════════════════
# 5. Guardrail: >50 Kombinationen
# ════════════════════════════════════════════════════════
echo "[5/8] Guardrail: MAX_COMBINATIONS >50..."

python3 -c "
import sys
sys.path.insert(0, 'research')
from backtest.parameter_sweep import ParameterSweep
param_grid = {'ema': list(range(10, 100, 10)), 'rsi': list(range(10, 100, 10))}
sweep = ParameterSweep(None)
try:
    sweep.sweep(param_grid)
except ValueError as e:
    print(f'GUARDRAIL TRIGGERED: {e}')
" 1> "$EVIDENCE_DIR/guardrail_max_combinations_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/guardrail_max_combinations_stderr_${TIMESTAMP}.log" || true

echo ""

# ════════════════════════════════════════════════════════
# 6. Guardrail: >3 Assets
# ════════════════════════════════════════════════════════
echo "[6/8] Guardrail: MAX_ASSETS >3..."

python3 -c "
import sys
sys.path.insert(0, 'research/strategy_lab')
from multi_asset_selector import *
import polars as pl
import numpy as np

df = pl.DataFrame({
    'timestamp': range(100),
    'BTCUSDT': np.random.randn(100).cumsum(),
    'ETHUSDT': np.random.randn(100).cumsum(),
    'SOLUSDT': np.random.randn(100).cumsum(),
    'ADAUSDT': np.random.randn(100).cumsum()
})
try:
    result = calculate_signals(df, ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT'])
    print(f'ERROR: Guardrail NOT triggered, got result')
except ValueError as e:
    print(f'GUARDRAIL TRIGGERED: {e}')
except Exception as e:
    print(f'EXCEPTION: {type(e).__name__}: {e}')
" 1> "$EVIDENCE_DIR/guardrail_max_assets_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/guardrail_max_assets_stderr_${TIMESTAMP}.log" || true

echo ""

# ════════════════════════════════════════════════════════
# 7. Fallback: fehlender API-Key
# ════════════════════════════════════════════════════════
echo "[7/8] Fallback: Missing API-Key..."

OLLAMA_API_KEY="" \
OLLAMA_MODEL="gemma4:31b-cloud" \
OLLAMA_API_URL="http://172.17.0.1:32770/v1/chat/completions" \
python3 research/analyst.py --scorecard research/research/scorecards/scorecard_mean_reversion_panic.json \
  --output "$EVIDENCE_DIR/fallback_missing_api_key_${TIMESTAMP}.json" \
  1> "$EVIDENCE_DIR/fallback_missing_api_key_stdout_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/fallback_missing_api_key_stderr_${TIMESTAMP}.log" || true

echo ""

# ════════════════════════════════════════════════════════
# 8. Negativtest: ungültige Scorecard
# ════════════════════════════════════════════════════════
echo "[8/8] Negativtest: Invalid Scorecard..."

python3 research/analyst.py --scorecard does_not_exist.json \
  --output "$EVIDENCE_DIR/parser_failure_${TIMESTAMP}.json" \
  1> "$EVIDENCE_DIR/parser_failure_stdout_${TIMESTAMP}.log" \
  2> "$EVIDENCE_DIR/parser_failure_stderr_${TIMESTAMP}.log" || true

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║  Recovery Complete                                     ║"
echo "║  Timestamp: $TIMESTAMP                                ║"
echo "║  Model: gemma4:31b-cloud                               ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "Erzeugte Artefakte:"
ls -la "$EVIDENCE_DIR/" | grep "$TIMESTAMP"