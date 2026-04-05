#!/bin/bash
# Pre-Flight Check Script für 24h+ Tests
# Muss VOR Test-Start ausgeführt werden

set -e

echo "🛫 Pre-Flight Check für langlaufende Tests"
echo "========================================="

# 1. Disk-Space Check (Rule DISK-001)
DISK_USED=$(df -h /data | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USED" -gt 30 ]; then
    echo "❌ FAILED: Disk ${DISK_USED}% used (max 30% erlaubt)"
    echo "   Bereinige erst: du -sh /data/.openclaw/workspace/archive/*"
    exit 1
fi
echo "✅ Disk OK: ${DISK_USED}% used (max 30%)"

# 2. Memory Check
FREE_MEM=$(free -m | awk 'NR==2{printf "%.0f", $7*100/$2}')
if [ "$FREE_MEM" -lt 20 ]; then
    echo "⚠️  WARN: Nur ${FREE_MEM}% freier Speicher"
else
    echo "✅ Memory OK: ${FREE_MEM}% frei"
fi

# 3. Archive Cleanup (älter als 30 Tage)
ARCHIVE_DIR="/data/.openclaw/workspace/archive"
if [ -d "$ARCHIVE_DIR" ]; then
    OLD_DIRS=$(find "$ARCHIVE_DIR" -maxdepth 1 -type d -mtime +30 | wc -l)
    if [ "$OLD_DIRS" -gt 0 ]; then
        echo "🗑️  Cleaning: ${OLD_DIRS} alte Archive (>30 Tage)"
        find "$ARCHIVE_DIR" -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \; 2>/dev/null || true
    fi
fi

# 4. Log-Rotation (falls Logs zu groß)
LOG_DIR="/data/.openclaw/workspace/forward_v5/forward_v5/logs"
if [ -d "$LOG_DIR" ]; then
    LOG_SIZE=$(du -sm "$LOG_DIR" | awk '{print $1}')
    if [ "$LOG_SIZE" -gt 100 ]; then  # >100MB
        echo "🗑️  Cleaning: Logs ${LOG_SIZE}MB (>100MB)"
        find "$LOG_DIR" -name "*.log" -size +10M -exec truncate -s 0 {} \;
    fi
fi

# 5. Prozess-Check (keine doppelten Tests)
RUNNING_TESTS=$(pgrep -f "simulation_24h" | wc -l)
if [ "$RUNNING_TESTS" -gt 0 ]; then
    echo "⚠️  WARN: ${RUNNING_TESTS} Test(s) laufen bereits"
    pgrep -f "simulation_24h"
fi

echo ""
echo "✅ Pre-Flight Check BESTANDEN"
echo "   Starte Test mit: node --test tests/simulation_24h_stability.test.js"
exit 0
