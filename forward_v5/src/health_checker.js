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
  EVENT_STORE_PATH: process.env.EVENT_STORE_PATH || './runtime/event_store.db',
  MEMORY_HISTORY_MINUTES: 60,                // Track memory for trend calculation
  MEMORY_ALERT_THRESHOLD_PERCENT: 10         // Max 10% growth over 6h window
};

// Store reference to heartbeat service for callbacks
let heartbeatService = null;
let checkTimer = null;
let isRunning = false;

// Memory history for trend calculation (P1 Fix)
const memoryHistory = [];
const MAX_HISTORY_SAMPLES = 72; // 6 hours of samples every 5 min

// Health check counter (P2 Fix)
const healthCheckStats = {
  total: 0,
  passed: 0,
  failed: 0,
  lastCheckTime: null
};

/**
 * Set the heartbeat service reference
 */
function setHeartbeatService(service) {
  heartbeatService = service;
}

/**
 * Check Event Store connectivity
 * P0: Enforce persistent event store
 */
async function checkEventStore() {
  try {
    // P0 Fix: Check EVENT_STORE_PATH is configured
    if (!process.env.EVENT_STORE_PATH) {
      return {
        name: 'event_store',
        status: 'CRITICAL',
        details: 'EVENT_STORE_PATH not set - in-memory mode not allowed for validation'
      };
    }
    
    // Check if event store file exists and is writable
    const dbExists = fs.existsSync(CONFIG.EVENT_STORE_PATH);
    
    if (!dbExists) {
      return {
        name: 'event_store',
        status: 'CRITICAL',
        details: 'Event store path not found - persistent store required'
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
 * Check memory usage with trend analysis (P1 Fix v2 - 5.0b)
 * Uses linear regression on filtered samples to calculate true trend,
 * filtering out GC spikes and startup artifacts
 */
async function checkMemory() {
  try {
    const memUsage = process.memoryUsage();
    const heapUsed = memUsage.heapUsed / 1024 / 1024; // MB
    const heapTotal = memUsage.heapTotal / 1024 / 1024;
    const percentUsed = (memUsage.heapUsed / memUsage.heapTotal) * 100;
    const rss = memUsage.rss / 1024 / 1024;
    const now = Date.now();
    
    // Add to history (P1 Fix)
    memoryHistory.push({
      timestamp: now,
      percentUsed: Math.round(percentUsed * 10) / 10,
      heapUsed: Math.round(heapUsed * 10) / 10
    });
    
    // Keep only samples from last 6 hours
    const cutoffTime = now - (6 * 60 * 60 * 1000); // 6 hours ago
    while (memoryHistory.length > 0 && memoryHistory[0].timestamp < cutoffTime) {
      memoryHistory.shift();
    }
    
    // Trim to max samples
    while (memoryHistory.length > MAX_HISTORY_SAMPLES) {
      memoryHistory.shift();
    }
    
    // P1 Fix v2 (5.0b): Filter GC spikes - only keep samples >5min apart
    const filteredSamples = [];
    let lastSampleTime = 0;
    for (let i = memoryHistory.length - 1; i >= 0; i--) {
      const sample = memoryHistory[i];
      if (filteredSamples.length === 0 || (lastSampleTime - sample.timestamp) >= CONFIG.HEALTH_CHECK_INTERVAL_MS) {
        filteredSamples.unshift(sample);
        lastSampleTime = sample.timestamp;
      }
    }
    
    // Calculate growth trend using linear regression (proper method)
    let growthPercent = 0;
    let trendReliability = 'insufficient_data';
    
    if (filteredSamples.length >= 12) { // Need at least 1 hour of filtered data
      // Linear regression: y = mx + b
      // x = time in hours (relative to first sample)
      // y = percentUsed
      const n = filteredSamples.length;
      const firstTime = filteredSamples[0].timestamp;
      
      let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
      for (let i = 0; i < n; i++) {
        const sample = filteredSamples[i];
        const x = (sample.timestamp - firstTime) / (1000 * 60 * 60); // hours
        const y = sample.percentUsed;
        sumX += x;
        sumY += y;
        sumXY += x * y;
        sumXX += x * x;
      }
      
      const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
      growthPercent = slope * 6; // Convert to 6-hour growth
      trendReliability = 'sufficient';
    }
    
    // P1 Fix v2 (5.0b): Determine status with startup delay (first 30 min no trend alerts)
    const uptimeMinutes = process.uptime() / 60;
    const startupPeriod = uptimeMinutes < 30;
    
    let status = 'OK';
    if (percentUsed > CONFIG.MEMORY_THRESHOLD_ERROR) {
      status = 'CRITICAL';
    } else if (percentUsed > CONFIG.MEMORY_THRESHOLD_WARN) {
      status = 'WARN';
    } else if (!startupPeriod && trendReliability === 'sufficient' && 
               Math.abs(growthPercent) >= CONFIG.MEMORY_ALERT_THRESHOLD_PERCENT) {
      // P1 Fix v2: Only alert on sustained trend after startup period
      status = growthPercent > 0 ? 'CRITICAL' : 'WARN';
    }
    
    return {
      name: 'memory',
      status,
      heap_used_mb: Math.round(heapUsed),
      heap_total_mb: Math.round(heapTotal),
      percent_used: Math.round(percentUsed * 10) / 10,
      rss_mb: Math.round(rss),
      growth_percent: Math.round(growthPercent * 10) / 10,
      samples_count: memoryHistory.length,
      details: `Heap: ${heapUsed.toFixed(1)}/${heapTotal.toFixed(1)} MB (${percentUsed.toFixed(1)}%), Trend: ${growthPercent > 0 ? '+' : ''}${growthPercent.toFixed(1)}% over 6h`
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
 * P2 Fix: Track health check statistics correctly
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
  
  // P2 Fix: Update health check statistics
  healthCheckStats.total++;
  healthCheckStats.lastCheckTime = Date.now();
  if (results.overall === 'OK') {
    healthCheckStats.passed++;
  } else {
    healthCheckStats.failed++;
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
 * Get health check statistics (P2 Fix)
 */
function getHealthCheckStats() {
  return {
    ...healthCheckStats,
    passRate: healthCheckStats.total > 0 
      ? Math.round((healthCheckStats.passed / healthCheckStats.total) * 100 * 10) / 10 
      : 0
  };
}

/**
 * Reset health check statistics
 */
function resetHealthCheckStats() {
  healthCheckStats.total = 0;
  healthCheckStats.passed = 0;
  healthCheckStats.failed = 0;
  healthCheckStats.lastCheckTime = null;
  memoryHistory.length = 0;
}

/**
 * Start the health checker
 * P0 Fix: Pre-flight check for EVENT_STORE_PATH
 */
function start(service = null) {
  if (isRunning) {
    console.log('Health checker already running');
    return;
  }
  
  // P0 Fix: Pre-flight check - EVENT_STORE_PATH must be set and writable
  if (!process.env.EVENT_STORE_PATH) {
    console.error('CRITICAL: EVENT_STORE_PATH environment variable not set');
    console.error('Persistent event store is required for validation runs');
    throw new Error('EVENT_STORE_PATH not configured');
  }
  
  const eventStoreDir = path.dirname(CONFIG.EVENT_STORE_PATH);
  if (!fs.existsSync(eventStoreDir)) {
    try {
      fs.mkdirSync(eventStoreDir, { recursive: true });
      console.log(`Created event store directory: ${eventStoreDir}`);
    } catch (err) {
      console.error(`CRITICAL: Cannot create event store directory: ${eventStoreDir}`);
      throw new Error(`EVENT_STORE_PATH not writable: ${err.message}`);
    }
  }
  
  if (service) {
    heartbeatService = service;
  }
  
  isRunning = true;
  
  // Reset stats on start (P2 Fix)
  resetHealthCheckStats();
  
  console.log('Health checker started');
  console.log(`Event Store: ${CONFIG.EVENT_STORE_PATH}`);
  
  // Start loop
  healthCheckLoop();
  
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
  getHealthCheckStats,
  resetHealthCheckStats,
  checkEventStore,
  checkCircuitBreaker,
  checkMemory,
  checkLogs,
  checkUptime,
  CONFIG,
  memoryHistory
};

// Auto-start if called directly with service passed
if (require.main === module) {
  start();
  
  // Keep process alive
  setInterval(() => {}, 1000);
}
