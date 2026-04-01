#!/usr/bin/env node
/**
 * OpenClaw Forward v5 - Health Server
 * Block 5.3.3: Health Endpoints + Alert Integration
 * 
 * Endpoints:
 *   GET /health/live    - Liveness probe (<10ms)
 *   GET /health/ready   - Readiness probe (<50ms) + Alert Evaluation
 *   GET /health/startup - Startup probe (<1ms)
 *   GET /health         - Aggregated health
 *   GET /alerts         - Active alerts for dashboard
 * 
 * Port: 3000 (configurable via PORT env)
 * 
 * Exit Codes:
 *   0 - Normal shutdown
 *   1 - Startup error
 */

const express = require('express');
const fs = require('fs');
const path = require('path');
const AlertEngine = require('./alertEngine');

const app = express();
const PORT = process.env.PORT || 3000;
const STATE_FILE = path.join(__dirname, '../runtime_validation/state.json');

// Track server start time for uptime
const SERVER_START = Date.now();

// Initialize Alert Engine
const alertEngine = new AlertEngine({
  discordWebhook: process.env.DISCORD_WEBHOOK_URL
});

/**
 * LIVENESS CHECK
 * Minimal: only "is the process alive?"
 * NO state.json dependency
 * NO heartbeat checks
 * NO memory checks
 * Returns 200 if server responds, 503 only on error
 */
app.get('/health/live', (req, res) => {
  // Just return UP - if this endpoint responds, we're alive
  // This is the K8s livenessProbe pattern
  const uptimeSeconds = Math.floor((Date.now() - SERVER_START) / 1000);
  
  res.status(200).json({
    status: "UP",
    component: "liveness",
    timestamp: new Date().toISOString(),
    uptime_seconds: uptimeSeconds
  });
});

/**
 * READINESS CHECK
 * Checks if service can handle requests
 * Includes: state.json access, heartbeat freshness, memory
 * Returns 200 if ready, 503 if not
 */
app.get('/health/ready', (req, res) => {
  const startTime = Date.now();
  const uptimeSeconds = Math.floor((Date.now() - SERVER_START) / 1000);
  let responseData;
  
  // Read state
  let state = null;
  let checks = {};
  
  try {
    if (fs.existsSync(STATE_FILE)) {
      state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
    }
  } catch (e) {
    checks.state_file = "UNREADABLE: " + e.message;
  }
  
  // Check 1: State accessible
  checks.state = state ? "OK" : "MISSING";
  
  // Check 2: Heartbeat freshness (<60s)
  if (state?.last_heartbeat) {
    const lastHeartbeat = new Date(state.last_heartbeat).getTime();
    const secondsAgo = (Date.now() - lastHeartbeat) / 1000;
    checks.heartbeat = secondsAgo < 60 ? "OK" : `STALE (${Math.floor(secondsAgo)}s ago)`;
  } else {
    checks.heartbeat = "NO_DATA";
  }
  
  // Check 3: Memory not critical (<95%)
  if (state?.metrics?.memory_percent) {
    const memPct = parseInt(state.metrics.memory_percent) || 0;
    checks.memory = memPct < 95 ? `OK (${memPct}%)` : `CRITICAL (${memPct}%)`;
  } else {
    checks.memory = "NO_DATA";
  }
  
  // Check 4: Service status
  const validStatuses = ["RUNNING", "COMPLETED"];
  checks.service_status = validStatuses.includes(state?.status) ? state.status : (state?.status || "NO_STATE");
  
  // Check 5: Startup complete
  checks.startup = state?.status !== "STARTING" ? "COMPLETE" : "IN_PROGRESS";
  
  // Determine overall health
  const isHealthy = 
    checks.state === "OK" && 
    checks.heartbeat === "OK" && 
    checks.memory.startsWith("OK") &&
    validStatuses.includes(state?.status);
  
  const responseTime = Date.now() - startTime;
  
  if (isHealthy) {
    responseData = {
      status: "UP",
      component: "readiness",
      timestamp: new Date().toISOString(),
      uptime_seconds: uptimeSeconds,
      checks: checks
    };
    res.status(200).json(responseData);
  } else {
    // Find first failing check
    const failing = Object.entries(checks).find(([k, v]) => 
      !["OK", "COMPLETE", "RUNNING", "COMPLETED"].some(ok => String(v).startsWith(ok)));
    
    responseData = {
      status: "DOWN",
      component: "readiness",
      timestamp: new Date().toISOString(),
      uptime_seconds: uptimeSeconds,
      reason: failing ? `${failing[0]}: ${failing[1]}` : "unknown",
      checks: checks
    };
    res.status(503).json(responseData);
  }
  
  // Alert Evaluation (after response sent)
  const alertResult = alertEngine.evaluate(responseData);
  if (alertResult.fired.length > 0) {
    // Send new alerts to Discord
    alertResult.fired.forEach(alert => {
      alertEngine.sendDiscord(alert);
    });
  }
});

