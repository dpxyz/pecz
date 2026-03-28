/**
 * Health Checker - Runtime Validation for Forward V5
 * 
 * Responsibilities:
 * - Poll system health every 5 minutes
 * - Check Event Store, Circuit Breaker, Memory, Logs
 * - Report results to heartbeat service
 * - NO automatic remediation - only reporting
 * 
 * Design: RUNTIME_VALIDATION_DESIGN.md v1.0
 */

const fs = require('fs');
const path = require('path');

// Configuration
const CONFIG = {
  HEALTH_CHECK_INTERVAL_MS: 5 * 60 * 1000, // 5 minutes
  LOG_CHECK_INTERVAL_MS: 30 * 60 * 1000,     // 30 minutes
  MEMORY_THRESHOLD_WARN: 80,                 // %
  MEMORY_THRESHOLD_ERROR: 90,                // %
  LOG_SIZE_THRESHOLD_MB: 1000,               // 1GB per day
  LOG_DIR: './logs',
  EVENT_STORE_PATH: './data/events.db' // Adjust as needed
};

// Store reference to heartbeat service for callbacks
let heartbeatService = null;
let checkTimer = null;
let isRunning = false;

/**
 * Set the heartbeat service reference
 */
function setHeartbeatService(service) {
  heartbeatService = service;
}

/**
 * Check Event Store connectivity
 */
async function checkEventStore() {
  try {
    // Check if event store file exists and is writable
    // This is a placeholder - actual implementation would connect to real Event Store
    const dbExists = fs.existsSync(CONFIG.EVENT_STORE_PATH);
    
    if (!dbExists) {
      return {
        name: 'event_store',
        status: 'WARN',
        details: 'Event store path not found (may be using in-memory)'
      };
    }
    
    // Try to get stats
    const stats = fs.statSync(CONFIG.EVENT_STORE_PATH);
    const age = (Date.now() - stats.mtime.getTime()) / 1000;
    
    return {
      name: 'event_store',
      status: 'OK',
      details: `DB exists, last modified ${age.toFixed(0)}s ago`
    };
  } catch (err) {
    return {
      name: 'event_store',
      status: 'ERROR',
      details: `Access failed: ${err.message}`
    };
  }
}

/**
 * Check Circuit Breaker state
 */
async function checkCircuitBreaker() {
  try {
    // Placeholder - actual implementation would check real Circuit Breaker
    // For now, assume we can read from a state file or check in-memory
    
    // Try to load circuit breaker module if available
    let cbState = 'CLOSED'; // Default
    
    try {
      const circuitBreaker = require('./circuit_breaker');
      if (circuitBreaker.getCurrentState) {
        cbState = circuitBreaker.getCurrentState();
      }
    } catch (e) {
      // Module not available, use default
    }
    
    const status = cbState === 'CLOSED' ? 'OK' : 
                   cbState === 'HALF_OPEN' ? 'WARN' : 'CRITICAL';
    
    return {
      name: 'circuit_breaker',
      status,
      state: cbState,
      details: `Circuit Breaker is ${cbState}`
    };
  } catch (err) {
    return {
      name: 'circuit_breaker',
      status: 'ERROR',
      details: `Check failed: ${err.message}`
    };
  }
}

/**
 * Check memory usage
 */
async function checkMemory() {
  try {
    const memUsage = process.memoryUsage();
    const heapUsed = memUsage.heapUsed / 1024 / 1024; // MB
    const heapTotal = memUsage.heapTotal / 1024 / 1024;
    const percentUsed = (memUsage.heapUsed / memUsage.heapTotal) * 100;
    const rss = memUsage.rss / 1024 / 1024;
    
    let status = 'OK';
    if (percentUsed > CONFIG.MEMORY_THRESHOLD_ERROR) {
      status = 'CRITICAL';
    } else if (percentUsed > CONFIG.MEMORY_THRESHOLD_WARN) {
      status = 'WARN';
    }
    
    return {
      name: 'memory',
      status,
      heap_used_mb: Math.round(heapUsed),
      heap_total_mb: Math.round(heapTotal),
      percent_used: Math.round(percentUsed * 10) / 10,
      rss_mb: Math.round(rss),
      details: `Heap: ${heapUsed.toFixed(1)}/${heapTotal.toFixed(1)} MB (${percentUsed.toFixed(1)}%)`
    };
  } catch (err) {
    return {
      name: 'memory',
      status: 'ERROR',
      details: `Check failed: ${err.message}`
    };
  }
}

/**
 * Check log file sizes
 */
