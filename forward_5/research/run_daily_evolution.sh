#!/bin/bash
# Foundry Evolution V4 — Daily Run + Walk-Forward Gate
# Runs at 4:30 AM Berlin time, reports to Discord
# Learns from previous runs (Hall of Fame)
# NEW: Walk-Forward gate for any candidate that beats V17

set -euo pipefail

RESEARCH_DIR="/data/.openclaw/workspace/forward_v5/forward_5/research"
LOG_DIR="$RESEARCH_DIR/runs/evolution_v4"
DATE=$(date +%Y-%m-%d)
LOG="$LOG_DIR/daily_${DATE}.log"

echo "======================================================================" | tee -a "$LOG"
echo "FOUNDRY EVOLUTION V4 — Daily Run $DATE" | tee -a "$LOG"
echo "======================================================================" | tee -a "$LOG"

cd "$RESEARCH_DIR"

# Step 1: Run evolution
PYTHONUNBUFFERED=1 python3 -u run_evolution_v4.py --iterations 10 --candidates 3 2>&1 | tee -a "$LOG"

EXIT_CODE=${PIPESTATUS[0]:-0}

    # Step 2: Walk-Forward Gate — validate ALL HOF candidates (not just V17-beaters)
# A strategy with lower IS but WF-pass is MORE robust than V17 with IS=4.88 but WF-failed
echo "" | tee -a "$LOG"
echo "======================================================================" | tee -a "$LOG"
echo "WALK-FORWARD GATE — Validating ALL HOF candidates" | tee -a "$LOG"
echo "======================================================================" | tee -a "$LOG"

HOF_FILE="$LOG_DIR/evolution_v4_results.json"
WF_LOG="$LOG_DIR/wf_gate_${DATE}.log"

if [ -f "$HOF_FILE" ]; then
    python3 -u walk_forward_gate.py --hof "$HOF_FILE" --windows 5 2>&1 | tee -a "$WF_LOG"
else
    echo "⚠️  No HOF file found, skipping WF gate" | tee -a "$LOG"
fi

# Step 3: Generate report JSON for the agent
python3 -c "
import json

RESULTS_FILE = '$LOG_DIR/evolution_v4_results.json'
WF_FILE = None
REPORT_FILE = '$LOG_DIR/daily_${DATE}_report.json'

# Find latest WF gate file
from pathlib import Path
wf_files = sorted(Path('$LOG_DIR').parent.glob('runs/walk_forward/wf_gate_*.json'))
if wf_files:
    WF_FILE = str(wf_files[-1])

try:
    with open(RESULTS_FILE) as f:
        data = json.load(f)
    hof = data.get('hall_of_fame', [])
    v17_score = 4.88
    total = len(data.get('results', []))

    report = {
        'date': '$DATE',
        'total_candidates': total,
        'hof_count': len(hof),
        'v17_score': v17_score,
        'top': []
    }

    for r in hof[:5]:
        report['top'].append({
            'name': r['name'],
            'score': r['score'],
            'avg_return': r['avg_return'],
            'avg_dd': r['avg_dd'],
            'max_cl': r['max_cl'],
            'profitable_assets': r['profitable_assets']
        })

    if hof:
        report['best_score'] = hof[0]['score']
        report['gap'] = round(v17_score - hof[0]['score'], 2)
        report['new_champion'] = hof[0]['score'] > v17_score

    # V17 WF status
    report['v17_wf_status'] = 'FAILED'

    # Add Walk-Forward results if available
    if WF_FILE:
        try:
            with open(WF_FILE) as f:
                wf_data = json.load(f)
            report['walk_forward'] = {
                'results': [{
                    'name': r['name'],
                    'passed': r['passed'],
                    'robustness': r['robustness_score'],
                    'avg_oos_return': r['avg_oos_return'],
                    'profitable_assets': r['profitable_assets'],
                } for r in wf_data.get('results', [])]
            }
        except Exception:
            report['walk_forward'] = 'error'

    with open(REPORT_FILE, 'w') as f:
        json.dump(report, f, indent=2)

    print(f'Report saved to {REPORT_FILE}')

except Exception as e:
    print(f'Error generating report: {e}')
" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "Daily run complete. Exit code: $EXIT_CODE" | tee -a "$LOG"