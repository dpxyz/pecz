#!/bin/bash
# Nightly Auto-Cleanup Script
# Sollte via Cron täglich laufen (z.B. 3 Uhr morgens)

LOG_FILE="/data/.openclaw/workspace/forward_v5/forward_v5/logs/cleanup.log"

echo "$(date '+%Y-%m-%d %H:%M:%S') - Auto-Cleanup gestartet" >> "$LOG_FILE"

# 1. Archive älter als 30 Tage löschen
ARCHIVE_DIR="/data/.openclaw/workspace/archive"
if [ -d "$ARCHIVE_DIR" ]; then
    DELETED=$(find "$ARCHIVE_DIR" -maxdepth 1 -type d -mtime +30 | wc -l)
    if [ "$DELETED" -gt 0 ]; then
        find "$ARCHIVE_DIR" -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \; 2>/dev/null
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Gelöscht: ${DELETED} alte Archive" >> "$LOG_FILE"
    fi
fi

# 2. Alte .gz Logs komprimieren
find "$ARCHIVE_DIR" -name "*.log" -size +1M -exec gzip -f {} \; 2>/dev/null

# 3. Simulation-Logs älter als 7 Tage bereinigen
SIM_DIR="/data/.openclaw/workspace/forward_v5/forward_v5/simulation"
if [ -d "$SIM_DIR" ]; then
    find "$SIM_DIR" -name "heartbeat_*.log" -mtime +7 -delete 2>/dev/null
    find "$SIM_DIR" -name "report_*.json" -mtime +7 -delete 2>/dev/null
fi

# 4. Disk-Status loggen
DISK_USED=$(df -h /data | awk 'NR==2 {print $5}')
echo "$(date '+%Y-%m-%d %H:%M:%S') - Disk Usage: ${DISK_USED}" >> "$LOG_FILE"

# 5. Warnung bei >80%
if [ "${DISK_USED%\%}" -gt 80 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - WARNUNG: Disk >80%" >> "$LOG_FILE"
    # Optional: Discord Alert hier einfügen
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - Auto-Cleanup beendet" >> "$LOG_FILE"