/**
 * STARTUP CHECK
 * Returns 200 if startup complete, 503 if still starting
 */
app.get('/health/startup', (req, res) => {
  const uptimeSeconds = Math.floor((Date.now() - SERVER_START) / 1000);
  const startupDuration = 120; // 2 minutes grace period
  
  let state = null;
  try {
    if (fs.existsSync(STATE_FILE)) {
      state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
    }
  } catch (e) {}
  
  const isStarting = state?.status === "STARTING" || uptimeSeconds < startupDuration;
  
  if (!isStarting) {
    res.status(200).json({
      status: "UP",
      component: "startup",
      timestamp: new Date().toISOString(),
      uptime_seconds: uptimeSeconds,
      startup_phase: "COMPLETE",
      startup_duration_seconds: uptimeSeconds
    });
  } else {
    res.status(503).json({
      status: "DOWN",
      component: "startup",
      timestamp: new Date().toISOString(),
      uptime_seconds: uptimeSeconds,
      startup_phase: "IN_PROGRESS",
      progress_percent: Math.min(100, Math.floor((uptimeSeconds / startupDuration) * 100)),
      message: uptimeSeconds < startupDuration ? 
        `Starting up (${uptimeSeconds}s / ${startupDuration}s)` : 
        "State shows STARTING"
    });
  }
});

/**
 * AGGREGATED HEALTH
 * Combines live + ready
 */
app.get('/health', (req, res) => {
  const uptimeSeconds = Math.floor((Date.now() - SERVER_START) / 1000);
  
  // Quick checks (no external calls)
  let state = null;
  try {
    if (fs.existsSync(STATE_FILE)) {
      state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
    }
  } catch (e) {}
  
  // Liveness: server responds (always UP if we get here)
  const live = true;
  
  // Readiness: state OK + heartbeat fresh + memory OK
  const heartbeatFresh = state?.last_heartbeat ? 
    (Date.now() - new Date(state.last_heartbeat).getTime()) / 1000 < 60 : false;
  const memoryOk = state?.metrics?.memory_percent ? 
    parseInt(state.metrics.memory_percent) < 95 : false;
  const ready = !!state && heartbeatFresh && memoryOk && 
    ["RUNNING", "COMPLETED"].includes(state?.status);
  
  const isHealthy = live && ready;
  
  const components = {
    liveness: live ? "UP" : "DOWN",
    readiness: ready ? "UP" : "DOWN",
    startup: "UP"
  };
  
  if (isHealthy) {
    res.status(200).json({
      status: "UP",
      timestamp: new Date().toISOString(),
      uptime_seconds: uptimeSeconds,
      components: components,
      summary: "All systems operational"
    });
  } else {
    res.status(503).json({
      status: "DOWN",
      timestamp: new Date().toISOString(),
      uptime_seconds: uptimeSeconds,
      components: components,
      reason: ready ? "none" : "readiness_check_failed",
      summary: "Readiness check failed"
    });
  }
});

// Root redirect with Dashboard
app.get('/', (req, res) => {
  const dashboardPath = path.join(__dirname, 'dashboard.html');
  if (fs.existsSync(dashboardPath)) {
    res.sendFile(dashboardPath);
  } else {
    res.json({
      service: "OpenClaw Forward v5 Health Server",
      version: "5.3.1",
      dashboard: "Not installed",
      endpoints: [
        "/health/live",
        "/health/ready", 
        "/health/startup",
        "/health"
      ]
    });
  }
});

/**
 * ALERTS ENDPOINT
 * Returns active alerts for dashboard display
 */
app.get('/alerts', (req, res) => {
  const activeAlerts = alertEngine.getActiveAlerts();
  res.json({
    active: activeAlerts,
    count: activeAlerts.length,
    inGrace: alertEngine.isInGracePeriod(),
    timestamp: new Date().toISOString()
  });
});

// Error handling
app.use((err, req, res, next) => {
  console.error('Health Server Error:', err);
  res.status(500).json({
    status: "DOWN",
    component: "health_server",
    error: "Internal server error"
  });
});

// Start server
const server = app.listen(PORT, () => {
  console.log(`╔════════════════════════════════════════════════════════╗`);
  console.log(`║  Forward v5 Health Server v5.3.3                   ║`);
  console.log(`║  Listening on port ${PORT}                               ║`);
  console.log(`╚════════════════════════════════════════════════════════╝`);
  console.log();
  console.log('Endpoints:');
  console.log(`  http://localhost:${PORT}/health/live`);
  console.log(`  http://localhost:${PORT}/health/ready`);
  console.log(`  http://localhost:${PORT}/health/startup`);
  console.log(`  http://localhost:${PORT}/health`);
  console.log(`  http://localhost:${PORT}/alerts`);
  console.log();
  console.log('Press Ctrl+C to stop');
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('\nShutting down health server...');
  server.close(() => {
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('\nShutting down health server...');
  server.close(() => {
    process.exit(0);
  });
});
