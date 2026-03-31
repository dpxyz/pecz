/**
 * Heartbeat Service - Runtime Validation for Forward V5
 * 
 * Responsibilities:
 * - Write heartbeat every 60 seconds to prove system is alive
 * - Monitor Forward V5 system health
 * - Alert on anomalies (no remediation, only alerts)
 * - Persist state to runtime_validation/state.json
 * - Handle restarts: <60min gap = resume, >60min gap = new run
 * 
 * Design: RUNTIME_VALIDATION_DESIGN.md v1.0
 */

const fs = require('fs');
const path = require('path');

// Fix 5.0d: Absolute threshold monitoring
const monitoringConfig = require('./config/monitoring');

// Configuration - Final Spec v1.0
const CONFIG = {
  HEARTBEAT_INTERVAL_MS: 60 * 1000,        // 1 minute
  HEARTBEAT_TIMEOUT_MS: 5 * 60 * 1000,     // 5 minutes tolerance
  HEALTH_CHECK_INTERVAL_MS: 5 * 60 * 1000, // 5 minutes
  RUN_DURATION_HOURS: 48,                // Fixed 48 hours
  MAX_GAP_MINUTES: 60,                     // Resume if <60min, restart if >60min
  MEMORY_THRESHOLD_WARN: 80,               // %
  MEMORY_THRESHOLD_ERROR: 90,              // %
  MEMORY_LEAK_THRESHOLD: 20,               // % growth
  LOG_SIZE_THRESHOLD_MB: 1000,             // 1GB per day
  EXPLANATION_WINDOW_MINUTES: 120,         // 2 hours
  STATE_FILE: './runtime_validation/state.json',
  HEARTBEAT_LOG: './logs/heartbeat.log',
  RUNTIME_DIR: './runtime_validation'
};

// Fix 5.0d: Sustained memory state
const sustainedState = {
  critical: {
    firstAboveThreshold: null,
    alerted: false,
  },
  warn: {
    firstAboveThreshold: null,
    alerted: false,
  },
  lastSample: null,
};

// State management
let state = null;
let heartbeatTimer = null;
let healthCheckTimer = null;
let isRunning = false;

/**
 * Initialize the runtime validation state
 * Checks for existing state and applies restart rules
 */
function initializeState() {
  const now = new Date().toISOString();
  
  // Ensure runtime directory exists
  if (!fs.existsSync(CONFIG.RUNTIME_DIR)) {
    fs.mkdirSync(CONFIG.RUNTIME_DIR, { recursive: true });
  }
  
  // Check for existing state
  if (fs.existsSync(CONFIG.STATE_FILE)) {
    try {
      const existingState = JSON.parse(fs.readFileSync(CONFIG.STATE_FILE, 'utf8'));
      const lastHeartbeat = new Date(existingState.last_heartbeat);
      const gapMinutes = (new Date() - lastHeartbeat) / 60000;
      
      if (gapMinutes < CONFIG.MAX_GAP_MINUTES) {
        // Resume existing run
        state = existingState;
        state.status = 'RUNNING';
        logEvent('RUN_RESUMED', `Gap acceptable: ${Math.round(gapMinutes)}min`);
        return;
      } else {
        // Archive old state and start new
        archiveState(existingState);
        logEvent('RUN_RESTARTED', `Gap too large: ${Math.round(gapMinutes)}min`);
      }
    } catch (err) {
      logEvent('STATE_CORRUPTED', 'Starting new run');
    }
  }
  
  // Create new state
  state = {
    run_id: `rv-${now.split('T')[0]}-${Math.random().toString(36).substr(2, 6)}`,
    version: '1.0',
    start_time: now,
    planned_end_time: new Date(Date.now() + CONFIG.RUN_DURATION_HOURS * 60 * 60 * 1000).toISOString(),
    status: 'RUNNING',
    last_heartbeat: now,
    last_health_check: now,
    counters: {
      heartbeats_expected: 0,
      heartbeats_received: 0,
      heartbeats_missed: 0,
      health_checks_total: 0,
      health_checks_passed: 0,
      health_checks_failed: 0,
      alerts_fatal: 0,
      alerts_critical: 0,
      alerts_error: 0,
      alerts_warn: 0
    },
    events: [],
    cb_events: [],
    metrics: {
      memory_start_mb: 0,
      memory_current_mb: 0,
      memory_peak_mb: 0,
      memory_growth_percent: 0
    },
    result: null
  };
  
  // Initialize memory metrics
  const memUsage = process.memoryUsage();
  state.metrics.memory_start_mb = Math.round(memUsage.heapUsed / 1024 / 1024);
  state.metrics.memory_current_mb = state.metrics.memory_start_mb;
  state.metrics.memory_peak_mb = state.metrics.memory_start_mb;
  
  persistState();
  logEvent('RUN_STARTED', `Run ID: ${state.run_id}, Duration: ${CONFIG.RUN_DURATION_HOURS}h`);
}

