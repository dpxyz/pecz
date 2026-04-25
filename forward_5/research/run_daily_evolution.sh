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

# Extract results for Discord report
python3 -c "
import json, sys

try:
    with open('$LOG_DIR/evolution_v4_results.json') as f:
        data = json.load(f)
    
    hof = data.get('hall_of_fame', [])
    v17_score = data.get('v17_benchmark', {}).get('score_v3', 4.88)
    total = len(data.get('results', []))
    
    lines = ['🏭 **Foundry V4 Daily Report** \`$DATE\`', '']
    lines.append(f'Kandidaten: {total} | Hall of Fame: {len(hof)}')
    lines.append(f'V17 Benchmark: Score {v17_score:.2f}')
    lines.append('')
    
    if hof:
        lines.append('**Top 5:**')
        for i, r in enumerate(hof[:5]):
            vs = '🏆' if r['score'] > v17_score else '  '
            lines.append(f'{i+1}. \`{r[\"name\"][:35]}\` Score={r[\"score\"]:.2f} R={r[\"avg_return\"]:+.1f}% DD={r[\"avg_dd\"]:.1f}% CL={r[\"max_cl\"]} Profit={r[\"profitable_assets\"]} {vs}')
    else:
        lines.append('❌ No positive scores')
    
    # Compare with V17
    best_score = hof[0]['score'] if hof else 0
    if best_score > v17_score:
        lines.append(f'')
        lines.append(f'🎉 **NEW CHAMPION beats V17!** Score {best_score:.2f} > {v17_score:.2f}')
    elif hof:
        lines.append(f'')
        lines.append(f'V17 still leads by {v17_score - best_score:.2f} points')
    
    print('\n'.join(lines))
except Exception as e:
    print(f'⚠️ Error reading results: {e}')
    sys.exit(1)
" >> "$LOG" 2>&1

# Send report via OpenClaw message tool
REPORT=$(tail -20 "$LOG" | grep -A 50 "Top 5\|Daily Report\|CHAMPION\|V17 still" || echo "See log for details")

openclaw message send --channel discord --target "1476565086708695104" "$REPORT" 2>/dev/null || echo "Discord report sent via log (openclaw message failed)"

echo "" | tee -a "$LOG"
echo "Daily run complete. Exit code: $EXIT_CODE" | tee -a "$LOG"