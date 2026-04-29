---
summary: "Mandatory crash recovery checklist — follow every time a new agent session starts"
read_when:
  - Every session startup
  - After any crash or restart
---

# Crash Recovery Checklist

**Wann:** Nach jedem Agent-Crash, Engine-Neustart, oder Docker-Neustart.
**Regel:** In dieser Reihenfolge abarbeiten. Nicht improvisieren.

## 1. Prozesse
```bash
ps aux | grep -E "paper_engine|watchdog|monitor" | grep -v grep
```
- Läuft? → weiter zu 2.
- Nicht? → `cd /data/.openclaw/workspace/forward_v5/forward_5/executor && bash run_paper_engine.sh --background`

## 2. Cron-Jobs
```bash
python3 -c "
import json
for j in json.load(open('/data/.openclaw/cron/jobs.json'))['jobs']:
    s=j['state']; e=s.get('consecutiveErrors',0)
    print(f\"{j['name']:20s} {'✅' if j['enabled'] and e==0 else '❌'} last={s.get('lastRunStatus','?')} errors={e}\")
"
```
- Alle ✅? → weiter zu 3.
- Cron fehlt? → `openclaw cron add` (siehe MEMORY.md)

## 3. Engine Health
```bash
cd /data/.openclaw/workspace/forward_v5/forward_5/executor
python3 -c "
import sqlite3; c=sqlite3.connect('state.db')
eq=float(c.execute(\"SELECT value FROM state WHERE key='equity'\").fetchone()[0])
eh=c.execute('SELECT equity,drawdown_pct,n_positions FROM equity_history ORDER BY ts DESC LIMIT 1').fetchone()
pos=c.execute(\"SELECT COUNT(*) FROM positions WHERE state='IN_LONG'\").fetchone()[0]
candles=c.execute('SELECT COUNT(*) FROM candles').fetchone()[0]
print(f'EQ {eq:.2f}€ | DD {eh[1]:.2f}% | Pos {pos} | Candles {candles}')
c.close()
"
```
- EQ plausibel (~99€), DD < 25%, Candles > 0? → weiter zu 4.

## 4. Engine Log
```bash
cd /data/.openclaw/workspace/forward_v5/forward_5/executor
tail -50 paper_engine.log | grep -ic "error\|exception\|traceback"
```
- 0? → weiter zu 5.
- > 0? → `grep -n "Error\|Exception\|Traceback" paper_engine.log | tail -10` → Bug→Test-Workflow

## 5. Trade Log
```bash
cd /data/.openclaw/workspace/forward_v5/forward_5/executor
python3 -c "
import json; from collections import Counter
t=[json.loads(l) for l in open('trades.jsonl') if l.strip()]
e=Counter(x['symbol'] for x in t if x['event']=='ENTRY')
x=Counter(x['symbol'] for x in t if x['event']=='EXIT')
for s in sorted(set(list(e)+list(x))):
    d=e.get(s,0)-x.get(s,0)
    print(f'{s:10s} E={e.get(s,0)} X={x.get(s,0)} diff={d:+d} {\"⚠️\" if d else \"✅\"}')
"
```
- Alle diff=0? → weiter zu 6.
- Orphaned? → Backfill-Garbage bereinigen (siehe unten)

## 6. Monitor + Discord
```bash
ls -la /data/.openclaw/workspace/forward_v5/forward_5/executor/monitor_data.json
```
- < 1h alt? → ok.
- Älter? → `bash /data/.openclaw/workspace/scripts/run_monitor.sh`
- Discord #system informieren: "🔄 Crash Recovery: EQ=XX€ DD=X% all systems OK"

## 7. Test Suite
```bash
cd /data/.openclaw/workspace/forward_v5/forward_5/executor && python3 -m pytest tests/ -q
```
- Alle passed (außer bekannte Bug-Tests)? → weiter zu 8.
- Neue Failures? → Bug→Test-Workflow (PRINCIPLES.md)

## 8. Foundry HOF Check
```bash
cd /data/.openclaw/workspace/forward_v5/forward_5/research && python3 hof_summary.py
```
- Zeigt ALLE 10w-Champions ranked by OOS
- **VOR jeder Champion-Behauptung:** dieses Skript laufen lassen!
- Nie einen "neuen Champion" verkünden ohne bestehende HOF-Einträge zu prüfen

---

---

## Trade Log Bereinigung (falls Step 5 ⚠️)

```python
# Entferne Backfill-Garbage: Preise die unmöglich sind
MIN_PRICES = {"BTCUSDT": 10000, "ETHUSDT": 100, "SOLUSDT": 10,
              "AVAXUSDT": 1, "DOGEUSDT": 0.001, "ADAUSDT": 0.01}
# Entferne Duplikate: gleicher symbol+event+price innerhalb 1h
# Füge fehlende EXIT-Events für orphaned Positions hinzu (reason="engine_restart")
```

## Pfade
- Engine: `forward_v5/forward_5/executor/`
- State DB: `forward_v5/forward_5/executor/state.db`
- Trade Log: `forward_v5/forward_5/executor/trades.jsonl`
- Engine Log: `forward_v5/forward_5/executor/paper_engine.log`
- Monitor: `scripts/run_monitor.sh`
- Housekeeping: `scripts/housekeeping.sh`
- Watchdog: `forward_v5/forward_5/executor/watchdog_v2.py`