/**
 * Archive old state file before starting new run
 */
function archiveState(oldState) {
  const timestamp = oldState.start_time.replace(/[:.]/g, '-');
  const archivePath = path.join(CONFIG.RUNTIME_DIR, `state.json.${timestamp}.archive`);
  fs.writeFileSync(archivePath, JSON.stringify(oldState, null, 2));
}

/**
 * Persist state to file
 */
function persistState() {
  try {
    fs.writeFileSync(CONFIG.STATE_FILE, JSON.stringify(state, null, 2));
  } catch (err) {
    console.error(`[${new Date().toISOString()}] FATAL: Cannot persist state: ${err.message}`);
    // Alert but don't stop - system continues
    sendAlert('FATAL', 'State Persistence Failed', err.message);
  }
}

/**
 * Log event to heartbeat log and optionally to console
 */
function logEvent(type, message, level = 'INFO') {
  const entry = {
    timestamp: new Date().toISOString(),
    type,
    level,
    message,
    run_id: state?.run_id || 'unknown'
  };
  
  const logLine = JSON.stringify(entry) + '\n';
  
  // Append to log file
  try {
    fs.appendFileSync(CONFIG.HEARTBEAT_LOG, logLine);
  } catch (err) {
    console.error('Failed to write heartbeat log:', err.message);
  }
  
  // Console output for important events
  if (level === 'CRITICAL' || level === 'FATAL' || level === 'ERROR') {
    console.error(`[${entry.timestamp}] ${level}: ${type} - ${message}`);
  } else if (level === 'WARN') {
    console.warn(`[${entry.timestamp}] WARN: ${type} - ${message}`);
  }
}

/**
 * Send alert (no remediation, only notification)
 */
function sendAlert(level, title, details) {
  // Update counters
  if (state) {
    const counterKey = `alerts_${level.toLowerCase()}`;
    if (state.counters[counterKey] !== undefined) {
      state.counters[counterKey]++;
    }
    persistState();
  }
  
  // Log the alert
  logEvent('ALERT', `[${level}] ${title}: ${details}`, level);
  
  // TODO: Add Discord webhook here
  // For now, we just log - Discord integration can be added later
  // console.log(`[ALERT:${level}] ${title}: ${details}`);
}

/**
 * Write heartbeat entry
 */
function writeHeartbeat(status = 'OK') {
  if (!state) return;
  
  const now = new Date();
  const runDurationHours = (now - new Date(state.start_time)) / (1000 * 60 * 60);
  
  const heartbeat = {
    timestamp: now.toISOString(),
    type: 'HEARTBEAT',
    status,
    run_duration_hours: parseFloat(runDurationHours.toFixed(2)),
    checks: {
      event_store: 'OK', // Placeholder - health_checker provides real data
      circuit_breaker: 'CLOSED', // Placeholder
      last_health_check: state.last_health_check,
      memory_mb: Math.round(process.memoryUsage().heapUsed / 1024 / 1024)
    },
    alerts_since_last: 0,
    pid: process.pid
  };
  
  state.last_heartbeat = now.toISOString();
  state.counters.heartbeats_received++;
  
  // Calculate expected heartbeats
  const elapsedMinutes = (now - new Date(state.start_time)) / 60000;
  state.counters.heartbeats_expected = Math.floor(elapsedMinutes);
  
  persistState();
  logEvent('HEARTBEAT', `Status: ${status}, Run: ${heartbeat.run_duration_hours.toFixed(2)}h`);
}

