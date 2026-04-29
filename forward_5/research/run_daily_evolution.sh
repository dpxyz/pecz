#!/bin/bash
# Foundry Evolution V9 — Oktopus Evolution Daily Run
# 6 Asset-Specific Arms: MR-ALT, MR-RELAXED, TREND-REGIME, SIGNAL-EXIT, VOL-BOOSTED, CROSS-ASSET
# Signal-Reversal Exits (no trailing stop), Entry-Only Mutations
# IS pre-filter: ≥3 trades/asset/window
# Runs at 4:30 AM Berlin time

set -euo pipefail

RESEARCH_DIR="/data/.openclaw/workspace/forward_v5/forward_5/research"
OLLAMA_API_URL="${OLLAMA_API_URL:-http://172.17.0.1:32771/v1/chat/completions}"
OLLAMA_API_KEY="${OLLAMA_API_KEY:-ollama-cloud}"
LOG_DIR="$RESEARCH_DIR/runs/evolution_v9"
DATE=$(date +%Y-%m-%d)
LOG="$LOG_DIR/daily_${DATE}.log"

mkdir -p "$LOG_DIR"

echo "======================================================================" | tee -a "$LOG"
echo "FOUNDRY EVOLUTION V9 — Oktopus Evolution Daily Run $DATE" | tee -a "$LOG"
echo "======================================================================" | tee -a "$LOG"

cd "$RESEARCH_DIR"

# Model selection: Try DeepSeek-V4-Pro first, fallback to Gemma4
SELECTED_MODEL=$(python3 "$RESEARCH_DIR/test_model.py" "$OLLAMA_API_URL" "$OLLAMA_API_KEY" 2>&1 | grep -E "^[a-z].*:cloud$" | head -1)

if [ -z "$SELECTED_MODEL" ]; then
    echo "❌ No model available! Aborting." | tee -a "$LOG"
    exit 1
fi

export GENERATOR_MODEL="$SELECTED_MODEL"

# Run V9
PYTHONUNBUFFERED=1 python3 -u run_evolution_v9.py 2>&1 | tee -a "$LOG"

EXIT_CODE=${PIPESTATUS[0]:-0}

# Generate report
python3 -c "
import json
from pathlib import Path

LOG_DIR = '$LOG_DIR'
REPORT_FILE = '$LOG_DIR/daily_${DATE}_report.json'

v9_files = sorted(Path(LOG_DIR).glob('evolution_v9_results_*.json'))

try:
    if v9_files:
        with open(v9_files[-1]) as f:
            data = json.load(f)
        
        # Build 10w champions ranked by OOS
        hof = data.get('hof', [])
        champs_10w = sorted(
            [h for h in hof if h.get('wf_passed_10w')],
            key=lambda h: h.get('avg_oos_return', -999),
            reverse=True
        )
        best_oos = champs_10w[0] if champs_10w else None
        
        report = {
            'date': '$DATE',
            'version': 'V9_oktopus',
            'phase1_evaluated': data.get('phase1_evaluated', 0),
            'phase1_passed': data.get('phase1_passed', 0),
            'phase2_evaluated': data.get('phase2_evaluated', 0),
            'phase2_passed': data.get('phase2_passed', 0),
            'hof_size': data.get('hof_size', 0),
            'champion': data.get('champion'),
            'best_oos_champion': {
                'name': best_oos['name'],
                'oos': best_oos.get('avg_oos_return', 0),
                'wf_10w': best_oos.get('wf_robustness_10w', 0),
                'profitable_10w': best_oos.get('wf_profitable_10w', '?'),
                'entry': best_oos['entry_condition'],
                'exit_condition': best_oos.get('exit_condition', ''),
            } if best_oos else None,
            'champions_10w_ranked': [{
                'name': c['name'],
                'oos': c.get('avg_oos_return', 0),
                'wf_10w': c.get('wf_robustness_10w', 0),
                'profitable_10w': c.get('wf_profitable_10w', '?'),
                'exit_condition': c.get('exit_condition', ''),
            } for c in champs_10w],
            'type_stats': data.get('type_stats', {}),
            'exit_type_stats': data.get('exit_type_stats', {}),
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