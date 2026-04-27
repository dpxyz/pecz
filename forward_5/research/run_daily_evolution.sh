#!/bin/bash
# Foundry Evolution V8 — Multi-Strategy Daily Run
# 5 Strategy Types: MR, Trend, Momentum, Volume-Boosted, Regime
# Extended DSL: Stochastic, Williams %R, ATR, ROC, MACD, ADX, Volume
# Gradient IS-Score (negative = losing but comparable)
# Runs at 4:30 AM Berlin time

set -euo pipefail

RESEARCH_DIR="/data/.openclaw/workspace/forward_v5/forward_5/research"
LOG_DIR="$RESEARCH_DIR/runs/evolution_v7"
DATE=$(date +%Y-%m-%d)
LOG="$LOG_DIR/daily_${DATE}.log"

mkdir -p "$LOG_DIR"

echo "======================================================================" | tee -a "$LOG"
echo "FOUNDRY EVOLUTION V8 — Multi-Strategy Daily Run $DATE" | tee -a "$LOG"
echo "======================================================================" | tee -a "$LOG"

cd "$RESEARCH_DIR"

# Run V8
PYTHONUNBUFFERED=1 python3 -u run_evolution_v8.py 2>&1 | tee -a "$LOG"

EXIT_CODE=${PIPESTATUS[0]:-0}

# Generate report
python3 -c "
import json
from pathlib import Path

LOG_DIR = '$LOG_DIR'
REPORT_FILE = '$LOG_DIR/daily_${DATE}_report.json'

v8_files = sorted(Path(LOG_DIR).glob('evolution_v7_results_*.json'))

try:
    if v8_files:
        with open(v8_files[-1]) as f:
            data = json.load(f)
        
        report = {
            'date': '$DATE',
            'version': 'V8_multi_strategy',
            'phase1_evaluated': data.get('phase1_evaluated', 0),
            'phase1_passed': data.get('phase1_passed', 0),
            'phase2_evaluated': data.get('phase2_evaluated', 0),
            'phase2_passed': data.get('phase2_passed', 0),
            'hof_size': data.get('hof_size', 0),
            'champion': data.get('champion'),
            'type_stats': data.get('type_stats', {}),
            'hof_top5': data.get('hof_top5', []),
        }
    else:
        report = {'date': '$DATE', 'error': 'No results file found'}
    
    with open(REPORT_FILE, 'w') as f:
        json.dump(report, f, indent=2)
    print(f'Report saved to {REPORT_FILE}')
except Exception as e:
    print(f'Error generating report: {e}')
" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "Daily run complete. Exit code: $EXIT_CODE" | tee -a "$LOG"