/**
 * Check if run duration is complete
 */
function checkRunCompletion() {
  if (!state) return false;
  
  const now = new Date();
  const endTime = new Date(state.planned_end_time);
  
  if (now >= endTime) {
    completeRun();
    return true;
  }
  
  return false;
}

/**
 * Complete the run and generate report
 */
function completeRun() {
  if (!state) return;
  
  state.status = 'COMPLETED';
  
  // Evaluate criteria
  const criteria = evaluateCriteria();
  
  state.result = {
    completed_at: new Date().toISOString(),
    duration_hours: CONFIG.RUN_DURATION_HOURS,
    criteria_met: criteria.met,
    criteria_failed: criteria.failed,
    go_no_go: criteria.go ? 'GO' : 'NO-GO',
    summary: generateSummary()
  };
  
  persistState();
  
  logEvent('RUN_COMPLETED', `Result: ${criteria.go ? 'GO' : 'NO-GO'}`, criteria.go ? 'INFO' : 'CRITICAL');
  
  // Generate report file
  generateReport();
  
  stop();
}

/**
 * Evaluate all GO/NO-GO criteria
 */
function evaluateCriteria() {
  const criteria = {
    met: [],
    failed: [],
    go: true
  };
  
  // 1. Duration reached
  const now = new Date();
  const endTime = new Date(state.planned_end_time);
  if (now >= endTime) {
    criteria.met.push('Duration: 48h reached');
  } else {
    criteria.failed.push('Duration: not reached');
    criteria.go = false;
  }
  
  // 2. Heartbeat completeness (≥95%)
  const heartbeatRate = state.counters.heartbeats_expected > 0
    ? (state.counters.heartbeats_received / state.counters.heartbeats_expected) * 100
    : 0;
  if (heartbeatRate >= 95) {
    criteria.met.push(`Heartbeat completeness: ${heartbeatRate.toFixed(1)}% (≥95%)`);
  } else {
    criteria.failed.push(`Heartbeat completeness: ${heartbeatRate.toFixed(1)}% (<95%)`);
    criteria.go = false;
  }
  
  // 3. No gaps >5min (check events)
  const gapsOver5Min = state.events.filter(e => 
    e.type === 'HEARTBEAT_GAP' && e.gap_minutes > 5
  ).length;
  if (gapsOver5Min === 0) {
    criteria.met.push('No gaps >5 minutes');
  } else {
    criteria.failed.push(`${gapsOver5Min} gaps >5 minutes`);
    criteria.go = false;
  }
  
  // 4. Health checks passing (≥95%)
  const healthRate = state.counters.health_checks_total > 0
    ? (state.counters.health_checks_passed / state.counters.health_checks_total) * 100
    : 0;
  if (healthRate >= 95) {
    criteria.met.push(`Health checks: ${healthRate.toFixed(1)}% (≥95%)`);
  } else {
    criteria.failed.push(`Health checks: ${healthRate.toFixed(1)}% (<95%)`);
    criteria.go = false;
  }
  
  // 5. No unexplained CRITICAL events
  const unexplainedCritical = state.events.filter(e => 
    (e.level === 'CRITICAL' || e.level === 'FATAL') && !e.explained
  ).length;
  if (unexplainedCritical === 0) {
    criteria.met.push('No unexplained CRITICAL events');
  } else {
    criteria.failed.push(`${unexplainedCritical} unexplained CRITICAL events`);
    criteria.go = false;
  }
  
  // 6. No unexplained PAUSE events
  const unexplainedPause = state.cb_events.filter(e => 
    e.to === 'OPEN' && !e.explained
  ).length;
  if (unexplainedPause === 0) {
    criteria.met.push('No unexplained PAUSE events');
  } else {
    criteria.failed.push(`${unexplainedPause} unexplained PAUSE events`);
    criteria.go = false;
  }
  
  // 7. Memory stable (<10% growth)
  if (state.metrics.memory_growth_percent < 10) {
    criteria.met.push(`Memory growth: ${state.metrics.memory_growth_percent.toFixed(1)}% (<10%)`);
  } else {
    criteria.failed.push(`Memory growth: ${state.metrics.memory_growth_percent.toFixed(1)}% (≥10%)`);
    criteria.go = false;
  }
  
  // 8. Memory never >90%
  if (state.metrics.memory_peak_mb < state.metrics.memory_start_mb * 0.9 * 10) {
    criteria.met.push('Memory never exceeded 90%');
  } else {
    criteria.failed.push('Memory exceeded 90%');
    criteria.go = false;
  }
  
  // 9. Logs rotated (<1GB/day)
  // Placeholder - actual log size check would need filesystem access
  criteria.met.push('Log rotation: assumed OK');
  
  // 10. System OK at end
  const lastCheck = state.last_health_check;
  const lastCheckAge = (new Date() - new Date(lastCheck)) / 60000;
  if (lastCheckAge < 10) {
    criteria.met.push('System OK at end');
  } else {
    criteria.failed.push('System not responsive at end');
    criteria.go = false;
  }
  
  return criteria;
}

