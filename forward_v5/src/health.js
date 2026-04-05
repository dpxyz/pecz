/**
 * Block 3.2: Health Service with SAFETY/OBSERVABILITY Boundary
 *
 * Continuous health checks with STRICT boundary separation:
 * - SAFETY: Trading-critical checks (event_store, watchdog, reconcile, etc.)
 * - OBSERVABILITY: Non-critical checks (reports, delivery, latency)
 *
 * Boundary Rules:
 * - SAFETY failure => BLOCK/PAUSE + Event + Log (may trigger trading halt)
 * - OBSERVABILITY failure => WARN + Log (never blocks trading)
 *
 * @module health
 * @version 2.0.0
 */

const Logger = require('./logger.js');
const EventStore = require('./event_store.js');

// ============================================================================
// Configuration
// ============================================================================

const DEFAULT_INTERVAL = 30000; // 30 seconds
const DEFAULT_WATCHDOG_TIMEOUT = 30000; // 30 seconds for stale detection

// ============================================================================
// Domain Classification
// ============================================================================

const DOMAIN = {
  SAFETY: 'SAFETY',       // Trading-critical: failure => BLOCK/PAUSE
  OBSERVABILITY: 'OBSERVABILITY'  // Non-critical: failure => WARN only
};

// ============================================================================
// State
// ============================================================================

const checks = new Map();
const watchdogs = new Map();
let monitoringInterval = null;
let isMonitoring = false;
let isPaused = false;  // SAFETY failure can trigger pause
let alertConfig = {
  discordWebhook: null,
  logToFile: true,
  minSeverity: 'WARN'
};

// Track last results
const lastResults = new Map();

// ============================================================================
// Severity Levels
// ============================================================================

const SEVERITY = {
  HEALTHY: 0,
  WARN: 1,
  CRITICAL: 2
};

function severityLevel(severity) {
  return SEVERITY[severity.toUpperCase()] || SEVERITY.HEALTHY;
}

// ============================================================================
// Core Health Check Functions with Domain
// ============================================================================

/**
 * Register a health check with Domain classification
 * @param {string} name - Check name
 * @param {Function} checkFn - Async function returning { status, details }
 * @param {Object} options - { domain: 'SAFETY'|'OBSERVABILITY', severity, timeout }
 */
function register(name, checkFn, options = {}) {
  const domain = options.domain || DOMAIN.OBSERVABILITY;
  
  // Safety checks default to CRITICAL severity
  const defaultSeverity = domain === DOMAIN.SAFETY ? 'CRITICAL' : 'WARN';
  
  checks.set(name, {
    fn: checkFn,
    domain,
    severity: options.severity || defaultSeverity,
    timeout: options.timeout || 5000
  });
  
  Logger.debug(`Health check registered: ${name} [${domain}]`, { module: 'health' });
}

/**
 * Built-in Disk Space Check (SAFETY)
 * Returns available space on critical path
 */
async function checkDiskSpace() {
  const { execSync } = require('child_process');
  const PATH = '/data';
  const CRITICAL_THRESHOLD = 90;  // Pause trading at 90%
  const WARN_THRESHOLD = 80;      // Warn at 80%
  
  try {
    // Get disk usage in percentage
    const output = execSync(`df -h ${PATH} | awk 'NR==2 {print $5}' | tr -d '%'`, {
      encoding: 'utf8',
      timeout: 5000
    }).trim();
    
    const usedPercent = parseInt(output, 10);
    const availablePercent = 100 - usedPercent;
    
    if (usedPercent >= CRITICAL_THRESHOLD) {
      return {
        status: 'critical',
        severity: 'CRITICAL',
        details: {
          path: PATH,
          used_percent: usedPercent,
          available_percent: availablePercent,
          message: `DISK CRITICAL: ${usedPercent}% used (> ${CRITICAL_THRESHOLD}%) - TRADING PAUSED`,
          action: 'PAUSE_TRADING'
        }
      };
    }
    
    if (usedPercent >= WARN_THRESHOLD) {
      return {
        status: 'warn',
        severity: 'WARN',
        details: {
          path: PATH,
          used_percent: usedPercent,
          available_percent: availablePercent,
          message: `DISK WARNING: ${usedPercent}% used (> ${WARN_THRESHOLD}%)`
        }
      };
    }
    
    return {
      status: 'healthy',
      severity: 'HEALTHY',
      details: {
        path: PATH,
        used_percent: usedPercent,
        available_percent: availablePercent,
        message: `DISK OK: ${usedPercent}% used`
      }
    };
    
  } catch (err) {
    return {
      status: 'error',
      severity: 'CRITICAL',
      details: {
        path: PATH,
        error: err.message,
        message: 'DISK CHECK FAILED: Cannot determine disk usage'
      }
    };
  }
}

