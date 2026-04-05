#!/bin/bash
# Lightweight Monitor - nur bei Critical Events
# Requires DISCORD_WEBHOOK_URL environment variable

WEBHOOK="${DISCORD_WEBHOOK_URL:-}"
LOG="/data/.openclaw/workspace/forward_v5/forward_v5/simulation/1h_smoke.log"
PID_FILE="/tmp/1h_smoke_monitor.pid"

echo $$ > "$PID_FILE"

send_discord() {
  if [ -z "$WEBHOOK" ]; then
    echo "[Discord skipped - no webhook configured]"
    return
  fi
  curl -s -X POST -H "Content-Type: application/json" \
    -d "{\"content\":\"$1\"}" "$WEBHOOK" > /dev/null 2>&1
}

while true; do
  sleep 60  # Jede Minute prüfen
  
  # Prüfe ob Test noch läuft
  if ! pgrep -f "simulation_1h_smoke" > /dev/null; then
    # Test beendet - prüfe Ergebnis
    if grep -q "PASSED" "$LOG" 2>/dev/null; then
      send_discord "✅ **1h Smoke Test BESTANDEN**\nÜbergang zu 24h Stability..."
    elif grep -q "FAILED" "$LOG" 2>/dev/null; then
      send_discord "❌ **1h Smoke Test FEHLGESCHLAGEN**\nPrüfe Logs für Details"
    fi
    break
  fi
  
  # Prüfe auf CRITICAL Events
  LAST_LINES=$(tail -5 "$LOG" 2>/dev/null)
  
  if echo "$LAST_LINES" | grep -q "Memory threshold exceeded"; then
    send_discord "🚨 **CRITICAL** 1h Smoke: Memory > 80%"
  fi
  
  if echo "$LAST_LINES" | grep -q "Circuit Breaker opened"; then
    send_discord "🚨 **CRITICAL** 1h Smoke: Circuit Breaker geöffnet"
  fi
  
  if echo "$LAST_LINES" | grep -q "STATE INCONSISTENT"; then
    send_discord "🚨 **CRITICAL** 1h Smoke: State Inkonsistenz"
  fi
  
done

rm -f "$PID_FILE"
