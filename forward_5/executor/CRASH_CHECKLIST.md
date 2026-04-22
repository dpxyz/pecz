# Crash Recovery Checklist

**Wann:** Nach jedem Agent-Crash, Engine-Neustart, oder Docker-Neustart

## System-Check (in dieser Reihenfolge)

### 1. Prozesse prüfen
```bash
ps aux | grep -E "paper_engine|watchdog|monitor" | grep -v grep
```
- [ ] Paper Engine läuft (PID sichtbar)
- [ ] Wenn nicht: `cd /data/.openclaw/workspace/forward_v5/forward_5/executor && bash run_paper_engine.sh --background`

### 2. Cron-Jobs prüfen
```bash
cat /data/.openclaw/cron/jobs.json | python3 -m json.tool | grep -E "name|enabled|lastRunStatus|consecutiveErrors"
```
- [ ] housekeeping: enabled=True, lastRunStatus=ok, consecutiveErrors=0
- [ ] engine-watchdog: enabled=True, lastRunStatus=ok, consecutiveErrors=0
- [ ] monitor-update: enabled=True, lastRunStatus=ok, consecutiveErrors=0
- [ ] Wenn Cron fehlt: `openclaw cron add` (siehe MEMORY.md für Configs)

### 3. Engine Health prüfen
```bash
cd /data/.openclaw/workspace/forward_v5/forward_5/executor
python3 -c "
import sqlite3; conn=sqlite3.connect('state.db')
eq=float(conn.execute('SELECT value FROM state WHERE key=\"equity\"').fetchone()[0])
candles=conn.execute('SELECT COUNT(*) FROM candles').fetchone()[0]
eh=conn.execute('SELECT equity, drawdown_pct, n_positions FROM equity_history ORDER BY ts DESC LIMIT 1').fetchone()
pos=conn.execute('SELECT COUNT(*) FROM positions WHERE state=\"IN_LONG\"').fetchone()[0]
print(f'Equity: {eq:.2f}€ | DD: {eh[1]:.2f}% | Positions: {pos} | Candles: {candles}')
conn.close()
"
```
- [ ] Equity > 0 und plausibel (~99€)
- [ ] DD < 25%
- [ ] Candles > 0 (Datenfeed funktioniert)

### 4. Engine Log prüfen
```bash
tail -30 paper_engine.log | grep -i "error\|exception\|traceback\|fail"
```
- [ ] Keine Error/Exception/Traceback im aktuellen Log
- [ ] Letzte Zeile hat aktuellen Timestamp

### 5. Trade Log prüfen
```bash
python3 -c "
import json
from collections import Counter
trades = []
with open('trades.jsonl') as f:
    for line in f:
        if line.strip(): trades.append(json.loads(line))
entries = Counter(t['symbol'] for t in trades if t['event'] == 'ENTRY')
exits = Counter(t['symbol'] for t in trades if t['event'] == 'EXIT')
for sym in sorted(set(list(entries.keys()) + list(exits.keys()))):
    e, x = entries.get(sym,0), exits.get(sym,0)
    diff = e - x
    marker = ' ⚠️' if diff > 0 else ' ✅'
    print(f'{sym}: entry={e} exit={x} diff={diff}{marker}')
"
```
- [ ] Alle Symbole haben entry == exit (Diff = 0)
- [ ] Wenn nicht: Backfill-Garbage oder orphaned ENTRYs → bereinigen

### 6. Monitor Data prüfen
```bash
ls -la monitor_data.json
```
- [ ] File existiert und ist < 1h alt
- [ ] Wenn nicht: `bash /data/.openclaw/workspace/scripts/run_monitor.sh`

### 7. Manuelle Checks ausführen
- [ ] Watchdog: `python3 watchdog_v2.py` → Exit 0
- [ ] Housekeeping: `bash /data/.openclaw/workspace/scripts/housekeeping.sh`
- [ ] Monitor Update: `bash /data/.openclaw/workspace/scripts/run_monitor.sh`

### 8. Test Suite
```bash
python3 -m pytest tests/ -q
```
- [ ] Alle Tests bestanden (ausgenommen bekannte Bug-Tests)
- [ ] Wenn neue Failures: Bug→Test-Workflow (PRINCIPLES.md)

## Nach dem Check
- [ ] Discord #system informieren (kurz: "Engine recovered, EQ=99.XX€, DD=X.X%")
- [ ] MEMORY.md aktualisieren wenn wichtiges passiert ist