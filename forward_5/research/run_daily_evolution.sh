#!/bin/bash
# Foundry Evolution V4 — Daily Run
# Runs at 4:30 AM Berlin time, reports to Discord
# Learns from previous runs (Hall of Fame)

set -euo pipefail

RESEARCH_DIR="/data/.openclaw/workspace/forward_v5/forward_5/research"
LOG_DIR="$RESEARCH_DIR/runs/evolution_v4"
DATE=$(date +%Y-%m-%d)
LOG="$LOG_DIR/daily_${DATE}.log"

echo "======================================================================" | tee -a "$LOG"
echo "FOUNDRY EVOLUTION V4 — Daily Run $DATE" | tee -a "$LOG"
echo "======================================================================" | tee -a "$LOG"

cd "$RESEARCH_DIR"

# Run evolution with 10 iterations, 3 candidates
PYTHONUNBUFFERED=1 python3 -u run_evolution_v4.py --iterations 10 --candidates 3 2>&1 | tee -a "$LOG"

EXIT_CODE=${PIPESTATUS[0]:-0}

# Generate report JSON for the agent to send via message tool
# The agent (OpenClaw cron) will pick this up and format it properly
python3 -c "
import json

RESULTS_FILE = '$LOG_DIR/evolution_v4_results.json'
REPORT_FILE = '$LOG_DIR/daily_${DATE}_report.json'

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

    with open(REPORT_FILE, 'w') as f:
        json.dump(report, f, indent=2)

    print(f'Report saved to {REPORT_FILE}')

except Exception as e:
    print(f'Error generating report: {e}')
" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "Daily run complete. Exit code: $EXIT_CODE" | tee -a "$LOG"