/**
 * Register a watchdog with Domain classification
 * @param {string} name - Watchdog name
 * @param {number} thresholdMs - Threshold in milliseconds
 * @param {Function} getLastUpdateFn - Function returning last update timestamp
 * @param {Object} options - { domain, severity, onStale }
 */
function watchdog(name, thresholdMs, getLastUpdateFn, options = {}) {
  const domain = options.domain || DOMAIN.SAFETY;  // Watchdogs are SAFETY by default
  
  watchdogs.set(name, {
    threshold: thresholdMs,
    getLastUpdate: getLastUpdateFn,
    domain,
    severity: options.severity || 'CRITICAL',
    onStale: options.onStale || null,
    lastHealthy: Date.now()
  });
  
  Logger.debug(`Watchdog registered: ${name} [${domain}] (threshold: ${thresholdMs}ms)`, { module: 'health' });
}

/**
 * Run a single health check with timeout
 */
async function runSingleCheck(name, config) {
  const startTime = Date.now();
  
  try {
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error(`Timeout after ${config.timeout}ms`)), config.timeout);
    });
    
    const result = await Promise.race([
      config.fn(),
      timeoutPromise
    ]);
    
    const duration = Date.now() - startTime;
    
    return {
      name,
      domain: config.domain,
      status: result.status || 'healthy',
      severity: result.severity || config.severity,
      details: result.details || {},
      duration,
      timestamp: new Date().toISOString(),
      healthy: result.status === 'healthy'
    };
    
  } catch (err) {
    return {
      name,
      domain: config.domain,
      status: 'error',
      severity: config.severity,
      details: { error: err.message },
      duration: Date.now() - startTime,
      timestamp: new Date().toISOString(),
      healthy: false
    };
  }
}

/**
 * Run all registered watchdogs
 */
async function runWatchdogs() {
  const results = [];
  
  for (const [name, config] of watchdogs) {
    try {
      const lastUpdate = config.getLastUpdate();
      const now = Date.now();
      const stale = now - lastUpdate > config.threshold;
      
      const result = {
        name: `watchdog_${name}`,
        domain: config.domain,
        status: stale ? 'stale' : 'healthy',
        severity: stale ? config.severity : 'HEALTHY',
        details: {
          lastUpdate: new Date(lastUpdate).toISOString(),
          threshold: config.threshold,
          staleDuration: stale ? now - lastUpdate - config.threshold : 0
        },
        timestamp: new Date().toISOString(),
        healthy: !stale
      };
      
      results.push(result);
      
      // SAFETY watchdog stale => trigger pause
      if (stale && config.domain === DOMAIN.SAFETY) {
        await triggerSafetyPause(result);
      }
      
      // Call onStale callback if provided
      if (stale && config.onStale) {
        try {
          config.onStale(result);
        } catch (cbErr) {
          Logger.error(`Watchdog onStale callback failed: ${cbErr.message}`, { module: 'health' });
        }
      }
      
    } catch (err) {
      results.push({
        name: `watchdog_${name}`,
        domain: config.domain || DOMAIN.SAFETY,
        status: 'error',
        severity: 'CRITICAL',
        details: { error: err.message },
        timestamp: new Date().toISOString(),
        healthy: false
      });
    }
  }
  
  return results;
}

/**
 * Trigger trading pause due to SAFETY failure
 */
async function triggerSafetyPause(reason) {
  if (isPaused) return;  // Already paused
  
  isPaused = true;
  
  Logger.error(`SAFETY CHECK FAILED: Trading PAUSED`, {
    module: 'health',
    reason: reason.name,
    details: reason.details
  });
  
  // Emit PAUSE event
  await emitHealthEvent('HEALTH_SAFETY_PAUSE', {
    reason: reason.name,
    timestamp: new Date().toISOString(),
    details: reason.details
  });
}

/**
 * Resume trading (manual operation)
 */
function resumeTrading() {
  if (!isPaused) return false;
  
  isPaused = false;
  Logger.info('Trading resumed', { module: 'health' });
  
  emitHealthEvent('HEALTH_SAFETY_RESUME', {
    timestamp: new Date().toISOString()
  });
  
  return true;
}

/**
 * Run all health checks
 * @returns {Object} Full health report with SAFETY/OBSERVABILITY separation
 */
