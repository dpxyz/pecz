#!/bin/bash
# Watchdog V2 wrapper — called by OpenClaw cron hourly
cd "$(dirname "$0")"
python3 watchdog_v2.py >> watchdog.log 2>&1
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "$(date): Watchdog V2 FAILED (exit $EXIT_CODE)" >> watchdog.log
fi
exit $EXIT_CODE