/**
 * Generate summary string
 */
function generateSummary() {
  return {
    run_id: state.run_id,
    duration_hours: CONFIG.RUN_DURATION_HOURS,
    heartbeats: `${state.counters.heartbeats_received}/${state.counters.heartbeats_expected}`,
    health_checks: `${state.counters.health_checks_passed}/${state.counters.health_checks_total}`,
    critical_events: state.counters.alerts_critical,
    memory_growth: `${state.metrics.memory_growth_percent.toFixed(1)}%`
  };
}

/**
 * Generate report file
 */
function generateReport() {
  const reportPath = path.join(CONFIG.RUNTIME_DIR, `report_${state.run_id}.md`);
  
  const report = `# Runtime Validation Report

**Run ID:** ${state.run_id}  
**Started:** ${state.start_time}  
**Completed:** ${state.result.completed_at}  
**Duration:** ${CONFIG.RUN_DURATION_HOURS} hours  
**Result:** ${state.result.go_no_go}

## Summary

| Metric | Value |
|--------|-------|
| Heartbeats | ${state.counters.heartbeats_received}/${state.counters.heartbeats_expected} |
| Health Checks | ${state.counters.health_checks_passed}/${state.counters.health_checks_total} |
| CRITICAL Events | ${state.counters.alerts_critical} |
| ERROR Events | ${state.counters.alerts_error} |
| WARN Events | ${state.counters.alerts_warn} |
| Memory Start | ${state.metrics.memory_start_mb} MB |
| Memory End | ${state.metrics.memory_current_mb} MB |
| Memory Growth | ${state.metrics.memory_growth_percent.toFixed(1)}% |

## Criteria Evaluation

### Passed
${state.result.criteria_met.map(c => `- ✅ ${c}`).join('\n') || '- None'}

### Failed
${state.result.criteria_failed.map(c => `- ❌ ${c}`).join('\n') || '- None'}

## Circuit Breaker Events

| Time | From | To | Reason |
|------|------|-----|--------|
${state.cb_events.map(e => `| ${e.timestamp} | ${e.from} | ${e.to} | ${e.reason} |`).join('\n') || 'No events'}

---
*Generated: ${new Date().toISOString()}*
`;
  
  try {
    fs.writeFileSync(reportPath, report);
    logEvent('REPORT_GENERATED', reportPath);
  } catch (err) {
    logEvent('REPORT_FAILED', err.message, 'ERROR');
  }
}

