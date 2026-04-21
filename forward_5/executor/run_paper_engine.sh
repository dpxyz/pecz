#!/bin/bash
# Paper Trading Engine — Process Manager
# Auto-start with restart on crash. Replaces systemd in Docker container.
# Usage: bash run_paper_engine.sh [--foreground|--background|--stop|--status]

set -e

ENGINE_DIR="/data/.openclaw/workspace/forward_v5/forward_5/executor"
PID_FILE="$ENGINE_DIR/.paper_engine.pid"
LOG_FILE="$ENGINE_DIR/paper_engine.log"
RESTART_DELAY=30  # seconds between restarts
MAX_RESTARTS=5
RESTART_WINDOW=300  # 5 minutes

cd "$ENGINE_DIR"

# Load .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

case "${1:---foreground}" in
    --background)
        # Start in background with nohup
        nohup bash "$0" --foreground >> "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        echo "🚀 Paper Engine started in background (PID: $(cat $PID_FILE))"
        echo "   Log: $LOG_FILE"
        echo "   Stop: bash $0 --stop"
        echo "   Status: bash $0 --status"
        ;;

    --stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            # Kill the parent script and all children
            pkill -P "$PID" 2>/dev/null || true
            kill "$PID" 2>/dev/null || true
            rm -f "$PID_FILE"
            echo "🛑 Paper Engine stopped"
        else
            echo "⚠️ No PID file found — engine not running?"
        fi
        ;;

    --status)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
            echo "🟢 Paper Engine running (PID: $(cat $PID_FILE))"
            echo "   Uptime: $(ps -o etime= -p $(cat $PID_FILE) 2>/dev/null || echo 'unknown')"
            echo "   Log: tail -f $LOG_FILE"
        else
            echo "🔴 Paper Engine not running"
            rm -f "$PID_FILE" 2>/dev/null
        fi
        ;;

    --foreground)
        echo "🚀 Paper Trading Engine V1 starting..."
        echo "   $(date -Iseconds)"
        echo "   Strategy: MACD+ADX+EMA Baseline"
        echo "   Kill-switches: DailyLoss>5%, MaxDD>20%, MaxPos=1, CL≥5"
        echo "   Commands: !kill, !resume, !status, !help"
        echo "   Press Ctrl+C to stop"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        # Rotate log on start (keep last 1MB, append fresh)
        if [ -f "$LOG_FILE" ] && [ $(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null || echo 0) -gt 1048576 ]; then
            mv "$LOG_FILE" "${LOG_FILE}.old"
            echo "[$(date -Iseconds)] Log rotated (${LOG_FILE}.old)" >> "$LOG_FILE"
        fi

        restart_count=0
        first_start=$(date +%s)

        while true; do
            echo ""
            echo "[$(date -Iseconds)] Starting engine..."
            python3 paper_engine.py 2>&1 || true

            EXIT_CODE=$?
            now=$(date +%s)

            if [ $EXIT_CODE -eq 0 ]; then
                echo "[$(date -Iseconds)] Engine stopped cleanly"
                break
            fi

            # Count restarts within window
            if [ $((now - first_start)) -gt $RESTART_WINDOW ]; then
                restart_count=0
                first_start=$now
            fi

            restart_count=$((restart_count + 1))

            if [ $restart_count -gt $MAX_RESTARTS ]; then
                echo "🚨 [$(date -Iseconds)] MAX RESTARTS ($MAX_RESTARTS) exceeded — giving up"
                echo "   Check logs: $LOG_FILE"
                break
            fi

            echo "⚠️ [$(date -Iseconds)] Engine crashed (exit $EXIT_CODE), restarting in ${RESTART_DELAY}s... ($restart_count/$MAX_RESTARTS)"
            sleep $RESTART_DELAY
        done

        echo ""
        echo "[$(date -Iseconds)] Paper Engine shutdown complete"
        ;;

    *)
        echo "Usage: bash $0 [--foreground|--background|--stop|--status]"
        exit 1
        ;;
esac