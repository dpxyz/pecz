#!/bin/bash
cd "$(dirname "$0")"
python3 watchdog.py >> watchdog.log 2>&1
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "$(date): Watchdog FAILED (exit $EXIT_CODE)" >> watchdog.log
fi
exit $EXIT_CODE