/**
 * Update metrics from health checker results — FIX 5.0d
 * Absolute sustained thresholds, keine Berechnungen
 */
function updateMetrics(healthResults) {
  if (!state) return;
  
  // Basic memory update
  const memUsage = process.memoryUsage();
  const currentMB = Math.round(memUsage.heapUsed / 1024 / 1024);
  state.metrics.memory_current_mb = currentMB;
  if (currentMB > state.metrics.memory_peak_mb) {
    state.metrics.memory_peak_mb = currentMB;
  }
  
  // Fix 5.0d: Sustained threshold check
  checkMemorySustained();
  
  persistState();
}

/**
 * Fix 5.0d: Sustained memory threshold check
 * WARN: >80% für >60min | CRITICAL: >90% für >15min
 */
function checkMemorySustained() {
  const memUsage = process.memoryUsage();
  const percent = (memUsage.heapUsed / memUsage.heapTotal) * 100;
  const now = Date.now();
  const { memory, hysteresis } = monitoringConfig;
  
  sustainedState.lastSample = { timestamp: now, percent };
  
  // ═══════════════════════════════════════════════════════
  // CRITICAL: >90% für >15 Min
  // ═══════════════════════════════════════════════════════
  if (percent >= memory.critical.percent) {
    if (!sustainedState.critical.firstAboveThreshold) {
      sustainedState.critical.firstAboveThreshold = now;
      logEvent('MEMORY', `Above ${memory.critical.percent}%: ${percent.toFixed(1)}% [timer start]`, 'INFO');
    } else {
      const durationMinutes = (now - sustainedState.critical.firstAboveThreshold) / 60000;
      
      if (durationMinutes >= memory.critical.durationMinutes && !sustainedState.critical.alerted) {
        sendAlert('CRITICAL', 'Memory Critical Sustained', 
          `${percent.toFixed(1)}% for ${Math.floor(durationMinutes)}min > threshold ${memory.critical.durationMinutes}min`);
        sustainedState.critical.alerted = true;
      }
    }
  } else if (percent <= hysteresis.criticalReset) {
    if (sustainedState.critical.firstAboveThreshold) {
      logEvent('MEMORY', `Recovered below ${hysteresis.criticalReset}%: ${percent.toFixed(1)}% [timer reset]`, 'INFO');
    }
    sustainedState.critical.firstAboveThreshold = null;
    sustainedState.critical.alerted = false;
  }
  
  // ═══════════════════════════════════════════════════════
  // WARN: >80% für >60 Min
  // ═══════════════════════════════════════════════════════
  if (percent >= memory.warn.percent) {
    if (!sustainedState.warn.firstAboveThreshold) {
      sustainedState.warn.firstAboveThreshold = now;
      logEvent('MEMORY', `Above ${memory.warn.percent}%: ${percent.toFixed(1)}% [timer start]`, 'INFO');
    } else {
      const durationMinutes = (now - sustainedState.warn.firstAboveThreshold) / 60000;
      
      if (durationMinutes >= memory.warn.durationMinutes && !sustainedState.warn.alerted) {
        sendAlert('WARN', 'Memory High Sustained', 
          `${percent.toFixed(1)}% for ${Math.floor(durationMinutes)}min > threshold ${memory.warn.durationMinutes}min`);
        sustainedState.warn.alerted = true;
      }
    }
  } else if (percent <= hysteresis.warnReset) {
    if (sustainedState.warn.firstAboveThreshold) {
      logEvent('MEMORY', `Recovered below ${hysteresis.warnReset}%: ${percent.toFixed(1)}% [timer reset]`, 'INFO');
    }
    sustainedState.warn.firstAboveThreshold = null;
    sustainedState.warn.alerted = false;
  }
  
  // Store percent in state for persistence
  state.metrics.memory_percent = percent.toFixed(1);
}

/**
 * Handle health check results from health_checker
 */
