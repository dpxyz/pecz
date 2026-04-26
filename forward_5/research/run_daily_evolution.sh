#!/bin/bash
# Foundry Evolution V5 — Daily Run + Walk-Forward Gate
# Runs at 4:30 AM Berlin time, reports to Discord
# V5: Mean Reversion focus, V32 (WF-champion) as seed, WF feedback in prompt
# Learns from previous runs (Hall of Fame)

set -euo pipefail

RESEARCH_DIR="/data/.openclaw/workspace/forward_v5/forward_5/research"
LOG_DIR="$RESEARCH_DIR/runs/evolution_v5"
DATE=$(date +%Y-%m-%d)
LOG="$LOG_DIR/daily_${DATE}.log"

mkdir -p "$LOG_DIR"

echo "======================================================================" | tee -a "$LOG"
echo "FOUNDRY EVOLUTION V5 — Daily Run $DATE" | tee -a "$LOG"
echo "======================================================================" | tee -a "$LOG"

cd "$RESEARCH_DIR"

# Step 1: Run evolution (V5 = Mean Reversion, temp 0.3, 15 iterations)
PYTHONUNBUFFERED=1 python3 -u run_evolution_v5.py --iterations 15 --candidates 3 2>&1 | tee -a "$LOG"

EXIT_CODE=${PIPESTATUS[0]:-0}

# Step 2: Walk-Forward Gate — validate ALL HOF candidates
# V32 (WF-champion, 88.3 robustness) is the benchmark to beat
echo "" | tee -a "$LOG"
echo "======================================================================" | tee -a "$LOG"
echo "WALK-FORWARD GATE — Validating ALL HOF candidates" | tee -a "$LOG"
echo "======================================================================" | tee -a "$LOG"

HOF_FILE="$LOG_DIR/evolution_v5_results.json"
WF_LOG_DIR="$RESEARCH_DIR/runs/walk_forward"
mkdir -p "$WF_LOG_DIR"
WF_LOG="$WF_LOG_DIR/wf_gate_${DATE}.log"

if [ -f "$HOF_FILE" ]; then
    python3 -u walk_forward_gate.py --hof "$HOF_FILE" --windows 5 2>&1 | tee -a "$WF_LOG"
else
    echo "⚠️  No HOF file found, skipping WF gate" | tee -a "$LOG"
fi

# Step 3: Generate report JSON for the agent
python3 -c "
import json
from pathlib import Path

RESULTS_FILE = '$LOG_DIR/evolution_v5_results.json'
WF_DIR = '$WF_LOG_DIR'
REPORT_FILE = '$LOG_DIR/daily_${DATE}_report.json'

# Find latest WF gate file
wf_files = sorted(Path(WF_DIR).glob('wf_gate_*.json'))
WF_FILE = str(wf_files[-1]) if wf_files else None

try:
    with open(RESULTS_FILE) as f:
        data = json.load(f)
    hof = data.get('hall_of_fame', [])
    total = len(data.get('results', []))

    # Find current champion (best WF robustness from WF results)
    champion = {'name': 'V32_MR_BB_FAST_RSI_EMA50', 'wf_robustness': 88.3, 'is_score': 1.28}

    report = {
        'date': '$DATE',
        'total_candidates': total,
        'hof_count': len(hof),
        'champion': champion,
        'top': []
    }

    for r in hof[:5]:
        report['top'].append({
            'name': r['name'],
            'score': r.get('score', 0),
            'avg_return': r.get('avg_return', 0),
            'avg_dd': r.get('avg_dd', 0),
            'max_cl': r.get('max_cl', 0),
            'profitable_assets': r.get('profitable_assets', '?'),
            'entry_condition': r.get('entry_condition', '?'),
        })

    # Add Walk-Forward results if available
    wf_passed = 0
    wf_new_champion = None
    if WF_FILE:
        try:
            with open(WF_FILE) as f:
                wf_data = json.load(f)
            wf_results = []
            for r in wf_data.get('results', []):
                entry = {
                    'name': r['name'],
                    'passed': r['passed'],
                    'robustness': r['robustness_score'],
                    'avg_oos_return': r['avg_oos_return'],
                    'profitable_assets': r['profitable_assets'],
                    'tier': r.get('tier', '?'),
                    'is_score': r.get('is_score', 0),
                }
                wf_results.append(entry)
                if r['passed'] and r['robustness_score'] > champion['wf_robustness']:
                    wf_new_champion = entry
                if r['passed']:
                    wf_passed += 1
            report['walk_forward'] = {'results': wf_results, 'passed': wf_passed}
            report['wf_new_champion'] = wf_new_champion
        except Exception as e:
            report['walk_forward'] = f'error: {e}'

    with open(REPORT_FILE, 'w') as f:
        json.dump(report, f, indent=2)

    print(f'Report saved to {REPORT_FILE}')
    if wf_new_champion:
        print(f'🎉 NEW WF-CHAMPION: {wf_new_champion[\"name\"]} (Robustness {wf_new_champion[\"robustness\"]})')
    else:
        print(f'No new WF-champion. Current: V32 (88.3)')

except Exception as e:
    print(f'Error generating report: {e}')
" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "Daily run complete. Exit code: $EXIT_CODE" | tee -a "$LOG"