/**
 * Block 3.2: Health Service
 *
 * Continuous health checks with Discord/webhook alerts.
 * Non-blocking: Health failures NEVER block trading directly.
 *
 * Severity:
 * - WARN: Log + Alert, trading continues
 * - CRITICAL: Log + Alert + Event, may trigger pause via event handler
 *
 * @module health
 * @version 1.0.0
 */

const Logger = require('./logger.js');
const EventStore = require('./event_store.js');

// ============================================================================
// Configuration
// ============================================================================

const DEFAULT_INTERVAL = 30000; // 30 seconds
const DEFAULT_WATCHDOG_TIMEOUT = 30000; // 30 seconds for stale detection

// ============================================================================
// State
// ============================================================================

const checks = new Map();
const watchdogs = new Map();
let monitoringInterval = null;
let isMonitoring = false;
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

/**
 * Convert severity string to level number
 */
function severityLevel(severity) {
  return SEVERITY[severity.toUpperCase()] || SEVERITY.HEALTHY;
}

// ============================================================================
// Core Health Check Functions
// ============================================================================

/**
 * Register a health check
 * @param {string} name - Check name
 * @param {Function} checkFn - Async function returning { status, details, severity? }
 * @param {Object} options - { severity: 'WARN'|'CRITICAL', timeout: ms }
 */
function register(name, checkFn, options = {}) {
  checks.set(name, {
    fn: checkFn,
    severity: options.severity || 'WARN',
    timeout: options.timeout || 5000
  });
  Logger.debug(`Health check registered: ${name}`, { module: 'health' });
}

/**
 * Register a watchdog for stale detection
 * @param {string} name - Watchdog name
 * @param {number} thresholdMs - Threshold in milliseconds
 * @param {Function} getLastUpdateFn - Function returning last update timestamp
 * @param {Object} options - { severity, onStale }
 */
function watchdog(name, thresholdMs, getLastUpdateFn, options = {}) {
  watchdogs.set(name, {
    threshold: thresholdMs,
    getLastUpdate: getLastUpdateFn,
    severity: options.severity || 'CRITICAL',
    onStale: options.onStale || null,
    lastHealthy: Date.now()
  });
  Logger.debug(`Watchdog registered: ${name} (threshold: ${thresholdMs}ms)`, { module: 'health' });
}

/**
 * Run a single health check with timeout
 */
async function runSingleCheck(name, config) {
  const startTime = Date.now();
  
  try {
    // Create timeout promise
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error(`Timeout after ${config.timeout}ms`)), config.timeout);
    });
    
    // Run check with timeout
    const result = await Promise.race([
      config.fn(),
      timeoutPromise
    ]);
    
    const duration = Date.now() - startTime;
    
    return {
      name,
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
 * Run all health checks
 * @returns {Object} Full health report
 */
async function runChecks() {
  const checkResults = [];
  
  // Run registered checks
  for (const [name, config] of checks) {
    const result = await runSingleCheck(name, config);
    checkResults.push(result);
    lastResults.set(name, result);
  }
  
  // Run watchdogs
  const watchdogResults = await runWatchdogs();
  checkResults.push(...watchdogResults);
  
  // Calculate overall status
  const criticalCount = checkResults.filter(r => r.severity === 'CRITICAL' && !r.healthy).length;
  const warnCount = checkResults.filter(r => r.severity === 'WARN' && !r.healthy).length;
  
  let overallStatus = 'healthy';
  if (criticalCount > 0) overallStatus = 'critical';
  else if (warnCount > 0) overallStatus = 'degraded';
  
  const report = {
    timestamp: new Date().toISOString(),
    overallStatus,
    checks: checkResults,
    summary: {
      total: checkResults.length,
      healthy: checkResults.filter(r => r.healthy).length,
      degraded: warnCount,
      critical: criticalCount
    }
  };
  
  // Alert on issues
  await maybeAlert(report);
  
  // Emit event for critical issues
  if (criticalCount > 0) {
    await emitHealthEvent('HEALTH_CHECK_FAILED', report);
  } else if (overallStatus === 'healthy') {
    await emitHealthEvent('HEALTH_CHECK_PASSED', report);
  }
  
  return report;
}

/**
 * Emit health event to Event Store
 */
async function emitHealthEvent(eventType, report) {
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
      payload: report,
      correlation_id: report.correlation_id || null,
      causation_id: null
    };
    
    EventStore.append(event);
    Logger.debug(`Health event emitted: ${eventType}`, { module: 'health', event_id: event.event_id });
    
  } catch (err) {
    Logger.error(`Failed to emit health event: ${err.message}`, { module: 'health' });
  }
}