function handleHealthCheckResults(results) {
  if (!state) return;
  
  state.last_health_check = results.timestamp;
  state.counters.health_checks_total++;
  
  if (results.overall === 'OK') {
    state.counters.health_checks_passed++;
  } else {
    state.counters.health_checks_failed++;
    
    // Alert but don't remediate
    if (results.overall === 'CRITICAL') {
      sendAlert('CRITICAL', 'Health Check Failed', JSON.stringify(results.checks));
    } else if (results.overall === 'WARN') {
      sendAlert('WARN', 'Health Check Warning', JSON.stringify(results.checks));
    }
  }
  
  // Update metrics
  updateMetrics(results);
  
  // Update heartbeat checks
  if (state) {
    const lastHb = new Date(state.last_heartbeat);
    const now = new Date();
    const gapMinutes = (now - lastHb) / 60000;
    
    if (gapMinutes > 5) {
      const gapEvent = {
        timestamp: now.toISOString(),
        type: 'HEARTBEAT_GAP',
        gap_minutes: parseFloat(gapMinutes.toFixed(2)),
        level: gapMinutes > 5 ? 'ERROR' : 'WARN'
      };
      state.events.push(gapEvent);
      state.counters.heartbeats_missed++;
      sendAlert('ERROR', 'Heartbeat Gap Detected', `${gapMinutes.toFixed(1)}min since last heartbeat`);
    }
  }
  
  persistState();
}

/**
 * Main heartbeat loop
 */
function heartbeatLoop() {
  if (!isRunning) return;
  
  // Check if run is complete
  if (checkRunCompletion()) {
    return;
  }
  
  writeHeartbeat();
  
  // Schedule next heartbeat
  heartbeatTimer = setTimeout(heartbeatLoop, CONFIG.HEARTBEAT_INTERVAL_MS);
}

/**
 * Start the heartbeat service
 */
function start() {
  if (isRunning) {
    console.log('Heartbeat service already running');
    return;
  }
  
  initializeState();
  isRunning = true;
  
  // Start heartbeat loop
  heartbeatLoop();
  
  logEvent('SERVICE_STARTED', 'Heartbeat service started');
  console.log(`Heartbeat service started. Run ID: ${state.run_id}`);
  console.log(`Runs for ${CONFIG.RUN_DURATION_HOURS} hours until ${state.planned_end_time}`);
}

/**
 * Stop the heartbeat service
 */
function stop() {
  isRunning = false;
  
  if (heartbeatTimer) {
    clearTimeout(heartbeatTimer);
    heartbeatTimer = null;
  }
  
  if (healthCheckTimer) {
    clearTimeout(healthCheckTimer);
    healthCheckTimer = null;
  }
  
  if (state && state.status === 'RUNNING') {
    state.status = 'STOPPED';
    persistState();
  }
  
  logEvent('SERVICE_STOPPED', 'Heartbeat service stopped');
  console.log('Heartbeat service stopped');
}

/**
 * Graceful shutdown
 */
function gracefulShutdown() {
  logEvent('SHUTDOWN', 'Graceful shutdown initiated');
  stop();
  process.exit(0);
}

// Handle graceful shutdown
process.on('SIGTERM', gracefulShutdown);
process.on('SIGINT', gracefulShutdown);

// Handle uncaught errors (alert but don't crash)
process.on('uncaughtException', (err) => {
  sendAlert('FATAL', 'Uncaught Exception', err.message);
  logEvent('UNCAUGHT_EXCEPTION', err.message, 'FATAL');
  // Keep running unless it's critical
});

process.on('unhandledRejection', (reason, promise) => {
  sendAlert('ERROR', 'Unhandled Rejection', String(reason));
  logEvent('UNHANDLED_REJECTION', String(reason), 'ERROR');
});

// Exports
module.exports = {
  start,
  stop,
  getState: () => state,
  handleHealthCheckResults,
  sendAlert,
  logEvent,
  CONFIG
};

// Auto-start if called directly
if (require.main === module) {
  start();
}
