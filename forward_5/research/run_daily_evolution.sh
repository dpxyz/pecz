#!/bin/bash
# Foundry Evolution V6 — Daily Run (True Evolutionary Algorithm)
# Fitness = WF Robustness, Elitism, Mutation + Crossover
# Runs at 4:30 AM Berlin time, reports to Discord

set -euo pipefail

RESEARCH_DIR="/data/.openclaw/workspace/forward_v5/forward_5/research"
LOG_DIR="$RESEARCH_DIR/runs/evolution_v6"
DATE=$(date +%Y-%m-%d)
LOG="$LOG_DIR/daily_${DATE}.log"

mkdir -p "$LOG_DIR"

echo "======================================================================" | tee -a "$LOG"
echo "FOUNDRY EVOLUTION V6 — Daily Run $DATE" | tee -a "$LOG"
echo "======================================================================" | tee -a "$LOG"

cd "$RESEARCH_DIR"

# Step 1: Run evolution (V6 = true evolutionary algorithm)
PYTHONUNBUFFERED=1 python3 -u run_evolution_v6.py 2>&1 | tee -a "$LOG"

EXIT_CODE=${PIPESTATUS[0]:-0}

# Step 2: Generate report JSON for the agent
python3 -c "
import json
from pathlib import Path

LOG_DIR = '$LOG_DIR'
REPORT_FILE = '$LOG_DIR/daily_${DATE}_report.json'

# Find latest V6 results file
v6_files = sorted(Path(LOG_DIR).glob('evolution_v6_results_*.json'))

try:
    if v6_files:
        with open(v6_files[-1]) as f:
            data = json.load(f)
        hof = data.get('hof', [])
        champion = data.get('champion', {})
        all_results = data.get('all_results', [])
        
        wf_passed = [r for r in all_results if r.get('wf_passed')]
        
        report = {
            'date': '$DATE',
            'version': 'V6_evolutionary',
            'generations': data.get('generations', '?'),
            'total_evaluated': len(all_results),
            'wf_passed_count': len(wf_passed),
            'champion': champion,
            'hof': hof[:10],
            'v32_wf_robustness': 88.3,
            'new_champion_beats_v32': champion.get('wf_robustness', 0) > 88.3 if champion else False,
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