/**
 * Send alert if severity threshold met
 */
async function maybeAlert(report) {
  const minLevel = severityLevel(alertConfig.minSeverity);
  
  const issues = report.checks.filter(c => 
    !c.healthy && severityLevel(c.severity) >= minLevel
  );
  
  if (issues.length === 0) return;
  
  // Log all issues
  for (const issue of issues) {
    const logFn = issue.severity === 'CRITICAL' ? Logger.error : Logger.warn;
    logFn(`Health check failed: ${issue.name}`, { 
      module: 'health',
      check: issue.name,
      severity: issue.severity,
      status: issue.status,
      details: issue.details
    });
  }
  
  // Discord webhook alert
  if (alertConfig.discordWebhook) {
    await sendDiscordAlert(report, issues);
  }
}

/**
 * Send Discord webhook alert
 */
async function sendDiscordAlert(report, issues) {
  try {
    const criticalIssues = issues.filter(i => i.severity === 'CRITICAL');
    const color = criticalIssues.length > 0 ? 0xff0000 : 0xffa500; // Red or Orange
    
    const embed = {
      title: `⚠️ Health Alert: ${report.overallStatus.toUpperCase()}`,
      color: color,
      timestamp: report.timestamp,
      fields: issues.map(issue => ({
        name: `${issue.severity}: ${issue.name}`,
        value: `Status: ${issue.status}\nDuration: ${issue.duration || 'N/A'}ms`,
        inline: false
      }))
    };
    
    const response = await fetch(alertConfig.discordWebhook, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ embeds: [embed] })
    });
    
    if (!response.ok) {
      throw new Error(`Discord returned ${response.status}`);
    }
    
    Logger.info('Discord alert sent', { module: 'health', issues: issues.length });
    
  } catch (err) {
    // Non-blocking: log error but don't fail
    Logger.error(`Failed to send Discord alert: ${err.message}`, { module: 'health' });
  }
}

// ============================================================================
// Monitoring Loop
// ============================================================================

/**
 * Start continuous monitoring
 * @param {Object} options - { interval: ms }
 */
function startMonitoring(options = {}) {
  if (isMonitoring) {
    Logger.warn('Health monitoring already running', { module: 'health' });
    return;
  }
  
  const interval = options.interval || DEFAULT_INTERVAL;
  
  isMonitoring = true;
  Logger.info(`Health monitoring started (interval: ${interval}ms)`, { module: 'health' });
  
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

/**
 * Stop continuous monitoring
 */
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

/**
 * Configure alerting
 * @param {Object} config
 */
function configureAlerts(config) {
  alertConfig = {
    ...alertConfig,
    ...config
  };
  Logger.debug('Alert configuration updated', { module: 'health', minSeverity: alertConfig.minSeverity });
}

/**
 * Get current health status (last run)
 */
function getStatus() {
  return {
    isMonitoring,
    lastCheck: lastResults.size > 0 ? Array.from(lastResults.values()) : null,
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
  
  // Configuration
  configureAlerts,
  
  // Status
  getStatus,
  
  // Built-in severity levels
  SEVERITY: Object.keys(SEVERITY),
  
  // For testing
  _reset: () => {
    checks.clear();
    watchdogs.clear();
    lastResults.clear();
    stopMonitoring();
    alertConfig = {
      discordWebhook: null,
      logToFile: true,
      minSeverity: 'WARN'
    };
  }
};
