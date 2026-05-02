#!/bin/bash
# Run Paper Engine V2 — writes PID file and redirects log
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Write PID file
echo $$ > engine.pid

# Log to both file and stdout
exec python3 -u paper_engine_v2.py "$@" 2>&1 | tee paper_engine_v2.log