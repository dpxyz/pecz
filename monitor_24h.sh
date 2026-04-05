#!/bin/bash
# 24h Stability Test Monitor
# Requires DISCORD_WEBHOOK_URL environment variable

WEBHOOK="${DISCORD_WEBHOOK_URL:-}"
SKIP_DISCORD="${SKIP_DISCORD:-false}"

LOG_FILE="/data/.openclaw/workspace/forward_v5/forward_v5/simulation/24h_test.log"
REPORT_DIR="/data/.openclaw/workspace/forward_v5/forward_v5/simulation"

send_discord() {
    if [ -z "$WEBHOOK" ] || [ "$SKIP_DISCORD" = "true" ]; then
        echo "[Discord: $1]"
        return
    fi
    curl -X POST -H "Content-Type: application/json" \
        -d "{\"content\":\"$1\"}" \
        "$WEBHOOK" > /dev/null 2>&1
}

check_test() {
    local check_time="$1"
    local is_final="$2"
    
    # Prüfe ob Prozess 266 läuft
    if ps -p 266 > /dev/null 2>&1; then
        if [ "$is_final" = "true" ]; then
            send_discord "🤔 **24h Test Update** T+24h\n\nDer Prozess läuft noch (PID 266)\nDies ist unerwartet - sollte bereits beendet sein.\n\n*Überwache weiter...*"
        else
            send_discord "🔄 **24h Test Update** ${check_time}\n\n✅ Prozess PID 266 läuft noch\n📄 Log wird fortgesetzt\n\n*Weiterhin stabil...*"
        fi
    else
        # Prozess beendet - prüfe Report
        REPORT=$(ls -t $REPORT_DIR/report_24h_*.json 2>/dev/null | head -1)
        
        if [ -n "$REPORT" ]; then
            if grep -q '"status": "PASSED"' "$REPORT" 2>/dev/null || grep -q '"passed": true' "$REPORT" 2>/dev/null; then
                send_discord "✅ **24h Stability Test BESTANDEN!**\n\n🎉 Der 24-Stunden-Test wurde erfolgreich abgeschlossen\n📊 Report: $(basename $REPORT)\n\n*Monitoring beendet.*"
            else
                send_discord "❌ **24h Stability Test FEHLGESCHLAGEN**\n\n⚠️ Der Test wurde mit Fehlern beendet\n📊 Report: $(basename $REPORT)\n\n*Bitte Logs prüfen!*"
            fi
        else
            send_discord "⚠️ **24h Test unterbrochen**\n\n❌ Prozess PID 266 beendet\n📄 Kein Report gefunden\n\n*Test wurde vorzeitig beendet oder abgebrochen*"
        fi
        
        exit 0
    fi
}

# Haupt-Loop: Prüfe alle 4 Stunden
(sleep 14400 && check_test "T+4h (13:40)" false) &
(sleep 28800 && check_test "T+8h (17:40)" false) &  
(sleep 43200 && check_test "T+12h (21:40)" false) &
(sleep 57600 && check_test "T+16h (01:40)" false) &
(sleep 72000 && check_test "T+20h (05:40)" false) &
(sleep 86400 && check_test "T+24h (09:40)" true) &

echo "24h Stability Test Monitoring gestartet - PID 266"
echo "Nächste Updates: +4h, +8h, +12h, +16h, +20h, +24h"
