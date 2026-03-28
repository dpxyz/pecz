#!/bin/bash
#
# Runtime Validation Start Script for Forward V5
# Usage: ./scripts/runtime_validation_start.sh [--mode paper|testnet] [--duration 48]
#
# Starts a 48-hour runtime validation with heartbeat and health monitoring
# Design: RUNTIME_VALIDATION_DESIGN.md v1.0
#

set -e  # Exit on error

# Configuration
DEFAULT_DURATION=48
DEFAULT_MODE="paper"
CONFIG_HEARTBEAT_INTERVAL=60
CONFIG_HEALTH_CHECK_INTERVAL=300
CONFIG_MAX_GAP_MINUTES=60

# Parse command line arguments
MODE=$DEFAULT_MODE
DURATION=$DEFAULT_DURATION

while [[ $# -gt 0 ]]; do
  case $1 in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --duration)
      DURATION="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 [--mode paper|testnet] [--duration 48]"
      echo ""
      echo "Options:"
      echo "  --mode       Run mode: paper (default) or testnet"
      echo "  --duration   Duration in hours (default: 48, fixed - no changes)"
      echo "  --help       Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

echo "==================================================================="
echo "Forward V5 - Runtime Validation Start"
echo "==================================================================="
echo "Mode:      $MODE"
echo "Duration:  $DURATION hours (fixed - cannot be changed)"
echo "Started:   $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "Expected:  $(date -u -d "+$DURATION hours" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -v+${DURATION}H +"%Y-%m-%dT%H:%M:%SZ")"
echo "==================================================================="
echo ""

# Check prerequisites
echo "[1/5] Checking prerequisites..."

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js not found"
    exit 1
fi

NODE_VERSION=$(node --version)
echo "  ✓ Node.js: $NODE_VERSION"

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "ERROR: Must be run from project root directory"
    echo "  Current: $(pwd)"
    exit 1
fi
echo "  ✓ Project directory: $(pwd)"

# Check runtime_validation directory
if [ ! -d "runtime_validation" ]; then
    echo "  Creating runtime_validation directory..."
    mkdir -p runtime_validation
fi
echo "  ✓ runtime_validation directory exists"

# Check logs directory
if [ ! -d "logs" ]; then
    echo "  Creating logs directory..."
    mkdir -p logs
fi
echo "  ✓ logs directory exists"

echo ""
echo "[2/5] Checking for existing state..."

if [ -f "runtime_validation/state.json" ]; then
    echo "  Found existing state file"
    
    # Check last modified time
    LAST_MODIFIED=$(stat -c %Y "runtime_validation/state.json" 2>/dev/null || stat -f %m "runtime_validation/state.json")
    CURRENT_TIME=$(date +%s)
    GAP_MINUTES=$(( (CURRENT_TIME - LAST_MODIFIED) / 60 ))
    
    echo "  Last modified: $(date -r $LAST_MODIFIED "+%Y-%m-%d %H:%M:%S UTC" 2>/dev/null || date -r $LAST_MODIFIED "+%Y-%m-%d %H:%M:%S UTC")"
    echo "  Gap: $GAP_MINUTES minutes"
    
    if [ $GAP_MINUTES -lt $CONFIG_MAX_GAP_MINUTES ]; then
        echo "  ✓ Gap < $CONFIG_MAX_GAP_MINUTES minutes - will RESUME existing run"
    else
        echo "  ! Gap > $CONFIG_MAX_GAP_MINUTES minutes - will START NEW run"
        echo "  Archiving old state..."
        TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
        cp runtime_validation/state.json "runtime_validation/state.json.${TIMESTAMP}.archive"
        echo "  Archived to: runtime_validation/state.json.${TIMESTAMP}.archive"
    fi
else
    echo "  No existing state - will START NEW run"
fi

echo ""
echo "[3/5] Starting services..."

# Create PID tracking
echo $$ > runtime_validation/validation.pid
echo "  PID file created: runtime_validation/validation.pid"

# Start the services
export RUNTIME_VALIDATION_MODE=$MODE
export RUNTIME_VALIDATION_DURATION=$DURATION

# Create combined runner script
RUNNER_SCRIPT=$(cat << 'EOF'
const path = require('path');

// Load services
const heartbeat = require('./src/heartbeat_service');
const healthChecker = require('./src/health_checker');

console.log('');
console.log('===================================================================');
console.log('Runtime Validation Services Starting');
console.log('===================================================================');
console.log('');

// Start heartbeat service first
heartbeat.start();

// Connect health checker to heartbeat
healthChecker.setHeartbeatService(heartbeat);

// Start health checker
healthChecker.start();

console.log('');
console.log('Services started successfully');
console.log('Press Ctrl+C to stop gracefully');
console.log('');

// Keep process alive
setInterval(() => {}, 1000);

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down gracefully...');
  heartbeat.stop();
  healthChecker.stop();
  process.exit(0);
});

process.on('SIGTERM', () => {
  heartbeat.stop();
  healthChecker.stop();
  process.exit(0);
});
EOF
)

echo "  Starting combined validation service..."
echo "$RUNNER_SCRIPT" > runtime_validation/runner.js

# Start in foreground (use nohup if you want background)
echo ""
echo "==================================================================="
echo "Runtime Validation is RUNNING"
echo "==================================================================="
echo "Mode:           $MODE"
echo "Duration:       $DURATION hours"
echo "Started:        $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "Expected End:   $(date -u -d "+$DURATION hours" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -v+${DURATION}H +"%Y-%m-%dT%H:%M:%SZ")"
echo ""
echo "Configuration:"
echo "  Heartbeat Interval:      ${CONFIG_HEARTBEAT_INTERVAL}s"
echo "  Health Check Interval:     ${CONFIG_HEALTH_CHECK_INTERVAL}s"
echo "  Max Gap for Resume:        ${CONFIG_MAX_GAP_MINUTES} minutes"
echo ""
echo "Files:"
echo "  State:     runtime_validation/state.json"
echo "  Logs:      logs/heartbeat.log"
echo "  Report:    runtime_validation/report_*.md (generated at end)"
echo ""
echo "Commands:"
echo "  Check status:  tail -f logs/heartbeat.log"
echo "  View state:    cat runtime_validation/state.json"
echo "  Stop:          Ctrl+C (graceful shutdown)"
echo "==================================================================="
echo ""

# Run the actual service
node runtime_validation/runner.js
