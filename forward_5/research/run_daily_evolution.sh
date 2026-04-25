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

# Generate and send Discord report
python3 -c "
import json, subprocess

RESULTS_FILE = '$LOG_DIR/evolution_v4_results.json'

try:
    with open(RESULTS_FILE) as f:
        data = json.load(f)
    hof = data.get('hall_of_fame', [])
    v17_score = 4.88
    total = len(data.get('results', []))
    lines = ['🏭 **Foundry V4 Daily Report**', '']
    lines.append(f'Kandidaten: {total} | Hall of Fame: {len(hof)}')
    lines.append(f'V17 Benchmark: Score {v17_score:.2f}')
    if hof:
        for i, r in enumerate(hof[:5]):
            vs = '🏆' if r['score'] > v17_score else '  '
            lines.append(f\"{i+1}. \`{r['name'][:35]}\` Score={r['score']:.2f} R={r['avg_return']:+.1f}% DD={r['avg_dd']:.1f}% CL={r['max_cl']} Profit={r['profitable_assets']} {vs}\")
        best = hof[0]['score']
        if best > v17_score:
            lines.append('')
            lines.append(f'🎉 **NEW CHAMPION beats V17!** Score {best:.2f} > {v17_score:.2f}')
        else:
            lines.append(f'V17 leads by {v17_score - best:.2f} points (V17: {v17_score:.2f} vs best: {best:.2f})')
    else:
        lines.append('❌ No positive scores')
    report = '\n'.join(lines)
    print(report)
    subprocess.run(['openclaw', 'message', 'send', '--channel', 'discord', '--target', '1476565086708695104', report], timeout=30)
except Exception as e:
    print(f'⚠️ Discord report failed: {e}')
" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "Daily run complete. Exit code: $EXIT_CODE" | tee -a "$LOG"