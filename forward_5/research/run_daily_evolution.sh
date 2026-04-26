#!/bin/bash
# Foundry Evolution V7 — Three-Phase Daily Run
# Phase 1: Exploration (temp 0.3 + 0.7)
# Phase 2: Evolution (mutate + crossover HOF)
# Phase 3: Hard Check (10-window WF on top-3)
# Runs at 4:30 AM Berlin time

set -euo pipefail

RESEARCH_DIR="/data/.openclaw/workspace/forward_v5/forward_5/research"
LOG_DIR="$RESEARCH_DIR/runs/evolution_v7"
DATE=$(date +%Y-%m-%d)
LOG="$LOG_DIR/daily_${DATE}.log"

mkdir -p "$LOG_DIR"

echo "======================================================================" | tee -a "$LOG"
echo "FOUNDRY EVOLUTION V7 — Daily Run $DATE" | tee -a "$LOG"
echo "======================================================================" | tee -a "$LOG"

cd "$RESEARCH_DIR"

# Run V7
PYTHONUNBUFFERED=1 python3 -u run_evolution_v7.py 2>&1 | tee -a "$LOG"

EXIT_CODE=${PIPESTATUS[0]:-0}

# Generate report
python3 -c "
import json
from pathlib import Path

LOG_DIR = '$LOG_DIR'
REPORT_FILE = '$LOG_DIR/daily_${DATE}_report.json'

v7_files = sorted(Path(LOG_DIR).glob('evolution_v7_results_*.json'))

try:
    if v7_files:
        with open(v7_files[-1]) as f:
            data = json.load(f)
        
        hof = data.get('hof', [])
        champion = data.get('champion')
        
        report = {
            'date': '$DATE',
            'version': 'V7_three_phase',
            'phase1_evaluated': data.get('phase1_evaluated', 0),
            'phase1_passed': data.get('phase1_passed', 0),
            'phase2_evaluated': data.get('phase2_evaluated', 0),
            'phase2_passed': data.get('phase2_passed', 0),
            'hof_size': len(hof),
            'champion': champion,
            'hof_top5': [{
                'name': s.get('name', '?'),
                'wf_robustness': s.get('wf_robustness', 0),
                'wf_passed': s.get('wf_passed', False),
                'is_score': s.get('is_score', 0),
                'wf_robustness_10w': s.get('wf_robustness_10w'),
            } for s in hof[:5]],
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