async function checkLogs() {
  try {
    if (!fs.existsSync(CONFIG.LOG_DIR)) {
      return {
        name: 'logs',
        status: 'WARN',
        details: 'Log directory not found'
      };
    }
    
    const files = fs.readdirSync(CONFIG.LOG_DIR);
    const logFiles = files.filter(f => f.endsWith('.log'));
    
    let totalSizeMB = 0;
    const fileDetails = [];
    
    for (const file of logFiles) {
      const filePath = path.join(CONFIG.LOG_DIR, file);
      const stats = fs.statSync(filePath);
      const sizeMB = stats.size / 1024 / 1024;
      totalSizeMB += sizeMB;
      
      if (sizeMB > CONFIG.LOG_SIZE_THRESHOLD_MB) {
        fileDetails.push(`${file}: ${sizeMB.toFixed(1)}MB (needs rotation)`);
      }
    }
    
    const status = totalSizeMB > CONFIG.LOG_SIZE_THRESHOLD_MB ? 'WARN' : 'OK';
    const details = fileDetails.length > 0 
      ? `Large files: ${fileDetails.join(', ')}` 
      : `Total: ${totalSizeMB.toFixed(1)}MB`;
    
    return {
      name: 'logs',
      status,
      total_size_mb: Math.round(totalSizeMB * 100) / 100,
      large_files: fileDetails.length,
      details
    };
  } catch (err) {
    return {
      name: 'logs',
      status: 'ERROR',
      details: `Check failed: ${err.message}`
    };
  }
}

/**
 * Check process uptime
 */
async function checkUptime() {
  try {
    const uptimeSeconds = process.uptime();
    const uptimeHours = uptimeSeconds / 3600;
    
    return {
      name: 'uptime',
      status: 'OK',
      uptime_seconds: Math.floor(uptimeSeconds),
      uptime_hours: Math.round(uptimeHours * 100) / 100,
      details: `Process running for ${uptimeHours.toFixed(2)} hours`
    };
  } catch (err) {
    return {
      name: 'uptime',
      status: 'ERROR',
      details: `Check failed: ${err.message}`
    };
  }
}

/**
 * Perform single health check
 */
async function performHealthCheck() {
  const results = {
    timestamp: new Date().toISOString(),
    overall: 'OK',
    checks: []
  };
  
  // Run all checks
  const checks = [
    await checkEventStore(),
    await checkCircuitBreaker(),
    await checkMemory(),
    await checkUptime(),
    await checkLogs()
  ];
  
  results.checks = checks;
  
  // Determine overall status
  const hasCritical = checks.some(c => c.status === 'CRITICAL');
  const hasError = checks.some(c => c.status === 'ERROR');
  const hasWarn = checks.some(c => c.status === 'WARN');
  
  if (hasCritical) {
    results.overall = 'CRITICAL';
  } else if (hasError) {
    results.overall = 'ERROR';
  } else if (hasWarn) {
    results.overall = 'WARN';
  }
  
  // Report to heartbeat service if available
  if (heartbeatService && heartbeatService.handleHealthCheckResults) {
    heartbeatService.handleHealthCheckResults(results);
  }
  
  return results;
}

/**
 * Health check loop
 */
function healthCheckLoop() {
  if (!isRunning) return;
  
  performHealthCheck()
    .then(results => {
      console.log(`[${new Date().toISOString()}] Health Check: ${results.overall}`);
      if (results.overall !== 'OK') {
        console.log(`  Details:`, JSON.stringify(results.checks.map(c => 
          ({ name: c.name, status: c.status })), null, 2));
      }
    })
    .catch(err => {
      console.error(`[${new Date().toISOString()}] Health Check Error:`, err.message);
      
      // Report error to heartbeat service
      if (heartbeatService && heartbeatService.sendAlert) {
        heartbeatService.sendAlert('ERROR', 'Health Check Loop Failed', err.message);
      }
    });
  
  // Schedule next check
  checkTimer = setTimeout(healthCheckLoop, CONFIG.HEALTH_CHECK_INTERVAL_MS);
}

/**
 * Start the health checker
 */
function start(service = null) {
  if (isRunning) {
    console.log('Health checker already running');
    return;
  }
  
  if (service) {
    heartbeatService = service;
  }
  
  isRunning = true;
  
  // Start loop
  healthCheckLoop();
  
  console.log('Health checker started');
  
  // Also run immediate check
  performHealthCheck();
}

/**
 * Stop the health checker
 */
function stop() {
  isRunning = false;
  
  if (checkTimer) {
    clearTimeout(checkTimer);
    checkTimer = null;
  }
  
  console.log('Health checker stopped');
}

/**
 * Get current health status (synchronous)
 */
function getHealthStatus() {
  return performHealthCheck();
}

// Exports
module.exports = {
  start,
  stop,
  setHeartbeatService,
  performHealthCheck,
  getHealthStatus,
  checkEventStore,
  checkCircuitBreaker,
  checkMemory,
  checkLogs,
  checkUptime,
  CONFIG
};

// Auto-start if called directly with service passed
if (require.main === module) {
  start();
  
  // Keep process alive
  setInterval(() => {}, 1000);
}