async function runChecks() {
  const checkResults = [];
  
  // Run registered checks
  for (const [name, config] of checks) {
    const result = await runSingleCheck(name, config);
    checkResults.push(result);
    lastResults.set(name, result);
    
    // SAFETY check failed => trigger pause
    if (!result.healthy && result.domain === DOMAIN.SAFETY) {
      await triggerSafetyPause(result);
    }
  }
  
  // Run watchdogs
  const watchdogResults = await runWatchdogs();
  checkResults.push(...watchdogResults);
  
  // Calculate status per domain
  const safetyIssues = checkResults.filter(r => 
    r.domain === DOMAIN.SAFETY && !r.healthy
  );
  const observabilityIssues = checkResults.filter(r => 
    r.domain === DOMAIN.OBSERVABILITY && !r.healthy
  );
  
  let overallStatus = 'healthy';
  if (isPaused) overallStatus = 'paused';
  else if (safetyIssues.length > 0) overallStatus = 'critical';
  else if (observabilityIssues.length > 0) overallStatus = 'degraded';
  
  const report = {
    timestamp: new Date().toISOString(),
    overallStatus,
    isPaused,
    checks: checkResults,
    summary: {
      total: checkResults.length,
      healthy: checkResults.filter(r => r.healthy).length,
      degraded: observabilityIssues.length,
      critical: safetyIssues.length,
      byDomain: {
        SAFETY: {
          total: checkResults.filter(r => r.domain === DOMAIN.SAFETY).length,
          failed: safetyIssues.length
        },
        OBSERVABILITY: {
          total: checkResults.filter(r => r.domain === DOMAIN.OBSERVABILITY).length,
          failed: observabilityIssues.length
        }
      }
    }
  };
  
  // Handle alerts (different handling per domain)
  await handleDomainAlerts(report, safetyIssues, observabilityIssues);
  
  // Emit health status event
  if (safetyIssues.length > 0) {
    await emitHealthEvent('HEALTH_SAFETY_FAILED', report);
  } else if (observabilityIssues.length > 0) {
    await emitHealthEvent('HEALTH_OBSERVABILITY_WARNING', report);
  } else {
    await emitHealthEvent('HEALTH_CHECK_PASSED', report);
  }
  
  return report;
}

/**
 * Handle alerts per domain (SAFETY vs OBSERVABILITY)
 */
async function handleDomainAlerts(report, safetyIssues, observabilityIssues) {
  // SAFETY issues: BLOCK/PAUSE + Event + Log (already triggered in runChecks)
  for (const issue of safetyIssues) {
    Logger.error(`[SAFETY] ${issue.name}: ${issue.status}`, {
      module: 'health',
      domain: 'SAFETY',
      check: issue.name,
      status: issue.status,
      details: issue.details
    });
  }
  
  // OBSERVABILITY issues: WARN + Log (never blocks)
  for (const issue of observabilityIssues) {
    Logger.warn(`[OBSERVABILITY] ${issue.name}: ${issue.status}`, {
      module: 'health',
      domain: 'OBSERVABILITY',
      check: issue.name,
      status: issue.status,
      details: issue.details
    });
  }
  
  // Discord alert for SAFETY issues (always)
  // Discord alert for OBSERVABILITY issues (if configured)
  const minLevel = severityLevel(alertConfig.minSeverity);
  const alertableIssues = report.checks.filter(c => 
    !c.healthy && severityLevel(c.severity) >= minLevel
  );
  
  if (alertConfig.discordWebhook && alertableIssues.length > 0) {
    await sendDiscordAlert(report, alertableIssues);
  }
}

/**
 * Send Discord webhook alert
 */
async function sendDiscordAlert(report, issues) {
  try {
    const safetyIssues = issues.filter(i => i.domain === DOMAIN.SAFETY);
    const obsIssues = issues.filter(i => i.domain === DOMAIN.OBSERVABILITY);
    
    // Safety = Red, Observability = Orange
    const color = safetyIssues.length > 0 ? 0xff0000 : 0xffa500;
    
    const embed = {
      title: `Health Alert [${report.overallStatus.toUpperCase()}]`,
      description: `SAFETY: ${safetyIssues.length}, OBSERVABILITY: ${obsIssues.length}`,
      color: color,
      timestamp: report.timestamp,
      fields: [
        ...safetyIssues.slice(0, 5).map(i => ({
          name: `🔴 SAFETY: ${i.name}`,
          value: `Status: ${i.status}`,
          inline: false
        })),
        ...obsIssues.slice(0, 3).map(i => ({
          name: `⚠️ OBSERVABILITY: ${i.name}`,
          value: `Status: ${i.status}`,
          inline: false
        }))
      ]
    };
    
    const response = await fetch(alertConfig.discordWebhook, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ embeds: [embed] })
    });
    
    if (!response.ok) {
      throw new Error(`Discord returned ${response.status}`);
    }
    
    Logger.info('Discord alert sent', { module: 'health', 
      safety: safetyIssues.length, 
      observability: obsIssues.length 
    });
    
  } catch (err) {
    // Non-blocking: log error but don't fail
    Logger.error(`Failed to send Discord alert: ${err.message}`, { module: 'health' });
  }
}

/**
 * Emit health event to Event Store
 */
async function emitHealthEvent(eventType, payload) {
  try {
    if (!EventStore.db) {
      Logger.warn('Cannot emit health event: EventStore not initialized', { module: 'health' });
      return;
    }
    
    const event = {
      event_id: `health-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      event_type: eventType,
      occurred_at: new Date().toISOString(),
      entity_type: 'health',
      entity_id: 'system',
      payload,
      correlation_id: null,
      causation_id: null
    };
    
    EventStore.append(event);
    Logger.debug(`Health event emitted: ${eventType}`, { module: 'health' });
    
  } catch (err) {
    Logger.error(`Failed to emit health event: ${err.message}`, { module: 'health' });
  }
}

// ============================================================================
// Monitoring Loop
// ============================================================================

function startMonitoring(options = {}) {
  if (isMonitoring) {
    Logger.warn('Health monitoring already running', { module: 'health' });
    return;
  }
  
  const interval = options.interval || DEFAULT_INTERVAL;
  
  isMonitoring = true;
  Logger.info(`Health monitoring started [${interval}ms]`, { module: 'health' });
  
  // Run first check immediately
  runChecks().catch(err => {
    Logger.error(`Initial health check failed: ${err.message}`, { module: 'health' });
  });
  
  // Schedule periodic checks
  monitoringInterval = setInterval(() => {
    runChecks().catch(err => {
      Logger.error(`Health check failed: ${err.message}`, { module: 'health' });
    });
  }, interval);
}

function stopMonitoring() {
  if (!isMonitoring) return;
  
  if (monitoringInterval) {
    clearInterval(monitoringInterval);
    monitoringInterval = null;
  }
  
  isMonitoring = false;
  Logger.info('Health monitoring stopped', { module: 'health' });
}

// ============================================================================
// Configuration
// ============================================================================

function configureAlerts(config) {
  alertConfig = { ...alertConfig, ...config };
  Logger.debug('Alert config updated', { module: 'health' });
}

function getStatus() {
  return {
    isMonitoring,
    isPaused,
    timestamp: new Date().toISOString()
  };
}

// ============================================================================
// Module Exports
// ============================================================================

module.exports = {
  // Registration
  register,
  watchdog,
  
  // Control
  startMonitoring,
  stopMonitoring,
  runChecks,
  resumeTrading,
  
  // Disk Safety (SAFETY level - can pause trading)
  checkDiskSpace,
  
  // Configuration
  configureAlerts,
  
  // Status
  getStatus,
  isPaused: () => isPaused,
  
  // Constants
  DOMAIN,
  SEVERITY: Object.keys(SEVERITY),
  
  // Built-in SAFETY checks
  safetyChecks: {
    event_store: { domain: DOMAIN.SAFETY, severity: 'CRITICAL' },
    state_projection: { domain: DOMAIN.SAFETY, severity: 'CRITICAL' },
    risk_engine: { domain: DOMAIN.SAFETY, severity: 'CRITICAL' },
    watchdog_tick: { domain: DOMAIN.SAFETY, severity: 'CRITICAL' },
    reconcile_positions: { domain: DOMAIN.SAFETY, severity: 'CRITICAL' },
    disk_space: { domain: DOMAIN.SAFETY, severity: 'CRITICAL' }  // 🛡️ DISK SAFETY - can PAUSE trading
  },
  
  // Built-in OBSERVABILITY checks
  observabilityChecks: {
    discord_webhook: { domain: DOMAIN.OBSERVABILITY, severity: 'WARN' },
    logger_fallback: { domain: DOMAIN.OBSERVABILITY, severity: 'WARN' },
    check_latency: { domain: DOMAIN.OBSERVABILITY, severity: 'WARN' }
  },
  
  // For testing
  _reset: () => {
    checks.clear();
    watchdogs.clear();
    lastResults.clear();
    stopMonitoring();
    isPaused = false;
    alertConfig = {
      discordWebhook: null,
      logToFile: true,
      minSeverity: 'WARN'
    };
  }
};
